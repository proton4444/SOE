"""
Magical items: the enchantress's amulets, crystals, orbs, rings and wands.

`rules.md` gives items their own economy that cuts across several subsystems,
so the shared logic lives here rather than in `engine`:

- **Crystals** pool with the caster's own power and are always tapped first.
- **Amulets** lend a skill without teaching it.
- **Rings** divide an attacker's hit chance.
- **Wands** supply both the skill and the power for one named spell, but only
  when the order names the wand.
- **Orbs** carry their own power for SCAN and never fill up.

Two rules constrain almost everything here. Items are indestructible, so
nothing in this module deletes a found item — only conjured ones expire. And
"magical items will never work together to perform the same task", so a wand
never draws on a crystal, and two wands never combine.
"""

import random
from typing import Optional

from spoils_engine import config
from spoils_engine.models import (
    Character, GameState, ItemType, MagicalItem,
)


# ============================================================================
# NAMING
# ============================================================================

# The enchantress's names are polysyllabic and vaguely Polynesian in rules.md
# (*Wameka*, *Opistama*, *Kwimikonta*, *Nenikasta*). These syllables generate
# names in the same register.
_NAME_HEAD = ["wa", "ha", "ka", "ni", "ju", "ta", "me", "gi", "am", "opi",
              "kwi", "nen", "fi", "um", "ash", "bo", "dela", "sur"]
_NAME_MID = ["me", "si", "ka", "mi", "ne", "do", "pu", "la", "ti", "ra",
             "shen", "kon", "bam", "wu", ""]
_NAME_TAIL = ["ka", "sta", "ni", "ta", "bo", "mba", "shi", "du", "kwa",
              "la", "ma", "pesh"]


def generate_item_name(game_state: GameState, rng: random.Random) -> str:
    """
    Invent a name in the enchantress's style, wrapped in asterisks.

    Retries on collision with an existing item so that a name always identifies
    exactly one item, which is what lets orders refer to items by name at all.
    """
    taken = {item.name.lower() for item in game_state.magical_items.values()}
    for _ in range(50):
        name = (rng.choice(_NAME_HEAD) + rng.choice(_NAME_MID)
                + rng.choice(_NAME_TAIL))
        candidate = f"*{name.capitalize()}*"
        if candidate.lower() not in taken:
            return candidate
    # Astronomically unlikely; fall back to something guaranteed unique.
    return f"*Relic{len(game_state.magical_items) + 1}*"


def normalize_item_name(name: str) -> str:
    """
    Reduce an item name to its comparable core.

    Players may or may not type the asterisks, so both `*Wameka*` and `Wameka`
    have to resolve to the same item.
    """
    return name.strip().strip("*").strip().lower()


def find_item_by_name(name: str, game_state: GameState) -> Optional[MagicalItem]:
    """Look up an item by the enchantress's name, asterisks optional."""
    target = normalize_item_name(name)
    if not target:
        return None
    for item in game_state.magical_items.values():
        if normalize_item_name(item.name) == target:
            return item
    return None


# ============================================================================
# POSSESSION
# ============================================================================

def items_held_by(character_id: str, game_state: GameState) -> list[MagicalItem]:
    """Every item the given character is carrying, in a stable order."""
    if not character_id:
        return []
    return sorted(
        (item for item in game_state.magical_items.values()
         if item.holder_character_id == character_id),
        key=lambda i: i.id,
    )


def items_of_type(character_id: str, item_type: ItemType,
                  game_state: GameState) -> list[MagicalItem]:
    """The character's items of one kind."""
    return [i for i in items_held_by(character_id, game_state)
            if i.item_type == item_type]


def can_reach_item(character: Character, item: MagicalItem,
                   game_state: GameState) -> bool:
    """
    Whether `character` may CHARGE or ABSORB this item.

    rules.md: the item need not be in his possession, as long as whoever holds
    it is in the same location and controlled by the same player. An item with
    no holder is lying in a ruin and is reachable by nobody.
    """
    if not item.holder_character_id:
        return False
    if item.holder_character_id == character.id:
        return True
    holder = game_state.characters.get(item.holder_character_id)
    if not holder or holder.is_dead:
        return False
    return (holder.faction_id == character.faction_id
            and holder.location_city_id == character.location_city_id)


# ============================================================================
# CRYSTALS: THE SHARED POWER POOL
# ============================================================================

def crystal_power(character: Character, game_state: GameState) -> int:
    """Total power stored across every crystal the character carries."""
    return sum(c.power_current
               for c in items_of_type(character.id, ItemType.CRYSTAL, game_state))


def available_magic_power(character: Character, game_state: GameState) -> int:
    """
    Magic power the character can spend right now: crystals plus their own.

    This is the number every magic phase should test against instead of
    `magic_power_current`, so that a crystal actually helps.
    """
    return character.magic_power_current + crystal_power(character, game_state)


def spend_magic_power(character: Character, amount: int,
                      game_state: GameState) -> bool:
    """
    Spend magic power, draining crystals before the caster's own reserves.

    rules.md: "The power in a crystal is always tapped before the natural power
    of the spell-caster", and where several crystals are held "one will be
    completely drained of power before the next one is tapped, and there is no
    way to predict which one will be tapped first" — so they drain in id order,
    one at a time.

    Returns False and changes nothing if the total is short.
    """
    if amount <= 0:
        return True
    if available_magic_power(character, game_state) < amount:
        return False

    remaining = amount
    for crystal in items_of_type(character.id, ItemType.CRYSTAL, game_state):
        if remaining <= 0:
            break
        take = min(crystal.power_current, remaining)
        crystal.power_current -= take
        remaining -= take
    if remaining > 0:
        character.magic_power_current -= remaining
    return True


# ============================================================================
# AMULETS: BORROWED SKILL
# ============================================================================

# rules.md: "An amulet NEVER provides skill in magic or religion."
AMULET_FORBIDDEN_SKILLS = frozenset({"magic", "religion"})

# Skills an amulet may carry, mapped to the Character field they stand in for.
AMULET_SKILLS = {
    "trading": "trading_skill",
    "combat": "combat_skill",
}


def amulet_skill_level(character: Character, skill: str,
                       game_state: GameState) -> int:
    """
    The best level any amulet lends this character for `skill`.

    rules.md: "If a person possesses more than one amulet for the same skill,
    then the highest level will apply." Returns 0 when no amulet applies.
    """
    if skill in AMULET_FORBIDDEN_SKILLS:
        return 0
    levels = [a.skill_level
              for a in items_of_type(character.id, ItemType.AMULET, game_state)
              if a.skill == skill]
    return max(levels, default=0)


def effective_skill_with_items(character: Character, skill: str,
                               game_state: GameState) -> int:
    """
    A character's working level in `skill`, taking amulets into account.

    The character's own skill is reduced by ill health as usual; an amulet's
    level is not, because the knowledge is the item's rather than the wearer's.
    """
    field_name = AMULET_SKILLS.get(skill)
    own = character.effective_skill(getattr(character, field_name, 0)) if field_name else 0
    return max(own, amulet_skill_level(character, skill, game_state))


# ============================================================================
# RINGS: PROTECTION IN COMBAT
# ============================================================================

def ring_protection(character: Character, game_state: GameState,
                    blessed: bool = False) -> int:
    """
    The protection factor of the character's best ring, 0 if they wear none.

    rules.md: "If a person possesses more than one ring, then the most powerful
    one will be effective. If a person with a ring is also BLESSED, then the
    blessing will effectively add +1 to the ring's protection factor." The
    blessing bonus only applies to someone who actually has a ring.
    """
    best = max((r.protection
                for r in items_of_type(character.id, ItemType.RING, game_state)),
               default=0)
    if best <= 0:
        return 0
    return best + 1 if blessed else best


def apply_ring_protection(hit_chance: float, protection: int) -> float:
    """
    Divide a hit chance by a ring's protection factor.

    rules.md works the example in whole percent: a 74% chance against *Fidula*
    (prot 3) becomes 24%, "drop fractions". The chance is passed and returned
    as a 0..1 fraction here, so the truncation is done on the percentage.
    """
    if protection <= 0:
        return hit_chance
    return int(hit_chance * 100.0 / protection) / 100.0


# ============================================================================
# WANDS: BORROWED SKILL AND POWER
# ============================================================================

# rules.md lists the words a player may use to describe a wand's spell. They
# fold onto the five spells the engine actually casts.
WAND_SPELLS = {
    "conjure": "conjure", "conjuring": "conjure", "conjuration": "conjure",
    "fly": "fly", "flying": "fly",
    "probe": "probe", "probing": "probe",
    "summon": "summon", "summoning": "summon",
    "teleport": "teleport", "teleporting": "teleport",
    "teleportation": "teleport",
}


def canonical_spell(word: str) -> str:
    """Fold one of the rules' wand words onto its spell, or '' if unknown."""
    return WAND_SPELLS.get(word.strip().lower(), "")


def find_wand(character: Character, name: str, spell: str,
              game_state: GameState) -> tuple[Optional[MagicalItem], str]:
    """
    Resolve the wand a spell order named.

    rules.md: "A wand will never be used automatically - its name must be
    specified in the order", so this is only called when the player named one.
    Returns (wand, error); exactly one is meaningful.
    """
    item = find_item_by_name(name, game_state)
    if not item:
        return None, f"there is no magical item called {name}"
    if item.item_type != ItemType.WAND:
        return None, f"{item.name} is a {item.item_type.value}, not a wand"
    if item.holder_character_id != character.id:
        return None, f"{character.name} does not possess {item.name}"
    if spell and item.spell != spell:
        return None, f"{item.name} is a wand of {item.spell}, not {spell}"
    return item, ""


def cast_with_wand(wand: MagicalItem, cost: int, skill_needed: int) -> str:
    """
    Spend a wand's power on a spell, or explain why it cannot be cast.

    A wand supplies both the skill and the power, and never borrows either:
    "a wand will not tap a crystal if it needs power - it can only use its own
    power". Returns "" on success, having debited the wand.
    """
    if wand.skill_level < skill_needed:
        return (f"{wand.name} casts at magic skill {wand.skill_level}, "
                f"which is not enough (needs {skill_needed})")
    if wand.power_current < cost:
        return (f"{wand.name} has {wand.power_current} power, "
                f"not the {cost} this spell needs")
    wand.power_current -= cost
    return ""


def pay_for_spell(character: Character, cost: int, spell: str,
                  wand_name: str, game_state: GameState,
                  skill_needed: int = 0) -> str:
    """
    Pay a spell's cost, from a named wand if the order named one.

    This is the single entry point every spell phase should use, so that the
    two rules that cut across all of them hold everywhere: a crystal is tapped
    before the caster's own power, and a wand is used only when named and never
    pools with anything else.

    Returns "" on success, or the reason the spell could not be paid for.
    """
    if wand_name:
        wand, error = find_wand(character, wand_name, spell, game_state)
        if error:
            return error
        return cast_with_wand(wand, cost, skill_needed)

    if skill_needed and character.effective_skill(character.magic_skill) < skill_needed:
        return (f"{character.name} has magic skill "
                f"{character.effective_skill(character.magic_skill)}, "
                f"which is not enough (needs {skill_needed})")
    if not spend_magic_power(character, cost, game_state):
        return (f"{character.name} has "
                f"{available_magic_power(character, game_state)} magic power, "
                f"not the {cost} this spell needs")
    return ""


# ============================================================================
# CREATING ITEMS
# ============================================================================

def _new_item_id(game_state: GameState) -> str:
    """Allocate an item id that no live item is using."""
    n = len(game_state.magical_items) + 1
    while f"item_{n}" in game_state.magical_items:
        n += 1
    return f"item_{n}"


def make_item(game_state: GameState, rng: random.Random, item_type: ItemType,
              holder_id: str = "", expires_turn: int = -1,
              skill: str = "", spell: str = "") -> MagicalItem:
    """
    Mint a magical item of the requested kind and roll its strength.

    `rules.md` is explicit that the finder or conjurer gets no say in how
    strong an item is — "there is no way to specify the power or skill level of
    the item obtained" — so every level is rolled here. `skill` and `spell` are
    honoured for amulets and wands, because those the player does choose.
    """
    item = MagicalItem(
        id=_new_item_id(game_state),
        name=generate_item_name(game_state, rng),
        item_type=item_type,
        holder_character_id=holder_id,
        expires_turn=expires_turn,
    )

    if item_type == ItemType.AMULET:
        choices = [s for s in AMULET_SKILLS if s not in AMULET_FORBIDDEN_SKILLS]
        item.skill = skill if skill in AMULET_SKILLS else rng.choice(choices)
        item.skill_level = rng.randint(*config.ITEM_AMULET_SKILL_RANGE)
    elif item_type == ItemType.CRYSTAL:
        item.power_max = rng.randint(*config.ITEM_CRYSTAL_MAX_RANGE)
        item.power_current = rng.randint(0, item.power_max)
    elif item_type == ItemType.ORB:
        # An orb has no ceiling, so power_max stays 0 and means "no maximum".
        item.power_current = rng.randint(*config.ITEM_ORB_POWER_RANGE)
    elif item_type == ItemType.RING:
        item.protection = rng.randint(*config.ITEM_RING_PROTECTION_RANGE)
    elif item_type == ItemType.WAND:
        item.spell = spell or rng.choice(sorted(set(WAND_SPELLS.values())))
        item.power_max = rng.randint(*config.ITEM_WAND_MAX_RANGE)
        item.power_current = rng.randint(0, item.power_max)
        item.skill_level = rng.randint(*config.ITEM_WAND_SKILL_RANGE)

    game_state.magical_items[item.id] = item
    return item


def describe(item: MagicalItem, game_state: Optional[GameState] = None) -> str:
    """
    Format an item the way `rules.md` shows it on a status report.

    e.g. `*Wameka* [amulet, trading 72]`, `*Nashi* [crystal, power 51/60]`,
    `*Opistama* [wand, teleport 62/75, 3d]`. The trailing day count appears
    only for a conjured item and needs the game state to know the turn.
    """
    if item.item_type == ItemType.AMULET:
        body = f"amulet, {item.skill} {item.skill_level}"
    elif item.item_type == ItemType.CRYSTAL:
        body = f"crystal, power {item.power_current}/{item.power_max}"
    elif item.item_type == ItemType.ORB:
        body = f"orb, power {item.power_current}"
    elif item.item_type == ItemType.RING:
        body = f"ring, prot {item.protection}"
    else:
        body = (f"wand, {item.spell} {item.power_current}/{item.power_max}, "
                f"skill {item.skill_level}")

    if item.is_temporary and game_state is not None:
        turns_left = max(0, item.expires_turn - game_state.turn_number)
        body += f", {turns_left * config.DAYS_PER_TURN}d"
    return f"{item.name} [{body}]"


# ============================================================================
# UPKEEP: REGENERATION AND EXPIRY
# ============================================================================

def _in_magic_free_zone(item: MagicalItem, game_state: GameState) -> bool:
    """Whether this item is being carried somewhere magic cannot exist."""
    holder = game_state.characters.get(item.holder_character_id)
    if not holder:
        return False
    city = game_state.world_map.cities.get(holder.location_city_id)
    return bool(city and city.is_magic_free)


def regenerate(game_state: GameState) -> None:
    """
    Restore item power for one turn's worth of days.

    rules.md gives orbs and wands "one point per day" automatically. A crystal
    is different: it only gains a point on a day its possessor is already at
    his natural maximum, so the overflow that the possessor cannot use goes
    into the crystal instead. Held crystals therefore charge only for a
    possessor at full power, and an unheld one does not charge at all.
    """
    days = config.DAYS_PER_TURN
    for item in game_state.magical_items.values():
        if _in_magic_free_zone(item, game_state):
            # Power does not exist here, so there is nothing to regenerate.
            continue
        if item.item_type in (ItemType.ORB, ItemType.WAND):
            gain = days
            if item.item_type == ItemType.ORB:
                item.power_current += gain  # no ceiling
            else:
                item.power_current = min(item.power_max,
                                         item.power_current + gain)
        elif item.item_type == ItemType.CRYSTAL:
            holder = game_state.characters.get(item.holder_character_id)
            if not holder or holder.is_dead:
                continue
            if holder.magic_skill < 1:
                # "The possessor must have a magic skill level of at least 1
                # to be able to charge a crystal."
                continue
            if holder.magic_power_current >= holder.max_magic_power:
                item.power_current = min(item.power_max,
                                         item.power_current + days)


def expire(game_state: GameState) -> list[tuple[MagicalItem, str]]:
    """
    Remove conjured items whose time is up.

    Returns (item, holder_faction_id) for each, so the caller can tell the
    player: "You will be notified when a magical item disappears." Found items
    are indestructible and are never touched here.
    """
    gone = []
    for item_id, item in list(game_state.magical_items.items()):
        if not item.is_temporary or item.expires_turn > game_state.turn_number:
            continue
        holder = game_state.characters.get(item.holder_character_id)
        gone.append((item, holder.faction_id if holder else ""))
        del game_state.magical_items[item_id]
    return gone


def drain_magic_free_zone(character: Character, game_state: GameState) -> bool:
    """
    Empty a character's power, and their items', on entering a magic-free zone.

    rules.md: in such a location magical power does not exist "either in people
    or in magical items". Returns True if anything was actually drained.
    """
    drained = character.magic_power_current > 0
    character.magic_power_current = 0
    for item in items_held_by(character.id, game_state):
        if item.holds_power and item.power_current > 0:
            item.power_current = 0
            drained = True
    return drained
