"""Config flow and options flow for the Sigen Battery Rebalancer."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    CONF_BACKUP_SOC_1,
    CONF_BACKUP_SOC_2,
    CONF_EXPORT_LIMIT_1,
    CONF_EXPORT_LIMIT_2,
    CONF_EXPORT_POWER_1,
    CONF_EXPORT_POWER_2,
    CONF_HA_SWITCH_1,
    CONF_HA_SWITCH_2,
    CONF_IMPORT_LIMIT_1,
    CONF_IMPORT_LIMIT_2,
    CONF_IMPORT_POWER_1,
    CONF_IMPORT_POWER_2,
    CONF_MODE_1,
    CONF_MODE_2,
    CONF_SOC_1,
    CONF_SOC_2,
    DEFAULT_BACKUP_SOC_1,
    DEFAULT_BACKUP_SOC_2,
    DEFAULT_EXPORT_LIMIT_1,
    DEFAULT_EXPORT_LIMIT_2,
    DEFAULT_EXPORT_POWER_1,
    DEFAULT_EXPORT_POWER_2,
    DEFAULT_HA_SWITCH_1,
    DEFAULT_HA_SWITCH_2,
    DEFAULT_IMPORT_LIMIT_1,
    DEFAULT_IMPORT_LIMIT_2,
    DEFAULT_IMPORT_POWER_1,
    DEFAULT_IMPORT_POWER_2,
    DEFAULT_MODE_1,
    DEFAULT_MODE_2,
    DEFAULT_SOC_1,
    DEFAULT_SOC_2,
    DEFAULT_START_THRESHOLD,
    DEFAULT_STOP_THRESHOLD,
    DEFAULT_TRANSFER_RATE,
    DOMAIN,
    OPT_START_THRESHOLD,
    OPT_STOP_THRESHOLD,
    OPT_TRANSFER_RATE,
)


def _sensor_selector() -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))


def _select_selector() -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain="select"))


def _switch_selector() -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain="switch"))


def _number_selector() -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain="number"))


PLANT1_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SOC_1, default=DEFAULT_SOC_1): _sensor_selector(),
        vol.Required(CONF_MODE_1, default=DEFAULT_MODE_1): _select_selector(),
        vol.Required(CONF_HA_SWITCH_1, default=DEFAULT_HA_SWITCH_1): _switch_selector(),
        vol.Required(CONF_EXPORT_LIMIT_1, default=DEFAULT_EXPORT_LIMIT_1): _number_selector(),
        vol.Required(CONF_IMPORT_LIMIT_1, default=DEFAULT_IMPORT_LIMIT_1): _number_selector(),
        vol.Required(CONF_BACKUP_SOC_1, default=DEFAULT_BACKUP_SOC_1): _number_selector(),
        vol.Required(CONF_EXPORT_POWER_1, default=DEFAULT_EXPORT_POWER_1): _sensor_selector(),
        vol.Required(CONF_IMPORT_POWER_1, default=DEFAULT_IMPORT_POWER_1): _sensor_selector(),
    }
)

PLANT2_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SOC_2, default=DEFAULT_SOC_2): _sensor_selector(),
        vol.Required(CONF_MODE_2, default=DEFAULT_MODE_2): _select_selector(),
        vol.Required(CONF_HA_SWITCH_2, default=DEFAULT_HA_SWITCH_2): _switch_selector(),
        vol.Required(CONF_EXPORT_LIMIT_2, default=DEFAULT_EXPORT_LIMIT_2): _number_selector(),
        vol.Required(CONF_IMPORT_LIMIT_2, default=DEFAULT_IMPORT_LIMIT_2): _number_selector(),
        vol.Required(CONF_BACKUP_SOC_2, default=DEFAULT_BACKUP_SOC_2): _number_selector(),
        vol.Required(CONF_EXPORT_POWER_2, default=DEFAULT_EXPORT_POWER_2): _sensor_selector(),
        vol.Required(CONF_IMPORT_POWER_2, default=DEFAULT_IMPORT_POWER_2): _sensor_selector(),
    }
)


def _settings_schema(defaults: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                OPT_START_THRESHOLD,
                default=defaults.get(OPT_START_THRESHOLD, DEFAULT_START_THRESHOLD),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=50, step=0.5, unit_of_measurement="%", mode="box"
                )
            ),
            vol.Required(
                OPT_STOP_THRESHOLD,
                default=defaults.get(OPT_STOP_THRESHOLD, DEFAULT_STOP_THRESHOLD),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.5, max=20, step=0.5, unit_of_measurement="%", mode="box"
                )
            ),
            vol.Required(
                OPT_TRANSFER_RATE,
                default=defaults.get(OPT_TRANSFER_RATE, DEFAULT_TRANSFER_RATE),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.5, max=7, step=0.5, unit_of_measurement="kW", mode="box"
                )
            ),
        }
    )


class SigenRebalancerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Three-step config flow: Plant 1 entities → Plant 2 entities → Settings."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_plant2()

        return self.async_show_form(step_id="user", data_schema=PLANT1_SCHEMA)

    async def async_step_plant2(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_settings()

        return self.async_show_form(step_id="plant2", data_schema=PLANT2_SCHEMA)

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="Sigen Battery Rebalancer",
                data=self._data,
                options={
                    OPT_START_THRESHOLD: user_input[OPT_START_THRESHOLD],
                    OPT_STOP_THRESHOLD: user_input[OPT_STOP_THRESHOLD],
                    OPT_TRANSFER_RATE: user_input[OPT_TRANSFER_RATE],
                },
            )

        return self.async_show_form(
            step_id="settings", data_schema=_settings_schema({})
        )

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return SigenRebalancerOptionsFlow(config_entry)


class SigenRebalancerOptionsFlow(config_entries.OptionsFlow):
    """Options flow for changing operational thresholds without reinstalling."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_settings_schema(dict(self._config_entry.options)),
        )
