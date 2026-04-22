"""Number entities for the Sigen Battery Rebalancer operational settings."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEFAULT_START_THRESHOLD,
    DEFAULT_STOP_THRESHOLD,
    DEFAULT_TRANSFER_RATE,
    DOMAIN,
    OPT_START_THRESHOLD,
    OPT_STOP_THRESHOLD,
    OPT_TRANSFER_RATE,
)
from .coordinator import RebalancerCoordinator


@dataclass(frozen=True, kw_only=True)
class RebalancerNumberDescription(NumberEntityDescription):
    option_key: str
    default_value: float


NUMBERS: tuple[RebalancerNumberDescription, ...] = (
    RebalancerNumberDescription(
        key="start_threshold",
        option_key=OPT_START_THRESHOLD,
        name="Rebalancing Start Threshold",
        icon="mdi:battery-arrow-up",
        native_min_value=1,
        native_max_value=50,
        native_step=0.5,
        native_unit_of_measurement=PERCENTAGE,
        default_value=DEFAULT_START_THRESHOLD,
    ),
    RebalancerNumberDescription(
        key="stop_threshold",
        option_key=OPT_STOP_THRESHOLD,
        name="Rebalancing Stop Threshold",
        icon="mdi:battery-arrow-down",
        native_min_value=0.5,
        native_max_value=20,
        native_step=0.5,
        native_unit_of_measurement=PERCENTAGE,
        default_value=DEFAULT_STOP_THRESHOLD,
    ),
    RebalancerNumberDescription(
        key="transfer_rate",
        option_key=OPT_TRANSFER_RATE,
        name="Rebalancing Transfer Rate",
        icon="mdi:transfer",
        native_min_value=0.5,
        native_max_value=7,
        native_step=0.5,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        default_value=DEFAULT_TRANSFER_RATE,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: RebalancerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        RebalancerNumber(coordinator, description) for description in NUMBERS
    )


class RebalancerNumber(CoordinatorEntity[RebalancerCoordinator], NumberEntity):
    """A number entity backed by a coordinator option.

    Changes are persisted immediately to the config entry options so they
    survive HA restarts.
    """

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: RebalancerCoordinator,
        description: RebalancerNumberDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = (
            f"{coordinator._config_entry.entry_id}_{description.key}"
        )

    @property
    def native_value(self) -> float:
        return float(
            self.coordinator._opts.get(
                self.entity_description.option_key,
                self.entity_description.default_value,
            )
        )

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_option(
            self.entity_description.option_key, value
        )
        self.async_write_ha_state()
