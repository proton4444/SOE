"""
Web server for SOE — humans in the browser, agents over JSON.

Run locally with:
    uvicorn webapp.main:app --port 8000

Humans get a minimal HTMX UI; agents get the /api endpoints, where a per-room
agent key is the only credential (header ``X-Agent-Key`` or ``key`` query
param).
"""

from __future__ import annotations

import hashlib
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import (
    BackgroundTasks,
    FastAPI,
    Form,
    HTTPException,
    Query,
    Request,
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from soe import __version__, map_loader

from webapp import (
    backups,
    blueprints,
    coaches,
    coach_ui,
    competition,
    debrief,
    alpha,
    mapimg,
    mapview,
    net,
    ratelimit,
    service,
    training,
)
from webapp.ai import autoplay, bot_jobs, brain, orchestrator
from webapp.ai.registry import AgentProfile, default_registry
from webapp.blueprints import (
    BlueprintAccessError,
    BlueprintError,
    BlueprintIntegrityError,
)
from webapp.coaches import Coach, CoachAuthError, CoachError
from webapp.observability import logger, request_id
from webapp.rooms import (
    GAMES_ROOT,
    SERVER_DATA,
    Room,
    RoomError,
    RoomPlayer,
    default_store,
)

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Jobs left running when the last process died go back on the queue."""
    if not OPERATOR_KEY:
        logger.warning(
            "operator_key_unset: operator routes fall back to this server's own "
            "console. Set SOE_OPERATOR_KEY before putting a proxy in front."
        )
    competition.default_store().requeue_orphans()
    yield


app = FastAPI(
    title="SOE",
    version=__version__,
    lifespan=_lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

_TEMPLATES = Path(__file__).resolve().parent / "templates"
_STATIC = Path(__file__).resolve().parent / "static"

templates = Jinja2Templates(directory=str(_TEMPLATES))
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

_store = default_store()

HOST_COOKIE = "soe_host"
PLAYER_COOKIE = "soe_player"
BETA_INVITE_HEADER = "X-SOE-Beta-Invite"
#: A coach key is a separate credential from a room's seat key: it proves who
#: owns a blueprint, not who holds a seat.
COACH_KEY_HEADER = "X-Coach-Key"
COACH_COOKIE = "soe_coach"
#: One-shot display of the plaintext key after register. Not the session.
COACH_FLASH_COOKIE = "soe_coach_once"
BETA_ACCESS_CODE = os.environ.get("SOE_BETA_ACCESS_CODE", "").strip()
# The server's LLM key and the URL that key is sent to are operator property,
# not room property: anyone can create a room, so a host cookie is not proof
# of anything here. Without a configured secret only the server's own console
# qualifies.
OPERATOR_COOKIE = "soe_operator"
OPERATOR_HEADER = "X-SOE-Operator-Key"
OPERATOR_KEY = os.environ.get("SOE_OPERATOR_KEY", "").strip()
_LOOPBACK_CLIENTS = frozenset({"127.0.0.1", "::1", "localhost"})
_cookie_secure_env = os.environ.get("SOE_COOKIE_SECURE", "").strip().lower()
#: Secure-by-default once an operator key exists: that flag is the "this is a
#: real deployment" signal, and auth cookies over plain http are then a
#: mistake rather than a convenience. An explicit env value still wins.
COOKIE_SECURE = (
    _cookie_secure_env in {"1", "true", "yes", "on"}
    if _cookie_secure_env
    else bool(OPERATOR_KEY)
)
COOKIE_MAX_AGE = 30 * 24 * 60 * 60
#: The ``?key=`` fallback predates taking proxy access logs seriously: a URL
#: credential leaks into logs, history and Referer headers. It stays because
#: documented agents still use it, but it is deprecated -- prefer the header.
#: Set SOE_REJECT_QUERY_KEYS=1 to refuse query credentials outright once
#: every caller has migrated.
REJECT_QUERY_KEYS = os.environ.get("SOE_REJECT_QUERY_KEYS", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_query_credential_warned = False


def _accept_query_credential(
    request: Request, value: Optional[str], what: str
) -> str:
    """The deprecated ``?key=`` fallback: warn once, or refuse when hardened."""
    global _query_credential_warned
    value = value or ""
    if not value:
        return ""
    if REJECT_QUERY_KEYS:
        raise HTTPException(401, f"{what} must be sent in a header, not the URL.")
    if not _query_credential_warned:
        _query_credential_warned = True
        logger.warning(
            "credential_in_query what=%s path=%s -- deprecated; send it as a "
            "header instead. SOE_REJECT_QUERY_KEYS=1 refuses this.",
            what,
            request.url.path,
        )
    return value


def _operator_session_value() -> str:
    """Cookie value derived from the operator key, not the key itself.

    A browser holds this for 30 days; a stolen cookie must not be a stolen
    credential. Rotating ``SOE_OPERATOR_KEY`` invalidates every session at
    once, which is exactly what a raw-key cookie could not promise.
    """
    return hashlib.sha256(
        f"soe-operator-session:{OPERATOR_KEY}".encode()
    ).hexdigest()


@app.middleware("http")
async def safe_request_logging(request: Request, call_next):
    """Log request metadata only; never log headers, query values, or bodies."""
    rid = request_id()
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request_failed request_id=%s method=%s path=%s",
            rid,
            request.method,
            request.url.path,
        )
        raise
    duration_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = rid
    logger.info(
        "request_completed request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
        rid,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


def _player_cookie_name(code: str) -> str:
    return f"{PLAYER_COOKIE}_{code}"


def _host_cookie_name(code: str) -> str:
    return f"{HOST_COOKIE}_{code}"


def _set_auth_cookie(response, name: str, value: str) -> None:
    response.set_cookie(
        name,
        value,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=COOKIE_MAX_AGE,
    )


def _require_beta_invite(request: Request, supplied: str = "") -> None:
    """Require the operator-supplied invite code when beta mode enables it."""
    if BETA_ACCESS_CODE and not (
        net.secret_eq(request.headers.get(BETA_INVITE_HEADER), BETA_ACCESS_CODE)
        or net.secret_eq(str(supplied or "").strip(), BETA_ACCESS_CODE)
    ):
        raise HTTPException(403, "A valid beta invitation is required.")


def _is_operator(request: Request, supplied: str = "") -> bool:
    """True for the server operator, never merely for a room host."""
    if OPERATOR_KEY:
        offered = (
            request.headers.get(OPERATOR_HEADER, ""),
            str(supplied or "").strip(),
        )
        if any(
            secrets.compare_digest(value, OPERATOR_KEY) for value in offered if value
        ):
            return True
        # The browser session carries a derived value, never the key itself.
        cookie = request.cookies.get(OPERATOR_COOKIE, "")
        return bool(cookie) and secrets.compare_digest(
            cookie, _operator_session_value()
        )
    # Without a configured secret only the server's own console qualifies --
    # and only when it reached us directly. Both documented deployments put a
    # TLS terminator on this host and forward to 127.0.0.1, so every visitor
    # on the internet arrives from a loopback address: trusting loopback on a
    # proxied request would hand the operator's seat to all of them.
    # `scripts/start_beta.ps1` refuses to start without the key; this is what
    # stands behind that when someone runs uvicorn by hand.
    if net.arrived_via_proxy(request):
        return False
    client = request.client
    return (client.host if client else "").strip().lower() in _LOOPBACK_CLIENTS


def _require_operator(request: Request, supplied: str = "") -> None:
    if _is_operator(request, supplied):
        return
    raise HTTPException(
        403,
        f"LLM settings are operator-only: send {OPERATOR_HEADER}."
        if OPERATOR_KEY
        else "LLM settings are operator-only: set SOE_OPERATOR_KEY, or reach "
        "this server from its own console without a proxy in between.",
    )


def _remember_operator(response, supplied: str) -> None:
    """Keep a browser operator signed in after a correct key.

    The cookie stores the derived session value, not the key: see
    ``_operator_session_value``.
    """
    supplied = str(supplied or "").strip()
    if OPERATOR_KEY and supplied and secrets.compare_digest(supplied, OPERATOR_KEY):
        _set_auth_cookie(response, OPERATOR_COOKIE, _operator_session_value())


def _resolve_room(code: str) -> Room:
    room = _store.get(code)
    if not room:
        raise HTTPException(404, "No game found with that code.")
    return room


def _player_for(
    room: Room, request: Request, key: Optional[str]
) -> RoomPlayer | None:
    if key:
        return room.player_by_key(key)
    cookie = request.cookies.get(_player_cookie_name(room.code))
    if cookie:
        return room.player_by_key(cookie)
    return None


def _submission_text(room: Room, player: RoomPlayer | None) -> str:
    if not player:
        return ""
    return (
        room.submissions.get(room.next_turn(), {})
        .get(player.faction_id, {})
        .get("orders", "")
    )


def _panel_context(
    request: Request,
    room: Room,
    player: RoomPlayer | None,
    is_host: bool,
    notice: str = "",
) -> dict:
    return {
        "room": room,
        "player": player,
        "is_host": is_host,
        "status": service.room_status(room),
        "notice": notice,
        "pin": room.pin if is_host else "",
        "submission_text": _submission_text(room, player),
        "map_file": room.map_file,
        # In a room the map is the live board, seen from this player's seat.
        # The host with no seat, and anyone before the game starts, gets the
        # plain published map.
        "map_svg": _map_svg(room.map_file, _overlay_for(room, player)),
        "map_islands": _map_islands(room.map_file),
        "beta_invite_required": bool(BETA_ACCESS_CODE),
    }


def _master_context(
    room: Room, notice: str = "", phase: str = "", faction: str = ""
) -> dict:
    return {
        "room": room,
        "notice": notice,
        "phase": phase,
        "faction": faction,
        "autoplay": autoplay.default_controller().status(),
        **service.master_dashboard(room, phase_filter=phase, faction_filter=faction),
    }


def _setup_context(room: Room, notice: str = "", request: Request | None = None) -> dict:
    from webapp import llm_settings

    registry = default_registry()
    slots = []
    for player in room.players:
        profile = registry.get(room.code, player.faction_id)
        slots.append(
            {
                "slot": player.slot,
                "faction_id": player.faction_id,
                "faction_name": player.faction_name,
                "kind": player.kind,
                "display_name": player.display_name,
                "key": player.agent_key if player.kind != "empty" else "",
                "profile": profile or AgentProfile(),
                "has_profile": profile is not None,
            }
        )
    return {
        "room": room,
        "slots": slots,
        "notice": notice,
        "llm": llm_settings.public_settings(),
        "llm_env": {
            "base_url": bool(os.environ.get("SOE_LLM_BASE", "").strip()),
            "key": bool(os.environ.get("SOE_LLM_KEY", "").strip()),
            "model": os.environ.get("SOE_LLM_MODEL", "").strip(),
        },
        "is_operator": bool(request is not None and _is_operator(request)),
        "operator_key_required": bool(OPERATOR_KEY),
        "allowed_base_hosts": llm_settings.allowed_base_hosts(),
    }


def _require_master(request: Request, room: Room) -> None:
    if not net.secret_eq(
        request.cookies.get(_host_cookie_name(room.code)), room.host_key
    ):
        raise HTTPException(403, "The master dashboard requires the host session.")


def _my_games(request: Request, current_code: str) -> list[dict]:
    """Other games this browser already holds a valid host cookie for.

    Deliberately not every room on the server: anyone can create a room and
    become its host, so a switcher that listed every game would hand that
    host every other room's session out through a shared page. Reading only
    cookies already on this request keeps each room's host session private
    to whoever is actually holding it.
    """
    out = []
    for r in default_store().all():
        if r.code == current_code:
            continue
        if not net.secret_eq(request.cookies.get(_host_cookie_name(r.code)), r.host_key):
            continue
        out.append(
            {
                "code": r.code,
                "name": r.name,
                "turn": r.last_resolved_turn,
                "joined": len(r.joined_players()),
                "slots": r.slots,
            }
        )
    out.sort(key=lambda d: d["code"])
    return out


def _overlay_for(room: Room, player) -> Optional[dict]:
    if player is None:
        return None
    try:
        return service.map_overlay(room, player.faction_id)
    except Exception:  # a broken save must not take the whole page down
        return None


# ============================================================================
# pages (humans)
# ============================================================================


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    maps = service.available_maps()
    chosen = service.default_map()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "maps": maps,
            "default_map": chosen,
            "map_svg": _map_fragment(chosen) if maps else "",
            "legend": mapview.legend_html(),
            "error": request.query_params.get("error", ""),
            "beta_invite_required": bool(BETA_ACCESS_CODE),
            "is_any_host": _any_host_session(request),
            "llm_summary": _llm_summary(),
            "llm_env_key": bool(os.environ.get("SOE_LLM_KEY", "").strip()),
            "is_operator": _is_operator(request),
        },
    )


def _any_host_session(request: Request) -> bool:
    """True when the request carries a valid host cookie for any room."""
    return any(
        net.secret_eq(request.cookies.get(_host_cookie_name(r.code)), r.host_key)
        for r in default_store().all()
    )


def _llm_summary() -> dict:
    from webapp import llm_settings

    return llm_settings.public_settings()


@app.get("/healthz")
def healthz():
    """Non-sensitive liveness/readiness check for manual operator monitoring."""
    return {
        "status": "ok",
        "version": __version__,
        "storage": {
            "server_data": SERVER_DATA.is_dir(),
            "games_root": GAMES_ROOT.is_dir(),
            "backup_root": backups.BACKUP_ROOT.is_dir(),
        },
        "ai": {
            "configured": brain.is_configured(),
        },
        "single_worker_required": True,
    }


def _map_svg(name: str, overlay: Optional[dict] = None) -> str:
    try:
        return mapview.render_svg(name, overlay)
    except FileNotFoundError:
        return ""


def _map_fragment(name: str) -> str:
    try:
        return mapview.render_map_fragment(name)
    except FileNotFoundError:
        return ""


def _map_islands(name: str) -> str:
    try:
        return mapview.islands_html(name)
    except FileNotFoundError:
        return ""


@app.get("/map/{name}", response_class=HTMLResponse)
def map_preview(name: str):
    """HTMX fragment: SVG + landmass index for one map.

    Unauthenticated, so the name is checked against the playable-map list
    rather than merely being resolved inside ``maps/``.
    """
    if name not in service.available_maps():
        raise HTTPException(404, "No such map.")
    try:
        return mapview.render_map_fragment(name)
    except FileNotFoundError:
        raise HTTPException(404, "No such map.")


@app.post("/create")
def create_room(
    request: Request,
    name: str = Form(""),
    slots: int = Form(2),
    map_file: str = Form(None),
    beta_invite: str = Form(""),
):
    ratelimit.check(request, "signup")
    _require_beta_invite(request, beta_invite)
    map_file = map_file or service.default_map()
    if map_file not in service.available_maps():
        raise HTTPException(400, f"Unknown map '{map_file}'.")
    room = _store.create(name, slots, map_file)
    try:
        service.create_game(room)
    except (RuntimeError, FileNotFoundError, map_loader.MapValidationError) as exc:
        raise HTTPException(400 if not isinstance(exc, RuntimeError) else 500, str(exc))
    response = RedirectResponse(url=f"/room/{room.code}", status_code=303)
    _set_auth_cookie(response, _host_cookie_name(room.code), room.host_key)
    return response


@app.post("/join")
def join_room(
    request: Request,
    code: str = Form(...),
    pin: str = Form(...),
    display_name: str = Form(...),
    beta_invite: str = Form(""),
):
    try:
        ratelimit.check(request, "signup")
        _require_beta_invite(request, beta_invite)
    except HTTPException as exc:
        return RedirectResponse(url=f"/?error={exc.detail}", status_code=303)
    try:
        room, player = _store.join(code, pin, display_name)
    except RoomError as exc:
        return RedirectResponse(url=f"/?error={exc}", status_code=303)
    response = RedirectResponse(url=f"/room/{room.code}", status_code=303)
    _set_auth_cookie(response, _player_cookie_name(room.code), player.agent_key)
    return response


@app.get("/room/{code}", response_class=HTMLResponse)
def room_page(request: Request, code: str):
    room = _resolve_room(code)
    player = _player_for(room, request, None)
    is_host = net.secret_eq(
        request.cookies.get(_host_cookie_name(code)), room.host_key
    )
    return templates.TemplateResponse(
        request,
        "room.html",
        _panel_context(request, room, player, is_host),
    )


@app.get("/room/{code}/master", response_class=HTMLResponse)
def master_page(request: Request, code: str):
    """Private host view of the complete game state and turn activity."""
    room = _resolve_room(code)
    _require_master(request, room)
    context = _master_context(
        room,
        phase=request.query_params.get("phase", ""),
        faction=request.query_params.get("faction", ""),
    )
    context["map_svg"] = _map_svg(
        room.map_file, service.map_overlay(room, None, all_visible=True)
    )
    context["map_islands"] = _map_islands(room.map_file)
    context["my_games"] = _my_games(request, room.code)
    return templates.TemplateResponse(request, "master.html", context)


@app.get("/room/{code}/master/panel", response_class=HTMLResponse)
def master_panel(request: Request, code: str):
    room = _resolve_room(code)
    _require_master(request, room)
    return templates.TemplateResponse(
        request,
        "partials/master_panel.html",
        _master_context(
            room,
            phase=request.query_params.get("phase", ""),
            faction=request.query_params.get("faction", ""),
        ),
    )


@app.get("/room/{code}/master/map", response_class=HTMLResponse)
def master_map(request: Request, code: str):
    room = _resolve_room(code)
    _require_master(request, room)
    return HTMLResponse(
        _map_svg(room.map_file, service.map_overlay(room, None, all_visible=True))
    )


@app.get("/room/{code}/master/player/{faction_id}", response_class=HTMLResponse)
def master_player_detail(request: Request, code: str, faction_id: str):
    """HTMX fragment for the host's per-faction state and command inspector."""
    room = _resolve_room(code)
    _require_master(request, room)
    try:
        detail = service.master_player_detail(room, faction_id)
    except KeyError:
        raise HTTPException(404, "No such faction in this game.")
    return templates.TemplateResponse(
        request, "partials/master_player_detail.html", detail
    )


@app.get("/room/{code}/setup", response_class=HTMLResponse)
def setup_page(request: Request, code: str):
    """Host-only: decide who plays each faction seat, configure bot profiles."""
    room = _resolve_room(code)
    _require_master(request, room)
    return templates.TemplateResponse(
        request,
        "setup.html",
        _setup_context(room, request.query_params.get("msg", ""), request),
    )


@app.post("/room/{code}/setup/agents/{faction_id}")
def setup_agent(
    request: Request,
    code: str,
    faction_id: str,
    model: str = Form(""),
    persona: str = Form(""),
    temperature: str = Form("0"),
    enabled: str = Form(""),
    action: str = Form("save"),
):
    room = _resolve_room(code)
    _require_master(request, room)
    player = _faction_by_id(room, faction_id)
    registry = default_registry()
    if action == "clear":
        registry.delete(room.code, faction_id)
        msg = f"Bot profile cleared for {player.faction_name}."
        return RedirectResponse(
            url=f"/room/{room.code}/setup?msg={quote(msg)}", status_code=303
        )
    profile = registry.get(room.code, faction_id) or AgentProfile()
    if model.strip():
        profile.model = model.strip()
    profile.persona = persona.strip()
    try:
        profile.temperature = max(0.0, min(2.0, float(temperature or "0")))
    except ValueError:
        profile.temperature = 0.0
    profile.enabled = enabled == "on"
    claimed = False
    if profile.enabled and player.kind == "empty":
        player.kind = "agent"
        player.display_name = player.display_name or "bot"
        player.agent_key = "soe_" + secrets.token_hex(12)
        default_store().save()
        claimed = True
    registry.set(room.code, faction_id, profile)
    if action == "run":
        try:
            ratelimit.check(request, "bot")
            result = orchestrator.run_bot_turn(room, player)
            msg = (
                f"Bot {player.faction_name} ran: {result['parsed']} order(s) submitted."
            )
        except HTTPException as exc:
            msg = f"Bot {player.faction_name} not run: {exc.detail}"
        except orchestrator.BotError as exc:
            msg = f"Bot {player.faction_name} not run: {exc}"
        except Exception as exc:  # noqa: BLE001 - keep the dashboard usable
            logger.exception(
                "bot_run_failed room=%s faction=%s", room.code, faction_id
            )
            msg = f"Bot {player.faction_name} failed: {type(exc).__name__}."
        return RedirectResponse(
            url=f"/room/{room.code}/setup?msg={quote(msg)}", status_code=303
        )
    msg = f"Bot profile saved for {player.faction_name}."
    if claimed:
        msg += " Empty seat claimed for the bot."
    return RedirectResponse(
        url=f"/room/{room.code}/setup?msg={quote(msg)}", status_code=303
    )


@app.get("/llm-settings", response_class=HTMLResponse)
def llm_settings_page(request: Request):
    """Server-wide LLM settings, reachable from the home page. Readable by
    anyone; writable only by the operator."""
    from webapp import llm_settings

    return templates.TemplateResponse(
        request,
        "llm_settings.html",
        {
            "llm": llm_settings.public_settings(),
            "llm_env": {
                "base_url": bool(os.environ.get("SOE_LLM_BASE", "").strip()),
                "key": bool(os.environ.get("SOE_LLM_KEY", "").strip()),
                "model": os.environ.get("SOE_LLM_MODEL", "").strip(),
            },
            "is_operator": _is_operator(request),
            "operator_key_required": bool(OPERATOR_KEY),
            "allowed_base_hosts": llm_settings.allowed_base_hosts(),
            "notice": request.query_params.get("msg", ""),
            "room": None,
        },
    )


@app.post("/llm-settings")
def llm_settings_save(
    request: Request,
    base_url: str = Form(""),
    key: str = Form(""),
    model: str = Form(""),
    temperature: str = Form(""),
    timeout_seconds: str = Form(""),
    max_retries: str = Form(""),
    max_tokens: str = Form(""),
    clear_key: str = Form(""),
    action: str = Form("save"),
    operator_key: str = Form(""),
):
    _require_operator(request, operator_key)
    msg = _apply_llm_settings(
        base_url, key, model, temperature, timeout_seconds, max_retries,
        max_tokens, clear_key, action,
    )
    response = RedirectResponse(
        url=f"/llm-settings?msg={quote(msg)}", status_code=303
    )
    _remember_operator(response, operator_key)
    return response


def _apply_llm_settings(
    base_url: str,
    key: str,
    model: str,
    temperature: str,
    timeout_seconds: str,
    max_retries: str,
    max_tokens: str,
    clear_key: str,
    action: str,
) -> str:
    """Shared save/clear/probe logic for both the room setup page and the
    standalone /llm-settings page. Returns the notice message.

    Callers must have passed ``_require_operator`` first: this writes the key
    the whole process uses and decides which host receives it.
    """
    from webapp import llm_settings

    patch: dict = {}
    new_base = base_url.strip().rstrip("/")
    if new_base:
        problem = llm_settings.base_url_error(new_base)
        if problem:
            return f"Base URL rejected: {problem}"
        patch["base_url"] = new_base
    if model.strip():
        patch["model"] = model.strip()
    if temperature.strip():
        try:
            patch["temperature"] = max(0.0, min(2.0, float(temperature)))
        except ValueError:
            pass
    if timeout_seconds.strip():
        try:
            patch["timeout_seconds"] = max(1, int(float(timeout_seconds)))
        except ValueError:
            pass
    if max_retries.strip():
        try:
            patch["max_retries"] = max(0, int(max_retries))
        except ValueError:
            pass
    if max_tokens.strip():
        try:
            patch["max_tokens"] = max(16, int(max_tokens))
        except ValueError:
            pass
    if clear_key == "on":
        patch["key"] = ""
    elif key.strip():
        patch["key"] = key.strip()

    if action == "probe":
        saved_base = (
            str(llm_settings.load_settings().get("base_url") or "").strip().rstrip("/")
        )
        if new_base and new_base != saved_base:
            # A probe sends the live key to the base URL. Changing where it
            # goes and sending it are two deliberate acts, not one.
            llm_settings.save_settings(patch)
            return (
                "Base URL changed and saved without probing. Probe again to "
                "send the key to the new endpoint."
            )
        llm_settings.save_settings(patch)
        return _probe_llm()
    if action == "clear":
        llm_settings.clear_key()
        return "LLM settings kept; API key cleared."
    llm_settings.save_settings(patch)
    msg = "LLM settings saved."
    if not llm_settings.load_settings().get("key") and not os.environ.get(
        "SOE_LLM_KEY", ""
    ).strip():
        msg += " No API key set: bots will refuse to run until one is added."
    return msg


@app.post("/room/{code}/setup/llm")
def setup_llm(
    request: Request,
    code: str,
    base_url: str = Form(""),
    key: str = Form(""),
    model: str = Form(""),
    temperature: str = Form(""),
    timeout_seconds: str = Form(""),
    max_retries: str = Form(""),
    max_tokens: str = Form(""),
    clear_key: str = Form(""),
    action: str = Form("save"),
    operator_key: str = Form(""),
):
    """Operator-only: configure the server-wide LLM settings from the room
    setup page. The host session gets you onto this page; changing the
    process-wide key and its destination still needs the operator. Env vars
    keep priority at runtime; the file fills the gaps. The key is stored for
    the server, never echoed back (only a masked tail is shown).
    """
    room = _resolve_room(code)
    _require_master(request, room)
    _require_operator(request, operator_key)
    msg = _apply_llm_settings(
        base_url, key, model, temperature, timeout_seconds, max_retries,
        max_tokens, clear_key, action,
    )
    response = RedirectResponse(
        url=f"/room/{room.code}/setup?msg={quote(msg)}", status_code=303
    )
    _remember_operator(response, operator_key)
    return response


def _probe_llm() -> str:
    """One tiny model call to verify the configured brain (dashboard probe)."""
    from scripts.probe_model import PROBE_TASK

    from webapp.ai.orchestrator import extract_orders

    model = brain.model_name("")
    try:
        result = brain.chat_result(
            model=model,
            messages=[
                {"role": "system", "content": "You are a strategic game AI."},
                {"role": "user", "content": PROBE_TASK},
            ],
            temperature=0.0,
        )
    except brain.LLMError as exc:
        return f"Probe failed ({model}): {str(exc)[:200]}"
    orders = extract_orders(result.text)
    usage = result.usage
    cost = usage.get("cost") if isinstance(usage, dict) else None
    cost_s = f" cost=${cost:.4f}" if isinstance(cost, (int, float)) else ""
    return (
        f"Probe OK ({model}): orders={'yes' if orders.strip() else 'NO'} "
        f"latency={result.latency_ms:.0f}ms attempts={result.attempts} "
        f"tokens={usage.get('total_tokens', '?')}{cost_s}"
    )


@app.post("/room/{code}/master/resolve", response_class=HTMLResponse)
def master_resolve_now(request: Request, code: str):
    ratelimit.check(request, "resolve")
    room = _resolve_room(code)
    _require_master(request, room)
    try:
        result = service.resolve_turn(room, force=False)
        notice = f"Turn {result['turn']} resolved (seed {result['seed']})."
    except service.NotReadyError as exc:
        notice = f"Not resolved: {exc}"
    except service.BackupUnavailableError:
        notice = "Not resolved: the pre-turn backup failed. Contact the operator."
    except Exception:  # noqa: BLE001 - keep browser errors generic
        notice = "Resolution failed. Contact the operator with the request ID."
    return templates.TemplateResponse(
        request,
        "partials/master_panel.html",
        _master_context(room, notice),
    )


@app.post("/room/{code}/master/autoplay", response_class=HTMLResponse)
def master_autoplay(
    request: Request,
    code: str,
    action: str = Form("start"),
    turns: int = Form(10),
    delay: float = Form(5.0),
    force: str = Form(""),
    wait_humans: str = Form(""),
):
    """Host-only: start or stop the background auto-play loop."""
    room = _resolve_room(code)
    _require_master(request, room)
    controller = autoplay.default_controller()
    if action == "stop":
        controller.stop(room.code)
        notice = "Auto-play stop requested."
    else:
        try:
            controller.start(
                room.code,
                turns=turns,
                delay=delay,
                force=force == "on",
                wait_humans=wait_humans == "on",
            )
            notice = "Auto-play started."
        except autoplay.AutoplayError as exc:
            notice = f"Auto-play not started: {exc}"
    return templates.TemplateResponse(
        request,
        "partials/master_panel.html",
        _master_context(room, notice),
    )


@app.get("/room/{code}/panel", response_class=HTMLResponse)
def room_panel(request: Request, code: str):
    """HTMX fragment: live room status, order form, latest report."""
    room = _resolve_room(code)
    player = _player_for(room, request, None)
    is_host = net.secret_eq(
        request.cookies.get(_host_cookie_name(code)), room.host_key
    )
    return templates.TemplateResponse(
        request,
        "partials/panel.html",
        _panel_context(request, room, player, is_host),
    )


@app.post("/room/{code}/orders", response_class=HTMLResponse)
def submit_orders(request: Request, code: str, orders: str = Form(...)):
    ratelimit.check(request, "orders")
    room = _resolve_room(code)
    player = _player_for(room, request, None)
    is_host = net.secret_eq(
        request.cookies.get(_host_cookie_name(code)), room.host_key
    )
    if not player:
        return templates.TemplateResponse(
            request,
            "partials/panel.html",
            _panel_context(request, room, None, is_host, "Join the game first."),
        )
    try:
        text = _check_order_text(orders)
        feedback = service.submit_orders(room, player, text)
    except HTTPException as exc:
        return templates.TemplateResponse(
            request,
            "partials/panel.html",
            _panel_context(request, room, player, is_host, exc.detail),
        )
    notice = f"Stored {feedback['parsed']} order(s) for turn {feedback['turn']}."
    if not feedback["parsed"]:
        notice = "No orders recognised."
    if feedback["warnings"]:
        notice += " Warnings: " + "; ".join(feedback["warnings"])
    return templates.TemplateResponse(
        request,
        "partials/panel.html",
        _panel_context(request, room, player, is_host, notice),
    )


@app.post("/room/{code}/resolve", response_class=HTMLResponse)
def resolve_now(request: Request, code: str):
    ratelimit.check(request, "resolve")
    room = _resolve_room(code)
    is_host = net.secret_eq(
        request.cookies.get(_host_cookie_name(code)), room.host_key
    )
    player = _player_for(room, request, None)
    if not is_host:
        return templates.TemplateResponse(
            request,
            "partials/panel.html",
            _panel_context(request, room, player, False, "Only the host can resolve."),
        )
    try:
        result = service.resolve_turn(room, force=False)
        notice = f"Turn {result['turn']} resolved (seed {result['seed']})."
    except service.NotReadyError as exc:
        notice = f"Not resolved: {exc}"
    except service.BackupUnavailableError:
        notice = "Not resolved: the pre-turn backup failed. Contact the operator."
    except Exception:  # noqa: BLE001 - keep browser errors generic
        notice = "Resolution failed. Contact the operator with the request ID."
    return templates.TemplateResponse(
        request,
        "partials/panel.html",
        _panel_context(request, room, player, True, notice),
    )


# ============================================================================
# agent API
# ============================================================================


def _key(request: Request, key: Optional[str] = Query(None)) -> str:
    token = request.headers.get("X-Agent-Key") or _accept_query_credential(
        request, key, "The agent key"
    )
    if not token:
        raise HTTPException(401, "Missing agent key (X-Agent-Key header or ?key=).")
    return token


#: Ceiling on one order submission. The parser reads prose; a real turn of
#: orders is a few kilobytes, so this bounds disk and registry growth without
#: ever being felt by a legitimate seat. Bots cannot approach it: their text
#: is capped by the model's max_tokens.
MAX_ORDER_CHARS = 100_000


def _check_order_text(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(400, "No orders given.")
    if len(text) > MAX_ORDER_CHARS:
        raise HTTPException(
            400,
            f"Orders are limited to {MAX_ORDER_CHARS} characters.",
        )
    return text


def _require_host_key(request: Request, room: Room, key: Optional[str]) -> None:
    token = _key(request, key)
    if not net.secret_eq(token, room.host_key):
        raise HTTPException(403, "Host key required.")


def _faction_by_id(room: Room, faction_id: str):
    for player in room.players:
        if player.faction_id == faction_id:
            return player
    raise HTTPException(404, "No such faction in this game.")


def _profile_payload(faction_id: str, profile: AgentProfile) -> dict:
    return {
        "faction_id": faction_id,
        "model": profile.model,
        "persona": profile.persona,
        "temperature": profile.temperature,
        "enabled": profile.enabled,
        "state": profile.state,
        "last_error": profile.last_error,
        "last_run_at": profile.last_run_at,
        # The enrolled blueprint, by reference. The strategy text is not
        # copied here: the seat reads it back from the store by hash.
        "blueprint": (
            {
                "blueprint_id": profile.blueprint_id,
                "version": profile.blueprint_version,
                "content_hash": profile.blueprint_hash,
            }
            if profile.blueprint_id
            else None
        ),
    }


# ============================================================================
# coach pages — the Phase 2 loop a new user can finish without curl
# ============================================================================


def _coach_gate(request: Request, error: str = ""):
    return templates.TemplateResponse(
        request,
        "coach_gate.html",
        {
            "error": error or request.query_params.get("error", ""),
            "beta_invite_required": bool(BETA_ACCESS_CODE),
            "alpha_invite_required": alpha.default_store().is_open(),
        },
    )


def _coach_desk(
    request: Request,
    coach: Coach,
    *,
    revealed_key: str = "",
    error: str = "",
    notice: str = "",
):
    store = training.default_store()
    visible = blueprints.default_store().visible_to(coach)
    league = competition.default_store()
    seasons = [
        item
        for item in league.seasons()
        if item.status
        in (
            competition.STATUS_FROZEN,
            competition.STATUS_SEALED,
            competition.STATUS_COMPLETE,
            competition.STATUS_SUSPENDED,
        )
    ]
    return templates.TemplateResponse(
        request,
        "coach_desk.html",
        {
            "coach": coach,
            "revealed_key": revealed_key,
            "error": error or request.query_params.get("error", ""),
            "notice": notice or request.query_params.get("notice", ""),
            "quota": store.quota_state(coach),
            "blueprints": visible,
            "runs": store.for_coach(coach),
            "seasons": seasons,
            "season_entries": {
                item.id: league.entry_for_coach(item.id, coach) for item in seasons
            },
        },
    )


def _blueprint_page(
    request: Request,
    coach: Coach,
    blueprint,
    *,
    version: int | None = None,
    error: str = "",
    notice: str = "",
):
    current = (
        blueprint.version(version) if version is not None else blueprint.latest()
    )
    return templates.TemplateResponse(
        request,
        "coach_blueprint.html",
        {
            "coach": coach,
            "blueprint": blueprint,
            "current": current,
            "mine": blueprint.writable_by(coach),
            "doctrine_sections": blueprints.DOCTRINE_SECTIONS,
            "frozen_versions": [v for v in blueprint.versions if v.frozen],
            "scenarios": list(training.scenarios().values()),
            "error": error or request.query_params.get("error", ""),
            "notice": notice or request.query_params.get("notice", ""),
        },
    )


def _load_blueprint(coach: Coach, blueprint_id: str):
    try:
        return blueprints.default_store().get(coach, blueprint_id)
    except BlueprintError as exc:
        raise _blueprint_http(exc)


def _run_page_context(request: Request, coach: Coach, run: training.TrainingRun) -> dict:
    view = None
    if run.status == training.STATUS_COMPLETE:
        try:
            view = debrief.build(run)
        except debrief.DebriefError as exc:
            return {
                "coach": coach,
                "run": run,
                "view": None,
                "blueprint_name": _blueprint_name(coach, run.blueprint_id),
                "error": str(exc),
            }
    name = _blueprint_name(coach, run.blueprint_id)
    ctx: dict = {
        "coach": coach,
        "run": run,
        "view": view,
        "blueprint_name": name,
        "error": request.query_params.get("error", ""),
    }
    if view is not None:
        ctx.update(
            {
                "outcome": {
                    "kind": coach_ui.outcome_kind(view.headline),
                    "line": coach_ui.outcome_line(view.headline),
                },
                "main_error": coach_ui.main_error(view.errors),
                "cost": {"line": coach_ui.cost_line(view.cost)},
                "other_runs": [
                    item
                    for item in training.default_store().for_coach(coach)
                    if item.id != run.id and item.status == training.STATUS_COMPLETE
                ],
                "alpha_member": bool(alpha.default_store().claimed_by(coach.id)),
                "alpha_intent": alpha.default_store().intent_for(coach),
                "alpha_share": alpha.default_store().share_for(coach, run.id),
            }
        )
    return ctx


def _blueprint_name(coach: Coach, blueprint_id: str) -> str:
    try:
        return blueprints.default_store().get(coach, blueprint_id).name
    except BlueprintError:
        return blueprint_id


def _set_coach_cookie(response, key: str) -> None:
    _set_auth_cookie(response, COACH_COOKIE, key)


def _html_training_error(path: str, exc: Exception) -> RedirectResponse:
    return RedirectResponse(
        url=f"{path}?error={quote(str(exc))}", status_code=303
    )


@app.get("/coach", response_class=HTMLResponse)
def coach_desk(request: Request):
    """The coach's front door: register, or the desk if the browser is signed in."""
    coach = _optional_coach(request)
    if coach is None:
        return _coach_gate(request)
    flash = request.cookies.get(COACH_FLASH_COOKIE, "")
    response = _coach_desk(request, coach, revealed_key=flash)
    if flash:
        response.delete_cookie(
            COACH_FLASH_COOKIE, samesite="lax", secure=COOKIE_SECURE
        )
    return response


@app.post("/coach/register")
def coach_register(
    request: Request,
    name: str = Form(""),
    invite: str = Form(""),
):
    try:
        ratelimit.check(request, "signup")
        _require_beta_invite(request, invite)
        roster = alpha.default_store()
        if roster.is_open():
            roster.peek(invite)
        _coach, key = coaches.default_store().create(name)
        if roster.is_open():
            roster.claim(invite, _coach)
    except HTTPException as exc:
        return _coach_gate(request, error=str(exc.detail))
    except (CoachError, alpha.AlphaError) as exc:
        return _coach_gate(request, error=str(exc))
    response = RedirectResponse(url="/coach", status_code=303)
    _set_coach_cookie(response, key)
    _set_auth_cookie(response, COACH_FLASH_COOKIE, key)
    return response


@app.post("/coach/signin")
def coach_signin(request: Request, coach_key: str = Form("")):
    try:
        coaches.default_store().require(coach_key.strip())
    except CoachAuthError as exc:
        return _coach_gate(request, error=str(exc))
    response = RedirectResponse(url="/coach", status_code=303)
    _set_coach_cookie(response, coach_key.strip())
    return response


@app.post("/coach/leave")
def coach_leave():
    response = RedirectResponse(url="/coach", status_code=303)
    response.delete_cookie(COACH_COOKIE, samesite="lax", secure=COOKIE_SECURE)
    return response


@app.post("/coach/blueprints")
def coach_create_blueprint(
    request: Request,
    name: str = Form(""),
    persona: str = Form(""),
    notes: str = Form(""),
    objective: str = Form(""),
    economy: str = Form(""),
    risk: str = Form(""),
    diplomacy: str = Form(""),
    model: str = Form(""),
    temperature: str = Form(""),
):
    coach = _optional_coach(request)
    if coach is None:
        return RedirectResponse(url="/coach", status_code=303)
    try:
        blueprint = blueprints.default_store().create(
            coach,
            name,
            persona=persona,
            doctrine=coach_ui.doctrine_from_mapping(
                {
                    "objective": objective,
                    "economy": economy,
                    "risk": risk,
                    "diplomacy": diplomacy,
                }
            ),
            runtime=coach_ui.runtime_from_mapping(
                {"model": model, "temperature": temperature}
            ),
            notes=notes,
        )
    except BlueprintError as exc:
        return _coach_desk(request, coach, error=str(exc))
    return RedirectResponse(url=f"/coach/blueprints/{blueprint.id}", status_code=303)


@app.get("/coach/blueprints/{blueprint_id}", response_class=HTMLResponse)
def coach_blueprint_page(
    blueprint_id: str, request: Request, v: Optional[int] = Query(None)
):
    coach = _optional_coach(request)
    if coach is None:
        return RedirectResponse(url="/coach", status_code=303)
    blueprint = _load_blueprint(coach, blueprint_id)
    try:
        return _blueprint_page(request, coach, blueprint, version=v)
    except BlueprintError as exc:
        raise _blueprint_http(exc)


@app.post("/coach/blueprints/{blueprint_id}")
def coach_edit_blueprint(
    blueprint_id: str,
    request: Request,
    version: int = Form(...),
    name: str = Form(""),
    persona: str = Form(""),
    notes: str = Form(""),
    objective: str = Form(""),
    economy: str = Form(""),
    risk: str = Form(""),
    diplomacy: str = Form(""),
    model: str = Form(""),
    temperature: str = Form(""),
):
    coach = _optional_coach(request)
    if coach is None:
        return RedirectResponse(url="/coach", status_code=303)
    try:
        blueprints.default_store().edit(
            coach,
            blueprint_id,
            version,
            persona=persona,
            doctrine=coach_ui.doctrine_from_mapping(
                {
                    "objective": objective,
                    "economy": economy,
                    "risk": risk,
                    "diplomacy": diplomacy,
                }
            ),
            runtime=coach_ui.runtime_from_mapping(
                {"model": model, "temperature": temperature}
            ),
            notes=notes,
            name=name,
        )
        blueprint = blueprints.default_store().get(coach, blueprint_id)
    except BlueprintError as exc:
        return _html_training_error(
            f"/coach/blueprints/{blueprint_id}?v={version}", exc
        )
    return RedirectResponse(
        url=f"/coach/blueprints/{blueprint.id}?v={version}", status_code=303
    )


@app.post("/coach/blueprints/{blueprint_id}/versions")
def coach_new_blueprint_version(
    blueprint_id: str,
    request: Request,
    from_version: Optional[int] = Form(None),
):
    coach = _optional_coach(request)
    if coach is None:
        return RedirectResponse(url="/coach", status_code=303)
    store = blueprints.default_store()
    try:
        store.new_version(coach, blueprint_id, from_version=from_version)
        blueprint = store.get(coach, blueprint_id)
    except BlueprintError as exc:
        return _html_training_error(f"/coach/blueprints/{blueprint_id}", exc)
    return RedirectResponse(
        url=f"/coach/blueprints/{blueprint.id}?v={blueprint.latest().version}",
        status_code=303,
    )


@app.post("/coach/blueprints/{blueprint_id}/versions/{version}/freeze")
def coach_freeze_blueprint(
    blueprint_id: str, version: int, request: Request
):
    coach = _optional_coach(request)
    if coach is None:
        return RedirectResponse(url="/coach", status_code=303)
    try:
        blueprints.default_store().freeze(coach, blueprint_id, version)
    except BlueprintError as exc:
        return _html_training_error(
            f"/coach/blueprints/{blueprint_id}?v={version}", exc
        )
    return RedirectResponse(
        url=f"/coach/blueprints/{blueprint_id}?v={version}", status_code=303
    )


@app.post("/coach/training")
def coach_start_training(
    request: Request,
    background: BackgroundTasks,
    blueprint_id: str = Form(""),
    scenario_id: str = Form(""),
    version: Optional[int] = Form(None),
):
    coach = _optional_coach(request)
    if coach is None:
        return RedirectResponse(url="/coach", status_code=303)
    store = training.default_store()
    try:
        run = store.start(coach, blueprint_id, scenario_id, version=version)
    except (training.TrainingError, BlueprintError) as exc:
        target = f"/coach/blueprints/{blueprint_id}" if blueprint_id else "/coach"
        return _html_training_error(target, exc)
    background.add_task(training.execute, run, store)
    return RedirectResponse(url=f"/coach/training/{run.id}", status_code=303)


@app.get("/coach/training/{run_id}", response_class=HTMLResponse)
def coach_training_page(run_id: str, request: Request):
    coach = _optional_coach(request)
    if coach is None:
        return RedirectResponse(url="/coach", status_code=303)
    try:
        run = training.default_store().get(coach, run_id)
    except training.TrainingError as exc:
        raise HTTPException(404, str(exc))
    return templates.TemplateResponse(
        request, "coach_run.html", _run_page_context(request, coach, run)
    )


@app.get("/coach/training/{run_id}/panel", response_class=HTMLResponse)
def coach_training_panel(run_id: str, request: Request):
    """HTMX fragment: status while the match is running, debrief when it is not."""
    coach = _optional_coach(request)
    if coach is None:
        raise HTTPException(401, "Sign in at /coach first.")
    try:
        run = training.default_store().get(coach, run_id)
    except training.TrainingError as exc:
        raise HTTPException(404, str(exc))
    return templates.TemplateResponse(
        request, "partials/coach_status.html", _run_page_context(request, coach, run)
    )


@app.post("/coach/training/{run_id}/iterate")
def coach_iterate(
    run_id: str,
    request: Request,
    as_clone: str = Form(""),
    name: str = Form(""),
):
    coach = _optional_coach(request)
    if coach is None:
        return RedirectResponse(url="/coach", status_code=303)
    try:
        run = training.default_store().get(coach, run_id)
    except training.TrainingError as exc:
        raise HTTPException(404, str(exc))
    store = blueprints.default_store()
    try:
        if as_clone:
            blueprint = store.clone(
                coach,
                run.blueprint_id,
                from_version=run.blueprint_version,
                name=name,
            )
        else:
            store.new_version(
                coach, run.blueprint_id, from_version=run.blueprint_version
            )
            blueprint = store.get(coach, run.blueprint_id)
    except BlueprintError as exc:
        return _html_training_error(f"/coach/training/{run_id}", exc)
    return RedirectResponse(
        url=f"/coach/blueprints/{blueprint.id}?v={blueprint.latest().version}",
        status_code=303,
    )


@app.get("/coach/compare", response_class=HTMLResponse)
def coach_compare(
    request: Request,
    left: str = Query(""),
    right: str = Query(""),
):
    coach = _optional_coach(request)
    if coach is None:
        return RedirectResponse(url="/coach", status_code=303)
    comparison = debrief.compare(
        _debrief_or_404(coach, left), _debrief_or_404(coach, right)
    )
    return templates.TemplateResponse(
        request,
        "coach_compare.html",
        {
            "coach": coach,
            "comparison": comparison,
            "left_id": left,
            "right_id": right,
        },
    )


# ======================================================================
# Coach League — operator panel and coach entry (Phase 3)
# ======================================================================


def _html_league_error(path: str, exc: Exception) -> RedirectResponse:
    return RedirectResponse(url=f"{path}?error={quote(str(exc))}", status_code=303)


def _catalogue_rows() -> list[dict]:
    rows = []
    for item in competition.catalogues().values():
        rows.append(
            {
                "id": item.get("id"),
                "name": item.get("name") or item.get("id"),
            }
        )
    return rows


def _eligible_blueprints(coach: Coach, rules: competition.Regulation):
    eligible = []
    for item in blueprints.default_store().owned_by(coach):
        frozen = item.latest_frozen()
        if frozen is None:
            continue
        model = str((frozen.runtime or {}).get("model") or "").strip()
        if model and model != rules.model:
            continue
        eligible.append(item)
    return eligible


def _ops_league_page(request: Request, *, error: str = "", notice: str = ""):
    _require_operator(request)
    return templates.TemplateResponse(
        request,
        "ops_league.html",
        {
            "seasons": competition.default_store().seasons(),
            "catalogues": _catalogue_rows(),
            "error": error or request.query_params.get("error", ""),
            "notice": notice or request.query_params.get("notice", ""),
        },
    )


def _ops_season_page(request: Request, season_id: str, *, error: str = "", notice: str = ""):
    _require_operator(request)
    store = competition.default_store()
    try:
        season = store.season(season_id)
    except competition.CompetitionError as exc:
        raise HTTPException(404, str(exc))
    return templates.TemplateResponse(
        request,
        "ops_season.html",
        {
            "season": season,
            "rules": season.rules(),
            "entries": store.entries(season.id, include_withdrawn=True),
            "jobs": store.jobs(season.id),
            "queued": [
                item
                for item in store.jobs(season.id)
                if item.status == competition.JOB_QUEUED
            ],
            "finished": sum(
                1
                for item in store.jobs(season.id)
                if item.status == competition.JOB_COMPLETE
            ),
            "table": competition.standings(store, season.id),
            "audit": store.audit(season.id),
            "error": error or request.query_params.get("error", ""),
            "notice": notice or request.query_params.get("notice", ""),
        },
    )


def _coach_season_page(
    request: Request, coach: Coach, season_id: str, *, error: str = "", notice: str = ""
):
    store = competition.default_store()
    try:
        season = store.season(season_id)
    except competition.CompetitionError as exc:
        raise HTTPException(404, str(exc))
    return templates.TemplateResponse(
        request,
        "coach_season.html",
        {
            "coach": coach,
            "season": season,
            "rules": season.rules(),
            "mine": store.entry_for_coach(season.id, coach),
            "eligible": _eligible_blueprints(coach, season.rules()),
            "table": competition.standings(store, season.id),
            "error": error or request.query_params.get("error", ""),
            "notice": notice or request.query_params.get("notice", ""),
        },
    )


def _apply_regulation_overrides(season: competition.Season, data: dict) -> None:
    current = season.rules()
    payload = competition.regulation_payload(current)
    if data.get("map"):
        payload["map"] = str(data["map"]).strip()
    if data.get("turns"):
        payload["turns"] = int(data["turns"])
    if data.get("model"):
        payload["model"] = str(data["model"]).strip()
    if data.get("seed_pairs"):
        payload["seed_pairs"] = int(data["seed_pairs"])
    if payload != competition.regulation_payload(current):
        competition.default_store().set_regulation(
            season.id, competition.regulation_from_mapping(payload)
        )


@app.get("/ops/league", response_class=HTMLResponse)
def ops_league(request: Request):
    return _ops_league_page(request)


@app.post("/ops/league/seasons")
def ops_create_season(
    request: Request,
    name: str = Form(""),
    catalogue_id: str = Form("coach_league"),
    map: str = Form(""),
    turns: str = Form(""),
    model: str = Form(""),
    seed_pairs: str = Form(""),
):
    _require_operator(request)
    store = competition.default_store()
    try:
        season = store.create_season(name, catalogue_id=catalogue_id or "coach_league")
        _apply_regulation_overrides(
            season,
            {"map": map, "turns": turns, "model": model, "seed_pairs": seed_pairs},
        )
    except (competition.CompetitionError, ValueError) as exc:
        return _ops_league_page(request, error=str(exc))
    return RedirectResponse(url=f"/ops/league/seasons/{season.id}", status_code=303)


@app.get("/ops/league/seasons/{season_id}", response_class=HTMLResponse)
def ops_season(season_id: str, request: Request):
    return _ops_season_page(request, season_id)


@app.post("/ops/league/seasons/{season_id}/freeze")
def ops_freeze_season(season_id: str, request: Request):
    _require_operator(request)
    try:
        competition.default_store().freeze(season_id)
    except competition.CompetitionError as exc:
        return _html_league_error(f"/ops/league/seasons/{season_id}", exc)
    return RedirectResponse(url=f"/ops/league/seasons/{season_id}", status_code=303)


@app.post("/ops/league/seasons/{season_id}/pair")
def ops_pair_season(season_id: str, request: Request):
    _require_operator(request)
    try:
        competition.default_store().pair(season_id)
    except competition.CompetitionError as exc:
        return _html_league_error(f"/ops/league/seasons/{season_id}", exc)
    return RedirectResponse(url=f"/ops/league/seasons/{season_id}", status_code=303)


@app.post("/ops/league/seasons/{season_id}/run")
def ops_run_season(
    season_id: str, request: Request, background: BackgroundTasks
):
    """Play every queued match. The operator starts it; they do not edit the ledger."""
    _require_operator(request)
    store = competition.default_store()
    try:
        job = store.next_job(season_id)
    except competition.CompetitionError as exc:
        return _html_league_error(f"/ops/league/seasons/{season_id}", exc)
    if job is None:
        return _html_league_error(
            f"/ops/league/seasons/{season_id}",
            competition.CompetitionError("Nothing is queued."),
        )
    background.add_task(competition.run_until_idle, store, season_id)
    return RedirectResponse(url=f"/ops/league/seasons/{season_id}", status_code=303)


@app.post("/ops/league/seasons/{season_id}/dispatch")
def ops_dispatch_season(
    season_id: str, request: Request, background: BackgroundTasks
):
    _require_operator(request)
    store = competition.default_store()
    try:
        job = store.next_job(season_id)
    except competition.CompetitionError as exc:
        return _html_league_error(f"/ops/league/seasons/{season_id}", exc)
    if job is None:
        return _html_league_error(
            f"/ops/league/seasons/{season_id}",
            competition.CompetitionError("Nothing is queued."),
        )
    background.add_task(competition.execute, job, store)
    return RedirectResponse(url=f"/ops/league/seasons/{season_id}", status_code=303)


@app.post("/ops/league/seasons/{season_id}/recover")
def ops_recover_season(
    season_id: str, request: Request, background: BackgroundTasks
):
    _require_operator(request)
    store = competition.default_store()
    try:
        store.season(season_id)
    except competition.CompetitionError as exc:
        return _html_league_error("/ops/league", exc)
    store.requeue_orphans()
    job = store.next_job(season_id)
    if job is not None:
        background.add_task(competition.execute, job, store)
    return RedirectResponse(url=f"/ops/league/seasons/{season_id}", status_code=303)


@app.post("/ops/league/seasons/{season_id}/final")
def ops_stage_final(season_id: str, request: Request):
    _require_operator(request)
    try:
        competition.default_store().stage_final(season_id)
    except competition.CompetitionError as exc:
        return _html_league_error(f"/ops/league/seasons/{season_id}", exc)
    return RedirectResponse(url=f"/ops/league/seasons/{season_id}", status_code=303)


@app.post("/ops/league/seasons/{season_id}/suspend")
def ops_suspend_season(season_id: str, request: Request, reason: str = Form("")):
    _require_operator(request)
    try:
        competition.default_store().suspend(season_id, reason)
    except competition.CompetitionError as exc:
        return _html_league_error(f"/ops/league/seasons/{season_id}", exc)
    return RedirectResponse(url=f"/ops/league/seasons/{season_id}", status_code=303)


@app.post("/ops/league/jobs/{job_id}/retry")
def ops_retry_job(job_id: str, request: Request):
    _require_operator(request)
    try:
        job = competition.default_store().retry(job_id)
    except competition.CompetitionError as exc:
        return _html_league_error("/ops/league", exc)
    return RedirectResponse(url=f"/ops/league/seasons/{job.season_id}", status_code=303)


@app.post("/ops/league/jobs/{job_id}/suspend")
def ops_suspend_job(job_id: str, request: Request):
    _require_operator(request)
    try:
        job = competition.default_store().suspend_job(job_id)
    except competition.CompetitionError as exc:
        return _html_league_error("/ops/league", exc)
    return RedirectResponse(url=f"/ops/league/seasons/{job.season_id}", status_code=303)


@app.get("/coach/seasons/{season_id}", response_class=HTMLResponse)
def coach_season_page(season_id: str, request: Request):
    coach = _optional_coach(request)
    if coach is None:
        return RedirectResponse(url="/coach", status_code=303)
    return _coach_season_page(request, coach, season_id)


@app.post("/coach/seasons/{season_id}/enter")
def coach_enter_season(
    season_id: str,
    request: Request,
    blueprint_id: str = Form(""),
    version: str = Form(""),
):
    coach = _optional_coach(request)
    if coach is None:
        return RedirectResponse(url="/coach", status_code=303)
    chosen = int(version) if str(version).strip() else None
    try:
        competition.default_store().enter(
            coach, season_id, blueprint_id, chosen
        )
    except (competition.CompetitionError, BlueprintError, ValueError) as exc:
        return _html_league_error(f"/coach/seasons/{season_id}", exc)
    return RedirectResponse(url=f"/coach/seasons/{season_id}", status_code=303)


@app.post("/coach/seasons/{season_id}/withdraw")
def coach_withdraw_season(season_id: str, request: Request):
    coach = _optional_coach(request)
    if coach is None:
        return RedirectResponse(url="/coach", status_code=303)
    try:
        competition.default_store().withdraw(coach, season_id)
    except competition.CompetitionError as exc:
        return _html_league_error(f"/coach/seasons/{season_id}", exc)
    return RedirectResponse(url=f"/coach/seasons/{season_id}", status_code=303)


@app.get("/ops/alpha", response_class=HTMLResponse)
def ops_alpha(request: Request):
    _require_operator(request)
    roster = alpha.default_store()
    return templates.TemplateResponse(
        request,
        "ops_alpha.html",
        {
            "roster": roster,
            "fmt": roster.format,
            "funnel": alpha.funnel(
                roster,
                coaches=coaches.default_store(),
                blueprints=blueprints.default_store(),
                training=training.default_store(),
                competition=competition.default_store(),
            ),
            "revealed": request.query_params.get("invite", ""),
            "error": request.query_params.get("error", ""),
            "notice": request.query_params.get("notice", ""),
        },
    )


@app.post("/ops/alpha/open")
def ops_alpha_open(request: Request):
    _require_operator(request)
    alpha.default_store().open()
    return RedirectResponse(url="/ops/alpha", status_code=303)


@app.post("/ops/alpha/close")
def ops_alpha_close(request: Request):
    _require_operator(request)
    alpha.default_store().close()
    return RedirectResponse(url="/ops/alpha", status_code=303)


@app.post("/ops/alpha/invites")
def ops_alpha_invite(request: Request, name: str = Form("")):
    _require_operator(request)
    try:
        _invite, code = alpha.default_store().issue(name)
    except alpha.AlphaError as exc:
        return RedirectResponse(
            url=f"/ops/alpha?error={quote(str(exc))}", status_code=303
        )
    return RedirectResponse(url=f"/ops/alpha?invite={quote(code)}", status_code=303)


@app.post("/coach/training/{run_id}/share")
def coach_share_run(run_id: str, request: Request):
    coach = _optional_coach(request)
    if coach is None:
        return RedirectResponse(url="/coach", status_code=303)
    try:
        run = training.default_store().get(coach, run_id)
    except training.TrainingError as exc:
        return _html_training_error(f"/coach/training/{run_id}", exc)
    if run.status != training.STATUS_COMPLETE:
        return _html_training_error(
            f"/coach/training/{run_id}",
            training.TrainingError("Share a finished run."),
        )
    item = alpha.default_store().share(coach, run.id)
    return RedirectResponse(url=f"/alpha/s/{item.token}", status_code=303)


@app.post("/coach/alpha/intent")
def coach_alpha_intent(
    request: Request,
    kind: str = Form(""),
    source: str = Form(""),
):
    coach = _optional_coach(request)
    if coach is None:
        return RedirectResponse(url="/coach", status_code=303)
    try:
        alpha.default_store().record_intent(coach, kind, source=source)
    except alpha.AlphaError as exc:
        target = f"/coach/training/{source}" if source else "/coach"
        return _html_training_error(target, exc)
    target = f"/coach/training/{source}" if source else "/coach"
    return RedirectResponse(url=target, status_code=303)


@app.get("/alpha/s/{token}", response_class=HTMLResponse)
def alpha_share_page(token: str, request: Request):
    roster = alpha.default_store()
    try:
        item = roster.share_by_token(token)
    except alpha.AlphaError as exc:
        raise HTTPException(404, str(exc))
    try:
        run = training.default_store().get_shared(item.run_id)
    except training.TrainingError:
        raise HTTPException(404, "That shared result is gone.")
    try:
        view = debrief.build(run)
    except debrief.DebriefError as exc:
        raise HTTPException(409, str(exc))
    coach = coaches.default_store().get(item.coach_id)
    name = run.blueprint_id
    if coach is not None:
        try:
            name = blueprints.default_store().get(coach, run.blueprint_id).name
        except BlueprintError:
            name = run.blueprint_id
    return templates.TemplateResponse(
        request,
        "alpha_share.html",
        {"card": alpha.public_card(run, view, blueprint_name=name), "token": token},
    )


@app.get("/alpha/final/{season_id}", response_class=HTMLResponse)
def alpha_final_page(season_id: str, request: Request):
    store = competition.default_store()
    try:
        season = store.season(season_id)
        if not season.final_match_id:
            raise competition.CompetitionError("No final has been staged.")
        match = store.match(season.final_match_id)
    except competition.CompetitionError as exc:
        raise HTTPException(404, str(exc))
    left = store.entry(match.left_entry_id)
    right = store.entry(match.right_entry_id)
    return templates.TemplateResponse(
        request,
        "alpha_final.html",
        {
            "season": season,
            "match": match,
            "left": left,
            "right": right,
        },
    )


@app.post("/api/rooms")
def api_create_room(request: Request, payload: dict):
    ratelimit.check(request, "signup")
    _require_beta_invite(request, payload.get("invite", ""))
    name = payload.get("name", "")
    try:
        slots = int(payload.get("slots", 2))
    except (TypeError, ValueError):
        raise HTTPException(400, "slots must be a whole number.")
    map_file = payload.get("map") or service.default_map()
    if map_file not in service.available_maps():
        raise HTTPException(400, f"Unknown map '{map_file}'.")
    room = _store.create(name, slots, map_file)
    try:
        service.create_game(room)
    except (RuntimeError, FileNotFoundError, map_loader.MapValidationError) as exc:
        raise HTTPException(400 if not isinstance(exc, RuntimeError) else 500, str(exc))
    return {
        "code": room.code,
        "pin": room.pin,
        "host_key": room.host_key,
        "slots": room.slots,
        "map_file": room.map_file,
        "players": [
            {"faction_id": p.faction_id, "faction_name": p.faction_name}
            for p in room.players
        ],
    }


@app.post("/api/join")
def api_join(request: Request, payload: dict):
    ratelimit.check(request, "signup")
    _require_beta_invite(request, payload.get("invite", ""))
    missing = [
        field
        for field in ("code", "pin", "name")
        if not isinstance(payload.get(field), str) or not payload[field].strip()
    ]
    if missing:
        raise HTTPException(400, f"Missing field(s): {', '.join(missing)}.")
    try:
        room, player = _store.join(
            payload["code"], payload["pin"], payload["name"]
        )
    except RoomError as exc:
        raise HTTPException(400, str(exc))
    return {
        "code": room.code,
        "faction_id": player.faction_id,
        "faction_name": player.faction_name,
        "agent_key": player.agent_key,
        "turn": room.last_resolved_turn,
    }


@app.get("/api/rooms/{code}/status")
def api_status(code: str, request: Request, key: Optional[str] = Query(None)):
    room = _resolve_room(code)
    token = _key(request, key)
    if not room.player_by_key(token) and not net.secret_eq(token, room.host_key):
        raise HTTPException(403, "This key does not belong to the game.")
    return service.room_status(room)


@app.post("/api/rooms/{code}/orders")
def api_orders(
    code: str, request: Request, payload: dict, key: Optional[str] = Query(None)
):
    room = _resolve_room(code)
    ratelimit.check(request, "orders")
    token = _key(request, key)
    player = room.player_by_key(token)
    if not player:
        raise HTTPException(403, "This key does not belong to the game.")
    text = _check_order_text(payload.get("orders", ""))
    feedback = service.submit_orders(room, player, text)
    return feedback


@app.get("/api/rooms/{code}/state")
def api_state(code: str, request: Request, key: Optional[str] = Query(None)):
    room = _resolve_room(code)
    token = _key(request, key)
    player = room.player_by_key(token)
    if not player:
        raise HTTPException(403, "This key does not belong to the game.")
    return JSONResponse(service.player_state(room, player.faction_id))


@app.get("/api/rooms/{code}/report")
def api_report(
    code: str,
    request: Request,
    turn: Optional[int] = Query(None),
    key: Optional[str] = Query(None),
):
    room = _resolve_room(code)
    token = _key(request, key)
    player = room.player_by_key(token)
    if not player:
        raise HTTPException(403, "This key does not belong to the game.")
    available = sorted(room.reports.keys())
    if not available:
        return {"turn": room.last_resolved_turn, "report": ""}
    if turn is None:
        turn = available[-1]
    reports = room.reports.get(turn)
    if not reports:
        raise HTTPException(404, f"No report for turn {turn}.")
    return {
        "turn": turn,
        "faction_id": player.faction_id,
        "report": reports.get(player.faction_id, ""),
    }


@app.post("/api/rooms/{code}/resolve")
def api_resolve(
    code: str,
    request: Request,
    payload: Optional[dict] = None,
    key: Optional[str] = Query(None),
):
    room = _resolve_room(code)
    token = _key(request, key)
    if not net.secret_eq(token, room.host_key):
        raise HTTPException(403, "Host key required to resolve.")
    ratelimit.check(request, "resolve")
    force = bool((payload or {}).get("force", False))
    try:
        result = service.resolve_turn(room, force=force)
    except service.NotReadyError as exc:
        raise HTTPException(409, str(exc))
    except service.BackupUnavailableError:
        raise HTTPException(
            503,
            "Turn not resolved because the pre-turn backup failed. Contact the operator.",
        )
    return {
        "turn": result["turn"],
        "seed": result["seed"],
        "reports_available": True,
    }


@app.get("/api/rooms/{code}/agents")
def api_list_agents(code: str, request: Request, key: Optional[str] = Query(None)):
    """Host view: bot profiles for every faction slot in the room."""
    room = _resolve_room(code)
    _require_host_key(request, room, key)
    return {
        "code": room.code,
        "agents": {
            p.faction_id: _profile_payload(p.faction_id, profile)
            for p in room.players
            if (profile := default_registry().get(room.code, p.faction_id))
        },
    }


@app.put("/api/rooms/{code}/agents/{faction_id}")
def api_upsert_agent(
    code: str,
    faction_id: str,
    request: Request,
    payload: Optional[dict] = None,
    key: Optional[str] = Query(None),
):
    """Host-only: create or patch the bot profile for one faction slot."""
    room = _resolve_room(code)
    _require_host_key(request, room, key)
    _faction_by_id(room, faction_id)
    profile = default_registry().get(room.code, faction_id) or AgentProfile()
    body = payload or {}
    if "model" in body:
        if not isinstance(body["model"], str):
            raise HTTPException(400, "model must be a string.")
        profile.model = body["model"].strip()
    if "persona" in body:
        if not isinstance(body["persona"], str):
            raise HTTPException(400, "persona must be a string.")
        profile.persona = body["persona"].strip()
    if "temperature" in body:
        try:
            temperature = float(body["temperature"])
        except (TypeError, ValueError):
            raise HTTPException(400, "temperature must be a number.")
        if not 0.0 <= temperature <= 2.0:
            raise HTTPException(400, "temperature must be between 0 and 2.")
        profile.temperature = temperature
    if "enabled" in body:
        if not isinstance(body["enabled"], bool):
            raise HTTPException(400, "enabled must be a boolean.")
        profile.enabled = body["enabled"]
    default_registry().set(room.code, faction_id, profile)
    return _profile_payload(faction_id, profile)


@app.delete("/api/rooms/{code}/agents/{faction_id}")
def api_delete_agent(
    code: str, faction_id: str, request: Request, key: Optional[str] = Query(None)
):
    """Host-only: remove a bot profile; the slot plays as human/external again."""
    room = _resolve_room(code)
    _require_host_key(request, room, key)
    _faction_by_id(room, faction_id)
    removed = default_registry().delete(room.code, faction_id)
    if not removed:
        raise HTTPException(404, "No agent profile for that faction.")
    return {"deleted": faction_id}


@app.post("/api/rooms/{code}/agents/{faction_id}/run")
def api_run_agent(
    code: str,
    faction_id: str,
    request: Request,
    key: Optional[str] = Query(None),
    background: bool = Query(False),
):
    """Host-only: have one bot decide and submit orders for the next turn.

    ``?background=1`` returns 202 with a job id immediately and plays the
    seat on the bot worker; poll ``GET /api/bot-jobs/{job_id}``. The default
    stays synchronous and holds the connection until the turn is played.
    """
    room = _resolve_room(code)
    _require_host_key(request, room, key)
    ratelimit.check(request, "bot")
    player = _faction_by_id(room, faction_id)
    if background:
        return JSONResponse(
            _submit_bot_job(room.code, faction_id), status_code=202
        )
    try:
        return orchestrator.run_bot_turn(room, player)
    except orchestrator.BotError as exc:
        status = 503 if str(exc).startswith("LLM not configured") else 400
        raise HTTPException(status, str(exc))
    except brain.LLMError as exc:
        raise HTTPException(503, str(exc))


def _submit_bot_job(room_code: str, faction_id: str) -> dict:
    """Enqueue one seat on the bot worker; returns its public payload."""
    try:
        job = bot_jobs.default_runner().submit(room_code, faction_id)
    except bot_jobs.QueueFullError as exc:
        raise HTTPException(503, str(exc))
    payload = job.public()
    payload["status_url"] = f"/api/bot-jobs/{job.id}"
    return payload


@app.get("/api/bot-jobs/{job_id}")
def api_bot_job(
    job_id: str, request: Request, key: Optional[str] = Query(None)
):
    """Poll one background bot turn. Any key valid for its room works."""
    job = bot_jobs.default_runner().get(job_id)
    if not job:
        raise HTTPException(404, "No such bot job.")
    room = _resolve_room(job.room_code)
    token = _key(request, key)
    if not room.player_by_key(token) and not net.secret_eq(token, room.host_key):
        raise HTTPException(403, "This key does not belong to the game.")
    return job.public()


@app.get("/api/rooms/{code}/map")
def api_map(
    code: str,
    request: Request,
    format: str = "json",
    turn: Optional[int] = Query(None),
    faction: Optional[str] = Query(None),
    key: Optional[str] = Query(None),
):
    """Map payloads for agents: fog-of-war json/svg, or png for vision models.

    ``format`` is json (default), svg, or png. ``turn`` rewinds to the end of
    a resolved turn. A player sees their own seat's fog of war; the host may
    pass ``faction`` or omit it for the all-visible board.
    """
    room = _resolve_room(code)
    token = _key(request, key)
    player = room.player_by_key(token)
    is_host = net.secret_eq(token, room.host_key)
    if not player and not is_host:
        raise HTTPException(403, "This key does not belong to the game.")
    fmt = (format or "json").lower()
    if fmt not in ("json", "svg", "png"):
        raise HTTPException(400, "format must be json, svg, or png.")
    if faction and not is_host:
        raise HTTPException(403, "Only the host may view another faction's map.")
    faction_id = (
        faction if (is_host and faction) else (player.faction_id if player else None)
    )
    all_visible = is_host and not faction
    try:
        payload = service.ai_map(
            room, faction_id, fmt=fmt, turn=turn, all_visible=all_visible
        )
    except service.TurnNotFoundError as exc:
        raise HTTPException(404, str(exc))
    except mapimg.PngBackendUnavailable as exc:
        raise HTTPException(501, str(exc))
    if fmt == "json":
        return JSONResponse(payload["json"])
    if fmt == "svg":
        return HTMLResponse(payload["svg"])
    return Response(payload["png"], media_type="image/png")


def _run_all_budget_seconds() -> float:
    """Wall-clock ceiling for one run-all request.

    Each bot carries brain's own retry budget, so six slow bots could
    otherwise hold a threadpool worker for the sum of all of them. Bots that
    do not get their turn are reported as skipped, not silently dropped.
    """
    raw = os.environ.get("SOE_RUN_ALL_BUDGET_SECONDS", "").strip()
    try:
        return max(60.0, float(raw) if raw else 600.0)
    except ValueError:
        return 600.0


@app.post("/api/rooms/{code}/agents/run-all")
def api_run_all_agents(
    code: str,
    request: Request,
    key: Optional[str] = Query(None),
    background: bool = Query(False),
):
    """Host-only: run every enabled bot in the room, one turn each.

    ``?background=1`` enqueues each enabled seat and returns its job id
    immediately; the worker plays them one at a time.
    """
    room = _resolve_room(code)
    _require_host_key(request, room, key)
    registry = default_registry()
    results = []
    jobs: list[dict] = []
    started = time.monotonic()
    for player in room.players:
        profile = registry.get(room.code, player.faction_id)
        if not profile or not profile.enabled:
            continue
        # One charge per bot: this endpoint's cost scales with the room's
        # size, so counting the request once would price it wrong. Stopping
        # beats a 429 here -- the bots above this one already ran, and the
        # caller needs to be told which.
        try:
            ratelimit.check(request, "bot")
        except HTTPException as exc:
            results.append({"faction_id": player.faction_id, "error": exc.detail})
            break
        if background:
            payload = _submit_bot_job(room.code, player.faction_id)
            jobs.append(
                {
                    "faction_id": player.faction_id,
                    "job_id": payload["job_id"],
                    "status_url": payload["status_url"],
                }
            )
            continue
        if time.monotonic() - started >= _run_all_budget_seconds():
            results.append(
                {
                    "faction_id": player.faction_id,
                    "error": (
                        "Skipped: the run-all time budget ran out; "
                        "run this bot individually."
                    ),
                }
            )
            continue
        try:
            results.append(orchestrator.run_bot_turn(room, player))
        except Exception as exc:  # noqa: BLE001 - report per-bot, keep going
            results.append(
                {
                    "faction_id": player.faction_id,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    if background:
        if not jobs:
            raise HTTPException(400, "No enabled bots in this room.")
        return JSONResponse({"jobs": jobs}, status_code=202)
    if not results:
        raise HTTPException(400, "No enabled bots in this room.")
    return {"results": results}


# ============================================================================
# coach API — the agent as an owned object (Phase 1)
# ============================================================================


def _presented_coach_key(request: Request, key: Optional[str] = None) -> str:
    return (
        request.headers.get(COACH_KEY_HEADER)
        or _accept_query_credential(request, key, "The coach key")
        or request.cookies.get(COACH_COOKIE, "")
    ).strip()


def _coach_key(request: Request, key: Optional[str] = None) -> str:
    token = _presented_coach_key(request, key)
    if not token:
        raise HTTPException(
            401, f"Missing coach key ({COACH_KEY_HEADER} header or ?coach_key=)."
        )
    return token


def _optional_coach(request: Request, key: Optional[str] = None) -> Coach | None:
    token = _presented_coach_key(request, key)
    if not token:
        return None
    try:
        return coaches.default_store().require(token)
    except CoachAuthError:
        return None


def _require_coach(request: Request, key: Optional[str] = None) -> Coach:
    try:
        return coaches.default_store().require(_coach_key(request, key))
    except CoachAuthError as exc:
        raise HTTPException(403, str(exc))


def _version_payload(version) -> dict:
    return {
        "version": version.version,
        "state": version.state,
        "persona": version.persona,
        "doctrine": dict(version.doctrine),
        "runtime": dict(version.runtime),
        "notes": version.notes,
        "created_at": version.created_at,
        "frozen_at": version.frozen_at,
        "content_hash": version.content_hash,
    }


def _blueprint_payload(blueprint, *, coach: Coach) -> dict:
    return {
        "id": blueprint.id,
        "name": blueprint.name,
        "coach_id": blueprint.coach_id,
        "mine": blueprint.coach_id == coach.id,
        "visibility": blueprint.visibility,
        "retired": blueprint.retired,
        "created_at": blueprint.created_at,
        "updated_at": blueprint.updated_at,
        "versions": [_version_payload(v) for v in blueprint.versions],
    }


def _blueprint_http(exc: BlueprintError) -> HTTPException:
    """Access failures are 404, not 403: a 403 confirms the id exists."""
    if isinstance(exc, BlueprintAccessError):
        return HTTPException(404, str(exc))
    if isinstance(exc, BlueprintIntegrityError):
        return HTTPException(409, str(exc))
    return HTTPException(400, str(exc))


@app.post("/api/coaches")
def api_create_coach(request: Request, payload: Optional[dict] = None):
    """Register a coach. The key is returned once and stored only hashed."""
    body = payload or {}
    ratelimit.check(request, "signup")
    _require_beta_invite(request, body.get("invite", ""))
    try:
        coach, key = coaches.default_store().create(body.get("name", ""))
    except CoachError as exc:
        raise HTTPException(400, str(exc))
    return {
        "coach_id": coach.id,
        "name": coach.display_name,
        "coach_key": key,
        "created_at": coach.created_at,
    }


@app.get("/api/blueprints")
def api_list_blueprints(request: Request, coach_key: Optional[str] = Query(None)):
    """Every blueprint this coach may read: their own, plus public ones."""
    coach = _require_coach(request, coach_key)
    store = blueprints.default_store()
    return {
        "coach_id": coach.id,
        "blueprints": [
            _blueprint_payload(b, coach=coach) for b in store.visible_to(coach)
        ],
    }


@app.post("/api/blueprints")
def api_create_blueprint(
    request: Request, payload: dict, coach_key: Optional[str] = Query(None)
):
    """Create a blueprint owned by this coach, with version 1 as a draft."""
    coach = _require_coach(request, coach_key)
    try:
        blueprint = blueprints.default_store().create(
            coach,
            payload.get("name", ""),
            persona=payload.get("persona", ""),
            doctrine=payload.get("doctrine"),
            runtime=payload.get("runtime"),
            notes=payload.get("notes", ""),
            visibility=payload.get("visibility", blueprints.VISIBILITY_PRIVATE),
        )
    except BlueprintError as exc:
        raise _blueprint_http(exc)
    return _blueprint_payload(blueprint, coach=coach)


@app.get("/api/blueprints/{blueprint_id}")
def api_get_blueprint(
    blueprint_id: str, request: Request, coach_key: Optional[str] = Query(None)
):
    coach = _require_coach(request, coach_key)
    try:
        blueprint = blueprints.default_store().get(coach, blueprint_id)
    except BlueprintError as exc:
        raise _blueprint_http(exc)
    return _blueprint_payload(blueprint, coach=coach)


@app.patch("/api/blueprints/{blueprint_id}/versions/{version}")
def api_edit_blueprint_version(
    blueprint_id: str,
    version: int,
    request: Request,
    payload: Optional[dict] = None,
    coach_key: Optional[str] = Query(None),
):
    """Edit a version. Strategy and runtime only while it is still a draft."""
    coach = _require_coach(request, coach_key)
    body = payload or {}
    try:
        blueprints.default_store().edit(
            coach,
            blueprint_id,
            version,
            persona=body.get("persona"),
            doctrine=body.get("doctrine"),
            runtime=body.get("runtime"),
            notes=body.get("notes"),
            name=body.get("name"),
            visibility=body.get("visibility"),
        )
        blueprint = blueprints.default_store().get(coach, blueprint_id)
    except BlueprintError as exc:
        raise _blueprint_http(exc)
    return _blueprint_payload(blueprint, coach=coach)


@app.post("/api/blueprints/{blueprint_id}/versions")
def api_new_blueprint_version(
    blueprint_id: str,
    request: Request,
    payload: Optional[dict] = None,
    coach_key: Optional[str] = Query(None),
):
    """Open a new draft version from an existing one."""
    coach = _require_coach(request, coach_key)
    body = payload or {}
    try:
        blueprints.default_store().new_version(
            coach, blueprint_id, from_version=body.get("from_version")
        )
        blueprint = blueprints.default_store().get(coach, blueprint_id)
    except BlueprintError as exc:
        raise _blueprint_http(exc)
    return _blueprint_payload(blueprint, coach=coach)


@app.post("/api/blueprints/{blueprint_id}/versions/{version}/freeze")
def api_freeze_blueprint_version(
    blueprint_id: str,
    version: int,
    request: Request,
    coach_key: Optional[str] = Query(None),
):
    """Seal a version and give it the hash a match can be bound to."""
    coach = _require_coach(request, coach_key)
    try:
        frozen = blueprints.default_store().freeze(coach, blueprint_id, version)
    except BlueprintError as exc:
        raise _blueprint_http(exc)
    return _version_payload(frozen)


@app.post("/api/blueprints/{blueprint_id}/clone")
def api_clone_blueprint(
    blueprint_id: str,
    request: Request,
    payload: Optional[dict] = None,
    coach_key: Optional[str] = Query(None),
):
    """Copy a readable blueprint into a new private one owned by this coach."""
    coach = _require_coach(request, coach_key)
    body = payload or {}
    try:
        clone = blueprints.default_store().clone(
            coach,
            blueprint_id,
            from_version=body.get("from_version"),
            name=body.get("name", ""),
        )
    except BlueprintError as exc:
        raise _blueprint_http(exc)
    return _blueprint_payload(clone, coach=coach)


@app.post("/api/blueprints/{blueprint_id}/retire")
def api_retire_blueprint(
    blueprint_id: str, request: Request, coach_key: Optional[str] = Query(None)
):
    """Take a blueprint out of circulation. Played matches still resolve it."""
    coach = _require_coach(request, coach_key)
    try:
        blueprint = blueprints.default_store().retire(coach, blueprint_id)
    except BlueprintError as exc:
        raise _blueprint_http(exc)
    return _blueprint_payload(blueprint, coach=coach)


@app.post("/api/rooms/{code}/agents/{faction_id}/blueprint")
def api_enroll_blueprint(
    code: str,
    faction_id: str,
    request: Request,
    payload: Optional[dict] = None,
    key: Optional[str] = Query(None),
    coach_key: Optional[str] = Query(None),
):
    """Enter a frozen blueprint version on one seat.

    Two credentials, because two different things are being authorised: the
    seat key (or the host key) says this seat may be reconfigured, and the
    coach key says this coach may play that blueprint. Neither implies the
    other — that is what lets a coach, not only the host, field their own
    agent. Passing ``blueprint_id: null`` clears the binding.
    """
    room = _resolve_room(code)
    seat = _faction_by_id(room, faction_id)
    token = _key(request, key)
    if not net.secret_eq(token, room.host_key) and not net.secret_eq(
        token, seat.agent_key
    ):
        raise HTTPException(403, "This key does not hold that seat.")
    coach = _require_coach(request, coach_key)
    body = payload or {}
    blueprint_id = body.get("blueprint_id")
    if default_registry().get(room.code, faction_id) is None:
        raise HTTPException(404, "No agent profile for that faction.")
    try:
        ref = (
            blueprints.default_store().enroll(
                coach, blueprint_id, body.get("version")
            )
            if blueprint_id
            else None
        )
        profile = default_registry().enroll_blueprint(room.code, faction_id, ref)
    except BlueprintError as exc:
        raise _blueprint_http(exc)
    return _profile_payload(faction_id, profile)


@app.post("/api/blueprints/migrate-personas")
def api_migrate_personas(
    request: Request,
    payload: Optional[dict] = None,
    coach_key: Optional[str] = Query(None),
    operator_key: str = "",
):
    """One-off: turn every seat persona into a frozen blueprint for this coach.

    Operator-gated, because it reads and rewrites profiles across every room,
    not only the calling coach's. The blueprints it creates belong to the coach
    whose key is presented.
    """
    body = payload or {}
    _require_operator(request, body.get("operator_key", operator_key))
    coach = _require_coach(request, coach_key)
    try:
        migrated = blueprints.migrate_personas(coach)
    except BlueprintError as exc:
        raise _blueprint_http(exc)
    return {"coach_id": coach.id, "migrated": migrated}


# ============================================================================
# training API — create, try, understand, change (Phase 2)
# ============================================================================


def _run_payload(run: training.TrainingRun) -> dict:
    return {
        "id": run.id,
        "blueprint_id": run.blueprint_id,
        "version": run.blueprint_version,
        "content_hash": run.blueprint_hash,
        "scenario_id": run.scenario_id,
        "opponent": run.opponent,
        "model": run.model,
        "status": run.status,
        "created_at": run.created_at,
        "finished_at": run.finished_at,
        "run_id": run.run_id,
        "error": run.error,
        "result": run.result,
    }


def _training_http(exc: Exception) -> HTTPException:
    if isinstance(exc, training.QuotaExceeded):
        return HTTPException(429, str(exc))
    if isinstance(exc, BlueprintError):
        return _blueprint_http(exc)
    return HTTPException(400, str(exc))


@app.get("/api/training/scenarios")
def api_training_scenarios(request: Request, coach_key: Optional[str] = Query(None)):
    """The fixed catalogue. Nothing here is chosen at request time."""
    _require_coach(request, coach_key)
    return {
        "scenarios": [
            {
                "id": scenario.id,
                "name": scenario.name,
                "description": scenario.description,
                "map": scenario.map,
                "turns": scenario.turns,
                "seed_pairs": scenario.seed_pairs,
                "opponent": scenario.opponent_label,
            }
            for scenario in training.scenarios().values()
        ]
    }


@app.get("/api/training")
def api_list_training(request: Request, coach_key: Optional[str] = Query(None)):
    """This coach's runs, newest first, with what is left of their allowance."""
    coach = _require_coach(request, coach_key)
    store = training.default_store()
    return {
        "coach_id": coach.id,
        "quota": store.quota_state(coach),
        "runs": [_run_payload(r) for r in store.for_coach(coach)],
    }


@app.post("/api/training")
def api_start_training(
    request: Request,
    payload: dict,
    background: BackgroundTasks,
    coach_key: Optional[str] = Query(None),
):
    """Start a training run of a frozen version against a catalogue opponent.

    The run is recorded before it is played and then played in the background:
    a batch takes minutes, and a coach should not be holding a request open to
    find out how it went. Poll ``GET /api/training/{id}``.
    """
    coach = _require_coach(request, coach_key)
    store = training.default_store()
    try:
        run = store.start(
            coach,
            payload.get("blueprint_id", ""),
            payload.get("scenario_id", ""),
            version=payload.get("version"),
        )
    except (training.TrainingError, BlueprintError) as exc:
        raise _training_http(exc)
    background.add_task(training.execute, run, store)
    return _run_payload(run)


@app.get("/api/training/{run_id}")
def api_get_training(
    run_id: str, request: Request, coach_key: Optional[str] = Query(None)
):
    coach = _require_coach(request, coach_key)
    try:
        run = training.default_store().get(coach, run_id)
    except training.TrainingError as exc:
        raise HTTPException(404, str(exc))
    return _run_payload(run)


def _debrief_or_404(coach: Coach, run_id: str) -> debrief.Debrief:
    store = training.default_store()
    try:
        run = store.get(coach, run_id)
    except training.TrainingError as exc:
        raise HTTPException(404, str(exc))
    if run.status != training.STATUS_COMPLETE:
        raise HTTPException(
            409,
            f"Training run '{run_id}' is {run.status}"
            + (f": {run.error}" if run.error else "."),
        )
    try:
        return debrief.build(run)
    except debrief.DebriefError as exc:
        raise HTTPException(409, str(exc))


@app.get("/api/training/{run_id}/debrief")
def api_training_debrief(
    run_id: str, request: Request, coach_key: Optional[str] = Query(None)
):
    """What this run's agent did, turn by turn, from the coach's seat only.

    Every field is read out of the persisted bundle. The opponent's orders and
    position are not in the payload: the coach gets the result of the match and
    a full account of their own play.
    """
    coach = _require_coach(request, coach_key)
    return _debrief_or_404(coach, run_id).as_dict()


@app.post("/api/training/{run_id}/iterate")
def api_training_iterate(
    run_id: str,
    request: Request,
    payload: Optional[dict] = None,
    coach_key: Optional[str] = Query(None),
):
    """Go from a debrief to the next attempt in one call.

    The loop Phase 2 exists to close is create, try, understand, change, and
    the last step is where a coach gives up if it takes six requests. This
    opens the next draft of the blueprint that was just trained — a new version
    of it by default, or a separate clone with ``as_clone`` — and returns it
    ready to edit, freeze and run again.
    """
    coach = _require_coach(request, coach_key)
    body = payload or {}
    try:
        run = training.default_store().get(coach, run_id)
    except training.TrainingError as exc:
        raise HTTPException(404, str(exc))
    store = blueprints.default_store()
    try:
        if body.get("as_clone"):
            blueprint = store.clone(
                coach,
                run.blueprint_id,
                from_version=run.blueprint_version,
                name=body.get("name", ""),
            )
        else:
            store.new_version(
                coach, run.blueprint_id, from_version=run.blueprint_version
            )
            blueprint = store.get(coach, run.blueprint_id)
    except BlueprintError as exc:
        raise _blueprint_http(exc)
    return {
        "from_run": run.id,
        "from_version": run.blueprint_version,
        "blueprint": _blueprint_payload(blueprint, coach=coach),
        "next_version": blueprint.latest().version,
    }


@app.get("/api/training/{run_id}/compare/{other_run_id}")
def api_training_compare(
    run_id: str,
    other_run_id: str,
    request: Request,
    coach_key: Optional[str] = Query(None),
):
    """Two of this coach's runs side by side — normally two versions of one
    blueprint. The payload says whether they were even asked the same question."""
    coach = _require_coach(request, coach_key)
    return debrief.compare(
        _debrief_or_404(coach, run_id), _debrief_or_404(coach, other_run_id)
    )


def _season_payload(season: competition.Season, store: competition.CompetitionStore) -> dict:
    return {
        "id": season.id,
        "competition": season.competition,
        "name": season.name,
        "status": season.status,
        "regulation": season.regulation,
        "regulation_hash": season.regulation_hash,
        "entries": [item.id for item in store.entries(season.id)],
        "matches": [item.id for item in store.matches(season.id)],
        "created_at": season.created_at,
        "frozen_at": season.frozen_at,
        "sealed_at": season.sealed_at,
    }


def _league_http(exc: Exception) -> HTTPException:
    if isinstance(exc, competition.CompetitionIntegrityError):
        return HTTPException(409, str(exc))
    if isinstance(exc, BlueprintError):
        return _blueprint_http(exc)
    return HTTPException(400, str(exc))


@app.get("/api/seasons")
def api_list_seasons(request: Request, coach_key: Optional[str] = Query(None)):
    """Seasons a coach may see. Drafts stay on the operator side."""
    _require_coach(request, coach_key)
    store = competition.default_store()
    visible = [
        item
        for item in store.seasons()
        if item.status != competition.STATUS_DRAFT
    ]
    return {"seasons": [_season_payload(item, store) for item in visible]}


@app.post("/api/seasons")
def api_create_season(request: Request, payload: Optional[dict] = None):
    _require_operator(request)
    body = payload or {}
    store = competition.default_store()
    try:
        season = store.create_season(
            str(body.get("name") or ""),
            catalogue_id=str(body.get("catalogue_id") or "coach_league"),
        )
        _apply_regulation_overrides(season, body)
        season = store.season(season.id)
    except (competition.CompetitionError, ValueError) as exc:
        raise _league_http(exc)
    return _season_payload(season, store)


@app.get("/api/seasons/{season_id}")
def api_get_season(season_id: str, request: Request, coach_key: Optional[str] = Query(None)):
    _require_coach(request, coach_key)
    store = competition.default_store()
    try:
        season = store.season(season_id)
    except competition.CompetitionError as exc:
        raise HTTPException(404, str(exc))
    return {
        **_season_payload(season, store),
        "standings": competition.standings(store, season.id),
    }


@app.post("/api/seasons/{season_id}/freeze")
def api_freeze_season(season_id: str, request: Request):
    _require_operator(request)
    try:
        season = competition.default_store().freeze(season_id)
    except competition.CompetitionError as exc:
        raise _league_http(exc)
    return _season_payload(season, competition.default_store())


@app.post("/api/seasons/{season_id}/enter")
def api_enter_season(
    season_id: str,
    request: Request,
    payload: Optional[dict] = None,
    coach_key: Optional[str] = Query(None),
):
    coach = _require_coach(request, coach_key)
    body = payload or {}
    try:
        entry = competition.default_store().enter(
            coach,
            season_id,
            str(body.get("blueprint_id") or ""),
            body.get("version"),
        )
    except (competition.CompetitionError, BlueprintError) as exc:
        raise _league_http(exc)
    return {
        "id": entry.id,
        "season_id": entry.season_id,
        "blueprint_id": entry.blueprint_id,
        "blueprint_version": entry.blueprint_version,
        "blueprint_hash": entry.blueprint_hash,
    }


@app.post("/api/seasons/{season_id}/pair")
def api_pair_season(season_id: str, request: Request):
    _require_operator(request)
    try:
        matches = competition.default_store().pair(season_id)
    except competition.CompetitionError as exc:
        raise _league_http(exc)
    return {"matches": [item.id for item in matches]}


@app.post("/api/seasons/{season_id}/dispatch")
def api_dispatch_season(
    season_id: str,
    request: Request,
    background: BackgroundTasks,
):
    _require_operator(request)
    store = competition.default_store()
    try:
        job = store.next_job(season_id)
    except competition.CompetitionError as exc:
        raise _league_http(exc)
    if job is None:
        raise HTTPException(409, "Nothing is queued.")
    background.add_task(competition.execute, job, store)
    return {"job_id": job.id, "match_id": job.match_id, "status": job.status}


@app.post("/api/seasons/{season_id}/run")
def api_run_season(
    season_id: str,
    request: Request,
    background: BackgroundTasks,
):
    """Play every queued match. The operator starts it; they do not edit the ledger."""
    _require_operator(request)
    store = competition.default_store()
    try:
        job = store.next_job(season_id)
    except competition.CompetitionError as exc:
        raise _league_http(exc)
    if job is None:
        raise HTTPException(409, "Nothing is queued.")
    background.add_task(competition.run_until_idle, store, season_id)
    return competition.completion(store, season_id)


@app.post("/api/seasons/{season_id}/recover")
def api_recover_season(season_id: str, request: Request):
    _require_operator(request)
    store = competition.default_store()
    try:
        store.season(season_id)
    except competition.CompetitionError as exc:
        raise HTTPException(404, str(exc))
    orphans = store.requeue_orphans()
    return {"requeued": [item.id for item in orphans]}


@app.get("/api/seasons/{season_id}/standings")
def api_standings(season_id: str, request: Request, coach_key: Optional[str] = Query(None)):
    _require_coach(request, coach_key)
    store = competition.default_store()
    try:
        store.season(season_id)
    except competition.CompetitionError as exc:
        raise HTTPException(404, str(exc))
    return {"standings": competition.standings(store, season_id)}


@app.post("/api/jobs/{job_id}/retry")
def api_retry_job(job_id: str, request: Request):
    _require_operator(request)
    try:
        job = competition.default_store().retry(job_id)
    except competition.CompetitionError as exc:
        raise _league_http(exc)
    return {"job_id": job.id, "status": job.status, "attempts": job.attempts}


@app.post("/api/jobs/{job_id}/suspend")
def api_suspend_job(job_id: str, request: Request):
    _require_operator(request)
    try:
        job = competition.default_store().suspend_job(job_id)
    except competition.CompetitionError as exc:
        raise _league_http(exc)
    return {"job_id": job.id, "status": job.status}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
