"""Config flow for Sentinel Energy Manager."""

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigEntry, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_SOC_1,
    CONF_MODE_1,
    CONF_HA_SWITCH_1,
    CONF_EXPORT_LIMIT_1,
    CONF_IMPORT_LIMIT_1,
    CONF_BACKUP_SOC_1,
    CONF_EXPORT_POWER_1,
    CONF_IMPORT_POWER_1,
    CONF_SOC_2,
    CONF_MODE_2,
    CONF_HA_SWITCH_2,
    CONF_EXPORT_LIMIT_2,
    CONF_IMPORT_LIMIT_2,
    CONF_BACKUP_SOC_2,
    CONF_EXPORT_POWER_2,
    CONF_IMPORT_POWER_2,
    CONF_CAPACITY_KWH,
    CONF_AMBER_GENERAL_PRICE,
    CONF_AMBER_GENERAL_FORECAST,
    CONF_AMBER_PRICE_SPIKE,
    CONF_SOLCAST_TODAY,
    CONF_SOLCAST_TOMORROW,
    OPT_REBALANCE_START_THRESHOLD,
    OPT_REBALANCE_STOP_THRESHOLD,
    OPT_REBALANCE_TRANSFER_RATE,
    DEFAULT_BATTERY_CAPACITY_KWH,
    DEFAULT_REBALANCE_START_THRESHOLD,
    DEFAULT_REBALANCE_STOP_THRESHOLD,
    DEFAULT_REBALANCE_TRANSFER_RATE,
    DEFAULT_SOC_1,
    DEFAULT_MODE_1,
    DEFAULT_HA_SWITCH_1,
    DEFAULT_EXPORT_LIMIT_1,
    DEFAULT_IMPORT_LIMIT_1,
    DEFAULT_BACKUP_SOC_1,
    DEFAULT_EXPORT_POWER_1,
    DEFAULT_IMPORT_POWER_1,
    DEFAULT_SOC_2,
    DEFAULT_MODE_2,
    DEFAULT_HA_SWITCH_2,
    DEFAULT_EXPORT_LIMIT_2,
    DEFAULT_IMPORT_LIMIT_2,
    DEFAULT_BACKUP_SOC_2,
    DEFAULT_EXPORT_POWER_2,
    DEFAULT_IMPORT_POWER_2,
)


class SentinelConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Sentinel."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """First step: Plant 1 entity configuration."""
        if not hasattr(self, "_collected_data"):
            self._collected_data = {}

        if user_input is not None:
            self._collected_data.update(user_input)
            return await self.async_step_plant2()

        schema = vol.Schema(
            {
                vol.Required(CONF_SOC_1, default=DEFAULT_SOC_1): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(CONF_MODE_1, default=DEFAULT_MODE_1): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="select")
                ),
                vol.Required(CONF_HA_SWITCH_1, default=DEFAULT_HA_SWITCH_1): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="switch")
                ),
                vol.Required(CONF_EXPORT_LIMIT_1, default=DEFAULT_EXPORT_LIMIT_1): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="number")
                ),
                vol.Required(CONF_IMPORT_LIMIT_1, default=DEFAULT_IMPORT_LIMIT_1): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="number")
                ),
                vol.Required(CONF_BACKUP_SOC_1, default=DEFAULT_BACKUP_SOC_1): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="number")
                ),
                vol.Required(CONF_EXPORT_POWER_1, default=DEFAULT_EXPORT_POWER_1): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(CONF_IMPORT_POWER_1, default=DEFAULT_IMPORT_POWER_1): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_plant2(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Second step: Plant 2 entity configuration."""
        if user_input is not None:
            self._collected_data.update(user_input)
            return await self.async_step_capacity()

        schema = vol.Schema(
            {
                vol.Required(CONF_SOC_2, default=DEFAULT_SOC_2): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(CONF_MODE_2, default=DEFAULT_MODE_2): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="select")
                ),
                vol.Required(CONF_HA_SWITCH_2, default=DEFAULT_HA_SWITCH_2): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="switch")
                ),
                vol.Required(CONF_EXPORT_LIMIT_2, default=DEFAULT_EXPORT_LIMIT_2): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="number")
                ),
                vol.Required(CONF_IMPORT_LIMIT_2, default=DEFAULT_IMPORT_LIMIT_2): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="number")
                ),
                vol.Required(CONF_BACKUP_SOC_2, default=DEFAULT_BACKUP_SOC_2): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="number")
                ),
                vol.Required(CONF_EXPORT_POWER_2, default=DEFAULT_EXPORT_POWER_2): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(CONF_IMPORT_POWER_2, default=DEFAULT_IMPORT_POWER_2): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
            }
        )

        return self.async_show_form(step_id="plant2", data_schema=schema)

    async def async_step_capacity(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Third step: Battery capacity."""
        if user_input is not None:
            self._collected_data.update(user_input)
            return await self.async_step_amber()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CAPACITY_KWH, default=DEFAULT_BATTERY_CAPACITY_KWH
                ): vol.All(vol.Coerce(float), vol.Range(min=1, max=100)),
            }
        )

        return self.async_show_form(step_id="capacity", data_schema=schema)

    async def async_step_amber(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Fourth step: Amber Electric (optional)."""
        if user_input is not None:
            self._collected_data.update(user_input)
            return await self.async_step_solcast()

        schema = vol.Schema(
            {
                vol.Optional(CONF_AMBER_GENERAL_PRICE): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_AMBER_GENERAL_FORECAST): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_AMBER_PRICE_SPIKE): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="binary_sensor")
                ),
            }
        )

        return self.async_show_form(step_id="amber", data_schema=schema)

    async def async_step_solcast(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Fifth step: Solcast (optional)."""
        if user_input is not None:
            self._collected_data.update(user_input)
            return await self.async_step_settings()

        schema = vol.Schema(
            {
                vol.Optional(CONF_SOLCAST_TODAY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_SOLCAST_TOMORROW): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
            }
        )

        return self.async_show_form(step_id="solcast", data_schema=schema)

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Sixth step: Rebalancing settings."""
        if user_input is not None:
            self._collected_data.update(user_input)

            # Create entry with all collected config (data) and settings (options)
            options = {
                OPT_REBALANCE_START_THRESHOLD: user_input.get(
                    OPT_REBALANCE_START_THRESHOLD,
                    DEFAULT_REBALANCE_START_THRESHOLD,
                ),
                OPT_REBALANCE_STOP_THRESHOLD: user_input.get(
                    OPT_REBALANCE_STOP_THRESHOLD,
                    DEFAULT_REBALANCE_STOP_THRESHOLD,
                ),
                OPT_REBALANCE_TRANSFER_RATE: user_input.get(
                    OPT_REBALANCE_TRANSFER_RATE,
                    DEFAULT_REBALANCE_TRANSFER_RATE,
                ),
            }

            return self.async_create_entry(
                title="Sentinel Energy Manager",
                data=self._collected_data,
                options=options,
            )

        schema = vol.Schema(
            {
                vol.Required(
                    OPT_REBALANCE_START_THRESHOLD,
                    default=DEFAULT_REBALANCE_START_THRESHOLD,
                ): vol.All(vol.Coerce(float), vol.Range(min=1, max=50)),
                vol.Required(
                    OPT_REBALANCE_STOP_THRESHOLD,
                    default=DEFAULT_REBALANCE_STOP_THRESHOLD,
                ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=20)),
                vol.Required(
                    OPT_REBALANCE_TRANSFER_RATE,
                    default=DEFAULT_REBALANCE_TRANSFER_RATE,
                ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=7)),
            }
        )

        return self.async_show_form(step_id="settings", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return options flow."""
        return SentinelOptionsFlow(config_entry)


class SentinelOptionsFlow(OptionsFlow):
    """Options flow for Sentinel."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage options (rebalancing settings only)."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    OPT_REBALANCE_START_THRESHOLD,
                    default=self.config_entry.options.get(
                        OPT_REBALANCE_START_THRESHOLD,
                        DEFAULT_REBALANCE_START_THRESHOLD,
                    ),
                ): vol.All(vol.Coerce(float), vol.Range(min=1, max=50)),
                vol.Required(
                    OPT_REBALANCE_STOP_THRESHOLD,
                    default=self.config_entry.options.get(
                        OPT_REBALANCE_STOP_THRESHOLD,
                        DEFAULT_REBALANCE_STOP_THRESHOLD,
                    ),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=20)),
                vol.Required(
                    OPT_REBALANCE_TRANSFER_RATE,
                    default=self.config_entry.options.get(
                        OPT_REBALANCE_TRANSFER_RATE,
                        DEFAULT_REBALANCE_TRANSFER_RATE,
                    ),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=7)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
