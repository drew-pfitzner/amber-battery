# Sentinel — Optimisation & Simplification Plan
_Drafted 2026-07-27. Companion to `CONTROL_LOGIC.md` (current behaviour) and
`CLAUDE.md` (architecture). This is the target design; nothing here is built yet._

## 1. Goals (from owner)

A battery manager that **runs itself with zero input**, and:

1. Works **regardless of weather** — sunny or cloudy.
2. Works **regardless of price** — cheap or expensive grid.
3. **Maximises solar self-consumption** — every generated kWh goes to loads or
   the battery before any export.
4. Covers **both daily price peaks** (morning & evening) from the battery, using
   the cheapest energy available to get there.
5. **Fewer knobs.** The current ~25-item Controls panel is overwhelming.

## 2. The single guiding principle

> **Keep the battery charged from the cheapest available energy to cover the next
> price peak — but never so full that the day's forecast solar has nowhere to go.**

Every mode below is just an expression of this. It replaces MORNING_FLOOR,
SPIKE_EXPORT, and the entire adaptive-target settings tangle.

## 3. Target mode stack (was 8 modes → now 6)

| Pri | Mode | Role |
|---|---|---|
| 1 | **FAILSAFE** | unchanged — safety |
| 2 | **OUTAGE_PREP** | unchanged — kept, stays visible |
| 3 | **GRID_CHARGE** | **redesigned** — unified two-peak charger (§4) |
| 4 | **REBALANCE** | unchanged — keeps the two packs even |
| 5 | **SOLAR_CURTAIL** | unchanged — no export at bad feed-in |
| 6 | **SELF_CONSUMPTION** | unchanged — always-on fallback |

**Deleted:** SPIKE_EXPORT (no capacity headroom to exploit spikes yet) and
MORNING_FLOOR (its job is now just GRID_CHARGE's morning target, done properly).

## 4. GRID_CHARGE, redesigned: "charge for the next peak"

At any time there is exactly one *next peak* to prepare for. GRID_CHARGE detects
it, picks a seasonal target, and charges to it — from solar first, cheap grid
second — completing **before the peak-price period begins.**

### 4a. Deadline = the price jump, detected (not a clock)

Instead of hardcoded `06:00` / `16:00` deadlines:

- Each cycle, read the Amber price **forecast** (already fetched + 15-min cached).
- Find the **onset of the next peak-price period**: the start of the next run of
  intervals whose `per_kwh` steps above a baseline (baseline = ~30th-percentile
  of the next-24 h prices; onset = first interval ≥ `baseline × peak_factor`,
  default 1.4). Amber's per-interval `descriptor` (`high`/`spike`) is used as a
  cross-check.
- **Morning peak onset** = first such run in the 04:00–11:00 band → the overnight
  charge deadline.
- **Evening peak onset** = first such run in the 13:00–21:00 band → the daytime
  charge deadline.
- **Fallbacks** if no clear peak is found: 06:00 (morning) / 16:00 (evening).
- This is why "4 PM" auto-pushes later in summer: the deadline follows the actual
  tariff jump, which the forecast already knows about. Exposed as read-only
  sensors `next_morning_peak` / `next_evening_peak` for visibility.

Charge **windows** (when charging is *allowed*) stay simple in v1: overnight opens
22:00, daytime opens 09:00; each closes at its detected peak onset. (Fully
peak-boundary-driven windows are a possible later refinement.)

### 4b. Target = learned & seasonal (not a fixed %)

Both targets come from **your own consumption history** (§5), so they self-tune
across the seasons with no manual input:

- **Morning target (overnight):**
  `target = clamp(ceiling − solar_surplus_soc, morning_floor, ceiling)`
  - `morning_floor` = learned morning-peak energy as SOC → **guarantees the
    morning peak is covered from battery.**
  - `solar_surplus_soc` = `max(0, Solcast_tomorrow − learned_daytime_load)` as
    SOC → in summer this pulls the target down so daytime solar fills the pack
    for free; in winter it's ~0 so the pack charges to the ceiling overnight.
- **Evening target (daytime):**
  `target = clamp(learned_evening_peak_energy / capacity, min_reserve, max_charge)`
  - Naturally seasonal: dark winter evenings learn a bigger load → higher target;
    lighter summer evenings → lower. Solar fills it first; cheap grid tops up the
    remainder before the detected evening peak onset.

`min_reserve` (floor) and `max_charge` (ceiling, protects solar headroom &
battery health) are the only two SOC knobs left, and rarely touched.

### 4c. Force logic (unchanged in spirit)

If, approaching a deadline, there isn't enough cheap time left to reach target
(`hours_remaining < required × 1.5`), charge immediately. Otherwise charge only
in the cheapest contiguous block before the deadline. Guarantees target-by-peak.

## 5. Learning engine (new — this is what makes it hands-off)

The coordinator already reads the plant load sensors every 30 s. Add a light
rolling-average learner:

- Accumulate energy consumed in three daily windows: **morning peak**,
  **evening peak**, and **daytime** (solar hours).
- Maintain a **trailing 14-day average** per window, persisted across restarts
  (RestoreEntity / stored state — no heavy recorder queries).
- Degrade gracefully: until enough history exists, fall back to conservative
  seeded defaults (today's manual numbers as seeds).
- Expose as read-only sensors: `learned_morning_load`, `learned_evening_load`,
  `learned_daytime_load`, plus `effective_overnight_target` /
  `effective_evening_target` so you can *see* what it's deciding.

This replaces the manual **Expected Daytime Load** number and the fixed
target/adaptive numbers entirely.

## 6. Settings: before → after

**Deleted entities:** Enable Spike Export · Enable Morning Floor · Morning Floor
SOC · Grid Charge Adaptive Target (toggle) · Grid Charge Overnight Cap (fixed) ·
Grid Charge Solar Low/High Threshold · Grid Charge Target Poor/Strong Solar ·
Grid Charge Deadline Hour · Expected Daytime Load. *(~13 removed.)*

**Final Controls panel (~9 items):**

- Switches: **Enable Grid Charging · Enable Rebalancing · Enable Solar Curtail ·
  Enable Outage Prep**
- Numbers: **Grid Charge Rate (kW) · Min Reserve % · Max Charge % · Outage
  Target %** · Date: **Outage Date**

**New read-only sensors (visibility, not controls):** active mode, mean SOC,
learned morning/evening/daytime load, effective overnight & evening targets,
next morning & evening peak times.

Advanced/hidden (disabled by default, still reachable): peak-detection factor,
learning-window days, rebalance transfer rate, grid-charge hysteresis.

## 7. How each goal is met

- **Any weather** — targets scale with the Solcast forecast + learned load.
- **Any price** — all charging picks cheapest Amber intervals; deadline is the
  real price jump.
- **Max solar self-consumption** — the adaptive overnight floor never fills the
  pack past what leaves room for forecast solar; Max Self Consumption routes
  solar→load→battery; Solar Curtail blocks export only when feed-in is worthless.
  Result: generated kWh land in loads/battery, not exported cheap.
- **Both peaks covered** — one charger, two learned targets, each timed to its
  detected peak.
- **Fewer knobs** — 25 → 9, and the survivors are set-once hardware/safety values.

## 8. Rollout

- **`.82` restart risk is resolved** (battery firmware update) — full HA restarts
  for `.py` deploys are now safe; update `ISSUES.md #3` to CLOSED on ship.
- Build behind the existing structure; keep each deleted mode's removal isolated
  and reviewable. Deploy via the Samba `config` share, clear `__pycache__`,
  restart. Commit to the `amber-battery` repo.
- Suggested order: (1) delete SPIKE_EXPORT + MORNING_FLOOR; (2) peak-onset
  detection + dynamic deadlines; (3) learning engine + learned targets;
  (4) prune/rename entities; (5) new visibility sensors.

## 9. Defaults to confirm

`peak_factor` 1.4 · learning window 14 days · `min_reserve` 20% · `max_charge`
90% · morning band 04:00–11:00 · evening band 13:00–21:00 · fallback deadlines
06:00 / 16:00.
