"""Date entities for Sentinel Energy Manager."""

from datetime import date

from homeassistant.components.date import DateEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, OPT_OUTAGE_DATE


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up date entities for Sentinel."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([SentinelOutageDate(coordinator)])


class SentinelOutageDate(CoordinatorEntity, DateEntity):
    """Date entity for the next planned grid outage."""

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_outage_date"
        self._attr_name = "Outage Date"
        self._attr_icon = "mdi:calendar-alert"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> date | None:
        stored = self.coordinator.config_entry.options.get(OPT_OUTAGE_DATE, "")
        if not stored:
            return None
        try:
            return date.fromisoformat(stored)
        except ValueError:
            return None

    async def async_set_value(self, value: date) -> None:
        await self.coordinator.async_set_option(
            OPT_OUTAGE_DATE, value.isoformat() if value else ""
        )
