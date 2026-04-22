# Sigen Rebalancer (Legacy)

**This integration is not deployed to Home Assistant.** It is kept here as the source code for porting into the **Sentinel** integration.

## What this is

A working HA custom integration that implements battery SOC rebalancing between two Sigen plants on split phases. All logic is in `coordinator.py`.

## Where it's going

The entire rebalancing logic from this integration is being ported into the new Sentinel integration (`../sentinel/`). Sentinel extends this single feature into a full energy management system with 7 operating modes, forecasting, price-based charging, and outage prep.

## How to use this folder

When building Sentinel Phase 1, reference this code:
- `coordinator.py` — port `_async_apply()`, `_async_stop()`, all safety conditions to Sentinel's `_async_apply_rebalance()` and `_async_apply_self_consumption()`
- `config_flow.py` — the Plant 1/2 entity selector pattern extends to Sentinel's 6-step flow
- `const.py` — all CONF_* and DEFAULT_* keys carry directly to Sentinel's const.py
- `number.py` — the `RebalancerNumberDescription` dataclass pattern extends to Sentinel's 13 number entities
- `sensor.py`, `binary_sensor.py`, `switch.py` — port net grid sensors and rebalancing active indicator

Do **not** deploy this integration. Do **not** copy it to your HA config. Build Sentinel instead.

## Plan reference

See `/Users/drewpfitzner/.claude/plans/dynamic-finding-gizmo.md` for the complete Sentinel design and phased build plan.
