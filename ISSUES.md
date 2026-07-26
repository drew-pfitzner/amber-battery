# Sentinel / Sigen — Known Issues & Investigation Log

_Last updated: 2026-07-26_

## TL;DR

Plant 1 (`192.168.1.82`) repeatedly drops off Home Assistant. Over one long
session we ruled out the network as the primary cause, fixed a self-inflicted
Sentinel write-storm, and reduced HA's polling — but the **root remaining
problem is that `.82`'s WiFi comms module is running at its connection limit
with no headroom.** The durable fix is **Ethernet for `.82`.**

---

## System topology & naming (the confusing part — read this first)

Two independent Sigenergy ESS plants, each with its own gateway/dongle on
**2.4 GHz WiFi** via UniFi FlexHD **"Fitz Farming Workshop AP"**. Router/DHCP is
**Google/Nest WiFi** (UniFi = APs/switches only; shows as "third-party gateway").
Both dongles on **static IP reservations**. Names are crossed between systems —
**always refer by IP**:

| IP | HA entities | HA config entry | UniFi client | Status |
|----|-------------|-----------------|--------------|--------|
| **192.168.1.79** | `sigen_plant_2_*` ("Sigen Plant 2") | "Sigen 2" `01KNP5RXRQ5GWEMM3PCQM22KAQ` | "Sigen 2" | **healthy** |
| **192.168.1.82** | `sigen_plant_*` / `sigen_inverter_*` (base) | "Sigen 1" `01KNP56N2KCYK6FDSESQD5NQDT` | "Sigen 1" | **problem child** |

- Sentinel integration config entry: `01KPX299CTBCVAZJCPQJ0HKNKS` (domain `sentinel`).
- Sigen Modbus: TCP port 502, unit/slave id 247.

---

## Root causes found (in order of discovery)

### 1. Two Sigen systems must not see each other on the LAN — FIXED
Sigenergy does not support two systems on the same network; they conflict when
they can discover each other. Symptom: `.82` half-joins WiFi then can't
communicate; flaps every ~15–20 min.

**Fix:** On the **"Fitz Farming IOT"** SSID, enable **both**:
- ✅ Client Device Isolation
- ✅ Multicast and Broadcast Blocker

Client isolation **alone is not enough** — it passes broadcast/mDNS, so the two
still discover each other. The broadcast blocker is what actually stopped it.
**Do NOT disable either** (turning isolation off made `.82` fully drop, app included).

### 2. Sentinel FAILSAFE write-storm — FIXED (took two passes)
When a plant's critical entities go unavailable, Sentinel enters FAILSAFE and
`_async_apply_failsafe()` re-writes limits/modes to **both** plants **every
cycle**. Against an offline `.82` those writes hammer its single-connection
Modbus interface and keep it wedged → self-sustaining feedback loop.

**Fix v1** (`coordinator.py`): added `WRITE_TOLERANCE` + guards in
`_call_service_set_mode` / `_call_service_set_limit` to skip a write when the
target entity is unavailable or already at the requested value.

**Fix v2** (the gotcha): the Sigen **number** entities (`grid_export/import_limitation`,
`ess_backup_state_of_charge`) keep reporting a **stale `0.0`** when their plant is
offline — they do **not** go `unavailable` like the sensors/select do. So limit
writes still leaked through. Added `_plant_is_reachable_for(entity_id)` which
gates every write on the plant's **SOC sensor** (which reliably goes unavailable),
keyed by whether the target is in the plant-2 config set.

Result: confirmed `.82` can drop and Sentinel issues **zero** writes to it.

### 3. `.82`'s WiFi comms module is marginal — **OPEN (root cause)**
Even with the network conflict fixed and the write-storm gone:
- `.82` holds WiFi association fine (30+ min), but its **Modbus/comms tips over
  whenever anything beyond a single throttled HA poll connects to it.**
- **Opening the mySigen app reproducibly drops `.82`** (confirmed by timing: dropped
  the instant the app was opened; WiFi stayed associated, only Modbus died). The
  app is a second client the module can't spare.
- Once wedged it **does not self-recover** — needs a **power-cycle**.
- It was only ever rock-stable (36 min) with **zero** HA traffic (config entry disabled).

`.79` (identical hardware) handles the same polling + app + cloud fine, so `.82`'s
module specifically has ~one connection of headroom.

---

## Changes made this session

- **coordinator.py** (Sentinel): write guards + `_plant_is_reachable_for` (see #2).
- **Sigen scan_interval for `.82` lowered 5s → 30s** (`.79` left at 5s). The `sigen`
  integration has `DEFAULT_SCAN_INTERVAL = 5`, no UI option, no reconfigure support —
  changed by editing `/config/.storage/core.config_entries`
  (`data.plant_connection.scan_interval`) + restart. Reads are the steady load;
  Sentinel control **writes are separate Modbus transactions on top**, but now rare
  (only fire on a genuine setpoint change, never to an offline plant).
- **Deleted 3 legacy `battery_rebalancing_*` automations** (superseded by Sentinel's
  REBALANCE mode; were a second controller fighting over the same Sigen limits).
  ⚠️ Their **5 `input_*` helpers are YAML-defined orphans** (now `unavailable`) —
  still need removal from the YAML config; the API can't delete YAML helpers.

---

## Still OPEN — pick up here next time

1. **`.82` drops whenever a 2nd client touches it and won't recover without a
   power-cycle.** → **Recommended fix: put `.82` on Ethernet.** The gateway has an
   RJ45 port; wired Modbus gives the module capacity for HA + app + cloud at once,
   and lets it be cleanly separated (VLAN/switch) from `.79` without relying on
   WiFi client-isolation. This is the real cure; WiFi software tuning is exhausted.

2. **Sentinel FAILSAFE halts BOTH plants when either is unavailable.** So one `.82`
   blip freezes `.79`'s arbitrage too (max self-consumption, no grid charge / morning
   floor). **Proposed: per-plant failsafe** — isolate the dead plant, keep managing
   the live one. NOT yet built. High value regardless of Ethernet; makes overnight
   runs productive even when `.82` drops.

3. **Remove the 5 orphaned `input_*` rebalancing helpers** from YAML config.

---

## How to check status quickly

- `sensor.sigen_plant_grid_connection_status` / `sensor.sigen_plant_battery_state_of_charge`
  — `.82` health (unknown/unavailable = down).
- `binary_sensor.failsafe_active` — ON means a plant is unavailable and BOTH are frozen.
- Error log filter `192.168.1.82`: `Failed to write …` = write-storm (should be gone);
  `Modbus error reading …` / `Failed to connect` = `.82` unreachable for reads.
- UniFi WiFi association: controller `https://192.168.1.64`, Integration API with
  `X-API-KEY` (key in `UNIFY.md`), site `88f7af54-98f8-306a-a1c7-c9349722b1f6`,
  endpoint `/proxy/network/integrations/v1/sites/<site>/clients`. A changing
  `connectedAt` = WiFi re-association (flapping); steady = WiFi is fine (problem is
  higher up, at Modbus/comms).

## Deploy notes (no auto-sync!)

Repo is **source only**. Live HA `custom_components` reached via Samba:
Finder ⌘K `smb://homeassistant.local` → mount `config` share →
`/Volumes/config/custom_components/sentinel/`. Copy the changed file, clear
`__pycache__/*.pyc`, then restart HA (integration `.py` changes need a full restart;
automations/helpers are editable live via the HA API).
