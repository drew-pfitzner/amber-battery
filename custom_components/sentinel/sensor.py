"""Sensors for Sentinel Energy Manager."""

from datetime import datetime
import logging

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower, UnitOfEnergy, PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors for Sentinel."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    sensors = [
        SentinelActiveModeSensor(coordinator),
        SentinelNetGridPowerSensor(coordinator),
        SentinelMeanBatterySocSensor(coordinator),
        SentinelCombinedPvPowerSensor(coordinator),
        SentinelDailyGridImportSensor(coordinator),
        SentinelDailyGridExportSensor(coordinator),
    ]

    async_add_entities(sensors)


class SentinelActiveModeSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing the current active mode."""

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_active_mode"
        self._attr_name = "Active Mode"
        self._attr_icon = "mdi:lightbulb-multiple"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> str:
        """Return the current mode."""
        return self.coordinator.data.get("active_mode", "UNKNOWN")


class SentinelNetGridPowerSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing net grid power (signed)."""

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_net_grid_power"
        self._attr_name = "Net Grid Power"
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> float | None:
        """Return net grid power (positive = export)."""
        return self.coordinator.data.get("net_grid_power")


class SentinelMeanBatterySocSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing mean battery SOC."""

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_mean_battery_soc"
        self._attr_name = "Mean Battery SOC"
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_icon = "mdi:battery"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> float | None:
        """Return mean SOC."""
        soc_1 = self.coordinator.data.get("soc_1")
        soc_2 = self.coordinator.data.get("soc_2")
        if soc_1 is not None and soc_2 is not None:
            return (soc_1 + soc_2) / 2
        return None


class SentinelCombinedPvPowerSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing combined PV production from both plants."""

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_combined_pv_power"
        self._attr_name = "Combined PV Power"
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:solar-power"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> float | None:
        """Return combined PV power."""
        return self.coordinator.data.get("combined_pv_power")


class SentinelDailyEnergySensor(CoordinatorEntity, RestoreEntity, SensorEntity):
    """Base class for daily energy accumulation sensors.

    Integrates instantaneous power (kW) over time to produce daily kWh.
    Resets at midnight local time. Survives restarts via RestoreEntity.
    """

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator, key: str, name: str, icon: str, power_key: str):
        """Initialize the daily energy sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{key}"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_device_info = coordinator.device_info
        self._power_key = power_key
        self._accumulated_kwh: float = 0.0
        self._last_update: datetime | None = None
        self._last_reset_date: str | None = None

    async def async_added_to_hass(self) -> None:
        """Restore state on startup."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            try:
                restored_value = float(last_state.state)
                restored_date = (last_state.attributes or {}).get("last_reset_date")
                today = dt_util.now().date().isoformat()
                if restored_date == today:
                    self._accumulated_kwh = restored_value
                    self._last_reset_date = today
                    _LOGGER.debug(
                        "Restored %s: %.3f kWh for %s",
                        self._attr_name, restored_value, today,
                    )
                else:
                    self._accumulated_kwh = 0.0
                    self._last_reset_date = today
            except (ValueError, TypeError):
                self._last_reset_date = dt_util.now().date().isoformat()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Accumulate energy on each coordinator update."""
        now = dt_util.now()
        today = now.date().isoformat()

        if self._last_reset_date != today:
            self._accumulated_kwh = 0.0
            self._last_reset_date = today
            self._last_update = None

        power_kw = self.coordinator.data.get(self._power_key)
        if power_kw is not None and power_kw > 0 and self._last_update is not None:
            elapsed_hours = (now - self._last_update).total_seconds() / 3600
            if 0 < elapsed_hours < 0.1:  # Skip if gap > 6 min
                self._accumulated_kwh += power_kw * elapsed_hours

        self._last_update = now
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        """Return accumulated energy today."""
        return round(self._accumulated_kwh, 3)

    @property
    def extra_state_attributes(self) -> dict:
        """Store reset date for restore logic."""
        return {"last_reset_date": self._last_reset_date}


class SentinelDailyGridImportSensor(SentinelDailyEnergySensor):
    """Daily kWh imported from the grid."""

    def __init__(self, coordinator):
        super().__init__(
            coordinator,
            key="daily_grid_import",
            name="Daily Grid Import",
            icon="mdi:transmission-tower-import",
            power_key="net_grid_import",
        )


class SentinelDailyGridExportSensor(SentinelDailyEnergySensor):
    """Daily kWh exported to the grid."""

    def __init__(self, coordinator):
        super().__init__(
            coordinator,
            key="daily_grid_export",
            name="Daily Grid Export",
            icon="mdi:transmission-tower-export",
            power_key="net_grid_export",
        )
