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
* Each level has 32 bars; the player advances by pressing Enter.

Archipelago model
-----------------
Locations : Collecting each of the 32 bars across up to N levels (configurable, default 10)
            = bar locations, plus one completion check per level. Total varies with num_levels.
Items     : Physics upgrades (retract speed, decay reduction, impact reduction),
            score bonuses, and traps (gravity spike, decay spike, grapple disconnect).
Goals     : One of four configurable goal types (see GoalType option).
"""

from dataclasses import dataclass
from typing import Dict, Any, List

from BaseClasses import Region, Location, Item, ItemClassification, Tutorial
from worlds.AutoWorld import World, WebWorld
from Options import PerGameCommonOptions, Choice, Range


# ── Base IDs ────────────────────────────────────────────────────────────────
BASE_ID = 45_000_000

# Maximum number of levels supported (used to size the static location ID table)
MAX_LEVELS     = 30
NUM_LEVELS     = 10  # default; actual value comes from options at generation time
BARS_PER_LEVEL = 32
LEVEL_COMPLETE_OFFSET = 10_000  # completion IDs: BASE_ID + 10_000 + levelIndex

# These reflect the maximum possible counts for the static location registry
_MAX_BAR_LOCATIONS        = MAX_LEVELS * BARS_PER_LEVEL   # 960
_MAX_COMPLETION_LOCATIONS = MAX_LEVELS                    # 30
_MAX_LOCATIONS            = _MAX_BAR_LOCATIONS + _MAX_COMPLETION_LOCATIONS  # 990

# Goal type constants — must stay in sync with GoalType in C# LocationManager
GOAL_LEVELS_COMPLETED = 0
GOAL_SCORE            = 1
GOAL_BARS_COLLECTED   = 2
GOAL_ALL_LOCATIONS    = 3

# Level complete condition constants — must stay in sync with LevelCompleteCondition in C#
LEVEL_COMPLETE_ALL_BARS   = 0
LEVEL_COMPLETE_PRESS_ENTER = 1

# Water access — bars 24-31 (0-based) per level are gated behind Water Access
WATER_GATED_BAR_START = 24   # first bar index (0-based) that requires Water Access


# ── Options ──────────────────────────────────────────────────────────────────
class GoalType(Choice):
    """
    What you need to do to complete your goal.

    levels_completed: Complete a set number of levels (press Enter to advance,
                      collecting all bars on the level). Default and recommended.
    score:            Accumulate a target total score across all levels.
    bars_collected:   Collect a set total number of bars across all levels.
    all_locations:    Collect every bar check available in the multiworld (320 total).
    """
    display_name = "Goal Type"
    option_levels_completed = GOAL_LEVELS_COMPLETED
    option_score            = GOAL_SCORE
    option_bars_collected   = GOAL_BARS_COLLECTED
    option_all_locations    = GOAL_ALL_LOCATIONS
    default = GOAL_LEVELS_COMPLETED


class LevelsRequired(Range):
    """
    [Goal: levels_completed] Number of levels that must be fully completed.
    Must be <= num_levels. Ignored for other goal types.
    """
    display_name = "Levels Required"
    range_start = 1
    range_end = MAX_LEVELS
    default = 3


class GoalScore(Range):
    """
    [Goal: score] Total score that must be accumulated across all levels to win.
    Ignored for other goal types.
    """
    display_name = "Goal Score"
    range_start = 1000
    range_end = 100_000
    default = 10_000


class BarsRequired(Range):
    """
    [Goal: bars_collected] Total number of bars to collect across all levels.
    Must be <= num_levels * 32. Ignored for other goal types.
    """
    display_name = "Bars Required"
    range_start = 10
    range_end = _MAX_BAR_LOCATIONS
    default = 96   # 3 full levels worth


class NumLevels(Range):
    """
    How many levels to include in the multiworld.
    Each level contributes 32 bar locations and 1 level-complete location.
    Default is 10 (320 bar + 10 completion = 330 locations total).
    """
    display_name = "Number of Levels"
    range_start = 1
    range_end = MAX_LEVELS
    default = 10


class TrapPercentage(Range):
    """Percentage of filler item slots that are traps."""
    display_name = "Trap Percentage"
    range_start = 0
    range_end = 50
    default = 15


class LevelCompleteCondition(Choice):
    """
    What counts as completing a level.

    all_bars:    All 32 bars on the level must be collected. A "Level N - Complete"
                 check is sent when the last bar is picked up.
    press_enter: Pressing Enter to advance to the next level sends the completion
                 check immediately, regardless of how many bars were collected.
    """
    display_name = "Level Complete Condition"
    option_all_bars    = LEVEL_COMPLETE_ALL_BARS
    option_press_enter = LEVEL_COMPLETE_PRESS_ENTER
    default = LEVEL_COMPLETE_ALL_BARS


class WaterAccess(Choice):
    """
    Whether the Water Access item is required to go below the water surface.

    enabled:  The water surface acts as a solid floor until you receive the
              Water Access item from the multiworld. Bars 25-32 on every level
              are logically gated behind this item.
    disabled: Water behaves normally from the start — no gate, no item.
    """
    display_name = "Water Access"
    option_enabled  = 1
    option_disabled = 0
    default = 1


@dataclass
class FPOptions(PerGameCommonOptions):
    goal_type:                GoalType
    num_levels:               NumLevels
    levels_required:          LevelsRequired
    goal_score:               GoalScore
    bars_required:            BarsRequired
    trap_percentage:          TrapPercentage
    level_complete_condition: LevelCompleteCondition
    water_access:             WaterAccess


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
    # Progression (physics upgrades)
    FPItemData("Retract Speed Up",       BASE_ID + 3,  ItemClassification.progression, count=6),
    FPItemData("Retract Bonus Up",       BASE_ID + 4,  ItemClassification.progression, count=6),
    FPItemData("Bar Decay Rate Down",    BASE_ID + 5,  ItemClassification.progression, count=5),
    FPItemData("Bar Decay Factor Down",  BASE_ID + 6,  ItemClassification.progression, count=5),
    FPItemData("Impact Penalty Down",    BASE_ID + 7,  ItemClassification.useful,      count=5),
    FPItemData("Bar Threshold Down",     BASE_ID + 8,  ItemClassification.useful,      count=4),
    # Progression (level gating)
    FPItemData("Extra Level",            BASE_ID + 9,  ItemClassification.progression, count=MAX_LEVELS),
    # Progression (water gating)
    FPItemData("Water Access",           BASE_ID + 10, ItemClassification.progression, count=1),
    # Traps
    FPItemData("Gravity Spike (Trap)",        BASE_ID + 20, ItemClassification.trap, count=5),
    FPItemData("Decay Spike (Trap)",          BASE_ID + 21, ItemClassification.trap, count=5),
    FPItemData("Grapple Disconnect (Trap)",   BASE_ID + 22, ItemClassification.trap, count=5),
]

ITEM_NAME_TO_DATA: Dict[str, FPItemData] = {i.name: i for i in ITEM_TABLE}


def _build_item_name_to_id() -> Dict[str, int]:
    return {i.name: i.item_id for i in ITEM_TABLE}


# ── Locations ────────────────────────────────────────────────────────────────
def _location_name(level: int, bar: int) -> str:
    return f"Level {level + 1} - Bar {bar + 1}"


def _location_id(level: int, bar: int) -> int:
    return BASE_ID + level * BARS_PER_LEVEL + bar


def _level_complete_name(level: int) -> str:
    return f"Level {level + 1} - Complete"


def _level_complete_id(level: int) -> int:
    return BASE_ID + LEVEL_COMPLETE_OFFSET + level


LOCATION_TABLE: Dict[str, int] = {
    **{
        _location_name(lvl, bar): _location_id(lvl, bar)
        for lvl in range(MAX_LEVELS)
        for bar in range(BARS_PER_LEVEL)
    },
    **{
        _level_complete_name(lvl): _level_complete_id(lvl)
        for lvl in range(MAX_LEVELS)
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
    options: FPOptions
    web = FPWeb()

    item_name_to_id = _build_item_name_to_id()
    location_name_to_id = LOCATION_TABLE

    def create_item(self, name: str) -> FloatingPointItem:
        data = ITEM_NAME_TO_DATA[name]
        return FloatingPointItem(name, data.classification, data.item_id, self.player)

    def create_items(self) -> None:
        num_levels   = self.options.num_levels.value
        total_locs   = num_levels * BARS_PER_LEVEL + num_levels  # bars + completions
        pool: List[FloatingPointItem] = []
        trap_pct   = self.options.trap_percentage.value / 100.0
        trap_names = [i.name for i in ITEM_TABLE if i.classification == ItemClassification.trap]

        # Add fixed-count non-trap items
        for data in ITEM_TABLE:
            if data.classification == ItemClassification.trap:
                continue
            for _ in range(data.count):
                pool.append(self.create_item(data.name))

        # Pad to total_locs with traps or small bonuses
        remaining = total_locs - len(pool)
        for _ in range(remaining):
            if trap_names and self.random.random() < trap_pct:
                name = self.random.choice(trap_names)
            else:
                name = "Score Bonus (Small)"
            pool.append(self.create_item(name))

        self.multiworld.itempool += pool

    def create_regions(self) -> None:
        num_levels = self.options.num_levels.value
        menu = Region("Menu", self.player, self.multiworld)
        self.multiworld.regions.append(menu)

        prev_region = menu
        for lvl in range(num_levels):
            region = Region(f"Level {lvl + 1}", self.player, self.multiworld)
            self.multiworld.regions.append(region)

            # Bar locations
            for bar in range(BARS_PER_LEVEL):
                loc = FloatingPointLocation(
                    self.player, _location_name(lvl, bar), _location_id(lvl, bar), region
                )
                region.locations.append(loc)

            # Level completion location
            completion_loc = FloatingPointLocation(
                self.player, _level_complete_name(lvl), _level_complete_id(lvl), region
            )
            region.locations.append(completion_loc)

            if lvl == 0:
                menu.connect(region)
            else:
                prev_region.connect(
                    region,
                    rule=lambda state, l=lvl: (
                        state.has("Extra Level", self.player, l) or
                        state.has("Retract Speed Up", self.player, l * 2)
                    )
                )
            prev_region = region

    def set_rules(self) -> None:
        goal       = self.options.goal_type.value
        num_levels = self.options.num_levels.value
        # Clamp levels_required and bars_required to what's actually available
        lvl_req    = min(self.options.levels_required.value, num_levels)
        score_req  = self.options.goal_score.value
        bars_req   = min(self.options.bars_required.value, num_levels * BARS_PER_LEVEL)
        water_on   = self.options.water_access.value == 1

        # Water Access gate: bars 24-31 (0-based) on every level require Water Access
        if water_on:
            for lvl in range(num_levels):
                for bar in range(WATER_GATED_BAR_START, BARS_PER_LEVEL):
                    loc_name = _location_name(lvl, bar)
                    loc = self.multiworld.get_location(loc_name, self.player)
                    loc.access_rule = lambda state: state.has("Water Access", self.player)

        if goal == GOAL_LEVELS_COMPLETED:
            self.multiworld.completion_condition[self.player] = (
                lambda state: state.has("Extra Level", self.player, lvl_req)
            )

        elif goal == GOAL_SCORE:
            def score_rule(state) -> bool:
                received = (
                    state.count("Score Bonus (Large)",  self.player) * 5_000 +
                    state.count("Score Bonus (Medium)", self.player) * 2_000 +
                    state.count("Score Bonus (Small)",  self.player) * 500
                )
                physics_bonus = (
                    state.count("Retract Speed Up",     self.player) * 1_000 +
                    state.count("Retract Bonus Up",     self.player) * 1_000 +
                    state.count("Bar Decay Rate Down",  self.player) * 800 +
                    state.count("Bar Decay Factor Down",self.player) * 800
                )
                return (received + physics_bonus) >= score_req
            self.multiworld.completion_condition[self.player] = score_rule

        elif goal == GOAL_BARS_COLLECTED:
            levels_needed = (bars_req + BARS_PER_LEVEL - 1) // BARS_PER_LEVEL
            levels_needed = min(levels_needed, num_levels)
            self.multiworld.completion_condition[self.player] = (
                lambda state, ln=levels_needed: (
                    ln <= 1 or
                    state.has("Extra Level", self.player, ln - 1) or
                    state.has("Retract Speed Up", self.player, (ln - 1) * 2)
                )
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
            "goal_type":                self.options.goal_type.value,
            "num_levels":               num_levels,
            "levels_required":          min(self.options.levels_required.value, num_levels),
            "goal_score":               self.options.goal_score.value,
            "bars_required":            min(self.options.bars_required.value, num_levels * BARS_PER_LEVEL),
            "total_locations":          num_levels * BARS_PER_LEVEL + num_levels,
            "level_complete_condition": self.options.level_complete_condition.value,
        }
