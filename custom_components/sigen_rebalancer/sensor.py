"""Sensor entities for the Sigen Battery Rebalancer."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RebalancerCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: RebalancerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            NetGridPowerSensor(coordinator),
            NetGridImportSensor(coordinator),
            NetGridExportSensor(coordinator),
            SocDifferenceSensor(coordinator),
        ]
    )


class _BaseSensor(CoordinatorEntity[RebalancerCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: RebalancerCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator._config_entry.entry_id}_{key}"

    @property
    def native_value(self):
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._key)


class NetGridPowerSensor(_BaseSensor):
    """Signed net grid power (positive = exporting, negative = importing)."""

    _attr_name = "Net Grid Power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

    def __init__(self, coordinator: RebalancerCoordinator) -> None:
        super().__init__(coordinator, "net_grid_power")


class NetGridImportSensor(_BaseSensor):
    """Net grid draw — zero during a balanced rebalance."""

    _attr_name = "Net Grid Import Power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

    def __init__(self, coordinator: RebalancerCoordinator) -> None:
        super().__init__(coordinator, "net_grid_import")


class NetGridExportSensor(_BaseSensor):
    """Net grid feed-in — zero during a balanced rebalance."""

    _attr_name = "Net Grid Export Power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

    def __init__(self, coordinator: RebalancerCoordinator) -> None:
        super().__init__(coordinator, "net_grid_export")


class SocDifferenceSensor(_BaseSensor):
    """Absolute SOC difference between the two batteries."""

    _attr_name = "Battery SOC Difference"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:battery-arrow-up-outline"

    def __init__(self, coordinator: RebalancerCoordinator) -> None:
        super().__init__(coordinator, "soc_diff")
