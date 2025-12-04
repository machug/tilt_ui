"""ML pipeline orchestrator.

Coordinates all ML components (Kalman filtering, anomaly detection,
predictions, and MPC control) to provide a unified interface for
processing fermentation readings.

The pipeline:
1. Filters raw readings through Kalman filter
2. Checks for anomalies
3. Fits fermentation curve and predicts completion (if enough history)
4. Computes optimal temperature control action (if MPC enabled)
"""

from typing import Optional
from backend.ml.config import MLConfig
from backend.ml.sensor_fusion.kalman import TiltKalmanFilter
from backend.ml.anomaly.detector import FermentationAnomalyDetector
from backend.ml.predictions.curve_fitter import FermentationCurveFitter
from backend.ml.control.mpc import MPCTemperatureController


class MLPipeline:
    """Orchestrates all ML components for fermentation monitoring.

    The pipeline maintains state across readings and coordinates:
    - Sensor fusion (Kalman filtering)
    - Anomaly detection
    - Fermentation predictions (curve fitting)
    - Temperature control (MPC)

    Each component can be individually enabled/disabled via MLConfig.
    """

    def __init__(self, config: Optional[MLConfig] = None):
        """Initialize the ML pipeline.

        Args:
            config: ML configuration (uses defaults if not provided)
        """
        self.config = config or MLConfig()

        # Initialize components based on config
        if self.config.enable_kalman_filter:
            self.kalman_filter = TiltKalmanFilter(
                process_noise_sg=self.config.kalman_process_noise_sg,
                process_noise_temp=self.config.kalman_process_noise_temp,
                measurement_noise_sg=self.config.kalman_measurement_noise_sg,
                measurement_noise_temp=self.config.kalman_measurement_noise_temp,
            )
        else:
            self.kalman_filter = None

        if self.config.enable_anomaly_detection:
            self.anomaly_detector = FermentationAnomalyDetector(
                contamination=self.config.anomaly_contamination,
                min_history=self.config.anomaly_min_history,
                sg_rate_threshold=self.config.anomaly_sg_rate_threshold,
            )
        else:
            self.anomaly_detector = None

        if self.config.enable_predictions:
            self.curve_fitter = FermentationCurveFitter(
                min_readings=self.config.prediction_min_readings,
                completion_threshold=self.config.prediction_completion_threshold,
            )
        else:
            self.curve_fitter = None

        if self.config.enable_mpc:
            self.mpc_controller = MPCTemperatureController(
                horizon_hours=self.config.mpc_horizon_hours,
                max_temp_rate=self.config.mpc_max_temp_rate,
                dt_hours=self.config.mpc_dt_hours,
            )
        else:
            self.mpc_controller = None

        # History for predictions and MPC
        self.sg_history: list[float] = []
        self.temp_history: list[float] = []
        self.time_history: list[float] = []
        self.heater_history: list[bool] = []
        self.ambient_history: list[float] = []

    def process_reading(
        self,
        sg: float,
        temp: float,
        rssi: float,
        time_hours: float,
        ambient_temp: Optional[float] = None,
        heater_on: Optional[bool] = None,
        target_temp: Optional[float] = None,
    ) -> dict:
        """Process a fermentation reading through the ML pipeline.

        Args:
            sg: Raw specific gravity reading
            temp: Raw temperature reading (°F)
            rssi: Bluetooth signal strength (dBm)
            time_hours: Time since fermentation start (hours)
            ambient_temp: Ambient/room temperature (°F)
            heater_on: Current heater state (for MPC learning)
            target_temp: Target temperature (°F, for MPC control)

        Returns:
            Dictionary with results from each component:
            - kalman: Filtered readings and rates
            - anomaly: Anomaly detection results
            - predictions: Fermentation predictions (if enough history)
            - mpc: Temperature control action (if MPC enabled)
        """
        result = {}

        # Calculate time delta for Kalman filter
        if self.time_history:
            dt_hours = time_hours - self.time_history[-1]
            dt_hours = max(dt_hours, 1 / 60)  # At least 1 minute
        else:
            dt_hours = 1 / 60  # Default: 1 minute

        # Stage 1: Kalman filtering
        if self.kalman_filter:
            kalman_result = self.kalman_filter.update(
                sg=sg,
                temp=temp,
                rssi=rssi,
                dt_hours=dt_hours,
            )
            result["kalman"] = kalman_result

            # Use filtered values for downstream components
            filtered_sg = kalman_result["sg_filtered"]
            filtered_temp = kalman_result["temp_filtered"]
        else:
            # No filtering, use raw values
            filtered_sg = sg
            filtered_temp = temp
            result["kalman"] = None

        # Stage 2: Anomaly detection
        if self.anomaly_detector:
            anomaly_result = self.anomaly_detector.check_reading(
                sg=filtered_sg,
                time_hours=time_hours,
            )
            result["anomaly"] = anomaly_result
        else:
            result["anomaly"] = None

        # Add to history
        self.sg_history.append(filtered_sg)
        self.temp_history.append(filtered_temp)
        self.time_history.append(time_hours)

        if heater_on is not None:
            self.heater_history.append(heater_on)

        if ambient_temp is not None:
            self.ambient_history.append(ambient_temp)

        # Stage 3: Predictions (curve fitting)
        if self.curve_fitter and len(self.sg_history) >= self.config.prediction_min_readings:
            prediction_result = self.curve_fitter.fit(
                times=self.time_history,
                sgs=self.sg_history,
            )
            result["predictions"] = prediction_result
        else:
            result["predictions"] = None

        # Stage 4: MPC temperature control
        if self.mpc_controller and target_temp is not None and ambient_temp is not None:
            # Learn thermal model if we have enough history
            # CRITICAL: All histories must be same length for MPC learning
            min_history_len = min(
                len(self.temp_history),
                len(self.heater_history),
                len(self.ambient_history),
            )
            if min_history_len >= 3:
                self.mpc_controller.learn_thermal_model(
                    temp_history=self.temp_history[-min_history_len:],
                    time_history=self.time_history[-min_history_len:],
                    heater_history=self.heater_history[-min_history_len:],
                    ambient_history=self.ambient_history[-min_history_len:],
                )

            # Compute control action
            mpc_result = self.mpc_controller.compute_action(
                current_temp=filtered_temp,
                target_temp=target_temp,
                ambient_temp=ambient_temp,
                heater_currently_on=heater_on,
            )
            result["mpc"] = mpc_result
        else:
            result["mpc"] = None

        return result

    def reset(self, initial_sg: float = 1.050, initial_temp: float = 68.0) -> None:
        """Reset pipeline state for a new fermentation batch.

        Args:
            initial_sg: Starting specific gravity
            initial_temp: Starting temperature (°F)
        """
        # Reset Kalman filter
        if self.kalman_filter:
            self.kalman_filter.reset(sg=initial_sg, temp=initial_temp)

        # Reset anomaly detector
        if self.anomaly_detector:
            self.anomaly_detector.reset()

        # Clear history
        self.sg_history = []
        self.temp_history = []
        self.time_history = []
        self.heater_history = []
        self.ambient_history = []

        # Note: curve_fitter and mpc_controller don't maintain state,
        # so no reset needed
