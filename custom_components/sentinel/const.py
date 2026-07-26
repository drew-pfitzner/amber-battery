"""Constants for Sentinel Energy Manager."""

DOMAIN = "sentinel"
SCAN_INTERVAL_SECONDS = 30

# Consecutive polls a critical entity must read unavailable before FAILSAFE trips.
# Rides out a single missed poll (transient sensor dropout) without dropping the
# whole stack to Maximum Self Consumption. HA-switch-off still trips immediately.
FAILSAFE_DEBOUNCE_POLLS = 2

# Mode constants
MODE_FAILSAFE = "FAILSAFE"
MODE_SPIKE_EXPORT = "SPIKE_EXPORT"
MODE_OUTAGE_PREP = "OUTAGE_PREP"
MODE_GRID_CHARGE = "GRID_CHARGE"
MODE_REBALANCE = "REBALANCE"
MODE_SOLAR_CURTAIL = "SOLAR_CURTAIL"
MODE_MORNING_FLOOR = "MORNING_FLOOR"
MODE_SELF_CONSUMPTION = "SELF_CONSUMPTION"

# Config entry keys (for Sigen entity IDs)
# Plant 1
CONF_SOC_1 = "soc_1"
CONF_MODE_1 = "mode_1"
CONF_HA_SWITCH_1 = "ha_switch_1"
CONF_EXPORT_LIMIT_1 = "export_limit_1"
CONF_IMPORT_LIMIT_1 = "import_limit_1"
CONF_BACKUP_SOC_1 = "backup_soc_1"
CONF_EXPORT_POWER_1 = "export_power_1"
CONF_IMPORT_POWER_1 = "import_power_1"

# Plant 2
CONF_SOC_2 = "soc_2"
CONF_MODE_2 = "mode_2"
CONF_HA_SWITCH_2 = "ha_switch_2"
CONF_EXPORT_LIMIT_2 = "export_limit_2"
CONF_IMPORT_LIMIT_2 = "import_limit_2"
CONF_BACKUP_SOC_2 = "backup_soc_2"
CONF_EXPORT_POWER_2 = "export_power_2"
CONF_IMPORT_POWER_2 = "import_power_2"

# Battery capacity
CONF_CAPACITY_KWH = "battery_capacity_kwh"

# Amber integration (Phase 3)
CONF_AMBER_GENERAL_PRICE = "amber_general_price"
CONF_AMBER_GENERAL_FORECAST = "amber_general_forecast"
CONF_AMBER_PRICE_SPIKE = "amber_price_spike"

# Solcast integration (Phase 2)
CONF_SOLCAST_TODAY = "solcast_pv_solar_forecast_today"
CONF_SOLCAST_TOMORROW = "solcast_pv_solar_forecast_tomorrow"

# Amber forecast action (Phase 3+)
CONF_AMBER_SITE_NAME = "amber_site_name"

# Options keys — rebalancing
OPT_REBALANCE_START_THRESHOLD = "rebalance_start_threshold"
OPT_REBALANCE_STOP_THRESHOLD = "rebalance_stop_threshold"
OPT_REBALANCE_TRANSFER_RATE = "rebalance_transfer_rate"

# Options keys — solar curtail
OPT_SOLAR_CURTAIL_PRICE_THRESHOLD = "solar_curtail_price_threshold"

# Options keys — morning floor
OPT_MORNING_FLOOR_SOC = "morning_floor_soc"

# Options keys — grid charge
OPT_GRID_CHARGE_TARGET_SOC = "grid_charge_target_soc"
OPT_GRID_CHARGE_DEADLINE_HOUR = "grid_charge_deadline_hour"
OPT_GRID_CHARGE_RATE_KW = "grid_charge_rate_kw"
# SOC band below target before a stopped GRID_CHARGE restarts (hysteresis). A
# wider band stops the mode re-triggering every cycle as load nibbles the pack.
OPT_GRID_CHARGE_HYSTERESIS_SOC = "grid_charge_hysteresis_soc"

# Options keys — grid charge solar-adaptive target
# When enabled, the overnight GRID_CHARGE target SOC is interpolated from
# tomorrow's Solcast forecast: poor solar → high target (buy cheap overnight),
# strong solar → low target (let the sun refill the batteries for free).
OPT_GRID_CHARGE_ADAPTIVE = "grid_charge_adaptive_target"
OPT_GRID_CHARGE_SOLAR_LOW_KWH = "grid_charge_solar_low_kwh"      # at/below → high target
OPT_GRID_CHARGE_SOLAR_HIGH_KWH = "grid_charge_solar_high_kwh"    # at/above → low target
OPT_GRID_CHARGE_TARGET_HIGH_SOC = "grid_charge_target_high_soc"  # evening target at poor solar
OPT_GRID_CHARGE_TARGET_LOW_SOC = "grid_charge_target_low_soc"    # evening target at strong solar

# Options keys — grid charge overnight cap (phase 1)
# GRID_CHARGE runs in two phases: an overnight phase (charge to a modest cap by
# the morning peak, leaving headroom for solar) and a daytime top-up phase
# (let solar charge first, top up with cheap grid to the evening target). The
# overnight cap uses the SAME solar low/high kWh thresholds as the evening
# target for its adaptive interpolation.
OPT_GRID_CHARGE_OVERNIGHT_TARGET_SOC = "grid_charge_overnight_target_soc"            # fixed cap (adaptive off)
OPT_GRID_CHARGE_OVERNIGHT_TARGET_HIGH_SOC = "grid_charge_overnight_target_high_soc"  # overnight cap ceiling (no solar surplus)
OPT_GRID_CHARGE_OVERNIGHT_TARGET_LOW_SOC = "grid_charge_overnight_target_low_soc"    # overnight cap floor (large solar surplus)
# Expected daytime household/site consumption during solar hours (kWh). Used to
# turn tomorrow's forecast solar into an *exportable surplus* (forecast PV minus
# this load). The adaptive overnight cap leaves headroom only for that surplus,
# so a high-load site still charges to the ceiling (solar won't export) while a
# sunny, low-load day holds the cap down so daytime solar fills the pack for free
# instead of spilling to the grid at a poor feed-in price.
OPT_EXPECTED_DAYTIME_LOAD_KWH = "expected_daytime_load_kwh"

# Options keys — outage prep
OPT_OUTAGE_DATE = "outage_date"               # ISO date string (YYYY-MM-DD) or ""
OPT_OUTAGE_TARGET_SOC = "outage_target_soc"

# Default values
DEFAULT_BATTERY_CAPACITY_KWH = 24.5
DEFAULT_REBALANCE_START_THRESHOLD = 10.0  # % — wider start band curbs all-day rebalance churn
DEFAULT_REBALANCE_STOP_THRESHOLD = 3.0   # %
DEFAULT_REBALANCE_TRANSFER_RATE = 3.0    # kW
DEFAULT_MORNING_FLOOR_SOC = 40.0         # %
DEFAULT_SOLAR_CURTAIL_PRICE_THRESHOLD = 0.01  # $/kWh — curtail export below this feed-in price
DEFAULT_GRID_CHARGE_TARGET_SOC = 85.0       # %
DEFAULT_GRID_CHARGE_DEADLINE_HOUR = 17      # 5 PM local time
DEFAULT_GRID_CHARGE_RATE_KW = 7.0           # kW total across both plants
DEFAULT_GRID_CHARGE_HYSTERESIS_SOC = 3.0    # % — restart band below target once stopped
DEFAULT_GRID_CHARGE_ADAPTIVE = False        # off by default — opt-in seasonal target
DEFAULT_GRID_CHARGE_SOLAR_LOW_KWH = 20.0    # kWh — at/below this tomorrow's solar → high target
DEFAULT_GRID_CHARGE_SOLAR_HIGH_KWH = 45.0   # kWh — at/above this tomorrow's solar → low target
DEFAULT_GRID_CHARGE_TARGET_HIGH_SOC = 95.0  # % — evening target when solar is poor
DEFAULT_GRID_CHARGE_TARGET_LOW_SOC = 35.0   # % — evening target when solar is strong
# Overnight cap (phase 1) — how full to charge by the morning peak. Kept below
# the evening target so daytime solar has headroom to fill the rest for free.
DEFAULT_GRID_CHARGE_OVERNIGHT_TARGET_SOC = 60.0       # % — fixed cap when adaptive off
DEFAULT_GRID_CHARGE_OVERNIGHT_TARGET_HIGH_SOC = 85.0  # % — overnight cap ceiling (no exportable solar surplus)
DEFAULT_GRID_CHARGE_OVERNIGHT_TARGET_LOW_SOC = 45.0   # % — overnight cap floor (large exportable solar surplus)
DEFAULT_EXPECTED_DAYTIME_LOAD_KWH = 45.0    # kWh — site consumption during solar hours (surplus = forecast PV − this)
DEFAULT_OUTAGE_TARGET_SOC = 90.0            # %

# Outage prep overnight charge window (local time, day BEFORE outage → outage day morning)
OUTAGE_PREP_START_HOUR = 22                 # 10 PM on day before
OUTAGE_PREP_END_HOUR = 6                    # 6 AM on outage day
DEFAULT_NORMAL_BACKUP_SOC = 10.0         # % — restored when leaving morning floor
DEFAULT_MAX_GRID_LIMIT = 12.0            # kW — full inverter capacity; Sigen throttles to its own internal limit
DEFAULT_MAX_CHARGE_SOC = 95.0            # %
DEFAULT_BACKUP_BUFFER = 5.0              # % margin above backup SOC

# GRID_CHARGE off-peak windows (local time). Grid charging is only allowed
# inside these windows to avoid network/Amber peak periods (06:00–09:00 and
# 16:00–22:00). Each entry is (start_hour, end_hour); a window whose start > end
# wraps past midnight. Applies to all GRID_CHARGE paths, including forced charge.
GRID_CHARGE_WINDOWS = ((22, 6), (9, 16))    # 10 PM–6 AM and 9 AM–4 PM

# GRID_CHARGE phase boundaries (local hour). The overnight phase charges toward
# the overnight cap by the morning peak; the daytime phase tops up toward the
# evening target by the evening deadline (grid_charge_deadline_hour).
GRID_CHARGE_MORNING_DEADLINE_HOUR = 6       # 6 AM — overnight phase completes by here
GRID_CHARGE_DAYTIME_START_HOUR = 9          # 9 AM — daytime top-up window opens

# Morning floor time window
MORNING_FLOOR_START_HOUR = 22   # 10 PM
MORNING_FLOOR_START_MINUTE = 10
MORNING_FLOOR_END_HOUR = 5      # 5 AM
MORNING_FLOOR_END_MINUTE = 50

# Load power sensors (not configurable — known Sigen entity IDs)
LOAD_POWER_1 = "sensor.sigen_plant_consumed_power"
LOAD_POWER_2 = "sensor.sigen_plant_2_consumed_power"

# PV power sensors (not configurable — known Sigen entity IDs)
PV_POWER_1 = "sensor.sigen_plant_pv_power"
PV_POWER_2 = "sensor.sigen_plant_2_pv_power"

# Battery power sensors (signed: positive = charging, negative = discharging)
BATTERY_POWER_1 = "sensor.sigen_plant_battery_power"
BATTERY_POWER_2 = "sensor.sigen_plant_2_battery_power"

# Grid active power sensors (signed: positive = import, negative = export)
# Used for true net metering calculation across both phases
GRID_ACTIVE_POWER_1 = "sensor.sigen_plant_grid_active_power"
GRID_ACTIVE_POWER_2 = "sensor.sigen_plant_2_grid_active_power"

# Default Sigen entity IDs (pre-fill for user convenience)
DEFAULT_SOC_1 = "sensor.sigen_plant_battery_state_of_charge"
DEFAULT_MODE_1 = "select.sigen_plant_remote_ems_control_mode"
DEFAULT_HA_SWITCH_1 = "switch.sigen_plant_remote_ems_controlled_by_home_assistant"
DEFAULT_EXPORT_LIMIT_1 = "number.sigen_plant_grid_export_limitation"
DEFAULT_IMPORT_LIMIT_1 = "number.sigen_plant_grid_import_limitation"
DEFAULT_BACKUP_SOC_1 = "number.sigen_plant_ess_backup_state_of_charge"
DEFAULT_EXPORT_POWER_1 = "sensor.sigen_plant_grid_export_power"
DEFAULT_IMPORT_POWER_1 = "sensor.sigen_plant_grid_import_power"

DEFAULT_SOC_2 = "sensor.sigen_plant_2_battery_state_of_charge"
DEFAULT_MODE_2 = "select.sigen_plant_2_remote_ems_control_mode"
DEFAULT_HA_SWITCH_2 = "switch.sigen_plant_2_remote_ems_controlled_by_home_assistant"
DEFAULT_EXPORT_LIMIT_2 = "number.sigen_plant_2_grid_export_limitation"
DEFAULT_IMPORT_LIMIT_2 = "number.sigen_plant_2_grid_import_limitation"
DEFAULT_BACKUP_SOC_2 = "number.sigen_plant_2_ess_backup_state_of_charge"
DEFAULT_EXPORT_POWER_2 = "sensor.sigen_plant_2_grid_export_power"
DEFAULT_IMPORT_POWER_2 = "sensor.sigen_plant_2_grid_import_power"

# Amber feed-in price sensor
AMBER_FEED_IN_PRICE = "sensor.hill_end_feed_in_price"

# Grid connection status sensors (not configurable — known Sigen entity IDs)
GRID_CONNECTION_1 = "sensor.sigen_plant_grid_connection_status"
GRID_CONNECTION_2 = "sensor.sigen_plant_2_grid_connection_status"

# Battery mode names (as they appear in sigen_plant remote_ems_control_mode select)
MODE_MAXIMUM_SELF_CONSUMPTION = "Maximum Self Consumption"
MODE_COMMAND_CHARGING_GRID_FIRST = "Command Charging (Grid First)"
MODE_COMMAND_CHARGING_PV_FIRST = "Command Charging (PV First)"
MODE_COMMAND_DISCHARGING_PV_FIRST = "Command Discharging (PV First)"
