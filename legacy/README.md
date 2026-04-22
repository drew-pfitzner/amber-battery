# Legacy Files

These YAML files are the original pre-integration implementation of rebalancing logic and net grid sensors. They are superseded by the **Sentinel** custom integration (`custom_components/sentinel/`).

- `rebalancing_helpers.yaml` — HA helpers (input_boolean, input_number)
- `rebalancing_automation.yaml` — Two automations (Start, Monitor) that implement rebalancing logic
- `net_grid_sensors.yaml` — Template sensors for net grid power calculation

**Do not use these in your HA config.** They are kept here for reference during the Sentinel port only. Once Sentinel is deployed and working, delete these files.
