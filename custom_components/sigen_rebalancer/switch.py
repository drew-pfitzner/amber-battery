"""Switch entity for the Sigen Battery Rebalancer."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    async_add_entities([RebalancingEnabledSwitch(coordinator)])


class RebalancingEnabledSwitch(
    CoordinatorEntity[RebalancerCoordinator], SwitchEntity
):
    """Enable/disable the rebalancing logic.

    When turned on, the coordinator will start transferring charge on the next
    poll cycle if SOC conditions are met. Turning off immediately stops any
    active transfer and returns both batteries to Maximum Self Consumption.
    """

    _attr_has_entity_name = True
    _attr_name = "Battery Rebalancing Enabled"
    _attr_icon = "mdi:battery-sync-outline"

    def __init__(self, coordinator: RebalancerCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator._config_entry.entry_id}_rebalancing_enabled"

    @property
    def is_on(self) -> bool:
        return self.coordinator.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_enable()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_disable()
