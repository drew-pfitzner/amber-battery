"""Constants for Sentinel Energy Manager."""

DOMAIN = "sentinel"
SCAN_INTERVAL_SECONDS = 30

# Mode constants
MODE_FAILSAFE = "FAILSAFE"
MODE_SPIKE_EXPORT = "SPIKE_EXPORT"
MODE_OUTAGE_PREP = "OUTAGE_PREP"
MODE_GRID_CHARGE = "GRID_CHARGE"
MODE_REBALANCE = "REBALANCE"
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

# Options keys — morning floor
OPT_MORNING_FLOOR_SOC = "morning_floor_soc"

# Default values
DEFAULT_BATTERY_CAPACITY_KWH = 24.5
DEFAULT_REBALANCE_START_THRESHOLD = 7.0  # %
DEFAULT_REBALANCE_STOP_THRESHOLD = 3.0   # %
DEFAULT_REBALANCE_TRANSFER_RATE = 3.0    # kW
DEFAULT_MORNING_FLOOR_SOC = 40.0         # %
DEFAULT_NORMAL_BACKUP_SOC = 10.0         # % — restored when leaving morning floor
DEFAULT_MAX_GRID_LIMIT = 7.0             # kW
DEFAULT_MAX_CHARGE_SOC = 95.0            # %
DEFAULT_BACKUP_BUFFER = 5.0              # % margin above backup SOC

# Morning floor time window
MORNING_FLOOR_START_HOUR = 22   # 10 PM
MORNING_FLOOR_START_MINUTE = 10
MORNING_FLOOR_END_HOUR = 5      # 5 AM
MORNING_FLOOR_END_MINUTE = 50

# Load power sensors (not configurable — known Sigen entity IDs)
LOAD_POWER_1 = "sensor.sigen_plant_load_power"
LOAD_POWER_2 = "sensor.sigen_plant_2_load_power"

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

# Grid connection status sensors (not configurable — known Sigen entity IDs)
GRID_CONNECTION_1 = "sensor.sigen_plant_grid_connection_status"
GRID_CONNECTION_2 = "sensor.sigen_plant_2_grid_connection_status"

# Battery mode names (as they appear in sigen_plant remote_ems_control_mode select)
MODE_MAXIMUM_SELF_CONSUMPTION = "Maximum Self Consumption"
MODE_COMMAND_CHARGING_GRID_FIRST = "Command Charging (Grid First)"
MODE_COMMAND_CHARGING_PV_FIRST = "Command Charging (PV First)"
MODE_COMMAND_DISCHARGING_PV_FIRST = "Command Discharging (PV First)"
