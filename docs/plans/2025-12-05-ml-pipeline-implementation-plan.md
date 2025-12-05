# ML Pipeline Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate ML pipeline (Kalman filtering, anomaly detection, predictions) into production reading handler, standardize all temperatures to Celsius, and remove legacy smoothing service.

**Architecture:** Per-device ML pipeline instances managed by MLPipelineManager, with graceful degradation on errors and full temperature unit standardization.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite, backend/ml modules (Kalman, anomaly, predictions)

---

## Task 1: Database Schema Migration - Add ML Output Columns

**Files:**
- Modify: `backend/database.py:1-200` (add migration function)
- Modify: `backend/models.py:110-153` (add columns to Reading model)

**Step 1: Write test for Reading model with ML columns**

Create file: `tests/test_ml_schema.py`

```python
"""Test ML schema changes."""
import pytest
from backend.models import Reading
from sqlalchemy import inspect


def test_reading_has_ml_columns():
    """Reading model has ML output columns."""
    inspector = inspect(Reading)
    column_names = [col.name for col in inspector.columns]

    # Kalman filtered values
    assert "sg_filtered" in column_names
    assert "temp_filtered" in column_names

    # Confidence and rates
    assert "confidence" in column_names
    assert "sg_rate" in column_names
    assert "temp_rate" in column_names

    # Anomaly detection
    assert "is_anomaly" in column_names
    assert "anomaly_score" in column_names
    assert "anomaly_reasons" in column_names
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ml_schema.py::test_reading_has_ml_columns -v`
Expected: FAIL with "AssertionError: assert 'sg_filtered' in column_names"

**Step 3: Add ML columns to Reading model**

File: `backend/models.py` (after line 147, before relationships)

```python
    # ML outputs - Kalman filtered values (Celsius)
    sg_filtered: Mapped[Optional[float]] = mapped_column()
    temp_filtered: Mapped[Optional[float]] = mapped_column()

    # ML outputs - Confidence and rates
    confidence: Mapped[Optional[float]] = mapped_column()  # 0.0-1.0
    sg_rate: Mapped[Optional[float]] = mapped_column()     # d(SG)/dt in points/hour
    temp_rate: Mapped[Optional[float]] = mapped_column()   # d(temp)/dt in °C/hour

    # ML outputs - Anomaly detection
    is_anomaly: Mapped[Optional[bool]] = mapped_column(default=False)
    anomaly_score: Mapped[Optional[float]] = mapped_column()  # 0.0-1.0
    anomaly_reasons: Mapped[Optional[str]] = mapped_column(Text)  # JSON array
```

**Step 4: Add migration function**

File: `backend/database.py` (before `async def init_db()`)

```python
async def _migrate_add_ml_columns(engine):
    """Add ML output columns to readings table."""
    async with engine.begin() as conn:
        # Check if migration already applied
        result = await conn.execute(text("PRAGMA table_info(readings)"))
        columns = {row[1] for row in result}

        if "sg_filtered" in columns:
            logging.info("ML columns already exist, skipping migration")
            return

        logging.info("Adding ML output columns to readings table")

        # Add ML columns
        await conn.execute(text("""
            ALTER TABLE readings ADD COLUMN sg_filtered REAL
        """))
        await conn.execute(text("""
            ALTER TABLE readings ADD COLUMN temp_filtered REAL
        """))
        await conn.execute(text("""
            ALTER TABLE readings ADD COLUMN confidence REAL
        """))
        await conn.execute(text("""
            ALTER TABLE readings ADD COLUMN sg_rate REAL
        """))
        await conn.execute(text("""
            ALTER TABLE readings ADD COLUMN temp_rate REAL
        """))
        await conn.execute(text("""
            ALTER TABLE readings ADD COLUMN is_anomaly INTEGER DEFAULT 0
        """))
        await conn.execute(text("""
            ALTER TABLE readings ADD COLUMN anomaly_score REAL
        """))
        await conn.execute(text("""
            ALTER TABLE readings ADD COLUMN anomaly_reasons TEXT
        """))

        logging.info("ML columns added successfully")
```

**Step 5: Call migration from init_db()**

File: `backend/database.py` (in `init_db()` function, before `create_all()`)

```python
async def init_db():
    # ... existing migrations ...

    # Add ML output columns
    await _migrate_add_ml_columns(engine)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

**Step 6: Run test to verify it passes**

Run: `pytest tests/test_ml_schema.py::test_reading_has_ml_columns -v`
Expected: PASS

**Step 7: Commit**

```bash
git add backend/models.py backend/database.py tests/test_ml_schema.py
git commit -m "feat: add ML output columns to Reading model

- sg_filtered, temp_filtered (Kalman outputs)
- confidence, sg_rate, temp_rate (quality metrics)
- is_anomaly, anomaly_score, anomaly_reasons (detection)"
```

---

## Task 2: Temperature Unit Migration - Convert F to C

**Files:**
- Modify: `backend/database.py` (add temperature conversion migration)

**Step 1: Write test for temperature conversion**

File: `tests/test_temp_migration.py`

```python
"""Test temperature unit migration."""
import pytest
from sqlalchemy import text
from backend.database import async_session_factory


@pytest.mark.asyncio
async def test_temperatures_stored_in_celsius():
    """Readings and calibration points use Celsius."""
    async with async_session_factory() as session:
        # Check a sample reading temp is in Celsius range (0-40 typical fermentation)
        result = await session.execute(text(
            "SELECT temp_raw, temp_calibrated FROM readings WHERE temp_raw IS NOT NULL LIMIT 1"
        ))
        row = result.fetchone()

        if row:
            temp_raw, temp_calibrated = row
            # Celsius range check (not Fahrenheit 60-80)
            assert 0 <= temp_raw <= 40, f"temp_raw {temp_raw} not in Celsius range"
            assert 0 <= temp_calibrated <= 40, f"temp_calibrated {temp_calibrated} not in Celsius range"
```

**Step 2: Run test to verify current state (may fail if DB has F data)**

Run: `pytest tests/test_temp_migration.py::test_temperatures_stored_in_celsius -v`
Expected: FAIL if database has Fahrenheit data

**Step 3: Add temperature conversion migration**

File: `backend/database.py` (before `init_db()`)

```python
async def _migrate_temps_fahrenheit_to_celsius(engine):
    """Convert all temperature data from Fahrenheit to Celsius."""
    async with engine.begin() as conn:
        # Check if migration already applied by sampling a reading
        result = await conn.execute(text(
            "SELECT temp_raw FROM readings WHERE temp_raw IS NOT NULL LIMIT 1"
        ))
        row = result.fetchone()

        if row and row[0] < 50:  # Already in Celsius (fermentation temps are 0-40°C)
            logging.info("Temperatures already in Celsius, skipping migration")
            return

        logging.info("Converting temperatures from Fahrenheit to Celsius")

        # Convert readings table
        await conn.execute(text("""
            UPDATE readings
            SET
                temp_raw = (temp_raw - 32) * 5.0 / 9.0,
                temp_calibrated = (temp_calibrated - 32) * 5.0 / 9.0
            WHERE temp_raw IS NOT NULL OR temp_calibrated IS NOT NULL
        """))

        # Convert calibration points
        await conn.execute(text("""
            UPDATE calibration_points
            SET
                raw_value = (raw_value - 32) * 5.0 / 9.0,
                actual_value = (actual_value - 32) * 5.0 / 9.0
            WHERE type = 'temp'
        """))

        logging.info("Temperature conversion complete")
```

**Step 4: Call migration from init_db()**

File: `backend/database.py` (in `init_db()` function, after ML columns migration)

```python
async def init_db():
    # ... existing migrations ...

    # Add ML output columns
    await _migrate_add_ml_columns(engine)

    # Convert temperatures F→C
    await _migrate_temps_fahrenheit_to_celsius(engine)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

**Step 5: Run test to verify conversion**

Run: `pytest tests/test_temp_migration.py::test_temperatures_stored_in_celsius -v`
Expected: PASS (temps now in Celsius)

**Step 6: Commit**

```bash
git add backend/database.py tests/test_temp_migration.py
git commit -m "feat: migrate all temperatures from Fahrenheit to Celsius

- Converts readings.temp_raw and temp_calibrated
- Converts calibration_points for type='temp'
- Uses F→C formula: (F - 32) * 5/9"
```

---

## Task 3: MLPipelineManager Implementation

**Files:**
- Create: `backend/ml/pipeline_manager.py`
- Create: `tests/test_ml_pipeline_manager.py`

**Step 1: Write test for MLPipelineManager creation**

File: `tests/test_ml_pipeline_manager.py`

```python
"""Tests for ML Pipeline Manager."""
import pytest
from backend.ml.pipeline_manager import MLPipelineManager
from backend.ml.config import MLConfig


class TestMLPipelineManager:
    """Test pipeline manager lifecycle."""

    def test_creates_pipeline_on_demand(self):
        """Manager creates pipeline for new device."""
        manager = MLPipelineManager()

        pipeline = manager.get_or_create_pipeline("device-1")

        assert pipeline is not None
        assert manager.get_pipeline_count() == 1

    def test_reuses_existing_pipeline(self):
        """Manager reuses pipeline for same device."""
        manager = MLPipelineManager()

        pipeline1 = manager.get_or_create_pipeline("device-1")
        pipeline2 = manager.get_or_create_pipeline("device-1")

        assert pipeline1 is pipeline2  # Same object
        assert manager.get_pipeline_count() == 1

    def test_manages_multiple_devices(self):
        """Manager handles multiple devices independently."""
        manager = MLPipelineManager()

        pipeline1 = manager.get_or_create_pipeline("device-1")
        pipeline2 = manager.get_or_create_pipeline("device-2")

        assert pipeline1 is not pipeline2
        assert manager.get_pipeline_count() == 2

    def test_reset_pipeline(self):
        """Manager resets pipeline state."""
        manager = MLPipelineManager()
        pipeline = manager.get_or_create_pipeline("device-1")

        # Process some readings
        pipeline.process_reading(sg=1.050, temp=20.0, rssi=-60, time_hours=0)
        pipeline.process_reading(sg=1.045, temp=20.0, rssi=-60, time_hours=1)

        # Reset
        manager.reset_pipeline("device-1", initial_sg=1.060, initial_temp=18.0)

        # Pipeline should be reset (history cleared)
        assert len(pipeline.sg_history) == 0

    def test_remove_pipeline(self):
        """Manager removes pipeline for device."""
        manager = MLPipelineManager()
        manager.get_or_create_pipeline("device-1")

        assert manager.get_pipeline_count() == 1

        manager.remove_pipeline("device-1")

        assert manager.get_pipeline_count() == 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ml_pipeline_manager.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'backend.ml.pipeline_manager'"

**Step 3: Implement MLPipelineManager**

File: `backend/ml/pipeline_manager.py`

```python
"""ML Pipeline Manager for per-device pipeline instances."""

import logging
from typing import Optional
from .pipeline import MLPipeline
from .config import MLConfig


class MLPipelineManager:
    """Manages per-device ML pipeline instances.

    Each device (Tilt, iSpindel, etc.) gets its own MLPipeline instance
    to maintain independent state for Kalman filtering, anomaly detection,
    and fermentation predictions.
    """

    def __init__(self, config: Optional[MLConfig] = None):
        """Initialize manager with optional ML configuration.

        Args:
            config: ML configuration (uses defaults if not provided)
        """
        self.pipelines: dict[str, MLPipeline] = {}
        self.config = config or MLConfig()
        logging.info(f"MLPipelineManager initialized with config: {self.config}")

    def get_or_create_pipeline(self, device_id: str) -> MLPipeline:
        """Get existing pipeline or create new one for device.

        Args:
            device_id: Unique device identifier

        Returns:
            MLPipeline instance for this device
        """
        if device_id not in self.pipelines:
            logging.info(f"Creating new ML pipeline for device: {device_id}")
            self.pipelines[device_id] = MLPipeline(self.config)
        return self.pipelines[device_id]

    def reset_pipeline(
        self,
        device_id: str,
        initial_sg: float = 1.050,
        initial_temp: float = 20.0
    ):
        """Reset pipeline state for new batch.

        Args:
            device_id: Unique device identifier
            initial_sg: Starting specific gravity
            initial_temp: Starting temperature (°C)
        """
        if device_id in self.pipelines:
            logging.info(f"Resetting ML pipeline for device: {device_id}")
            self.pipelines[device_id].reset(initial_sg, initial_temp)

    def remove_pipeline(self, device_id: str):
        """Remove pipeline for device (cleanup).

        Args:
            device_id: Unique device identifier
        """
        if device_id in self.pipelines:
            logging.info(f"Removing ML pipeline for device: {device_id}")
            del self.pipelines[device_id]

    def get_pipeline_count(self) -> int:
        """Get count of active pipelines."""
        return len(self.pipelines)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ml_pipeline_manager.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add backend/ml/pipeline_manager.py tests/test_ml_pipeline_manager.py
git commit -m "feat: add MLPipelineManager for per-device pipelines

- Lazy pipeline instantiation
- Independent state per device
- Reset and cleanup methods"
```

---

## Task 4: Helper Function - Calculate Time Since Batch Start

**Files:**
- Modify: `backend/main.py` (add helper function before handle_tilt_reading)

**Step 1: Write test for time calculation**

File: `tests/test_batch_time_helpers.py`

```python
"""Test batch time calculation helpers."""
import pytest
from datetime import datetime, timezone, timedelta
from backend.main import calculate_time_since_batch_start
from backend.models import Batch
from backend.database import async_session_factory


@pytest.mark.asyncio
async def test_calculate_time_since_batch_start():
    """Calculate hours since batch start."""
    async with async_session_factory() as session:
        # Create test batch
        start_time = datetime.now(timezone.utc) - timedelta(hours=48)
        batch = Batch(
            name="Test Batch",
            status="fermenting",
            start_date=start_time
        )
        session.add(batch)
        await session.commit()
        await session.refresh(batch)

        # Calculate time
        hours = await calculate_time_since_batch_start(session, batch.id)

        # Should be approximately 48 hours (allow 1 minute tolerance)
        assert 47.9 <= hours <= 48.1


@pytest.mark.asyncio
async def test_calculate_time_returns_zero_for_no_batch():
    """Returns 0.0 when batch_id is None."""
    async with async_session_factory() as session:
        hours = await calculate_time_since_batch_start(session, None)
        assert hours == 0.0


@pytest.mark.asyncio
async def test_calculate_time_returns_zero_for_no_start_date():
    """Returns 0.0 when batch has no start_date."""
    async with async_session_factory() as session:
        batch = Batch(
            name="Test Batch",
            status="planning",
            start_date=None
        )
        session.add(batch)
        await session.commit()
        await session.refresh(batch)

        hours = await calculate_time_since_batch_start(session, batch.id)
        assert hours == 0.0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_batch_time_helpers.py -v`
Expected: FAIL with "NameError: name 'calculate_time_since_batch_start' is not defined"

**Step 3: Implement helper function**

File: `backend/main.py` (add before `handle_tilt_reading` function, around line 40)

```python
async def calculate_time_since_batch_start(session, batch_id: Optional[int]) -> float:
    """Calculate hours since batch start.

    Args:
        session: Database session
        batch_id: Batch ID

    Returns:
        Hours since batch start_date (0.0 if no batch or no start_date)
    """
    if not batch_id:
        return 0.0

    batch = await session.get(Batch, batch_id)
    if not batch or not batch.start_date:
        return 0.0

    now = datetime.now(timezone.utc)
    delta = now - batch.start_date
    return delta.total_seconds() / 3600.0  # Convert to hours
```

**Step 4: Add import for Optional**

File: `backend/main.py` (update imports at top)

```python
from typing import Optional  # Add if not already present
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_batch_time_helpers.py -v`
Expected: All 3 tests PASS

**Step 6: Commit**

```bash
git add backend/main.py tests/test_batch_time_helpers.py
git commit -m "feat: add helper to calculate time since batch start

- Returns hours since batch.start_date
- Handles None batch_id and missing start_date
- Used for ML time series context"
```

---

## Task 5: Update Reading Handler - Tilt F to C Conversion

**Files:**
- Modify: `backend/main.py:44-148` (handle_tilt_reading function)

**Step 1: Write test for Fahrenheit to Celsius conversion at boundary**

File: `tests/test_tilt_temp_conversion.py`

```python
"""Test Tilt temperature conversion at boundary."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from backend.main import handle_tilt_reading
from backend.scanner import TiltReading


@pytest.mark.asyncio
@patch('backend.main.websocket_manager')
@patch('backend.main.calibration_service')
async def test_tilt_reading_converts_fahrenheit_to_celsius(mock_calib, mock_ws):
    """Tilt readings convert F→C immediately."""
    # Mock calibration to pass through
    mock_calib.calibrate_reading = AsyncMock(return_value=(1.050, 20.0))

    # Tilt reading in Fahrenheit
    reading = TiltReading(
        id="tilt-red",
        color="RED",
        mac="AA:BB:CC:DD:EE:FF",
        sg=1.050,
        temp_f=68.0,  # 68°F = 20°C
        rssi=-60
    )

    await handle_tilt_reading(reading)

    # Verify calibration was called with Celsius
    args = mock_calib.calibrate_reading.call_args[0]
    temp_c = args[3]  # Fourth argument is temperature

    # 68°F should be 20°C
    assert abs(temp_c - 20.0) < 0.1, f"Expected 20°C, got {temp_c}"
```

**Step 2: Run test to verify current behavior (may fail)**

Run: `pytest tests/test_tilt_temp_conversion.py -v`
Expected: FAIL if conversion not implemented

**Step 3: Update handle_tilt_reading to convert F→C**

File: `backend/main.py` (replace lines 62-65 with conversion)

```python
    # Convert Tilt's Fahrenheit to Celsius immediately
    temp_raw_c = (reading.temp_f - 32) * 5.0 / 9.0

    # Apply calibration in Celsius
    sg_calibrated, temp_calibrated_c = await calibration_service.calibrate_reading(
        session, reading.id, reading.sg, temp_raw_c
    )
```

**Step 4: Update temperature validation range to Celsius**

File: `backend/main.py` (replace lines 77-81)

```python
    elif not (0.0 <= temp_calibrated_c <= 100.0):
        status = "invalid"
        logging.warning(
            f"Outlier temperature detected: {temp_calibrated_c:.1f}°C (valid: 0-100) for device {reading.id}"
        )
```

**Step 5: Update Reading storage to use Celsius**

File: `backend/main.py` (replace lines 117-118)

```python
                temp_raw=temp_raw_c,
                temp_calibrated=temp_calibrated_c,
```

**Step 6: Update WebSocket broadcast to use Celsius**

File: `backend/main.py` (replace lines 136-137)

```python
            "temp": temp_calibrated_c,
            "temp_raw": temp_raw_c,
```

**Step 7: Run test to verify conversion works**

Run: `pytest tests/test_tilt_temp_conversion.py -v`
Expected: PASS

**Step 8: Commit**

```bash
git add backend/main.py tests/test_tilt_temp_conversion.py
git commit -m "feat: convert Tilt temperatures F→C at boundary

- Convert immediately upon reading reception
- Update validation range to 0-100°C
- Store and broadcast in Celsius"
```

---

## Task 6: Integrate ML Pipeline into Reading Handler

**Files:**
- Modify: `backend/main.py` (add ML pipeline processing)

**Step 1: Initialize MLPipelineManager at startup**

File: `backend/main.py` (add to global variables section, around line 25)

```python
# Global ML pipeline manager
ml_pipeline_manager: Optional[MLPipelineManager] = None
```

**Step 2: Import MLPipelineManager**

File: `backend/main.py` (add to imports at top)

```python
from backend.ml.pipeline_manager import MLPipelineManager
```

**Step 3: Initialize in lifespan**

File: `backend/main.py` (in `lifespan` function after `init_db()`)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    global ml_pipeline_manager

    # ... existing init_db() call ...

    # Initialize ML pipeline manager
    ml_pipeline_manager = MLPipelineManager()
    logging.info("ML Pipeline Manager initialized")

    # ... rest of startup ...

    yield

    # Cleanup
    ml_pipeline_manager = None
```

**Step 4: Remove smoothing service (replace with ML pipeline)**

File: `backend/main.py` (replace lines 83-101 smoothing section with ML processing)

```python
        # Process through ML pipeline if paired and valid
        sg_filtered = sg_calibrated
        temp_filtered = temp_calibrated_c
        confidence = None
        sg_rate = None
        temp_rate = None
        is_anomaly = False
        anomaly_score = None
        anomaly_reasons = None
        predictions = None

        if tilt.paired and status == "valid":
            # Get or create pipeline for this device
            pipeline = ml_pipeline_manager.get_or_create_pipeline(reading.id)

            # Calculate time since batch start (if batch linked)
            # Fetch batch_id first for time calculation
            device_id = reading.id
            batch_id_for_time = await link_reading_to_batch(session, device_id)
            time_hours = await calculate_time_since_batch_start(session, batch_id_for_time)

            # Process through ML pipeline
            try:
                ml_result = pipeline.process_reading(
                    sg=sg_calibrated,
                    temp=temp_calibrated_c,
                    rssi=reading.rssi,
                    time_hours=time_hours,
                )

                # Extract ML outputs
                if ml_result.get("kalman"):
                    sg_filtered = ml_result["kalman"]["sg_filtered"]
                    temp_filtered = ml_result["kalman"]["temp_filtered"]
                    confidence = ml_result["kalman"]["confidence"]
                    sg_rate = ml_result["kalman"]["sg_rate"]
                    temp_rate = ml_result["kalman"]["temp_rate"]

                # Anomaly detection
                if ml_result.get("anomaly"):
                    anomaly = ml_result["anomaly"]
                    is_anomaly = anomaly["is_anomaly"]
                    anomaly_score = anomaly["anomaly_score"]
                    anomaly_reasons = json.dumps(anomaly["reasons"])

                # Predictions (may be None if not enough history)
                predictions = ml_result.get("predictions")

            except Exception as e:
                logging.error(f"ML pipeline error for {reading.id}: {e}")
                # Fallback: use calibrated values (graceful degradation)
                sg_filtered = sg_calibrated
                temp_filtered = temp_calibrated_c
```

**Step 5: Update Reading storage to include ML outputs**

File: `backend/main.py` (replace Reading creation lines 111-121)

```python
            # Store reading in DB with ML outputs
            db_reading = Reading(
                tilt_id=reading.id,
                device_id=device_id,
                batch_id=batch_id_for_time,
                sg_raw=reading.sg,
                sg_calibrated=sg_calibrated,
                sg_filtered=sg_filtered,
                temp_raw=temp_raw_c,
                temp_calibrated=temp_calibrated_c,
                temp_filtered=temp_filtered,
                rssi=reading.rssi,
                status=status,
                confidence=confidence,
                sg_rate=sg_rate,
                temp_rate=temp_rate,
                is_anomaly=is_anomaly,
                anomaly_score=anomaly_score,
                anomaly_reasons=anomaly_reasons,
            )
```

**Step 6: Update WebSocket broadcast to include ML data**

File: `backend/main.py` (update reading_data dict lines 129-141)

```python
        # Build reading data for WebSocket broadcast
        reading_data = {
            "id": reading.id,
            "color": reading.color,
            "beer_name": tilt.beer_name,
            "original_gravity": tilt.original_gravity,
            "sg": sg_calibrated,
            "sg_raw": reading.sg,
            "sg_filtered": sg_filtered,
            "temp": temp_calibrated_c,
            "temp_raw": temp_raw_c,
            "temp_filtered": temp_filtered,
            "confidence": confidence,
            "is_anomaly": is_anomaly,
            "anomaly_reasons": json.loads(anomaly_reasons) if anomaly_reasons else [],
            "predicted_fg": predictions.get("predicted_fg") if predictions else None,
            "hours_to_complete": predictions.get("hours_to_complete") if predictions else None,
            "rssi": reading.rssi,
            "last_seen": serialize_datetime_to_utc(datetime.now(timezone.utc)),
            "paired": tilt.paired,
        }
```

**Step 7: Add json import**

File: `backend/main.py` (add to imports at top)

```python
import json
```

**Step 8: Run all tests to verify integration**

Run: `pytest -v`
Expected: All tests PASS

**Step 9: Commit**

```bash
git add backend/main.py
git commit -m "feat: integrate ML pipeline into reading handler

- Replace smoothing with Kalman filtering
- Store ML outputs in database
- Broadcast ML data via WebSocket
- Graceful degradation on ML errors"
```

---

## Task 7: Remove Legacy Smoothing Service

**Files:**
- Delete: `backend/services/smoothing.py`
- Modify: `backend/main.py` (remove smoothing imports and config cache)

**Step 1: Remove smoothing service file**

```bash
git rm backend/services/smoothing.py
```

**Step 2: Remove smoothing imports from main.py**

File: `backend/main.py` (remove from imports)

```python
# REMOVE this line:
from backend.services.smoothing import SmoothingService
```

**Step 3: Remove smoothing config cache variables**

File: `backend/main.py` (remove global variables around line 25)

```python
# REMOVE these lines:
smoothing_service = SmoothingService()
_smoothing_config_cache = (False, None)
_smoothing_cache_time = 0.0
```

**Step 4: Run tests to ensure nothing breaks**

Run: `pytest -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add backend/main.py
git commit -m "refactor: remove legacy smoothing service

- Kalman filtering replaces moving average
- Remove smoothing config cache
- Simplify reading handler"
```

---

## Task 8: Integration Testing

**Files:**
- Create: `tests/test_ml_integration_e2e.py`

**Step 1: Write end-to-end integration test**

File: `tests/test_ml_integration_e2e.py`

```python
"""End-to-end ML integration tests."""
import pytest
from unittest.mock import AsyncMock, patch
from backend.main import handle_tilt_reading
from backend.scanner import TiltReading
from backend.database import async_session_factory
from backend.models import Reading, Tilt


@pytest.mark.asyncio
@patch('backend.main.websocket_manager')
async def test_ml_integration_end_to_end(mock_ws):
    """Full ML pipeline integration test."""
    async with async_session_factory() as session:
        # Create paired Tilt
        tilt = Tilt(
            id="tilt-test",
            color="TEST",
            beer_name="Integration Test",
            paired=True
        )
        session.add(tilt)
        await session.commit()

    # Send reading in Fahrenheit
    reading = TiltReading(
        id="tilt-test",
        color="TEST",
        mac="AA:BB:CC:DD:EE:FF",
        sg=1.050,
        temp_f=68.0,  # 20°C
        rssi=-60
    )

    await handle_tilt_reading(reading)

    # Verify reading stored with ML outputs
    async with async_session_factory() as session:
        db_reading = await session.execute(
            text("SELECT * FROM readings WHERE tilt_id = 'tilt-test' ORDER BY id DESC LIMIT 1")
        )
        row = db_reading.fetchone()

        assert row is not None

        # Temperature stored in Celsius
        temp_calibrated = row[7]  # temp_calibrated column
        assert 19.5 <= temp_calibrated <= 20.5

        # ML outputs present
        sg_filtered = row[8]  # sg_filtered column
        temp_filtered = row[9]  # temp_filtered column
        confidence = row[10]  # confidence column

        assert sg_filtered is not None
        assert temp_filtered is not None
        assert confidence is not None
        assert 0.0 <= confidence <= 1.0


@pytest.mark.asyncio
@patch('backend.main.websocket_manager')
async def test_anomaly_detection_in_production(mock_ws):
    """Anomaly detection works in production flow."""
    async with async_session_factory() as session:
        # Create paired Tilt
        tilt = Tilt(
            id="tilt-anomaly",
            color="ANOMALY",
            beer_name="Anomaly Test",
            paired=True
        )
        session.add(tilt)
        await session.commit()

    # Send normal readings
    for i in range(10):
        reading = TiltReading(
            id="tilt-anomaly",
            color="ANOMALY",
            mac="AA:BB:CC:DD:EE:FF",
            sg=1.050 - i * 0.001,  # Normal fermentation
            temp_f=68.0,
            rssi=-60
        )
        await handle_tilt_reading(reading)

    # Send anomalous reading (SG spike)
    anomaly_reading = TiltReading(
        id="tilt-anomaly",
        color="ANOMALY",
        mac="AA:BB:CC:DD:EE:FF",
        sg=1.060,  # Impossible SG increase
        temp_f=68.0,
        rssi=-60
    )
    await handle_tilt_reading(anomaly_reading)

    # Verify anomaly flagged
    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT is_anomaly, anomaly_score FROM readings WHERE tilt_id = 'tilt-anomaly' ORDER BY id DESC LIMIT 1")
        )
        row = result.fetchone()

        is_anomaly = row[0]
        anomaly_score = row[1]

        assert is_anomaly == 1  # SQLite stores bool as int
        assert anomaly_score is not None
        assert anomaly_score > 0.5  # High anomaly score
```

**Step 2: Add missing import**

File: `tests/test_ml_integration_e2e.py` (add to imports)

```python
from sqlalchemy import text
```

**Step 3: Run integration tests**

Run: `pytest tests/test_ml_integration_e2e.py -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add tests/test_ml_integration_e2e.py
git commit -m "test: add end-to-end ML integration tests

- Verify full reading → ML → DB → WebSocket flow
- Test anomaly detection in production
- Validate Celsius storage and ML outputs"
```

---

## Task 9: Update Pydantic Response Schemas

**Files:**
- Modify: `backend/models.py` (add ML fields to ReadingResponse schema)

**Step 1: Find ReadingResponse schema**

File: `backend/models.py` (search for Pydantic schemas, likely after SQLAlchemy models)

**Step 2: Add ML fields to ReadingResponse**

File: `backend/models.py` (add fields to ReadingResponse schema)

```python
class ReadingResponse(BaseModel):
    # ... existing fields ...

    # ML outputs
    sg_filtered: Optional[float] = None
    temp_filtered: Optional[float] = None
    confidence: Optional[float] = None
    sg_rate: Optional[float] = None
    temp_rate: Optional[float] = None
    is_anomaly: Optional[bool] = None
    anomaly_score: Optional[float] = None
    anomaly_reasons: Optional[str] = None

    class Config:
        from_attributes = True
```

**Step 3: Run tests to verify schema changes**

Run: `pytest -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add backend/models.py
git commit -m "feat: add ML fields to ReadingResponse schema

- Expose ML outputs in API responses
- Support anomaly detection data
- Enable frontend ML feature development"
```

---

## Task 10: Documentation and Final Testing

**Files:**
- Update: `CLAUDE.md` (document ML integration)
- Run: Full test suite

**Step 1: Update CLAUDE.md with ML integration notes**

File: `CLAUDE.md` (add section after Temperature Units)

```markdown
### ML Pipeline Integration

**Per-Device Pipelines:** Each device maintains independent ML state via `MLPipelineManager`

**Components:**
- **Kalman Filtering:** Replaces legacy smoothing service, provides optimal state estimation
- **Anomaly Detection:** Flags readings with `is_anomaly` based on fermentation physics
- **Predictions:** Estimates final gravity and completion time after sufficient history

**Data Flow:**
```
Tilt Reading (F) → F→C Conversion → Calibration (C) → ML Pipeline (C) → Store (C) → Broadcast (C)
```

**ML Outputs Stored:**
- `sg_filtered`, `temp_filtered` - Kalman filtered values
- `confidence` - Reading quality (0.0-1.0)
- `sg_rate`, `temp_rate` - Derivatives for trend analysis
- `is_anomaly`, `anomaly_score`, `anomaly_reasons` - Anomaly detection

**Error Handling:** ML failures degrade gracefully to calibrated values, system continues operating.

**Frontend Impact:** All ML data available via WebSocket for UI enhancements.
```

**Step 2: Run full test suite**

Run: `pytest -v`
Expected: All tests PASS

**Step 3: Check test coverage**

Run: `pytest --cov=backend --cov-report=term-missing`
Expected: High coverage on modified files

**Step 4: Run type checking**

Run: `cd frontend && npm run check`
Expected: No type errors

**Step 5: Commit documentation**

```bash
git add CLAUDE.md
git commit -m "docs: document ML pipeline integration

- Explain per-device pipeline architecture
- Document ML outputs and data flow
- Add error handling notes"
```

**Step 6: Final commit with summary**

```bash
git commit --allow-empty -m "feat: ML pipeline integration complete

Summary of changes:
- Added ML output columns to Reading model
- Converted all temperatures from Fahrenheit to Celsius
- Implemented MLPipelineManager for per-device pipelines
- Integrated Kalman filtering, anomaly detection, predictions
- Removed legacy smoothing service
- Added comprehensive test coverage
- Updated documentation

All temperatures now in Celsius throughout the system.
ML provides real-time insights via WebSocket broadcasts."
```

---

## Task 11: Manual Testing on Development Machine

**Files:**
- None (runtime testing)

**Step 1: Start backend server**

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8080
```

**Step 2: Check logs for ML initialization**

Expected log output:
```
INFO: MLPipelineManager initialized with config: MLConfig(...)
```

**Step 3: Monitor database for ML outputs**

```bash
sqlite3 data/fermentation.db "SELECT sg_filtered, temp_filtered, confidence, is_anomaly FROM readings ORDER BY id DESC LIMIT 5"
```

Expected: See ML columns populated for new readings

**Step 4: Test with mock scanner**

```bash
SCANNER_MOCK=true uvicorn backend.main:app --reload
```

Watch for readings with ML processing in logs

**Step 5: Verify WebSocket broadcasts**

Use browser DevTools console:
```javascript
ws = new WebSocket('ws://localhost:8080/ws');
ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

Expected: Messages include `sg_filtered`, `temp_filtered`, `confidence`, etc.

**Step 6: Document manual testing results**

Create file: `docs/testing/ml-integration-manual-tests.md`

```markdown
# ML Integration Manual Testing Results

**Date:** 2025-12-05
**Tester:** [Name]

## Test Results

- [ ] ML pipeline manager initializes on startup
- [ ] Readings processed through ML pipeline
- [ ] ML outputs stored in database
- [ ] WebSocket broadcasts include ML data
- [ ] Anomaly detection triggers correctly
- [ ] Predictions appear after sufficient history
- [ ] Error handling degrades gracefully
- [ ] Performance acceptable (<50ms p99)

## Issues Found

(List any issues discovered)

## Notes

(Additional observations)
```

**Step 7: Commit manual testing results**

```bash
git add docs/testing/ml-integration-manual-tests.md
git commit -m "test: add manual testing checklist for ML integration"
```

---

## Verification Checklist

Before marking complete, verify:

- [ ] All unit tests pass (`pytest -v`)
- [ ] Integration tests pass
- [ ] Database migrations work on fresh DB
- [ ] Temperature conversion F→C verified
- [ ] ML outputs appear in database
- [ ] WebSocket broadcasts include ML data
- [ ] Smoothing service fully removed
- [ ] No import errors for removed smoothing
- [ ] Documentation updated
- [ ] Manual testing on dev machine completed

---

## Next Steps (Separate PRs)

1. **Frontend ML UI:** Display anomaly badges, predictions panel, filtered vs raw charts
2. **MPC Integration:** Connect ML pipeline to temperature controller
3. **Historical Visualization:** ML overlays on batch charts
4. **Advanced Configuration:** Expose ML tuning parameters in settings

---

## References

- Design doc: `docs/plans/2025-12-05-ml-pipeline-integration.md`
- ML pipeline code: `backend/ml/pipeline.py`
- MPC controller: `backend/ml/control/mpc.py`
- Overall roadmap: `docs/plans/2025-11-29-ml-enhancements.md`
