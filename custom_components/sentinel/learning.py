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

from datetime import datetime
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

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
            for key in self._history:
                self._history[key].append(round(self._partial[key], 3))
                self._history[key] = self._history[key][-MAX_DAYS:]
                self._partial[key] = 0.0
            _LOGGER.debug("LoadLearner rollover %s -> %s", self._current_day, today)
            self._current_day = today
            self._last_ts = None  # don't integrate across the rollover boundary
            await self._async_save()
            self._last_save_ts = now

        if self._last_ts is not None and load_kw is not None:
            dt_seconds = (now - self._last_ts).total_seconds()
            if 0 < dt_seconds <= MAX_GAP_SECONDS:
                band = _band_of(now.hour)
                if band is not None:
                    self._partial[band] += load_kw * (dt_seconds / 3600.0)
        self._last_ts = now

        if (
            self._last_save_ts is None
            or (now - self._last_save_ts).total_seconds() >= SAVE_INTERVAL_SECONDS
        ):
            await self._async_save()
            self._last_save_ts = now

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
