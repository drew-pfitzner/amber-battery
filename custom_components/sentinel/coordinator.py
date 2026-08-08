"""Sentinel Energy Manager coordinator."""

import asyncio
from datetime import date, datetime, time, timedelta
import logging
from time import monotonic
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
    MODE_OUTAGE_PREP,
    MODE_GRID_CHARGE,
    MODE_REBALANCE,
    MODE_SOLAR_CURTAIL,
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
    DEFAULT_SOLAR_CURTAIL_PRICE_THRESHOLD,
    DEFAULT_REBALANCE_START_THRESHOLD,
    DEFAULT_REBALANCE_STOP_THRESHOLD,
    DEFAULT_REBALANCE_TRANSFER_RATE,
    DEFAULT_MAX_GRID_LIMIT,
    DEFAULT_MAX_CHARGE_SOC,
    DEFAULT_BACKUP_BUFFER,
    GRID_CHARGE_MORNING_DEADLINE_HOUR,
    GRID_CHARGE_MIN_EFFECTIVE_KW,
    GRID_CHARGE_DAYTIME_START_HOUR,
    GRID_CHARGE_OVERNIGHT_START_HOUR,
    FALLBACK_EVENING_PEAK_HOUR,
    PEAK_DETECT_FACTOR,
    PEAK_DETECT_BASELINE_PCTL,
    MORNING_PEAK_BAND,
    EVENING_PEAK_BAND,
    PV_POWER_1,
    PV_POWER_2,
    LOAD_POWER_1,
    LOAD_POWER_2,
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
    OPT_GRID_CHARGE_RATE_KW,
    OPT_GRID_CHARGE_HYSTERESIS_SOC,
    OPT_GRID_CHARGE_MIN_RESERVE_SOC,
    OPT_GRID_CHARGE_MAX_SOC,
    OPT_OUTAGE_DATE,
    OPT_OUTAGE_TARGET_SOC,
    DEFAULT_GRID_CHARGE_RATE_KW,
    DEFAULT_GRID_CHARGE_HYSTERESIS_SOC,
    DEFAULT_OUTAGE_TARGET_SOC,
    DEFAULT_GRID_CHARGE_MIN_RESERVE_SOC,
    DEFAULT_GRID_CHARGE_MAX_SOC,
    DEFAULT_SEED_MORNING_KWH,
    DEFAULT_SEED_EVENING_KWH,
    DEFAULT_SEED_DAYTIME_KWH,
    CONF_SOLCAST_TODAY,
    CONF_SOLCAST_TOMORROW,
    FAILSAFE_DEBOUNCE_POLLS,
    OUTAGE_PREP_START_HOUR,
    OUTAGE_PREP_END_HOUR,
)
from .learning import LoadLearner

_LOGGER = logging.getLogger(__name__)

# Grid limits are in kW (0–12) and backup SOC in % — a setpoint that differs
# from the current value by less than this is treated as "already set" and the
# write is skipped. Keeps redundant writes off the Sigen Modbus interface.
WRITE_TOLERANCE = 0.05

# Minimum spacing between consecutive Modbus-backed writes to the Sigen gateways.
# Each dongle has a single-connection Modbus interface that can be knocked offline
# by a burst of commands, so a mode change (which may touch several controls) is
# trickled out one write at a time with at least this gap between them, and each
# write is awaited to completion before the next is issued. A full ~8-write mode
# change therefore spreads over a few seconds — comfortably inside the 30 s cycle.
WRITE_MIN_GAP_SECONDS = 0.4


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
            MODE_GRID_CHARGE: config_entry.options.get("grid_charge_enabled", False),
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
        self._grid_charge_target: float = DEFAULT_GRID_CHARGE_MAX_SOC
        self._outage_prep_active: bool = False
        # Consecutive polls with a critical entity unavailable (FAILSAFE debounce)
        self._unavailable_count: int = 0
        # Monotonic timestamp of the last Modbus-backed write, for write pacing.
        self._last_write_monotonic: float = 0.0
        # Detected next price-peak onsets (datetimes), for GRID_CHARGE deadlines
        # and visibility sensors. None until the first evaluation.
        self._next_morning_peak: datetime | None = None
        self._next_evening_peak: datetime | None = None
        # Learns per-window daily consumption so GRID_CHARGE targets self-tune.
        self._learner = LoadLearner(hass, config_entry.entry_id)

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
            OPT_GRID_CHARGE_RATE_KW: options.get(
                OPT_GRID_CHARGE_RATE_KW, DEFAULT_GRID_CHARGE_RATE_KW,
            ),
            OPT_GRID_CHARGE_HYSTERESIS_SOC: options.get(
                OPT_GRID_CHARGE_HYSTERESIS_SOC, DEFAULT_GRID_CHARGE_HYSTERESIS_SOC,
            ),
            OPT_GRID_CHARGE_MIN_RESERVE_SOC: options.get(
                OPT_GRID_CHARGE_MIN_RESERVE_SOC, DEFAULT_GRID_CHARGE_MIN_RESERVE_SOC,
            ),
            OPT_GRID_CHARGE_MAX_SOC: options.get(
                OPT_GRID_CHARGE_MAX_SOC, DEFAULT_GRID_CHARGE_MAX_SOC,
            ),
            OPT_OUTAGE_DATE: options.get(OPT_OUTAGE_DATE, ""),
            OPT_OUTAGE_TARGET_SOC: options.get(
                OPT_OUTAGE_TARGET_SOC, DEFAULT_OUTAGE_TARGET_SOC,
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
            await self._learner.async_load()
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

            # Debounce transient sensor dropouts: a critical entity must read
            # unavailable for FAILSAFE_DEBOUNCE_POLLS consecutive cycles before
            # tripping FAILSAFE. An HA control switch turned off is a deliberate
            # user action and still trips immediately.
            if entities_unavailable:
                self._unavailable_count += 1
            else:
                self._unavailable_count = 0
            unavailable_confirmed = (
                entities_unavailable
                and self._unavailable_count >= FAILSAFE_DEBOUNCE_POLLS
            )

            if unavailable_confirmed or ha_switches_off:
                if self._current_mode != MODE_FAILSAFE:
                    _LOGGER.warning(
                        "Entering FAILSAFE: entities_unavailable=%s, ha_switches_off=%s",
                        entities_unavailable, ha_switches_off,
                    )
                await self._async_apply_failsafe()
                self._current_mode = MODE_FAILSAFE
            elif entities_unavailable:
                # Transient dropout within the debounce grace period — hold the
                # current mode this cycle rather than acting on partial data.
                _LOGGER.debug(
                    "Critical entity unavailable (%d/%d) — holding mode %s",
                    self._unavailable_count, FAILSAFE_DEBOUNCE_POLLS, self._current_mode,
                )
            else:
                mean_soc = (soc_1 + soc_2) / 2

                # Pre-compute GRID_CHARGE condition asynchronously before priority evaluation
                if self.is_mode_enabled(MODE_GRID_CHARGE):
                    self._grid_charge_active = await self._async_evaluate_grid_charge(mean_soc)
                else:
                    self._grid_charge_active = False
                    self._grid_charge_target = self._compute_grid_charge_target()

                # Pre-compute OUTAGE_PREP condition asynchronously before priority evaluation
                if self.is_mode_enabled(MODE_OUTAGE_PREP):
                    self._outage_prep_active = await self._async_evaluate_outage_prep(mean_soc)
                else:
                    self._outage_prep_active = False

                new_mode = self._evaluate_priority(
                    soc_1, soc_2, backup_soc_1, backup_soc_2, mean_soc,
                )

                if new_mode != self._current_mode:
                    _LOGGER.info("Mode change: %s -> %s", self._current_mode, new_mode)
                    # Restore grid limits when leaving grid charge / outage prep
                    if self._current_mode in (MODE_GRID_CHARGE, MODE_OUTAGE_PREP):
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
            combined_load = self._get_combined_load_kw()

            # Feed the load learner this cycle's consumption so GRID_CHARGE
            # targets self-tune from real usage.
            await self._learner.async_record(dt_util.now(), combined_load)

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
                "combined_load_power": combined_load,
                "net_battery_power": net_battery_power,
                "net_battery_discharge": net_battery_discharge,
                "net_battery_charge": net_battery_charge,
                "active_mode": self._current_mode,
                "rebalancing_active": self._current_mode == MODE_REBALANCE,
                "solar_curtail_active": self._current_mode == MODE_SOLAR_CURTAIL,
                "failsafe_active": self._current_mode == MODE_FAILSAFE,
                "grid_charging_active": self._current_mode in (
                    MODE_GRID_CHARGE, MODE_OUTAGE_PREP,
                ),
                "grid_charge_target": self._grid_charge_target,
                "outage_prep_active": self._current_mode == MODE_OUTAGE_PREP,
                "next_morning_peak": self._next_morning_peak,
                "next_evening_peak": self._next_evening_peak,
                "learned_morning_load": round(
                    self._learner.morning_kwh(DEFAULT_SEED_MORNING_KWH), 2,
                ),
                "learned_daytime_load": round(
                    self._learner.daytime_kwh(DEFAULT_SEED_DAYTIME_KWH), 2,
                ),
                "learned_evening_load": round(
                    self._learner.evening_kwh(DEFAULT_SEED_EVENING_KWH), 2,
                ),
                "learning_days": self._learner.days_learned,
                "evening_target_soc": self._compute_grid_charge_target(),
                "overnight_target_soc": self._compute_overnight_target(
                    self._next_morning_peak,
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

        # Priority 2: OUTAGE_PREP
        if self.is_mode_enabled(MODE_OUTAGE_PREP):
            if self._check_outage_prep_conditions():
                return MODE_OUTAGE_PREP

        # Priority 3: GRID_CHARGE (two-peak charger)
        if self.is_mode_enabled(MODE_GRID_CHARGE):
            if self._check_grid_charge_conditions():
                return MODE_GRID_CHARGE

        # Priority 4: REBALANCE
        if self.is_mode_enabled(MODE_REBALANCE):
            if self._check_rebalance_conditions(soc_1, soc_2, backup_soc_1, backup_soc_2):
                return MODE_REBALANCE

        # Priority 5: SOLAR_CURTAIL
        if self.is_mode_enabled(MODE_SOLAR_CURTAIL):
            if self._check_solar_curtail_conditions():
                return MODE_SOLAR_CURTAIL

        # Priority 6: SELF_CONSUMPTION (always valid)
        return MODE_SELF_CONSUMPTION

    def _check_outage_prep_conditions(self) -> bool:
        return self._outage_prep_active

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
        # Don't rebalance while actively grid-charging (or prepping for an
        # outage). Charging drives the two packs apart, so letting REBALANCE fire
        # in the same window makes them fight — one charges from grid while the
        # other discharges to it. Grid charge already outranks REBALANCE; this
        # also blocks it in any cycle where charging is engaged.
        if self._grid_charge_active or self._outage_prep_active:
            return False

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
        self, forecasts: list[dict], required_hours: float, deadline: datetime,
    ) -> set[str]:
        """Select the cheapest *contiguous* block of intervals covering required_hours.

        Picking the N globally-cheapest intervals scatters the charge across
        non-adjacent 5-min slots, so GRID_CHARGE toggles on/off every few minutes
        and REBALANCE steals the gaps — the pack thrashes instead of charging.
        Instead, slide over the time-ordered eligible intervals and pick the
        single contiguous run (cheapest by total cost) that covers the required
        hours, so the charge runs as one uninterrupted block.

        Returns a set of start_time strings for the selected intervals.
        """
        now = dt_util.now()
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
                # Include if start >= now AND end <= deadline. The deadline is the
                # next price-peak onset, so every eligible interval is pre-peak
                # (off-peak) by construction — no separate window gate needed.
                if start_dt >= now and end_dt <= deadline:
                    eligible.append({
                        "start_time": start_str,
                        "start_dt": start_dt,
                        "per_kwh": float(interval.get("per_kwh", 999)),
                        "duration_hours": (end_dt - start_dt).total_seconds() / 3600,
                    })
            except (ValueError, TypeError, KeyError):
                continue

        if not eligible:
            return set()

        # Order by time so a run of consecutive list entries is contiguous in
        # time (intervals within a single off-peak window have no gaps).
        eligible.sort(key=lambda x: x["start_dt"])
        total_hours = sum(e["duration_hours"] for e in eligible)
        if total_hours <= required_hours:
            # Not enough cheap time to be selective — take everything available.
            return {e["start_time"] for e in eligible}

        # Sliding window: cheapest contiguous run covering >= required_hours.
        n = len(eligible)
        best_cost: float | None = None
        best_range: tuple[int, int] | None = None
        for i in range(n):
            hours = 0.0
            cost = 0.0
            for j in range(i, n):
                dur = eligible[j]["duration_hours"]
                hours += dur
                cost += eligible[j]["per_kwh"] * dur
                if hours >= required_hours:
                    if best_cost is None or cost < best_cost:
                        best_cost = cost
                        best_range = (i, j)
                    break

        if best_range is None:
            return {e["start_time"] for e in eligible}
        lo, hi = best_range
        return {eligible[k]["start_time"] for k in range(lo, hi + 1)}

    def _kwh_to_soc(self, kwh: float) -> float:
        """Convert an energy amount to SOC percent of the combined pack."""
        capacity_kwh = 2 * self.config_entry.data.get(CONF_CAPACITY_KWH, 24.5)
        return (kwh / capacity_kwh) * 100 if capacity_kwh else 0.0

    def _backup_reserve_soc(self) -> float:
        """The Sigen ESS backup-reserve SOC below which the packs won't discharge.

        Energy sitting below this floor is not deliverable to the house, so a
        kWh-derived charge target must be lifted by this much or the pack floors
        out mid-peak with the load only partly covered. Uses the mean of the two
        packs' configured backup SOC (they share one meter); 0 if unreadable.
        """
        config = self.config_entry.data
        values = [
            v for v in (
                self._get_state_float(config[CONF_BACKUP_SOC_1]),
                self._get_state_float(config[CONF_BACKUP_SOC_2]),
            ) if v is not None
        ]
        return sum(values) / len(values) if values else 0.0

    def _compute_grid_charge_target(self) -> float:
        """Evening (daytime-phase) target SOC — enough to cover the *learned*
        evening-peak load, clamped to [min_reserve, max_charge].

        The learned load is deliverable energy, so it sits *on top of* the ESS
        backup reserve (the pack won't discharge below it); without that offset
        the target floors out mid-peak with ~reserve% of the load uncovered.

        Seasonal for free: the trailing average tracks dark winter evenings up
        (bigger load → higher target) and lighter summer evenings down.
        """
        min_reserve = self._opts[OPT_GRID_CHARGE_MIN_RESERVE_SOC]
        max_charge = self._opts[OPT_GRID_CHARGE_MAX_SOC]
        evening_kwh = self._learner.evening_kwh(DEFAULT_SEED_EVENING_KWH)
        reserve = self._backup_reserve_soc()
        target = reserve + self._kwh_to_soc(evening_kwh)
        clamped = round(max(min_reserve, min(max_charge, target)), 1)
        _LOGGER.debug(
            "Evening target %.1f%% (learned evening load %.1f kWh + reserve "
            "%.1f%%, %d days)",
            clamped, evening_kwh, reserve, self._learner.days_learned,
        )
        return clamped

    def _solcast_today_entity(self) -> str | None:
        """Entity id for *today's* Solcast forecast.

        Prefers the configured value. If the site only wired up the "tomorrow"
        sensor (today was an optional field and long went unused), derive today's
        from it — the Solcast integration names the pair identically bar the
        `_today` / `_tomorrow` suffix — so the post-midnight overnight path reads
        the right day without needing a reconfigure.
        """
        data = self.config_entry.data
        today = data.get(CONF_SOLCAST_TODAY)
        if today:
            return today
        tomorrow = data.get(CONF_SOLCAST_TOMORROW)
        if tomorrow and tomorrow.endswith("_tomorrow"):
            return tomorrow[: -len("_tomorrow")] + "_today"
        return None

    def _overnight_solar_kwh(
        self, morning_onset: datetime | None,
    ) -> tuple[float | None, str]:
        """Forecast generation (kWh) for the solar day that will refill the pack
        *after* this overnight charge, plus a short label of which day was read.

        The overnight window straddles midnight (22:00 → morning peak), so the
        day that dawns after the charge is *tomorrow* before midnight but
        *today* once past it. We decide from the date of the morning-peak onset
        this cap charges toward: same date as now → the peak is later today →
        today's Solcast; otherwise → tomorrow's. Falls back to the other day's
        entity if the preferred one is unavailable, and to None only when neither
        can be read.
        """
        now = dt_util.now()
        onset = morning_onset or self._next_morning_peak
        if onset is not None:
            coming_day_is_today = onset.date() == now.date()
        else:
            coming_day_is_today = now.hour < GRID_CHARGE_MORNING_DEADLINE_HOUR

        today_ent = self._solcast_today_entity()
        tomorrow_ent = self.config_entry.data.get(CONF_SOLCAST_TOMORROW)
        if coming_day_is_today:
            primary, secondary, label = today_ent, tomorrow_ent, "today"
        else:
            primary, secondary, label = tomorrow_ent, today_ent, "tomorrow"

        value = self._get_state_float(primary) if primary else None
        if value is not None:
            return value, label
        # Preferred day unavailable — fall back to the other day's forecast.
        value = self._get_state_float(secondary) if secondary else None
        return value, (label + "(fallback)" if value is not None else "n/a")

    def _compute_overnight_target(
        self, morning_onset: datetime | None = None,
    ) -> float:
        """Overnight (morning-phase) cap SOC.

        Floor = the *learned* morning-peak load as SOC — this guarantees the
        morning peak is covered from battery. Ceiling = max_charge. From the
        ceiling we subtract the exportable solar surplus (the *coming* day's
        Solcast minus the learned daytime load) so a sunny/low-load day leaves
        headroom for solar to fill the pack for free, while a winter/high-load
        day (≈ zero surplus) charges to the ceiling overnight. No forecast →
        charge to the ceiling to be safe.

        The coming solar day is resolved by `_overnight_solar_kwh` from the
        morning-peak onset, so the post-midnight part of the window reads
        today's forecast rather than tomorrow's.
        """
        min_reserve = self._opts[OPT_GRID_CHARGE_MIN_RESERVE_SOC]
        ceiling = self._opts[OPT_GRID_CHARGE_MAX_SOC]

        morning_kwh = self._learner.morning_kwh(DEFAULT_SEED_MORNING_KWH)
        daytime_kwh = self._learner.daytime_kwh(DEFAULT_SEED_DAYTIME_KWH)
        reserve = self._backup_reserve_soc()
        floor = max(
            min_reserve, min(ceiling, reserve + self._kwh_to_soc(morning_kwh)),
        )

        solar_kwh, solar_day = self._overnight_solar_kwh(morning_onset)
        if solar_kwh is None:
            cap = ceiling
        else:
            surplus_kwh = max(0.0, solar_kwh - daytime_kwh)
            cap = ceiling - self._kwh_to_soc(surplus_kwh)

        clamped = round(max(floor, min(ceiling, cap)), 1)
        _LOGGER.debug(
            "Overnight target %.1f%% (floor %.1f%% from morning %.1f kWh; "
            "ceiling %.0f%%; %s solar %s − daytime %.1f kWh)",
            clamped, floor, morning_kwh, ceiling, solar_day,
            f"{solar_kwh:.1f}" if solar_kwh is not None else "n/a", daytime_kwh,
        )
        return clamped

    @staticmethod
    def _next_hour_after(now: datetime, hour: int) -> datetime:
        """The next occurrence of `hour`:00 local time strictly after `now`."""
        cand = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if cand <= now:
            cand += timedelta(days=1)
        return cand

    @staticmethod
    def _percentile(values: list[float], q: float) -> float:
        """Simple nearest-rank percentile (q in 0..1)."""
        if not values:
            return 0.0
        ordered = sorted(values)
        idx = int(q * (len(ordered) - 1))
        return ordered[idx]

    def _detect_peak_onset(
        self,
        forecasts: list[dict] | None,
        now: datetime,
        band: tuple[int, int],
        fallback_hour: int,
    ) -> tuple[datetime, bool]:
        """Detect the next price-peak onset within a time-of-day `band`.

        Returns (onset_datetime, is_fallback). The onset is the start of the next
        forecast interval — occurring after `now`, with its local hour inside
        `band` — whose price steps above a low-percentile baseline (× factor) or
        is flagged high/spike by Amber, and which is *sustained* (the following
        interval is peak too, so a lone blip doesn't trigger). When no forecast or
        no qualifying peak is found, falls back to the next `fallback_hour`.
        """
        fallback = self._next_hour_after(now, fallback_hour)
        if not forecasts:
            return fallback, True

        parsed: list[tuple[datetime, float, str]] = []
        prices: list[float] = []
        for interval in forecasts:
            start = dt_util.parse_datetime(interval.get("start_time", "") or "")
            if start is None:
                continue
            try:
                price = float(interval.get("per_kwh"))
            except (TypeError, ValueError):
                continue
            start = dt_util.as_local(start)
            desc = str(interval.get("descriptor", "")).lower()
            parsed.append((start, price, desc))
            prices.append(price)

        if not parsed:
            return fallback, True

        parsed.sort(key=lambda x: x[0])
        baseline = self._percentile(prices, PEAK_DETECT_BASELINE_PCTL)
        threshold = baseline * PEAK_DETECT_FACTOR
        band_start, band_end = band

        def is_peak(price: float, desc: str) -> bool:
            return price >= threshold or desc in ("high", "spike", "extremehigh")

        n = len(parsed)
        for i, (start, price, desc) in enumerate(parsed):
            if start <= now:
                continue
            if not (band_start <= start.hour < band_end):
                continue
            if not is_peak(price, desc):
                continue
            # Must be the START of a peak run — the previous interval is not peak.
            # This stops a mid-peak interval being read as a fresh onset (which
            # would make the charger think a new peak is 30 min away and charge
            # right through the peak we're already in).
            if i == 0 or is_peak(parsed[i - 1][1], parsed[i - 1][2]):
                continue
            # Sustained: require the next interval to be peak too (unless last),
            # so a lone one-interval price blip doesn't count as a peak.
            if i + 1 < n:
                _, next_price, next_desc = parsed[i + 1]
                if not is_peak(next_price, next_desc):
                    continue
            _LOGGER.debug(
                "Peak onset detected %s @ $%.4f/kWh (baseline $%.4f × %.1f = $%.4f)",
                start.strftime("%a %H:%M"), price, baseline, PEAK_DETECT_FACTOR, threshold,
            )
            return start, False

        return fallback, True

    def _resolve_charge_phase(
        self, now: datetime, morning_onset: datetime, evening_onset: datetime,
    ) -> tuple[str | None, datetime | None]:
        """Which pre-peak charge window (if any) `now` falls in, and its deadline.

        - Daytime window: [09:00 on the evening peak's day, evening_onset).
        - Overnight window: [22:00 the evening before the morning peak, morning_onset).
        Returns (None, None) when `now` is inside a peak period or between windows.
        """
        daytime_start = evening_onset.replace(
            hour=GRID_CHARGE_DAYTIME_START_HOUR, minute=0, second=0, microsecond=0,
        )
        if daytime_start <= now < evening_onset:
            return "daytime", evening_onset

        overnight_start = morning_onset.replace(
            hour=GRID_CHARGE_OVERNIGHT_START_HOUR, minute=0, second=0, microsecond=0,
        ) - timedelta(days=1)
        if overnight_start <= now < morning_onset:
            return "overnight", morning_onset

        return None, None

    async def _async_evaluate_grid_charge(self, mean_soc: float) -> bool:
        """Evaluate whether GRID_CHARGE should be active this cycle.

        Two phases, each charging toward its target by the *detected* onset of the
        next price peak (not a fixed clock hour):
        - Overnight: charge toward the overnight cap by the morning-peak onset.
        - Daytime: let solar charge first, top up toward the evening target by the
          evening-peak onset (which shifts later in summer as the tariff peak does).
        Outside both pre-peak windows (i.e. during a peak) GRID_CHARGE is inactive.
        """
        charge_rate_kw = self._opts[OPT_GRID_CHARGE_RATE_KW]
        capacity_kwh = 2 * self.config_entry.data.get(CONF_CAPACITY_KWH, 24.5)
        now = dt_util.now()

        forecasts = await self._async_fetch_amber_forecasts()

        morning_onset, _m_fb = self._detect_peak_onset(
            forecasts, now, MORNING_PEAK_BAND, GRID_CHARGE_MORNING_DEADLINE_HOUR,
        )
        evening_onset, _e_fb = self._detect_peak_onset(
            forecasts, now, EVENING_PEAK_BAND, FALLBACK_EVENING_PEAK_HOUR,
        )
        self._next_morning_peak = morning_onset
        self._next_evening_peak = evening_onset

        phase, deadline = self._resolve_charge_phase(now, morning_onset, evening_onset)
        if phase == "overnight":
            target_soc = self._compute_overnight_target(morning_onset)
        elif phase == "daytime":
            target_soc = self._compute_grid_charge_target()
        else:
            # Inside a peak period / between windows — don't charge. Keep the
            # exposed target sensor meaningful while idle.
            self._grid_charge_target = self._compute_grid_charge_target()
            return False

        self._grid_charge_target = target_soc

        # Hysteresis: stop at target, don't restart until a configurable band
        # below it. A wider band stops the mode re-triggering every cycle as load
        # nibbles the pack just under target.
        hysteresis = self._opts[OPT_GRID_CHARGE_HYSTERESIS_SOC]
        if self._current_mode == MODE_GRID_CHARGE:
            if mean_soc >= target_soc:
                _LOGGER.info(
                    "GRID_CHARGE stop (%s): SOC %.1f%% >= target %.1f%%",
                    phase, mean_soc, target_soc,
                )
                return False
        else:
            if mean_soc >= (target_soc - hysteresis):
                return False

        soc_deficit = max(0.0, target_soc - mean_soc)
        deficit_kwh = (soc_deficit / 100.0) * capacity_kwh
        required_hours = deficit_kwh / self._effective_charge_rate_kw(charge_rate_kw)
        if required_hours <= 0:
            return False

        hours_remaining = (deadline - now).total_seconds() / 3600
        if hours_remaining <= 0:
            return False

        # Forced charge: not enough cheap time left before the peak to be selective
        if hours_remaining < required_hours * 1.5:
            _LOGGER.info(
                "GRID_CHARGE forced (%s): %.2fh to peak %s < %.2fh required × 1.5",
                phase, hours_remaining, deadline.strftime("%a %H:%M"), required_hours,
            )
            return True

        # No forecast → can't select cheap intervals; only the forced path above
        # (which needs none) can act. Stay idle rather than charge blindly.
        if not forecasts:
            return False

        selected = self._select_cheapest_charge_window(forecasts, required_hours, deadline)
        if not selected:
            _LOGGER.debug(
                "GRID_CHARGE (%s): no eligible intervals before peak %s",
                phase, deadline.strftime("%a %H:%M"),
            )
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

    def _select_cheapest_intervals_in_window(
        self,
        forecasts: list[dict],
        required_hours: float,
        window_start: datetime,
        window_end: datetime,
    ) -> set[str]:
        """Pick cheapest forecast intervals fully inside [window_start, window_end]."""
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
                if start_dt >= window_start and end_dt <= window_end:
                    eligible.append({
                        "start_time": start_str,
                        "per_kwh": float(interval.get("per_kwh", 999)),
                        "duration_hours": (end_dt - start_dt).total_seconds() / 3600,
                    })
            except (ValueError, TypeError, KeyError):
                continue

        if not eligible:
            return set()

        eligible.sort(key=lambda x: x["per_kwh"])
        selected: set[str] = set()
        hours_covered = 0.0
        for interval in eligible:
            if hours_covered >= required_hours:
                break
            selected.add(interval["start_time"])
            hours_covered += interval["duration_hours"]
        return selected

    async def _async_evaluate_outage_prep(self, mean_soc: float) -> bool:
        """Evaluate whether OUTAGE_PREP should be active this cycle.

        Charge window runs from OUTAGE_PREP_START_HOUR on the day BEFORE the
        configured outage date through OUTAGE_PREP_END_HOUR on the outage day.
        Selects cheapest Amber intervals to cover the required charge, or
        forces charging if not enough time remains.
        """
        date_str = self._opts.get(OPT_OUTAGE_DATE, "")
        if not date_str:
            return False
        try:
            outage_date = date.fromisoformat(date_str)
        except ValueError:
            _LOGGER.warning("OUTAGE_PREP: invalid date %r in options", date_str)
            return False

        now = dt_util.now()
        tz = now.tzinfo
        window_start = datetime.combine(
            outage_date - timedelta(days=1),
            time(OUTAGE_PREP_START_HOUR, 0),
            tzinfo=tz,
        )
        window_end = datetime.combine(
            outage_date, time(OUTAGE_PREP_END_HOUR, 0), tzinfo=tz,
        )

        if now < window_start or now >= window_end:
            return False

        target_soc = self._opts[OPT_OUTAGE_TARGET_SOC]

        # Hysteresis: stop at target, 1% buffer to start
        if self._current_mode == MODE_OUTAGE_PREP:
            if mean_soc >= target_soc:
                _LOGGER.info(
                    "OUTAGE_PREP stop: SOC %.1f%% >= target %.1f%%",
                    mean_soc, target_soc,
                )
                return False
        else:
            if mean_soc >= (target_soc - 1.0):
                return False

        charge_rate_kw = self._opts[OPT_GRID_CHARGE_RATE_KW]
        capacity_kwh = 2 * self.config_entry.data.get(CONF_CAPACITY_KWH, 24.5)
        soc_deficit = max(0.0, target_soc - mean_soc)
        deficit_kwh = (soc_deficit / 100.0) * capacity_kwh
        required_hours = deficit_kwh / self._effective_charge_rate_kw(charge_rate_kw)
        if required_hours <= 0:
            return False

        hours_remaining = (window_end - now).total_seconds() / 3600

        if hours_remaining < required_hours * 1.5:
            _LOGGER.info(
                "OUTAGE_PREP forced: %.2fh remaining < %.2fh required × 1.5",
                hours_remaining, required_hours,
            )
            return True

        forecasts = await self._async_fetch_amber_forecasts()
        if forecasts is None:
            _LOGGER.info("OUTAGE_PREP: no forecasts, charging immediately to be safe")
            return True

        selected = self._select_cheapest_intervals_in_window(
            forecasts, required_hours, window_start, window_end,
        )
        if not selected:
            _LOGGER.debug("OUTAGE_PREP: no eligible intervals in window")
            return False

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
                            "OUTAGE_PREP active: $%.4f/kWh in cheapest window",
                            interval.get("per_kwh", 0),
                        )
                        return True
                    _LOGGER.debug(
                        "OUTAGE_PREP inactive: $%.4f/kWh not in cheapest window",
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

    def _get_combined_load_kw(self) -> float | None:
        """Read combined household load from both Sigen plants (kW)."""
        load_1 = self._get_state_float(LOAD_POWER_1)
        load_2 = self._get_state_float(LOAD_POWER_2)
        if load_1 is not None and load_2 is not None:
            return load_1 + load_2
        if load_1 is not None:
            return load_1
        if load_2 is not None:
            return load_2
        return None

    def _effective_charge_rate_kw(self, charge_rate_kw: float) -> float:
        """Net power actually reaching the battery when grid-charging.

        The charge is applied by setting `grid_import_limitation = charge_rate`,
        but on Sigen that caps *total* grid import (household load + battery), and
        Command Charging (PV First) also diverts PV into the pack — so the battery
        fills at roughly `charge_rate + PV − load`, not the full `charge_rate`.
        Sizing `required_hours` off the raw rate under-books the cheap window, so
        the pack lands just shy of target and then top-ups in the pricier pre-peak
        tail. Uses live PV/load (re-evaluated each cycle, so it self-corrects) and
        clamps to a small floor so the estimate stays finite when load transiently
        exceeds the rate.
        """
        pv = self._get_combined_pv_kw() or 0.0
        load = self._get_combined_load_kw() or 0.0
        return max(GRID_CHARGE_MIN_EFFECTIVE_KW, charge_rate_kw + pv - load)

    async def async_backfill_learning(self) -> int:
        """Seed the load learner from recorder history and refresh.

        Returns the number of complete days written. Exposed via the
        ``sentinel.backfill_learning`` service so learning can be expedited
        instead of waiting for a fortnight of live accumulation.
        """
        days = await self._learner.async_backfill(
            self.hass, [LOAD_POWER_1, LOAD_POWER_2], dt_util.now(),
        )
        await self.async_request_refresh()
        return days

    async def _apply_mode(self, mode: str) -> None:
        """Apply the specified mode."""
        if mode == MODE_FAILSAFE:
            await self._async_apply_failsafe()
        elif mode == MODE_REBALANCE:
            await self._async_apply_rebalance()
        elif mode == MODE_SOLAR_CURTAIL:
            await self._async_apply_solar_curtail()
        elif mode == MODE_GRID_CHARGE:
            await self._async_apply_grid_charge()
        elif mode == MODE_OUTAGE_PREP:
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

    async def _async_apply_grid_charge(self) -> None:
        """GRID_CHARGE: both batteries Command Charging (PV First) at configured rate.

        Proportionally shifts power toward the lower-SOC battery to naturally
        resolve imbalances during charging, avoiding REBALANCE contention.
        """
        config = self.config_entry.data
        charge_rate_kw = self._opts[OPT_GRID_CHARGE_RATE_KW]

        soc_1 = self._get_state_float(config[CONF_SOC_1])
        soc_2 = self._get_state_float(config[CONF_SOC_2])

        if soc_1 is None or soc_2 is None:
            # Fall back to equal split if SOC unavailable
            per_plant = min(charge_rate_kw / 2, DEFAULT_MAX_GRID_LIMIT)
            rate_1 = rate_2 = per_plant
        else:
            soc_diff = abs(soc_1 - soc_2)
            # Linear shift: equal at 0% diff, up to 100% to lower battery at 100% diff
            share_lower = 0.5 + soc_diff / 200.0
            share_higher = 1.0 - share_lower

            if soc_1 <= soc_2:
                rate_1 = min(charge_rate_kw * share_lower, DEFAULT_MAX_GRID_LIMIT)
                rate_2 = min(charge_rate_kw * share_higher, DEFAULT_MAX_GRID_LIMIT)
            else:
                rate_2 = min(charge_rate_kw * share_lower, DEFAULT_MAX_GRID_LIMIT)
                rate_1 = min(charge_rate_kw * share_higher, DEFAULT_MAX_GRID_LIMIT)

            if soc_diff >= 1.0:
                _LOGGER.debug(
                    "GRID_CHARGE proportional split: SOC %.1f%%/%.1f%% → plant1 %.2fkW plant2 %.2fkW",
                    soc_1, soc_2, rate_1, rate_2,
                )

        await self._set_both_mode(MODE_COMMAND_CHARGING_PV_FIRST)
        await self._call_service_set_limit(config[CONF_IMPORT_LIMIT_1], rate_1)
        await self._call_service_set_limit(config[CONF_IMPORT_LIMIT_2], rate_2)
        await self._call_service_set_limit(config[CONF_EXPORT_LIMIT_1], DEFAULT_MAX_GRID_LIMIT)
        await self._call_service_set_limit(config[CONF_EXPORT_LIMIT_2], DEFAULT_MAX_GRID_LIMIT)

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
        """Restore all grid limits to maximum (12 kW)."""
        config = self.config_entry.data
        limit = DEFAULT_MAX_GRID_LIMIT
        await self._call_service_set_limit(config[CONF_EXPORT_LIMIT_1], limit)
        await self._call_service_set_limit(config[CONF_IMPORT_LIMIT_1], limit)
        await self._call_service_set_limit(config[CONF_EXPORT_LIMIT_2], limit)
        await self._call_service_set_limit(config[CONF_IMPORT_LIMIT_2], limit)

    async def _call_service_set_mode(self, entity_id: str, mode: str) -> None:
        """Set a battery mode via select service.

        Skips the write when the target entity is unavailable (e.g. a plant
        that has dropped off the network) or already in the requested mode.
        Repeatedly writing to an unreachable Sigen gateway hammers its
        single-connection Modbus interface and can knock it further offline,
        so we never issue a write we know will fail or be a no-op.
        """
        if not self._plant_is_reachable_for(entity_id):
            return
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return
        if state.state == mode:
            return
        await self._paced_service_call(
            "select", "select_option",
            {"entity_id": entity_id, "option": mode},
        )

    async def _call_service_set_limit(self, entity_id: str, value: float) -> None:
        """Set a grid limit via number service.

        Skips the write when the target entity is unavailable or already at
        the requested value (within WRITE_TOLERANCE). This stops the FAILSAFE
        re-apply loop from write-storming an offline plant and trims
        steady-state Modbus writes to genuine setpoint changes only.
        """
        if not self._plant_is_reachable_for(entity_id):
            return
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return
        try:
            current = float(state.state)
        except (ValueError, TypeError):
            current = None
        if current is not None and abs(current - value) < WRITE_TOLERANCE:
            return
        await self._paced_service_call(
            "number", "set_value",
            {"entity_id": entity_id, "value": value},
        )

    async def _paced_service_call(
        self, domain: str, service: str, data: dict
    ) -> None:
        """Issue a Modbus-backed service call, paced so the Sigen dongles are
        never hit with a burst of commands.

        The gateways have a single-connection Modbus interface that can be
        knocked offline by too many writes at once. Every actual write to a
        plant routes through here: consecutive writes are spaced by at least
        WRITE_MIN_GAP_SECONDS, and each is awaited to completion (blocking)
        before the next is dispatched, so a multi-control mode change trickles
        out one Modbus transaction at a time instead of all at once.
        """
        gap = WRITE_MIN_GAP_SECONDS - (monotonic() - self._last_write_monotonic)
        if gap > 0:
            await asyncio.sleep(gap)
        try:
            await self.hass.services.async_call(
                domain, service, data, blocking=True,
            )
        finally:
            self._last_write_monotonic = monotonic()

    def _plant_is_reachable_for(self, entity_id: str) -> bool:
        """Whether the plant that owns `entity_id` is currently reachable.

        The Sigen *number* entities (grid limits, backup SOC) keep reporting a
        stale numeric value when their plant drops off the network — unlike the
        sensors/select, which go unavailable. So gating a write on the target
        entity's own availability isn't enough to stop FAILSAFE hammering an
        offline plant. The plant's SOC sensor DOES go unavailable, so we use it
        as the reachability signal for every write to that plant.
        """
        config = self.config_entry.data
        plant2_targets = {
            config[CONF_MODE_2], config[CONF_EXPORT_LIMIT_2],
            config[CONF_IMPORT_LIMIT_2], config[CONF_BACKUP_SOC_2],
        }
        soc_entity = (
            config[CONF_SOC_2] if entity_id in plant2_targets
            else config[CONF_SOC_1]
        )
        soc = self.hass.states.get(soc_entity)
        return soc is not None and soc.state not in ("unknown", "unavailable")

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
