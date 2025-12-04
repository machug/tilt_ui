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

        # Base process noise covariance (scaled by dt in update())
        self.base_Q = np.diag([
            process_noise_sg,      # sg variance
            process_noise_sg / 10, # sg_rate variance
            process_noise_temp,    # temp variance
            process_noise_temp / 10,  # temp_rate variance
        ])
        self.kf.Q = self.base_Q.copy()

        # Base measurement noise covariance (adjusted by RSSI)
        self.base_R = np.diag([measurement_noise_sg, measurement_noise_temp])
        self.kf.R = self.base_R.copy()

        # Initial state covariance (uncertainty)
        self.kf.P = np.diag([1e-4, 1e-6, 1.0, 0.01])

    def _rssi_to_noise_factor(self, rssi: float) -> float:
        """Convert RSSI to measurement noise standard deviation multiplier.

        Strong signal (-40 dBm) = 1x std (trust measurement)
        Weak signal (-90 dBm) = 10x std (distrust measurement)

        Args:
            rssi: Bluetooth signal strength in dBm

        Returns:
            Standard deviation multiplier (1.0 to 10.0)
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

        # Scale process noise with time delta
        # Process noise accumulates over time, so scale by dt
        self.kf.Q = np.diag([
            self.base_Q[0, 0] * dt_hours,  # sg variance scales with time
            self.base_Q[1, 1] * dt_hours,  # sg_rate variance scales with time
            self.base_Q[2, 2] * dt_hours,  # temp variance scales with time
            self.base_Q[3, 3] * dt_hours,  # temp_rate variance scales with time
        ])

        # Adjust measurement noise based on signal quality
        # rssi_factor is a std multiplier, so square it for variance
        rssi_factor = self._rssi_to_noise_factor(rssi)
        self.kf.R = self.base_R * (rssi_factor ** 2)

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
        # Scale factor adjusted to work with typical variance values (1e-6 to 1e-4)
        confidence = 1.0 - np.sqrt(sg_variance) * 100
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
