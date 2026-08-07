"""
Web server for Spoils of Empire — humans in the browser, agents over JSON.

Run locally with:
    uvicorn webapp.main:app --reload --port 8000

Humans get a minimal HTMX UI; agents get the /api endpoints, where a per-room
agent key is the only credential (header ``X-Agent-Key`` or ``key`` query
param).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import (
    FastAPI,
    Form,
    HTTPException,
    Query,
    Request,
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from spoils_engine import map_loader

from webapp import mapview, service
from webapp.rooms import Room, RoomError, default_store

app = FastAPI(title="Spoils of Empire", version="0.1.0")

_TEMPLATES = Path(__file__).resolve().parent / "templates"
_STATIC = Path(__file__).resolve().parent / "static"

templates = Jinja2Templates(directory=str(_TEMPLATES))
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

_store = default_store()

HOST_COOKIE = "soe_host"
PLAYER_COOKIE = "soe_player"


def _player_cookie_name(code: str) -> str:
    return f"{PLAYER_COOKIE}_{code}"


def _host_cookie_name(code: str) -> str:
    return f"{HOST_COOKIE}_{code}"


def _resolve_room(code: str) -> Room:
    room = _store.get(code)
    if not room:
        raise HTTPException(404, "No game found with that code.")
    return room


def _player_for(room: Room, request: Request, key: Optional[str]) -> Room | None:
    if key:
        return room.player_by_key(key)
    cookie = request.cookies.get(_player_cookie_name(room.code))
    if cookie:
        return room.player_by_key(cookie)
    return None


def _submission_text(room: Room, player: Room | None) -> str:
    if not player:
        return ""
    return (
        room.submissions
        .get(room.next_turn(), {})
        .get(player.faction_id, {})
        .get("orders", "")
    )


def _panel_context(request: Request, room: Room, player, is_host: bool, notice: str = "") -> dict:
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
    }


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
        request, "index.html",
        {
            "maps": maps,
            "default_map": chosen,
            "map_svg": _map_fragment(chosen) if maps else "",
            "legend": mapview.legend_html(),
            "error": request.query_params.get("error", ""),
        },
    )


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
def create_room(request: Request, name: str = Form(""), slots: int = Form(2),
                map_file: str = Form(None)):
    map_file = map_file or service.default_map()
    if map_file not in service.available_maps():
        raise HTTPException(400, f"Unknown map '{map_file}'.")
    room = _store.create(name, slots, map_file)
    try:
        service.create_game(room)
    except (RuntimeError, FileNotFoundError, map_loader.MapValidationError) as exc:
        raise HTTPException(400 if not isinstance(exc, RuntimeError) else 500, str(exc))
    response = RedirectResponse(url=f"/room/{room.code}", status_code=303)
    response.set_cookie(_host_cookie_name(room.code), room.host_key, httponly=True)
    return response


@app.post("/join")
def join_room(request: Request, code: str = Form(...), pin: str = Form(...),
              display_name: str = Form(...)):
    try:
        room, player = _store.join(code, pin, display_name)
    except RoomError as exc:
        return RedirectResponse(url=f"/?error={exc}", status_code=303)
    response = RedirectResponse(url=f"/room/{room.code}", status_code=303)
    response.set_cookie(_player_cookie_name(room.code), player.agent_key, httponly=True)
    return response


@app.get("/room/{code}", response_class=HTMLResponse)
def room_page(request: Request, code: str):
    room = _resolve_room(code)
    player = _player_for(room, request, None)
    is_host = request.cookies.get(_host_cookie_name(code)) == room.host_key
    return templates.TemplateResponse(
        request, "room.html",
        _panel_context(request, room, player, is_host),
    )


@app.get("/room/{code}/panel", response_class=HTMLResponse)
def room_panel(request: Request, code: str):
    """HTMX fragment: live room status, order form, latest report."""
    room = _resolve_room(code)
    player = _player_for(room, request, None)
    is_host = request.cookies.get(_host_cookie_name(code)) == room.host_key
    return templates.TemplateResponse(
        request, "partials/panel.html",
        _panel_context(request, room, player, is_host),
    )


@app.post("/room/{code}/orders", response_class=HTMLResponse)
def submit_orders(request: Request, code: str, orders: str = Form(...)):
    room = _resolve_room(code)
    player = _player_for(room, request, None)
    is_host = request.cookies.get(_host_cookie_name(code)) == room.host_key
    if not player:
        return templates.TemplateResponse(
            request, "partials/panel.html",
            _panel_context(request, room, None, is_host, "Join the game first."),
        )
    feedback = service.submit_orders(room, player, orders)
    notice = f"Stored {feedback['parsed']} order(s) for turn {feedback['turn']}."
    if not feedback["parsed"]:
        notice = "No orders recognised."
    if feedback["warnings"]:
        notice += " Warnings: " + "; ".join(feedback["warnings"])
    return templates.TemplateResponse(
        request, "partials/panel.html",
        _panel_context(request, room, player, is_host, notice),
    )


@app.post("/room/{code}/resolve", response_class=HTMLResponse)
def resolve_now(request: Request, code: str):
    room = _resolve_room(code)
    is_host = request.cookies.get(_host_cookie_name(code)) == room.host_key
    player = _player_for(room, request, None)
    if not is_host:
        return templates.TemplateResponse(
            request, "partials/panel.html",
            _panel_context(request, room, player, False, "Only the host can resolve."),
        )
    try:
        result = service.resolve_turn(room, force=False)
        notice = f"Turn {result['turn']} resolved (seed {result['seed']})."
    except service.NotReadyError as exc:
        notice = f"Not resolved: {exc}"
    except Exception as exc:  # noqa: BLE001 - surface engine errors in the panel
        notice = f"Resolution failed: {exc}"
    return templates.TemplateResponse(
        request, "partials/panel.html",
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


@app.post("/api/rooms")
def api_create_room(payload: dict):
    name = payload.get("name", "")
    slots = int(payload.get("slots", 2))
    map_file = payload.get("map") or service.default_map()
    if map_file not in service.available_maps():
        raise HTTPException(400, f"Unknown map '{map_file}'. Available: {service.available_maps()}")
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
def api_join(payload: dict):
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
    if not room.player_by_key(token) and token != room.host_key:
        raise HTTPException(403, "This key does not belong to the game.")
    return service.room_status(room)


@app.post("/api/rooms/{code}/orders")
def api_orders(code: str, request: Request, payload: dict,
               key: Optional[str] = Query(None)):
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
def api_report(code: str, request: Request, turn: Optional[int] = Query(None),
               key: Optional[str] = Query(None)):
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
def api_resolve(code: str, request: Request, payload: Optional[dict] = None,
                key: Optional[str] = Query(None)):
    room = _resolve_room(code)
    token = _key(request, key)
    if token != room.host_key:
        raise HTTPException(403, "Host key required to resolve.")
    force = bool((payload or {}).get("force", False))
    try:
        result = service.resolve_turn(room, force=force)
    except service.NotReadyError as exc:
        raise HTTPException(409, str(exc))
    return {
        "turn": result["turn"],
        "seed": result["seed"],
        "reports_available": True,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
