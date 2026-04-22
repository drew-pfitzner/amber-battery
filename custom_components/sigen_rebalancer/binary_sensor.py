"""Binary sensor entities for the Sigen Battery Rebalancer."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
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
    async_add_entities([RebalancingActiveSensor(coordinator)])


class RebalancingActiveSensor(
    CoordinatorEntity[RebalancerCoordinator], BinarySensorEntity
):
    """True while charge transfer between batteries is actively running."""

    _attr_has_entity_name = True
    _attr_name = "Battery Rebalancing Active"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:battery-sync"

    def __init__(self, coordinator: RebalancerCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator._config_entry.entry_id}_rebalancing_active"

    @property
    def is_on(self) -> bool:
        if self.coordinator.data is None:
            return False
        return bool(self.coordinator.data.get("active", False))
