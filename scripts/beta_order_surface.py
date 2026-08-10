"""Full order surface for beta testing.

Maps rules.md verbs to engine order types, and builds opportunistic
orders so a beta player (human or AI) can exercise every live command.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from spoils_engine import config
from spoils_engine.models import UnitType
from spoils_engine.phases.pathing import find_route
from spoils_engine.models import RoadQuality

if TYPE_CHECKING:
    from spoils_engine import models

# Every primary order_type() the engine exposes.
ENGINE_ORDER_TYPES = (
    "ABSORB",
    "ADDRESS",
    "ALLY",
    "ASSIGN",
    "ATTACK",
    "AWAIT",
    "BLESS",
    "BORROW",
    "BUILD",
    "BUY_SHIP",
    "CAPTURE",
    "CHARGE",
    "COLLECT",
    "CONJURE",
    "CREATE",
    "CURSE",
    "ENEMY",
    "ENSLAVE",
    "FLY",
    "FORTIFY",
    "FREE",
    "GET",
    "HALT",
    "HEAL",
    "IF",
    "INTERROGATE",
    "INVEST",
    "JOIN",
    "KILL",
    "LURK",
    "MINE",
    "MOVE",
    "NAME",
    "NEUTRAL",
    "NONCOM",
    "OFFER",
    "PASSAGE",
    "PASSWORD",
    "PAY",
    "POST",
    "PRAY",
    "PREACH",
    "PROBE",
    "PROMOTE",
    "RECRUIT",
    "REPAY",
    "REPEAT",
    "REPORT",
    "RESURRECT",
    "SAIL",
    "SAY",
    "SCAN",
    "SCRY",
    "SEARCH",
    "SECURE",
    "STOP",
    "STUDY",
    "SUMMON",
    "SUPPORT",
    "TAX",
    "TEACH",
    "TELEPORT",
    "TRADE",
    "TRAIN",
    "TRANSFER",
    "UNFORTIFY",
    "UNLOAD",
    "UNNAME",
    "WORK",
)

# rules.md Table of Contents command verbs → engine order_type (aliases fold).
RULES_VERB_TO_ENGINE = {
    "ABSORB": "ABSORB",
    "ADDRESS": "ADDRESS",
    "ALLY": "ALLY",
    "ASSIGN": "ASSIGN",
    "ATTACK": "ATTACK",
    "AWAIT": "AWAIT",
    "BLESS": "BLESS",
    "BORROW": "BORROW",
    "BUILD": "BUILD",
    "BUY": "TRADE",
    "BUY PASSAGE": "PASSAGE",
    "CAPTURE": "CAPTURE",
    "CHARGE": "CHARGE",
    "COLLECT": "COLLECT",
    "COMBATANT": "NONCOM",
    "COME": "MOVE",
    "CONJURE": "CONJURE",
    "CONSTRUCT": "BUILD",
    "CREATE": "CREATE",
    "CURE": "HEAL",
    "CURSE": "CURSE",
    "DISCARD": "FREE",
    "DISMISS": "FREE",
    "ENEMY": "ENEMY",
    "ENSLAVE": "ENSLAVE",
    "EXECUTE": "KILL",
    "EXPLORE": "SEARCH",
    "FLY": "FLY",
    "FORTIFY": "FORTIFY",
    "FREE": "FREE",
    "GATHER": "COLLECT",
    "GET": "GET",
    "GIVE": "ASSIGN",
    "GO": "MOVE",
    "HALT": "HALT",
    "HEAL": "HEAL",
    "HIRE": "RECRUIT",
    "INTERROGATE": "INTERROGATE",
    "JOIN": "JOIN",
    "INVEST": "INVEST",
    "KILL": "KILL",
    "LURK": "LURK",
    "MAKE": "BUILD",
    "MINE": "MINE",
    "MOVE": "MOVE",
    "NAME": "NAME",
    "NEUTRAL": "NEUTRAL",
    "NONCOM": "NONCOM",
    "OBTAIN": "GET",
    "OFFER": "OFFER",
    "PASSWORD": "PASSWORD",
    "PAY": "PAY",
    "POST": "POST",
    "PRAY": "PRAY",
    "PREACH": "PREACH",
    "PROBE": "PROBE",
    "PROMOTE": "PROMOTE",
    "PURCHASE": "TRADE",
    "QUERY": "REPORT",
    "RECHARGE": "CHARGE",
    "RECRUIT": "RECRUIT",
    "REPAY": "REPAY",
    "REPORT": "REPORT",
    "RELEASE": "FREE",
    "SAIL": "SAIL",
    "SAY": "SAY",
    "SCAN": "SCAN",
    "SEARCH": "SEARCH",
    "SECURE": "SECURE",
    "SELL": "TRADE",
    "STOP": "STOP",
    "STUDY": "STUDY",
    "SUMMON": "SUMMON",
    "SUPPORT": "SUPPORT",
    "TAKE": "GET",
    "TAX": "TAX",
    "TEACH": "TEACH",
    "TELEPORT": "TELEPORT",
    "TELL": "SAY",
    "TRAIN": "TRAIN",
    "TRANSFER": "TRANSFER",
    "TRAVEL": "MOVE",
    "UNFORTIFY": "UNFORTIFY",
    "UNLOAD": "UNLOAD",
    "UNLURK": "LURK",
    "UNNAME": "UNNAME",
    "WAIT": "AWAIT",
    "WORK": "WORK",
}


def _alive_chars(gs: models.GameState, faction_id: str) -> list:
    return [
        c
        for c in gs.characters.values()
        if c.faction_id == faction_id and not c.is_dead and not c.is_prisoner
    ]


def _soldiers_at(gs, faction_id: str, city_id: str) -> int:
    return sum(
        s.count
        for s in gs.unit_stacks.values()
        if s.faction_id == faction_id
        and s.location_city_id == city_id
        and s.unit_type == UnitType.SOLDIER
    )


def _workers_total(gs, faction_id: str) -> int:
    return sum(
        s.count
        for s in gs.unit_stacks.values()
        if s.faction_id == faction_id and s.unit_type == UnitType.WORKER
    )


def _soldiers_total(gs, faction_id: str) -> int:
    return sum(
        s.count
        for s in gs.unit_stacks.values()
        if s.faction_id == faction_id and s.unit_type == UnitType.SOLDIER
    )


def _controller(gs, city_id: str) -> str | None:
    for fid, fac in gs.factions.items():
        if city_id in fac.controlled_city_ids:
            return fid
    return None


def _land_neighbors(gs, city_id: str) -> list:
    out = []
    for city, road in gs.world_map.neighbors(city_id):
        if road.quality == RoadQuality.SEA:
            continue
        out.append(city)
    return out


def _reachable_land(gs, from_city_id: str, max_mp: float | None = None):
    if max_mp is None:
        max_mp = float(config.CHARACTER_MOVEMENT_POINTS_PER_TURN)
    results = []
    for city_id, city in gs.world_map.cities.items():
        if city_id == from_city_id:
            continue
        route = find_route(from_city_id, city_id, gs, allow_land=True, allow_sea=False)
        if route and route.cost <= max_mp + 1e-9:
            results.append((city, route.cost))
    results.sort(key=lambda t: t[1])
    return results


def _subordinates(gs, faction_id: str, leader) -> list:
    return [c for c in _alive_chars(gs, faction_id) if c.id != leader.id]


def _prisoners_held(gs, faction_id: str, city_id: str) -> list:
    out = []
    for c in gs.characters.values():
        if not c.is_prisoner or c.location_city_id != city_id:
            continue
        captor = gs.characters.get(getattr(c, "captor_id", "") or "")
        if captor and captor.faction_id == faction_id:
            out.append(c)
        elif c.faction_id != faction_id:
            out.append(c)
    return out


def _ships_at(gs, faction_id: str, city_id: str) -> list:
    return [
        s
        for s in gs.ships.values()
        if s.faction_id == faction_id and s.location_city_id == city_id
    ]


def _rival_faction_name(gs, faction_id: str) -> str | None:
    for fid, fac in gs.factions.items():
        if fid == faction_id or getattr(fac, "is_npc", False):
            continue
        return fac.name
    return None


def _own_items(gs, faction_id: str) -> list:
    out = []
    for item in (getattr(gs, "magical_items", None) or {}).values():
        owner = getattr(item, "holder_character_id", "") or ""
        ch = gs.characters.get(owner)
        if ch and ch.faction_id == faction_id:
            out.append(item)
    return out


def exercise_orders(
    lines: list[str],
    gs,
    faction_id: str,
    leader,
    city_name: str,
    gold: float,
    soldiers_here: int,
    enemies: list,
    moved: bool,
    style: str,
    rng: random.Random,
) -> None:
    """Append opportunistic orders covering the full command surface."""
    fac = gs.factions[faction_id]
    city = gs.world_map.cities.get(leader.location_city_id)
    turn = gs.turn_number + 1
    subs = _subordinates(gs, faction_id, leader)
    sub = subs[0] if subs else None
    rival_name = _rival_faction_name(gs, faction_id)
    prisoners = _prisoners_held(gs, faction_id, leader.location_city_id)
    ships = _ships_at(gs, faction_id, leader.location_city_id)
    is_port = bool(city and city.is_port)
    is_ruin = bool(city and city.is_ruin)
    magic_ok = leader.magic_skill >= 5 and leader.magic_power_current >= 5
    rel_ok = leader.religion_skill >= 5
    workers = _workers_total(gs, faction_id)
    bucket = turn % 12

    # Early-turn calibration: guarantee several families appear so a short
    # beta run already exercises more than the core strategy.
    if turn <= 6:
        lines.append(
            f"If {leader.name} has at least 1 gold, then have {leader.name} tax."
        )
        lines.append(f"Have {leader.name} work.")
        if magic_ok:
            lines.append(f"Have {leader.name} scry Kitesta.")
            lines.append(f"Have {leader.name} conjure a wand of teleport.")
        if rel_ok:
            lines.append(f"Have {leader.name} pray.")
        if rival_name and turn == 2:
            lines.append(f"Enemy {rival_name}.")
        if rival_name and turn == 5:
            lines.append(f"Ally {rival_name}.")
        if rival_name and turn == 6:
            lines.append(f"Neutral {rival_name}.")
        if is_port and turn == 3 and gold >= 30:
            dest = (
                "Albatross City"
                if leader.location_city_id != "albatross_city"
                else "Madegi Doy"
            )
            lines.append(f"Have {leader.name} definitely buy passage to {dest}.")
        if turn == 4:
            lines.append(f'Have {leader.name} say "Calibration ping." to everyone.')

    if workers >= 1 and not sub and gold >= 20 and (turn <= 8 or rng.random() < 0.35):
        gender = "male" if rng.random() < 0.5 else "female"
        who = f"Aide {faction_id[-1]} {turn:03d}"
        lines.append(f"Name {gender} worker {who}.")
        if rng.random() < 0.4:
            lines.append(f"Promote {who} to Captain.")

    if sub:
        if soldiers_here >= 5 and rng.random() < 0.25:
            lines.append(f"Have {leader.name} assign 5 soldiers to {sub.name}.")
        if gold >= 30 and rng.random() < 0.2:
            lines.append(f"Have {leader.name} transfer 10 gold to {sub.name}.")
            lines.append(f"Have {leader.name} take 5 gold from {sub.name}.")
        if leader.combat_skill >= 10 and rng.random() < 0.15:
            lines.append(f"Have {leader.name} teach combat to {sub.name}.")
        if rng.random() < 0.12:
            lines.append(f"Have {sub.name} join {leader.name}.")
        if enemies and rng.random() < 0.2:
            lines.append(f"Have {sub.name} support {leader.name}.")
        if rng.random() < 0.08 and bucket == 0:
            lines.append(f"Have {leader.name} unload {sub.name}.")
        if rng.random() < 0.05 and turn > 40:
            lines.append(f"Have {leader.name} unname {sub.name}.")

    if gold < 80 and rng.random() < 0.35:
        lines.append(f"Have {leader.name} work.")
    if workers >= 5 and leader.combat_skill >= 10 and rng.random() < 0.25:
        n = min(10, workers)
        lines.append(f"Have {leader.name} train {n} soldiers.")
    if (
        workers >= 5
        and getattr(leader, "sailing_skill", 0) >= 10
        and is_port
        and rng.random() < 0.2
    ):
        lines.append(f"Have {leader.name} train 5 sailors.")
    if soldiers_here >= 25 and rng.random() < 0.12:
        unit = f"Guard {faction_id[-1]}{turn % 97}"
        n = min(20, soldiers_here // 2)
        lines.append(f"Create {unit} using {n} soldiers.")
    if gold >= 50 and bucket in (1, 2) and rng.random() < 0.4:
        lines.append("Buy 10 wood.")
        if rng.random() < 0.5:
            lines.append(f"Have {leader.name} sell 5 wood.")
    if city and not is_ruin and bucket in (2, 3) and rng.random() < 0.35:
        lines.append(f"Have {leader.name} collect wood.")
        lines.append(f"Have {leader.name} gather stone.")
    if city and bucket == 3 and rng.random() < 0.3:
        lines.append(f"Have {leader.name} mine iron.")
    if bucket == 4 and rng.random() < 0.3:
        lines.append(f"Have {leader.name} build 5 weapons.")
    if (
        gold >= 100
        and leader.location_city_id in fac.controlled_city_ids
        and rng.random() < 0.25
    ):
        lines.append(f"Have {leader.name} fortify {city_name}.")
    if city and getattr(city, "fortification_level", 0) > 0 and rng.random() < 0.1:
        lines.append(f"Have {leader.name} unfortify {city_name}.")

    if is_port and gold >= 1000 and not ships and rng.random() < 0.15:
        lines.append(f"Buy 1 galley in {city_name}.")
    if is_port and ships and not moved and rng.random() < 0.35:
        dest = (
            "Albatross City"
            if leader.location_city_id != "albatross_city"
            else "Madegi Doy"
        )
        lines.append(f"Have {leader.name} sail to {dest}.")
    if is_port and not moved and gold >= 20 and bucket == 5 and rng.random() < 0.3:
        dest = (
            "Albatross City"
            if leader.location_city_id != "albatross_city"
            else "Madegi Doy"
        )
        lines.append(f"Have {leader.name} definitely buy passage to {dest}.")

    if magic_ok:
        if not moved and leader.magic_power_current >= 8 and rng.random() < 0.2:
            dests = _reachable_land(gs, leader.location_city_id)
            if dests:
                dest, _ = rng.choice(dests)
                lines.append(f"Have {leader.name} teleport himself to {dest.name}.")
            else:
                lines.append(f"Have {leader.name} fly to Kitesta.")
        if leader.magic_skill >= 10 and rng.random() < 0.2:
            lines.append(f"Have {leader.name} summon 1 demon.")
        if bucket == 6 and rng.random() < 0.35:
            lines.append(f"Have {leader.name} scry Kitesta.")
        if bucket == 6 and rng.random() < 0.25:
            lines.append(f"Have {leader.name} conjure a wand of teleport.")
        for item in _own_items(gs, faction_id)[:1]:
            iname = getattr(item, "name", "item")
            if not str(iname).startswith("*"):
                iname = f"*{iname}*"
            if rng.random() < 0.4:
                lines.append(f"Have {leader.name} charge {iname} to 10 power.")
            if rng.random() < 0.3:
                lines.append(f"Have {leader.name} absorb 5 from {iname}.")
        if leader.magic_skill < 40 and gold > 40 and rng.random() < 0.2:
            lines.append(f"Have {leader.name} study magic.")

    if rel_ok and enemies and rng.random() < 0.25:
        lines.append(f"Have {leader.name} curse {enemies[0].name}.")
    if rel_ok and bucket == 7 and rng.random() < 0.15:
        dead = [
            c
            for c in gs.characters.values()
            if c.faction_id == faction_id and c.is_dead
        ]
        if dead:
            lines.append(f"Have {leader.name} resurrect {dead[0].name}.")

    if enemies and magic_ok and rng.random() < 0.3:
        lines.append(f"Have {leader.name} probe {enemies[0].name}.")
    if is_ruin and rng.random() < 0.5:
        lines.append(f"Have {leader.name} search.")
        lines.append(f"Have {leader.name} explore.")
    if bucket == 8 and rng.random() < 0.35:
        lines.append(f"Have {leader.name} scan Kitesta.")
    if not enemies and rng.random() < 0.12:
        lines.append(f"Have {leader.name} lurk.")
    if sub and rng.random() < 0.1:
        lines.append(f"Have {leader.name} noncom {sub.name}.")

    if prisoners:
        p = prisoners[0]
        roll = rng.random()
        if roll < 0.35:
            lines.append(f"Have {leader.name} interrogate {p.name}.")
        elif roll < 0.55:
            lines.append(f"Have {leader.name} free {p.name}.")
        elif roll < 0.75:
            lines.append(f"Have {leader.name} enslave {p.name}.")
        else:
            lines.append(f"Have {leader.name} kill {p.name}.")

    if rival_name and bucket == 9:
        roll = rng.random()
        if style == "military" or roll < 0.5:
            lines.append(f"Enemy {rival_name}.")
        elif roll < 0.75:
            lines.append(f"Ally {rival_name}.")
        else:
            lines.append(f"Neutral {rival_name}.")

    if rival_name and rng.random() < 0.2:
        other = next(
            (
                c
                for c in gs.characters.values()
                if c.faction_id != faction_id
                and not c.is_dead
                and not getattr(gs.factions.get(c.faction_id), "is_npc", False)
            ),
            None,
        )
        if other:
            lines.append(
                f'Have {leader.name} say "Beta turn {turn} from {leader.name}." '
                f"to {other.name}."
            )
    secured = getattr(fac, "secured_city_ids", set()) or set()
    if leader.location_city_id in secured and rng.random() < 0.2:
        lines.append(
            f'Have {leader.name} post "Beta notice week {turn}" in {city_name}.'
        )
    if rng.random() < 0.15:
        lines.append(f"Have {leader.name} briefly report.")
    if turn == 3:
        lines.append(f'Address "{faction_id}@beta.test".')
    if turn == 4:
        lines.append(f"Password BetaTestPass{faction_id[-1]}9.")

    if gold < 100 and rng.random() < 0.15:
        lines.append(f"Have {leader.name} borrow 50 gold.")
    if gold > 200 and rng.random() < 0.1:
        lines.append(f"Have {leader.name} repay 10 gold.")
    if gold > 50 and rng.random() < 0.1:
        lines.append(f"Have {leader.name} pay.")
    if bucket == 10 and rng.random() < 0.5:
        lines.append(
            f"If {leader.name} has at least 10 gold, then have {leader.name} tax."
        )
    if sub and bucket == 11 and rng.random() < 0.2:
        lines.append(f"Have {sub.name} wait for 1 week.")
    if sub and turn % 20 == 7 and rng.random() < 0.4:
        lines.append(f"Have {sub.name} repeatedly tax 2 times.")
    if sub and turn % 25 == 0 and rng.random() < 0.5:
        lines.append(f"Have {sub.name} halt.")
