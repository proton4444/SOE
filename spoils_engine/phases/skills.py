"""Turn phase handlers — extracted from engine without behavior change."""

from __future__ import annotations

from typing import Dict, List

from spoils_engine.models import (
    GameState, debit_gold,
)
from spoils_engine.orders import (
    Order, StudyOrder, TeachOrder,
)
from spoils_engine.turn_log import TurnLog


def process_study(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog, rng):
    """Process STUDY orders for character skill training."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, StudyOrder):
                continue

            if order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            if not actor or actor.is_dead:
                continue

            faction = game_state.factions.get(player_id)
            if not faction:
                continue

            # Cost: 1 gold per week
            cost = order.duration_weeks
            if not debit_gold(actor, faction, cost):
                turn_log.add("study", player_id, "study_failed",
                            f"{actor.name}: insufficient gold to study (need {cost}g)",
                            character_id=actor.id, success=False)
                continue

            # Get current skill level
            if order.skill_name == "combat":
                current_skill = actor.combat_skill
            elif order.skill_name == "magic":
                current_skill = actor.magic_skill
            elif order.skill_name == "religion":
                current_skill = actor.religion_skill
            elif order.skill_name == "sailing":
                current_skill = actor.sailing_skill
            else:
                continue

            # Study for each week
            for week in range(order.duration_weeks):
                if current_skill >= 100:
                    break

                # Gain 1-5 points per week (simplified - no partial tracking in alpha)
                gain = rng.randint(1, 5)
                current_skill = min(100, current_skill + gain)

            # Update skill
            if order.skill_name == "combat":
                actor.combat_skill = current_skill
            elif order.skill_name == "magic":
                actor.magic_skill = current_skill
            elif order.skill_name == "religion":
                actor.religion_skill = current_skill
            elif order.skill_name == "sailing":
                actor.sailing_skill = current_skill

            turn_log.add("study", player_id, "study_success",
                        f"{actor.name}: studied {order.skill_name} for {order.duration_weeks} weeks (now level {current_skill})",
                        character_id=actor.id)


def process_teach(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog, rng):
    """Process TEACH orders for character skill training."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, TeachOrder):
                continue

            if order.warnings:
                continue

            teacher = game_state.characters.get(order.teacher_id)
            student = game_state.characters.get(order.student_id)

            if not teacher or teacher.is_dead or not student or student.is_dead:
                continue

            # Check same location
            if teacher.location_city_id != student.location_city_id:
                turn_log.add("teach", player_id, "teach_failed",
                            f"{teacher.name}: {student.name} is not at the same location",
                            character_id=teacher.id, success=False)
                continue

            # Get teacher's skill level
            if order.skill_name == "combat":
                teacher_skill = teacher.combat_skill
                student_skill = student.combat_skill
            elif order.skill_name == "magic":
                teacher_skill = teacher.magic_skill
                student_skill = student.magic_skill
            elif order.skill_name == "religion":
                teacher_skill = teacher.religion_skill
                student_skill = student.religion_skill
            elif order.skill_name == "sailing":
                teacher_skill = teacher.sailing_skill
                student_skill = student.sailing_skill
            else:
                continue

            # Teacher must have higher skill
            if teacher_skill <= student_skill:
                turn_log.add("teach", player_id, "teach_failed",
                            f"{teacher.name}: cannot teach {student.name} {order.skill_name} (teacher skill {teacher_skill} <= student skill {student_skill})",
                            character_id=teacher.id, success=False)
                continue

            # Teach for each week (no cost, better gains than studying)
            for week in range(order.duration_weeks):
                if student_skill >= 100 or student_skill >= teacher_skill:
                    break

                # Gain 2-7 points per week with teacher (better than self-study)
                gain = rng.randint(2, 7)
                student_skill = min(100, min(teacher_skill, student_skill + gain))

            # Update skill
            if order.skill_name == "combat":
                student.combat_skill = student_skill
            elif order.skill_name == "magic":
                student.magic_skill = student_skill
            elif order.skill_name == "religion":
                student.religion_skill = student_skill
            elif order.skill_name == "sailing":
                student.sailing_skill = student_skill

            turn_log.add("teach", player_id, "teach_success",
                        f"{teacher.name}: taught {student.name} {order.skill_name} for {order.duration_weeks} weeks (now level {student_skill})",
                        character_id=teacher.id)

