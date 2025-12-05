# ML Pipeline Integration Design

**Date:** 2025-12-05
**Author:** Claude Code
**Status:** Design Complete, Ready for Implementation

## Overview

Integrate the ML pipeline (Kalman filtering, anomaly detection, fermentation predictions) into the production reading handler to provide real-time ML-enhanced fermentation monitoring.

**Key Decision:** Replace existing simple smoothing with Kalman filtering and add full ML capabilities in one integration.

## Goals

1. **Better noise reduction** via Kalman filtering (replaces simple moving average smoothing)
2. **Anomaly detection** for early problem identification (stuck fermentation, sensor issues)
3. **Fermentation predictions** (predicted final gravity, estimated completion time)
4. **Foundation for MPC** temperature control (thermal history tracked for future use)

## Non-Goals (Deferred)

- Full frontend UI for predictions (just pass data via WebSocket, UI in separate PR)
- MPC temperature control integration (separate task)
- Advanced ML configuration tuning (use sensible defaults)
- Historical data backfilling with ML (forward-only, new readings get ML processing)

## Architecture

### Component Structure

```
MLPipelineManager (new)
├── Manages dict of {device_id: MLPipeline}
├── Lifecycle: create on startup, cleanup on shutdown
├── API: get_or_create_pipeline(device_id)
└── Auto-cleanup: remove pipelines for inactive devices

MLPipeline (existing, complete from PR #61)
├── Kalman filter (per-device state)
├── Anomaly detector (per-device history)
├── Curve fitter (fermentation predictions)
└── MPC controller (thermal model, not used in this integration)
```

### Data Flow

```
Tilt BLE Reading (°F)
    ↓
Convert F→C immediately
    ↓
Calibration (°C)
    ↓
Outlier Check (°C)
    ↓
ML Pipeline (°C)
    ├── Kalman Filter → filtered values, confidence
    ├── Anomaly Detector → anomaly flag, reasons
    └── Curve Fitter → predictions (if enough history)
    ↓
Store in DB (°C)
    ↓
WebSocket Broadcast (°C)
    ↓
Frontend converts to user preference (°C or °F)
```

## Temperature Unit Standardization

**Core Principle:** Celsius everywhere except Tilt BLE boundary.

### Conversion Points

1. **Tilt BLE → App:** Convert F→C immediately upon reading reception
2. **App Internal:** All processing, storage, and ML in Celsius
3. **App → Frontend:** Send Celsius in WebSocket/API
4. **Frontend Display:** Convert to user preference (stored in system settings)

### Database Migration

Convert all existing temperature data from Fahrenheit to Celsius:

**Affected tables:**
- `readings.temp_raw` (F → C)
- `readings.temp_calibrated` (F → C)
- `calibration_points` where `type='temp'` (both raw_value and actual_value)

**Migration SQL:**
```sql
UPDATE readings
SET
    temp_raw = (temp_raw - 32) * 5.0 / 9.0,
    temp_calibrated = (temp_calibrated - 32) * 5.0 / 9.0
WHERE temp_raw IS NOT NULL OR temp_calibrated IS NOT NULL;

UPDATE calibration_points
SET
    raw_value = (raw_value - 32) * 5.0 / 9.0,
    actual_value = (actual_value - 32) * 5.0 / 9.0
WHERE type = 'temp';
```

**Validation ranges updated:**
- Old: 32-212°F (freezing to boiling)
- New: 0-100°C (freezing to boiling)

### Code Changes for Temperature Units

**Reading Handler (`backend/main.py`):**
```python
async def handle_tilt_reading(reading: TiltReading):
    # Convert Tilt's Fahrenheit to Celsius immediately
    temp_raw_c = (reading.temp_f - 32) * 5 / 9

    # Calibration in Celsius
    sg_calibrated, temp_calibrated_c = await calibration_service.calibrate_reading(
        session, reading.id, reading.sg, temp_raw_c
    )

    # Outlier check in Celsius
    if not (0.0 <= temp_calibrated_c <= 100.0):
        status = "invalid"

    # ML pipeline in Celsius
    ml_result = pipeline.process_reading(
        sg=sg_calibrated,
        temp=temp_calibrated_c,  # Celsius
        rssi=reading.rssi,
        time_hours=time_hours
    )

    # Store in DB in Celsius
    db_reading = Reading(
        temp_raw=temp_raw_c,
        temp_calibrated=temp_calibrated_c,
        temp_filtered=ml_result["kalman"]["temp_filtered"],  # Celsius
    )
```

**Calibration Service (`backend/services/calibration.py`):**
- Update to expect/return Celsius
- Calibration points stored in Celsius after migration

**Frontend:**
- Receives Celsius from WebSocket
- Converts to user preference using existing conversion utilities
- System settings already has temperature unit preference

## Database Schema Changes

### New Columns for Reading Model

```python
class Reading(Base):
    # ... existing columns ...

    # ML outputs - Kalman filtered values (Celsius)
    sg_filtered: Mapped[Optional[float]] = mapped_column()
    temp_filtered: Mapped[Optional[float]] = mapped_column()

    # ML outputs - Confidence and rates
    confidence: Mapped[Optional[float]] = mapped_column()  # 0.0-1.0, reading quality
    sg_rate: Mapped[Optional[float]] = mapped_column()     # d(SG)/dt in points/hour
    temp_rate: Mapped[Optional[float]] = mapped_column()   # d(temp)/dt in °C/hour

    # ML outputs - Anomaly detection
    is_anomaly: Mapped[Optional[bool]] = mapped_column(default=False)
    anomaly_score: Mapped[Optional[float]] = mapped_column()  # 0.0-1.0
    anomaly_reasons: Mapped[Optional[str]] = mapped_column(Text)  # JSON array
```

### Migration Strategy

1. Add new columns with `nullable=True`
2. Convert existing temps F→C (one-time migration)
3. Only new readings get ML values (existing readings have NULL)
4. Frontend handles NULL gracefully (show "N/A" or hide ML features)

**Rationale:** Avoids backfilling historical ML data. ML processing is forward-looking only.

## Integration Points

### 1. Startup (backend/main.py)

```python
# Global instance
ml_pipeline_manager: Optional[MLPipelineManager] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global ml_pipeline_manager

    # After init_db()
    ml_pipeline_manager = MLPipelineManager()
    logging.info("ML Pipeline Manager initialized")

    # ... existing startup code ...

    yield

    # Cleanup
    ml_pipeline_manager = None
```

### 2. Reading Handler (backend/main.py)

**Replace smoothing section with ML pipeline:**

```python
# OLD (remove):
if smoothing_enabled and smoothing_samples and smoothing_samples > 1:
    sg_calibrated, temp_calibrated = await smoothing_service.smooth_reading(...)

# NEW:
if tilt.paired and status == "valid":
    # Convert temp to Celsius for ML pipeline
    temp_c = temp_calibrated_c  # Already converted from Tilt F

    # Get or create pipeline for this device
    pipeline = ml_pipeline_manager.get_or_create_pipeline(reading.id)

    # Calculate time since batch start (if batch linked)
    time_hours = 0.0
    if batch_id:
        time_hours = await calculate_time_since_batch_start(session, batch_id)

    # Process through ML pipeline
    try:
        ml_result = pipeline.process_reading(
            sg=sg_calibrated,
            temp=temp_c,
            rssi=reading.rssi,
            time_hours=time_hours,
        )

        # Extract ML outputs
        sg_filtered = ml_result["kalman"]["sg_filtered"]
        temp_filtered = ml_result["kalman"]["temp_filtered"]  # Celsius
        confidence = ml_result["kalman"]["confidence"]
        sg_rate = ml_result["kalman"]["sg_rate"]
        temp_rate = ml_result["kalman"]["temp_rate"]

        # Anomaly detection
        anomaly = ml_result.get("anomaly")
        is_anomaly = anomaly["is_anomaly"] if anomaly else False
        anomaly_score = anomaly["anomaly_score"] if anomaly else None
        anomaly_reasons = json.dumps(anomaly["reasons"]) if anomaly else None

        # Predictions (may be None if not enough history)
        predictions = ml_result.get("predictions")

    except Exception as e:
        logging.error(f"ML pipeline error for {reading.id}: {e}")
        # Graceful fallback: use calibrated values
        sg_filtered = sg_calibrated
        temp_filtered = temp_c
        confidence = None
        sg_rate = None
        temp_rate = None
        is_anomaly = False
        anomaly_score = None
        anomaly_reasons = None
        predictions = None
```

**Store ML outputs in database:**

```python
db_reading = Reading(
    tilt_id=reading.id,
    device_id=device_id,
    batch_id=batch_id,
    sg_raw=reading.sg,
    sg_calibrated=sg_calibrated,
    sg_filtered=sg_filtered,
    temp_raw=temp_raw_c,          # Celsius
    temp_calibrated=temp_c,       # Celsius
    temp_filtered=temp_filtered,  # Celsius
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

### 3. WebSocket Broadcasting

**Update reading_data dict to include ML outputs:**

```python
reading_data = {
    "id": reading.id,
    "color": reading.color,
    "beer_name": tilt.beer_name,
    "original_gravity": tilt.original_gravity,

    # Raw/calibrated (Celsius)
    "sg": sg_calibrated,
    "sg_raw": reading.sg,
    "temp": temp_c,          # Celsius
    "temp_raw": temp_raw_c,  # Celsius

    # ML outputs (Celsius for temps)
    "sg_filtered": sg_filtered,
    "temp_filtered": temp_filtered,  # Celsius
    "confidence": confidence,
    "is_anomaly": is_anomaly,
    "anomaly_reasons": json.loads(anomaly_reasons) if anomaly_reasons else [],

    # Predictions (optional)
    "predicted_fg": predictions.get("predicted_fg") if predictions else None,
    "hours_to_complete": predictions.get("hours_to_complete") if predictions else None,

    "rssi": reading.rssi,
    "last_seen": serialize_datetime_to_utc(datetime.now(timezone.utc)),
    "paired": tilt.paired,
}
```

**Frontend impact:**
- Receives all temps in Celsius
- Converts to user preference using existing utilities
- Can display anomaly badge (red dot if `is_anomaly`)
- Can show predictions panel (if predictions available)

### 4. Cleanup: Remove Smoothing

**Files to modify:**
- Delete `backend/services/smoothing.py` (entire file)
- Remove smoothing imports from `backend/main.py`
- Remove smoothing config variables (`_smoothing_config_cache`, etc.)
- Database migration to remove smoothing config settings (optional)

**Justification:** Kalman filter is scientifically superior to moving average smoothing. No need for both.

## MLPipelineManager Implementation

**File:** `backend/ml/pipeline_manager.py` (new)

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

**Design rationale:**
- Minimal API surface (YAGNI)
- Lazy instantiation (pipelines created on first reading)
- Simple dict-based storage (adequate for <10 devices)
- Logging for observability

## Helper Functions

### Calculate Time Since Batch Start

**File:** `backend/main.py` (add helper function)

```python
async def calculate_time_since_batch_start(session, batch_id: int) -> float:
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

**Used by:** Reading handler to provide time context for ML pipeline (predictions and MPC need time series).

## Error Handling & Edge Cases

### ML Pipeline Failure

**Strategy:** Graceful degradation

```python
try:
    ml_result = pipeline.process_reading(...)
except Exception as e:
    logging.error(f"ML pipeline error for {reading.id}: {e}")
    # Fallback: use calibrated values as filtered values
    sg_filtered = sg_calibrated
    temp_filtered = temp_c
    confidence = None
    is_anomaly = False
    # Reading still gets stored, system continues operating
```

**Rationale:** ML is enhancement, not critical path. If ML fails, degrade to basic functionality.

### Edge Cases

**1. First Reading (Cold Start):**
- Kalman filter needs 2-3 readings to converge
- Confidence will be low (0.3-0.5) initially
- Predictions will be NULL (not enough history)
- **Behavior:** Valid but low confidence, no anomalies flagged

**2. Batch Reset:**
- When user starts new batch, call `ml_pipeline_manager.reset_pipeline(device_id, new_og, new_temp)`
- Clears history, reinitializes Kalman state
- **Integration point:** Batch creation/start endpoint

**3. Device Unpaired:**
- Stop processing through ML (already gated by `if tilt.paired`)
- Keep pipeline in memory (might be re-paired)
- **Cleanup:** Optional background task to remove pipelines for devices inactive >24 hours

**4. Stale Devices:**
- Optional: Periodic cleanup task removes pipelines for devices not seen recently
- **Deferred:** Not critical for initial integration, can add later if memory becomes concern

**5. Invalid Readings:**
- Outlier check happens BEFORE ML pipeline
- Invalid readings never reach ML (status="invalid")
- **Behavior:** ML only processes physically plausible readings

## Testing Strategy

### Unit Tests

**File:** `tests/test_ml_pipeline_manager.py` (new)

```python
"""Tests for ML Pipeline Manager."""

import pytest
from backend.ml.pipeline_manager import MLPipelineManager
from backend.ml.config import MLConfig


class TestMLPipelineManager:
    """Tests for pipeline manager."""

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

        # Pipeline should be reset (Kalman state cleared)
        assert len(pipeline.sg_history) == 0

    def test_remove_pipeline(self):
        """Manager removes pipeline for device."""
        manager = MLPipelineManager()
        manager.get_or_create_pipeline("device-1")

        assert manager.get_pipeline_count() == 1

        manager.remove_pipeline("device-1")

        assert manager.get_pipeline_count() == 0
```

### Integration Tests

**File:** `tests/test_integration_ml.py` (new)

```python
"""Integration tests for ML pipeline with reading handler."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_ml_integration_with_reading_handler():
    """Reading handler integrates with ML pipeline end-to-end."""
    # This test will verify:
    # 1. Reading flows through ML pipeline
    # 2. ML outputs stored in database
    # 3. WebSocket broadcast includes ML data
    # 4. Temperature conversion F→C works correctly

    # Implementation deferred to implementation phase
    pass


@pytest.mark.asyncio
async def test_anomaly_detection_integration():
    """Anomaly detection works in production flow."""
    # Send readings with intentional anomaly (SG spike)
    # Verify is_anomaly flag set in database
    # Verify anomaly reasons populated

    # Implementation deferred to implementation phase
    pass


@pytest.mark.asyncio
async def test_predictions_appear_after_history():
    """Predictions available after sufficient history."""
    # Send 20+ readings over simulated time
    # Verify predictions appear in ML result
    # Verify predictions stored in reading_data (WebSocket)

    # Implementation deferred to implementation phase
    pass
```

### Regression Testing

**Verify existing functionality:**
1. All existing tests must pass
2. Outlier detection still works
3. Calibration still applied
4. Batch linking still works
5. WebSocket broadcasting still works

### Performance Testing

**Benchmark reading handler latency:**
- Measure p50, p95, p99 latency with ML enabled
- Target: <50ms p99 (reading handler is not critical path for 15s BLE intervals)
- ML pipeline is fast (Kalman filter is O(1), anomaly detection is O(n) where n=history length <1000)

### Manual Testing

**Deploy to test Raspberry Pi:**
1. Start fermentation with paired Tilt
2. Monitor database for ML outputs (sg_filtered, confidence, is_anomaly)
3. Verify WebSocket broadcasts include ML data
4. Check frontend receives ML data (inspect browser console)
5. Test batch reset (start new batch, verify pipeline resets)

## Migration Checklist

**Database migrations (in order):**
1. ✅ Add ML output columns to Reading model (nullable)
2. ✅ Convert all temps F→C (readings, calibration_points)
3. ✅ Remove smoothing config settings (optional cleanup)

**Code changes:**
1. ✅ Create `MLPipelineManager` class
2. ✅ Update `handle_tilt_reading()` to use ML pipeline
3. ✅ Remove smoothing service
4. ✅ Update calibration service for Celsius
5. ✅ Add helper function for time calculation
6. ✅ Update WebSocket broadcast format
7. ✅ Update temp validation ranges (0-100°C)

**Testing:**
1. ✅ Unit tests for MLPipelineManager
2. ✅ Integration tests for full flow
3. ✅ Verify all existing tests pass
4. ✅ Manual testing on Raspberry Pi

## Rollout Plan

**Phase 1: Development & Testing**
1. Implement on feature branch
2. Unit tests pass
3. Integration tests pass
4. Manual testing on development machine

**Phase 2: Raspberry Pi Deployment**
1. Deploy to production Raspberry Pi
2. Monitor logs for ML pipeline errors
3. Verify ML outputs in database
4. Check WebSocket broadcasts

**Phase 3: Frontend Enhancement (Separate PR)**
1. Add anomaly badge to dashboard
2. Add predictions panel
3. Add chart toggle (raw vs filtered)
4. Full ML insights UI

## Success Criteria

**Must have (this PR):**
- ✅ ML pipeline integrated with reading handler
- ✅ Kalman filtering active for all paired devices
- ✅ ML outputs stored in database
- ✅ WebSocket broadcasts include ML data
- ✅ All temperatures in Celsius (database, ML, internal processing)
- ✅ Smoothing service removed
- ✅ All existing tests pass
- ✅ No performance regression

**Nice to have (future PRs):**
- Frontend UI for ML insights
- MPC temperature control integration
- Advanced ML configuration tuning
- Historical data visualization with ML overlays

## Open Questions

None - design is complete and validated.

## References

- PR #61: ML pipeline implementation (Kalman, anomaly, predictions, MPC)
- PR #65: MPC dual-mode extension (Celsius conversion)
- `docs/plans/2025-11-29-ml-enhancements.md`: Overall ML roadmap
- `CLAUDE.md`: Temperature unit standards (Celsius internal, Fahrenheit at Tilt boundary)
