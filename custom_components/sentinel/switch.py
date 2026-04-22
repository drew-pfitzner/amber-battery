"""Switches for Sentinel Energy Manager."""

from dataclasses import dataclass
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MODE_REBALANCE,
    MODE_MORNING_FLOOR,
    MODE_GRID_CHARGE,
    MODE_SPIKE_EXPORT,
    MODE_OUTAGE_PREP,
    OPT_REBALANCE_START_THRESHOLD,
    OPT_REBALANCE_STOP_THRESHOLD,
    OPT_REBALANCE_TRANSFER_RATE,
    DEFAULT_REBALANCE_START_THRESHOLD,
    DEFAULT_REBALANCE_STOP_THRESHOLD,
    DEFAULT_REBALANCE_TRANSFER_RATE,
)


@dataclass
class SentinelSwitchDescription(SwitchEntityDescription):
    """Description for a Sentinel mode switch."""

    mode_key: str | None = None


SWITCH_DESCRIPTIONS = [
    SentinelSwitchDescription(
        key="rebalance_enabled",
        name="Enable Rebalancing",
        icon="mdi:scale-balance",
        mode_key=MODE_REBALANCE,
    ),
    SentinelSwitchDescription(
        key="morning_floor_enabled",
        name="Enable Morning Floor",
        icon="mdi:power-sleep",
        mode_key=MODE_MORNING_FLOOR,
    ),
    SentinelSwitchDescription(
        key="grid_charge_enabled",
        name="Enable Grid Charging",
        icon="mdi:battery-charging",
        mode_key=MODE_GRID_CHARGE,
    ),
    SentinelSwitchDescription(
        key="spike_export_enabled",
        name="Enable Spike Export",
        icon="mdi:lightning-bolt",
        mode_key=MODE_SPIKE_EXPORT,
    ),
    SentinelSwitchDescription(
        key="outage_prep_enabled",
        name="Enable Outage Prep",
        icon="mdi:shield-alert",
        mode_key=MODE_OUTAGE_PREP,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches for Sentinel."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    switches = [
        SentinelModeSwitch(coordinator, description)
        for description in SWITCH_DESCRIPTIONS
    ]

    async_add_entities(switches)


class SentinelModeSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to enable/disable a specific mode."""

    entity_description: SentinelSwitchDescription

    def __init__(
        self, coordinator, description: SentinelSwitchDescription
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{description.key}"
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool:
        """Return True if switch is on."""
        # Read from config entry options
        option_key = f"{self.entity_description.mode_key.lower()}_enabled"
        # For Phase 1, all switches default to OFF (not in options yet)
        return self.coordinator.config_entry.options.get(option_key, False)

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on the switch (enable mode)."""
        option_key = f"{self.entity_description.mode_key.lower()}_enabled"
        await self.coordinator.async_set_option(option_key, True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the switch (disable mode)."""
        option_key = f"{self.entity_description.mode_key.lower()}_enabled"
        await self.coordinator.async_set_option(option_key, False)
