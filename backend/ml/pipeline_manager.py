"""ML pipeline manager for multi-device/multi-batch state isolation.

Manages separate MLPipeline instances per device/batch to prevent
state contamination when processing readings from multiple sources.
"""

from typing import Optional
from backend.ml.config import MLConfig
from backend.ml.pipeline import MLPipeline


class MLPipelineManager:
    """Manages separate ML pipelines for each device/batch.

    Each device (identified by device_id) gets its own MLPipeline instance
    with isolated state (Kalman filter, anomaly history, predictions, MPC).

    This prevents cross-contamination when processing readings from:
    - Multiple Tilt devices
    - Multiple fermentation batches
    - Different time series that should not be mixed
    """

    def __init__(self, config: Optional[MLConfig] = None):
        """Initialize the pipeline manager.

        Args:
            config: ML configuration (shared across all pipelines)
        """
        self.config = config or MLConfig()
        self._pipelines: dict[str, MLPipeline] = {}

    def get_pipeline(self, device_id: str) -> MLPipeline:
        """Get or create a pipeline for a device.

        Args:
            device_id: Unique identifier for device/batch

        Returns:
            MLPipeline instance for this device
        """
        if device_id not in self._pipelines:
            self._pipelines[device_id] = MLPipeline(config=self.config)
        return self._pipelines[device_id]

    def process_reading(
        self,
        device_id: str,
        sg: float,
        temp: float,
        rssi: float,
        time_hours: float,
        ambient_temp: Optional[float] = None,
        heater_on: Optional[bool] = None,
        target_temp: Optional[float] = None,
    ) -> dict:
        """Process a reading through the appropriate device pipeline.

        Args:
            device_id: Unique identifier for device/batch
            sg: Raw specific gravity reading
            temp: Raw temperature reading (°F)
            rssi: Bluetooth signal strength (dBm)
            time_hours: Time since fermentation start (hours)
            ambient_temp: Ambient/room temperature (°F)
            heater_on: Current heater state (for MPC learning)
            target_temp: Target temperature (°F, for MPC control)

        Returns:
            Dictionary with results from each component
        """
        pipeline = self.get_pipeline(device_id)
        return pipeline.process_reading(
            sg=sg,
            temp=temp,
            rssi=rssi,
            time_hours=time_hours,
            ambient_temp=ambient_temp,
            heater_on=heater_on,
            target_temp=target_temp,
        )

    def reset_pipeline(
        self,
        device_id: str,
        initial_sg: float = 1.050,
        initial_temp: float = 68.0,
    ) -> None:
        """Reset a device's pipeline state for new batch.

        Args:
            device_id: Unique identifier for device/batch
            initial_sg: Starting specific gravity
            initial_temp: Starting temperature (°F)
        """
        if device_id in self._pipelines:
            self._pipelines[device_id].reset(
                initial_sg=initial_sg,
                initial_temp=initial_temp,
            )

    def remove_pipeline(self, device_id: str) -> None:
        """Remove a device's pipeline (e.g., when batch completes).

        Args:
            device_id: Unique identifier for device/batch
        """
        self._pipelines.pop(device_id, None)

    def list_active_pipelines(self) -> list[str]:
        """Get list of active device IDs with pipelines.

        Returns:
            List of device_ids with active pipelines
        """
        return list(self._pipelines.keys())
