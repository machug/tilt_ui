# Tilt UI ML Enhancements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add AI/ML capabilities to Tilt UI for noise reduction (Kalman filter), anomaly detection, fermentation predictions, smart heater control (MPC with overshoot prevention), and optional small language model assistant.

**Architecture:** Local-first classical ML using filterpy, scipy, and scikit-learn running entirely on Raspberry Pi. Optional SLM (Mistral Ministral 3B via llama-cpp-python) for natural language queries. All ML processing happens in a new `backend/ml/` module that integrates with the existing reading pipeline in `backend/main.py:handle_tilt_reading()`.

**Tech Stack:** Python 3.11+, filterpy (Kalman), scipy (curve fitting, MPC optimization), scikit-learn (anomaly detection), pytest-asyncio (testing), llama-cpp-python (optional SLM)

**Note on Overshoot Prevention:** Task 6 (MPC Temperature Controller) includes thermal inertia modeling inspired by BrewPi's overshoot prevention techniques. This solves Issue #60 where cooling overshoots target temperature and triggers unnecessary heating. The MPC predicts post-shutdown temperature drift using self-learning coefficients that adapt to your specific chamber characteristics.

**Dual-Mode Extension (Issue #64):** The MPC now supports active cooling in addition to heating. The thermal model learns separate heating_rate and cooling_rate parameters from historical data, with shared ambient_coeff for natural heat exchange. Control decisions evaluate three actions: heater ON, cooler ON, or both OFF. Mutual exclusion is enforced in both learning and predictions. See `docs/plans/2025-12-05-mpc-dual-mode.md` for full design details.

**Temperature Units:** All MPC calculations now use Celsius (°C) to align with project standards (CLAUDE.md). Previously used Fahrenheit.

---

## Research: Other Wireless/BLE Hydrometers (beyond Tilt)

Goal: design ingestion + ML that can handle multiple hydrometers so we are not Tilt-only. Snapshot of notable devices/software and integration work needed.

- **iSpindel (ESP8266 WiFi)**
  - Hardware: Wemos D1 Mini + MPU-6050 IMU (tilt angle), DS18B20 temperature, 18650 battery, deep sleep between samples. Open PCB (Jeffrey 2.x) fits PET preforms; needs 20–30° angle in water; calibration via polynomial (angle→SG); firmware flashing via USB.
  - Protocols: HTTP/HTTPS POST, MQTT, TCP/UDP; JSON payload with `ID`, `token`, `angle`, `temperature`, `battery`, `gravity` (post-calibration), `interval`, `rssi`, `timestamp`. Config via captive portal. Sampling interval usually 30–900s (affects battery life).
  - Data model: raw tilt angle + polynomial calibration to SG; DS18B20 temperature; Li-ion battery voltage; WiFi RSSI. Battery lasts weeks at 15–30 min interval.
  - Integration ideas: expose `/api/ingest/ispindel` accepting native JSON; auto-detect per-device calibration fields and store calibration poly; surface battery + RSSI in UI + anomaly heuristics (e.g., spike when WiFi weak). Add MQTT topic handler (`ispindel/<device_id>`). Map to unified ML reading: `sg`, `temp`, `rssi`, `battery`, `source=device_id`.
  - Edge cases: sleep/wake clock drift; need clock sync; some firmwares omit `timestamp` so server should time-stamp on receipt. Allow per-device gravity offset.

- **Floaty Hydrometer (ESP32 WiFi, open hardware)**
  - Hardware/software: WiFi hydrometer/thermometer with rechargeable micro-USB, gravity+temp sensors, ESP32 deep sleep. Official Android app receives data over WiFi and shows real-time graphs; promises 14k data points per charge (2 months–1 year depending on interval). DIY version exists.
  - Protocols: HTTP/HTTPS POST (Brewfather-style), MQTT publish (JSON), optional InfluxDB line protocol. Payload includes `device`, `gravity`, `temp`, `battery`, `angle`, `interval`, `rssi`. Sample interval configurable (deep sleep capable).
  - Data model: similar to iSpindel but ESP32; claims better WiFi stability, onboard IMU; calibration polynomial stored on device. Battery via 18650/LiPo.
  - Integration ideas: reuse iSpindel ingest with alias; accept Brewfather-format query/body; implement MQTT subscription to `floaty/<device>` or Brewfather topics. Add OTA-friendly device registry to store calibration + firmware version. ML: treat like iSpindel; add device-type tag for feature flags if needed.
  - Edge cases: some firmwares send gravity in °P not SG; need unit detection; RSSI may be missing on older builds.

- **GravityMon (software stack + gateway)**
  - What it is: open-source replacement firmware for iSpindel hardware (ESP8266 or ESP32-C3/S2/S3 mini) plus optional gateway; docs v2.3.0-beta (2025-11-08).
  - Protocols/outputs: HTTP POST (iSpindel format), HTTP GET, MQTT, InfluxDB v2; can push to Brewfather, Fermentrack, Grainfather, Ubidots, Home Assistant, Brewer’s Friend, Brewspy, Thingspeak, BrewBlox, etc. Gateway can forward BLE/WiFi hydrometers to MQTT/HTTP targets.
  - Gateway role: Raspberry Pi/ESP listener for BLE (Tilt), WiFi (iSpindel, RAPT Pill), publishing via MQTT/HTTP; can run on ESP32 with screen. Good path to quickly support RAPT/DIYs indirectly.
  - Integration ideas: add `/api/ingest/gravitymon` endpoint + MQTT subscription; treat GravityMon as multi-device forwarder with `source_device` preserved; allow `raw` vs `filtered` flag and idempotent handling (gateway may replay last state on reconnect).
  - Edge cases: if GravityMon already filters, tag payload with processing stage; MQTT topics often `gravitymon/<device>/state` containing `sg`, `temp`, `rssi`, `battery`, `source`, `timestamp`.

- **Cross-cutting ingest plan**
  - Build `backend/ml/ingest` service with adapters: `tilt_ble`, `ispindel_http`, `brewfather_http` (Floaty/GravityMon), `mqtt_ingest`. Normalize to `{device_id, device_type, sg, temp_f, rssi, battery, angle?, ts}` before ML pipeline.
  - Add device registry table/file: `device_id`, `type` (tilt/ispindel/floaty/gravitymon/rapt), `calibration_poly` (for angle->SG), `units` (SG/Plato), `firmware`, `last_seen`, `signal_stats`.
  - Calibration: support uploading iSpindel/Floaty polynomial (3–5 coefficients) and apply serverside; also allow auto-fit using our ML curve fitter from a calibration run.
  - Testing: create fixture payloads for each device and golden normalized output; simulate weak-signal + long-interval behavior; ensure ML pipeline still works with sparse 15–30 min data.
  - UI/UX: show device-type badge, battery tile, RSSI/WiFi strength, sample interval; alert on stale data (>2x interval) or low battery; per-device calibration management.
  - Security: HTTP ingest should require token per device; MQTT uses user/pass and topic ACL; reject unknown device ids by default; rate-limit ingest.

---

## Task 1: Set Up Test Infrastructure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `pytest.ini`

**Step 1: Create pytest configuration**

Create `pytest.ini`:
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_functions = test_*
addopts = -v --tb=short
```

**Step 2: Create test fixtures**

Create `tests/__init__.py`:
```python
# Test package
```

Create `tests/conftest.py`:
```python
"""Shared test fixtures for Tilt UI tests."""

import pytest
from datetime import datetime, timezone


@pytest.fixture
def sample_readings():
    """Generate sample Tilt readings with realistic noise."""
    return [
        {"sg": 1.050, "temp": 68.0, "rssi": -60, "dt_hours": 0.0},
        {"sg": 1.049, "temp": 68.2, "rssi": -55, "dt_hours": 1.0},
        {"sg": 1.048, "temp": 68.1, "rssi": -70, "dt_hours": 2.0},
        {"sg": 1.055, "temp": 67.8, "rssi": -85, "dt_hours": 3.0},  # Anomaly - SG jump
        {"sg": 1.046, "temp": 68.0, "rssi": -58, "dt_hours": 4.0},
        {"sg": 1.045, "temp": 68.3, "rssi": -62, "dt_hours": 5.0},
    ]


@pytest.fixture
def fermentation_data():
    """Generate realistic 7-day fermentation curve data."""
    import numpy as np

    # Exponential decay: SG(t) = FG + (OG - FG) * exp(-k * t)
    og = 1.055
    fg = 1.012
    k = 0.02  # decay rate

    hours = np.arange(0, 168, 4)  # Every 4 hours for 7 days
    sg_clean = fg + (og - fg) * np.exp(-k * hours)

    # Add realistic noise
    np.random.seed(42)
    noise = np.random.normal(0, 0.001, len(hours))
    sg_noisy = sg_clean + noise

    return {
        "hours": hours.tolist(),
        "sg": sg_noisy.tolist(),
        "og": og,
        "fg": fg,
        "k": k,
    }
```

**Step 3: Verify pytest runs**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest --collect-only`

Expected: "no tests ran" (we haven't written any yet)

**Step 4: Commit**

```bash
git add pytest.ini tests/
git commit -m "test: add pytest infrastructure for ML tests"
```

---

## Task 2: Create ML Module Structure

**Files:**
- Create: `backend/ml/__init__.py`
- Create: `backend/ml/config.py`

**Step 1: Write the failing test**

Create `tests/test_ml_config.py`:
```python
"""Tests for ML configuration."""

import pytest
from backend.ml.config import MLConfig


def test_default_config():
    """ML config has sensible defaults."""
    config = MLConfig()

    assert config.enable_kalman_filter is True
    assert config.enable_anomaly_detection is True
    assert config.enable_predictions is True
    assert config.enable_mpc is False  # Opt-in, requires HA setup
    assert config.enable_slm is False  # Opt-in, requires model download


def test_config_from_env(monkeypatch):
    """ML config can be overridden via environment."""
    monkeypatch.setenv("TILT_ML_ENABLE_KALMAN_FILTER", "false")
    monkeypatch.setenv("TILT_ML_ENABLE_SLM", "true")

    config = MLConfig()

    assert config.enable_kalman_filter is False
    assert config.enable_slm is True
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest tests/test_ml_config.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'backend.ml'"

**Step 3: Write minimal implementation**

Create `backend/ml/__init__.py`:
```python
"""ML module for Tilt UI fermentation analytics."""

from .config import MLConfig

__all__ = ["MLConfig"]
```

Create `backend/ml/config.py`:
```python
"""Configuration for ML features."""

from pydantic_settings import BaseSettings


class MLConfig(BaseSettings):
    """ML feature configuration with environment variable overrides."""

    # Feature flags
    enable_kalman_filter: bool = True
    enable_anomaly_detection: bool = True
    enable_predictions: bool = True
    enable_mpc: bool = False  # Requires Home Assistant heater setup
    enable_slm: bool = False  # Requires model download (~1GB)

    # Kalman filter parameters
    kalman_process_noise_sg: float = 1e-8
    kalman_process_noise_temp: float = 0.01
    kalman_measurement_noise_sg: float = 1e-6
    kalman_measurement_noise_temp: float = 0.1

    # Anomaly detection
    anomaly_contamination: float = 0.05
    anomaly_min_history: int = 20
    anomaly_sg_rate_threshold: float = 0.001  # SG/hour

    # Predictions
    prediction_min_readings: int = 10
    prediction_completion_threshold: float = 0.002  # SG/day

    # MPC parameters
    mpc_horizon_hours: float = 4.0
    mpc_max_temp_rate: float = 1.0  # Max F/hour change
    mpc_dt_hours: float = 0.25  # 15-minute steps

    # SLM parameters
    slm_model_path: str = "~/.cache/llm/ministral-3b-instruct-q4_k_m.gguf"  # Mistral Ministral 3B
    slm_max_tokens: int = 256
    slm_context_size: int = 2048

    class Config:
        env_prefix = "TILT_ML_"
```

**Step 4: Run test to verify it passes**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest tests/test_ml_config.py -v`

Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/ml/ tests/test_ml_config.py
git commit -m "feat(ml): add ML module with configuration"
```

---

## Task 3: Implement Kalman Filter

**Files:**
- Create: `backend/ml/sensor_fusion/__init__.py`
- Create: `backend/ml/sensor_fusion/kalman.py`
- Create: `tests/test_kalman.py`

**Step 1: Write the failing test**

Create `tests/test_kalman.py`:
```python
"""Tests for Kalman filter sensor fusion."""

import pytest
from backend.ml.sensor_fusion.kalman import TiltKalmanFilter


class TestTiltKalmanFilter:
    """Tests for the Tilt Kalman filter."""

    def test_initialization(self):
        """Filter initializes with provided values."""
        kf = TiltKalmanFilter(initial_sg=1.050, initial_temp=68.0)

        assert kf.get_state()["sg_filtered"] == pytest.approx(1.050, abs=0.001)
        assert kf.get_state()["temp_filtered"] == pytest.approx(68.0, abs=0.1)

    def test_filters_noisy_readings(self, sample_readings):
        """Filter smooths out noisy readings."""
        kf = TiltKalmanFilter(initial_sg=1.050, initial_temp=68.0)

        results = []
        for reading in sample_readings:
            result = kf.update(
                sg=reading["sg"],
                temp=reading["temp"],
                rssi=reading["rssi"],
                dt_hours=reading["dt_hours"] if reading["dt_hours"] > 0 else 1/60,
            )
            results.append(result)

        # The anomalous reading (1.055) should be dampened
        sg_values = [r["sg_filtered"] for r in results]

        # Filtered values should be smoother (smaller std dev)
        raw_sg = [r["sg"] for r in sample_readings]
        import numpy as np
        assert np.std(sg_values) < np.std(raw_sg)

    def test_rssi_affects_confidence(self):
        """Weak RSSI increases measurement uncertainty."""
        kf = TiltKalmanFilter(initial_sg=1.050, initial_temp=68.0)

        # Strong signal reading
        result_strong = kf.update(sg=1.049, temp=68.0, rssi=-50, dt_hours=1.0)
        kf_strong_confidence = result_strong["confidence"]

        # Reset and test weak signal
        kf2 = TiltKalmanFilter(initial_sg=1.050, initial_temp=68.0)
        result_weak = kf2.update(sg=1.049, temp=68.0, rssi=-90, dt_hours=1.0)
        kf_weak_confidence = result_weak["confidence"]

        # Strong signal should give higher confidence
        assert kf_strong_confidence > kf_weak_confidence

    def test_returns_sg_rate(self, sample_readings):
        """Filter estimates rate of SG change."""
        kf = TiltKalmanFilter(initial_sg=1.050, initial_temp=68.0)

        for reading in sample_readings:
            result = kf.update(
                sg=reading["sg"],
                temp=reading["temp"],
                rssi=reading["rssi"],
                dt_hours=max(reading["dt_hours"], 1/60),
            )

        # After several readings showing decline, rate should be negative
        assert result["sg_rate"] < 0

    def test_reset(self):
        """Reset reinitializes the filter state."""
        kf = TiltKalmanFilter(initial_sg=1.050, initial_temp=68.0)

        # Process some readings
        kf.update(sg=1.040, temp=70.0, rssi=-60, dt_hours=1.0)
        kf.update(sg=1.035, temp=71.0, rssi=-60, dt_hours=1.0)

        # Reset to new batch
        kf.reset(sg=1.060, temp=65.0)

        state = kf.get_state()
        assert state["sg_filtered"] == pytest.approx(1.060, abs=0.001)
        assert state["temp_filtered"] == pytest.approx(65.0, abs=0.1)
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest tests/test_kalman.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'backend.ml.sensor_fusion'"

**Step 3: Install filterpy dependency**

Run: `cd /home/ladmin/Projects/tilt_ui && pip install filterpy`

**Step 4: Write implementation**

Create `backend/ml/sensor_fusion/__init__.py`:
```python
"""Sensor fusion module for noise reduction."""

from .kalman import TiltKalmanFilter

__all__ = ["TiltKalmanFilter"]
```

Create `backend/ml/sensor_fusion/kalman.py`:
```python
"""Kalman filter for Tilt hydrometer readings.

Uses an adaptive Kalman filter that adjusts measurement noise based on
Bluetooth signal strength (RSSI). Weak signals increase uncertainty,
strong signals trust the measurement more.
"""

import numpy as np
from filterpy.kalman import KalmanFilter


class TiltKalmanFilter:
    """Adaptive Kalman filter for Tilt hydrometer sensor fusion.

    State vector: [sg, sg_rate, temp, temp_rate]
    - sg: Specific gravity
    - sg_rate: Rate of SG change (points per hour)
    - temp: Temperature (Fahrenheit)
    - temp_rate: Rate of temperature change (F per hour)

    The filter uses RSSI to dynamically adjust measurement noise.
    Weak Bluetooth signals result in higher measurement uncertainty.
    """

    def __init__(
        self,
        initial_sg: float = 1.050,
        initial_temp: float = 68.0,
        process_noise_sg: float = 1e-8,
        process_noise_temp: float = 0.01,
        measurement_noise_sg: float = 1e-6,
        measurement_noise_temp: float = 0.1,
    ):
        """Initialize the Kalman filter.

        Args:
            initial_sg: Starting specific gravity estimate
            initial_temp: Starting temperature estimate (Fahrenheit)
            process_noise_sg: Process noise for SG (how much natural variation)
            process_noise_temp: Process noise for temperature
            measurement_noise_sg: Base measurement noise for SG
            measurement_noise_temp: Base measurement noise for temperature
        """
        # State vector: [sg, sg_rate, temp, temp_rate]
        self.kf = KalmanFilter(dim_x=4, dim_z=2)

        # State transition matrix (constant velocity model)
        # sg = sg + sg_rate * dt
        # sg_rate = sg_rate (constant)
        # temp = temp + temp_rate * dt
        # temp_rate = temp_rate (constant)
        self.kf.F = np.array([
            [1, 1, 0, 0],
            [0, 1, 0, 0],
            [0, 0, 1, 1],
            [0, 0, 0, 1],
        ], dtype=float)

        # Measurement matrix (we observe sg and temp directly)
        self.kf.H = np.array([
            [1, 0, 0, 0],
            [0, 0, 1, 0],
        ], dtype=float)

        # Initial state
        self.kf.x = np.array([initial_sg, 0.0, initial_temp, 0.0], dtype=float)

        # Process noise covariance
        self.kf.Q = np.diag([
            process_noise_sg,      # sg variance
            process_noise_sg / 10, # sg_rate variance
            process_noise_temp,    # temp variance
            process_noise_temp / 10,  # temp_rate variance
        ])

        # Base measurement noise covariance (adjusted by RSSI)
        self.base_R = np.diag([measurement_noise_sg, measurement_noise_temp])
        self.kf.R = self.base_R.copy()

        # Initial state covariance (uncertainty)
        self.kf.P = np.diag([1e-4, 1e-6, 1.0, 0.01])

    def _rssi_to_noise_factor(self, rssi: float) -> float:
        """Convert RSSI to measurement noise multiplier.

        Strong signal (-40 dBm) = 1x noise (trust measurement)
        Weak signal (-90 dBm) = 10x noise (distrust measurement)

        Args:
            rssi: Bluetooth signal strength in dBm

        Returns:
            Noise multiplier (1.0 to 10.0)
        """
        # Normalize RSSI: -40 dBm -> 0, -90 dBm -> 1
        rssi_normalized = np.clip((rssi + 40) / -50, 0, 1)
        return 1.0 + 9.0 * rssi_normalized

    def update(
        self,
        sg: float,
        temp: float,
        rssi: float,
        dt_hours: float = 1 / 60,
    ) -> dict:
        """Process a new reading and return filtered values.

        Args:
            sg: Raw specific gravity reading
            temp: Raw temperature reading (Fahrenheit)
            rssi: Bluetooth signal strength (dBm)
            dt_hours: Time since last reading in hours (default: 1 minute)

        Returns:
            Dictionary with filtered values and metadata:
            - sg_filtered: Kalman-filtered specific gravity
            - sg_rate: Estimated SG change rate (points per hour)
            - temp_filtered: Kalman-filtered temperature
            - temp_rate: Estimated temperature change rate (F per hour)
            - confidence: Confidence score (0-1)
            - rssi_factor: Applied noise multiplier
        """
        # Adjust state transition matrix for actual time delta
        self.kf.F[0, 1] = dt_hours  # sg += sg_rate * dt
        self.kf.F[2, 3] = dt_hours  # temp += temp_rate * dt

        # Adjust measurement noise based on signal quality
        rssi_factor = self._rssi_to_noise_factor(rssi)
        self.kf.R = self.base_R * rssi_factor

        # Predict next state
        self.kf.predict()

        # Update with measurement
        measurement = np.array([sg, temp])
        self.kf.update(measurement)

        return {
            "sg_filtered": float(self.kf.x[0]),
            "sg_rate": float(self.kf.x[1]),
            "temp_filtered": float(self.kf.x[2]),
            "temp_rate": float(self.kf.x[3]),
            "confidence": self._calculate_confidence(),
            "rssi_factor": rssi_factor,
        }

    def _calculate_confidence(self) -> float:
        """Calculate confidence score from state covariance.

        Returns:
            Confidence score between 0 and 1
        """
        # Use SG variance as primary confidence indicator
        sg_variance = self.kf.P[0, 0]
        # Map variance to confidence: low variance = high confidence
        confidence = 1.0 - np.sqrt(sg_variance) * 1000
        return float(np.clip(confidence, 0, 1))

    def get_state(self) -> dict:
        """Get current filter state without processing a reading.

        Returns:
            Dictionary with current state estimates
        """
        return {
            "sg_filtered": float(self.kf.x[0]),
            "sg_rate": float(self.kf.x[1]),
            "temp_filtered": float(self.kf.x[2]),
            "temp_rate": float(self.kf.x[3]),
            "confidence": self._calculate_confidence(),
        }

    def reset(self, sg: float, temp: float) -> None:
        """Reset filter state for a new batch.

        Args:
            sg: New initial specific gravity
            temp: New initial temperature
        """
        self.kf.x = np.array([sg, 0.0, temp, 0.0], dtype=float)
        self.kf.P = np.diag([1e-4, 1e-6, 1.0, 0.01])
```

**Step 5: Run test to verify it passes**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest tests/test_kalman.py -v`

Expected: PASS (5 tests)

**Step 6: Commit**

```bash
git add backend/ml/sensor_fusion/ tests/test_kalman.py
git commit -m "feat(ml): implement Kalman filter for sensor fusion"
```

---

## Task 4: Implement Anomaly Detection

**Files:**
- Create: `backend/ml/anomaly/__init__.py`
- Create: `backend/ml/anomaly/detector.py`
- Create: `tests/test_anomaly.py`

**Step 1: Write the failing test**

Create `tests/test_anomaly.py`:
```python
"""Tests for anomaly detection."""

import pytest
from backend.ml.anomaly.detector import FermentationAnomalyDetector


class TestAnomalyDetector:
    """Tests for fermentation anomaly detection."""

    def test_detects_gravity_increase(self):
        """Flags readings where gravity increases during fermentation."""
        detector = FermentationAnomalyDetector()

        result = detector.check_reading(
            sg=1.050,
            temp=68.0,
            rssi=-60,
            sg_rate=0.002,  # Positive rate = gravity increasing
        )

        assert result["is_anomaly"] is True
        assert "gravity_increasing" in result["reasons"]

    def test_allows_small_gravity_increase(self):
        """Small increases (CO2 degassing) are OK."""
        detector = FermentationAnomalyDetector()

        result = detector.check_reading(
            sg=1.050,
            temp=68.0,
            rssi=-60,
            sg_rate=0.0005,  # Small positive rate
        )

        assert result["is_anomaly"] is False

    def test_detects_weak_signal(self):
        """Flags readings with very weak Bluetooth signal."""
        detector = FermentationAnomalyDetector()

        result = detector.check_reading(
            sg=1.050,
            temp=68.0,
            rssi=-88,  # Very weak signal
            sg_rate=-0.001,
        )

        assert result["is_anomaly"] is True
        assert "weak_signal" in result["reasons"]

    def test_statistical_outlier_detection(self):
        """Detects statistical outliers after training."""
        detector = FermentationAnomalyDetector(window_size=30)

        # Build history with normal readings
        for i in range(25):
            sg = 1.050 - (i * 0.001)  # Gradual decline
            detector.check_reading(sg=sg, temp=68.0, rssi=-60, sg_rate=-0.001)

        # Now submit an outlier
        result = detector.check_reading(
            sg=1.080,  # Way too high
            temp=68.0,
            rssi=-60,
            sg_rate=-0.001,
        )

        assert result["is_anomaly"] is True
        assert "statistical_outlier" in result["reasons"]

    def test_should_use_flag(self):
        """Provides guidance on whether to use the reading."""
        detector = FermentationAnomalyDetector()

        # Gravity anomaly - don't use
        result1 = detector.check_reading(sg=1.050, temp=68.0, rssi=-60, sg_rate=0.01)
        assert result1["should_use"] is False

        # Weak signal only - might still use (Kalman will handle it)
        result2 = detector.check_reading(sg=1.050, temp=68.0, rssi=-88, sg_rate=-0.001)
        assert result2["should_use"] is True  # Weak signal readings can be used with caution
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest tests/test_anomaly.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'backend.ml.anomaly'"

**Step 3: Write implementation**

Create `backend/ml/anomaly/__init__.py`:
```python
"""Anomaly detection for fermentation readings."""

from .detector import FermentationAnomalyDetector

__all__ = ["FermentationAnomalyDetector"]
```

Create `backend/ml/anomaly/detector.py`:
```python
"""Anomaly detection for fermentation readings.

Detects readings that violate fermentation physics or are statistical outliers.
"""

from collections import deque
from typing import Optional

import numpy as np
from sklearn.ensemble import IsolationForest


class FermentationAnomalyDetector:
    """Detects anomalous readings during fermentation.

    Uses both rule-based checks (physics violations) and statistical
    anomaly detection (Isolation Forest) to identify problematic readings.

    Rule-based checks:
    - Gravity significantly increasing during active fermentation
    - Very weak Bluetooth signal (unreliable reading)

    Statistical checks:
    - Isolation Forest trained on recent history
    """

    def __init__(
        self,
        window_size: int = 50,
        sg_rate_threshold: float = 0.001,
        rssi_threshold: float = -85,
        contamination: float = 0.05,
    ):
        """Initialize the anomaly detector.

        Args:
            window_size: Number of readings to keep in history
            sg_rate_threshold: Max allowed positive SG rate (SG/hour)
            rssi_threshold: Minimum acceptable RSSI (dBm)
            contamination: Expected fraction of outliers for Isolation Forest
        """
        self.window_size = window_size
        self.sg_rate_threshold = sg_rate_threshold
        self.rssi_threshold = rssi_threshold

        self.history: deque = deque(maxlen=window_size)
        self.isolation_forest = IsolationForest(
            contamination=contamination,
            random_state=42,
            n_estimators=50,
        )
        self.is_fitted = False

    def check_reading(
        self,
        sg: float,
        temp: float,
        rssi: float,
        sg_rate: float,
    ) -> dict:
        """Check if a reading is anomalous.

        Args:
            sg: Specific gravity reading
            temp: Temperature reading (Fahrenheit)
            rssi: Bluetooth signal strength (dBm)
            sg_rate: Rate of SG change from Kalman filter (SG/hour)

        Returns:
            Dictionary with:
            - is_anomaly: Whether the reading is anomalous
            - reasons: List of reasons why it's anomalous
            - should_use: Whether to use this reading despite anomaly
        """
        reasons = []
        is_anomaly = False

        # Rule 1: Gravity can't significantly increase during fermentation
        # Small increases due to CO2 degassing or temperature changes are OK
        if sg_rate > self.sg_rate_threshold:
            reasons.append("gravity_increasing")
            is_anomaly = True

        # Rule 2: Very weak RSSI suggests unreliable reading
        if rssi < self.rssi_threshold:
            reasons.append("weak_signal")
            is_anomaly = True

        # Rule 3: Statistical anomaly via Isolation Forest
        if len(self.history) >= 20:
            if not self.is_fitted:
                self._fit()

            features = np.array([[sg, temp, rssi, sg_rate]])
            score = self.isolation_forest.decision_function(features)[0]
            if score < -0.3:  # Threshold for anomaly
                reasons.append("statistical_outlier")
                is_anomaly = True

        # Add to history for future fitting
        self.history.append([sg, temp, rssi, sg_rate])

        # Determine if reading should still be used
        # Weak signal readings can be used - Kalman filter handles uncertainty
        # But physics violations (gravity up) should be rejected
        should_use = not is_anomaly or reasons == ["weak_signal"]

        return {
            "is_anomaly": is_anomaly,
            "reasons": reasons,
            "should_use": should_use,
        }

    def _fit(self) -> None:
        """Fit Isolation Forest on accumulated history."""
        X = np.array(list(self.history))
        self.isolation_forest.fit(X)
        self.is_fitted = True

    def reset(self) -> None:
        """Reset detector state for a new batch."""
        self.history.clear()
        self.is_fitted = False
```

**Step 4: Run test to verify it passes**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest tests/test_anomaly.py -v`

Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add backend/ml/anomaly/ tests/test_anomaly.py
git commit -m "feat(ml): implement anomaly detection for fermentation readings"
```

---

## Task 5: Implement Fermentation Curve Fitting

**Files:**
- Create: `backend/ml/fermentation/__init__.py`
- Create: `backend/ml/fermentation/curve_fitter.py`
- Create: `tests/test_curve_fitter.py`

**Step 1: Write the failing test**

Create `tests/test_curve_fitter.py`:
```python
"""Tests for fermentation curve fitting and predictions."""

import pytest
import numpy as np
from backend.ml.fermentation.curve_fitter import FermentationCurveFitter


class TestFermentationCurveFitter:
    """Tests for fermentation curve fitting."""

    def test_fit_requires_minimum_data(self):
        """Fitting fails with insufficient data."""
        fitter = FermentationCurveFitter()

        times = np.array([0, 1, 2, 3, 4])
        gravities = np.array([1.050, 1.049, 1.048, 1.047, 1.046])

        success = fitter.fit(times, gravities)

        assert success is False  # Need at least 10 points

    def test_fit_exponential_decay(self, fermentation_data):
        """Fits exponential decay model to fermentation data."""
        fitter = FermentationCurveFitter()

        times = np.array(fermentation_data["hours"])
        gravities = np.array(fermentation_data["sg"])

        success = fitter.fit(times, gravities)

        assert success is True
        assert fitter.fit_quality > 0.9  # Good fit

    def test_predicts_final_gravity(self, fermentation_data):
        """Predicts final gravity from fitted curve."""
        fitter = FermentationCurveFitter()

        times = np.array(fermentation_data["hours"])
        gravities = np.array(fermentation_data["sg"])
        fitter.fit(times, gravities)

        prediction = fitter.predict_completion()

        assert prediction is not None
        assert prediction["predicted_fg"] == pytest.approx(fermentation_data["fg"], abs=0.003)

    def test_predicts_completion_time(self, fermentation_data):
        """Estimates hours to fermentation completion."""
        fitter = FermentationCurveFitter()

        # Use only first half of data
        times = np.array(fermentation_data["hours"][:21])  # First ~3.5 days
        gravities = np.array(fermentation_data["sg"][:21])
        fitter.fit(times, gravities)

        prediction = fitter.predict_completion()

        assert prediction is not None
        assert prediction["hours_to_complete"] > 0
        assert prediction["hours_to_complete"] < 500  # Reasonable bound

    def test_calculates_attenuation(self, fermentation_data):
        """Calculates apparent attenuation percentage."""
        fitter = FermentationCurveFitter()

        times = np.array(fermentation_data["hours"])
        gravities = np.array(fermentation_data["sg"])
        fitter.fit(times, gravities)

        prediction = fitter.predict_completion()

        # Expected attenuation: (OG - FG) / (OG - 1.0) * 100
        # (1.055 - 1.012) / (1.055 - 1.0) * 100 = 78.2%
        assert prediction["attenuation_percent"] == pytest.approx(78.2, abs=5)

    def test_detects_fermentation_phase(self, fermentation_data):
        """Identifies current fermentation phase."""
        fitter = FermentationCurveFitter()

        times = np.array(fermentation_data["hours"])
        gravities = np.array(fermentation_data["sg"])
        fitter.fit(times, gravities)

        # Early in fermentation (high SG, fast rate)
        phase_early = fitter.get_current_phase(current_sg=1.045, current_rate=-0.003)
        assert phase_early in ("lag", "exponential")

        # Late in fermentation (low SG, slow rate)
        phase_late = fitter.get_current_phase(current_sg=1.015, current_rate=-0.0005)
        assert phase_late in ("deceleration", "stationary")
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest tests/test_curve_fitter.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'backend.ml.fermentation'"

**Step 3: Write implementation**

Create `backend/ml/fermentation/__init__.py`:
```python
"""Fermentation analysis and prediction module."""

from .curve_fitter import FermentationCurveFitter

__all__ = ["FermentationCurveFitter"]
```

Create `backend/ml/fermentation/curve_fitter.py`:
```python
"""Fermentation curve fitting for predictions.

Fits fermentation data to an exponential decay model to predict
final gravity and completion time.
"""

from datetime import datetime, timedelta
from typing import Optional

import numpy as np
from scipy.optimize import curve_fit


class FermentationCurveFitter:
    """Fits fermentation data to predict completion.

    Uses exponential decay model:
        SG(t) = FG + (OG - FG) * exp(-k * t)

    Where:
        - OG: Original gravity
        - FG: Final gravity (asymptote)
        - k: Decay rate constant
        - t: Time in hours
    """

    def __init__(self):
        """Initialize the curve fitter."""
        self.params: Optional[tuple] = None
        self.fit_quality: float = 0.0

    @staticmethod
    def _exp_decay(t: np.ndarray, og: float, fg: float, k: float) -> np.ndarray:
        """Exponential decay model for fermentation.

        Args:
            t: Time in hours from start
            og: Original gravity
            fg: Final gravity (asymptote)
            k: Decay rate constant

        Returns:
            Predicted specific gravity at time t
        """
        return fg + (og - fg) * np.exp(-k * t)

    def fit(self, times_hours: np.ndarray, gravities: np.ndarray) -> bool:
        """Fit the exponential decay model to fermentation data.

        Args:
            times_hours: Array of elapsed times in hours
            gravities: Array of specific gravity readings

        Returns:
            True if fit succeeded, False otherwise
        """
        if len(times_hours) < 10:
            return False

        try:
            # Initial guesses based on data
            og_guess = float(np.max(gravities))
            fg_guess = float(np.min(gravities)) - 0.005  # Assume it'll drop more
            k_guess = 0.02  # Typical decay rate

            # Bounds to keep parameters physical
            bounds = (
                [og_guess - 0.01, 0.990, 0.001],  # Lower bounds
                [og_guess + 0.01, og_guess, 0.5],  # Upper bounds
            )

            self.params, _ = curve_fit(
                self._exp_decay,
                times_hours,
                gravities,
                p0=[og_guess, fg_guess, k_guess],
                bounds=bounds,
                maxfev=5000,
            )

            # Calculate R-squared for fit quality
            predicted = self._exp_decay(times_hours, *self.params)
            ss_res = np.sum((gravities - predicted) ** 2)
            ss_tot = np.sum((gravities - np.mean(gravities)) ** 2)
            self.fit_quality = float(1 - (ss_res / ss_tot)) if ss_tot > 0 else 0.0

            return True

        except Exception:
            return False

    def predict_completion(self, threshold: float = 0.002) -> Optional[dict]:
        """Predict when fermentation will complete.

        Args:
            threshold: SG change per day to consider "complete"

        Returns:
            Dictionary with predictions, or None if not fitted
        """
        if self.params is None:
            return None

        og, fg, k = self.params

        # Time when rate drops below threshold (SG/day)
        # d(SG)/dt = -k * (OG - FG) * exp(-k * t)
        # We want |d(SG)/dt| < threshold/24 (convert to per-hour)
        threshold_per_hour = threshold / 24
        rate_at_start = k * (og - fg)

        if rate_at_start <= threshold_per_hour:
            hours_to_complete = 0.0
        else:
            # Solve: k * (OG - FG) * exp(-k * t) = threshold_per_hour
            hours_to_complete = float(-np.log(threshold_per_hour / rate_at_start) / k)

        return {
            "predicted_fg": float(fg),
            "predicted_og": float(og),
            "hours_to_complete": hours_to_complete,
            "completion_date": datetime.now() + timedelta(hours=hours_to_complete),
            "attenuation_percent": float((og - fg) / (og - 1.0) * 100),
            "fit_quality": self.fit_quality,
            "decay_rate": float(k),
        }

    def get_current_phase(self, current_sg: float, current_rate: float) -> str:
        """Determine current fermentation phase.

        Args:
            current_sg: Current specific gravity
            current_rate: Current rate of change (SG/hour, negative during fermentation)

        Returns:
            Phase name: "lag", "exponential", "deceleration", or "stationary"
        """
        if self.params is None:
            return "unknown"

        og, fg, _ = self.params

        # Calculate progress through fermentation
        total_drop = og - fg
        if total_drop <= 0:
            return "unknown"

        current_drop = og - current_sg
        progress = current_drop / total_drop

        # Phase classification based on progress and rate
        if progress < 0.1:
            return "lag"
        elif progress < 0.5 and abs(current_rate) > 0.002:
            return "exponential"
        elif progress < 0.9:
            return "deceleration"
        else:
            return "stationary"
```

**Step 4: Run test to verify it passes**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest tests/test_curve_fitter.py -v`

Expected: PASS (6 tests)

**Step 5: Commit**

```bash
git add backend/ml/fermentation/ tests/test_curve_fitter.py
git commit -m "feat(ml): implement fermentation curve fitting and predictions"
```

---

## Task 6: Implement MPC Temperature Controller

**Files:**
- Create: `backend/ml/control/__init__.py`
- Create: `backend/ml/control/mpc.py`
- Create: `tests/test_mpc.py`

**Step 1: Write the failing test**

Create `tests/test_mpc.py`:
```python
"""Tests for Model Predictive Control temperature controller."""

import pytest
from backend.ml.control.mpc import MPCTemperatureController, ThermalModel


class TestMPCController:
    """Tests for MPC temperature control."""

    def test_heats_when_cold(self):
        """Controller turns on heater when below target."""
        controller = MPCTemperatureController(target_temp=68.0)

        result = controller.compute_optimal_duty(
            current_temp=65.0,  # 3F below target
            ambient_temp=60.0,
        )

        assert result["optimal_duty"] > 0.5  # Should heat significantly

    def test_no_heat_when_at_target(self):
        """Controller minimal heat when at target with warm ambient."""
        controller = MPCTemperatureController(target_temp=68.0)

        result = controller.compute_optimal_duty(
            current_temp=68.0,
            ambient_temp=70.0,  # Warm ambient, no heat needed
        )

        assert result["optimal_duty"] < 0.3

    def test_predicts_temperature_trajectory(self):
        """Controller returns predicted temperature trajectory."""
        controller = MPCTemperatureController(target_temp=68.0)

        result = controller.compute_optimal_duty(
            current_temp=64.0,
            ambient_temp=60.0,
        )

        assert "predicted_temps" in result
        assert len(result["predicted_temps"]) > 1
        # Temps should be moving toward target
        assert result["predicted_temps"][-1] > result["predicted_temps"][0]

    def test_time_to_target(self):
        """Controller estimates time to reach target temperature."""
        controller = MPCTemperatureController(target_temp=68.0)

        result = controller.compute_optimal_duty(
            current_temp=64.0,
            ambient_temp=60.0,
        )

        assert result["time_to_target"] is not None
        assert result["time_to_target"] > 0

    def test_respects_max_rate(self):
        """Controller limits temperature change rate."""
        model = ThermalModel(heater_power=100.0)  # Very powerful heater
        controller = MPCTemperatureController(
            target_temp=68.0,
            thermal_model=model,
            max_rate=1.0,  # Max 1F/hour
        )

        result = controller.compute_optimal_duty(
            current_temp=50.0,  # Way below target
            ambient_temp=60.0,
        )

        # Despite big gap, trajectory should respect rate limit
        temps = result["predicted_temps"]
        for i in range(1, len(temps)):
            rate = (temps[i] - temps[i - 1]) / 0.25  # dt is 0.25 hours
            assert rate <= 1.5  # Allow small overshoot

    def test_phase_adjustment(self):
        """Controller adjusts behavior during exponential phase."""
        controller = MPCTemperatureController(target_temp=68.0)

        # During exponential phase, yeast generates heat
        result_exp = controller.compute_optimal_duty(
            current_temp=66.0,
            ambient_temp=60.0,
            fermentation_phase="exponential",
        )

        # Normal phase
        result_normal = controller.compute_optimal_duty(
            current_temp=66.0,
            ambient_temp=60.0,
            fermentation_phase="lag",
        )

        # Should heat less during exponential (yeast generates heat)
        assert result_exp["optimal_duty"] <= result_normal["optimal_duty"]

    def test_predicts_cooling_overshoot(self):
        """Controller predicts temperature continues dropping after cooler off."""
        model = ThermalModel(cooling_overshoot_rate=0.5, overshoot_decay_time=0.5)
        controller = MPCTemperatureController(target_temp=68.0, thermal_model=model)

        # Simulate cooler turning off at target + hysteresis
        result = controller.compute_optimal_duty(
            current_temp=69.0,  # Just above target
            ambient_temp=70.0,
        )

        # Temperature should be predicted to drop below target due to overshoot
        temps = result["predicted_temps"]
        assert any(t < 68.0 for t in temps), "Should predict overshoot below target"

    def test_predicts_heating_overshoot(self):
        """Controller predicts temperature continues rising after heater off."""
        model = ThermalModel(heating_overshoot_rate=0.3, overshoot_decay_time=0.5)
        controller = MPCTemperatureController(target_temp=68.0, thermal_model=model)

        # Simulate heater turning off near target
        result = controller.compute_optimal_duty(
            current_temp=67.5,  # Just below target
            ambient_temp=60.0,
        )

        # Temperature should be predicted to rise above target due to overshoot
        temps = result["predicted_temps"]
        assert any(t > 68.0 for t in temps), "Should predict overshoot above target"

    def test_learning_adjusts_coefficients(self):
        """Controller learns from prediction errors."""
        model = ThermalModel(cooling_overshoot_rate=0.1)  # Start with wrong estimate
        controller = MPCTemperatureController(target_temp=68.0, thermal_model=model)

        # Simulate learning: predicted 69°F, actual 67°F (overshoot by 2°F)
        initial_rate = model.cooling_overshoot_rate

        controller.update_overshoot_estimates(
            predicted_temp=69.0,
            actual_temp=67.0,
            device_just_turned_off="cooler",
            time_since_turnoff=0.25,  # 15 minutes
        )

        # Rate should increase toward actual overshoot
        assert model.cooling_overshoot_rate > initial_rate

    def test_dual_mode_prevents_oscillation(self):
        """Controller prevents heater activation by predicting cooling overshoot."""
        model = ThermalModel(
            cooling_overshoot_rate=0.5,
            heating_overshoot_rate=0.3,
            overshoot_decay_time=0.5,
        )
        controller = MPCTemperatureController(target_temp=68.0, thermal_model=model)

        # Temperature dropping toward target after cooling
        result = controller.compute_optimal_duty(
            current_temp=68.5,  # 0.5°F above target
            ambient_temp=70.0,
        )

        # Heater duty should be minimal (trusting overshoot prediction)
        assert result["optimal_duty"] < 0.2, "Should not heat aggressively"

        # Predicted trajectory should not need correction
        temps = result["predicted_temps"]
        final_temp = temps[-1]
        assert abs(final_temp - 68.0) < 1.0, "Should stabilize near target"
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest tests/test_mpc.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'backend.ml.control'"

**Step 3: Write implementation**

Create `backend/ml/control/__init__.py`:
```python
"""Temperature control module with MPC."""

from .mpc import MPCTemperatureController, ThermalModel

__all__ = ["MPCTemperatureController", "ThermalModel"]
```

Create `backend/ml/control/mpc.py`:
```python
"""Model Predictive Control for fermentation temperature.

Replaces simple bang-bang hysteresis control with predictive optimization.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy.optimize import minimize


@dataclass
class ThermalModel:
    """Thermal model parameters for the fermentation chamber.

    Default values are conservative estimates. Can be tuned based on
    actual chamber behavior.

    Includes thermal inertia parameters for overshoot prevention (Issue #60).
    Inspired by BrewPi's self-learning overshoot estimators.
    """

    heater_power: float = 50.0  # Temperature rise rate when on (F/hour)
    ambient_loss_rate: float = 0.5  # Heat loss per degree difference (F/hour per F)

    # Thermal inertia parameters (learned automatically)
    cooling_overshoot_rate: float = 0.3  # °F/hour coast after cooler turns off
    heating_overshoot_rate: float = 0.2  # °F/hour coast after heater turns off
    overshoot_decay_time: float = 0.5   # Hours for drift to decay to zero

    # Learning parameters
    learning_rate: float = 0.2  # EMA alpha for coefficient updates


class MPCTemperatureController:
    """Model Predictive Controller for fermentation temperature.

    Optimizes heater duty cycle over a prediction horizon to:
    1. Minimize deviation from target temperature
    2. Avoid rapid temperature changes (thermal stress on yeast)
    3. Minimize energy usage
    """

    def __init__(
        self,
        target_temp: float,
        thermal_model: Optional[ThermalModel] = None,
        horizon_hours: float = 4.0,
        max_rate: float = 1.0,
    ):
        """Initialize the MPC controller.

        Args:
            target_temp: Target fermentation temperature (Fahrenheit)
            thermal_model: Thermal characteristics of the chamber
            horizon_hours: Prediction horizon for optimization
            max_rate: Maximum allowed temperature change (F/hour)
        """
        self.target_temp = target_temp
        self.model = thermal_model or ThermalModel()
        self.horizon = horizon_hours
        self.max_rate = max_rate
        self.dt = 0.25  # 15-minute steps
        self.n_steps = int(horizon_hours / self.dt)

    def _simulate(
        self,
        duty_cycles: np.ndarray,
        current_temp: float,
        ambient_temp: float,
        heater_power: float,
        cooler_power: float = 0.0,
        cooler_duties: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """Simulate temperature trajectory with thermal inertia modeling.

        Args:
            duty_cycles: Array of heater duty cycles (0-1) for each time step
            current_temp: Current temperature
            ambient_temp: Ambient temperature
            heater_power: Effective heater power (may be adjusted for phase)
            cooler_power: Cooling power (negative temperature rate when on)
            cooler_duties: Array of cooler duty cycles (0-1), if dual-mode control

        Returns:
            Array of predicted temperatures

        Thermal inertia modeling:
            When a device turns off, temperature continues to drift due to
            thermal mass (cold/hot chamber walls, residual air temp, sensor lag).
            This drift decays exponentially: drift(t) = rate * exp(-t / decay_time)
        """
        temps = np.zeros(self.n_steps + 1)
        temps[0] = current_temp

        # Track device states to detect transitions
        prev_heater_on = duty_cycles[0] > 0.1 if len(duty_cycles) > 0 else False
        prev_cooler_on = (
            cooler_duties[0] > 0.1 if cooler_duties is not None and len(cooler_duties) > 0 else False
        )

        # Overshoot drift tracking (decays exponentially)
        heating_drift = 0.0
        cooling_drift = 0.0

        for i, duty in enumerate(duty_cycles):
            # Current device states
            heater_on = duty > 0.1
            cooler_on = cooler_duties[i] > 0.1 if cooler_duties is not None else False

            # Detect state transitions and initialize drift
            if prev_heater_on and not heater_on:
                # Heater just turned off - start heating drift
                heating_drift = self.model.heating_overshoot_rate
            if prev_cooler_on and not cooler_on:
                # Cooler just turned off - start cooling drift
                cooling_drift = -self.model.cooling_overshoot_rate

            # Exponential decay of drift
            decay_factor = np.exp(-self.dt / self.model.overshoot_decay_time)
            heating_drift *= decay_factor
            cooling_drift *= decay_factor

            # Temperature changes
            heat_input = heater_power * duty * self.dt
            cool_output = -cooler_power * (cooler_duties[i] if cooler_duties is not None else 0) * self.dt
            heat_loss = self.model.ambient_loss_rate * (temps[i] - ambient_temp) * self.dt
            drift = (heating_drift + cooling_drift) * self.dt

            temps[i + 1] = temps[i] + heat_input + cool_output - heat_loss + drift

            prev_heater_on = heater_on
            prev_cooler_on = cooler_on

        return temps

    def _objective(
        self,
        duty_cycles: np.ndarray,
        current_temp: float,
        ambient_temp: float,
        heater_power: float,
    ) -> float:
        """Objective function to minimize.

        Penalizes:
        - Deviation from target temperature
        - Rapid temperature changes
        - Excessive energy usage
        """
        temps = self._simulate(duty_cycles, current_temp, ambient_temp, heater_power)

        # Temperature deviation cost
        deviation_cost = float(np.sum((temps[1:] - self.target_temp) ** 2))

        # Rate of change cost (avoid thermal stress on yeast)
        rates = np.diff(temps) / self.dt
        rate_violations = np.maximum(np.abs(rates) - self.max_rate, 0)
        rate_cost = float(np.sum(rate_violations ** 2) * 10)

        # Energy cost (prefer less heating)
        energy_cost = float(np.sum(duty_cycles) * 0.1)

        return deviation_cost + rate_cost + energy_cost

    def compute_optimal_duty(
        self,
        current_temp: float,
        ambient_temp: float,
        fermentation_phase: str = "unknown",
    ) -> dict:
        """Compute optimal heater duty cycle.

        Args:
            current_temp: Current fermentation temperature (Fahrenheit)
            ambient_temp: Current ambient temperature (Fahrenheit)
            fermentation_phase: Current phase for phase-specific tuning

        Returns:
            Dictionary with:
            - optimal_duty: Recommended duty cycle (0-1)
            - predicted_temps: Temperature trajectory
            - time_to_target: Hours until reaching target (or None)
            - optimization_success: Whether optimization converged
        """
        # Phase-specific adjustments
        heater_power = self.model.heater_power
        if fermentation_phase == "exponential":
            # During peak fermentation, yeast generates heat
            # Be more conservative with heating
            heater_power *= 0.7

        # Initial guess: proportional to error
        error = self.target_temp - current_temp
        initial_duty = float(np.clip(error * 0.1, 0, 1))
        x0 = np.full(self.n_steps, initial_duty)

        # Optimize
        result = minimize(
            self._objective,
            x0,
            args=(current_temp, ambient_temp, heater_power),
            method="SLSQP",
            bounds=[(0, 1)] * self.n_steps,
            options={"maxiter": 100},
        )

        optimal_duties = result.x
        predicted_temps = self._simulate(
            optimal_duties, current_temp, ambient_temp, heater_power
        )

        return {
            "optimal_duty": float(optimal_duties[0]),
            "predicted_temps": predicted_temps.tolist(),
            "time_to_target": self._time_to_target(predicted_temps),
            "optimization_success": result.success,
        }

    def _time_to_target(
        self, temps: np.ndarray, tolerance: float = 0.5
    ) -> Optional[float]:
        """Calculate hours until temperature reaches target.

        Args:
            temps: Predicted temperature trajectory
            tolerance: Acceptable deviation from target

        Returns:
            Hours to reach target, or None if not reached in horizon
        """
        within_target = np.abs(temps - self.target_temp) < tolerance
        if within_target.any():
            return float(np.argmax(within_target) * self.dt)
        return None

    def update_overshoot_estimates(
        self,
        predicted_temp: float,
        actual_temp: float,
        device_just_turned_off: str,  # "heater", "cooler", or None
        time_since_turnoff: float,  # Hours since device turned off
    ) -> None:
        """Learn from prediction errors to improve overshoot estimates.

        This implements self-learning similar to BrewPi's overshoot estimators.
        After each control cycle, compare predicted vs actual temperature to
        adjust the overshoot rate coefficients.

        Args:
            predicted_temp: What the MPC predicted
            actual_temp: What actually happened
            device_just_turned_off: Which device (if any) recently turned off
            time_since_turnoff: Time elapsed since device turned off

        The learning happens when a device turns off and we can measure
        how much the temperature actually coasted vs what we predicted.
        """
        if device_just_turned_off is None or time_since_turnoff > self.model.overshoot_decay_time * 2:
            return  # No learning opportunity

        # Calculate prediction error
        error = actual_temp - predicted_temp

        # Decay factor for time elapsed
        decay = np.exp(-time_since_turnoff / self.model.overshoot_decay_time)

        # Estimate actual overshoot rate from observed error
        if device_just_turned_off == "heater" and decay > 0.1:
            actual_overshoot_rate = error / (time_since_turnoff * decay)
            # Update with exponential moving average
            self.model.heating_overshoot_rate = (
                self.model.learning_rate * actual_overshoot_rate
                + (1 - self.model.learning_rate) * self.model.heating_overshoot_rate
            )
        elif device_just_turned_off == "cooler" and decay > 0.1:
            actual_overshoot_rate = -error / (time_since_turnoff * decay)
            self.model.cooling_overshoot_rate = (
                self.model.learning_rate * actual_overshoot_rate
                + (1 - self.model.learning_rate) * self.model.cooling_overshoot_rate
            )
```

**Step 4: Run test to verify it passes**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest tests/test_mpc.py -v`

Expected: PASS (6 tests)

**Step 5: Commit**

```bash
git add backend/ml/control/ tests/test_mpc.py
git commit -m "feat(ml): implement MPC temperature controller"
```

---

## Task 7: Create ML Pipeline Orchestrator

**Files:**
- Create: `backend/ml/pipeline.py`
- Create: `tests/test_pipeline.py`

**Step 1: Write the failing test**

Create `tests/test_pipeline.py`:
```python
"""Tests for the ML pipeline orchestrator."""

import pytest
from backend.ml.pipeline import MLPipeline
from backend.ml.config import MLConfig


class TestMLPipeline:
    """Tests for ML pipeline orchestration."""

    def test_processes_reading(self, sample_readings):
        """Pipeline processes a reading through all components."""
        config = MLConfig(
            enable_kalman_filter=True,
            enable_anomaly_detection=True,
            enable_predictions=False,  # Need more data
            enable_mpc=False,
        )
        pipeline = MLPipeline(config)

        reading = sample_readings[0]
        result = pipeline.process_reading(
            tilt_id="test-tilt",
            sg=reading["sg"],
            temp=reading["temp"],
            rssi=reading["rssi"],
        )

        assert "sg_filtered" in result
        assert "temp_filtered" in result
        assert "confidence" in result
        assert "is_anomaly" in result

    def test_kalman_filter_disabled(self, sample_readings):
        """Returns raw values when Kalman filter disabled."""
        config = MLConfig(enable_kalman_filter=False)
        pipeline = MLPipeline(config)

        reading = sample_readings[0]
        result = pipeline.process_reading(
            tilt_id="test-tilt",
            sg=reading["sg"],
            temp=reading["temp"],
            rssi=reading["rssi"],
        )

        # Should return raw values
        assert result["sg_filtered"] == reading["sg"]
        assert result["temp_filtered"] == reading["temp"]

    def test_maintains_per_tilt_state(self, sample_readings):
        """Pipeline maintains separate state per Tilt."""
        config = MLConfig()
        pipeline = MLPipeline(config)

        # Process readings for two different Tilts
        result1 = pipeline.process_reading(
            tilt_id="tilt-red",
            sg=1.050,
            temp=68.0,
            rssi=-60,
        )

        result2 = pipeline.process_reading(
            tilt_id="tilt-blue",
            sg=1.040,
            temp=70.0,
            rssi=-55,
        )

        # Each should have its own filtered value
        assert result1["sg_filtered"] != result2["sg_filtered"]

    def test_resets_for_new_batch(self):
        """Pipeline can reset state for a new fermentation batch."""
        config = MLConfig()
        pipeline = MLPipeline(config)

        # Process some readings
        pipeline.process_reading("tilt-red", 1.050, 68.0, -60)
        pipeline.process_reading("tilt-red", 1.045, 68.0, -60)

        # Reset for new batch
        pipeline.reset_tilt("tilt-red", initial_sg=1.060, initial_temp=65.0)

        result = pipeline.process_reading("tilt-red", 1.059, 65.0, -60)

        # Should be close to new initial value
        assert result["sg_filtered"] == pytest.approx(1.059, abs=0.002)

    def test_get_predictions(self, fermentation_data):
        """Pipeline provides fermentation predictions."""
        config = MLConfig(enable_predictions=True)
        pipeline = MLPipeline(config)

        # Feed fermentation history
        for i, (hours, sg) in enumerate(zip(
            fermentation_data["hours"][:15],
            fermentation_data["sg"][:15]
        )):
            pipeline.process_reading(
                tilt_id="test-tilt",
                sg=sg,
                temp=68.0,
                rssi=-60,
            )

        predictions = pipeline.get_predictions("test-tilt")

        assert predictions is not None
        assert "predicted_fg" in predictions
        assert "hours_to_complete" in predictions
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest tests/test_pipeline.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'backend.ml.pipeline'"

**Step 3: Write implementation**

Create `backend/ml/pipeline.py`:
```python
"""ML Pipeline orchestrator for Tilt readings.

Coordinates all ML components: Kalman filter, anomaly detection,
predictions, and MPC control.
"""

from datetime import datetime, timezone
from typing import Optional

from .config import MLConfig
from .sensor_fusion.kalman import TiltKalmanFilter
from .anomaly.detector import FermentationAnomalyDetector
from .fermentation.curve_fitter import FermentationCurveFitter


class TiltMLState:
    """ML state for a single Tilt hydrometer."""

    def __init__(self, initial_sg: float = 1.050, initial_temp: float = 68.0):
        """Initialize ML state for a Tilt.

        Args:
            initial_sg: Starting specific gravity
            initial_temp: Starting temperature
        """
        self.kalman = TiltKalmanFilter(initial_sg=initial_sg, initial_temp=initial_temp)
        self.anomaly_detector = FermentationAnomalyDetector()
        self.curve_fitter = FermentationCurveFitter()

        # History for curve fitting
        self.times_hours: list[float] = []
        self.gravities: list[float] = []
        self.start_time: Optional[datetime] = None
        self.last_update: Optional[datetime] = None

    def reset(self, initial_sg: float, initial_temp: float) -> None:
        """Reset state for a new batch.

        Args:
            initial_sg: New starting specific gravity
            initial_temp: New starting temperature
        """
        self.kalman.reset(initial_sg, initial_temp)
        self.anomaly_detector.reset()
        self.curve_fitter = FermentationCurveFitter()
        self.times_hours.clear()
        self.gravities.clear()
        self.start_time = None
        self.last_update = None


class MLPipeline:
    """Orchestrates ML processing for Tilt readings.

    Manages per-Tilt state and coordinates:
    - Kalman filtering for noise reduction
    - Anomaly detection for invalid readings
    - Curve fitting for predictions
    """

    def __init__(self, config: Optional[MLConfig] = None):
        """Initialize the ML pipeline.

        Args:
            config: ML configuration, uses defaults if not provided
        """
        self.config = config or MLConfig()
        self._tilt_states: dict[str, TiltMLState] = {}

    def _get_or_create_state(
        self,
        tilt_id: str,
        initial_sg: float = 1.050,
        initial_temp: float = 68.0,
    ) -> TiltMLState:
        """Get or create ML state for a Tilt.

        Args:
            tilt_id: Unique Tilt identifier
            initial_sg: Initial SG if creating new state
            initial_temp: Initial temp if creating new state

        Returns:
            TiltMLState for this Tilt
        """
        if tilt_id not in self._tilt_states:
            self._tilt_states[tilt_id] = TiltMLState(
                initial_sg=initial_sg,
                initial_temp=initial_temp,
            )
        return self._tilt_states[tilt_id]

    def process_reading(
        self,
        tilt_id: str,
        sg: float,
        temp: float,
        rssi: float,
    ) -> dict:
        """Process a new Tilt reading through the ML pipeline.

        Args:
            tilt_id: Unique Tilt identifier
            sg: Raw specific gravity reading
            temp: Raw temperature reading (Fahrenheit)
            rssi: Bluetooth signal strength (dBm)

        Returns:
            Dictionary with processed results:
            - sg_filtered: Kalman-filtered SG
            - sg_rate: Rate of SG change
            - temp_filtered: Kalman-filtered temperature
            - temp_rate: Rate of temperature change
            - confidence: Reading confidence (0-1)
            - is_anomaly: Whether reading is anomalous
            - anomaly_reasons: List of anomaly reasons
        """
        state = self._get_or_create_state(tilt_id, initial_sg=sg, initial_temp=temp)
        now = datetime.now(timezone.utc)

        # Calculate time delta
        if state.last_update is not None:
            dt_hours = (now - state.last_update).total_seconds() / 3600
        else:
            dt_hours = 1 / 60  # Default to 1 minute
        state.last_update = now

        # Apply Kalman filter
        if self.config.enable_kalman_filter:
            kalman_result = state.kalman.update(
                sg=sg,
                temp=temp,
                rssi=rssi,
                dt_hours=max(dt_hours, 1 / 3600),  # Min 1 second
            )
            sg_filtered = kalman_result["sg_filtered"]
            sg_rate = kalman_result["sg_rate"]
            temp_filtered = kalman_result["temp_filtered"]
            temp_rate = kalman_result["temp_rate"]
            confidence = kalman_result["confidence"]
        else:
            sg_filtered = sg
            sg_rate = 0.0
            temp_filtered = temp
            temp_rate = 0.0
            confidence = 1.0

        # Anomaly detection
        if self.config.enable_anomaly_detection:
            anomaly_result = state.anomaly_detector.check_reading(
                sg=sg_filtered,
                temp=temp_filtered,
                rssi=rssi,
                sg_rate=sg_rate,
            )
            is_anomaly = anomaly_result["is_anomaly"]
            anomaly_reasons = anomaly_result["reasons"]
        else:
            is_anomaly = False
            anomaly_reasons = []

        # Update history for predictions (only non-anomalous readings)
        if self.config.enable_predictions and not is_anomaly:
            if state.start_time is None:
                state.start_time = now

            hours_elapsed = (now - state.start_time).total_seconds() / 3600
            state.times_hours.append(hours_elapsed)
            state.gravities.append(sg_filtered)

            # Refit curve periodically
            if len(state.times_hours) >= self.config.prediction_min_readings:
                import numpy as np
                state.curve_fitter.fit(
                    np.array(state.times_hours),
                    np.array(state.gravities),
                )

        return {
            "sg_filtered": sg_filtered,
            "sg_rate": sg_rate,
            "temp_filtered": temp_filtered,
            "temp_rate": temp_rate,
            "confidence": confidence,
            "is_anomaly": is_anomaly,
            "anomaly_reasons": anomaly_reasons,
        }

    def get_predictions(self, tilt_id: str) -> Optional[dict]:
        """Get fermentation predictions for a Tilt.

        Args:
            tilt_id: Unique Tilt identifier

        Returns:
            Prediction dictionary or None if insufficient data
        """
        if tilt_id not in self._tilt_states:
            return None

        state = self._tilt_states[tilt_id]
        return state.curve_fitter.predict_completion()

    def get_phase(self, tilt_id: str) -> str:
        """Get current fermentation phase for a Tilt.

        Args:
            tilt_id: Unique Tilt identifier

        Returns:
            Phase name or "unknown"
        """
        if tilt_id not in self._tilt_states:
            return "unknown"

        state = self._tilt_states[tilt_id]
        kalman_state = state.kalman.get_state()

        return state.curve_fitter.get_current_phase(
            current_sg=kalman_state["sg_filtered"],
            current_rate=kalman_state["sg_rate"],
        )

    def reset_tilt(
        self,
        tilt_id: str,
        initial_sg: float = 1.050,
        initial_temp: float = 68.0,
    ) -> None:
        """Reset ML state for a Tilt (new batch).

        Args:
            tilt_id: Unique Tilt identifier
            initial_sg: New starting specific gravity
            initial_temp: New starting temperature
        """
        if tilt_id in self._tilt_states:
            self._tilt_states[tilt_id].reset(initial_sg, initial_temp)
        else:
            self._tilt_states[tilt_id] = TiltMLState(
                initial_sg=initial_sg,
                initial_temp=initial_temp,
            )
```

**Step 4: Run test to verify it passes**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest tests/test_pipeline.py -v`

Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add backend/ml/pipeline.py tests/test_pipeline.py
git commit -m "feat(ml): implement ML pipeline orchestrator"
```

---

## Task 8: Integrate ML Pipeline with Reading Handler

**Files:**
- Modify: `backend/models.py:28-44` (Reading model)
- Modify: `backend/main.py:36-88` (handle_tilt_reading)
- Create: `tests/test_integration.py`

**Step 1: Write the failing test**

Create `tests/test_integration.py`:
```python
"""Integration tests for ML pipeline with main app."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_reading_handler_uses_ml_pipeline():
    """Reading handler integrates with ML pipeline."""
    # Mock the ML pipeline
    mock_pipeline = MagicMock()
    mock_pipeline.process_reading.return_value = {
        "sg_filtered": 1.049,
        "sg_rate": -0.001,
        "temp_filtered": 68.0,
        "temp_rate": 0.0,
        "confidence": 0.95,
        "is_anomaly": False,
        "anomaly_reasons": [],
    }

    with patch("backend.main.ml_pipeline", mock_pipeline):
        from backend.main import handle_tilt_reading
        from backend.scanner import TiltReading

        # Create a mock reading
        reading = TiltReading(
            id="test-tilt",
            color="RED",
            mac="AA:BB:CC:DD:EE:FF",
            sg=1.050,
            temp_f=68.0,
            rssi=-60,
        )

        # Mock the database session
        with patch("backend.main.async_session_factory") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            mock_db.get.return_value = MagicMock(beer_name="Test Beer")

            # Mock calibration service
            with patch("backend.main.calibration_service") as mock_cal:
                mock_cal.calibrate_reading = AsyncMock(return_value=(1.050, 68.0))

                # Mock websocket manager
                with patch("backend.main.manager") as mock_ws:
                    mock_ws.broadcast = AsyncMock()

                    await handle_tilt_reading(reading)

        # Verify ML pipeline was called
        mock_pipeline.process_reading.assert_called_once_with(
            tilt_id="test-tilt",
            sg=1.050,  # Calibrated value
            temp=68.0,
            rssi=-60,
        )
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest tests/test_integration.py -v`

Expected: FAIL with "AttributeError: module 'backend.main' has no attribute 'ml_pipeline'"

**Step 3: Add ML columns to Reading model**

Modify `backend/models.py`, update the Reading class (around line 28-44):

```python
class Reading(Base):
    __tablename__ = "readings"
    __table_args__ = (
        Index("ix_readings_tilt_timestamp", "tilt_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tilt_id: Mapped[str] = mapped_column(ForeignKey("tilts.id"), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), index=True)
    sg_raw: Mapped[Optional[float]] = mapped_column()
    sg_calibrated: Mapped[Optional[float]] = mapped_column()
    sg_filtered: Mapped[Optional[float]] = mapped_column()  # ML: Kalman filtered
    temp_raw: Mapped[Optional[float]] = mapped_column()
    temp_calibrated: Mapped[Optional[float]] = mapped_column()
    temp_filtered: Mapped[Optional[float]] = mapped_column()  # ML: Kalman filtered
    rssi: Mapped[Optional[int]] = mapped_column()
    confidence: Mapped[Optional[float]] = mapped_column()  # ML: Reading confidence
    is_anomaly: Mapped[Optional[bool]] = mapped_column()  # ML: Anomaly flag

    tilt: Mapped["Tilt"] = relationship(back_populates="readings")
```

**Step 4: Integrate ML pipeline into main.py**

Modify `backend/main.py`, add imports at top (after line 24):

```python
from .ml.pipeline import MLPipeline
from .ml.config import MLConfig
```

Add global ML pipeline instance (after line 33):

```python
# ML pipeline instance
ml_pipeline = MLPipeline(MLConfig())
```

Modify `handle_tilt_reading` function (replace lines 36-88):

```python
async def handle_tilt_reading(reading: TiltReading):
    """Process a new Tilt reading: apply ML, update DB, and broadcast."""
    async with async_session_factory() as session:
        # Upsert Tilt record
        tilt = await session.get(Tilt, reading.id)
        if not tilt:
            tilt = Tilt(
                id=reading.id,
                color=reading.color,
                mac=reading.mac,
                beer_name="Untitled",
            )
            session.add(tilt)

        tilt.last_seen = datetime.now(timezone.utc)
        tilt.mac = reading.mac

        # Apply calibration
        sg_calibrated, temp_calibrated = await calibration_service.calibrate_reading(
            session, reading.id, reading.sg, reading.temp_f
        )

        # Apply ML pipeline
        ml_result = ml_pipeline.process_reading(
            tilt_id=reading.id,
            sg=sg_calibrated,
            temp=temp_calibrated,
            rssi=reading.rssi,
        )

        # Store reading in DB with ML results
        db_reading = Reading(
            tilt_id=reading.id,
            sg_raw=reading.sg,
            sg_calibrated=sg_calibrated,
            sg_filtered=ml_result["sg_filtered"],
            temp_raw=reading.temp_f,
            temp_calibrated=temp_calibrated,
            temp_filtered=ml_result["temp_filtered"],
            rssi=reading.rssi,
            confidence=ml_result["confidence"],
            is_anomaly=ml_result["is_anomaly"],
        )
        session.add(db_reading)
        await session.commit()

        # Build reading data for WebSocket broadcast
        reading_data = {
            "id": reading.id,
            "color": reading.color,
            "beer_name": tilt.beer_name,
            "original_gravity": tilt.original_gravity,
            "sg": ml_result["sg_filtered"],  # Use filtered value
            "sg_raw": reading.sg,
            "sg_calibrated": sg_calibrated,
            "temp": ml_result["temp_filtered"],  # Use filtered value
            "temp_raw": reading.temp_f,
            "temp_calibrated": temp_calibrated,
            "rssi": reading.rssi,
            "confidence": ml_result["confidence"],
            "is_anomaly": ml_result["is_anomaly"],
            "sg_rate": ml_result["sg_rate"],
            "last_seen": datetime.now(timezone.utc).isoformat(),
        }

        # Update in-memory cache
        latest_readings[reading.id] = reading_data

        # Broadcast to all WebSocket clients
        await manager.broadcast(reading_data)
```

**Step 5: Run test to verify it passes**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest tests/test_integration.py -v`

Expected: PASS

**Step 6: Commit**

```bash
git add backend/models.py backend/main.py tests/test_integration.py
git commit -m "feat(ml): integrate ML pipeline with reading handler"
```

---

## Task 9: Add Predictions API Endpoint

**Files:**
- Modify: `backend/routers/tilts.py`
- Create: `tests/test_predictions_api.py`

**Step 1: Write the failing test**

Create `tests/test_predictions_api.py`:
```python
"""Tests for predictions API endpoint."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


@pytest.mark.asyncio
async def test_get_predictions_endpoint():
    """Predictions endpoint returns fermentation predictions."""
    mock_predictions = {
        "predicted_fg": 1.012,
        "predicted_og": 1.055,
        "hours_to_complete": 48.5,
        "completion_date": datetime.now().isoformat(),
        "attenuation_percent": 78.2,
        "fit_quality": 0.95,
        "decay_rate": 0.02,
    }

    with patch("backend.routers.tilts.ml_pipeline") as mock_pipeline:
        mock_pipeline.get_predictions.return_value = mock_predictions
        mock_pipeline.get_phase.return_value = "exponential"

        from fastapi.testclient import TestClient
        from backend.main import app

        client = TestClient(app)
        response = client.get("/api/tilts/test-tilt/predictions")

        assert response.status_code == 200
        data = response.json()
        assert data["predicted_fg"] == pytest.approx(1.012)
        assert data["phase"] == "exponential"


@pytest.mark.asyncio
async def test_get_predictions_insufficient_data():
    """Predictions endpoint returns 404 when insufficient data."""
    with patch("backend.routers.tilts.ml_pipeline") as mock_pipeline:
        mock_pipeline.get_predictions.return_value = None

        from fastapi.testclient import TestClient
        from backend.main import app

        client = TestClient(app)
        response = client.get("/api/tilts/unknown-tilt/predictions")

        assert response.status_code == 404
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest tests/test_predictions_api.py -v`

Expected: FAIL

**Step 3: Add predictions endpoint to tilts router**

Add to `backend/routers/tilts.py` (add import at top and endpoint at bottom):

At the top, add import:
```python
from ..main import ml_pipeline
```

Add endpoint at bottom of file:
```python
@router.get("/tilts/{tilt_id}/predictions")
async def get_predictions(tilt_id: str):
    """Get fermentation predictions for a Tilt.

    Returns predicted final gravity, completion time, and current phase.
    Requires sufficient fermentation data (at least 10 readings).
    """
    predictions = ml_pipeline.get_predictions(tilt_id)

    if predictions is None:
        raise HTTPException(
            status_code=404,
            detail="Insufficient data for predictions. Need at least 10 readings.",
        )

    phase = ml_pipeline.get_phase(tilt_id)

    return {
        **predictions,
        "phase": phase,
        "completion_date": predictions["completion_date"].isoformat()
        if predictions.get("completion_date")
        else None,
    }
```

**Step 4: Run test to verify it passes**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest tests/test_predictions_api.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/routers/tilts.py tests/test_predictions_api.py
git commit -m "feat(api): add fermentation predictions endpoint"
```

---

## Task 10: Update Dependencies

**Files:**
- Modify: `pyproject.toml`

**Step 1: Update pyproject.toml**

Add ML dependencies to `pyproject.toml`:

```toml
[project]
name = "tilt-ui"
version = "1.0.0"
description = "Modern web UI for Tilt Hydrometer monitoring"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.104",
    "uvicorn[standard]>=0.24",
    "sqlalchemy>=2.0",
    "aiosqlite>=0.19",
    "pydantic>=2.5",
    "pydantic-settings>=2.1",
    "bleak>=0.22",
    "beacontools>=2.1",
    "httpx>=0.25",
    # ML dependencies
    "filterpy>=1.4.5",
    "scipy>=1.11.0",
    "scikit-learn>=1.3.0",
    "numpy>=1.24.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4",
    "pytest-asyncio>=0.21",
    "httpx>=0.25",
]
slm = [
    # Optional: Small Language Model support
    # Recommended: Mistral Ministral 3B (December 2025)
    # - Apache 2.0 license, multimodal, 40+ languages
    # - ~6GB quantized (INT4), runs on RPi 5 (8GB RAM)
    # - 5-10 tokens/sec on RPi 5
    # Alternative: qwen2.5:1.5b (smaller, text-only)
    "llama-cpp-python>=0.2.0",
]
```

**Step 2: Install dependencies**

Run: `cd /home/ladmin/Projects/tilt_ui && pip install -e ".[dev]"`

**Step 3: Run all tests**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest tests/ -v`

Expected: All tests pass

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add ML dependencies to pyproject.toml"
```

---

## Task 11: Run Full Test Suite and Verify

**Step 1: Run all tests**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m pytest tests/ -v --tb=short`

Expected: All tests pass

**Step 2: Run type checker (optional)**

Run: `cd /home/ladmin/Projects/tilt_ui && pip install mypy && mypy backend/ml/`

Expected: No errors (or only minor warnings)

**Step 3: Start the application**

Run: `cd /home/ladmin/Projects/tilt_ui && python -m uvicorn backend.main:app --reload`

Expected: Application starts without errors

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat(ml): complete ML enhancement implementation

- Kalman filter for sensor noise reduction
- Anomaly detection for invalid readings
- Fermentation curve fitting for predictions
- MPC temperature controller (optional)
- Full test coverage for all ML components"
```

---

## Summary of Files Created/Modified

### New Files (13)
- `pytest.ini`
- `tests/__init__.py`
- `tests/conftest.py`
- `tests/test_ml_config.py`
- `tests/test_kalman.py`
- `tests/test_anomaly.py`
- `tests/test_curve_fitter.py`
- `tests/test_mpc.py`
- `tests/test_pipeline.py`
- `tests/test_integration.py`
- `tests/test_predictions_api.py`
- `backend/ml/__init__.py`
- `backend/ml/config.py`
- `backend/ml/sensor_fusion/__init__.py`
- `backend/ml/sensor_fusion/kalman.py`
- `backend/ml/anomaly/__init__.py`
- `backend/ml/anomaly/detector.py`
- `backend/ml/fermentation/__init__.py`
- `backend/ml/fermentation/curve_fitter.py`
- `backend/ml/control/__init__.py`
- `backend/ml/control/mpc.py`
- `backend/ml/pipeline.py`

### Modified Files (3)
- `pyproject.toml` - Add ML dependencies
- `backend/models.py` - Add ML columns to Reading model
- `backend/main.py` - Integrate ML pipeline
- `backend/routers/tilts.py` - Add predictions endpoint

---

## Appendix: Mistral Ministral 3B for Natural Language Assistant

**Note:** This appendix provides guidance for Task 9 (Optional: Natural Language Assistant) if you choose to implement the SLM feature.

### Why Mistral Ministral 3B?

As of December 2025, Mistral AI released the Ministral 3 family, which is superior to qwen2.5:1.5b for BrewSignal's use case:

| Feature | Ministral 3B (Instruct) | qwen2.5:1.5b |
|---------|------------------------|--------------|
| **License** | Apache 2.0 | Apache 2.0 |
| **Parameters** | 3 billion | 1.5 billion |
| **Multimodal** | Yes (text + images) | No (text only) |
| **Languages** | 40+ native | Primarily English/Chinese |
| **RPi Performance** | 5-10 tokens/sec (RPi 5, 8GB) | 10-15 tokens/sec (RPi 4, 4GB) |
| **Quantized Size** | ~6GB (INT4) | ~3GB (Q4_K_M) |
| **Training Date** | 2025 | 2024 |

### Use Cases for BrewSignal

**Text-based queries:**
- "How's my IPA fermenting?" → Analyzes gravity curve, fermentation phase
- "When should I dry hop?" → Considers batch progress, style, timeline
- "Suggest a recipe for Belgian Tripel" → Generates recipe recommendations
- "What's wrong with batch #5?" → Reviews anomalies, temperature issues

**Multimodal capabilities (unique to Ministral):**
- Upload fermentation chamber photo → Estimates fermentation activity (krausen, clarity)
- Show gravity reading image → OCR + validation against expected values
- Analyze trub/sediment photos → Suggests when to rack

### Installation

**Download model:**
```bash
# Install llama-cpp-python with hardware acceleration
pip install llama-cpp-python

# Download Ministral 3B Instruct (INT4 quantization)
mkdir -p ~/.cache/llm
cd ~/.cache/llm
wget https://huggingface.co/mistralai/Ministral-3B-Instruct-Q4_K_M-GGUF/resolve/main/ministral-3b-instruct-q4_k_m.gguf
```

**Update config:**
```python
# backend/ml/config.py
slm_model_path: str = "~/.cache/llm/ministral-3b-instruct-q4_k_m.gguf"
slm_context_size: int = 4096  # Ministral supports 128K, but 4K is sufficient
```

### Integration Pattern

**API Endpoint:**
```python
# backend/routers/assistant.py
@router.post("/api/assistant/query")
async def query_assistant(
    query: str,
    batch_id: Optional[int] = None,
    image: Optional[UploadFile] = None,
) -> dict:
    """Natural language query about fermentation data."""
    # Gather context (batch data, recent readings, anomalies)
    context = await build_context(batch_id)

    # Load model (lazy loading to save memory)
    llm = get_llm()  # Returns cached llama-cpp-python model

    # Build prompt with fermentation context
    prompt = f"""You are a fermentation assistant. Answer based on this data:
{context}

User question: {query}
"""

    # Generate response
    response = llm(prompt, max_tokens=256, temperature=0.7)

    return {"answer": response["choices"][0]["text"]}
```

**Frontend integration:**
```svelte
<!-- frontend/src/routes/assistant/+page.svelte -->
<script lang="ts">
  let query = "";
  let answer = "";

  async function ask() {
    const res = await fetch("/api/assistant/query", {
      method: "POST",
      body: JSON.stringify({ query }),
    });
    const data = await res.json();
    answer = data.answer;
  }
</script>

<textarea bind:value={query} placeholder="Ask about your fermentation..."/>
<button on:click={ask}>Ask</button>
{#if answer}
  <p>{answer}</p>
{/if}
```

### Performance Considerations

**Memory usage:**
- Model: ~6GB (loaded once, kept in memory)
- Inference: ~500MB peak during generation
- **Total:** ~6.5GB RAM required
- **Requirement:** RPi 5 with 8GB RAM

**Latency:**
- First token: ~500ms (model loading cached)
- Subsequent tokens: 100-200ms each (5-10 tok/sec)
- Typical response (50 tokens): 5-10 seconds

**Optimization:**
- Use quantized INT4 model (already specified)
- Keep context window small (4K max, not 128K)
- Limit max_tokens to 256 (concise answers)
- Cache model in memory (don't reload per request)

### When NOT to Use the SLM

The classical ML features (Tasks 1-8) do NOT require an SLM:
- ✅ Kalman filtering - Pure linear algebra
- ✅ Anomaly detection - Statistical thresholds
- ✅ Curve fitting - scipy.optimize
- ✅ MPC temperature control - Numerical optimization
- ✅ Overshoot prevention - Self-learning estimators

Only use the SLM for **natural language interactions** and **image analysis**. The core ML pipeline runs continuously with <5% CPU and no LLM dependency.

### Fallback Option

If Ministral 3B is too large for your RPi setup:
1. Use qwen2.5:1.5b (~3GB, text-only)
2. Or skip the SLM entirely - classical ML provides all core functionality

The SLM is explicitly **optional** because BrewSignal's value is in accurate predictions and control, not conversational AI.
