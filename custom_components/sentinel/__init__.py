"""Sentinel Energy Manager custom integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN
from .coordinator import SentinelCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_BACKFILL_LEARNING = "backfill_learning"

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.DATE,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Sentinel from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Create coordinator
    coordinator = SentinelCoordinator(hass, entry)

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register options listener
    entry.async_on_unload(entry.add_update_listener(async_update_listener))

    _async_register_services(hass)

    return True


def _async_register_services(hass: HomeAssistant) -> None:
    """Register domain-level services once."""
    if hass.services.has_service(DOMAIN, SERVICE_BACKFILL_LEARNING):
        return

    async def _handle_backfill_learning(call: ServiceCall) -> None:
        """Seed every Sentinel coordinator's learner from recorder history."""
        total = 0
        for data in hass.data.get(DOMAIN, {}).values():
            coordinator = data.get("coordinator")
            if coordinator is not None:
                total += await coordinator.async_backfill_learning()
        _LOGGER.info("backfill_learning service seeded %d day(s)", total)

    hass.services.async_register(
        DOMAIN, SERVICE_BACKFILL_LEARNING, _handle_backfill_learning,
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
