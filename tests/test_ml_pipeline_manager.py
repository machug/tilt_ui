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
