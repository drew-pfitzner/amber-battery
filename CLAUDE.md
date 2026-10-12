# Sentinel — Home Battery Energy Manager

## System Setup

- 2 Sigen batteries (24.5 kWh each, 49 kWh total), each with smart gateway
- 2 separate phases, split-phase 240V, both feed a **single power meter**
- Retailer: **Amber Electric** / Distributor: **Essential Energy** (regional NSW)
- Inverters: **12 kW** each; practical max charge rate **~10 kW** per battery

## Net Metering

Both phases feed one meter — meter sees **net** of both phases. During rebalancing (Battery A exports, Battery B imports at equal rates), meter net ≈ 0, so no Amber charge. Only cost is round-trip efficiency loss.

**Verification pending:** Contact Metering Coordinator (from Amber bill, not Essential directly) to confirm net metering across phases.

## Home Assistant Integration

### Sigen Entity Names

| Purpose | Plant 1 | Plant 2 |
|---|---|---|
| SOC | `sensor.sigen_plant_battery_state_of_charge` | `sensor.sigen_plant_2_battery_state_of_charge` |
| Mode select | `select.sigen_plant_remote_ems_control_mode` | `select.sigen_plant_2_remote_ems_control_mode` |
| HA control switch | `switch.sigen_plant_remote_ems_controlled_by_home_assistant` | `switch.sigen_plant_2_remote_ems_controlled_by_home_assistant` |
| Grid export limit | `number.sigen_plant_grid_export_limitation` | `number.sigen_plant_2_grid_export_limitation` |
| Grid import limit | `number.sigen_plant_grid_import_limitation` | `number.sigen_plant_2_grid_import_limitation` |
| ESS backup SOC | `number.sigen_plant_ess_backup_state_of_charge` | `number.sigen_plant_2_ess_backup_state_of_charge` |
| Grid export power | `sensor.sigen_plant_grid_export_power` | `sensor.sigen_plant_2_grid_export_power` |
| Grid import power | `sensor.sigen_plant_grid_import_power` | `sensor.sigen_plant_2_grid_import_power` |
| Load power | `sensor.sigen_plant_load_power` | `sensor.sigen_plant_2_load_power` |
| Grid active power | `sensor.sigen_plant_grid_active_power` | `sensor.sigen_plant_2_grid_active_power` |
| Battery power | `sensor.sigen_plant_battery_power` | `sensor.sigen_plant_2_battery_power` |
| Grid connection | `sensor.sigen_plant_grid_connection_status` | `sensor.sigen_plant_2_grid_connection_status` |

### Mode Options (select entities)

- `Maximum Self Consumption` ← normal/restore state
- `Command Charging (PV First)` ← rebalancing charge (prioritises solar)
- `Command Discharging (PV First)` ← rebalancing discharge (prioritises solar)
- `Command Charging (Grid First)` / `Command Discharging (ESS First)` / `Standby` / `PCS Remote Control`

## Sentinel Architecture

Custom HA integration: **7-mode** priority stack evaluated every 30 seconds. First
mode whose trigger is true wins and is the only one to write controls that cycle.

> Redesigned July 2026 (`OPTIMISATION_PLAN.md`, branch
> `feature/self-running-optimisation`). SPIKE_EXPORT and MORNING_FLOOR were
> **removed**; GRID_CHARGE became a single self-tuning two-peak charger. See
> `CONTROL_LOGIC.md` for the full decision tree.

| Priority | Mode | Trigger |
|---|---|---|
| 1 | **FAILSAFE** | Any Sigen critical entity unavailable ≥2 polls OR HA switch off → Maximum Self Consumption + 12/12 limits |
| 1½ | **SPIKE_MISSION** | `input_boolean.spike_mission_active` on → Sentinel **yields** (writes nothing); the HA automation `automation.spike_mission_controller` flies the export from the Spike Control dashboard |
| 2 | **OUTAGE_PREP** | Registered outage within prep window → charge to target SOC |
| 3 | **GRID_CHARGE** | Two-peak charger: detects the next **price-peak onset** from the Amber forecast and charges to a **learned** seasonal target (evening) / adaptive overnight cap (morning) in the cheapest window before it; forces if time-pressed |
| 4 | **MORNING_EXPORT** | Morning window + Amber feed-in ≥ min price + SOC above the learned sell-down floor → Command Discharging (PV First), export capped at the configured rate |
| 5 | **REBALANCE** | SOC diff > threshold → discharge higher, charge lower at matched rate |
| 6 | **SOLAR_CURTAIL** | Amber feed-in price < threshold (default $0.01) + solar producing → export limit 0 kW |
| 7 | **SELF_CONSUMPTION** | Always valid → Maximum Self Consumption |

### Key Design Decisions

- All mode switches default **OFF** for safety — user must enable each mode
- **Write pacing:** every Modbus-backed write routes through `_paced_service_call`
  — consecutive writes are ≥`WRITE_MIN_GAP_SECONDS` (0.4 s) apart and awaited to
  completion, so a multi-control mode change trickles out one command at a time
  instead of flooding a single-connection Sigen dongle. No-op writes (already at
  value) and offline-plant writes are still skipped, so steady state = 0 writes.
- Failsafe always restores batteries to Maximum Self Consumption + 12 kW limits;
  debounced by `FAILSAFE_DEBOUNCE_POLLS` (2) so a single missed poll holds mode
- **GRID_CHARGE targets are learned, not set:** a `LoadLearner` (`learning.py`)
  integrates combined load each cycle into morning/daytime/evening windows and
  keeps a trailing 14-day average (persisted via Store). Evening target = learned
  evening-peak load as SOC; overnight floor = learned morning-peak load; overnight
  cap = `max_charge` − exportable solar surplus (coming-day Solcast − learned
  daytime load). The "coming day" is the one that dawns *after* the overnight
  charge (`_overnight_solar_kwh`): tomorrow's Solcast before midnight, today's
  from midnight onward (the window straddles midnight), keyed off the morning-peak
  onset date. Clamped to `[min_reserve, max_charge]`. Seeds until 1 day learned.
  **Learned load sits on top of the ESS backup reserve:** `_compute_grid_charge_target`
  and the overnight floor add `_backup_reserve_soc()` (mean of the two
  `ess_backup_state_of_charge` numbers, currently 10%) to the kWh-derived SOC —
  the pack won't discharge below the reserve, so without the offset the target
  floored out mid-peak leaving ~reserve% of the load bought at peak (fixed
  2026-07-28). E.g. evening 32 kWh → 65% + 10% = 75% target, not 65%.
- **GRID_CHARGE gives itself a buffer, and holds the target once reached**
  (added 2026-08-09 after the pack met the morning peak at 86.5% vs a 90%
  target). Three parts: (1) `required_hours` is booked with a
  `GRID_CHARGE_TIME_MARGIN` (1.3) of slack; (2) the charge rate used to size it
  is the *lower* of modelled (`rate + PV − load`) and **measured**
  (`_observed_charge_kw`, an EMA of ΔSOC/Δt while charging) — the plant modelled
  16 kW but actually took 10.8 kW, so the window was booked at half the time it
  needed; (3) reaching target **latches a hold to the deadline** instead of
  ending the charge, topping the pack back up whenever it sags 1% below target,
  so it enters the peak at target rather than coasting down on house load. The
  forced-charge path latches too — without it the trigger ratio flickered as SOC
  climbed and chattered the mode ~40 times overnight. See `CONTROL_LOGIC.md §4d–4e`.
- **GRID_CHARGE deadline is the price jump, detected:** `_detect_peak_onset`
  finds the start of the next sustained peak run (price ≥ baseline×`PEAK_DETECT_FACTOR`
  or Amber high/spike) within a morning/evening band; the charge window closes
  there, so the "be charged by" time tracks the tariff's seasonal shift. Falls
  back to fixed hours (06:00 / 16:00) with no forecast.
- **MORNING_EXPORT sells the morning surplus without losing the morning cover**
  (added 2026-09-03). Mornings were ending with energy still in the pack while
  midday feed-in went *negative* — the day's solar had nowhere to go. The mode
  discharges to grid while the morning feed-in price is high, down to a floor
  that is the **higher** of: (1) the ESS reserve plus the *learned* morning load
  still ahead of us (pro-rated across the 06–09 band as the morning burns off,
  never below current live load held flat to takeover, × a 1.2 margin) — this is
  the "never import at the morning peak" guarantee; and (2) the evening target
  minus what today's Solcast can refill (`solcast_today − learned daytime load`),
  so we never sell energy the sun can't put back. Both clamped up to
  `grid_charge_min_reserve_soc`. **No Solcast → assume no refill**, so the floor
  is the whole evening target and the mode effectively won't fire. Blocked while
  GRID_CHARGE/OUTAGE_PREP is active *or still holding a latch* — between top-ups
  the hold reads inactive, and without that guard it would sell off the charge
  bought for the morning peak. See `CONTROL_LOGIC.md §4b`.
- Rebalance uses hysteresis: start threshold (default **10%**) vs stop (3%); PV
  First modes for both legs; requires grid connection on both plants; suppressed
  while GRID_CHARGE/OUTAGE_PREP active
- Solar curtail sets export limit to 0 kW when Amber feed-in price < threshold
- Daily energy sensors use signed `grid_active_power` (net across both phases), NOT per-plant `grid_import_power`/`grid_export_power` which double-count during rebalancing
- Battery sensors use `battery_power` from both plants (already in kW); Sigen sign convention is positive = charging, negative = discharging — coordinator negates so `net_battery_power` follows positive = discharging
- **NEVER touch** `switch.sigen_plant_plant_power` or `switch.sigen_plant_2_plant_power` — these control whether plants output power at all

### LoadLearner (learning.py)

Learns per-window daily consumption (morning peak 06–09, daytime 09–16, evening
peak 16–22) as a trailing 14-day average, integrated from the combined load
reading each cycle and persisted with a Store (`sentinel_learning_<entry_id>`).
GRID_CHARGE targets self-tune from it; seeds (`DEFAULT_SEED_*_KWH`, 20/45/40 kWh)
reproduce the old fixed-target behaviour until a full day is learned. Exposed via
read-only `sensor.…learned_{morning,daytime,evening}_load` and `…learning_days`.

- **Rollover records only observed days:** a day is appended to history only if
  `_day_had_data` (real integration happened that day). Stops a stale store from
  stamping a phantom ~0 kWh day on the first post-deploy cycle — which would
  override the seeds and read `0.0` with `learning_days=1` (seen 2026-07-28).
- **Backfill service** `sentinel.backfill_learning` (`async_backfill`): integrates
  the last 14 days of recorder history for the two `consumed_power` sensors into
  the windows and overwrites the trailing history, so learning is useful
  immediately instead of after a fortnight. Auto-scales W→kW from the sensor unit;
  caps per-sample gaps at `MAX_GAP_SECONDS`. Run once after deploy.

### Services (Phase 5)

- `sentinel.add_outage` / `sentinel.remove_outage` / `sentinel.list_outages`

### Data Sources

- **Amber forecasts:** via action `amberelectric.get_forecasts`
  (**`config_entry_id`** = the Amber config **entry_id**, e.g.
  `01KPPRS5QNSK0G17RXTHKMVBMW` for "Hill End"; `channel_type="general"`). The
  field was previously `config_entry` taking the site *title* — passing the old
  key fails schema validation and silently kills all price-aware charging
  (`ISSUES.md #5`). Sentinel tries the new key and falls back to the old one. Returns 5-min intervals with `per_kwh` (dollars), `spot_per_kwh`, `spike_status`, `descriptor`, `start_time` (UTC), `nem_date` (AEST). Called with `return_response=True`.
- **Amber sensors:** `sensor.<site>_general_price`, `sensor.<site>_feed_in_price`, `binary_sensor.<site>_price_spike`
- **Solcast:** `sensor.solcast_pv_solar_forecast_today`, `sensor.solcast_pv_solar_forecast_tomorrow`
- **Sigen load:** `sensor.sigen_plant_consumed_power`, `sensor.sigen_plant_2_consumed_power` (hardcoded, not configurable)
- **Sigen PV:** `sensor.sigen_plant_pv_power`, `sensor.sigen_plant_2_pv_power` (hardcoded, not configurable)

## Build Status

### Self-Running Optimisation — Stages 1–4 (BUILT, NOT DEPLOYED — 2026-07-27)
Branch `feature/self-running-optimisation`; design in `OPTIMISATION_PLAN.md`.
Supersedes the SPIKE_EXPORT, MORNING_FLOOR, and solar-adaptive/two-phase
GRID_CHARGE work in the phase logs below.
- [x] **Stage 1** — write pacing (`_paced_service_call`); delete SPIKE_EXPORT +
  MORNING_FLOOR (modes, switches, morning-floor SOC number + binary sensor).
- [x] **Stage 2** — GRID_CHARGE deadline = detected next price-peak onset
  (`_detect_peak_onset` / `_resolve_charge_phase`), replacing fixed 06:00/16:00.
- [x] **Stage 3** — `LoadLearner`; GRID_CHARGE targets learned & seasonal; two
  survivor SOC knobs (`grid_charge_min_reserve_soc` 20%, `grid_charge_max_soc`
  90%); visibility sensors (learned loads, effective targets, next peak times).
- [x] **Stage 4** — prune inert entities. Panel now: **switches** Grid Charging /
  Rebalancing / Solar Curtail / Outage Prep; **numbers** Grid Charge Rate / Min
  Reserve / Max SOC / Outage Target (+ Outage Date). Advanced knobs
  (hysteresis, curtail price, rebalance thresholds/rate) disabled by default.
- [x] Logic validated offline (peak detection, learning integration, seasonal
  targets); all modules compile.
- [ ] **Deploy & test:** Samba-copy `custom_components/sentinel/`, clear
  `__pycache__`, restart HA. Removed old entities orphan (unavailable) until
  deleted. Learner runs on seeds ~1–2 weeks before it fully self-tunes.

### SPIKE_MISSION — 2026-10-12 (DEPLOYED)
Manual price-spike export is flown by an HA automation from the `/spike-control`
dashboard (levers: sell-down floor = mean SOC, total rate, rebalance %, min feed-in,
window end). Starting one used to mean disabling Sentinel's config entry by hand.
- [x] `MODE_SPIKE_MISSION`: while `input_boolean.spike_mission_active` is on,
  Sentinel enters it right after the FAILSAFE check and writes nothing; leaving it
  restores 12 kW limits and the normal stack resumes. FAILSAFE still outranks it.
- [x] State-change listener on the toggle → immediate refresh, so no 30 s overlap.
- [x] The controller's own hand-back (Max Self Consumption + 12 kW) now runs only
  if Sentinel's active-mode sensor is unavailable.
- [x] Deployed 16:08 (Samba copy of `__init__.py`/`const.py`/`coordinator.py`, live
  files verified identical to `7e3dc87` first, pycache cleared, HA restart).
  Live test: toggle on → SPIKE_MISSION in <5 s, plants untouched; off → back in <5 s.
- Controller + dashboard source: `../power/spike_control/`. Per-plant export
  ceiling is ~7 kW (installer/DNSP setting, not visible in HA).

### MORNING_EXPORT — 2026-09-03 (DEPLOYED, awaiting first live morning)
New priority-4 mode. Mornings were finishing with charge still in the pack while
the day's feed-in went negative, so excess solar had nowhere to go.
- [x] `MODE_MORNING_EXPORT` + `switch.sentinel_morning_export_enabled` (default OFF)
- [x] `_compute_morning_export_floor` — max(morning cover, evening refill,
  min reserve); `_morning_cover_kwh` pro-rates the learned morning load across the
  remaining 06–09 band and floors at live load × hours-to-takeover
- [x] `_check_morning_export_conditions` — window/price/on-grid/floor gating, 3%
  restart band, blocked by GRID_CHARGE latches as well as active charging
- [x] `_async_apply_morning_export` — Command Discharging (PV First), export split
  biased to the higher-SOC pack, import left at 12 kW; restore-on-exit wired up
- [x] Numbers `morning_export_min_price` ($0.15) / `morning_export_rate_kw` (10 kW)
  / `morning_export_takeover_hour` (09, advanced); `sensor.…morning_export_floor_soc`;
  `binary_sensor.…morning_export_active`
- [x] Simulated offline: floor table across sunny/average/dull/no-forecast days,
  decay through the morning, 10/10 trigger-gating cases, and a minute-by-minute
  sunny-morning replay (17.9 kWh sold, 2 mode changes, refilled by noon)
- [x] **Deployed 2026-09-03 21:37** (Samba copy + pycache clear + HA restart at
  21:39). All 6 entities registered; takeover-hour number correctly
  `disabled_by=integration`. Armed 21:52, no failsafe, stack idle in
  SELF_CONSUMPTION.
- [ ] **First live morning: 2026-09-04.** Watch
  `sensor.…morning_export_floor_soc` decay from ~39% at 06:00 toward the 25% min
  reserve by ~07:40, SOC stop *at* the floor, and **zero grid import** before
  09:00.

**Live entity naming:** the device sits in the *Site Office* area, so entities are
`…site_office_sentinel_energy_manager_*` (e.g.
`switch.site_office_sentinel_energy_manager_enable_morning_export`), not the
`sensor.sentinel_*` shorthand used elsewhere in these docs.

**Live tuning as deployed** (differs from code defaults): min reserve **25%**
(not 20), grid-charge hysteresis **5%** (not 3), grid charge rate **15 kW**,
morning export rate **15 kW** (set by Drew in the UI), morning export min price
**$0.10** — lowered from the $0.15 default because 2026-09-04's feed-in forecast
peaked at only **$0.13** (07:00) and the mode would never have fired. Feed-in that
day goes **negative (−$0.01) from 09:00**, which is the exact problem this mode
exists to solve.

**Real learned loads** (14 days, as at deploy): morning **11.97 kWh**, daytime
**31.7 kWh**, evening **13.21 kWh** — well below the 20/45/40 seeds, so the
floors are much lower than the seeded worked example in `CONTROL_LOGIC.md §4b`.

**GRID_CHARGE latch interaction, observed live:** SOC (73%) sits far above the
overnight target (34.4%), so from 22:00 GRID_CHARGE latches a top-up hold to the
06:00 morning-peak onset. The latch guard therefore holds MORNING_EXPORT off
until **06:00**, making the real first-morning window **06:00 → 09:00** rather
than 04:00 → 09:00. That is the intended ordering — the peak onset is where the
high feed-in price starts — but it is worth knowing when reading the logs.

### Charge-completion fixes — 2026-08-09 (BUILT, NOT DEPLOYED)
Diagnosed from the 2026-08-08/09 overnight: pack reached **86.5%** against a 90%
target at the 06:00 peak, all charging crammed into one block from 02:45, mode
chattering ~40 times.
- [x] **Amber forecast fetch repaired** — `config_entry_id` (entry_id), legacy key
  as fallback, throttled warning. This was the root cause: forecasts had been
  failing every poll since 2026-08-08 20:18, leaving only the forced path
  (`ISSUES.md #5`). Verified live: returns 50 intervals.
- [x] **Measured charge rate** (`_record_charge_rate_sample`, `_observed_charge_kw`)
  — EMA of ΔSOC/Δt while charging; `required_hours` sizes off `min(modelled,
  measured)`. Modelled 16 kW vs 10.8 kW actual.
- [x] **Time margin** `GRID_CHARGE_TIME_MARGIN` (1.3) on `required_hours`
  (GRID_CHARGE and OUTAGE_PREP).
- [x] **Top-up hold** to the deadline once target is met
  (`GRID_CHARGE_TOPUP_BAND_SOC` 1%), and a **forced-charge latch** to stop the
  chatter.
- [x] Replayed offline against the 08-09 overnight: SOC at deadline **89.2%** vs
  86.5% as-run; **still 89.6% when load doubles to 6 kW mid-charge**; mode changes
  40 → 6–16; the rate EMA converges on the true achievable kW.
- [ ] **Deploy & test:** confirm the error log is free of `Failed to fetch Amber
  forecasts`, that GRID_CHARGE now picks a cheap block well before the peak
  rather than forcing at the last minute, and that SOC sits *at* target when the
  peak starts.

---
### Phase 1 — Coordinator + Rebalancing (DEPLOYED 2026-04-22)
- [x] Coordinator, priority engine, rebalancing, failsafe, self-consumption
- [x] All entity files, 6-step config flow, deployed and tested
- [x] PV First rebalancing: uses PV First modes so solar is automatically prioritised
- [x] Grid connection check: rebalancing disabled when either plant is off-grid
- [ ] Verify rebalance stop condition restores SELF_CONSUMPTION

### Phase 2 — Morning Floor (REMOVED in Stage 1 — folded into GRID_CHARGE overnight)
- [x] 6am SOC prediction (live load sensors with fallback to typical kWh)
- [x] MORNING_FLOOR mode: charge both batteries via Grid First when predicted 6am SOC < floor
- [x] Number entities: floor SOC (40%), charge rate (2 kW), typical overnight load (5 kWh)
- [x] Predicted 6am SOC sensor, grid charging active binary sensor
- [x] Fix daily energy sensors: RestoreEntity + TOTAL_INCREASING for energy dashboard
- [x] Battery sensors: net battery power (kW), daily battery discharge/charge (kWh)
- [x] Verify battery power sign convention — Sigen uses positive = charging, negated in coordinator
- [ ] Deploy & test: enable morning floor switch, verify charging activates overnight
- [ ] Verify stop condition: charging stops when mean SOC >= floor

### Solar Curtail (COMPLETE)
- [x] SOLAR_CURTAIL mode: block export when Amber feed-in price < configurable threshold
- [x] Switch entity, price threshold number entity ($0.01 default), binary sensor
- [x] Uses `sensor.hill_end_feed_in_price` + combined PV power > 0 as triggers
- [ ] Deploy & test: enable switch, verify export blocked when feed-in < $0.01

### Phase 3 — Amber Grid Charging (COMPLETE)
- [x] Amber forecast fetching via `amberelectric.get_forecasts` with 15-min cache
- [x] GRID_CHARGE mode: Command Charging (PV First) during cheapest windows before deadline
- [x] Smart window selection: greedily picks cheapest intervals covering required charge hours
- [x] Forced charge safety: if remaining time < required_hours × 1.5, charge immediately
- [x] Number entities: target SOC (85%), deadline hour (5pm), charge rate (7 kW total)
- [x] Hysteresis: 1% buffer on entry, stops at target; auto-discovers Amber site from config entries
- [ ] Deploy & test: enable switch, monitor for GRID_CHARGE active/inactive/forced logs

#### Solar-adaptive target (SUPERSEDED by Stage 3 learned targets — entities removed in Stage 4)
- [x] `switch.sentinel_grid_charge_adaptive_target` (default OFF): when on, GRID_CHARGE target SOC is derived from tomorrow's Solcast forecast instead of the fixed target
- [x] Interpolation in `_compute_grid_charge_target()`: solar ≤ low threshold → high SOC target (winter, buy cheap overnight); solar ≥ high threshold → low SOC target (summer, let sun refill); linear between
- [x] Number entities: solar low threshold (20 kWh), solar high threshold (45 kWh), target poor-solar (95%), target strong-solar (35%)
- [x] Reads `sensor.solcast_pv_solar_forecast_tomorrow` (from config `CONF_SOLCAST_TOMORROW`); falls back to fixed `grid_charge_target_soc` if adaptive off, Solcast unconfigured, or unavailable
- [x] `sensor.sentinel_grid_charge_target_soc` exposes the effective (computed) target for visibility/tuning
- [ ] Deploy & test: enable adaptive switch, confirm target tracks Solcast tomorrow across a sunny vs cloudy day

#### Two-phase charging (SUPERSEDED by Stage 2 dynamic peak-onset deadlines)
- [x] GRID_CHARGE splits into an **overnight phase** (22:00–06:00, target = overnight cap, deadline 06:00) and a **daytime top-up phase** (09:00–16:00, target = evening target, deadline = `grid_charge_deadline_hour`), chosen by which off-peak window `now` is in (`_async_evaluate_grid_charge`)
- [x] Overnight's 06:00 deadline means `_select_cheapest_charge_window` only sees overnight intervals — the midday window can no longer steal the overnight charge (root cause of "sat in MORNING_FLOOR overnight, no cheap-window charging")
- [x] Overnight cap kept below the evening target so daytime solar has headroom to fill the rest for free; daytime phase yields to SELF_CONSUMPTION outside selected cheap intervals so solar charges first, then grid tops up when cheap
- [x] Overnight cap is adaptive too via shared `_interp_target_from_solar()` + shared solar low/high kWh thresholds: poor solar → high cap (85%, buy cheap overnight), strong solar → low cap (45%, lean on sun)
- [x] Number entities: overnight cap fixed (60%, adaptive off), overnight cap poor-solar (85%), overnight cap strong-solar (45%)
- [x] `sensor.sentinel_grid_charge_target_soc` is now phase-aware — shows the active phase's target (overnight cap overnight, evening target during the day)
- [ ] Deploy & test: confirm overnight charges to the cap at cheapest night intervals, then daytime tops up to the evening target after solar

#### Optimizations from July 2026 history analysis (rolled into Stages 2–4)
Diagnosed from `history-2.csv` (July 15–25, high-load site: 100–185 kWh/day load vs 49 kWh pack). Overnight cap was being *hit* but set too low (~50%) by gross-solar interpolation; daytime top-up thrashed (GRID_CHARGE↔REBALANCE↔SELF_CONSUMPTION flipping every 30–60 s) and never reached the evening target.
- [x] **Contiguous charge block**: `_select_cheapest_charge_window` now picks the single cheapest *contiguous* run covering `required_hours` (was N scattered globally-cheapest 5-min slots) — kills the on/off toggling that let REBALANCE steal the gaps
- [x] **Rebalance suppressed during charge**: `_check_rebalance_conditions` returns False when `_grid_charge_active`/`_outage_prep_active` so the two packs don't fight the charger
- [x] **Configurable hysteresis band** `OPT_GRID_CHARGE_HYSTERESIS_SOC` (default 3%, was hardcoded 1%) — stops re-trigger churn just under target (`number.…grid_charge_hysteresis_band`)
- [x] **Overnight cap keyed off exportable surplus** (option 1 rework): `_compute_overnight_target` = ceiling − (forecast PV − `OPT_EXPECTED_DAYTIME_LOAD_KWH`) as SOC, clamped to [floor, ceiling]. High-load site → ~0 surplus → charges to ceiling (85%); only genuine sunny/low-load surplus pulls the cap down so solar fills the pack instead of exporting. Overnight high/low SOC entities are now ceiling/floor. New `number.…expected_daytime_load` (default 45 kWh)
- [x] **Rebalance retamed**: `DEFAULT_REBALANCE_START_THRESHOLD` 7→10% (curbs all-day churn; 144 activations/10 days)
- [x] **FAILSAFE debounce**: `FAILSAFE_DEBOUNCE_POLLS` (2) — a single missed poll holds the current mode instead of dropping to Maximum Self Consumption; HA-switch-off still trips immediately
- [ ] Deploy & test: confirm daytime top-up sustains one block & reaches evening target; overnight cap tracks surplus; rebalance/failsafe churn drops

### Phase 4 — Price Spike Export (REMOVED in Stage 1 — insufficient pack headroom vs load)
- ~~SPIKE_EXPORT mode with safety logic~~ (deleted)

### Phase 5 — Planned Outage Prep (COMPLETE)
- [x] `date.sentinel_outage_date` entity: single planned outage date (ISO, persisted in options)
- [x] `number.sentinel_outage_target_soc` (default 90%); reuses `grid_charge_rate_kw` for charge power
- [x] OUTAGE_PREP mode: charge window 22:00 day-before → 06:00 outage day
- [x] Cheapest-interval selection within window via Amber forecasts; forced charge if `hours_remaining < required × 1.5`
- [x] Falls back to immediate charge if Amber forecasts unavailable
- [x] Hysteresis: stops at target, restarts 1% below; restores 12 kW grid limits on exit
- [x] `binary_sensor.sentinel_outage_prep_active`; reuses `_async_apply_grid_charge` (PV First + proportional SOC split)
- [ ] Deploy & test: set outage date, verify overnight charge picks cheapest intervals
