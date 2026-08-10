"""Turn phase handlers — extracted from engine without behavior change."""

from __future__ import annotations

import random
from typing import Dict, List

from spoils_engine.models import (
    GameState, Character, LocationPosition,
)
from spoils_engine.orders import (
    Order, MessageOrder, PostOrder, ReportOrder, AddressOrder, PasswordOrder,
)
from spoils_engine import config, fog, groups, order_queue, territory
from spoils_engine.turn_log import TurnLog


def report_pending_orders(game_state: GameState, turn_log: TurnLog):
    """Tell each player what is still sitting in their characters' queues."""
    for faction_id in game_state.factions:
        for line in order_queue.pending_summary(game_state, faction_id):
            turn_log.add("queue", faction_id, "pending", line)

def process_messages(orders_by_player: Dict[str, List[Order]],
                     game_state: GameState, turn_log: TurnLog):
    """
    SAY and TELL: deliver a message to other players.

    rules.md: "A character may give a message to any other character. If they
    are not in the same location, then inexpensive and readily available magic
    will be used to transmit the message" — so there is no distance rule and no
    cost. A message may also go to everyone at a town, or to every player.

    Delivery is a log event addressed to the recipient's faction, which is
    exactly how the reporting layer already routes per-player text.
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, MessageOrder) or order.warnings:
                continue
            sender = game_state.characters.get(order.actor_id)
            if not sender:
                continue

            body = order.message.strip()
            if len(body) > config.MESSAGE_MAX_LENGTH:
                body = body[:config.MESSAGE_MAX_LENGTH]
                turn_log.add("message", player_id, "message_truncated",
                            f"{sender.name}'s message was truncated to "
                            f"{config.MESSAGE_MAX_LENGTH} characters",
                            character_id=sender.id, success=False)

            audience = _message_audience(order, game_state)
            if not audience:
                turn_log.add("message", player_id, "message_failed",
                            f"{sender.name}'s message reached nobody",
                            character_id=sender.id, success=False)
                continue

            for faction_id, described in sorted(audience.items()):
                # The sender already gets a confirmation below; hearing their
                # own broadcast read back to them is just noise.
                if faction_id == player_id:
                    continue
                turn_log.add("message", faction_id, "message_received",
                            f"{sender.name} says to {described}: \"{body}\"",
                            character_id=sender.id)
            turn_log.add("message", player_id, "message_sent",
                        f"{sender.name} sent a message to "
                        f"{_message_target_name(order, game_state)}",
                        character_id=sender.id)


def _message_target_name(order: MessageOrder, game_state: GameState) -> str:
    """How to describe a message's addressee back to the sender."""
    if order.to_everyone:
        return "everyone"
    if order.recipient_city_id:
        return f"everyone in {order.recipient_city_name}"
    return ", ".join(order.recipient_names) or "nobody"


def _message_audience(order: MessageOrder,
                      game_state: GameState) -> Dict[str, str]:
    """
    Which factions hear this message, and how the delivery is addressed.

    A prisoner's own player still receives anything sent to them, per rules.md,
    which falls out of keying on the character's faction rather than on who is
    holding them.
    """
    audience: Dict[str, str] = {}

    if order.to_everyone:
        for faction_id in game_state.factions:
            audience[faction_id] = "everyone"
        return audience

    if order.recipient_city_id:
        for character in game_state.characters.values():
            if (character.location_city_id == order.recipient_city_id
                    and not character.is_dead):
                audience[character.faction_id] = (
                    f"everyone in {order.recipient_city_name}")

    for recipient_id in order.recipient_ids:
        recipient = game_state.characters.get(recipient_id)
        if not recipient or recipient.is_dead:
            continue
        audience[recipient.faction_id] = recipient.name

    return audience


def process_post(orders_by_player: Dict[str, List[Order]],
                 game_state: GameState, turn_log: TurnLog):
    """
    POST a notice at the gates of a town the faction has secured.

    rules.md: only in a town secured by one of your characters, and the poster
    must be there — though not necessarily the one who secured it. An empty
    message takes the notice down. Everyone inside or just outside the gates is
    told when a notice goes up or changes.
    """
    for player_id, orders in orders_by_player.items():
        faction = game_state.factions.get(player_id)
        for order in orders:
            if not isinstance(order, PostOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            if not actor or not faction:
                continue
            city = game_state.world_map.cities.get(actor.location_city_id)
            if not city:
                continue

            if not territory.is_valid_occupation(game_state, player_id, city.id):
                # POST needs occupation specifically, not sovereignty, so say
                # which one is missing -- a sovereign who has not SECUREd their
                # own town otherwise reads this as a bug.
                occupier = territory.occupying_faction_id(game_state, city.id)
                held = game_state.factions.get(occupier) if occupier else None
                detail = (
                    f"{held.name} has secured it" if held else
                    "your faction has not secured it — POST needs a SECURE, "
                    "and sovereignty alone is not enough"
                )
                turn_log.add("message", player_id, "post_failed",
                            f"{actor.name} cannot post at {city.name}: {detail}",
                            character_id=actor.id, location=city.id,
                            success=False)
                continue

            body = order.message.strip()
            if len(body) > config.POST_MAX_LENGTH:
                turn_log.add("message", player_id, "post_failed",
                            f"{actor.name}'s notice is longer than "
                            f"{config.POST_MAX_LENGTH} characters and was "
                            f"rejected",
                            character_id=actor.id, location=city.id,
                            success=False)
                continue

            if not body:
                game_state.posted_messages.pop(city.id, None)
                turn_log.add("message", player_id, "post_removed",
                            f"{actor.name} took down the notice at {city.name}",
                            character_id=actor.id, location=city.id)
                continue

            game_state.posted_messages[city.id] = body
            turn_log.add("message", player_id, "post",
                        f"{actor.name} posted a notice at {city.name}: \"{body}\"",
                        character_id=actor.id, location=city.id)

            # Everyone at the gates sees a notice go up.
            for faction_id in _factions_at_gates(city.id, game_state):
                if faction_id == player_id:
                    continue
                turn_log.add("message", faction_id, "post_seen",
                            f"A notice at the gates of {city.name} reads: "
                            f"\"{body}\"",
                            location=city.id)


def _factions_at_gates(city_id: str, game_state: GameState) -> set:
    """
    Factions with somebody inside or just outside a town.

    Those hiding *near* the town are not at the gates and do not see notices.
    """
    return {
        character.faction_id for character in game_state.characters.values()
        if character.location_city_id == city_id and not character.is_dead
        and character.location_position != LocationPosition.NEAR
    }


def process_report(orders_by_player: Dict[str, List[Order]],
                   game_state: GameState, turn_log: TurnLog,
                   rng: random.Random):
    """
    REPORT and QUERY: ask a character what they can see.

    rules.md: the report covers the reporter's own status plus what they can
    learn of the location. `briefly` drops the skill lists and the other people
    at the location. QUERY differs only in reaching a busy subordinate, which
    the engine gets for free: an order that has been released for this turn
    executes regardless of what else its actor is doing.
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, ReportOrder) or order.warnings:
                continue
            for subject_id in order.subject_ids:
                subject = game_state.characters.get(subject_id)
                if not subject or subject.is_dead:
                    turn_log.add("report", player_id, "report_failed",
                                "No report: that character is gone",
                                success=False)
                    continue
                for line in _compose_report(subject, order.brief, game_state, rng):
                    turn_log.add("report", player_id, "report", line,
                                character_id=subject.id,
                                location=subject.location_city_id)


def _compose_report(subject: Character, brief: bool, game_state: GameState,
                    rng: random.Random) -> List[str]:
    """
    Build one character's report.

    The full form follows the shape of the example in `rules.md`: the reporter
    and their group, then what else is notable at the location. The brief form
    keeps the first line and drops the skills and the neighbours.
    """
    city = game_state.world_map.cities.get(subject.location_city_id)
    city_name = city.name if city else "an unknown place"

    skills = ""
    if not brief:
        parts = [f"{label} {value}" for label, value in (
            ("combat", subject.combat_skill), ("magic", subject.magic_skill),
            ("religion", subject.religion_skill),
            ("trading", subject.trading_skill)) if value]
        skills = f" ({', '.join(parts)})" if parts else ""

    soldiers = groups.group_soldier_count(subject, game_state)
    followers = groups.group_members(subject.id, game_state)

    # The rules' example names the people in the group before counting the
    # unnamed units: "Captain John May (combat 20, magic 25), Adept Carolyn
    # Bond, 39 soldiers, 307 gold, currently awaiting orders in Umadosh."
    tail = [c.name for c in sorted(followers, key=lambda c: c.name)]
    if soldiers:
        tail.append(f"{soldiers} soldiers")
    tail.append(f"{subject.gold:,.0f} gold")

    head = (f"{subject.name}{skills}, {', '.join(tail)}, "
            f"currently {subject.location_position.value} {city_name}")
    lines = [("Brief report: " if brief else "Report: ") + head]

    if brief:
        return lines

    posted = game_state.posted_messages.get(subject.location_city_id)
    if posted and subject.location_position != LocationPosition.NEAR:
        lines.append(f"  A notice at the gates of {city_name} reads: \"{posted}\"")

    # Who else the reporter can make out, under the ordinary fog rules.
    if city:
        seen = sorted(
            (other for other in game_state.characters.values()
             if other.id != subject.id and not other.is_dead
             and other.location_city_id == subject.location_city_id
             and other.faction_id != subject.faction_id
             and fog.detects(subject, other, city, game_state, rng)),
            key=lambda c: c.name,
        )
        if seen:
            lines.append(f"  Other notable people in {city_name}: "
                         + ", ".join(c.name for c in seen))
    return lines


def process_address_and_password(orders_by_player: Dict[str, List[Order]],
                                 game_state: GameState, turn_log: TurnLog,
                                 rng: random.Random):
    """
    ADDRESS and PASSWORD: change a player's contact details.

    rules.md treats both as taking effect as soon as they are parsed rather
    than as things a character does, so neither needs an actor or a location.
    A password under eight characters is replaced by a generated one, and one
    over sixty-four is truncated.
    """
    for player_id, orders in orders_by_player.items():
        faction = game_state.factions.get(player_id)
        if not faction:
            continue
        for order in orders:
            if isinstance(order, AddressOrder) and not order.warnings:
                faction.email = order.address.strip()
                turn_log.add("message", player_id, "address",
                            f"Reports will now be sent to {faction.email}")

            elif isinstance(order, PasswordOrder) and not order.warnings:
                password = order.password.strip()
                if len(password) < config.PASSWORD_MIN_LENGTH:
                    password = "".join(
                        rng.choice("abcdefghijkmnpqrstuvwxyz23456789")
                        for _ in range(config.PASSWORD_MIN_LENGTH + 4))
                    faction.password = password
                    turn_log.add("message", player_id, "password",
                                f"That password was shorter than "
                                f"{config.PASSWORD_MIN_LENGTH} characters, so "
                                f"one was generated for you: {password}")
                    continue
                faction.password = password[:config.PASSWORD_MAX_LENGTH]
                turn_log.add("message", player_id, "password",
                            "Your password has been changed")


def expire_postings(game_state: GameState, turn_log: TurnLog):
    """
    Take down notices at towns nobody secures any more.

    rules.md: "A posting will remain in effect until you no longer secure the
    location." Ownership can change through combat, so this is checked at the
    end of every turn rather than only when a POST is issued.
    """
    secured = {
        city_id
        for faction in game_state.factions.values()
        for city_id in faction.secured_city_ids
        if territory.is_valid_occupation(game_state, faction.id, city_id)
    }

    for city_id in list(game_state.posted_messages):
        if city_id in secured:
            continue
        del game_state.posted_messages[city_id]
        city = game_state.world_map.cities.get(city_id)
        if city:
            turn_log.add("message", "", "post_lapsed",
                        f"The notice at {city.name} has come down: nobody "
                        f"secures the town any more", location=city_id)

