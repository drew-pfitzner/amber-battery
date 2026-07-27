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
    MODE_SOLAR_CURTAIL,
    MODE_GRID_CHARGE,
    MODE_OUTAGE_PREP,
)


@dataclass
class SentinelSwitchDescription(SwitchEntityDescription):
    """Description for a Sentinel mode switch."""

    mode_key: str | None = None


@dataclass
class SentinelOptionSwitchDescription(SwitchEntityDescription):
    """Description for a boolean-option switch (persisted in config options)."""

    option_key: str | None = None
    option_default: bool = False


SWITCH_DESCRIPTIONS = [
    SentinelSwitchDescription(
        key="rebalance_enabled",
        name="Enable Rebalancing",
        icon="mdi:scale-balance",
        mode_key=MODE_REBALANCE,
    ),
    SentinelSwitchDescription(
        key="solar_curtail_enabled",
        name="Enable Solar Curtail",
        icon="mdi:solar-power-variant-outline",
        mode_key=MODE_SOLAR_CURTAIL,
    ),
    SentinelSwitchDescription(
        key="grid_charge_enabled",
        name="Enable Grid Charging",
        icon="mdi:battery-charging",
        mode_key=MODE_GRID_CHARGE,
    ),
    SentinelSwitchDescription(
        key="outage_prep_enabled",
        name="Enable Outage Prep",
        icon="mdi:shield-alert",
        mode_key=MODE_OUTAGE_PREP,
    ),
]


# No option switches at present. GRID_CHARGE is always adaptive (targets are
# learned) — the old "Grid Charge Adaptive Target" toggle was removed in Stage 4.
OPTION_SWITCH_DESCRIPTIONS: list[SentinelOptionSwitchDescription] = []


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
    switches += [
        SentinelOptionSwitch(coordinator, description)
        for description in OPTION_SWITCH_DESCRIPTIONS
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
        return self.coordinator.is_mode_enabled(self.entity_description.mode_key)

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on the switch (enable mode)."""
        self.coordinator.set_mode_enabled(self.entity_description.mode_key, True)
        self.async_write_ha_state()
        await self.coordinator.async_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the switch (disable mode)."""
        self.coordinator.set_mode_enabled(self.entity_description.mode_key, False)
        self.async_write_ha_state()
        await self.coordinator.async_refresh()


class SentinelOptionSwitch(CoordinatorEntity, SwitchEntity):
    """Switch backed by a boolean config option."""

    entity_description: SentinelOptionSwitchDescription

    def __init__(
        self, coordinator, description: SentinelOptionSwitchDescription
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
        """Return True if the option is enabled."""
        return self.coordinator.config_entry.options.get(
            self.entity_description.option_key,
            self.entity_description.option_default,
        )

    async def async_turn_on(self, **kwargs) -> None:
        """Enable the option."""
        await self.coordinator.async_set_option(
            self.entity_description.option_key, True
        )

    async def async_turn_off(self, **kwargs) -> None:
        """Disable the option."""
        await self.coordinator.async_set_option(
            self.entity_description.option_key, False
        )
