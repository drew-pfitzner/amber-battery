"""Number entities for Sentinel Energy Manager."""

from dataclasses import dataclass
from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import PERCENTAGE, UnitOfPower

from .const import (
    DOMAIN,
    OPT_REBALANCE_START_THRESHOLD,
    OPT_REBALANCE_STOP_THRESHOLD,
    OPT_REBALANCE_TRANSFER_RATE,
    OPT_SOLAR_CURTAIL_PRICE_THRESHOLD,
    OPT_MORNING_FLOOR_SOC,
    DEFAULT_REBALANCE_START_THRESHOLD,
    DEFAULT_REBALANCE_STOP_THRESHOLD,
    DEFAULT_REBALANCE_TRANSFER_RATE,
    DEFAULT_SOLAR_CURTAIL_PRICE_THRESHOLD,
    DEFAULT_MORNING_FLOOR_SOC,
)


@dataclass
class SentinelNumberDescription(NumberEntityDescription):
    """Description for a Sentinel number entity."""

    option_key: str | None = None


NUMBER_DESCRIPTIONS = [
    SentinelNumberDescription(
        key="rebalance_start_threshold",
        name="Rebalance Start Threshold",
        icon="mdi:scale-balance",
        native_min_value=1.0,
        native_max_value=50.0,
        native_step=1.0,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.BOX,
        option_key=OPT_REBALANCE_START_THRESHOLD,
    ),
    SentinelNumberDescription(
        key="rebalance_stop_threshold",
        name="Rebalance Stop Threshold",
        icon="mdi:scale-balance",
        native_min_value=1.0,
        native_max_value=20.0,
        native_step=1.0,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.BOX,
        option_key=OPT_REBALANCE_STOP_THRESHOLD,
    ),
    SentinelNumberDescription(
        key="rebalance_transfer_rate",
        name="Rebalance Transfer Rate",
        icon="mdi:speedometer",
        native_min_value=0.5,
        native_max_value=7.0,
        native_step=0.5,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        option_key=OPT_REBALANCE_TRANSFER_RATE,
    ),
    SentinelNumberDescription(
        key="solar_curtail_price_threshold",
        name="Solar Curtail Price Threshold",
        icon="mdi:currency-usd",
        native_min_value=-0.50,
        native_max_value=0.20,
        native_step=0.01,
        native_unit_of_measurement="$/kWh",
        mode=NumberMode.BOX,
        option_key=OPT_SOLAR_CURTAIL_PRICE_THRESHOLD,
    ),
    SentinelNumberDescription(
        key="morning_floor_soc",
        name="Morning Floor SOC",
        icon="mdi:battery-arrow-up",
        native_min_value=10.0,
        native_max_value=80.0,
        native_step=5.0,
        native_unit_of_measurement=PERCENTAGE,
        option_key=OPT_MORNING_FLOOR_SOC,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities for Sentinel."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    numbers = [
        SentinelNumber(coordinator, description)
        for description in NUMBER_DESCRIPTIONS
    ]

    async_add_entities(numbers)


class SentinelNumber(CoordinatorEntity, NumberEntity):
    """Number entity for configurable Sentinel parameters."""

    entity_description: SentinelNumberDescription

    def __init__(
        self, coordinator, description: SentinelNumberDescription
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{description.key}"
        self._attr_name = description.name
        self._attr_device_info = coordinator.device_info

    _DEFAULTS = {
        OPT_REBALANCE_START_THRESHOLD: DEFAULT_REBALANCE_START_THRESHOLD,
        OPT_REBALANCE_STOP_THRESHOLD: DEFAULT_REBALANCE_STOP_THRESHOLD,
        OPT_REBALANCE_TRANSFER_RATE: DEFAULT_REBALANCE_TRANSFER_RATE,
        OPT_SOLAR_CURTAIL_PRICE_THRESHOLD: DEFAULT_SOLAR_CURTAIL_PRICE_THRESHOLD,
        OPT_MORNING_FLOOR_SOC: DEFAULT_MORNING_FLOOR_SOC,
    }

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        option_key = self.entity_description.option_key
        default = self._DEFAULTS.get(option_key)
        if default is not None:
            return self.coordinator.config_entry.options.get(option_key, default)
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        await self.coordinator.async_set_option(
            self.entity_description.option_key, value
        )
