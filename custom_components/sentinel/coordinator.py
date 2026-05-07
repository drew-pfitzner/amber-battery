"""Sentinel Energy Manager coordinator."""

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    SCAN_INTERVAL_SECONDS,
    MODE_FAILSAFE,
    MODE_SPIKE_EXPORT,
    MODE_OUTAGE_PREP,
    MODE_GRID_CHARGE,
    MODE_REBALANCE,
    MODE_SOLAR_CURTAIL,
    MODE_MORNING_FLOOR,
    MODE_SELF_CONSUMPTION,
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
    OPT_REBALANCE_START_THRESHOLD,
    OPT_REBALANCE_STOP_THRESHOLD,
    OPT_REBALANCE_TRANSFER_RATE,
    OPT_SOLAR_CURTAIL_PRICE_THRESHOLD,
    OPT_MORNING_FLOOR_SOC,
    DEFAULT_SOLAR_CURTAIL_PRICE_THRESHOLD,
    DEFAULT_REBALANCE_START_THRESHOLD,
    DEFAULT_REBALANCE_STOP_THRESHOLD,
    DEFAULT_REBALANCE_TRANSFER_RATE,
    DEFAULT_MORNING_FLOOR_SOC,
    DEFAULT_NORMAL_BACKUP_SOC,
    DEFAULT_MAX_GRID_LIMIT,
    DEFAULT_MAX_CHARGE_SOC,
    DEFAULT_BACKUP_BUFFER,
    MORNING_FLOOR_START_HOUR,
    MORNING_FLOOR_START_MINUTE,
    MORNING_FLOOR_END_HOUR,
    MORNING_FLOOR_END_MINUTE,
    PV_POWER_1,
    PV_POWER_2,
    BATTERY_POWER_1,
    BATTERY_POWER_2,
    GRID_ACTIVE_POWER_1,
    GRID_ACTIVE_POWER_2,
    GRID_CONNECTION_1,
    GRID_CONNECTION_2,
    AMBER_FEED_IN_PRICE,
    MODE_MAXIMUM_SELF_CONSUMPTION,
    MODE_COMMAND_CHARGING_PV_FIRST,
    MODE_COMMAND_DISCHARGING_PV_FIRST,
    CONF_CAPACITY_KWH,
    CONF_AMBER_SITE_NAME,
    OPT_GRID_CHARGE_TARGET_SOC,
    OPT_GRID_CHARGE_DEADLINE_HOUR,
    OPT_GRID_CHARGE_RATE_KW,
    DEFAULT_GRID_CHARGE_TARGET_SOC,
    DEFAULT_GRID_CHARGE_DEADLINE_HOUR,
    DEFAULT_GRID_CHARGE_RATE_KW,
)

_LOGGER = logging.getLogger(__name__)


class SentinelCoordinator(DataUpdateCoordinator[dict]):
    """Sentinel Energy Manager coordinator."""

    def __init__(self, hass: HomeAssistant, config_entry):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.config_entry = config_entry
        self._opts = {}
        self._current_mode = MODE_SELF_CONSUMPTION
        self._load_options()

        # Mode enable flags — stored in memory, persisted to options
        self._mode_enabled = {
            MODE_REBALANCE: config_entry.options.get("rebalance_enabled", False),
            MODE_SOLAR_CURTAIL: config_entry.options.get("solar_curtail_enabled", False),
            MODE_MORNING_FLOOR: config_entry.options.get("morning_floor_enabled", False),
            MODE_GRID_CHARGE: config_entry.options.get("grid_charge_enabled", False),
            MODE_SPIKE_EXPORT: config_entry.options.get("spike_export_enabled", False),
            MODE_OUTAGE_PREP: config_entry.options.get("outage_prep_enabled", False),
        }

        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name="Sentinel Energy Manager",
            manufacturer="Custom",
            model="Sentinel",
            sw_version="1.0.0",
            entry_type=DeviceEntryType.SERVICE,
        )

        # Forecast cache for GRID_CHARGE
        self._forecast_cache: list[dict] | None = None
        self._forecast_cache_time: datetime | None = None
        self._grid_charge_active: bool = False

    def _load_options(self):
        """Load options from config entry (options override data)."""
        data = self.config_entry.data
        options = self.config_entry.options
        self._opts = {
            OPT_REBALANCE_START_THRESHOLD: options.get(
                OPT_REBALANCE_START_THRESHOLD,
                data.get(OPT_REBALANCE_START_THRESHOLD, DEFAULT_REBALANCE_START_THRESHOLD),
            ),
            OPT_REBALANCE_STOP_THRESHOLD: options.get(
                OPT_REBALANCE_STOP_THRESHOLD,
                data.get(OPT_REBALANCE_STOP_THRESHOLD, DEFAULT_REBALANCE_STOP_THRESHOLD),
            ),
            OPT_REBALANCE_TRANSFER_RATE: options.get(
                OPT_REBALANCE_TRANSFER_RATE,
                data.get(OPT_REBALANCE_TRANSFER_RATE, DEFAULT_REBALANCE_TRANSFER_RATE),
            ),
            OPT_SOLAR_CURTAIL_PRICE_THRESHOLD: options.get(
                OPT_SOLAR_CURTAIL_PRICE_THRESHOLD, DEFAULT_SOLAR_CURTAIL_PRICE_THRESHOLD,
            ),
            OPT_MORNING_FLOOR_SOC: options.get(
                OPT_MORNING_FLOOR_SOC, DEFAULT_MORNING_FLOOR_SOC,
            ),
            OPT_GRID_CHARGE_TARGET_SOC: options.get(
                OPT_GRID_CHARGE_TARGET_SOC, DEFAULT_GRID_CHARGE_TARGET_SOC,
            ),
            OPT_GRID_CHARGE_DEADLINE_HOUR: options.get(
                OPT_GRID_CHARGE_DEADLINE_HOUR, DEFAULT_GRID_CHARGE_DEADLINE_HOUR,
            ),
            OPT_GRID_CHARGE_RATE_KW: options.get(
                OPT_GRID_CHARGE_RATE_KW, DEFAULT_GRID_CHARGE_RATE_KW,
            ),
        }

    async def async_set_option(self, key: str, value: Any) -> None:
        """Set an option and persist to config entry."""
        self.hass.config_entries.async_update_entry(
            self.config_entry, options={**self.config_entry.options, key: value}
        )
        self._load_options()
        await self.async_refresh()

    def set_mode_enabled(self, mode: str, enabled: bool) -> None:
        """Set a mode's enabled state (called by switch entities)."""
        self._mode_enabled[mode] = enabled
        # Persist to options (without triggering reload)
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            options={
                **self.config_entry.options,
                f"{mode.lower()}_enabled": enabled,
            },
        )

    def is_mode_enabled(self, mode: str) -> bool:
        """Check if a mode is enabled."""
        return self._mode_enabled.get(mode, False)

    async def _async_update_data(self) -> dict:
        """Fetch data from Sigen entities and evaluate priority mode."""
        try:
            config = self.config_entry.data
            soc_1 = self._get_state_float(config[CONF_SOC_1])
            soc_2 = self._get_state_float(config[CONF_SOC_2])
            backup_soc_1 = self._get_state_float(config[CONF_BACKUP_SOC_1])
            backup_soc_2 = self._get_state_float(config[CONF_BACKUP_SOC_2])
            ha_switch_1 = self._get_state_bool(config[CONF_HA_SWITCH_1])
            ha_switch_2 = self._get_state_bool(config[CONF_HA_SWITCH_2])
            export_power_1 = self._get_state_float(config[CONF_EXPORT_POWER_1]) or 0
            export_power_2 = self._get_state_float(config[CONF_EXPORT_POWER_2]) or 0
            import_power_1 = self._get_state_float(config[CONF_IMPORT_POWER_1]) or 0
            import_power_2 = self._get_state_float(config[CONF_IMPORT_POWER_2]) or 0

            # FAILSAFE: any critical entity unavailable OR either HA switch off
            entities_unavailable = any(
                val is None
                for val in [soc_1, soc_2, backup_soc_1, backup_soc_2, ha_switch_1, ha_switch_2]
            )
            ha_switches_off = (ha_switch_1 is False) or (ha_switch_2 is False)

            if entities_unavailable or ha_switches_off:
                if self._current_mode != MODE_FAILSAFE:
                    _LOGGER.warning(
                        "Entering FAILSAFE: entities_unavailable=%s, ha_switches_off=%s",
                        entities_unavailable, ha_switches_off,
                    )
                await self._async_apply_failsafe()
                self._current_mode = MODE_FAILSAFE
            else:
                mean_soc = (soc_1 + soc_2) / 2

                # Pre-compute GRID_CHARGE condition asynchronously before priority evaluation
                if self.is_mode_enabled(MODE_GRID_CHARGE):
                    self._grid_charge_active = await self._async_evaluate_grid_charge(mean_soc)
                else:
                    self._grid_charge_active = False

                new_mode = self._evaluate_priority(
                    soc_1, soc_2, backup_soc_1, backup_soc_2, mean_soc,
                )

                if new_mode != self._current_mode:
                    _LOGGER.info("Mode change: %s -> %s", self._current_mode, new_mode)
                    # Restore backup SOC when leaving morning floor
                    if self._current_mode == MODE_MORNING_FLOOR:
                        await self._restore_backup_soc()
                    # Restore grid limits when leaving grid charge
                    if self._current_mode == MODE_GRID_CHARGE:
                        await self._restore_all_grid_limits()
                    self._current_mode = new_mode

                await self._apply_mode(self._current_mode)

            # Calculate net grid power using signed grid_active_power sensors
            # These are per-plant signed values (positive = import, negative = export).
            # Summing across both phases gives the true net as seen by the meter,
            # so rebalancing (one imports, one exports equally) nets to ~0.
            gap_1 = self._get_state_float(GRID_ACTIVE_POWER_1) or 0
            gap_2 = self._get_state_float(GRID_ACTIVE_POWER_2) or 0
            net_grid = gap_1 + gap_2
            net_grid_import = max(0, net_grid)
            net_grid_export = max(0, -net_grid)
            net_grid_power = net_grid_export - net_grid_import

            soc_diff = abs((soc_1 or 0) - (soc_2 or 0))
            mean_soc = ((soc_1 or 0) + (soc_2 or 0)) / 2
            combined_pv = self._get_combined_pv_kw()

            # Calculate net battery power (sum of both plants)
            # Sigen battery_power: positive = charging, negative = discharging
            # Negate so net_battery_power follows positive = discharging convention
            bp_1 = self._get_state_float(BATTERY_POWER_1) or 0
            bp_2 = self._get_state_float(BATTERY_POWER_2) or 0
            net_battery_power = -(bp_1 + bp_2)  # already in kW
            net_battery_discharge = max(0, net_battery_power)
            net_battery_charge = max(0, -net_battery_power)

            return {
                "soc_1": soc_1,
                "soc_2": soc_2,
                "soc_diff": soc_diff,
                "mean_soc": mean_soc,
                "net_grid_power": net_grid_power,
                "net_grid_import": net_grid_import,
                "net_grid_export": net_grid_export,
                "combined_pv_power": combined_pv,
                "net_battery_power": net_battery_power,
                "net_battery_discharge": net_battery_discharge,
                "net_battery_charge": net_battery_charge,
                "active_mode": self._current_mode,
                "rebalancing_active": self._current_mode == MODE_REBALANCE,
                "solar_curtail_active": self._current_mode == MODE_SOLAR_CURTAIL,
                "failsafe_active": self._current_mode == MODE_FAILSAFE,
                "morning_floor_active": self._current_mode == MODE_MORNING_FLOOR,
                "grid_charging_active": self._current_mode in (
                    MODE_GRID_CHARGE, MODE_OUTAGE_PREP,
                ),
            }
        except Exception as err:
            _LOGGER.error("Error in coordinator update: %s", err)
            raise UpdateFailed(f"Error: {err}")

    def _evaluate_priority(
        self,
        soc_1: float,
        soc_2: float,
        backup_soc_1: float,
        backup_soc_2: float,
        mean_soc: float,
    ) -> str:
        """Evaluate priority and return the highest-priority valid mode."""
        # Priority 1: FAILSAFE — already handled in _async_update_data

        # Priority 2: SPIKE_EXPORT (stub)
        if self.is_mode_enabled(MODE_SPIKE_EXPORT):
            if self._check_spike_export_conditions():
                return MODE_SPIKE_EXPORT

        # Priority 3: OUTAGE_PREP (stub)
        if self.is_mode_enabled(MODE_OUTAGE_PREP):
            if self._check_outage_prep_conditions():
                return MODE_OUTAGE_PREP

        # Priority 4: GRID_CHARGE (stub)
        if self.is_mode_enabled(MODE_GRID_CHARGE):
            if self._check_grid_charge_conditions():
                return MODE_GRID_CHARGE

        # Priority 5: REBALANCE
        if self.is_mode_enabled(MODE_REBALANCE):
            if self._check_rebalance_conditions(soc_1, soc_2, backup_soc_1, backup_soc_2):
                return MODE_REBALANCE

        # Priority 6: SOLAR_CURTAIL
        if self.is_mode_enabled(MODE_SOLAR_CURTAIL):
            if self._check_solar_curtail_conditions():
                return MODE_SOLAR_CURTAIL

        # Priority 7: MORNING_FLOOR
        if self.is_mode_enabled(MODE_MORNING_FLOOR):
            if self._check_morning_floor_conditions(mean_soc):
                return MODE_MORNING_FLOOR

        # Priority 8: SELF_CONSUMPTION (always valid)
        return MODE_SELF_CONSUMPTION

    def _check_spike_export_conditions(self) -> bool:
        return False

    def _check_outage_prep_conditions(self) -> bool:
        return False

    def _check_grid_charge_conditions(self) -> bool:
        return self._grid_charge_active

    def _check_solar_curtail_conditions(self) -> bool:
        """Check if SOLAR_CURTAIL conditions are met (low feed-in price + solar producing)."""
        feed_in_price = self._get_state_float(AMBER_FEED_IN_PRICE)
        if feed_in_price is None:
            return False

        threshold = self._opts[OPT_SOLAR_CURTAIL_PRICE_THRESHOLD]
        if feed_in_price >= threshold:
            return False

        combined_pv = self._get_combined_pv_kw()
        if combined_pv is None or combined_pv <= 0:
            return False

        return True

    def _check_rebalance_conditions(
        self,
        soc_1: float,
        soc_2: float,
        backup_soc_1: float,
        backup_soc_2: float,
    ) -> bool:
        """Check if REBALANCE conditions are met."""
        # Require grid connection on both plants
        if not self._is_grid_connected():
            return False

        soc_diff = abs(soc_1 - soc_2)

        # Use stop threshold if already rebalancing, start threshold otherwise
        if self._current_mode == MODE_REBALANCE:
            threshold = self._opts[OPT_REBALANCE_STOP_THRESHOLD]
        else:
            threshold = self._opts[OPT_REBALANCE_START_THRESHOLD]

        if soc_diff <= threshold:
            return False

        # Determine which plant would discharge
        if soc_1 >= soc_2:
            discharge_soc, discharge_backup = soc_1, backup_soc_1
            charge_soc = soc_2
        else:
            discharge_soc, discharge_backup = soc_2, backup_soc_2
            charge_soc = soc_1

        # Discharge plant must have headroom above backup SOC
        if discharge_soc <= (discharge_backup + DEFAULT_BACKUP_BUFFER):
            return False

        # Charge plant must not be full
        if charge_soc >= DEFAULT_MAX_CHARGE_SOC:
            return False

        return True

    def _check_morning_floor_conditions(self, mean_soc: float) -> bool:
        """Check if MORNING_FLOOR conditions are met (inside overnight window)."""
        now = dt_util.now()
        t = now.hour * 60 + now.minute
        start = MORNING_FLOOR_START_HOUR * 60 + MORNING_FLOOR_START_MINUTE  # 22:10
        end = MORNING_FLOOR_END_HOUR * 60 + MORNING_FLOOR_END_MINUTE        # 05:50

        # Window spans midnight: active if past start OR before end
        return t >= start or t < end

    async def _async_fetch_amber_forecasts(self) -> list[dict] | None:
        """Fetch Amber forecasts, using a 15-minute cache."""
        now = dt_util.now()

        # Return cached data if fresh
        if (
            self._forecast_cache is not None
            and self._forecast_cache_time is not None
            and (now - self._forecast_cache_time).total_seconds() < 900
        ):
            return self._forecast_cache

        # Discover Amber config entry
        amber_entries = self.hass.config_entries.async_entries("amberelectric")
        if not amber_entries:
            _LOGGER.debug("No amberelectric config entries — GRID_CHARGE forecast unavailable")
            return None

        site_name = amber_entries[0].title
        try:
            response = await self.hass.services.async_call(
                "amberelectric",
                "get_forecasts",
                {"config_entry": site_name, "channel_type": "general"},
                blocking=True,
                return_response=True,
            )
            forecasts = (response or {}).get("forecasts", [])
            if not forecasts:
                _LOGGER.warning("Amber get_forecasts returned empty list")
                return None

            self._forecast_cache = forecasts
            self._forecast_cache_time = now
            _LOGGER.debug("Cached %d Amber forecast intervals", len(forecasts))
            return forecasts

        except Exception as err:
            _LOGGER.warning("Failed to fetch Amber forecasts: %s", err)
            return None

    def _select_cheapest_charge_window(
        self, forecasts: list[dict], required_hours: float, deadline_hour: int,
    ) -> set[str]:
        """Select the cheapest set of forecast intervals to cover required_hours.

        Returns a set of start_time strings for the selected intervals.
        """
        now = dt_util.now()
        deadline = now.replace(hour=deadline_hour, minute=0, second=0, microsecond=0)
        if deadline <= now:
            return set()

        # Filter to intervals that start at or after now and end before deadline
        eligible = []
        for interval in forecasts:
            try:
                start_str = interval.get("start_time", "")
                end_str = interval.get("end_time", "")
                if not start_str or not end_str:
                    continue
                start_dt = dt_util.as_local(dt_util.parse_datetime(start_str))
                end_dt = dt_util.as_local(dt_util.parse_datetime(end_str))
                if start_dt is None or end_dt is None:
                    continue
                # Include if: start >= now AND end <= deadline
                if start_dt >= now and end_dt <= deadline:
                    eligible.append({
                        "start_time": start_str,
                        "per_kwh": float(interval.get("per_kwh", 999)),
                        "duration_hours": (
                            dt_util.parse_datetime(end_str) - dt_util.parse_datetime(start_str)
                        ).total_seconds() / 3600,
                    })
            except (ValueError, TypeError, KeyError):
                continue

        if not eligible:
            return set()

        # Sort by price ascending, greedily pick cheapest until required_hours covered
        eligible.sort(key=lambda x: x["per_kwh"])
        selected: set[str] = set()
        hours_covered = 0.0
        for interval in eligible:
            if hours_covered >= required_hours:
                break
            selected.add(interval["start_time"])
            hours_covered += interval["duration_hours"]

        return selected

    async def _async_evaluate_grid_charge(self, mean_soc: float) -> bool:
        """Evaluate whether GRID_CHARGE should be active this cycle."""
        target_soc = self._opts[OPT_GRID_CHARGE_TARGET_SOC]
        deadline_hour = int(self._opts[OPT_GRID_CHARGE_DEADLINE_HOUR])
        charge_rate_kw = self._opts[OPT_GRID_CHARGE_RATE_KW]
        capacity_kwh = 2 * self.config_entry.data.get(CONF_CAPACITY_KWH, 24.5)

        # Hysteresis: stop at target, don't start unless 1% below target
        if self._current_mode == MODE_GRID_CHARGE:
            if mean_soc >= target_soc:
                _LOGGER.info("GRID_CHARGE stop: SOC %.1f%% >= target %.1f%%", mean_soc, target_soc)
                return False
        else:
            if mean_soc >= (target_soc - 1.0):
                return False

        soc_deficit = max(0.0, target_soc - mean_soc)
        required_hours = (soc_deficit / 100.0) * capacity_kwh / charge_rate_kw
        if required_hours <= 0:
            return False

        now = dt_util.now()
        deadline = now.replace(hour=deadline_hour, minute=0, second=0, microsecond=0)
        if deadline <= now:
            _LOGGER.debug("GRID_CHARGE: deadline %02d:00 already passed", deadline_hour)
            return False

        hours_remaining = (deadline - now).total_seconds() / 3600

        # Forced charge: not enough cheap time left to be selective
        if hours_remaining < required_hours * 1.5:
            _LOGGER.info(
                "GRID_CHARGE forced: %.2fh remaining < %.2fh required × 1.5",
                hours_remaining, required_hours,
            )
            return True

        forecasts = await self._async_fetch_amber_forecasts()
        if forecasts is None:
            return False

        selected = self._select_cheapest_charge_window(forecasts, required_hours, deadline_hour)
        if not selected:
            _LOGGER.debug("GRID_CHARGE: no eligible intervals before %02d:00", deadline_hour)
            return False

        # Check if current time falls in a selected interval
        for interval in forecasts:
            try:
                start_str = interval.get("start_time", "")
                end_str = interval.get("end_time", "")
                start_dt = dt_util.as_local(dt_util.parse_datetime(start_str))
                end_dt = dt_util.as_local(dt_util.parse_datetime(end_str))
                if start_dt is None or end_dt is None:
                    continue
                if start_dt <= now < end_dt:
                    if start_str in selected:
                        _LOGGER.info(
                            "GRID_CHARGE active: $%.4f/kWh interval in cheapest window",
                            interval.get("per_kwh", 0),
                        )
                        return True
                    _LOGGER.debug(
                        "GRID_CHARGE inactive: $%.4f/kWh interval not in cheapest window",
                        interval.get("per_kwh", 0),
                    )
                    return False
            except (ValueError, TypeError, AttributeError):
                continue

        return False

    def _is_grid_connected(self) -> bool:
        """Check if both plants are connected to the grid."""
        state_1 = self.hass.states.get(GRID_CONNECTION_1)
        state_2 = self.hass.states.get(GRID_CONNECTION_2)
        if not state_1 or not state_2:
            return False
        if state_1.state in ("unknown", "unavailable") or state_2.state in ("unknown", "unavailable"):
            return False
        return state_1.state == "On Grid" and state_2.state == "On Grid"

    def _get_combined_pv_kw(self) -> float | None:
        """Read combined PV production from both Sigen plants (kW)."""
        pv_1 = self._get_state_float(PV_POWER_1)
        pv_2 = self._get_state_float(PV_POWER_2)
        if pv_1 is not None and pv_2 is not None:
            return pv_1 + pv_2
        if pv_1 is not None:
            return pv_1
        if pv_2 is not None:
            return pv_2
        return None

    async def _apply_mode(self, mode: str) -> None:
        """Apply the specified mode."""
        if mode == MODE_FAILSAFE:
            await self._async_apply_failsafe()
        elif mode == MODE_REBALANCE:
            await self._async_apply_rebalance()
        elif mode == MODE_SOLAR_CURTAIL:
            await self._async_apply_solar_curtail()
        elif mode == MODE_MORNING_FLOOR:
            await self._async_apply_morning_floor()
        elif mode == MODE_GRID_CHARGE:
            await self._async_apply_grid_charge()
        elif mode == MODE_SELF_CONSUMPTION:
            await self._async_apply_self_consumption()
        else:
            await self._async_apply_self_consumption()

    async def _async_apply_failsafe(self) -> None:
        """FAILSAFE: both batteries to Maximum Self Consumption, restore limits."""
        await self._set_both_mode(MODE_MAXIMUM_SELF_CONSUMPTION)
        await self._restore_all_grid_limits()

    async def _async_apply_rebalance(self) -> None:
        """REBALANCE: discharge higher SOC battery, charge lower."""
        config = self.config_entry.data
        soc_1 = self._get_state_float(config[CONF_SOC_1])
        soc_2 = self._get_state_float(config[CONF_SOC_2])

        if soc_1 is None or soc_2 is None:
            return

        transfer_rate = self._opts[OPT_REBALANCE_TRANSFER_RATE]

        if soc_1 >= soc_2:
            # Plant 1 discharges, Plant 2 charges
            await self._call_service_set_mode(config[CONF_MODE_1], MODE_COMMAND_DISCHARGING_PV_FIRST)
            await self._call_service_set_mode(config[CONF_MODE_2], MODE_COMMAND_CHARGING_PV_FIRST)
            await self._call_service_set_limit(config[CONF_EXPORT_LIMIT_1], transfer_rate)
            await self._call_service_set_limit(config[CONF_IMPORT_LIMIT_2], transfer_rate)
            await self._call_service_set_limit(config[CONF_IMPORT_LIMIT_1], 0)
            await self._call_service_set_limit(config[CONF_EXPORT_LIMIT_2], 0)
        else:
            # Plant 2 discharges, Plant 1 charges
            await self._call_service_set_mode(config[CONF_MODE_2], MODE_COMMAND_DISCHARGING_PV_FIRST)
            await self._call_service_set_mode(config[CONF_MODE_1], MODE_COMMAND_CHARGING_PV_FIRST)
            await self._call_service_set_limit(config[CONF_EXPORT_LIMIT_2], transfer_rate)
            await self._call_service_set_limit(config[CONF_IMPORT_LIMIT_1], transfer_rate)
            await self._call_service_set_limit(config[CONF_IMPORT_LIMIT_2], 0)
            await self._call_service_set_limit(config[CONF_EXPORT_LIMIT_1], 0)

    async def _async_apply_solar_curtail(self) -> None:
        """SOLAR_CURTAIL: block grid export while keeping self-consumption."""
        config = self.config_entry.data
        await self._set_both_mode(MODE_MAXIMUM_SELF_CONSUMPTION)
        await self._call_service_set_limit(config[CONF_EXPORT_LIMIT_1], 0)
        await self._call_service_set_limit(config[CONF_EXPORT_LIMIT_2], 0)
        await self._call_service_set_limit(config[CONF_IMPORT_LIMIT_1], DEFAULT_MAX_GRID_LIMIT)
        await self._call_service_set_limit(config[CONF_IMPORT_LIMIT_2], DEFAULT_MAX_GRID_LIMIT)

    async def _async_apply_morning_floor(self) -> None:
        """MORNING_FLOOR: raise backup SOC to floor, stay in self-consumption.

        The battery's built-in ESS logic will grid-charge to maintain the
        backup SOC floor.  No need to switch to Grid First mode.
        """
        config = self.config_entry.data
        floor_soc = self._opts[OPT_MORNING_FLOOR_SOC]

        await self._set_both_mode(MODE_MAXIMUM_SELF_CONSUMPTION)
        await self._restore_all_grid_limits()
        await self._call_service_set_limit(config[CONF_BACKUP_SOC_1], floor_soc)
        await self._call_service_set_limit(config[CONF_BACKUP_SOC_2], floor_soc)

    async def _async_apply_grid_charge(self) -> None:
        """GRID_CHARGE: both batteries Command Charging (PV First) at configured rate."""
        config = self.config_entry.data
        charge_rate_kw = self._opts[OPT_GRID_CHARGE_RATE_KW]
        per_plant_rate = min(charge_rate_kw / 2, DEFAULT_MAX_GRID_LIMIT)

        await self._set_both_mode(MODE_COMMAND_CHARGING_PV_FIRST)
        await self._call_service_set_limit(config[CONF_IMPORT_LIMIT_1], per_plant_rate)
        await self._call_service_set_limit(config[CONF_IMPORT_LIMIT_2], per_plant_rate)
        await self._call_service_set_limit(config[CONF_EXPORT_LIMIT_1], DEFAULT_MAX_GRID_LIMIT)
        await self._call_service_set_limit(config[CONF_EXPORT_LIMIT_2], DEFAULT_MAX_GRID_LIMIT)

    async def _restore_backup_soc(self) -> None:
        """Restore backup SOC to normal value when leaving morning floor."""
        config = self.config_entry.data
        await self._call_service_set_limit(
            config[CONF_BACKUP_SOC_1], DEFAULT_NORMAL_BACKUP_SOC,
        )
        await self._call_service_set_limit(
            config[CONF_BACKUP_SOC_2], DEFAULT_NORMAL_BACKUP_SOC,
        )

    async def _async_apply_self_consumption(self) -> None:
        """SELF_CONSUMPTION: both batteries to normal mode, restore limits."""
        await self._set_both_mode(MODE_MAXIMUM_SELF_CONSUMPTION)
        await self._restore_all_grid_limits()

    async def _set_both_mode(self, mode: str) -> None:
        """Set both batteries to the same mode."""
        config = self.config_entry.data
        await self._call_service_set_mode(config[CONF_MODE_1], mode)
        await self._call_service_set_mode(config[CONF_MODE_2], mode)

    async def _restore_all_grid_limits(self) -> None:
        """Restore all grid limits to maximum (7 kW)."""
        config = self.config_entry.data
        limit = DEFAULT_MAX_GRID_LIMIT
        await self._call_service_set_limit(config[CONF_EXPORT_LIMIT_1], limit)
        await self._call_service_set_limit(config[CONF_IMPORT_LIMIT_1], limit)
        await self._call_service_set_limit(config[CONF_EXPORT_LIMIT_2], limit)
        await self._call_service_set_limit(config[CONF_IMPORT_LIMIT_2], limit)

    async def _call_service_set_mode(self, entity_id: str, mode: str) -> None:
        """Set a battery mode via select service."""
        await self.hass.services.async_call(
            "select", "select_option",
            {"entity_id": entity_id, "option": mode},
        )

    async def _call_service_set_limit(self, entity_id: str, value: float) -> None:
        """Set a grid limit via number service."""
        await self.hass.services.async_call(
            "number", "set_value",
            {"entity_id": entity_id, "value": value},
        )

    def _get_state_float(self, entity_id: str) -> float | None:
        """Get a numeric state value."""
        state = self.hass.states.get(entity_id)
        if not state or state.state in ("unknown", "unavailable"):
            return None
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return None

    def _get_state_bool(self, entity_id: str) -> bool | None:
        """Get a boolean state value."""
        state = self.hass.states.get(entity_id)
        if not state or state.state in ("unknown", "unavailable"):
            return None
        return state.state == "on"
