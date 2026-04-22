"""Constants for the Sigen Battery Rebalancer integration."""

DOMAIN = "sigen_rebalancer"

# ── Config entry keys (entity IDs, stored in data) ──────────────────────────
CONF_SOC_1 = "soc_1"
CONF_SOC_2 = "soc_2"
CONF_MODE_1 = "mode_1"
CONF_MODE_2 = "mode_2"
CONF_HA_SWITCH_1 = "ha_switch_1"
CONF_HA_SWITCH_2 = "ha_switch_2"
CONF_EXPORT_LIMIT_1 = "export_limit_1"
CONF_EXPORT_LIMIT_2 = "export_limit_2"
CONF_IMPORT_LIMIT_1 = "import_limit_1"
CONF_IMPORT_LIMIT_2 = "import_limit_2"
CONF_BACKUP_SOC_1 = "backup_soc_1"
CONF_BACKUP_SOC_2 = "backup_soc_2"
CONF_EXPORT_POWER_1 = "export_power_1"
CONF_EXPORT_POWER_2 = "export_power_2"
CONF_IMPORT_POWER_1 = "import_power_1"
CONF_IMPORT_POWER_2 = "import_power_2"

# ── Option keys (operational settings, stored in options) ────────────────────
OPT_START_THRESHOLD = "start_threshold"
OPT_STOP_THRESHOLD = "stop_threshold"
OPT_TRANSFER_RATE = "transfer_rate"

# ── Operational defaults ─────────────────────────────────────────────────────
DEFAULT_START_THRESHOLD = 7.0   # % SOC difference to begin rebalancing
DEFAULT_STOP_THRESHOLD = 3.0    # % SOC difference to end rebalancing
DEFAULT_TRANSFER_RATE = 3.0     # kW transfer rate
DEFAULT_MAX_GRID_LIMIT = 7.0    # kW — physical max, restored after any op
DEFAULT_MAX_CHARGE_SOC = 95.0   # % — don't charge above this
DEFAULT_BACKUP_BUFFER = 5.0     # % — headroom above backup SOC before discharging

SCAN_INTERVAL_SECONDS = 30

# ── Battery mode strings (must match HA select entity options exactly) ────────
MODE_SELF_CONSUMPTION = "Maximum Self Consumption"
MODE_DISCHARGE = "Command Discharging (ESS First)"
MODE_CHARGE = "Command Charging (Grid First)"

# ── Default entity IDs (pre-filled in config flow) ───────────────────────────
DEFAULT_SOC_1 = "sensor.sigen_plant_battery_state_of_charge"
DEFAULT_SOC_2 = "sensor.sigen_plant_2_battery_state_of_charge"
DEFAULT_MODE_1 = "select.sigen_plant_remote_ems_control_mode"
DEFAULT_MODE_2 = "select.sigen_plant_2_remote_ems_control_mode"
DEFAULT_HA_SWITCH_1 = "switch.sigen_plant_remote_ems_controlled_by_home_assistant"
DEFAULT_HA_SWITCH_2 = "switch.sigen_plant_2_remote_ems_controlled_by_home_assistant"
DEFAULT_EXPORT_LIMIT_1 = "number.sigen_plant_grid_export_limitation"
DEFAULT_EXPORT_LIMIT_2 = "number.sigen_plant_2_grid_export_limitation"
DEFAULT_IMPORT_LIMIT_1 = "number.sigen_plant_grid_import_limitation"
DEFAULT_IMPORT_LIMIT_2 = "number.sigen_plant_2_grid_import_limitation"
DEFAULT_BACKUP_SOC_1 = "number.sigen_plant_ess_backup_state_of_charge"
DEFAULT_BACKUP_SOC_2 = "number.sigen_plant_2_ess_backup_state_of_charge"
DEFAULT_EXPORT_POWER_1 = "sensor.sigen_plant_grid_export_power"
DEFAULT_EXPORT_POWER_2 = "sensor.sigen_plant_2_grid_export_power"
DEFAULT_IMPORT_POWER_1 = "sensor.sigen_plant_grid_import_power"
DEFAULT_IMPORT_POWER_2 = "sensor.sigen_plant_2_grid_import_power"
