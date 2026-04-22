# Home Battery System — Amber API & Net Metering Notes

## System Setup

- 2 batteries, each with a smart gateway
- 2 separate phases, split-phase 240V on each
- Both phases feed into a **single power meter**
- Retailer: **Amber Electric**
- Distributor: **Essential Energy** (regional NSW)

## The Problem with Amber SmartShift

Amber's SmartShift can only control **one battery at a time**, but both batteries feed the same meter. Goal is to use the **Amber API** to manage both batteries simultaneously.

## Battery Rebalancing Strategy

To balance state-of-charge between the two batteries:
- Discharge Battery A (Phase 1)
- Simultaneously charge Battery B (Phase 2)
- Energy flows phase-to-phase through the meter

Rate is governed by setting equal `grid_export_limitation` (discharging battery) and `grid_import_limitation` (charging battery) — equal and opposite flows keep meter net ≈ 0.

## Net Metering Clarification

Because both phases feed a **single meter**, the meter sees the **net** of both phases:

- Battery A exporting 3kW on Phase 1
- Battery B importing 3kW on Phase 2
- **Meter net = 0** — nothing crosses the grid boundary
- Amber bills on meter net, so **no import charge, no export credit**
- The only real cost is **round-trip efficiency loss** through the batteries

## Home Assistant Integration

### Battery Integration

- **Integration**: Energy Storage System by Signenergy
- **Devices**: Sigen Plant, Sigen Plant 2

### Key Entity Names

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

### Mode Options (select entities)

- `PCS Remote Control`
- `Standby`
- `Maximum Self Consumption` ← normal/restore state
- `Command Charging (Grid First)` ← used for rebalancing charge
- `Command Charging (PV First)`
- `Command Discharging (PV First)`
- `Command Discharging (PV First)` ← used for rebalancing discharge
- `Unknown`

### Grid Limits

- Physical max: **7 kW** per battery (import and export)
- Restore to 7 kW on both import and export after any operation

## Project Approach: Sentinel — Comprehensive Energy Management Integration

**Sentinel** is a custom Home Assistant integration that orchestrates **rebalancing, morning floor charging, solar-aware decisions, Amber price-based grid charging, price spike export, and planned outage prep** — all in a single priority-ordered decision engine.

### Why a custom integration

- Single config flow (UI) sets up all entity IDs and thresholds — no YAML editing
- All decision logic, sensors, and controls created automatically
- Exposes services callable from automations (`sentinel.add_outage`, etc.)
- Fails safe to "Maximum Self Consumption" (inverter-native safe state) if any component is unavailable
- Graceful degradation: works even if Amber or Solcast is offline

### Architecture: 7-mode priority stack

Every 30 seconds, Sentinel evaluates these modes in order and activates the highest-priority valid mode:

| Priority | Mode | Trigger | Commands | Failsafe? |
|---|---|---|---|---|
| 1 | **FAILSAFE** | Any Sigen entity unavailable OR HA switch off | Both batteries → Maximum Self Consumption | Yes |
| 2 | **SPIKE_EXPORT** | Amber spike active + SOC above floor + buffer | Both batteries discharge at 5 kW (configurable) | No |
| 3 | **OUTAGE_PREP** | Registered outage within prep window, SOC below target | Both batteries charge to target SOC | No |
| 4 | **GRID_CHARGE** | Amber price < threshold + solar won't cover + inside charge window | Both batteries grid-charge at 3.5 kW (configurable) | No |
| 5 | **REBALANCE** | SOC diff > threshold (default 7%) + safety met | Discharge higher battery, charge lower at 3 kW (ported from sigen_rebalancer) | No |
| 6 | **MORNING_FLOOR** | 22:00–06:00 + predicted 6am SOC < floor (default 40%) | Both batteries charge overnight at 2 kW | No |
| 7 | **SELF_CONSUMPTION** | Always valid | Both batteries → Maximum Self Consumption | Default |

### ForecastEngine

Separate pure-computation class called every 30s cycle. Predicts 6am SOC using:
- **Primary:** Live Sigen load power sensors (kW) integrated over hours until 6am
- **Fallback:** Configured typical overnight load (kWh) if sensors unavailable
- **Solar check:** Solcast forecast vs. battery deficit to decide if `solar_covers_deficit`
- **Price scan:** Amber forecast array to find cheapest charging window (next 20 hours)

All calculations gracefully degrade if Amber or Solcast is offline — system still works with time-based logic and configured estimates.

### Integration structure

**Status: BEING BUILT** — design complete, implementation phased.

```
custom_components/sentinel/
  __init__.py          ← setup/teardown, registers services (add_outage, remove_outage, list_outages)
  manifest.json        ← domain=sentinel, version=1.0.0
  const.py             ← all constants, defaults, entity ID defaults
  config_flow.py       ← 6-step UI wizard: Plant 1 → Plant 2 → Capacity → Amber → Solcast → Settings
  coordinator.py       ← SentinelCoordinator, priority engine, mode dispatch
  forecast_engine.py   ← ForecastEngine class, all 6am/solar/price forecasting
  outage_store.py      ← OutageStore (JSON persistence), OutageEvent dataclass
  
  sensor.py            ← 11 sensors: net grid power, mean SOC, predicted 6am, prices, mode, etc.
  binary_sensor.py     ← 6 binary sensors: failsafe, rebalancing, solar covers, spike, prep, charging
  switch.py            ← 5 switches: enable per mode (all default OFF for safety)
  number.py            ← 13 numbers: thresholds, rates, targets, confidence
  select.py            ← 2 selects: charge window start/end times
  
  strings.json         ← all UI labels
  translations/en.json
```

### Build phases (each independently deployable)

- **Phase 1:** Port coordinator + rebalancing logic, FAILSAFE/SELF_CONSUMPTION modes → deploy
- **Phase 2:** ForecastEngine + MORNING_FLOOR mode → live testing
- **Phase 3:** Amber price parsing + GRID_CHARGE mode → live testing
- **Phase 4:** SPIKE_EXPORT mode + safety checks → live testing
- **Phase 5:** OutageStore + OUTAGE_PREP mode + services → complete system

### Entities created by Sentinel

| Entity | Type | Default | Purpose |
|---|---|---|---|
| `sensor.sentinel_active_mode` | sensor | — | Current operating mode (string) |
| `sensor.sentinel_net_grid_power` | sensor | — | Net grid flow (kW, signed) |
| `sensor.sentinel_mean_battery_soc` | sensor | — | Average SOC % |
| `sensor.sentinel_predicted_soc_at_6am` | sensor | — | ForecastEngine prediction |
| `sensor.sentinel_solar_remaining_today` | sensor | — | Solcast passthrough (kWh) |
| `sensor.sentinel_cheapest_charge_price` | sensor | — | Next cheapest Amber window (c/kWh) |
| `sensor.sentinel_current_buy_price` | sensor | — | Amber current price (c/kWh) |
| `sensor.sentinel_current_sell_price` | sensor | — | Amber current feed-in price (c/kWh) |
| `sensor.sentinel_next_outage_start` | sensor | — | Nearest registered outage (datetime) |
| — | — | — | — |
| `binary_sensor.sentinel_failsafe_active` | binary_sensor | off | True in FAILSAFE mode |
| `binary_sensor.sentinel_rebalancing_active` | binary_sensor | off | True while REBALANCE active |
| `binary_sensor.sentinel_solar_covers_deficit` | binary_sensor | — | ForecastEngine: will solar cover needed charge? |
| `binary_sensor.sentinel_price_spike_active` | binary_sensor | — | Amber spike passthrough |
| `binary_sensor.sentinel_grid_charging_active` | binary_sensor | off | True during GRID_CHARGE/MORNING_FLOOR/OUTAGE_PREP |
| — | — | — | — |
| `switch.sentinel_rebalance_enabled` | switch | **OFF** | Enable REBALANCE mode |
| `switch.sentinel_morning_floor_enabled` | switch | **OFF** | Enable MORNING_FLOOR mode |
| `switch.sentinel_grid_charge_enabled` | switch | **OFF** | Enable GRID_CHARGE mode |
| `switch.sentinel_spike_export_enabled` | switch | **OFF** | Enable SPIKE_EXPORT mode |
| `switch.sentinel_outage_prep_enabled` | switch | **OFF** | Enable OUTAGE_PREP mode |
| — | — | — | — |
| `number.sentinel_rebalance_start_threshold` | number | 7% | SOC diff to trigger rebalance |
| `number.sentinel_rebalance_stop_threshold` | number | 3% | SOC diff to stop rebalance |
| `number.sentinel_rebalance_transfer_rate` | number | 3 kW | Rebalance rate (per battery) |
| `number.sentinel_morning_floor_soc` | number | 40% | Target SOC by 6am |
| `number.sentinel_morning_charge_rate` | number | 2 kW | Gentle overnight charge rate |
| `number.sentinel_grid_charge_threshold` | number | 5 c/kWh | Max price to trigger grid charge |
| `number.sentinel_grid_charge_target_soc` | number | 80% | SOC target when grid charging |
| `number.sentinel_grid_charge_rate` | number | 3.5 kW | Fast grid charge rate |
| `number.sentinel_spike_export_buffer` | number | 15% | SOC margin above floor before exporting |
| `number.sentinel_spike_export_rate` | number | 5 kW | Export rate per battery |
| `number.sentinel_solar_forecast_confidence` | number | 85% | Discount applied to Solcast forecast |
| `number.sentinel_typical_overnight_load` | number | 5 kWh | Fallback if load sensors offline |
| `number.sentinel_outage_prep_target_soc` | number | 95% | SOC target for outage prep |
| — | — | — | — |
| `select.sentinel_charge_window_start` | select | 00:00 | Grid charge window opens (off-peak) |
| `select.sentinel_charge_window_end` | select | 06:00 | Grid charge window closes |

### Services

- `sentinel.add_outage` — register a planned outage with start time, duration, prep hours, target SOC
- `sentinel.remove_outage` — remove outage by ID
- `sentinel.list_outages` — return current registered outages

### Hardware facts

- **System capacity:** 24.5 kWh per battery (49 kWh total usable)
- **Load sensors:** Each Sigen plant exposes `sensor.sigen_plant_load_power` and `sensor.sigen_plant_2_load_power` per phase (used for accurate overnight load estimation)

## Net Metering Verification

### Quick tests
1. **Amber app/bill** — check a period of simultaneous charge/discharge, confirm near-zero net recorded
2. **Controlled test** — discharge A and charge B at equal rates with no solar, watch meter in real time
3. **Physical meter display** — look for net import/export figure or LED pulse rate during the test

### Definitive confirmation
- Contact your **Metering Coordinator** (not Essential Energy directly — they use third-party metering)
- Find your Metering Coordinator name on your Amber bill or app alongside your **NMI** and **Meter ID**
- Ask: *"Is my meter configured to report net consumption across both phases, or does it measure each phase independently?"*

## Essential Energy Specifics

- Essential Energy outsources metering to third-party **Metering Coordinators** (e.g. Acumen, Intellihub, Wattwatchers)
- Meter configuration (net vs per-phase) is set by the Metering Coordinator, not Essential
- Essential's regional footprint means older meters are possible — **worth confirming before relying on net metering assumption**

## Sentinel Build Status

### Pre-requisite verification (before relying on net metering)
- [ ] Identify Metering Coordinator from Amber bill/app
- [ ] Confirm net metering configuration across phases
- [ ] Verify Amber & Solcast integrations installed and working in HA

### Phase 1 — Coordinator Architecture + Rebalancing (in progress)
- [ ] Create `custom_components/sentinel/` directory structure
- [ ] Port all constants, defaults, entity ID keys from sigen_rebalancer → sentinel
- [ ] Implement `SentinelCoordinator` with priority engine (`_evaluate_priority()`)
- [ ] Port rebalancing logic: `_async_apply_rebalance()` + safety conditions
- [ ] Implement FAILSAFE and SELF_CONSUMPTION modes
- [ ] Create all entity files (sensor, binary_sensor, switch, number, select)
- [ ] Implement 6-step config flow
- [ ] **Deploy to HA:** Copy to `config/custom_components/`, restart HA, run config flow
- [ ] **Test:** Rebalancing works, mode sensor shows correct state, failsafe triggers on entity loss

### Phase 2 — ForecastEngine + Morning Floor
- [ ] Implement `ForecastEngine` class with 6am SOC prediction
- [ ] Use live Sigen load sensors as primary, configured kWh as fallback
- [ ] Implement `MORNING_FLOOR` mode
- [ ] Add morning floor, load, solar confidence number entities
- [ ] Deploy & test: overnight charging to floor, verify 6am prediction accuracy

### Phase 3 — Amber Price-Based Grid Charging
- [ ] Extend `ForecastEngine` to parse Amber `forecasts[]` attribute
- [ ] Implement `GRID_CHARGE` mode
- [ ] Add price threshold, target SOC, charge rate number entities
- [ ] Add charge window start/end select entities
- [ ] Deploy & test: grid charge during cheap windows when solar insufficient

### Phase 4 — Price Spike Export
- [ ] Implement `SPIKE_EXPORT` mode with export safety logic
- [ ] Add spike buffer and export rate number entities
- [ ] Deploy & test: batteries export during spikes without risking morning floor

### Phase 5 — Planned Outage Prep
- [ ] Implement `OutageStore` (JSON persistence via HA helpers.storage)
- [ ] Implement `OUTAGE_PREP` mode
- [ ] Implement services: `sentinel.add_outage`, `sentinel.remove_outage`, `sentinel.list_outages`
- [ ] Deploy & test: register outages, verify pre-charging starts in prep window
- [ ] (Future) Integrate with BOM weather alerts for auto storm prep

### Data sources (required for full system)
- **Amber Electric HA integration:** `sensor.<site>_general_price`, `sensor.<site>_general_forecast` (with `forecasts[]` attr), `binary_sensor.<site>_price_spike`
- **Solcast HACS:** `sensor.solcast_pv_solar_forecast_today`, `sensor.solcast_pv_solar_forecast_tomorrow`
- **Sigen plants:** Load power sensors `sensor.sigen_plant_load_power`, `sensor.sigen_plant_2_load_power` (per-phase consumption)
