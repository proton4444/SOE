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


def _setup_context(room: Room, notice: str = "") -> dict:
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
    return {"room": room, "slots": slots, "notice": notice}


def _require_master(request: Request, room: Room) -> None:
    if request.cookies.get(_host_cookie_name(room.code)) != room.host_key:
        raise HTTPException(403, "The master dashboard requires the host session.")


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
        },
    )


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
    """HTMX fragment: SVG + landmass index for one map."""
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
        _setup_context(room, request.query_params.get("msg", "")),
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
