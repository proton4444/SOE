"""
The persistent per-character order queue.

the design describes an asynchronous game: orders are placed on a queue and
execute once enough game time has passed, so a player can send several days of
orders at once and cancel what has not started yet. The alpha engine runs fixed
weekly turns, so the queue here is turn-granular. It makes **one pass per turn**:
every entry it can reach is released into that turn's phases, and it stops at the
first entry that is still waiting.

That keeps two things true at once. An order submitted with nothing in front of
it still resolves in the turn it was given -- which is exactly what the design
says happens when the Gamemaster processes on a fixed schedule -- while AWAIT and
REPEAT genuinely carry work into later turns instead of being silently dropped.

Only four things ever hold work back:

* AWAIT -- a timed wait, or a wait for another character to arrive.
* REPEAT -- the loop body runs once per turn; the marker re-arms for the next.
* STOP   -- consumed in sequence, and discards everything behind it.
* HALT   -- applied before intake, discarding the backlog at once.
"""

import copy
from typing import Dict, List, Optional

from soe import config
from soe.models import Character, GameState
from soe.orders import (
    AwaitOrder,
    HaltOrder,
    Order,
    QueueEntry,
    RepeatOrder,
    StopOrder,
    actor_id_of,
)

# Defensive bound. Every entry is consumed at most once per pass and both loop
# markers and unmet waits break out, so this can only trip if a future edit
# reintroduces a cycle -- in which case a truncated turn beats a hung one.
_MAX_DRAIN_PER_ACTOR = 200


# ============================================================================
# ENTRY POINT
# ============================================================================

def process_order_queue(orders_by_player: Dict[str, List[Order]],
                        game_state: GameState,
                        turn_log) -> Dict[str, List[Order]]:
    """
    Run this turn's queue pass and return the orders the phases should execute.

    HALT is applied first so it clears the backlog a player is trying to
    abandon, then the new submission is appended, then the queue drains.

    The returned orders are *not* validated -- `engine.validate_orders` runs on
    them afterwards, so an order that sat in the queue for three turns is
    checked against the world as it is when the order finally executes, not as
    it was when the player wrote it.
    """
    _apply_halts(orders_by_player, game_state, turn_log)
    released = _enqueue(orders_by_player, game_state, turn_log)
    _drain(game_state, turn_log, released)
    return released


def resume_order_queue(game_state: GameState, turn_log) -> Dict[str, List[Order]]:
    """Wake queues after the game clock advances inside the current turn."""
    released: Dict[str, List[Order]] = {}
    _drain(game_state, turn_log, released)
    return released


def next_wake_hour(game_state: GameState, end_hour: int) -> Optional[int]:
    """Earliest queued wait check that falls inside this processing window."""
    wakeups = []
    now = current_hour(game_state)
    for queue in game_state.order_queues.values():
        if not queue or not isinstance(queue[0].order, AwaitOrder):
            continue
        entry = queue[0]
        candidate = entry.check_hour if entry.order.target_id else entry.release_hour
        if candidate > now and candidate < end_hour:
            wakeups.append(candidate)
    return min(wakeups) if wakeups else None


def current_hour(game_state: GameState) -> int:
    """Absolute game hour, including migration for directly-built old states."""
    return max(game_state.game_time_hours,
               game_state.turn_number * config.HOURS_PER_TURN)


# ============================================================================
# HELPERS
# ============================================================================

def _release(released: Dict[str, List[Order]], order: Order) -> None:
    """Hand an order to this turn's phases."""
    released.setdefault(order.player_id, []).append(order)


def _owned_actor(order: Order, player_id: str,
                 game_state: GameState) -> Optional[Character]:
    """
    The order's actor, but only if it is a living character of this player.

    Queue membership has to be ownership-checked here rather than left to
    `validate_orders`, because the queue is keyed by character: without this a
    player could append to (or HALT) somebody else's queue.
    """
    actor = game_state.characters.get(actor_id_of(order))
    if actor and actor.faction_id == player_id and not actor.is_dead:
        return actor
    return None


def _copy_block(block: List[QueueEntry]) -> List[QueueEntry]:
    """
    A fresh copy of a repeat body.

    Each pass gets its own Order objects: phases append warnings to the orders
    they run, and those must not accumulate on the pristine loop body.
    """
    return copy.deepcopy(block)


def turns_for_days(days: int) -> int:
    """
    Whole turns a wait of `days` game days occupies.

    Rounded up: a turn is the smallest unit the engine can hold work for, so a
    wait shorter than one turn still costs the rest of the current turn. This is
    the alpha's coarsest divergence from the rules' hour-level clock.
    """
    if days <= 0:
        return 0
    return max(1, (days + config.DAYS_PER_TURN - 1) // config.DAYS_PER_TURN)


# ============================================================================
# HALT
# ============================================================================

def _apply_halts(orders_by_player: Dict[str, List[Order]],
                 game_state: GameState, turn_log) -> None:
    """Clear the queues of every character ordered to halt."""
    for player_id, submitted in orders_by_player.items():
        for order in submitted:
            if not isinstance(order, HaltOrder) or order.warnings:
                continue

            actor = _owned_actor(order, player_id, game_state)
            if not actor:
                order.warnings.append("Cannot halt that character")
                continue

            queue = game_state.order_queues.get(actor.id) or []
            running_wait = _running_wait(queue) if not order.immediate else None

            dropped = len(queue) - (1 if running_wait else 0)
            game_state.order_queues[actor.id] = [running_wait] if running_wait else []

            if running_wait:
                turn_log.add("queue", player_id, "halt",
                             f"{actor.name} halted: {dropped} queued order(s) "
                             f"cancelled, but the wait already under way stands",
                             character_id=actor.id)
            else:
                turn_log.add("queue", player_id, "halt",
                             f"{actor.name} halted: {dropped} queued order(s) cancelled",
                             character_id=actor.id)


def _running_wait(queue: List[QueueEntry]) -> Optional[QueueEntry]:
    """The head entry if it is a wait that has already started, else None."""
    if (queue and isinstance(queue[0].order, AwaitOrder)
            and (queue[0].release_hour >= 0 or queue[0].release_turn >= 0)):
        return queue[0]
    return None


# ============================================================================
# INTAKE
# ============================================================================

def _enqueue(orders_by_player: Dict[str, List[Order]],
             game_state: GameState, turn_log) -> Dict[str, List[Order]]:
    """
    Append this turn's submission to the per-character queues.

    Returns the orders that bypassed the queue entirely and must be reported
    now: orders that name no character, and orders that already failed parsing.
    A dud is better rejected in the turn it was written than three turns later.
    """
    released: Dict[str, List[Order]] = {}

    for player_id, submitted in orders_by_player.items():
        by_actor: Dict[str, List[Order]] = {}

        for order in submitted:
            if isinstance(order, HaltOrder):
                continue  # already applied

            if order.warnings or not actor_id_of(order):
                _release(released, order)
                continue

            actor = _owned_actor(order, player_id, game_state)
            if not actor:
                # Let validate_orders produce the specific complaint.
                _release(released, order)
                continue

            by_actor.setdefault(actor.id, []).append(order)

        for actor_id, actor_orders in by_actor.items():
            queue = game_state.order_queues.setdefault(actor_id, [])
            _enqueue_for_actor(actor_id, actor_orders, queue, player_id,
                               game_state, turn_log)

    return released


def _enqueue_for_actor(actor_id: str, actor_orders: List[Order],
                       queue: List[QueueEntry], player_id: str,
                       game_state: GameState, turn_log) -> None:
    """
    Queue one character's orders, folding a REPEAT into a loop.

    Everything after a REPEAT is its body, per the design, where `repeatedly`
    precedes the commands it governs. A second REPEAT for the same character is
    dropped and its orders stay in sequence inside the outer loop, which is what
    the rules say happens to a nested loop.
    """
    actor = game_state.characters.get(actor_id)
    name = actor.name if actor else actor_id

    for index, order in enumerate(actor_orders):
        if not isinstance(order, RepeatOrder):
            queue.append(QueueEntry(order=order))
            continue

        body_orders = []
        for follower in actor_orders[index + 1:]:
            if isinstance(follower, RepeatOrder):
                follower.warnings.append(
                    "Nested repeat ignored; its orders run in sequence "
                    "inside the outer loop"
                )
                continue
            body_orders.append(follower)

        if not body_orders:
            order.warnings.append("Nothing to repeat - no orders follow it")
            turn_log.add("queue", player_id, "repeat_empty",
                         f"{name} was told to repeat, but no orders follow it",
                         character_id=actor_id, success=False)
            return

        block = [QueueEntry(order=body) for body in body_orders]
        queue.extend(_copy_block(block))
        queue.append(QueueEntry(
            order=order,
            repeat_remaining=(order.times - 1) if order.times > 0 else -1,
            block=block,
        ))

        passes = f"{order.times} time(s)" if order.times > 0 else "until halted"
        turn_log.add("queue", player_id, "repeat_scheduled",
                     f"{name} will repeat {len(block)} order(s) {passes}",
                     character_id=actor_id)
        return  # everything after the repeat is inside the loop


# ============================================================================
# DRAIN
# ============================================================================

def _drain(game_state: GameState, turn_log,
           released: Dict[str, List[Order]]) -> None:
    """Release one pass of every character's queue into this turn."""
    for actor_id in list(game_state.order_queues):
        queue = game_state.order_queues[actor_id]
        if not queue:
            del game_state.order_queues[actor_id]
            continue

        actor = game_state.characters.get(actor_id)
        player_id = queue[0].order.player_id if queue[0].order else ""

        if actor is None or actor.is_dead:
            turn_log.add("queue", player_id, "queue_lost",
                         f"{len(queue)} queued order(s) died with their character",
                         character_id=actor_id, success=False)
            del game_state.order_queues[actor_id]
            continue

        # A prisoner's queue is drained rather than held: he cannot act, so
        # `validate_orders` rejects each order as it surfaces and the player is
        # told, which beats silently banking orders he was never able to give.
        _drain_actor(actor, queue, game_state, turn_log, released)

        if not queue:
            del game_state.order_queues[actor_id]


def _drain_actor(actor: Character, queue: List[QueueEntry],
                 game_state: GameState, turn_log,
                 released: Dict[str, List[Order]]) -> None:
    """Pop entries for one character until the queue blocks or empties."""
    for _ in range(_MAX_DRAIN_PER_ACTOR):
        if not queue:
            return

        entry = queue[0]
        order = entry.order
        player_id = order.player_id if order else actor.faction_id

        if order is None:
            queue.pop(0)
            continue

        if isinstance(order, AwaitOrder):
            if not _resolve_wait(actor, entry, order, game_state, turn_log):
                return
            queue.pop(0)
            continue

        if isinstance(order, StopOrder):
            queue.pop(0)
            dropped = len(queue)
            queue.clear()
            turn_log.add("queue", player_id, "stop",
                         f"{actor.name} stopped as planned: "
                         f"{dropped} queued order(s) cancelled",
                         character_id=actor.id)
            return

        if isinstance(order, RepeatOrder):
            queue.pop(0)
            if entry.repeat_remaining == 0:
                turn_log.add("queue", player_id, "repeat_finished",
                             f"{actor.name} finished the repeat loop",
                             character_id=actor.id)
                continue

            remaining = entry.repeat_remaining - 1 if entry.repeat_remaining > 0 else -1
            # Re-armed at the head, not the tail: while a loop is running the
            # character never reaches orders queued after it.
            queue[0:0] = _copy_block(entry.block) + [QueueEntry(
                order=order, repeat_remaining=remaining, block=entry.block,
            )]
            left = "until halted" if remaining < 0 else f"{remaining + 1} pass(es) left"
            turn_log.add("queue", player_id, "repeat_rearmed",
                         f"{actor.name} will repeat next turn ({left})",
                         character_id=actor.id)
            return  # the next pass belongs to the next turn

        queue.pop(0)
        _release(released, order)


def _resolve_wait(actor: Character, entry: QueueEntry, order: AwaitOrder,
                  game_state: GameState, turn_log) -> bool:
    """
    Advance one AWAIT. True when the wait is over and the queue may continue.

    A wait for a character ends the moment that character shares the actor's
    city, and `duration_days` then acts as the deadline it gives up on.
    """
    player_id = order.player_id
    target = game_state.characters.get(order.target_id) if order.target_id else None

    now = current_hour(game_state)
    if entry.release_hour < 0:
        # Migrate an in-flight turn-granular wait, otherwise start a new
        # hour-granular deadline from the current clock position.
        if entry.release_turn >= 0:
            entry.release_hour = entry.release_turn * config.HOURS_PER_TURN
        else:
            duration = getattr(order, "duration_hours", 0)
            if duration <= 0:
                duration = order.duration_days * config.HOURS_PER_DAY
            entry.release_hour = now + duration
            entry.release_turn = (
                entry.release_hour + config.HOURS_PER_TURN - 1
            ) // config.HOURS_PER_TURN
        entry.check_hour = min(entry.release_hour, now + 4)
        if order.target_id and not target:
            turn_log.add("queue", player_id, "await_failed",
                         f"{actor.name} was told to wait for someone who does not exist",
                         character_id=actor.id, success=False)
            return True
        subject = f"for {target.name}" if target else f"{order.duration_days} day(s)"
        turn_log.add("queue", player_id, "await_started",
                     f"{actor.name} waits {subject}", character_id=actor.id)

    if target is not None:
        if target.location_city_id == actor.location_city_id and not target.is_dead:
            turn_log.add("queue", player_id, "await_met",
                         f"{target.name} reached {actor.name}; the wait is over",
                         character_id=actor.id)
            return True
        if now >= entry.release_hour:
            turn_log.add("queue", player_id, "await_expired",
                         f"{actor.name} gave up waiting for {target.name}",
                         character_id=actor.id, success=False)
            return True
        entry.check_hour = min(entry.release_hour, now + 4)
        turn_log.add("queue", player_id, "await_waiting",
                     f"{actor.name} is still waiting for {target.name}",
                     character_id=actor.id)
        return False

    if now >= entry.release_hour:
        turn_log.add("queue", player_id, "await_finished",
                     f"{actor.name} has finished waiting", character_id=actor.id)
        return True

    hours_left = entry.release_hour - now
    turn_log.add("queue", player_id, "await_waiting",
                 f"{actor.name} is waiting ({hours_left} more hour(s))",
                 character_id=actor.id)
    return False


# ============================================================================
# REPORTING SUPPORT
# ============================================================================

def pending_summary(game_state: GameState, player_id: str) -> List[str]:
    """One line per character with orders still queued, for the turn report."""
    lines = []
    for actor_id, queue in game_state.order_queues.items():
        actor = game_state.characters.get(actor_id)
        if not actor or actor.faction_id != player_id or not queue:
            continue
        verbs = [e.order.order_type() for e in queue if e.order]
        lines.append(f"{actor.name}: {len(queue)} pending ({', '.join(verbs)})")
    return lines
