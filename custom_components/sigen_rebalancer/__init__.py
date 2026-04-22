"""Sigen Battery Rebalancer — custom Home Assistant integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN
from .coordinator import RebalancerCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    coordinator = RebalancerCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload coordinator when options change (threshold/rate updates from UI)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Services callable from automations, scripts, Amber integrations, etc.
    async def _handle_start(call: ServiceCall) -> None:  # noqa: ARG001
        await coordinator.async_enable()

    async def _handle_stop(call: ServiceCall) -> None:  # noqa: ARG001
        await coordinator.async_disable()

    hass.services.async_register(DOMAIN, "start_rebalancing", _handle_start)
    hass.services.async_register(DOMAIN, "stop_rebalancing", _handle_stop)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the integration."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
        # Only remove services if no other entries remain
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, "start_rebalancing")
            hass.services.async_remove(DOMAIN, "stop_rebalancing")
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Refresh coordinator when options are changed via the UI."""
    coordinator: RebalancerCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator._opts = dict(entry.options)
    await coordinator.async_refresh()
