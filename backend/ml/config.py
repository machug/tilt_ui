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
