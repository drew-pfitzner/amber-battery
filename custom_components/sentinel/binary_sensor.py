"""Binary sensors for Sentinel Energy Manager."""

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors for Sentinel."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    sensors = [
        SentinelFailsafeActiveSensor(coordinator),
        SentinelRebalancingActiveSensor(coordinator),
        SentinelGridChargingActiveSensor(coordinator),
    ]

    async_add_entities(sensors)


class SentinelFailsafeActiveSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor showing if failsafe is active."""

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_failsafe_active"
        self._attr_name = "Failsafe Active"
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool | None:
        """Return True if failsafe is active."""
        return self.coordinator.data.get("failsafe_active", False)


class SentinelRebalancingActiveSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor showing if rebalancing is active."""

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_rebalancing_active"
        self._attr_name = "Rebalancing Active"
        self._attr_device_class = BinarySensorDeviceClass.RUNNING
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool | None:
        """Return True if rebalancing is active."""
        return self.coordinator.data.get("rebalancing_active", False)


class SentinelGridChargingActiveSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor showing if grid charging is active."""

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_grid_charging_active"
        self._attr_name = "Grid Charging Active"
        self._attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool | None:
        """Return True if grid charging is active."""
        return self.coordinator.data.get("grid_charging_active", False)
