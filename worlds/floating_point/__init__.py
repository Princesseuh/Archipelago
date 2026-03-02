"""
Floating Point — Archipelago World Definition
=============================================
Game: Floating Point (Tom Francis, 2014)
Engine: Unity 4.3 / Mono
Mod: BepInEx 5 plugin

Gameplay model
--------------
* The player swings through procedurally generated levels collecting red bars.
* Bars grow taller (worth more) the faster the player is moving.
* Each level has 32 bars; the player advances by pressing Enter freely at any time.
* Going below the water surface requires the Water Access item.

Archipelago model
-----------------
Locations (2*N + 23 total, default N=50 → 123):
  N  cumulative-bar milestones : "Total Bars - N Collected" (N = 8, 16, ..., N*8)
  N  level completion checks   : "Level Complete 1..N" — gated behind Water Access
  16 single-level best-bar     : "Best Single Level - N Bars" (N = 2, 4, ..., 32)
   6 score milestones          : "Score - 50k/100k/250k/500k/750k/1M"
   1 connected                 : "Connected to Archipelago"

Items : Physics upgrades, score bonuses, traps.
Goals : One of three configurable goal types (see GoalType option).
"""

from dataclasses import dataclass
from typing import Dict, Any, List

from BaseClasses import Region, Location, Item, ItemClassification, Tutorial
from worlds.AutoWorld import World, WebWorld
from Options import PerGameCommonOptions, Choice, Range, ItemsAccessibility


# ── Base IDs ────────────────────────────────────────────────────────────────
BASE_ID = 45_000_000

# ── Cumulative-bar milestones ────────────────────────────────────────────────
BAR_MILESTONE_STEP = 8  # thresholds: 8, 16, 24, ...

def _cumulative_bar_threshold(i: int) -> int:
    return (i + 1) * BAR_MILESTONE_STEP

def _cumulative_bar_milestone_id(i: int) -> int:
    return BASE_ID + i

def _cumulative_bar_milestone_name(i: int) -> str:
    return f"Total Bars - {_cumulative_bar_threshold(i)} Collected"

# ── Level completion locations ───────────────────────────────────────────────
LEVEL_COMPLETE_OFFSET = 10_000

def _level_complete_id(i: int) -> int:
    return BASE_ID + LEVEL_COMPLETE_OFFSET + i

def _level_complete_name(i: int) -> str:
    return f"Level Complete {i + 1}"

# ── "Connected" ─────────────────────────────────────────────────────────────
LOCATION_CONNECTED = BASE_ID + 20_000

# ── Single-level best-bar milestones ────────────────────────────────────────
# 16 entries: 2, 4, 6, ..., 32 (every 2 bars)
SINGLE_LEVEL_BAR_MILESTONES = [2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32]
BAR_MILESTONE_OFFSET        = 30_000
# Milestones with threshold strictly above this value require Water Access
WATER_GATED_BAR_START       = 24

def _single_level_milestone_id(i: int) -> int:
    return BASE_ID + BAR_MILESTONE_OFFSET + i

def _single_level_milestone_name(i: int) -> str:
    return f"Best Single Level - {SINGLE_LEVEL_BAR_MILESTONES[i]} Bars"

# ── Score milestones ─────────────────────────────────────────────────────────
SCORE_MILESTONES       = [50_000, 100_000, 250_000, 500_000, 750_000, 1_000_000]
SCORE_MILESTONE_OFFSET = 40_000

def _score_milestone_id(i: int) -> int:
    return BASE_ID + SCORE_MILESTONE_OFFSET + i

def _score_milestone_name(i: int) -> str:
    v = SCORE_MILESTONES[i]
    if v >= 1_000_000:
        label = f"{v // 1_000_000}M"
    elif v >= 1_000:
        label = f"{v // 1_000}k"
    else:
        label = str(v)
    return f"Score - {label}"

# ── Goal constants ───────────────────────────────────────────────────────────
GOAL_LEVELS_COMPLETED = 0
GOAL_BARS_COLLECTED   = 2
GOAL_ALL_LOCATIONS    = 3

# Fixed location count (doesn't depend on num_levels)
FIXED_LOCATION_COUNT = (
    1 +                              # Connected
    len(SINGLE_LEVEL_BAR_MILESTONES) +  # 16
    len(SCORE_MILESTONES)            # 4
)  # = 21

def _total_locations(num_levels: int) -> int:
    """Total location count for a given num_levels value (= 2*N + 21)."""
    return 2 * num_levels + FIXED_LOCATION_COUNT


# ── Options ──────────────────────────────────────────────────────────────────
class GoalType(Choice):
    """
    What you need to do to complete your goal.

    levels_completed: Complete a set number of levels (requires Water Access since
                      level completions are water-gated). Default and recommended.
    bars_collected:   Collect a set total number of bars across all levels.
    all_locations:    Collect every location in the multiworld.
    """
    display_name = "Goal Type"
    option_levels_completed = GOAL_LEVELS_COMPLETED
    option_bars_collected   = GOAL_BARS_COLLECTED
    option_all_locations    = GOAL_ALL_LOCATIONS
    default = GOAL_LEVELS_COMPLETED


class NumLevels(Range):
    """
    Number of levels tracked by the randomizer.
    Controls both the number of cumulative-bar milestone locations and the number of
    level-completion check locations. Total location count = 2 * num_levels + 21.
    """
    display_name = "Number of Levels"
    range_start = 1
    range_end   = 200
    default     = 50


class LevelsRequired(Range):
    """
    [Goal: levels_completed] Number of levels that must be completed to win.
    Level completions require Water Access. Must be <= num_levels.
    Ignored for other goal types.
    """
    display_name = "Levels Required"
    range_start = 1
    range_end   = 200   # Actual cap enforced in set_rules via min(value, num_levels)
    default     = 50


class BarsRequired(Range):
    """
    [Goal: bars_collected] Total number of bars to collect across all levels.
    Ignored for other goal types.
    """
    display_name = "Bars Required"
    range_start = 10
    range_end   = 6400   # 200 levels × 32 bars
    default     = 400


class TrapPercentage(Range):
    """Percentage of filler item slots that are traps."""
    display_name = "Trap Percentage"
    range_start = 0
    range_end   = 50
    default     = 22


class WaterAccess(Choice):
    """
    Whether the Water Access item is required to go below the water surface.

    enabled:  The water surface acts as a solid floor until you receive the
              Water Access item. Level completion checks and single-level
              milestones > 24 bars are gated behind this item.
    disabled: Water behaves normally from the start — no gate, no item.
    """
    display_name = "Water Access"
    option_enabled  = 1
    option_disabled = 0
    default = 1


class GrappleUnlock(Choice):
    """
    Whether the Grapple Unlock item is required before you can use the grapple.

    enabled:  The grapple is completely non-functional at the start. It is
              guaranteed to appear in sphere 1.
    disabled: The grapple works from the start.
    """
    display_name = "Grapple Unlock"
    option_enabled  = 1
    option_disabled = 0
    default = 1


class StartingRetractSpeed(Choice):
    """
    How fast the grapple retract starts before any Retract upgrades are received.

    very_slow:    retractSpeedBase=2,  retractSpeedBonus=3  (very sluggish — upgrades feel huge)
    moderate:     retractSpeedBase=8,  retractSpeedBonus=12 (halfway to vanilla)
    near_default: retractSpeedBase=13, retractSpeedBonus=22 (close to vanilla — upgrades are a small bonus)
    """
    display_name = "Starting Retract Speed"
    option_very_slow    = 0
    option_moderate     = 1
    option_near_default = 2
    default = 0


@dataclass
class FPOptions(PerGameCommonOptions):
    accessibility:          ItemsAccessibility
    goal_type:              GoalType
    num_levels:             NumLevels
    levels_required:        LevelsRequired
    bars_required:          BarsRequired
    trap_percentage:        TrapPercentage
    water_access:           WaterAccess
    grapple_unlock:         GrappleUnlock
    starting_retract_speed: StartingRetractSpeed


# ── Items ────────────────────────────────────────────────────────────────────
@dataclass
class FPItemData:
    name: str
    item_id: int
    classification: ItemClassification
    count: int = 1


ITEM_TABLE: List[FPItemData] = [
    # Filler / useful
    FPItemData("Score Bonus (Small)",    BASE_ID + 0,  ItemClassification.filler,      count=10),
    FPItemData("Score Bonus (Medium)",   BASE_ID + 1,  ItemClassification.useful,      count=5),
    FPItemData("Score Bonus (Large)",    BASE_ID + 2,  ItemClassification.useful,      count=3),
    # Physics upgrades (all start hobbled, each item upgrades toward/past default)
    # retractSpeedBase:   start=2,      step=+1.0,    count=20 → max 22  (vanilla 15)
    FPItemData("Retract Speed Up",       BASE_ID + 3,  ItemClassification.progression, count=20),
    # retractSpeedBonus:  start=3,      step=+2.0,    count=15 → max 33  (vanilla 25)
    FPItemData("Retract Bonus Up",       BASE_ID + 4,  ItemClassification.progression, count=15),
    # pointDecayRate:     start=26,     step=-0.6,    count=10 → min 20  (vanilla 20)
    FPItemData("Bar Decay Rate Down",    BASE_ID + 5,  ItemClassification.progression, count=10),
    # pointDecayFactor:   start=0.9955, step=+0.00025,count=10 → max 0.998 (vanilla 0.998)
    FPItemData("Bar Decay Factor Down",  BASE_ID + 6,  ItemClassification.progression, count=10),
    # pointImpactPenalty: start=26,     step=-0.6,    count=10 → min 20  (vanilla 20)
    FPItemData("Impact Penalty Down",    BASE_ID + 7,  ItemClassification.progression, count=10),
    # barHeightConsideredGood: start=6500, step=-500, count=8 → min 2500 (vanilla 6000)
    FPItemData("Bar Threshold Down",     BASE_ID + 8,  ItemClassification.progression, count=8),
    # Water / grapple gating
    FPItemData("Water Access",           BASE_ID + 10, ItemClassification.progression, count=1),
    # grapplePayoutSpeed: start=1,      step=+1.5,    count=10 → max 16  (vanilla ~4)
    FPItemData("Grapple Payout Speed Up", BASE_ID + 12, ItemClassification.progression, count=10),
    FPItemData("Grapple Unlock",          BASE_ID + 13, ItemClassification.progression, count=1),
    # Traps
    FPItemData("Gravity Spike (Trap)",        BASE_ID + 20, ItemClassification.trap, count=5),
    FPItemData("Decay Spike (Trap)",          BASE_ID + 21, ItemClassification.trap, count=5),
    FPItemData("Grapple Disconnect (Trap)",   BASE_ID + 22, ItemClassification.trap, count=5),
    FPItemData("Level Skip (Trap)",           BASE_ID + 11, ItemClassification.trap, count=4),
]

ITEM_NAME_TO_DATA: Dict[str, FPItemData] = {i.name: i for i in ITEM_TABLE}


def _build_item_name_to_id() -> Dict[str, int]:
    return {i.name: i.item_id for i in ITEM_TABLE}


# ── Static (game-wide) location name→id for all possible locations ───────────
# AP requires location_name_to_id to be a class-level dict covering every
# location that could ever be generated across any num_levels value (1–200).
# We register all 2*200+21 = 421 possible locations here; per-world instances
# only *add* the subset they actually use to regions.
_MAX_LEVELS = 200

LOCATION_TABLE: Dict[str, int] = {
    **{
        _cumulative_bar_milestone_name(i): _cumulative_bar_milestone_id(i)
        for i in range(_MAX_LEVELS)
    },
    **{
        _level_complete_name(i): _level_complete_id(i)
        for i in range(_MAX_LEVELS)
    },
    "Connected to Archipelago": LOCATION_CONNECTED,
    **{
        _single_level_milestone_name(i): _single_level_milestone_id(i)
        for i in range(len(SINGLE_LEVEL_BAR_MILESTONES))
    },
    **{
        _score_milestone_name(i): _score_milestone_id(i)
        for i in range(len(SCORE_MILESTONES))
    },
}


# ── AP classes ───────────────────────────────────────────────────────────────
class FloatingPointItem(Item):
    game = "Floating Point"


class FloatingPointLocation(Location):
    game = "Floating Point"


# ── Web world ─────────────────────────────────────────────────────────────────
class FPWeb(WebWorld):
    tutorials = [Tutorial(
        "Multiworld Setup Guide",
        "A guide to setting up the Floating Point Archipelago mod.",
        "English",
        "setup_en.md",
        "setup/en",
        ["archipelago"],
    )]
    theme = "ocean"


# ── World ────────────────────────────────────────────────────────────────────
class FloatingPointWorld(World):
    """
    Floating Point — a physics grappling-hook sandbox by Tom Francis.
    Swing through procedurally generated levels collecting red bars to build score.
    """

    game = "Floating Point"
    options_dataclass = FPOptions
    options: FPOptions  # type: ignore[override]
    web = FPWeb()

    item_name_to_id = _build_item_name_to_id()
    location_name_to_id = LOCATION_TABLE

    def create_item(self, name: str) -> FloatingPointItem:
        data = ITEM_NAME_TO_DATA[name]
        return FloatingPointItem(name, data.classification, data.item_id, self.player)

    def create_items(self) -> None:
        num_levels = self.options.num_levels.value
        total_locs = _total_locations(num_levels)

        trap_pct   = self.options.trap_percentage.value / 100.0
        trap_names = [i.name for i in ITEM_TABLE if i.classification == ItemClassification.trap]
        water_on   = self.options.water_access.value == 1
        grapple_on = self.options.grapple_unlock.value == 1

        excluded = set()
        if not water_on:
            excluded.add("Water Access")
        if not grapple_on:
            excluded.add("Grapple Unlock")

        # Split items into tiers so we can trim lower-priority ones when
        # total_locs is small (e.g. num_levels=10 → only 41 slots).
        progression_items: List[FloatingPointItem] = []
        useful_items: List[FloatingPointItem] = []
        filler_items: List[FloatingPointItem] = []

        for data in ITEM_TABLE:
            if data.classification == ItemClassification.trap:
                continue
            if data.name in excluded:
                continue
            target = (
                progression_items if data.classification == ItemClassification.progression
                else useful_items  if data.classification == ItemClassification.useful
                else filler_items
            )
            for _ in range(data.count):
                target.append(self.create_item(data.name))

        # Build pool: always include all progression items, then fill remaining
        # slots with useful then filler, trimming as needed.
        pool: List[FloatingPointItem] = list(progression_items)

        remaining = total_locs - len(pool)
        if remaining > 0:
            # Add useful items up to the remaining budget
            pool.extend(useful_items[:remaining])
            remaining = total_locs - len(pool)

        if remaining > 0:
            # Add filler items up to the remaining budget
            pool.extend(filler_items[:remaining])
            remaining = total_locs - len(pool)

        # Pad any remaining slots with traps or Score Bonus (Small)
        for _ in range(remaining):
            if trap_names and self.random.random() < trap_pct:
                name = self.random.choice(trap_names)
            else:
                name = "Score Bonus (Small)"
            pool.append(self.create_item(name))

        self.multiworld.itempool += pool

        # Guarantee Grapple Unlock is reachable in sphere 1 — without it the
        # player can't collect any bars at all.
        if grapple_on:
            self.multiworld.early_items[self.player]["Grapple Unlock"] = 1

    def create_regions(self) -> None:
        num_levels = self.options.num_levels.value

        menu = Region("Menu", self.player, self.multiworld)
        self.multiworld.regions.append(menu)

        # All locations live in Menu — no level-region gating.
        # Access rules are applied in set_rules().

        # Connected — always reachable
        menu.locations.append(FloatingPointLocation(
            self.player, "Connected to Archipelago", LOCATION_CONNECTED, menu
        ))

        # Cumulative-bar milestones (N of them)
        for i in range(num_levels):
            menu.locations.append(FloatingPointLocation(
                self.player, _cumulative_bar_milestone_name(i),
                _cumulative_bar_milestone_id(i), menu
            ))

        # Level completion locations (N of them)
        for i in range(num_levels):
            menu.locations.append(FloatingPointLocation(
                self.player, _level_complete_name(i),
                _level_complete_id(i), menu
            ))

        # Single-level best-bar milestones (always 16)
        for i in range(len(SINGLE_LEVEL_BAR_MILESTONES)):
            menu.locations.append(FloatingPointLocation(
                self.player, _single_level_milestone_name(i),
                _single_level_milestone_id(i), menu
            ))

        # Score milestones (always 4)
        for i in range(len(SCORE_MILESTONES)):
            menu.locations.append(FloatingPointLocation(
                self.player, _score_milestone_name(i),
                _score_milestone_id(i), menu
            ))

    def set_rules(self) -> None:
        num_levels = self.options.num_levels.value
        water_on   = self.options.water_access.value == 1
        grapple_on = self.options.grapple_unlock.value == 1

        def has_grapple(state):
            return state.has("Grapple Unlock", self.player)

        def has_water(state):
            return state.has("Water Access", self.player)

        def has_both(state):
            return has_grapple(state) and has_water(state)

        # Grapple gate: cumulative-bar, completion, and best-bar locations all
        # require the grapple (can't collect bars without it).
        # Cumulative-bar milestones also form a chain: each requires the previous,
        # so AP can't place "300 bars" before "8 bars" in the item sphere order.
        if grapple_on:
            for i in range(num_levels):
                loc = self.multiworld.get_location(_cumulative_bar_milestone_name(i), self.player)
                if i == 0:
                    loc.access_rule = has_grapple
                else:
                    prev = _cumulative_bar_milestone_name(i - 1)
                    def make_chain_rule(prev_loc):
                        def rule(state):
                            return has_grapple(state) and state.can_reach(prev_loc, "Location", self.player)
                        return rule
                    loc.access_rule = make_chain_rule(prev)

            for i in range(num_levels):
                loc = self.multiworld.get_location(_level_complete_name(i), self.player)
                if i == 0:
                    loc.access_rule = has_grapple
                else:
                    prev = _level_complete_name(i - 1)
                    def make_level_chain_grapple(prev_loc):
                        def rule(state):
                            return has_grapple(state) and state.can_reach(prev_loc, "Location", self.player)
                        return rule
                    loc.access_rule = make_level_chain_grapple(prev)

            for i in range(len(SINGLE_LEVEL_BAR_MILESTONES)):
                loc = self.multiworld.get_location(_single_level_milestone_name(i), self.player)
                loc.access_rule = has_grapple

            # Score milestones also require grapple — can't build score without it.
            # Higher score milestones additionally require total physics upgrades.
            # Thresholds scaled to match the larger upgrade pool (83 progression items).
            SCORE_UPGRADE_REQS = [0, 4, 10, 18, 26, 35]  # indexed by SCORE_MILESTONES position
            for i in range(len(SCORE_MILESTONES)):
                req = SCORE_UPGRADE_REQS[i]
                def make_score_rule(r):
                    def rule(state):
                        if not has_grapple(state):
                            return False
                        total = (
                            state.count("Retract Speed Up",      self.player) +
                            state.count("Retract Bonus Up",      self.player) +
                            state.count("Bar Decay Rate Down",   self.player) +
                            state.count("Bar Decay Factor Down", self.player) +
                            state.count("Impact Penalty Down",   self.player) +
                            state.count("Grapple Payout Speed Up", self.player)
                        )
                        return total >= r
                    return rule
                loc = self.multiworld.get_location(_score_milestone_name(i), self.player)
                loc.access_rule = make_score_rule(req)

        # Water gate: level completions always require Water Access + 2 retract upgrades.
        # Single-level milestones > WATER_GATED_BAR_START also require Water Access + 2 retract upgrades.
        # The retract requirement reflects that the water current pushes you away without enough speed.
        if water_on:
            def has_water_and_retract(state):
                retract = (state.count("Retract Speed Up", self.player) +
                           state.count("Retract Bonus Up", self.player))
                water = state.has("Water Access", self.player)
                return water and retract >= 2

            def has_all_and_retract(state):
                return has_grapple(state) and has_water_and_retract(state)

            water_rule = has_all_and_retract if grapple_on else has_water_and_retract

            for i in range(num_levels):
                loc = self.multiworld.get_location(_level_complete_name(i), self.player)
                if i == 0:
                    loc.access_rule = water_rule
                else:
                    prev = _level_complete_name(i - 1)
                    def make_level_chain_rule(prev_loc, base_rule):
                        def rule(state):
                            return base_rule(state) and state.can_reach(prev_loc, "Location", self.player)
                        return rule
                    loc.access_rule = make_level_chain_rule(prev, water_rule)

            for i, threshold in enumerate(SINGLE_LEVEL_BAR_MILESTONES):
                if threshold > WATER_GATED_BAR_START:
                    loc = self.multiworld.get_location(_single_level_milestone_name(i), self.player)
                    loc.access_rule = water_rule

        # Score milestones require physics upgrades regardless of grapple gate.
        # (The grapple gate block above already sets rules when grapple_on is True;
        #  here we handle the requirement when grapple_on is False.)
        if not grapple_on:
            # Still chain cumulative-bar milestones so AP respects ordering.
            for i in range(num_levels):
                loc = self.multiworld.get_location(_cumulative_bar_milestone_name(i), self.player)
                if i > 0:
                    prev = _cumulative_bar_milestone_name(i - 1)
                    def make_chain_rule_no_grapple(prev_loc):
                        def rule(state):
                            return state.can_reach(prev_loc, "Location", self.player)
                        return rule
                    loc.access_rule = make_chain_rule_no_grapple(prev)

            # Chain level completions too (water_on=False means no water rule was applied above).
            if not water_on:
                for i in range(1, num_levels):
                    loc = self.multiworld.get_location(_level_complete_name(i), self.player)
                    prev = _level_complete_name(i - 1)
                    def make_level_chain_no_gates(prev_loc):
                        def rule(state):
                            return state.can_reach(prev_loc, "Location", self.player)
                        return rule
                    loc.access_rule = make_level_chain_no_gates(prev)

            SCORE_UPGRADE_REQS = [0, 4, 10, 18, 26, 35]
            for i in range(len(SCORE_MILESTONES)):
                req = SCORE_UPGRADE_REQS[i]
                if req > 0:
                    def make_score_rule_no_grapple(r):
                        def rule(state):
                            total = (
                                state.count("Retract Speed Up",      self.player) +
                                state.count("Retract Bonus Up",      self.player) +
                                state.count("Bar Decay Rate Down",   self.player) +
                                state.count("Bar Decay Factor Down", self.player) +
                                state.count("Impact Penalty Down",   self.player) +
                                state.count("Grapple Payout Speed Up", self.player)
                            )
                            return total >= r
                        return rule
                    loc = self.multiworld.get_location(_score_milestone_name(i), self.player)
                    loc.access_rule = make_score_rule_no_grapple(req)

        # Goal conditions
        goal      = self.options.goal_type.value
        # Cap levels_required to the actual num_levels in case player set it higher
        lvl_req   = min(self.options.levels_required.value, num_levels)
        bars_req  = self.options.bars_required.value

        if goal == GOAL_LEVELS_COMPLETED:
            # levels_completed: the player must trigger lvl_req level-complete checks.
            # Those checks are water-gated, so reaching them logically requires Water Access.
            # We express this as: can_reach the lvl_req-th level-complete location.
            target_loc = _level_complete_name(lvl_req - 1)
            self.multiworld.completion_condition[self.player] = (
                lambda state, loc=target_loc: state.can_reach(loc, "Location", self.player)
            )

        elif goal == GOAL_BARS_COLLECTED:
            # Can reach the cumulative-bar milestone that covers bars_req bars.
            # Find the first milestone threshold >= bars_req, within num_levels.
            milestone_index = min(
                next(
                    (i for i in range(num_levels)
                     if _cumulative_bar_threshold(i) >= bars_req),
                    num_levels - 1
                ),
                num_levels - 1
            )
            target_loc = _cumulative_bar_milestone_name(milestone_index)
            self.multiworld.completion_condition[self.player] = (
                lambda state, loc=target_loc: state.can_reach(loc, "Location", self.player)
            )

        elif goal == GOAL_ALL_LOCATIONS:
            self.multiworld.completion_condition[self.player] = (
                lambda state: all(
                    state.can_reach(loc, "Location", self.player)
                    for loc in self.multiworld.get_locations(self.player)
                )
            )

    def fill_slot_data(self) -> Dict[str, Any]:
        num_levels = self.options.num_levels.value
        return {
            "goal_type":               self.options.goal_type.value,
            "num_levels":              num_levels,
            "levels_required":         min(self.options.levels_required.value, num_levels),
            "bars_required":           self.options.bars_required.value,
            "total_locations":         _total_locations(num_levels),
            "water_access_required":   self.options.water_access.value,
            "grapple_unlock_required": self.options.grapple_unlock.value,
            "starting_retract_speed":  self.options.starting_retract_speed.value,
        }
