"""ML Pipeline Manager for per-device pipeline instances."""

import logging
from typing import Optional
from .pipeline import MLPipeline
from .config import MLConfig

logger = logging.getLogger(__name__)


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
        logger.info(f"MLPipelineManager initialized with config: {self.config}")

    def get_or_create_pipeline(self, device_id: str) -> MLPipeline:
        """Get existing pipeline or create new one for device.

        Args:
            device_id: Unique device identifier

        Returns:
            MLPipeline instance for this device
        """
        if device_id not in self.pipelines:
            logger.info(f"Creating new ML pipeline for device: {device_id}")
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
            logger.info(f"Resetting ML pipeline for device: {device_id}")
            self.pipelines[device_id].reset(initial_sg, initial_temp)

    def remove_pipeline(self, device_id: str):
        """Remove pipeline for device (cleanup).

        Args:
            device_id: Unique device identifier
        """
        if device_id in self.pipelines:
            logger.info(f"Removing ML pipeline for device: {device_id}")
            del self.pipelines[device_id]

    def get_pipeline_count(self) -> int:
        """Get count of active pipelines."""
        return len(self.pipelines)
