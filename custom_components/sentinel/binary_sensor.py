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
        SentinelSolarCurtailActiveSensor(coordinator),
        SentinelMorningFloorActiveSensor(coordinator),
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


class SentinelSolarCurtailActiveSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor showing if solar curtail is active."""

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_solar_curtail_active"
        self._attr_name = "Solar Curtail Active"
        self._attr_device_class = BinarySensorDeviceClass.RUNNING
        self._attr_icon = "mdi:solar-power-variant-outline"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool | None:
        """Return True if solar curtail is active."""
        return self.coordinator.data.get("solar_curtail_active", False)


class SentinelMorningFloorActiveSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor showing if morning floor mode is active."""

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_morning_floor_active"
        self._attr_name = "Morning Floor Active"
        self._attr_device_class = BinarySensorDeviceClass.RUNNING
        self._attr_icon = "mdi:battery-arrow-up"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool | None:
        """Return True if morning floor is active."""
        return self.coordinator.data.get("morning_floor_active", False)


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
