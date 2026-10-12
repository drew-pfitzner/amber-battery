"""Rolling load learner for Sentinel.

Learns how much energy the site consumes in each of three daily windows —
morning peak, solar-hours daytime, and evening peak — as a trailing N-day
average. GRID_CHARGE uses these to size its targets automatically, so the system
self-tunes across the seasons instead of relying on hand-set numbers:

- evening peak load  → how full to be by the evening peak (evening target)
- morning peak load  → the overnight floor that guarantees morning-peak cover
- daytime load       → the solar headroom to leave overnight (surplus = PV − this)

State is integrated from the combined load-power reading each coordinator cycle
and persisted with a Store so it survives restarts.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
MAX_DAYS = 14  # trailing window length for the rolling average

# Learning windows (local hour bands). Fixed clock bands keep the learned
# magnitudes stable day to day; the trailing average captures the seasonal drift.
MORNING_BAND = (6, 9)    # morning peak
DAYTIME_BAND = (9, 16)   # solar hours
EVENING_BAND = (16, 22)  # evening peak

# Ignore integration across gaps longer than this (e.g. a restart) so a long dt
# never dumps a phantom slab of energy into a bucket. 2× the 30 s cycle + margin.
MAX_GAP_SECONDS = 300
# Persist at least this often (plus on every day rollover) so a mid-day restart
# loses at most this much of the current day's partial accumulation.
SAVE_INTERVAL_SECONDS = 600


def _band_of(hour: int) -> str | None:
    """Map a local hour to its learning window, or None if outside all of them."""
    if MORNING_BAND[0] <= hour < MORNING_BAND[1]:
        return "morning"
    if DAYTIME_BAND[0] <= hour < DAYTIME_BAND[1]:
        return "daytime"
    if EVENING_BAND[0] <= hour < EVENING_BAND[1]:
        return "evening"
    return None


class LoadLearner:
    """Trailing per-window daily energy learner, persisted via Store."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_learning_{entry_id}")
        self._loaded = False
        self._history: dict[str, list[float]] = {
            "morning": [], "daytime": [], "evening": [],
        }
        self._partial: dict[str, float] = {
            "morning": 0.0, "daytime": 0.0, "evening": 0.0,
        }
        self._current_day: str | None = None
        self._last_ts: datetime | None = None
        self._last_save_ts: datetime | None = None
        # Whether the current day has integrated any real energy yet. Guards the
        # rollover so a day we never actually observed (stale-store phantom day,
        # or a deploy at/near midnight) is not stamped into history as a
        # misleading ~0 kWh "learned day" that would override the seeds.
        self._day_had_data: bool = False

    async def async_load(self) -> None:
        """Load persisted state once. Idempotent — safe to call every cycle."""
        if self._loaded:
            return
        data = await self._store.async_load()
        if data:
            hist = data.get("history", {})
            self._history = {
                k: [float(v) for v in hist.get(k, [])][-MAX_DAYS:]
                for k in self._history
            }
            partial = data.get("partial", {})
            self._partial = {
                k: float(partial.get(k, 0.0)) for k in self._partial
            }
            self._current_day = data.get("current_day")
        self._loaded = True
        _LOGGER.debug(
            "LoadLearner loaded: %d days evening history, current_day=%s",
            len(self._history["evening"]), self._current_day,
        )

    async def _async_save(self) -> None:
        await self._store.async_save({
            "history": self._history,
            "partial": self._partial,
            "current_day": self._current_day,
        })

    async def async_record(self, now: datetime, load_kw: float | None) -> None:
        """Integrate one cycle's energy into the current window's daily bucket.

        Rolls the previous day's partials into the trailing history on a date
        change, and persists periodically so an intra-day restart loses little.
        """
        if not self._loaded:
            return

        today = now.date().isoformat()
        if self._current_day is None:
            self._current_day = today

        if today != self._current_day:
            # Only record a day we actually observed. A phantom day (stale store
            # rolled over on the first post-deploy cycle, or a deploy right at
            # midnight) would otherwise append a ~0 kWh entry that silently
            # overrides the seed fallback in _avg().
            if self._day_had_data:
                for key in self._history:
                    self._history[key].append(round(self._partial[key], 3))
                    self._history[key] = self._history[key][-MAX_DAYS:]
                _LOGGER.debug(
                    "LoadLearner rollover %s -> %s (recorded)",
                    self._current_day, today,
                )
            else:
                _LOGGER.debug(
                    "LoadLearner rollover %s -> %s (skipped, no data)",
                    self._current_day, today,
                )
            for key in self._partial:
                self._partial[key] = 0.0
            self._current_day = today
            self._day_had_data = False
            self._last_ts = None  # don't integrate across the rollover boundary
            await self._async_save()
            self._last_save_ts = now

        if self._last_ts is not None and load_kw is not None:
            dt_seconds = (now - self._last_ts).total_seconds()
            if 0 < dt_seconds <= MAX_GAP_SECONDS:
                band = _band_of(now.hour)
                if band is not None:
                    self._partial[band] += load_kw * (dt_seconds / 3600.0)
                    self._day_had_data = True
        self._last_ts = now

        if (
            self._last_save_ts is None
            or (now - self._last_save_ts).total_seconds() >= SAVE_INTERVAL_SECONDS
        ):
            await self._async_save()
            self._last_save_ts = now

    async def async_backfill(
        self,
        hass: HomeAssistant,
        load_entities: list[str],
        now: datetime,
    ) -> int:
        """Seed history from recorder so the learner is useful immediately.

        Integrates the last MAX_DAYS of recorded load power for the given
        entities into per-day / per-window kWh, then overwrites the trailing
        history with the complete days found (today is partial, so excluded).
        Returns the number of complete days written. This lets the operator
        expedite learning instead of waiting a fortnight for it to accrue.
        """
        # Imported lazily: recorder is an optional core component and we only
        # need it for this one-shot operation.
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.history import (
            state_changes_during_period,
        )

        await self.async_load()

        start = dt_util.as_utc(now) - timedelta(days=MAX_DAYS + 1)
        end = dt_util.as_utc(now)

        # buckets[date_iso][band] = kwh, summed across all load entities.
        buckets: dict[str, dict[str, float]] = {}

        def _band_energy(states: list, scale: float) -> None:
            prev_t: datetime | None = None
            prev_v: float | None = None
            for st in states:
                try:
                    value = float(st.state) * scale
                except (ValueError, TypeError):
                    value = None
                ts = st.last_changed
                if (
                    prev_t is not None
                    and prev_v is not None
                    and prev_v >= 0
                ):
                    dt_seconds = (ts - prev_t).total_seconds()
                    if 0 < dt_seconds <= MAX_GAP_SECONDS:
                        # The prior value was held over [prev_t, ts); attribute
                        # its energy to that interval's local day and window.
                        local = dt_util.as_local(prev_t)
                        band = _band_of(local.hour)
                        if band is not None:
                            day = local.date().isoformat()
                            day_bucket = buckets.setdefault(
                                day, {"morning": 0.0, "daytime": 0.0, "evening": 0.0},
                            )
                            day_bucket[band] += prev_v * (dt_seconds / 3600.0)
                prev_t, prev_v = ts, value

        recorder = get_instance(hass)
        for entity_id in load_entities:
            # Unit sanity: live code treats consumed_power as kW. If the sensor
            # reports W, scale so integrated energy stays in kWh.
            scale = 1.0
            cur = hass.states.get(entity_id)
            if cur is not None and cur.attributes.get("unit_of_measurement") == "W":
                scale = 0.001
            history = await recorder.async_add_executor_job(
                state_changes_during_period, hass, start, end, entity_id,
            )
            _band_energy(history.get(entity_id, []), scale)

        today = now.date().isoformat()
        complete_days = sorted(d for d in buckets if d != today)
        complete_days = complete_days[-MAX_DAYS:]
        if not complete_days:
            _LOGGER.warning(
                "LoadLearner backfill found no complete days of recorder "
                "history for %s", load_entities,
            )
            return 0

        for key in self._history:
            self._history[key] = [
                round(buckets[d][key], 3) for d in complete_days
            ]
        # Keep accumulating today's partial live rather than double-counting it.
        self._current_day = today
        self._day_had_data = False
        self._last_ts = None
        for key in self._partial:
            self._partial[key] = 0.0
        await self._async_save()
        _LOGGER.info(
            "LoadLearner backfill wrote %d days (morning=%.1f daytime=%.1f "
            "evening=%.1f kWh avg)",
            len(complete_days),
            self.morning_kwh(0.0), self.daytime_kwh(0.0), self.evening_kwh(0.0),
        )
        return len(complete_days)

    def _avg(self, key: str, seed: float) -> float:
        """Trailing average for a window, or the seed until any full day exists."""
        values = self._history.get(key, [])
        if values:
            return sum(values) / len(values)
        return seed

    def morning_kwh(self, seed: float) -> float:
        return self._avg("morning", seed)

    def daytime_kwh(self, seed: float) -> float:
        return self._avg("daytime", seed)

    def evening_kwh(self, seed: float) -> float:
        return self._avg("evening", seed)

    @property
    def days_learned(self) -> int:
        """Number of complete days in the trailing history."""
        return len(self._history["evening"])
