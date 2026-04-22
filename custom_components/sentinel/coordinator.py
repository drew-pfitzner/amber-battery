"""Sentinel Energy Manager coordinator."""

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.entity import State

from .const import (
    DOMAIN,
    SCAN_INTERVAL_SECONDS,
    MODE_FAILSAFE,
    MODE_SPIKE_EXPORT,
    MODE_OUTAGE_PREP,
    MODE_GRID_CHARGE,
    MODE_REBALANCE,
    MODE_MORNING_FLOOR,
    MODE_SELF_CONSUMPTION,
    CONF_SOC_1,
    CONF_MODE_1,
    CONF_HA_SWITCH_1,
    CONF_EXPORT_LIMIT_1,
    CONF_IMPORT_LIMIT_1,
    CONF_BACKUP_SOC_1,
    CONF_EXPORT_POWER_1,
    CONF_IMPORT_POWER_1,
    CONF_SOC_2,
    CONF_MODE_2,
    CONF_HA_SWITCH_2,
    CONF_EXPORT_LIMIT_2,
    CONF_IMPORT_LIMIT_2,
    CONF_BACKUP_SOC_2,
    CONF_EXPORT_POWER_2,
    CONF_IMPORT_POWER_2,
    OPT_REBALANCE_START_THRESHOLD,
    OPT_REBALANCE_STOP_THRESHOLD,
    OPT_REBALANCE_TRANSFER_RATE,
    DEFAULT_REBALANCE_START_THRESHOLD,
    DEFAULT_REBALANCE_STOP_THRESHOLD,
    DEFAULT_REBALANCE_TRANSFER_RATE,
    DEFAULT_MAX_GRID_LIMIT,
    DEFAULT_MAX_CHARGE_SOC,
    DEFAULT_BACKUP_BUFFER,
    MODE_MAXIMUM_SELF_CONSUMPTION,
    MODE_COMMAND_CHARGING_GRID_FIRST,
    MODE_COMMAND_DISCHARGING_ESS_FIRST,
)

_LOGGER = logging.getLogger(__name__)


class SentinelCoordinator(DataUpdateCoordinator[dict]):
    """Sentinel Energy Manager coordinator."""

    def __init__(self, hass: HomeAssistant, config_entry):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.config_entry = config_entry
        self._opts = {}
        self._current_mode = MODE_SELF_CONSUMPTION
        self._load_options()

    def _load_options(self):
        """Load options from config entry."""
        self._opts = {
            OPT_REBALANCE_START_THRESHOLD: self.config_entry.options.get(
                OPT_REBALANCE_START_THRESHOLD, DEFAULT_REBALANCE_START_THRESHOLD
            ),
            OPT_REBALANCE_STOP_THRESHOLD: self.config_entry.options.get(
                OPT_REBALANCE_STOP_THRESHOLD, DEFAULT_REBALANCE_STOP_THRESHOLD
            ),
            OPT_REBALANCE_TRANSFER_RATE: self.config_entry.options.get(
                OPT_REBALANCE_TRANSFER_RATE, DEFAULT_REBALANCE_TRANSFER_RATE
            ),
        }

    async def async_set_option(self, key: str, value: Any) -> None:
        """Set an option and persist to config entry."""
        self.hass.config_entries.async_update_entry(
            self.config_entry, options={**self.config_entry.options, key: value}
        )
        self._load_options()
        await self.async_refresh()

    async def _async_update_data(self) -> dict:
        """Fetch data from Sigen entities and evaluate priority mode."""
        try:
            # Read all Sigen entity states
            config = self.config_entry.data
            soc_1 = self._get_state_float(config[CONF_SOC_1])
            soc_2 = self._get_state_float(config[CONF_SOC_2])
            backup_soc_1 = self._get_state_float(config[CONF_BACKUP_SOC_1])
            backup_soc_2 = self._get_state_float(config[CONF_BACKUP_SOC_2])
            ha_switch_1 = self._get_state_bool(config[CONF_HA_SWITCH_1])
            ha_switch_2 = self._get_state_bool(config[CONF_HA_SWITCH_2])
            export_power_1 = self._get_state_float(config[CONF_EXPORT_POWER_1])
            export_power_2 = self._get_state_float(config[CONF_EXPORT_POWER_2])
            import_power_1 = self._get_state_float(config[CONF_IMPORT_POWER_1])
            import_power_2 = self._get_state_float(config[CONF_IMPORT_POWER_2])

            # Check for entity availability (failsafe if any unavailable)
            if any(
                val is None
                for val in [
                    soc_1,
                    soc_2,
                    backup_soc_1,
                    backup_soc_2,
                    ha_switch_1,
                    ha_switch_2,
                ]
            ):
                await self._async_apply_failsafe()
                self._current_mode = MODE_FAILSAFE
            else:
                # Evaluate priority
                new_mode = await self._evaluate_priority(
                    soc_1,
                    soc_2,
                    backup_soc_1,
                    backup_soc_2,
                    ha_switch_1,
                    ha_switch_2,
                )

                # Apply mode if changed
                if new_mode != self._current_mode:
                    await self._apply_mode(new_mode)
                    self._current_mode = new_mode
                else:
                    # Mode unchanged; re-apply to ensure state is correct
                    await self._apply_mode(self._current_mode)

            # Calculate net grid power
            net_grid_export = export_power_1 + export_power_2
            net_grid_import = import_power_1 + import_power_2
            net_grid_power = net_grid_export - net_grid_import

            # Clamp to 0 if negligible
            net_grid_import = max(0, net_grid_import)
            net_grid_export = max(0, net_grid_export)

            soc_diff = abs(soc_1 - soc_2)

            return {
                "soc_1": soc_1,
                "soc_2": soc_2,
                "soc_diff": soc_diff,
                "net_grid_power": net_grid_power,
                "net_grid_import": net_grid_import,
                "net_grid_export": net_grid_export,
                "active_mode": self._current_mode,
                "rebalancing_active": self._current_mode == MODE_REBALANCE,
                "failsafe_active": self._current_mode == MODE_FAILSAFE,
            }
        except Exception as err:
            _LOGGER.error("Error in coordinator update: %s", err)
            raise UpdateFailed(f"Error: {err}")

    async def _evaluate_priority(
        self,
        soc_1: float,
        soc_2: float,
        backup_soc_1: float,
        backup_soc_2: float,
        ha_switch_1: bool,
        ha_switch_2: bool,
    ) -> str:
        """Evaluate priority and return the highest-priority valid mode."""
        config = self.config_entry.data

        # Priority 1: FAILSAFE (already handled in _async_update_data)

        # Priority 2: SPIKE_EXPORT (stub)
        if self._is_mode_enabled(MODE_SPIKE_EXPORT):
            if await self._check_spike_export_conditions():
                return MODE_SPIKE_EXPORT

        # Priority 3: OUTAGE_PREP (stub)
        if self._is_mode_enabled(MODE_OUTAGE_PREP):
            if await self._check_outage_prep_conditions():
                return MODE_OUTAGE_PREP

        # Priority 4: GRID_CHARGE (stub)
        if self._is_mode_enabled(MODE_GRID_CHARGE):
            if await self._check_grid_charge_conditions():
                return MODE_GRID_CHARGE

        # Priority 5: REBALANCE
        if self._is_mode_enabled(MODE_REBALANCE):
            if self._check_rebalance_conditions(
                soc_1, soc_2, backup_soc_1, backup_soc_2, ha_switch_1, ha_switch_2
            ):
                return MODE_REBALANCE

        # Priority 6: MORNING_FLOOR (stub)
        if self._is_mode_enabled(MODE_MORNING_FLOOR):
            if await self._check_morning_floor_conditions():
                return MODE_MORNING_FLOOR

        # Priority 7: SELF_CONSUMPTION (always valid)
        return MODE_SELF_CONSUMPTION

    def _is_mode_enabled(self, mode: str) -> bool:
        """Check if a mode switch is enabled."""
        mode_switch_map = {
            MODE_REBALANCE: "switch.sentinel_rebalance_enabled",
            MODE_MORNING_FLOOR: "switch.sentinel_morning_floor_enabled",
            MODE_GRID_CHARGE: "switch.sentinel_grid_charge_enabled",
            MODE_SPIKE_EXPORT: "switch.sentinel_spike_export_enabled",
            MODE_OUTAGE_PREP: "switch.sentinel_outage_prep_enabled",
        }
        if mode not in mode_switch_map:
            return False
        entity_id = mode_switch_map[mode]
        state = self.hass.states.get(entity_id)
        return state and state.state == "on"

    async def _check_spike_export_conditions(self) -> bool:
        """Check if SPIKE_EXPORT conditions are met (stub)."""
        return False

    async def _check_outage_prep_conditions(self) -> bool:
        """Check if OUTAGE_PREP conditions are met (stub)."""
        return False

    async def _check_grid_charge_conditions(self) -> bool:
        """Check if GRID_CHARGE conditions are met (stub)."""
        return False

    def _check_rebalance_conditions(
        self,
        soc_1: float,
        soc_2: float,
        backup_soc_1: float,
        backup_soc_2: float,
        ha_switch_1: bool,
        ha_switch_2: bool,
    ) -> bool:
        """Check if REBALANCE conditions are met."""
        soc_diff = abs(soc_1 - soc_2)
        start_threshold = self._opts[OPT_REBALANCE_START_THRESHOLD]
        stop_threshold = self._opts[OPT_REBALANCE_STOP_THRESHOLD]

        # If already rebalancing, check stop condition
        if self._current_mode == MODE_REBALANCE:
            threshold = stop_threshold
        else:
            threshold = start_threshold

        # Safety conditions
        if not (ha_switch_1 and ha_switch_2):
            return False

        if soc_diff <= threshold:
            return False

        # Determine which plant would discharge
        plant_discharge_soc = max(soc_1, soc_2)
        plant_discharge_backup_soc = (
            backup_soc_1 if soc_1 >= soc_2 else backup_soc_2
        )

        # Check discharge plant has enough SOC
        if plant_discharge_soc <= (plant_discharge_backup_soc + DEFAULT_BACKUP_BUFFER):
            return False

        # Check charge plant is not already full
        plant_charge_soc = min(soc_1, soc_2)
        if plant_charge_soc >= DEFAULT_MAX_CHARGE_SOC:
            return False

        return True

    async def _check_morning_floor_conditions(self) -> bool:
        """Check if MORNING_FLOOR conditions are met (stub)."""
        return False

    async def _apply_mode(self, mode: str) -> None:
        """Apply the specified mode by calling the appropriate handler."""
        if mode == MODE_FAILSAFE:
            await self._async_apply_failsafe()
        elif mode == MODE_REBALANCE:
            await self._async_apply_rebalance()
        elif mode == MODE_SELF_CONSUMPTION:
            await self._async_apply_self_consumption()
        else:
            # Stub modes: default to self-consumption
            await self._async_apply_self_consumption()

    async def _async_apply_failsafe(self) -> None:
        """Apply FAILSAFE mode: both batteries to Maximum Self Consumption."""
        config = self.config_entry.data
        await self._set_both_mode(MODE_MAXIMUM_SELF_CONSUMPTION)
        await self._restore_all_grid_limits()

    async def _async_apply_rebalance(self) -> None:
        """Apply REBALANCE mode: port rebalancing logic from sigen_rebalancer."""
        config = self.config_entry.data
        soc_1 = self._get_state_float(config[CONF_SOC_1])
        soc_2 = self._get_state_float(config[CONF_SOC_2])
        ha_switch_1 = self._get_state_bool(config[CONF_HA_SWITCH_1])
        ha_switch_2 = self._get_state_bool(config[CONF_HA_SWITCH_2])

        # Check if conditions still met (safety)
        if not (ha_switch_1 and ha_switch_2):
            await self._async_apply_self_consumption()
            return

        backup_soc_1 = self._get_state_float(config[CONF_BACKUP_SOC_1])
        backup_soc_2 = self._get_state_float(config[CONF_BACKUP_SOC_2])

        soc_diff = abs(soc_1 - soc_2)
        stop_threshold = self._opts[OPT_REBALANCE_STOP_THRESHOLD]

        if soc_diff <= stop_threshold:
            await self._async_apply_self_consumption()
            return

        # Determine which plant discharges
        if soc_1 >= soc_2:
            plant_discharge = 1
            plant_charge = 2
            discharge_backup_soc = backup_soc_1
        else:
            plant_discharge = 2
            plant_charge = 1
            discharge_backup_soc = backup_soc_2

        # Check safety: discharge plant has headroom
        if plant_discharge == 1:
            if soc_1 <= (discharge_backup_soc + DEFAULT_BACKUP_BUFFER):
                await self._async_apply_self_consumption()
                return
        else:
            if soc_2 <= (discharge_backup_soc + DEFAULT_BACKUP_BUFFER):
                await self._async_apply_self_consumption()
                return

        # Check safety: charge plant is not full
        if plant_charge == 1:
            if soc_1 >= DEFAULT_MAX_CHARGE_SOC:
                await self._async_apply_self_consumption()
                return
        else:
            if soc_2 >= DEFAULT_MAX_CHARGE_SOC:
                await self._async_apply_self_consumption()
                return

        # Set modes and limits
        transfer_rate = self._opts[OPT_REBALANCE_TRANSFER_RATE]

        if plant_discharge == 1:
            # Plant 1 discharges, Plant 2 charges
            await self._call_service_set_mode(config[CONF_MODE_1], MODE_COMMAND_DISCHARGING_ESS_FIRST)
            await self._call_service_set_mode(config[CONF_MODE_2], MODE_COMMAND_CHARGING_GRID_FIRST)
            await self._call_service_set_limit(config[CONF_EXPORT_LIMIT_1], transfer_rate)
            await self._call_service_set_limit(config[CONF_IMPORT_LIMIT_2], transfer_rate)
            await self._call_service_set_limit(config[CONF_IMPORT_LIMIT_1], 0)
            await self._call_service_set_limit(config[CONF_EXPORT_LIMIT_2], 0)
        else:
            # Plant 2 discharges, Plant 1 charges
            await self._call_service_set_mode(config[CONF_MODE_2], MODE_COMMAND_DISCHARGING_ESS_FIRST)
            await self._call_service_set_mode(config[CONF_MODE_1], MODE_COMMAND_CHARGING_GRID_FIRST)
            await self._call_service_set_limit(config[CONF_EXPORT_LIMIT_2], transfer_rate)
            await self._call_service_set_limit(config[CONF_IMPORT_LIMIT_1], transfer_rate)
            await self._call_service_set_limit(config[CONF_IMPORT_LIMIT_2], 0)
            await self._call_service_set_limit(config[CONF_EXPORT_LIMIT_1], 0)

    async def _async_apply_self_consumption(self) -> None:
        """Apply SELF_CONSUMPTION mode: both batteries to Maximum Self Consumption."""
        await self._set_both_mode(MODE_MAXIMUM_SELF_CONSUMPTION)
        await self._restore_all_grid_limits()

    async def _set_both_mode(self, mode: str) -> None:
        """Set both batteries to the same mode."""
        config = self.config_entry.data
        await self._call_service_set_mode(config[CONF_MODE_1], mode)
        await self._call_service_set_mode(config[CONF_MODE_2], mode)

    async def _restore_all_grid_limits(self) -> None:
        """Restore all grid limits to maximum (7 kW)."""
        config = self.config_entry.data
        max_limit = DEFAULT_MAX_GRID_LIMIT
        await self._call_service_set_limit(config[CONF_EXPORT_LIMIT_1], max_limit)
        await self._call_service_set_limit(config[CONF_IMPORT_LIMIT_1], max_limit)
        await self._call_service_set_limit(config[CONF_EXPORT_LIMIT_2], max_limit)
        await self._call_service_set_limit(config[CONF_IMPORT_LIMIT_2], max_limit)

    async def _call_service_set_mode(self, entity_id: str, mode: str) -> None:
        """Set a battery mode via select service."""
        await self.hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity_id, "option": mode},
        )

    async def _call_service_set_limit(self, entity_id: str, value: float) -> None:
        """Set a grid limit via number service."""
        await self.hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": entity_id, "value": value},
        )

    def _get_state_float(self, entity_id: str) -> float | None:
        """Get a numeric state value."""
        state = self.hass.states.get(entity_id)
        if not state or state.state in ("unknown", "unavailable"):
            return None
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return None

    def _get_state_bool(self, entity_id: str) -> bool | None:
        """Get a boolean state value."""
        state = self.hass.states.get(entity_id)
        if not state or state.state in ("unknown", "unavailable"):
            return None
        return state.state == "on"
