"""
Web server for SOE — humans in the browser, agents over JSON.

Run locally with:
    uvicorn webapp.main:app --port 8000

Humans get a minimal HTMX UI; agents get the /api endpoints, where a per-room
agent key is the only credential (header ``X-Agent-Key`` or ``key`` query
param).
"""

from __future__ import annotations

import os
import secrets
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import (
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

from webapp import backups, mapimg, mapview, service
from webapp.ai import autoplay, brain, orchestrator
from webapp.ai.registry import AgentProfile, default_registry
from webapp.observability import logger, request_id
from webapp.rooms import (
    GAMES_ROOT,
    SERVER_DATA,
    Room,
    RoomError,
    RoomPlayer,
    default_store,
)

app = FastAPI(title="SOE", version=__version__)

_TEMPLATES = Path(__file__).resolve().parent / "templates"
_STATIC = Path(__file__).resolve().parent / "static"

templates = Jinja2Templates(directory=str(_TEMPLATES))
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

_store = default_store()

HOST_COOKIE = "soe_host"
PLAYER_COOKIE = "soe_player"
BETA_INVITE_HEADER = "X-SOE-Beta-Invite"
BETA_ACCESS_CODE = os.environ.get("SOE_BETA_ACCESS_CODE", "").strip()
# The server's LLM key and the URL that key is sent to are operator property,
# not room property: anyone can create a room, so a host cookie is not proof
# of anything here. Without a configured secret only the server's own console
# qualifies.
OPERATOR_COOKIE = "soe_operator"
OPERATOR_HEADER = "X-SOE-Operator-Key"
OPERATOR_KEY = os.environ.get("SOE_OPERATOR_KEY", "").strip()
_LOOPBACK_CLIENTS = frozenset({"127.0.0.1", "::1", "localhost"})
COOKIE_SECURE = os.environ.get("SOE_COOKIE_SECURE", "0").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
COOKIE_MAX_AGE = 30 * 24 * 60 * 60


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
    if BETA_ACCESS_CODE and (
        request.headers.get(BETA_INVITE_HEADER, "") != BETA_ACCESS_CODE
        and str(supplied or "").strip() != BETA_ACCESS_CODE
    ):
        raise HTTPException(403, "A valid beta invitation is required.")


def _is_operator(request: Request, supplied: str = "") -> bool:
    """True for the server operator, never merely for a room host."""
    if OPERATOR_KEY:
        offered = (
            request.headers.get(OPERATOR_HEADER, ""),
            request.cookies.get(OPERATOR_COOKIE, ""),
            str(supplied or "").strip(),
        )
        return any(
            secrets.compare_digest(value, OPERATOR_KEY) for value in offered if value
        )
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
        "this server from its own console.",
    )


def _remember_operator(response, supplied: str) -> None:
    """Keep a browser operator signed in after a correct key."""
    supplied = str(supplied or "").strip()
    if OPERATOR_KEY and supplied and secrets.compare_digest(supplied, OPERATOR_KEY):
        _set_auth_cookie(response, OPERATOR_COOKIE, OPERATOR_KEY)


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
    if request.cookies.get(_host_cookie_name(room.code)) != room.host_key:
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
        if request.cookies.get(_host_cookie_name(r.code)) != r.host_key:
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
        },
    )


def _any_host_session(request: Request) -> bool:
    """True when the request carries a valid host cookie for any room."""
    return any(
        request.cookies.get(_host_cookie_name(r.code)) == r.host_key
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
            "model": brain.LLM_MODEL,
            "base_url": brain.LLM_BASE_URL,
            "vision": orchestrator.VISION_ENABLED,
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
    is_host = request.cookies.get(_host_cookie_name(code)) == room.host_key
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
            result = orchestrator.run_bot_turn(room, player)
            msg = (
                f"Bot {player.faction_name} ran: {result['parsed']} order(s) submitted."
            )
        except orchestrator.BotError as exc:
            msg = f"Bot {player.faction_name} not run: {exc}"
        except Exception as exc:  # noqa: BLE001 - keep the dashboard usable
            msg = f"Bot {player.faction_name} failed: {type(exc).__name__}: {exc}"
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
    is_host = request.cookies.get(_host_cookie_name(code)) == room.host_key
    return templates.TemplateResponse(
        request,
        "partials/panel.html",
        _panel_context(request, room, player, is_host),
    )


@app.post("/room/{code}/orders", response_class=HTMLResponse)
def submit_orders(request: Request, code: str, orders: str = Form(...)):
    room = _resolve_room(code)
    player = _player_for(room, request, None)
    is_host = request.cookies.get(_host_cookie_name(code)) == room.host_key
    if not player:
        return templates.TemplateResponse(
            request,
            "partials/panel.html",
            _panel_context(request, room, None, is_host, "Join the game first."),
        )
    feedback = service.submit_orders(room, player, orders)
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
    room = _resolve_room(code)
    is_host = request.cookies.get(_host_cookie_name(code)) == room.host_key
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
    token = request.headers.get("X-Agent-Key") or key
    if not token:
        raise HTTPException(401, "Missing agent key (X-Agent-Key header or ?key=).")
    return token


def _require_host_key(request: Request, room: Room, key: Optional[str]) -> None:
    token = _key(request, key)
    if token != room.host_key:
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
    }


@app.post("/api/rooms")
def api_create_room(request: Request, payload: dict):
    _require_beta_invite(request, payload.get("invite", ""))
    name = payload.get("name", "")
    slots = int(payload.get("slots", 2))
    map_file = payload.get("map") or service.default_map()
    if map_file not in service.available_maps():
        raise HTTPException(
            400, f"Unknown map '{map_file}'. Available: {service.available_maps()}"
        )
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
    _require_beta_invite(request, payload.get("invite", ""))
    try:
        room, player = _store.join(payload["code"], payload["pin"], payload["name"])
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
    if not room.player_by_key(token) and token != room.host_key:
        raise HTTPException(403, "This key does not belong to the game.")
    return service.room_status(room)


@app.post("/api/rooms/{code}/orders")
def api_orders(
    code: str, request: Request, payload: dict, key: Optional[str] = Query(None)
):
    room = _resolve_room(code)
    token = _key(request, key)
    player = room.player_by_key(token)
    if not player:
        raise HTTPException(403, "This key does not belong to the game.")
    text = payload.get("orders", "")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(400, "No orders given.")
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
    if token != room.host_key:
        raise HTTPException(403, "Host key required to resolve.")
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
    code: str, faction_id: str, request: Request, key: Optional[str] = Query(None)
):
    """Host-only: have one bot decide and submit orders for the next turn."""
    room = _resolve_room(code)
    _require_host_key(request, room, key)
    player = _faction_by_id(room, faction_id)
    try:
        return orchestrator.run_bot_turn(room, player)
    except orchestrator.BotError as exc:
        status = 503 if str(exc).startswith("LLM not configured") else 400
        raise HTTPException(status, str(exc))
    except brain.LLMError as exc:
        raise HTTPException(503, str(exc))


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
    is_host = token == room.host_key
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


@app.post("/api/rooms/{code}/agents/run-all")
def api_run_all_agents(code: str, request: Request, key: Optional[str] = Query(None)):
    """Host-only: run every enabled bot in the room, one turn each."""
    room = _resolve_room(code)
    _require_host_key(request, room, key)
    registry = default_registry()
    results = []
    for player in room.players:
        profile = registry.get(room.code, player.faction_id)
        if not profile or not profile.enabled:
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
    if not results:
        raise HTTPException(400, "No enabled bots in this room.")
    return {"results": results}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
