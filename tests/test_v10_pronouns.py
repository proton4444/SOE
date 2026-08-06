"""
Tests for order pronouns.

`rules.md` fixes each pronoun's referent precisely: `me`/`I`/`you` are always
the leader, `him`/`her` are the most recently named person of that gender who
is neither the agent nor the leader, `it` is the last single thing, `them` the
last group, and the reflexives are the agent. Resolution happens before verb
dispatch, so these tests mostly check the rewritten sentence.
"""

import pytest

from spoils_engine import models, parser, pronouns
from spoils_engine.models import ItemType, PopulationBand


@pytest.fixture
def court():
    """A leader and a court of named characters, both genders represented."""
    gs = models.GameState()
    gs.turn_number = 1
    for cid, name in [("c1", "Madegi Doy"), ("c2", "Tashendi"),
                      ("c3", "Umadosh"), ("c4", "Kitesta")]:
        gs.world_map.cities[cid] = models.City(
            id=cid, name=name, population_band=PopulationBand.MEDIUM)
    for a, b in [("c1", "c2"), ("c2", "c3"), ("c3", "c4"), ("c1", "c3")]:
        gs.world_map.roads[a + b] = models.Road(
            id=a + b, from_city_id=a, to_city_id=b,
            quality=models.RoadQuality.GOOD)
    gs.factions["p1"] = models.Faction(id="p1", name="Empire")

    court = [
        ("l", "Billy Jones", "male", True),
        ("j", "Joe Flint", "male", False),
        ("m", "Doctor McCoy", "male", False),
        ("d", "Donald Nap", "male", False),
        ("b", "Mark Bolton", "male", False),
        ("n", "Nancy Myers", "female", False),
        ("f", "Bill Fenton", "male", False),
        ("w", "Mary Wise", "female", False),
    ]
    for cid, name, gender, is_leader in court:
        gs.characters[cid] = models.Character(
            id=cid, name=name, faction_id="p1", location_city_id="c1",
            is_leader=is_leader, gender=gender, gold=500,
            magic_skill=30, magic_power_current=30, religion_skill=30,
            religious_power_current=30,
        )
    return gs


def rewrite(gs, text, player="p1"):
    """Resolve pronouns sentence by sentence, returning the rewritten last one."""
    context = pronouns.ReferentContext()
    out = []
    for sentence in parser.extract_sentences(parser.normalize_text(text)):
        out.append(pronouns.resolve(sentence, context, gs, player))
    return out[-1] if out else ""


# ---------------------------------------------------------------------------
# me / I / you -- always the leader
# ---------------------------------------------------------------------------

def test_me_and_you_both_mean_the_leader(court):
    assert rewrite(court, "Have Joe Flint give me 100 gold.") == \
        "have joe flint give billy jones 100 gold"
    assert rewrite(court, "Have Joe Flint give you 100 gold.") == \
        "have joe flint give billy jones 100 gold"


def test_me_means_the_leader_even_when_somebody_else_acts(court):
    # rules.md: "you should always use the pronoun me or you when referring to
    # your leader", whoever the agent happens to be.
    assert "billy jones" in rewrite(court, "Have Mary Wise assign 25 soldiers to me.")


def test_me_is_a_whole_word(court):
    """`me` must not match inside another word."""
    assert rewrite(court, "Have Joe Flint mine silver.") == \
        "have joe flint mine silver"


# ---------------------------------------------------------------------------
# him / her
# ---------------------------------------------------------------------------

def test_him_is_the_last_named_man_not_the_current_agent(court):
    # rules.md's own example: him is Mark Bolton, because Donald Nap is the
    # agent of the order the pronoun appears in.
    result = rewrite(
        court,
        "Have Mark Bolton study combat for 4 weeks. "
        "Have Donald Nap go to Madegi Doy and give him 100 gold.")
    assert "mark bolton" in result
    assert "donald nap go" in result


def test_him_never_means_the_leader(court):
    # rules.md: him refers to Joe Flint, not to Billy Jones, even though the
    # leader was named later in the sentence.
    result = rewrite(
        court,
        "Have Joe Flint give 10 gold to Billy Jones. "
        "Have him go to Madegi Doy.")
    assert result == "have joe flint go to madegi doy"


def test_him_and_her_are_told_apart_by_gender(court):
    result = rewrite(
        court,
        "Give 50 gold to Nancy Myers. Give 20 gold to Bill Fenton. "
        "Have her join him.")
    assert result == "have nancy myers join bill fenton"


def test_a_person_inside_a_list_cannot_be_the_referent(court):
    # rules.md: him cannot be Doctor McCoy, who is linked to the 10 soldiers.
    result = rewrite(
        court,
        "Assign 10 soldiers and Doctor McCoy to Joe Flint. "
        "Have him go to Tashendi.")
    assert result == "have joe flint go to tashendi"


def test_the_agent_of_an_earlier_order_is_still_a_referent_later(court):
    """Being the agent only bars a pronoun in that character's own order."""
    result = rewrite(court, "Have Joe Flint tax. Have Mary Wise follow him.")
    assert "joe flint" in result


def test_an_unresolvable_pronoun_is_left_alone(court):
    """Better an honest 'not found' than a silently wrong actor."""
    assert rewrite(court, "Have him go to Tashendi.") == "have him go to tashendi"


# ---------------------------------------------------------------------------
# Reflexives
# ---------------------------------------------------------------------------

def test_reflexives_mean_the_agent(court):
    assert rewrite(court, "Have Bill Fenton bless himself.") == \
        "have bill fenton bless bill fenton"
    assert rewrite(court, "Have Nancy Myers bless herself.") == \
        "have nancy myers bless nancy myers"


def test_a_reflexive_without_an_agent_means_the_leader(court):
    assert rewrite(court, "Bless myself.") == "bless billy jones"


def test_himself_is_not_mangled_by_the_him_rule(court):
    """`himself` contains `him`; resolving in the wrong order would corrupt it."""
    result = rewrite(court, "Have Joe Flint tax. Have Bill Fenton bless himself.")
    assert result == "have bill fenton bless bill fenton"


# ---------------------------------------------------------------------------
# it / them
# ---------------------------------------------------------------------------

def test_it_means_a_single_unnamed_thing(court):
    assert rewrite(court, "Recruit 1 worker. Assign it to Joe Flint.") == \
        "assign 1 worker to joe flint"


def test_them_means_several(court):
    assert rewrite(court, "Recruit 5 soldiers. Assign them to me.") == \
        "assign 5 soldiers to billy jones"


def test_a_mass_noun_takes_it_however_much_there_is(court):
    # rules.md: "you must use it when referring to more than one unit of
    # substances (i.e. mass nouns) such as wood, iron, or armor".
    assert rewrite(court, "Buy 10 stone. Give it to Joe Flint.") == \
        "give 10 stone to joe flint"


def test_them_can_mean_a_group_of_people(court):
    result = rewrite(
        court,
        "Have Joe Flint and Mary Wise tax for 4 weeks. Assign them to me.")
    assert result == "assign joe flint and mary wise to billy jones"


def test_a_later_referent_replaces_an_earlier_one(court):
    # rules.md: "them can never refer to entities mentioned in separate
    # commands" -- only the most recent stands.
    result = rewrite(
        court,
        "Recruit 10 soldiers. Buy 10 horses. Assign them to Joe Flint.")
    assert result == "assign 10 horses to joe flint"


def test_it_can_mean_a_magical_item(court):
    court.magical_items["i1"] = models.MagicalItem(
        id="i1", name="*Ampu*", item_type=ItemType.CRYSTAL,
        holder_character_id="l", power_current=5, power_max=80)
    result = rewrite(court, "Charge *Ampu* to 75 power. Give it to Joe Flint.")
    assert result == "give *ampu* to joe flint"


# ---------------------------------------------------------------------------
# End to end through the parser
# ---------------------------------------------------------------------------

def test_a_pronoun_order_parses_into_a_real_order(court):
    orders = parser.parse_orders(
        "Have Joe Flint tax. Have him go to Tashendi.", court, "p1")
    move = [o for o in orders if o.order_type() == "MOVE"]
    assert move and not move[0].warnings
    assert move[0].actor_id == "j"
    assert move[0].destination_city_id == "c2"


def test_giving_an_item_by_pronoun_parses(court):
    court.magical_items["i1"] = models.MagicalItem(
        id="i1", name="*Ampu*", item_type=ItemType.CRYSTAL,
        holder_character_id="l", power_current=5, power_max=80)
    orders = parser.parse_orders(
        "Charge *Ampu* to 75 power. Give it to Doctor McCoy.", court, "p1")
    give = [o for o in orders if o.order_type() == "ASSIGN"]
    assert give and not give[0].warnings
    assert give[0].item_names == ["*Ampu*"]
    assert give[0].recipient_id == "m"


def test_teleporting_me_with_a_wand_parses(court):
    """The order that could not be written before pronouns existed."""
    court.magical_items["i1"] = models.MagicalItem(
        id="i1", name="*Opistama*", item_type=ItemType.WAND,
        holder_character_id="m", power_current=60, power_max=75,
        skill_level=80, spell="teleport")
    orders = parser.parse_orders(
        "Have Doctor McCoy teleport me to Kitesta using *Opistama*.",
        court, "p1")
    assert orders and not orders[0].warnings
    assert orders[0].actor_id == "m"
    assert orders[0].target_character_id == "l"
    assert orders[0].destination_city_id == "c4"
    assert orders[0].wand_name == "*opistama*"


def test_referents_do_not_leak_between_players(court):
    """Each submission gets its own context; one player cannot see another's."""
    court.factions["p2"] = models.Faction(id="p2", name="Horde")
    court.characters["e1"] = models.Character(
        id="e1", name="Tengri", faction_id="p2", location_city_id="c1",
        is_leader=True, gender="male")

    parser.parse_orders("Have Joe Flint tax.", court, "p1")
    # p2 never named anybody, so `him` has nothing to bind to.
    orders = parser.parse_orders("Have him go to Tashendi.", court, "p2")
    assert orders and orders[0].warnings
