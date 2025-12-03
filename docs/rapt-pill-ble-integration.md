# RAPT Pill BLE Integration Design

**Date:** 2025-12-03  
**Status:** Draft  
**Related docs:**  
- `docs/plans/2025-11-29-multi-hydrometer-design.md`  
- `docs/plans/2025-11-29-multi-hydrometer-impl.md`

## 1. Goals & Scope

Integrate the **RAPT Pill** floating hydrometer directly via **Bluetooth Low Energy (BLE)**, without relying on RAPT cloud services, and normalize its data into the existing universal ingest layer (`HydrometerReading` → `IngestManager`).

**Goals**
- Decode RAPT Pill BLE advertisements locally on a Raspberry Pi.
- Map RAPT metrics (temperature, gravity, battery, gravity velocity) into `HydrometerReading`.
- Treat RAPT as a first-class device type (`device_type="rapt"`) alongside Tilt, iSpindel, and GravityMon.
- Reuse existing components wherever possible:
  - `bleak` for scanning.
  - Ingest adapter architecture (`backend/ingest/adapters`).
  - `IngestManager` for calibration, storage, and WebSocket broadcast.

**Non-goals (for this doc)**
- Changing the existing Tilt BLE path to use the generic ingest layer (possible future refactor).
- Exposing a separate RAPT-specific HTTP API (RAPT will feed into existing generic/device APIs).
- Implementing any cloud polling of `api.rapt.io` (explicitly out of scope).

---

## 2. RAPT Pill BLE Protocol

RAPT Pills broadcast metrics in manufacturer data fields of BLE advertisements. The best public reference is the `rapt-ble` project:

- Repo: `sairon/rapt-ble`
- File: `src/rapt_ble/parser.py`

### 2.1 Manufacturer Data IDs

`BluetoothServiceInfo.manufacturer_data` (or Bleak’s equivalent) uses 16-bit manufacturer IDs as keys.

From `rapt_ble/parser.py`:

- **16722** – metrics payload, prefix `"RAPT"` (little-endian `0x52 0x41` / `"RA"`).
- **17739** – version payload, prefix `"KEG"` (little-endian `0x4b 0x45` / `"KE"`).

Interpretation:

- **Metrics** (temperature, gravity, battery, orientation) are carried in `manufacturer_data[16722]`.
- **Firmware version** is carried in `manufacturer_data[17739]`.
- BLE address (`service_info.address` / `device.address`) is used to derive a display name like `"RAPT Pill xx:yy"`.

### 2.2 Metrics Payload Layout

The parser describes two C structs; only the metrics layout is relevant for BrewSignal.

From the docstring:

```c
// Version 1 (with MAC, no gravity velocity)
typedef struct __attribute__((packed)) {
    char prefix[4];        // "RAPT"
    uint8_t version;       // always 0x01
    uint8_t mac[6];
    uint16_t temperature;  // x / 128 - 273.15
    float gravity;         // / 1000
    int16_t x;             // x / 16
    int16_t y;             // x / 16
    int16_t z;             // x / 16
    int16_t battery;       // x / 256
} RAPTPillMetricsV1;

// Version 2 (no MAC, with gravity velocity)
typedef struct __attribute__((packed)) {
    char prefix[4];        // "RAPT"
    uint8_t version;       // always 0x02
    bool gravity_velocity_valid;
    float gravity_velocity;
    uint16_t temperature;  // x / 128 - 273.15
    float gravity;         // / 1000
    int16_t x;             // x / 16
    int16_t y;             // x / 16
    int16_t z;             // x / 16
    int16_t battery;       // x / 256
} RAPTPillMetricsV2;
```

The actual parser implementation (simplified) is:

```python
RAPTPillMetrics = namedtuple(
    "RAPTPillMetrics", "version, mac, temperature, gravity, x, y, z, battery"
)

if len(data) != 23:
    raise ValueError("Metrics data must have length 23")

# Drop the first 2 bytes of the prefix, start at version
metrics_raw = RAPTPillMetrics._make(unpack(">B6sHfhhhh", data[2:]))

metrics = RAPTPillMetrics(
    version=metrics_raw.version,
    mac=hexlify(metrics_raw.mac).decode("ascii") if metrics_raw.version == 1 else "",
    temperature=round(metrics_raw.temperature / 128 - 273.15, 2),
    gravity=round(metrics_raw.gravity / 1000, 4),
    x=metrics_raw.x / 16,
    y=metrics_raw.y / 16,
    z=metrics_raw.z / 16,
    battery=round(metrics_raw.battery / 256),
)
```

**Key facts for BrewSignal:**

- The metrics payload in `manufacturer_data[16722]` is **23 bytes**.
- Parsing (big-endian) from `data[2:]` yields:
  - `version: uint8` – 1 or 2.
  - `mac: 6 bytes` – only valid for version 1; empty string for v2.
  - `temperature_raw: uint16` – convert to °C via `T = raw / 128 - 273.15`.
  - `gravity_raw: float32` – convert to SG via `SG = raw / 1000`.
  - `x, y, z: int16` – orientation axes (scaled /16); can be ignored initially or stored in `raw_payload`.
  - `battery_raw: int16` – convert to percent via `round(raw / 256)`.
- If `metrics.version > 2`, parsing still works but a warning is emitted.

Gravity velocity (rate of change) appears only in the V2 struct and is **not** yet parsed by `rapt-ble`. BrewSignal can ignore gravity velocity initially, and add support later if needed by extending the parser.

### 2.3 Version Payload Layout

Version information is carried in `manufacturer_data[17739]`. The parser treats this as an ASCII string:

```python
if 17739 in manufacturer_data:
    if data := manufacturer_data[17739]:
        # Example: b"GKEG20220612_050156_81c6d1..."
        if data[0] != 71:  # 'G'
            # Not a version payload
            return
        version_str = data[1:].decode("ascii")
        self.set_device_sw_version(version_str)
```

This is **optional metadata** for BrewSignal:

- Use it to populate a `firmware_version` field on the `Device` model (if desired).
- Not required for ingest/storage of readings.

### 2.4 Ignoring Non-Metrics Payloads

The parser explicitly ignores a special manufacturer payload:

```python
if manufacturer_data[16722] == b"PTdPillG1":
    # Likely a hardware revision advertisement - can be ignored
    return
```

BrewSignal should follow the same rule: if `manufacturer_data[16722]` equals `b"PTdPillG1"`, treat it as non-metrics and skip.

---

## 3. Mapping RAPT BLE → HydrometerReading

We will normalize RAPT BLE metrics into the existing `HydrometerReading` model (`backend/ingest/base.py`).

### 3.1 Device Identity

Options for `HydrometerReading.device_id`:

1. **BLE MAC address** (recommended):
   - Use `device.address` from Bleak (e.g., `"78:E3:6D:29:19:16"`).
   - Stable across sessions and matches the fields used in the `TravisEvashkevich` decoder’s `data.json` template.
2. **Derived ID from MAC suffix**, e.g., `"rapt-pill-291916"`.

**Recommendation:**  
Store the **full BLE MAC** as `device_id` (e.g., `"78:E3:6D:29:19:16"`) and let the `Device.name` / UI handle friendly naming (e.g., `"RAPT Pill 291916"`).

### 3.2 Units and Ranges

From the BLE metrics:

- **Temperature**
  - Raw: `uint16 temperature_raw`.
  - Conversion: `temp_c = raw / 128 - 273.15`.
  - Interpretation: °C.
  - In `HydrometerReading`:
    - `temperature_raw = temp_c`
    - `temperature_unit = TemperatureUnit.CELSIUS`

- **Gravity**
  - Raw: `float32 gravity_raw`.
  - Conversion: `gravity_sg = raw / 1000`.
  - Interpretation: specific gravity (SG).
  - In `HydrometerReading`:
    - `gravity_raw = gravity_sg`
    - `gravity_unit = GravityUnit.SG`

- **Battery**
  - Raw: `int16 battery_raw`.
  - Conversion: `battery_percent = round(battery_raw / 256)` (0–100).
  - In `HydrometerReading`:
    - Call `normalize_battery(battery_percent, device_type="rapt", is_percent=True)` → `(battery_voltage, battery_percent)`.
    - Requires adding `"rapt": (3.0, 4.2)` (Li-ion) to `BATTERY_RANGES` in `backend/ingest/units.py`.

- **RSSI**
  - Provided by Bleak as `advertisement_data.rssi`.
  - In `HydrometerReading`:
    - `rssi = advertisement_data.rssi`.

- **Orientation (x, y, z)**
  - Derived: `x = raw_x / 16`, etc.
  - RAPT uses this to infer tilt angle, but BrewSignal currently only models a single `angle` field (for iSpindel).
  - For now:
    - Do **not** populate `HydrometerReading.angle`.
    - Store the full metrics record in `raw_payload` if needed for debugging.

### 3.3 Status and Completeness

RAPT Pill BLE provides both gravity and temperature directly:

- For a normal metrics packet:
  - `gravity_raw` is non-`None`.
  - `temperature_raw` is non-`None`.
  - Set `status = ReadingStatus.VALID`.

If for any reason one value is missing or out of range (rare for BLE), we can follow the same rules as other adapters:

- If `gravity_raw` is `None` but temperature is present → `ReadingStatus.INCOMPLETE`.
- If both gravity and temperature are missing/invalid → `ReadingStatus.INVALID`.

Calibration is handled later by `calibration_service` and may adjust `gravity` and `temperature` to normalized values (in SG and °F).

---

## 4. Backend Integration Design

### 4.1 New Adapter: RaptAdapter

Create a new adapter to normalize RAPT BLE metrics into `HydrometerReading`.

**File:** `backend/ingest/adapters/rapt.py`

**Responsibilities:**

- Accept a normalized payload from the BLE layer, e.g.:

  ```python
  {
      "device_id": "78:E3:6D:29:19:16",
      "device_type": "rapt",
      "temperature_c": 18.3,
      "gravity_sg": 1.045,
      "battery_percent": 87,
      "rssi": -65,
      "raw_metrics": {
          "version": 1,
          "mac": "78e36d291916",
          "x": 0.5,
          "y": -0.2,
          "z": 9.7,
      },
  }
  ```

- Implement `BaseAdapter`:

  ```python
  class RaptAdapter(BaseAdapter):
      device_type = "rapt"
      native_gravity_unit = GravityUnit.SG
      native_temp_unit = TemperatureUnit.CELSIUS

      def can_handle(self, payload: dict) -> bool:
          return payload.get("device_type") == "rapt"

      def parse(self, payload: dict, source_protocol: str) -> Optional[HydrometerReading]:
          # Map fields into HydrometerReading (see §3.2)
  ```

- Behavior:
  - Extract `device_id` from payload.
  - Map `temperature_c` → `temperature_raw`, `temperature_unit=CELSIUS`.
  - Map `gravity_sg` → `gravity_raw`, `gravity_unit=SG`.
  - Normalize battery via `normalize_battery(payload.get("battery_percent"), "rapt", is_percent=True)`.
  - Set `rssi`, `status`, `is_pre_filtered=False`, `source_protocol="ble"`, and copy `raw_metrics` into `raw_payload`.

### 4.2 Register Adapter in Router

**File:** `backend/ingest/router.py`

Extend `AdapterRouter.__init__` to include the new adapter. Order matters (more specific first):

```python
from .adapters import GravityMonAdapter, ISpindelAdapter, TiltAdapter, RaptAdapter

class AdapterRouter:
    def __init__(self):
        self.adapters = [
            GravityMonAdapter(),
            RaptAdapter(),       # RAPT before generic iSpindel-ish HTTP formats
            ISpindelAdapter(),
            TiltAdapter(),
        ]
```

This allows **BLE-originated RAPT payloads** (tagged `device_type="rapt"`) to go through the same ingest pipeline as HTTP devices.

### 4.3 Device Registry & Battery Range

**File:** `backend/ingest/units.py`

Extend `BATTERY_RANGES`:

```python
BATTERY_RANGES: dict[str, tuple[float, float]] = {
    "ispindel": (3.0, 4.2),
    "floaty": (3.0, 4.2),
    "gravitymon": (3.0, 4.2),
    "tilt": (2.0, 3.0),
    "rapt": (3.0, 4.2),   # Li-ion 18650
}
```

**File:** `backend/services/ingest_manager.py`

Update `_get_or_create_device` to handle `device_type == "rapt"`:

```python
elif reading.device_type == "rapt":
    kwargs["native_gravity_unit"] = str(reading.gravity_unit.value)
    kwargs["native_temp_unit"] = str(reading.temperature_unit.value)
```

This ensures RAPT devices are properly registered in the `Device` table with native units and can reuse the same calibration and UI logic as other hydrometers.

---

## 5. BLE Scanner Integration

### 5.1 Current BLE Flow (Tilt)

Current path (Tilt-only):

1. `backend/main.py`:
   - Creates `TiltScanner(on_reading=handle_tilt_reading)`.
   - `handle_tilt_reading`:
     - Upserts `Tilt` record.
     - Applies Tilt-specific calibration via `calibration_service`.
     - Stores `Reading` with `tilt_id` and `device_id`.
     - Broadcasts via WebSocket using a Tilt-centric payload.

2. `backend/scanner.py`:
   - `BLEScanner` uses `BleakScanner` and `beacontools.parse_packet` to decode iBeacon Tilt packets into `TiltReading`.
   - `TiltScanner` picks BLE/File/Relay/Mock modes and calls `on_reading(TiltReading)`.

This path does **not** currently go through `IngestManager` or the universal `HydrometerReading` model.

### 5.2 Options for RAPT BLE

There are two main options to integrate RAPT:

#### Option A – Dedicated RAPT BLE Service (recommended initial approach)

Pros:
- Avoids touching the existing Tilt BLE path.
- Cleanly routes RAPT data into the universal ingest pipeline.

Design:

- Create a new service, e.g. `backend/rapt_ble_service.py`, that:
  - Uses `BleakScanner` directly to scan for RAPT manufacturer data (mirroring `rapt-ble`).
  - On each RAPT metrics packet:
    - Parse `manufacturer_data[16722]` into a metrics dict (using the same logic as `rapt-ble`).
    - Build a normalized payload for `RaptAdapter` (see §4.1).
    - Call:
      ```python
      await ingest_manager.ingest(
          db=session,
          payload=payload,
          source_protocol="ble",
          auth_token=None,
      )
      ```

- Start/stop this service in `backend/main.py` along with the Tilt scanner:
  - On startup: `rapt_ble_service.start()`.
  - On shutdown: `rapt_ble_service.stop()`.

This treats RAPT as a “generic” hydrometer from day one and leverages all the ingest, calibration, and device registry machinery.

#### Option B – Extend Existing BLEScanner

Pros:
- Single BLE scanner entrypoint.
- Reuses the same `BleakScanner` object for both Tilt and RAPT.

Design changes:

- In `backend/scanner.py`, modify `BLEScanner._detection_callback`:
  - First, check for Tilt (keep current behavior).
  - Also:
    - Inspect `advertisement_data.manufacturer_data` for keys `16722` and/or `17739`.
    - If present, parse RAPT metrics (`_process_metrics` logic from §2.2).
    - Instead of creating a `TiltReading`, create a RAPT payload dict and enqueue it for ingest via a callback.

Challenge:

- `TiltScanner` currently expects an `on_reading(TiltReading)` callback, not a generic hydrometer payload.
- To avoid tight coupling:
  - Introduce a secondary callback, e.g. `on_rapt_payload: Callable[[dict], Awaitable[None]]`, or
  - Refactor the scanner so that it reports generic “BLE readings” and let `main.py` decide how to route them.

Given the refactor cost and risk to existing Tilt behavior, **Option A** (separate RAPT BLE service) is a safer first step.

---

## 6. End-to-End Flow Summary

With the above pieces in place, the RAPT BLE path will look like this:

1. **BLE Advertisements**
   - RAPT Pill broadcasts metrics in `manufacturer_data[16722]` (and optionally version in `[17739]`).

2. **RAPT BLE Service**
   - `BleakScanner` callback receives `device`, `advertisement_data`.
   - Detects `16722` in `manufacturer_data`.
   - Parses metrics into:
     - `temperature_c`, `gravity_sg`, `battery_percent`, `rssi`, `raw_metrics`.
   - Builds BLE payload:
     ```python
     payload = {
         "device_id": device.address,
         "device_type": "rapt",
         "temperature_c": temp_c,
         "gravity_sg": gravity_sg,
         "battery_percent": battery_percent,
         "rssi": advertisement_data.rssi,
         "raw_metrics": metrics_dict,
     }
     ```

3. **Adapter Router & RaptAdapter**
   - `AdapterRouter.route(payload, source_protocol="ble")` selects `RaptAdapter`.
   - `RaptAdapter.parse()` returns a `HydrometerReading` with:
     - `device_type="rapt"`, `gravity_raw`, `temperature_raw`, `battery_voltage`, `battery_percent`, `rssi`, `raw_payload`, `status=VALID`, `source_protocol="ble"`.

4. **IngestManager Pipeline**
   - `_get_or_create_device` creates/updates a `Device` row for this RAPT Pill.
   - `convert_units` ensures normalized SG and °F (if needed).
   - RSSI filtering applies (optional).
   - `calibrate_device_reading` applies any per-device calibration.
   - `_store_reading` writes a `Reading` row.
   - `_broadcast_reading` builds a WebSocket payload (legacy-compatible) and updates `latest_readings`.

5. **Frontend**
   - Sees RAPT entries in the same WebSocket stream as Tilt/iSpindel/GravityMon:
     - `device_type="rapt"` distinguishes them.
     - All charts and batch linking work unchanged because they operate on the normalized `Reading` records and WebSocket payloads.

---

## 7. Implementation Checklist

1. **BLE Parsing**
   - [ ] Implement RAPT metrics parser (can be copied/ported from `rapt-ble`).
   - [ ] Write unit tests for parsing given raw `manufacturer_data[16722]` bytes.

2. **Adapter**
   - [ ] Add `backend/ingest/adapters/rapt.py` with `RaptAdapter`.
   - [ ] Register `RaptAdapter` in `AdapterRouter`.

3. **Unit Conversion & Device**
   - [ ] Add `"rapt": (3.0, 4.2)` to `BATTERY_RANGES` in `backend/ingest/units.py`.
   - [ ] Extend `_get_or_create_device` in `IngestManager` for `device_type=="rapt"`.

4. **BLE Service**
   - [ ] Implement a RAPT BLE service using `bleak` (Option A) or extend `BLEScanner` (Option B).
   - [ ] Wire service into FastAPI lifespan in `backend/main.py`.

5. **Validation**
   - [ ] Run on a Raspberry Pi with a real RAPT Pill in wort/water.
   - [ ] Confirm:
     - Devices appear with `device_type="rapt"` in `/api/devices`.
     - Readings show up in the dashboard and `/api/ingest/generic` continues to work for other device types.
     - Battery and RSSI values are reasonable.

Once this is implemented, BrewSignal will be able to monitor RAPT Pill devices **entirely locally**, without any dependency on the RAPT cloud.

