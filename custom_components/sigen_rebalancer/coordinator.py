"""DataUpdateCoordinator for the Sigen Battery Rebalancer."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_BACKUP_SOC_1,
    CONF_BACKUP_SOC_2,
    CONF_EXPORT_LIMIT_1,
    CONF_EXPORT_LIMIT_2,
    CONF_EXPORT_POWER_1,
    CONF_EXPORT_POWER_2,
    CONF_HA_SWITCH_1,
    CONF_HA_SWITCH_2,
    CONF_IMPORT_LIMIT_1,
    CONF_IMPORT_LIMIT_2,
    CONF_IMPORT_POWER_1,
    CONF_IMPORT_POWER_2,
    CONF_MODE_1,
    CONF_MODE_2,
    CONF_SOC_1,
    CONF_SOC_2,
    DEFAULT_BACKUP_BUFFER,
    DEFAULT_MAX_CHARGE_SOC,
    DEFAULT_MAX_GRID_LIMIT,
    DEFAULT_START_THRESHOLD,
    DEFAULT_STOP_THRESHOLD,
    DEFAULT_TRANSFER_RATE,
    DOMAIN,
    MODE_CHARGE,
    MODE_DISCHARGE,
    MODE_SELF_CONSUMPTION,
    OPT_START_THRESHOLD,
    OPT_STOP_THRESHOLD,
    OPT_TRANSFER_RATE,
    SCAN_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


class RebalancerCoordinator(DataUpdateCoordinator[dict]):
    """Manages rebalancing logic and aggregates sensor data every 30 seconds."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self._config_entry = config_entry
        self._cfg = config_entry.data
        self._opts = dict(config_entry.options)

        # Operational state — disabled/inactive on startup for safety
        self.enabled: bool = False
        self.active: bool = False

    # ── Option accessors ──────────────────────────────────────────────────────

    @property
    def start_threshold(self) -> float:
        return float(self._opts.get(OPT_START_THRESHOLD, DEFAULT_START_THRESHOLD))

    @property
    def stop_threshold(self) -> float:
        return float(self._opts.get(OPT_STOP_THRESHOLD, DEFAULT_STOP_THRESHOLD))

    @property
    def transfer_rate(self) -> float:
        return float(self._opts.get(OPT_TRANSFER_RATE, DEFAULT_TRANSFER_RATE))

    # ── HA state helpers ──────────────────────────────────────────────────────

    def _float(self, entity_id: str, default: float = -1.0) -> float:
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable", "none"):
            return default
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return default

    def _is_on(self, entity_id: str) -> bool:
        state = self.hass.states.get(entity_id)
        return state is not None and state.state == "on"

    # ── Main update loop ──────────────────────────────────────────────────────

    async def _async_update_data(self) -> dict:
        cfg = self._cfg

        soc_1 = self._float(cfg[CONF_SOC_1])
        soc_2 = self._float(cfg[CONF_SOC_2])
        backup_1 = self._float(cfg[CONF_BACKUP_SOC_1], 20.0)
        backup_2 = self._float(cfg[CONF_BACKUP_SOC_2], 20.0)
        ha_sw_1 = self._is_on(cfg[CONF_HA_SWITCH_1])
        ha_sw_2 = self._is_on(cfg[CONF_HA_SWITCH_2])
        export_pwr_1 = self._float(cfg[CONF_EXPORT_POWER_1], 0.0)
        export_pwr_2 = self._float(cfg[CONF_EXPORT_POWER_2], 0.0)
        import_pwr_1 = self._float(cfg[CONF_IMPORT_POWER_1], 0.0)
        import_pwr_2 = self._float(cfg[CONF_IMPORT_POWER_2], 0.0)

        soc_valid = soc_1 >= 0 and soc_2 >= 0
        soc_diff = abs(soc_1 - soc_2) if soc_valid else 0.0

        # Which plant currently has more charge (re-evaluated each cycle to
        # handle crossover mid-rebalance)
        plant1_discharging = soc_1 >= soc_2

        if self.active:
            await self._async_monitor(
                soc_valid, soc_diff, plant1_discharging,
                soc_1, soc_2, backup_1, backup_2, ha_sw_1, ha_sw_2,
            )
        elif self.enabled and soc_valid:
            await self._async_try_start(
                soc_diff, plant1_discharging,
                soc_1, soc_2, backup_1, backup_2, ha_sw_1, ha_sw_2,
            )

        net_power = round(
            (export_pwr_1 + export_pwr_2) - (import_pwr_1 + import_pwr_2), 2
        )
        net_import = round(
            max((import_pwr_1 + import_pwr_2) - (export_pwr_1 + export_pwr_2), 0.0), 2
        )
        net_export = round(max(net_power, 0.0), 2)

        return {
            "soc_1": soc_1,
            "soc_2": soc_2,
            "soc_diff": soc_diff,
            "net_grid_power": net_power,
            "net_grid_import": net_import,
            "net_grid_export": net_export,
            "active": self.active,
            "enabled": self.enabled,
        }

    async def _async_monitor(
        self,
        soc_valid: bool,
        soc_diff: float,
        plant1_discharging: bool,
        soc_1: float,
        soc_2: float,
        backup_1: float,
        backup_2: float,
        ha_sw_1: bool,
        ha_sw_2: bool,
    ) -> None:
        """Called each cycle while rebalancing is active. Stop or re-apply."""
        discharge_soc = soc_1 if plant1_discharging else soc_2
        charge_soc = soc_2 if plant1_discharging else soc_1
        discharge_backup = backup_1 if plant1_discharging else backup_2

        should_stop = (
            not self.enabled
            or not soc_valid
            or not ha_sw_1
            or not ha_sw_2
            or soc_diff < self.stop_threshold
            or discharge_soc <= discharge_backup + DEFAULT_BACKUP_BUFFER
            or charge_soc >= DEFAULT_MAX_CHARGE_SOC
        )

        if should_stop:
            _LOGGER.info(
                "Rebalancing stopping — diff=%.1f%%, soc1=%.1f%%, soc2=%.1f%%",
                soc_diff, soc_1, soc_2,
            )
            await self._async_stop()
        else:
            # Re-apply every cycle: handles crossover and live rate changes
            _LOGGER.debug(
                "Rebalancing active — diff=%.1f%%, plant1_discharging=%s",
                soc_diff, plant1_discharging,
            )
            await self._async_apply(plant1_discharging)

    async def _async_try_start(
        self,
        soc_diff: float,
        plant1_discharging: bool,
        soc_1: float,
        soc_2: float,
        backup_1: float,
        backup_2: float,
        ha_sw_1: bool,
        ha_sw_2: bool,
    ) -> None:
        """Called each cycle while idle. Start if conditions are met."""
        discharge_soc = soc_1 if plant1_discharging else soc_2
        charge_soc = soc_2 if plant1_discharging else soc_1
        discharge_backup = backup_1 if plant1_discharging else backup_2

        can_start = (
            ha_sw_1
            and ha_sw_2
            and soc_diff > self.start_threshold
            and discharge_soc > discharge_backup + DEFAULT_BACKUP_BUFFER
            and charge_soc < DEFAULT_MAX_CHARGE_SOC
        )

        if can_start:
            _LOGGER.info(
                "Rebalancing starting — diff=%.1f%%, plant1_discharging=%s",
                soc_diff, plant1_discharging,
            )
            await self._async_apply(plant1_discharging)
            self.active = True

    # ── Battery control ───────────────────────────────────────────────────────

    async def _async_apply(self, plant1_discharging: bool) -> None:
        """Set battery modes and grid limits for the current transfer direction.

        All four limits are written every cycle so that a SOC crossover
        (direction change mid-rebalance) never leaves a stale limit active.
        """
        cfg = self._cfg
        rate = self.transfer_rate

        if plant1_discharging:
            discharge_export = cfg[CONF_EXPORT_LIMIT_1]
            discharge_import = cfg[CONF_IMPORT_LIMIT_1]   # no restriction needed
            charge_export = cfg[CONF_EXPORT_LIMIT_2]       # no restriction needed
            charge_import = cfg[CONF_IMPORT_LIMIT_2]
            discharge_mode = cfg[CONF_MODE_1]
            charge_mode = cfg[CONF_MODE_2]
        else:
            discharge_export = cfg[CONF_EXPORT_LIMIT_2]
            discharge_import = cfg[CONF_IMPORT_LIMIT_2]
            charge_export = cfg[CONF_EXPORT_LIMIT_1]
            charge_import = cfg[CONF_IMPORT_LIMIT_1]
            discharge_mode = cfg[CONF_MODE_2]
            charge_mode = cfg[CONF_MODE_1]

        await self.hass.services.async_call(
            "number", "set_value", {"entity_id": discharge_export, "value": rate}
        )
        await self.hass.services.async_call(
            "number", "set_value", {"entity_id": discharge_import, "value": DEFAULT_MAX_GRID_LIMIT}
        )
        await self.hass.services.async_call(
            "number", "set_value", {"entity_id": charge_export, "value": DEFAULT_MAX_GRID_LIMIT}
        )
        await self.hass.services.async_call(
            "number", "set_value", {"entity_id": charge_import, "value": rate}
        )
        await self.hass.services.async_call(
            "select", "select_option",
            {"entity_id": discharge_mode, "option": MODE_DISCHARGE},
        )
        await self.hass.services.async_call(
            "select", "select_option",
            {"entity_id": charge_mode, "option": MODE_CHARGE},
        )

    async def _async_stop(self) -> None:
        """Return both batteries to self-consumption and restore all grid limits."""
        self.active = False
        cfg = self._cfg

        for entity_id in (
            cfg[CONF_EXPORT_LIMIT_1],
            cfg[CONF_EXPORT_LIMIT_2],
            cfg[CONF_IMPORT_LIMIT_1],
            cfg[CONF_IMPORT_LIMIT_2],
        ):
            await self.hass.services.async_call(
                "number", "set_value",
                {"entity_id": entity_id, "value": DEFAULT_MAX_GRID_LIMIT},
            )

        for entity_id in (cfg[CONF_MODE_1], cfg[CONF_MODE_2]):
            await self.hass.services.async_call(
                "select", "select_option",
                {"entity_id": entity_id, "option": MODE_SELF_CONSUMPTION},
            )

    # ── Public control API ────────────────────────────────────────────────────

    async def async_enable(self) -> None:
        """Enable rebalancing — next poll cycle will start if conditions met."""
        self.enabled = True
        await self.async_refresh()

    async def async_disable(self) -> None:
        """Disable rebalancing and immediately stop if active."""
        self.enabled = False
        if self.active:
            await self._async_stop()
        await self.async_refresh()

    async def async_set_option(self, key: str, value: float) -> None:
        """Persist an option change back to the config entry."""
        self._opts[key] = value
        self.hass.config_entries.async_update_entry(
            self._config_entry, options=dict(self._opts)
        )
