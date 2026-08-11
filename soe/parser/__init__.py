"""
Natural-language order parser (rule-based).

Parses English-like commands into structured Order objects.
This package is a split of the former monolithic parser module; the public
API is re-exported here so ``from soe.parser import ...`` still works.
"""

from soe.parser.text import (
    normalize_text,
    extract_sentences,
    protect_quotes,
    restore_quotes,
    restore_order_quotes,
    strip_wand,
    strip_repeatedly,
    parse_duration_days, parse_duration_hours,
)
from soe.parser.resolve import (
    ResolvedEntity,
    resolve_character,
    resolve_city,
    get_player_leader,
    OrderParserBase,
)
from soe.parser.dispatch import (
    ORDER_KEYWORDS,
    HAVE_PREFIX,
    split_clauses,
    parse_orders,
)
from soe.parser.control import (
    parse_if_order,
    parse_if_condition,
    parse_await_order,
    parse_repeat_order,
    parse_halt_order,
)

# Re-export verb parsers used by tests or tooling
from soe.parser.verbs_movement import (
    parse_move_order, parse_sail_order, parse_fly_order, parse_teleport_order,
    parse_passage_order,
)
from soe.parser.verbs_combat import (
    parse_attack_order, parse_capture_order, parse_free_order,
    parse_kill_order, parse_enslave_order, parse_interrogate_order,
    parse_noncom_order, parse_lurk_order,
)
from soe.parser.verbs_economy import (
    parse_recruit_order, parse_buy_ship_order, parse_tax_order, parse_trade_order,
    parse_collect_order, parse_build_order, parse_mine_order,
    parse_work_order, parse_train_order, parse_invest_order,
)
from soe.parser.verbs_magic import (
    parse_heal_order, parse_pray_order, parse_bless_order, parse_curse_order,
    parse_resurrect_order, parse_summon_order, parse_study_order, parse_teach_order,
    parse_scry_order, parse_probe_order, parse_search_order, parse_scan_order,
    parse_conjure_order, parse_charge_order, parse_absorb_order,
)
from soe.parser.verbs_social import (
    parse_secure_order, parse_fortify_order, parse_unfortify_order,
    parse_ally_order, parse_enemy_order, parse_neutral_order,
    parse_preach_order, parse_offer_order,
    parse_join_order, parse_support_order,
    parse_message_order, parse_post_order, parse_report_order,
    parse_address_order, parse_password_order,
)
from soe.parser.verbs_units import (
    parse_assign_order, parse_name_order, parse_promote_order,
    parse_get_order, parse_transfer_order, parse_unload_order,
    parse_pay_order, parse_borrow_order, parse_repay_order,
    parse_unname_order, parse_create_order, parse_disband_order,
)

__all__ = [
    "normalize_text", "extract_sentences", "protect_quotes", "restore_quotes",
    "restore_order_quotes", "strip_wand", "strip_repeatedly", "parse_duration_days", "parse_duration_hours",
    "ResolvedEntity", "resolve_character", "resolve_city", "get_player_leader",
    "OrderParserBase",
    "ORDER_KEYWORDS", "HAVE_PREFIX", "split_clauses", "parse_orders",
    "parse_if_order", "parse_if_condition", "parse_await_order",
    "parse_repeat_order", "parse_halt_order",
    "parse_move_order", "parse_sail_order", "parse_fly_order", "parse_teleport_order",
    "parse_passage_order",
    "parse_attack_order", "parse_capture_order", "parse_free_order",
    "parse_kill_order", "parse_enslave_order", "parse_interrogate_order",
    "parse_noncom_order", "parse_lurk_order",
    "parse_recruit_order", "parse_buy_ship_order", "parse_tax_order", "parse_trade_order",
    "parse_collect_order", "parse_build_order", "parse_mine_order",
    "parse_work_order", "parse_train_order", "parse_invest_order",
    "parse_heal_order", "parse_pray_order", "parse_bless_order", "parse_curse_order",
    "parse_resurrect_order", "parse_summon_order", "parse_study_order", "parse_teach_order",
    "parse_scry_order", "parse_probe_order", "parse_search_order", "parse_scan_order",
    "parse_conjure_order", "parse_charge_order", "parse_absorb_order",
    "parse_secure_order", "parse_fortify_order", "parse_unfortify_order",
    "parse_ally_order", "parse_enemy_order", "parse_neutral_order",
    "parse_preach_order", "parse_offer_order",
    "parse_join_order", "parse_support_order",
    "parse_message_order", "parse_post_order", "parse_report_order",
    "parse_address_order", "parse_password_order",
    "parse_assign_order", "parse_name_order", "parse_promote_order",
    "parse_get_order", "parse_transfer_order", "parse_unload_order",
    "parse_pay_order", "parse_borrow_order", "parse_repay_order",
    "parse_unname_order", "parse_create_order", "parse_disband_order",
]
