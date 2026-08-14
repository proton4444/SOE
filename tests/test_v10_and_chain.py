"""
Tests for `and`-chained commands.

the design lets one sentence carry several orders: "Assign 20 soldiers and 23
horses to Bill Jenkins, and have him go to Ashford and attack Mike May" is
three commands. `and` also joins items within one command, so the splitter
only breaks a sentence where the clause so far is a complete command and the
tail starts a new one -- with a verb, with `have`, or with a quantity that
continues the previous verb. The HAVE form's actor stays on the clauses that
follow it ("have him go to Ashford and tax for 3 weeks, and go to Ennistown
and tax" is four orders to the same character).
"""

import pytest

from soe import engine, models, parser, pronouns
from soe.models import ItemType, PopulationBand


@pytest.fixture
def court():
    """A leader, a court of named characters, and cities to move between."""
    gs = models.GameState()
    gs.turn_number = 1
    for cid, name in [("c1", "Highfell"), ("c2", "Ashford"),
                      ("c3", "Velika"), ("c4", "Calder"),
                      ("c5", "Redport"), ("c6", "Ennistown"),
                      ("c7", "Hampton"), ("c8", "Ironvale"),
                      ("c9", "Nandigwa"), ("c10", "Bindy Village")]:
        gs.world_map.cities[cid] = models.City(
            id=cid, name=name, population_band=PopulationBand.MEDIUM)
    for a, b in [("c1", "c2"), ("c2", "c3"), ("c3", "c4"), ("c4", "c5"),
                 ("c1", "c6"), ("c6", "c7"), ("c1", "c8"), ("c1", "c9"),
                 ("c9", "c10")]:
        gs.world_map.roads[a + b] = models.Road(
            id=a + b, from_city_id=a, to_city_id=b,
            quality=models.RoadQuality.GOOD)
    gs.factions["p1"] = models.Faction(id="p1", name="Empire")

    court = [
        ("l", "Billy Jones", "male", True),
        ("j", "Alan Reed", "male", False),
        ("m", "Doctor McCoy", "male", False),
        ("d", "Donald Nap", "male", False),
        ("b", "Mark Bolton", "male", False),
        ("n", "Nancy Myers", "female", False),
        ("f", "Bill Fenton", "male", False),
        ("w", "Mary Wise", "female", False),
        ("o", "Bill Jenkins", "male", False),
        ("k", "Mike May", "male", False),
        ("t", "Thomas Ames", "male", False),
        ("p", "Phil Lucas", "male", False),
        ("r", "Mary Anderson", "female", False),
        ("u", "Mike Fenton", "male", False),
        ("y", "George Doone", "male", False),
        ("z", "Baldur", "male", False),
        ("a", "Tom Baldwin", "male", False),
        ("x", "Merlinus", "male", False),
        ("h", "Ameriki", "male", False),
        ("bb", "Bishop Sami Lukasa", "male", False),
        ("cc", "Simon Peres", "male", False),
        ("dd", "John Parker", "male", False),
        ("gg", "Bill Gershwin", "male", False),
        ("bj", "Bill Jones", "male", False),
        ("bm", "Bill May", "male", False),
        ("bh", "Bill Hawthorne", "male", False),
        ("pa", "Pamadandu", "male", False),
    ]
    for cid, name, gender, is_leader in court:
        gs.characters[cid] = models.Character(
            id=cid, name=name, faction_id="p1", location_city_id="c1",
            is_leader=is_leader, gender=gender, gold=500,
            magic_skill=30, magic_power_current=30, religion_skill=30,
            religious_power_current=30,
        )
    gs.characters["kk"] = models.Character(
        id="kk", name="King Bodo Bunji", faction_id="p9",
        location_city_id="c2", is_leader=True, gender="male", gold=500)
    gs.factions["p9"] = models.Faction(id="p9", name="Foreign")

    gs.magical_items["i1"] = models.MagicalItem(
        id="i1", name="*Ampu*", item_type=ItemType.CRYSTAL,
        holder_character_id="l", power_current=5, power_max=80)
    gs.magical_items["i2"] = models.MagicalItem(
        id="i2", name="*Wasute*", item_type=ItemType.CRYSTAL,
        holder_character_id="l", power_current=5, power_max=80)
    gs.magical_items["i3"] = models.MagicalItem(
        id="i3", name="*Velika*", item_type=ItemType.WAND,
        holder_character_id="h", power_current=30, power_max=60)
    return gs


def parse(gs, text, player="p1"):
    return parser.parse_orders(text, gs, player)


def types(orders):
    return [o.order_type() for o in orders]


# ---------------------------------------------------------------------------
# The command-language chains
# ---------------------------------------------------------------------------

def test_assign_have_and_attack_is_three_orders(court):
    orders = parse(court, "Assign 20 soldiers and 23 horses to Bill Jenkins, "
                         "and have him go to Ashford and attack Mike May.")
    assert types(orders) == ["ASSIGN", "ASSIGN", "MOVE", "ATTACK"]
    # The chain split around the item list, not inside it.
    assert not orders[0].warnings
    assert orders[0].recipient_id == "o"
    assert orders[1].recipient_id == "o"  # "23 horses" carries its own warning
    assert orders[2].actor_id == "o"      # him = Bill Jenkins
    assert orders[2].destination_city_id == "c2"
    assert orders[3].actor_id == "o"      # the HAVE actor stays sticky
    assert orders[3].target_name.lower() == "mike may"


def test_the_have_actor_stays_for_the_whole_tax_chain(court):
    # the design's longest chained example.
    text = ("Assign 200 soldiers to Captain Bill Jones. Have him go to "
            "Ashford and tax for 3 weeks, and go to Ennistown and tax, and "
            "go to Hampton and tax for 3 days and go to Bindy Village and "
            "tax for 12 hours.")
    orders = parse(court, text)
    assert types(orders) == ["ASSIGN", "MOVE", "TAX", "MOVE", "TAX",
                             "MOVE", "TAX", "MOVE", "TAX"]
    # Titles are ignored (the design), so the assign reaches Bill Jones...
    assert not orders[0].warnings
    assert orders[0].recipient_id == "bj"
    # ...and the sticky HAVE sends every clause to the same character.
    for order in orders[1:]:
        assert not order.warnings
        assert order.actor_id == "bj"  # him = Bill Jones


def test_gold_to_nancy_and_horses_to_bill_elides_the_second_give(court):
    orders = parse(court, "Give 50 gold to Nancy Myers and 20 horses to "
                          "Bill Fenton and have her join him.")
    assert types(orders) == ["ASSIGN", "ASSIGN", "JOIN"]
    assert orders[0].recipient_id == "n"
    assert orders[0].gold_amount == 50
    assert orders[1].recipient_id == "f"  # the elided GIVE keeps its form
    assert orders[2].target_id == "f"  # her joins him (Bill Fenton)


def test_recruit_soldiers_and_workers_is_two_recruits(court):
    orders = parse(court, "Have Mary Anderson recruit 5 soldiers and 3 "
                          "workers and come to Velika and assign them "
                          "to me.")
    assert types(orders) == ["RECRUIT", "RECRUIT", "MOVE", "ASSIGN", "ASSIGN"]
    assert orders[0].count == 5 and orders[0].unit_type == "soldier"
    assert orders[1].count == 3 and orders[1].unit_type == "worker"
    assert orders[2].actor_id == "r" and orders[2].destination_city_id == "c3"
    # them = both kinds: one assign per kind, to the leader.
    assert orders[3].recipient_id == "l" and orders[3].unit_count == 5
    assert orders[4].recipient_id == "l" and orders[4].unit_count == 3
    assert not any(o.warnings for o in orders)


def test_assign_20_soldiers_and_23_horses_replicates_the_target(court):
    orders = parse(court, "Assign 20 soldiers and 23 horses to Bill Jenkins.")
    assert types(orders) == ["ASSIGN", "ASSIGN"]
    assert orders[0].unit_count == 20
    assert orders[0].recipient_id == "o"
    assert orders[1].recipient_id == "o"


def test_mixed_names_and_counts_assign_each_to_the_recipient(court):
    orders = parse(court, "Assign Bishop Sami Lukasa and Simon Peres and "
                          "200 soldiers to John Parker, and have him go to "
                          "Ashford and capture 30 soldiers.")
    assert types(orders) == ["ASSIGN", "ASSIGN", "MOVE", "CAPTURE"]
    assert orders[0].character_names == ["Bishop Sami Lukasa", "Simon Peres"]
    assert orders[0].recipient_id == "dd"
    assert orders[1].unit_count == 200 and orders[1].recipient_id == "dd"
    assert orders[2].actor_id == "dd"  # him = John Parker


def test_charge_keeps_its_own_item_list_but_splits_at_give(court):
    orders = parse(court, "Charge Ampu to 75 power and Wasute by 7 power "
                          "and give Ampu to Merlinus.")
    assert types(orders) == ["CHARGE", "ASSIGN"]
    assert len(orders[0].targets) == 2  # one CHARGE carrying both items
    assert orders[1].item_names == ["*Ampu*"]
    assert orders[1].recipient_id == "x"


def test_buy_and_go_and_give_it(court):
    orders = parse(court, "Buy 1 horse and go to Calder and give it to "
                          "Bill May.")
    assert types(orders) == ["TRADE", "MOVE", "ASSIGN"]
    assert not orders[1].warnings
    # it = "1 horse": the give order's subject says so (horses are not
    # transferable in the engine, so the order carries an honest warning).
    assert orders[2].warnings and "horse" in orders[2].warnings[0]


def test_charge_and_give_it_to_me(court):
    orders = parse(court, "Have Ameriki charge Velika to 30 points and "
                          "give it to me.")
    assert types(orders) == ["CHARGE", "ASSIGN"]
    assert orders[0].actor_id == "h"
    assert orders[0].targets[0].item_id == "i3"
    assert orders[1].donor_id == "h"      # sticky HAVE
    assert orders[1].recipient_id == "l"  # me = the leader
    assert orders[1].item_names == ["*Velika*"]
    assert not any(o.warnings for o in orders)


def test_the_two_thems_refer_to_different_lists(court):
    # Design: "the first them refers to 20 horses. The second them refers
    # to 20 horses and 2 sailors."
    text = ("Purchase 20 horses and assign them and 2 sailors to Watusingi, "
            "and have him go to Highfell and assign them to Alan Reed.")
    orders = parse(court, text)
    assert types(orders) == ["TRADE", "ASSIGN", "ASSIGN", "MOVE",
                             "ASSIGN", "ASSIGN"]
    assert "watusingi" in orders[1].warnings[0]  # the first them = 20 horses
    assert "watusingi" in orders[2].warnings[0]  # the 2 sailors
    assert "horses" in orders[4].warnings[0]  # second them = horses and sailors
    assert not orders[5].warnings
    assert orders[4].recipient_id == "j" and orders[5].recipient_id == "j"
    assert orders[3].actor_id == "j"  # him = Alan Reed (named later)


def test_only_the_last_list_is_assigned(court):
    # Design: "them can never refer to entities mentioned in separate
    # commands" -- only the 10 horses are assigned.
    orders = parse(court, "Recruit 10 soldiers and buy 10 horses and assign "
                          "them to Alan Reed.")
    assert types(orders) == ["RECRUIT", "TRADE", "ASSIGN"]
    assert orders[2].unit_type == "HORSE" or "horses" in orders[2].warnings[0]
    assert "soldier" not in str(orders[2].warnings)


def test_mass_nouns_take_it_and_split_on_and(court):
    orders = parse(court, "Take 10 copper and 20 silver from Bill Hawthorne, "
                          "and give it to Pamadandu.")
    assert types(orders) == ["GET", "GET", "ASSIGN", "ASSIGN"]
    assert orders[0].resources == {"copper": 10}
    assert orders[1].resources == {"silver": 20}
    # it = "10 copper and 20 silver", split by the chain into two gives.
    assert orders[2].resources == {"copper": 10}
    assert orders[3].resources == {"silver": 20}


def test_have_him_to_go_form(court):
    # the design writes "have him to go to Redport".
    orders = parse(court, "Give 50 armor to Thomas Ames and have him to go "
                          "to Redport and give it to Phil Lucas.")
    assert types(orders) == ["ASSIGN", "MOVE", "ASSIGN"]
    assert orders[0].resources == {"armor": 50}
    assert orders[1].actor_id == "t" and orders[1].destination_city_id == "c5"
    assert orders[2].donor_id == "t" and orders[2].recipient_id == "p"
    assert not any(o.warnings for o in orders)


def test_collect_and_give_what_was_gathered(court):
    # Design: "the pronoun it can be used to refer to whatever was
    # successfully collected."
    orders = parse(court, "Have George Doone go to Nandigwa and collect wood "
                          "for 5 days and give it to me.")
    assert types(orders) == ["MOVE", "COLLECT", "ASSIGN"]
    assert orders[1].actor_id == "y" and orders[1].resource_type == "wood"
    assert orders[2].donor_id == "y"
    assert orders[2].recipient_id == "l"
    assert orders[2].resources == {"wood": -1}  # whatever was collected
    assert not any(o.warnings for o in orders)


def test_repeatedly_governs_only_its_own_clause(court):
    orders = parse(court, "Have Baldur repeatedly gather stone for 10 hours "
                          "and give it to Engineer Tom Baldwin.")
    assert types(orders) == ["REPEAT", "COLLECT", "ASSIGN"]
    assert orders[1].actor_id == "z" and orders[1].resource_type == "stone"
    assert orders[2].donor_id == "z" and orders[2].recipient_id == "a"
    assert not any(o.warnings for o in orders)


def test_skill_lists_are_not_split(court):
    # "study magic and sailing" is two STUDY orders (C16); sailing is not a
    # command verb, so the `and` used to stay inside one clause and drop it.
    orders = parse(court, "Have Mike Fenton study magic and sailing for 1 week.")
    assert types(orders) == ["STUDY", "STUDY"]
    assert {o.skill_name for o in orders} == {"magic", "sailing"}
    assert not any(o.warnings for o in orders)


def test_city_waypoints_are_not_split(court):
    # "have him travel to Willis Grove and Ashford" is one journey, so the
    # `and` stays inside the move clause. Multi-stop routing is a separate
    # gap; what is pinned here is that the chain does not cut the sentence.
    orders = parse(court, "Have Alan Reed go to Highfell and Ashford.")
    assert types(orders) == ["MOVE"]
    assert orders[0].actor_id == "j"
    assert orders[0].warnings  # the second city is not a routable stop


def test_a_failed_chained_clause_keeps_its_neighbours(court):
    # An error in one clause drops only that clause; the rest of the chain
    # and the other sentences are untouched.
    orders = parse(court, "Go to Ironvale and sail to Atlantis.")
    assert types(orders) == ["MOVE", "SAIL"]
    assert not orders[0].warnings
    assert "atlantis" in orders[1].warnings[0]


# ---------------------------------------------------------------------------
# Pronouns across chained clauses
# ---------------------------------------------------------------------------

def test_him_binds_to_what_was_named_before_each_position(court):
    # The rules' own command-language example: the first `him` is Bill
    # Gershwin; the second is King Bodo Bunji, named in between.
    text = ("Assign 20 soldiers and 2 workers and 200 gold and 22 horses to "
            "Bill Gershwin. Have him go to Ashford, and say \"Here is the "
            "money I promised you.\" to King Bodo Bunji, and give him 100 "
            "gold.")
    orders = parse(court, text)
    assert types(orders) == ["ASSIGN", "ASSIGN", "ASSIGN", "ASSIGN",
                             "MOVE", "SAY", "ASSIGN"]
    assert all(not o.warnings for o in orders[4:])
    assert orders[4].actor_id == "gg"  # him = Bill Gershwin
    assert orders[5].actor_id == "gg"
    assert "Here is the money I promised you." in orders[5].message
    assert orders[6].donor_id == "gg"
    assert orders[6].recipient_id == "kk"  # him = King Bodo Bunji


def test_him_in_have_position_can_be_the_agent(court):
    # Design: "him refers to Alan Reed" even though Alan Reed is the
    # agent of the first command.
    orders = parse(court, "Have Alan Reed give 10 horses to Billy Jones and "
                          "have him go to Highfell.")
    assert types(orders) == ["ASSIGN", "MOVE"]
    assert orders[1].actor_id == "j"


def test_him_is_not_the_agent_of_an_earlier_command(court):
    # Design: him is Mark Bolton, because Donald Nap is the agent.
    orders = parse(court, "Have Mark Bolton study combat for 4 weeks. Have "
                          "Donald Nap go to Highfell and give him 100 gold.")
    assert types(orders) == ["STUDY", "MOVE", "ASSIGN"]
    assert orders[2].donor_id == "d" and orders[2].recipient_id == "b"


def test_mccoy_in_a_list_is_still_not_a_referent(court):
    orders = parse(court, "Assign 10 soldiers and Doctor McCoy to Alan Reed "
                          "and have him go to Velika.")
    assert types(orders) == ["ASSIGN", "MOVE"]
    assert orders[1].actor_id == "j"


def test_resolution_rewrites_the_two_thems(court):
    context = pronouns.ReferentContext()
    result = pronouns.resolve(
        "purchase 20 horses and assign them and 2 sailors to watusingi and "
        "have him go to highfell and assign them to alan reed",
        context, court, "p1")
    assert "assign 20 horses and 2 sailors to watusingi" in result
    assert result.endswith("assign 20 horses and 2 sailors to alan reed")


def test_bare_mass_noun_gives_it_something_to_stand_for(court):
    context = pronouns.ReferentContext()
    pronouns.resolve("have baldur gather stone for 10 hours",
                     context, court, "p1")
    second = pronouns.resolve("give it to engineer tom baldwin",
                              context, court, "p1")
    assert second == "give stone to engineer tom baldwin"


# ---------------------------------------------------------------------------
# End to end through the engine
# ---------------------------------------------------------------------------

def test_resource_give_and_take_move_through_the_engine(court):
    gs = court
    gs.characters["l"].resources["stone"] = 40
    gs.characters["l"].resources["wood"] = 25
    orders = parser.parse_orders(
        "Give 10 stone to Alan Reed. Have him take 5 wood from me.",
        gs, "p1")
    engine.run_turn(gs, {"p1": orders}, seed=42)
    assert gs.characters["l"].resources["stone"] == 30
    assert gs.characters["j"].resources["stone"] == 10
    assert gs.characters["j"].resources["wood"] == 5
    assert gs.characters["l"].resources["wood"] == 20


def test_give_all_of_a_gathered_resource(court):
    gs = court
    gs.characters["z"].resources["stone"] = 70
    orders = parser.parse_orders(
        "Have Baldur give stone to Tom Baldwin.", gs, "p1")
    engine.run_turn(gs, {"p1": orders}, seed=42)
    assert gs.characters["z"].resources.get("stone", 0) == 0
    assert gs.characters["a"].resources.get("stone", 0) == 70
