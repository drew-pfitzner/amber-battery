"""Sensors for Sentinel Energy Manager."""

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower, UnitOfEnergy, PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

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

    @property
    def native_value(self) -> float | None:
        """Return mean SOC."""
        soc_1 = self.coordinator.data.get("soc_1")
        soc_2 = self.coordinator.data.get("soc_2")
        if soc_1 is not None and soc_2 is not None:
            return (soc_1 + soc_2) / 2
        return None
