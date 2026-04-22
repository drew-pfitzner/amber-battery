"""Select entities for Sentinel Energy Manager."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities for Sentinel."""
    # Phase 1: No select entities
    # Phase 3 will add: charge_window_start, charge_window_end
    pass
