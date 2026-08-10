"""
Tests for the communication verbs.

SAY/TELL carry a message to another player, POST nails a notice to the gates of
a secured town, REPORT/QUERY ask a character what they can see, and
ADDRESS/PASSWORD change the player's own details. The load-bearing piece is
that a quoted message survives the parser at all: order text is lowercased,
stripped of commas and split on periods, none of which a message may suffer.
"""

from pathlib import Path

import pytest

from spoils_engine import config, engine, models, parser, reporting, storage
from spoils_engine.models import LocationPosition, PopulationBand, UnitType


@pytest.fixture
def world():
    """Two players sharing Madegi Doy, which the Empire has secured."""
    gs = models.GameState()
    gs.turn_number = 1
    gs.world_map.cities["c1"] = models.City(
        id="c1", name="Madegi Doy", population_band=PopulationBand.MEDIUM)
    gs.world_map.cities["c2"] = models.City(
        id="c2", name="Kitesta", population_band=PopulationBand.SMALL)
    gs.world_map.roads["r"] = models.Road(
        id="r", from_city_id="c1", to_city_id="c2",
        quality=models.RoadQuality.GOOD)

    gs.factions["p1"] = models.Faction(
        id="p1", name="Empire", controlled_city_ids={"c1"},
        secured_city_ids={"c1"})
    gs.factions["p2"] = models.Faction(id="p2", name="Horde")

    gs.characters["l"] = models.Character(
        id="l", name="Billy Jones", faction_id="p1", location_city_id="c1",
        is_leader=True, gold=300, combat_skill=20, magic_skill=25)
    gs.characters["j"] = models.Character(
        id="j", name="Joe Flint", faction_id="p1", location_city_id="c1",
        gold=50)
    gs.characters["b"] = models.Character(
        id="b", name="Bill Johnson", faction_id="p1", location_city_id="c2",
        gold=20)
    gs.characters["e"] = models.Character(
        id="e", name="John May", faction_id="p2", location_city_id="c1",
        is_leader=True, gold=90)
    gs.unit_stacks["garrison"] = models.UnitStack(
        id="garrison", faction_id="p1", location_city_id="c1",
        unit_type=UnitType.SOLDIER, count=1, owner_character_id="j")
    return gs


def run(gs, orders_by_player, seed=42):
    parsed = {pid: parser.parse_orders(text, gs, pid)
              for pid, text in orders_by_player.items()}
    return engine.run_turn(gs, parsed, seed=seed)


def messages(log, player):
    return [e.description for e in log.events if e.player_id == player]


def only(gs, text, player="p1", seed=42):
    """Parse one player's text and return the single order it produced."""
    orders = parser.parse_orders(text, gs, player)
    assert len(orders) == 1, [o.order_type() for o in orders]
    return orders[0]


# ---------------------------------------------------------------------------
# Quoted text survives the parser
# ---------------------------------------------------------------------------

def test_a_message_keeps_its_case(world):
    order = only(world, 'Tell John May "Fear And Obey Him!"')
    assert order.message == "Fear And Obey Him!"


def test_a_message_keeps_its_periods_and_commas(world):
    order = only(
        world,
        'Have Joe Flint post "Welcome to Madegi Doy. Recruiting is '
        'forbidden, by order of Major Calensa."')
    assert order.message == (
        "Welcome to Madegi Doy. Recruiting is forbidden, "
        "by order of Major Calensa.")


def test_a_period_in_a_message_does_not_split_the_order(world):
    # Note the period *after* the closing quote: that is what ends the
    # sentence, exactly as rules.md writes its own POST example.
    orders = parser.parse_orders(
        'Have Joe Flint post "One. Two. Three.". Report.', world, "p1")
    kinds = sorted(o.order_type() for o in orders)
    assert kinds == ["POST", "REPORT"]
    post = next(o for o in orders if o.order_type() == "POST")
    assert post.message == "One. Two. Three."


def test_pronouns_inside_a_message_are_left_alone(world):
    """`me` in a message is the sender's word, not a reference to resolve."""
    order = only(world, 'Have Joe Flint say "Give me the gold." to John May.')
    assert order.message == "Give me the gold."


def test_text_outside_the_quotes_still_resolves_pronouns(world):
    order = only(world, 'Tell John May "Here it is." Then give him 10 gold.'
                 .replace(" Then give him 10 gold.", ""))
    assert order.recipient_names == ["John May"]


# ---------------------------------------------------------------------------
# SAY and TELL
# ---------------------------------------------------------------------------

def test_say_puts_the_recipient_after_the_message(world):
    order = only(world, 'Have Joe Flint say "Not on your life!" to John May.')
    assert order.actor_id == "j"
    assert order.message == "Not on your life!"
    assert order.recipient_names == ["John May"]


def test_tell_puts_the_recipient_first(world):
    order = only(world, 'Tell John May "Not on your life!"')
    assert order.recipient_names == ["John May"]
    assert order.message == "Not on your life!"


def test_a_message_reaches_the_other_player(world):
    world, log = run(world, {
        "p1": 'Have Joe Flint say "Here is the gold." to John May.'})
    assert any('Joe Flint says to John May: "Here is the gold."' in m
               for m in messages(log, "p2"))
    assert any("sent a message to John May" in m for m in messages(log, "p1"))


def test_everyone_reaches_every_player(world):
    world, log = run(world, {"p2": 'Tell everyone "I rule the world!"'})
    assert any('"I rule the world!"' in m for m in messages(log, "p1"))


def test_a_broadcast_is_not_read_back_to_its_sender(world):
    world, log = run(world, {"p2": 'Tell everyone "I rule the world!"'})
    received = [m for m in messages(log, "p2") if "says to everyone" in m]
    assert not received
    assert any("sent a message to everyone" in m for m in messages(log, "p2"))


def test_a_town_name_broadcasts_to_everyone_in_it(world):
    world, log = run(world, {"p1": 'Tell Madegi Doy "All are welcome."'})
    assert any('"All are welcome."' in m for m in messages(log, "p2"))


def test_a_message_needs_quotes(world):
    order = only(world, "Tell John May hello")
    assert order.warnings and "double quotes" in order.warnings[0]


def test_a_message_needs_a_recipient(world):
    order = only(world, 'Say "hello"')
    assert order.warnings


def test_an_over_long_message_is_truncated(world):
    long_text = "x" * (config.MESSAGE_MAX_LENGTH + 50)
    world, log = run(world, {"p1": f'Tell John May "{long_text}"'})
    assert any("truncated" in m for m in messages(log, "p1"))
    delivered = [m for m in messages(log, "p2") if "says to" in m]
    assert delivered and len(delivered[0]) < len(long_text)


def test_a_message_may_cross_faction_lines_to_a_prisoner(world):
    """rules.md: the prisoner's own player receives it, not the captor."""
    world.characters["e"].is_prisoner = True
    world.characters["e"].captor_id = "j"
    world, log = run(world, {"p1": 'Tell John May "Surrender."'})
    assert any('"Surrender."' in m for m in messages(log, "p2"))


# ---------------------------------------------------------------------------
# POST
# ---------------------------------------------------------------------------

def test_posting_needs_a_secured_town(world):
    world.factions["p1"].secured_city_ids.clear()
    world, log = run(world, {"p1": 'Have Joe Flint post "No recruiting."'})
    assert not world.posted_messages
    assert any("has not secured it" in m for m in messages(log, "p1"))


def test_a_notice_goes_up_at_a_secured_town(world):
    world, log = run(world, {"p1": 'Have Joe Flint post "No recruiting."'})
    assert world.posted_messages["c1"] == "No recruiting."


def test_everyone_at_the_gates_sees_a_new_notice(world):
    world, log = run(world, {"p1": 'Have Joe Flint post "No recruiting."'})
    assert any("A notice at the gates of Madegi Doy reads" in m
               for m in messages(log, "p2"))


def test_someone_lurking_near_the_town_does_not_see_the_notice(world):
    world.characters["e"].location_position = LocationPosition.NEAR
    world, log = run(world, {"p1": 'Have Joe Flint post "No recruiting."'})
    assert not any("A notice at the gates" in m for m in messages(log, "p2"))


def test_an_empty_message_takes_the_notice_down(world):
    world.posted_messages["c1"] = "No recruiting."
    world, log = run(world, {"p1": 'Have Joe Flint post "".'})
    assert "c1" not in world.posted_messages
    assert any("took down the notice" in m for m in messages(log, "p1"))


def test_an_over_long_notice_is_rejected(world):
    long_text = "y" * (config.POST_MAX_LENGTH + 1)
    world, log = run(world, {"p1": f'Have Joe Flint post "{long_text}"'})
    assert "c1" not in world.posted_messages
    assert any("rejected" in m for m in messages(log, "p1"))


def test_a_notice_lapses_when_the_town_is_no_longer_secured(world):
    world.posted_messages["c1"] = "No recruiting."
    world.factions["p1"].secured_city_ids.clear()
    world, log = run(world, {"p1": ""})
    assert "c1" not in world.posted_messages


# ---------------------------------------------------------------------------
# REPORT and QUERY
# ---------------------------------------------------------------------------

def test_a_bare_report_describes_the_actor(world):
    order = only(world, "Report.")
    assert order.subject_ids == ["l"]
    assert not order.brief
    assert not order.immediate


def test_query_names_its_subjects_and_is_immediate(world):
    order = only(world, "Query Bill Johnson and Joe Flint.")
    assert order.subject_names == ["Bill Johnson", "Joe Flint"]
    assert order.immediate


def test_briefly_shortens_the_report(world):
    order = only(world, "Have Bill Johnson briefly report.")
    assert order.brief
    assert order.subject_ids == ["b"]


def test_a_report_states_skills_group_and_location(world):
    world.characters["b"].location_city_id = "c1"
    world.characters["b"].group_leader_id = "l"
    world.unit_stacks["u"] = models.UnitStack(
        id="u", faction_id="p1", location_city_id="c1",
        unit_type=UnitType.SOLDIER, count=39, owner_character_id="l")

    world, log = run(world, {"p1": "Report."})
    line = next(m for m in messages(log, "p1") if m.startswith("Report:"))
    assert "combat 20" in line and "magic 25" in line
    assert "Bill Johnson" in line          # named group member
    assert "39 soldiers" in line
    assert "Madegi Doy" in line


def test_a_brief_report_drops_the_skills(world):
    world, log = run(world, {"p1": "Briefly report."})
    line = next(m for m in messages(log, "p1") if m.startswith("Brief report:"))
    assert "combat" not in line


def test_a_report_relays_a_posted_notice(world):
    world.posted_messages["c1"] = "No recruiting."
    world, log = run(world, {"p1": "Report."})
    assert any("A notice at the gates" in m for m in messages(log, "p1"))


def test_a_report_can_name_other_people_at_the_location(world):
    """The neighbours line is a fog roll, so sweep seeds rather than fix one."""
    for seed in range(40):
        gs = _clone(world)
        gs, log = run(gs, {"p1": "Report."}, seed=seed)
        if any("Other notable people" in m and "John May" in m
               for m in messages(log, "p1")):
            return
    pytest.fail("no seed reported the rival at the same city")


def test_reporting_on_another_players_character_is_refused(world):
    order = only(world, "Query John May.")
    assert order.warnings


# ---------------------------------------------------------------------------
# ADDRESS and PASSWORD
# ---------------------------------------------------------------------------

def test_address_changes_where_reports_go(world):
    world, log = run(world, {"p1": 'Address "xyz@boogaloo.gov"'})
    assert world.factions["p1"].email == "xyz@boogaloo.gov"


def test_address_needs_quotes(world):
    # An unquoted address also splits on its own dot, which is the other half
    # of why the rules insist on the quotes.
    orders = parser.parse_orders("Address xyz@boogaloo.gov", world, "p1")
    address = next(o for o in orders if o.order_type() == "ADDRESS")
    assert address.warnings and "double quotes" in address.warnings[0]


def test_a_bare_password_is_accepted(world):
    world, log = run(world, {"p1": "Password SerendipityDoDah"})
    assert len(world.factions["p1"].password) >= config.PASSWORD_MIN_LENGTH
    assert any("password has been changed" in m for m in messages(log, "p1"))


def test_a_quoted_password_keeps_its_spaces_and_case(world):
    world, log = run(world, {"p1": 'password "This is a dum password."'})
    assert world.factions["p1"].password == "This is a dum password."


def test_a_short_password_is_replaced_by_a_generated_one(world):
    world, log = run(world, {"p1": 'Password "abc"'})
    assert len(world.factions["p1"].password) >= config.PASSWORD_MIN_LENGTH
    assert any("one was generated for you" in m for m in messages(log, "p1"))


def test_an_over_long_password_is_truncated(world):
    world, log = run(world, {"p1": f'Password "{"z" * 200}"'})
    assert len(world.factions["p1"].password) == config.PASSWORD_MAX_LENGTH


# ---------------------------------------------------------------------------
# Reporting and persistence
# ---------------------------------------------------------------------------

def test_messages_reach_the_player_report(world):
    parsed = {"p1": parser.parse_orders(
        'Have Joe Flint say "Here is the gold." to John May.', world, "p1")}
    world, log = engine.run_turn(world, parsed, seed=3)
    reports = reporting.generate_player_reports(world, log, parsed)
    assert '"Here is the gold."' in reports["p2"]


def test_postings_and_details_survive_save_and_load(world, tmp_path: Path):
    world.posted_messages["c1"] = "No recruiting."
    world.factions["p1"].email = "emperor@empire.gov"
    world.factions["p1"].password = "a good long password"

    storage.save_game_state(world, tmp_path)
    reloaded = storage.load_game_state(tmp_path)

    assert reloaded.posted_messages == {"c1": "No recruiting."}
    assert reloaded.factions["p1"].email == "emperor@empire.gov"
    assert reloaded.factions["p1"].password == "a good long password"


def test_an_old_save_without_postings_still_loads(world, tmp_path: Path):
    import json
    storage.save_game_state(world, tmp_path)
    state_file = tmp_path / "state.json"
    data = json.loads(state_file.read_text(encoding="utf-8"))
    del data["posted_messages"]
    for faction in data["factions"].values():
        faction.pop("email", None)
        faction.pop("password", None)
    state_file.write_text(json.dumps(data), encoding="utf-8")

    reloaded = storage.load_game_state(tmp_path)
    assert reloaded.posted_messages == {}
    assert reloaded.factions["p1"].email == ""


def _clone(gs):
    import copy
    return copy.deepcopy(gs)


def test_text_after_a_tell_message_is_reported_not_swallowed(world):
    """A missing period would otherwise merge the next order into this one."""
    order = only(world, 'Tell John May "Hello" Briefly report.')
    assert order.warnings
    assert "period after the closing quote" in order.warnings[0]
