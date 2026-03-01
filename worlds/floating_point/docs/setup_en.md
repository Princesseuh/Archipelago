# Floating Point — Archipelago Multiworld Setup Guide

## Requirements

- [Floating Point](https://store.steampowered.com/app/302380/Floating_Point/) on Steam
- [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases/latest) installed
- The `FloatingPointArchipelago` BepInEx plugin (included in this release)

## Installing the BepInEx Plugin

1. In your Steam library, right-click **Floating Point** → **Manage** → **Browse local files**.
2. The game folder should already contain a `BepInEx/` directory if you are using the provided release.  
   If not, copy the `BepInEx/` folder and `winhttp.dll` from the release into the game folder.
3. Copy `BepInEx/plugins/FloatingPointArchipelago/` from the release into your game's `BepInEx/plugins/` folder.

## Running the Game

1. Launch Floating Point through Steam as normal (Proton handles the Windows executable on Linux).
2. BepInEx will inject automatically on first launch. A `BepInEx/LogOutput.log` file will appear.
3. Press **F1** in-game to open the Archipelago connection panel.

## Connecting to Archipelago

Fill in the connection panel (**F1**):

| Field     | Value                                              |
|-----------|----------------------------------------------------|
| Host:port | `archipelago.gg:38281` (or your server's address) |
| Slot name | Your player name from the YAML                    |
| Password  | Leave blank unless the room has a password        |

Click **Connect**. A green `[AP]` indicator will appear in the top-right corner when connected.

## YAML Options

```yaml
game: Floating Point
name: YourName

Floating Point:
  goal_type: levels_completed       # See Goal Types below
  num_levels: 10                    # 1–30: how many levels to include
  levels_required: 3                # [goal_type: levels_completed] must be <= num_levels
  goal_score: 10000                 # [goal_type: score] target score
  bars_required: 96                 # [goal_type: bars_collected] total bars
  trap_percentage: 15               # 0–50: % of filler slots that are traps
  level_complete_condition: all_bars  # all_bars or press_enter (see below)
  water_access: enabled             # enabled or disabled (see below)
  level_skip: enabled               # enabled or disabled (see below)
```

## Goal Types

| `goal_type`        | Description                                                              |
|--------------------|--------------------------------------------------------------------------|
| `levels_completed` | Fully complete `levels_required` levels (collect all bars, press Enter). |
| `score`            | Accumulate at least `goal_score` total points across all levels.         |
| `bars_collected`   | Collect `bars_required` total bars across all levels.                    |
| `all_locations`    | Collect every bar check across all `num_levels` levels.                  |

The default goal is **`levels_completed`** with 3 levels required.

## Locations

The number of locations depends on the `num_levels` option (default 10):
- **Bar locations** — 32 bars × `num_levels`. A bar is checked the moment you collect it.
- **Level completion locations** — one per level (`Level N - Complete`), sent when the level is finished.

With the default `num_levels: 10` this gives **330 locations** (320 bar + 10 completion).
With `num_levels: 30` (maximum) this gives **990 locations** (960 bar + 30 completion).

### Level Complete Condition

| `level_complete_condition` | When "Level N - Complete" is sent |
|----------------------------|------------------------------------|
| `all_bars` (default)       | When the last of the 32 bars on that level is collected |
| `press_enter`              | The moment Enter is pressed to advance to the next level (even if no bars were collected) |

## Items

| Item                    | Effect                                      |
|-------------------------|---------------------------------------------|
| Retract Speed Up        | +5 grapple retract speed                   |
| Retract Bonus Up        | +5 retract speed bonus (at low multiplier) |
| Bar Decay Rate Down     | Bars shrink more slowly (flat rate)        |
| Bar Decay Factor Down   | Bars shrink more slowly (percentage)       |
| Impact Penalty Down     | Less score lost when bumping into things   |
| Bar Threshold Down      | Music/lights activate sooner               |
| Score Bonus (Small)     | +500 score                                 |
| Score Bonus (Medium)    | +2000 score                                |
| Score Bonus (Large)     | +5000 score                                |
| Extra Level             | Counts as 1 completed level toward goal   |
| Water Access            | Unlocks going below the water surface (see below) |
| Level Skip              | Lets you advance to the next level without completing it (see below) |
| Gravity Spike (Trap)    | Sudden downward impulse                    |
| Decay Spike (Trap)      | +10 decay rate for 10 seconds              |
| Grapple Disconnect (Trap)| Force-releases your grapple              |

## Water Access

When `water_access: enabled` (the default), the water surface at y=0 acts as a **solid floor** until you receive the **Water Access** item from the multiworld. While locked:

- You cannot go below the water surface — you bounce off it as if it were solid ground.
- Bars 25–32 on each level are logically gated behind Water Access, making them unreachable until unlocked.

Once you receive Water Access, the water returns to its normal buoyant behaviour and those bars become reachable.

Set `water_access: disabled` to skip the gate entirely — water behaves normally from the start and no Water Access item is added to the pool.

## Level Skip

When `level_skip: enabled` (the default), pressing **Enter** to advance to the next level is **gated**: you can only advance if the level is considered complete OR you spend a **Level Skip** item from your received stock.

- When locked and out of skips, pressing Enter does nothing. The HUD shows your current skip count (`skips:N`).
- Level Skip items are added to the multiworld pool (one per level on average).
- Using a skip consumes one from your stock permanently.

Set `level_skip: disabled` to remove the Enter gate entirely — you can advance at any time without needing a skip, and no Level Skip items are added to the pool.

## Goal

Your goal depends on the `goal_type` option set in your YAML. See the **Goal Types** section above.  
Received physics upgrades persist for the whole session.
