# Sentinel — Home Battery Energy Manager

## System Setup

- 2 Sigen batteries (24.5 kWh each, 49 kWh total), each with smart gateway
- 2 separate phases, split-phase 240V, both feed a **single power meter**
- Retailer: **Amber Electric** / Distributor: **Essential Energy** (regional NSW)
- Physical max: **7 kW** per battery (import and export)

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

Custom HA integration: 8-mode priority stack evaluated every 30 seconds.

| Priority | Mode | Trigger |
|---|---|---|
| 1 | **FAILSAFE** | Any Sigen entity unavailable OR HA switch off → Maximum Self Consumption |
| 2 | **SPIKE_EXPORT** | Amber spike + SOC above floor + buffer → discharge at configurable rate |
| 3 | **OUTAGE_PREP** | Registered outage within prep window → charge to target SOC |
| 4 | **GRID_CHARGE** | Amber price < threshold + solar won't cover + inside window → grid charge |
| 5 | **REBALANCE** | SOC diff > threshold → discharge higher, charge lower at matched rate |
| 6 | **SOLAR_CURTAIL** | Amber feed-in price < threshold (default $0.01) + solar producing → export limit 0 kW |
| 7 | **MORNING_FLOOR** | 22:00–06:00 + predicted 6am SOC < floor → gentle overnight charge |
| 8 | **SELF_CONSUMPTION** | Always valid → Maximum Self Consumption |

### Key Design Decisions

- All mode switches default **OFF** for safety — user must enable each mode
- Failsafe always restores batteries to Maximum Self Consumption + 7 kW limits
- Rebalance uses hysteresis: start threshold (default 7%) vs stop threshold (default 3%)
- Rebalance uses PV First modes for both charge and discharge — solar is automatically prioritised, no suppression needed
- Rebalance requires grid connection on both plants (disabled during grid outage)
- Solar curtail sets export limit to 0 kW when Amber feed-in price < threshold — inverters curtail solar to match load + battery charging only
- Daily energy sensors use signed `grid_active_power` (net across both phases), NOT per-plant `grid_import_power`/`grid_export_power` which double-count during rebalancing
- Battery sensors use `battery_power` from both plants (already in kW); Sigen sign convention is positive = charging, negative = discharging — coordinator negates so `net_battery_power` follows positive = discharging
- **NEVER touch** `switch.sigen_plant_plant_power` or `switch.sigen_plant_2_plant_power` — these control whether plants output power at all

### ForecastEngine (Phase 2+)

Predicts 6am SOC using live load sensors (fallback: configured kWh). Checks Solcast for solar coverage and Amber forecasts for cheapest charge windows. Degrades gracefully if external services offline.

### Services (Phase 5)

- `sentinel.add_outage` / `sentinel.remove_outage` / `sentinel.list_outages`

### Data Sources

- **Amber forecasts:** via action `amberelectric.get_forecasts` (config_entry="Hill End", channel_type="general"). Returns 5-min intervals with `per_kwh` (dollars), `spot_per_kwh`, `spike_status`, `descriptor`, `start_time` (UTC), `nem_date` (AEST). Called with `return_response=True`.
- **Amber sensors:** `sensor.<site>_general_price`, `sensor.<site>_feed_in_price`, `binary_sensor.<site>_price_spike`
- **Solcast:** `sensor.solcast_pv_solar_forecast_today`, `sensor.solcast_pv_solar_forecast_tomorrow`
- **Sigen load:** `sensor.sigen_plant_load_power`, `sensor.sigen_plant_2_load_power` (hardcoded, not configurable)
- **Sigen PV:** `sensor.sigen_plant_pv_power`, `sensor.sigen_plant_2_pv_power` (hardcoded, not configurable)

## Build Status

### Phase 1 — Coordinator + Rebalancing (DEPLOYED 2026-04-22)
- [x] Coordinator, priority engine, rebalancing, failsafe, self-consumption
- [x] All entity files, 6-step config flow, deployed and tested
- [x] PV First rebalancing: uses PV First modes so solar is automatically prioritised
- [x] Grid connection check: rebalancing disabled when either plant is off-grid
- [ ] Verify rebalance stop condition restores SELF_CONSUMPTION

### Phase 2 — Morning Floor (IN PROGRESS)
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

### Phase 3 — Amber Grid Charging
- [ ] Amber price parsing, GRID_CHARGE mode, charge window selects

### Phase 4 — Price Spike Export
- [ ] SPIKE_EXPORT mode with safety logic

### Phase 5 — Planned Outage Prep
- [ ] OutageStore, OUTAGE_PREP mode, services
