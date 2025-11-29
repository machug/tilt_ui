import json
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, field_validator
from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


# SQLAlchemy Models
class Tilt(Base):
    __tablename__ = "tilts"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    color: Mapped[str] = mapped_column(String(20), nullable=False)
    mac: Mapped[Optional[str]] = mapped_column(String(17))
    beer_name: Mapped[str] = mapped_column(String(100), default="Untitled")
    original_gravity: Mapped[Optional[float]] = mapped_column()
    last_seen: Mapped[Optional[datetime]] = mapped_column()

    readings: Mapped[list["Reading"]] = relationship(back_populates="tilt", cascade="all, delete-orphan")
    calibration_points: Mapped[list["CalibrationPoint"]] = relationship(
        back_populates="tilt", cascade="all, delete-orphan"
    )


class Device(Base):
    """Universal hydrometer device registry."""
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    device_type: Mapped[str] = mapped_column(String(20), nullable=False, default="tilt")
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(100))

    # Current assignment
    beer_name: Mapped[Optional[str]] = mapped_column(String(100))
    original_gravity: Mapped[Optional[float]] = mapped_column()

    # Native units (for display and conversion)
    native_gravity_unit: Mapped[str] = mapped_column(String(10), default="sg")
    native_temp_unit: Mapped[str] = mapped_column(String(5), default="f")

    # Calibration - stored as JSON string, use properties for access
    calibration_type: Mapped[str] = mapped_column(String(20), default="none")
    _calibration_data: Mapped[Optional[str]] = mapped_column("calibration_data", Text)

    @property
    def calibration_data(self) -> Optional[dict[str, Any]]:
        """Get calibration data as dict."""
        if self._calibration_data:
            return json.loads(self._calibration_data)
        return None

    @calibration_data.setter
    def calibration_data(self, value: Optional[dict[str, Any]]) -> None:
        """Set calibration data from dict."""
        if value is not None:
            self._calibration_data = json.dumps(value)
        else:
            self._calibration_data = None

    # Security
    auth_token: Mapped[Optional[str]] = mapped_column(String(100))

    # Status
    last_seen: Mapped[Optional[datetime]] = mapped_column()
    battery_voltage: Mapped[Optional[float]] = mapped_column()
    firmware_version: Mapped[Optional[str]] = mapped_column(String(50))

    # Legacy compatibility (Tilt-specific)
    color: Mapped[Optional[str]] = mapped_column(String(20))
    mac: Mapped[Optional[str]] = mapped_column(String(17))

    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))


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
    temp_raw: Mapped[Optional[float]] = mapped_column()
    temp_calibrated: Mapped[Optional[float]] = mapped_column()
    rssi: Mapped[Optional[int]] = mapped_column()

    tilt: Mapped["Tilt"] = relationship(back_populates="readings")


class CalibrationPoint(Base):
    __tablename__ = "calibration_points"
    __table_args__ = (
        UniqueConstraint("tilt_id", "type", "raw_value", name="uq_calibration_point"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tilt_id: Mapped[str] = mapped_column(ForeignKey("tilts.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(10), nullable=False)  # 'sg' or 'temp'
    raw_value: Mapped[float] = mapped_column(nullable=False)
    actual_value: Mapped[float] = mapped_column(nullable=False)

    tilt: Mapped["Tilt"] = relationship(back_populates="calibration_points")


class AmbientReading(Base):
    """Ambient temperature/humidity readings from Home Assistant sensors."""
    __tablename__ = "ambient_readings"
    __table_args__ = (
        Index("ix_ambient_timestamp", "timestamp"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), index=True)
    temperature: Mapped[Optional[float]] = mapped_column()
    humidity: Mapped[Optional[float]] = mapped_column()
    entity_id: Mapped[Optional[str]] = mapped_column(String(100))


class ControlEvent(Base):
    """Temperature control events (heater on/off, cooler on/off)."""
    __tablename__ = "control_events"
    __table_args__ = (
        Index("ix_control_timestamp", "timestamp"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), index=True)
    tilt_id: Mapped[Optional[str]] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(20))  # heat_on, heat_off, cool_on, cool_off
    wort_temp: Mapped[Optional[float]] = mapped_column()
    ambient_temp: Mapped[Optional[float]] = mapped_column()
    target_temp: Mapped[Optional[float]] = mapped_column()


class Config(Base):
    __tablename__ = "config"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text)  # JSON encoded


# Pydantic Schemas
class TiltBase(BaseModel):
    color: str
    beer_name: str = "Untitled"


class TiltCreate(TiltBase):
    id: str
    mac: Optional[str] = None


class TiltUpdate(BaseModel):
    beer_name: Optional[str] = None
    original_gravity: Optional[float] = None

    @field_validator("original_gravity")
    @classmethod
    def validate_og(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.990 or v > 1.200):
            raise ValueError("original_gravity must be between 0.990 and 1.200")
        return v


class TiltResponse(TiltBase):
    id: str
    mac: Optional[str]
    original_gravity: Optional[float]
    last_seen: Optional[datetime]

    class Config:
        from_attributes = True


class TiltReading(BaseModel):
    id: str
    color: str
    sg: float
    sg_raw: float
    temp: float
    temp_raw: float
    rssi: int
    last_seen: datetime
    beer_name: str


class ReadingResponse(BaseModel):
    id: int
    timestamp: datetime
    sg_raw: Optional[float]
    sg_calibrated: Optional[float]
    temp_raw: Optional[float]
    temp_calibrated: Optional[float]
    rssi: Optional[int]

    class Config:
        from_attributes = True


class AmbientReadingResponse(BaseModel):
    id: int
    timestamp: datetime
    temperature: Optional[float]
    humidity: Optional[float]

    class Config:
        from_attributes = True


class ControlEventResponse(BaseModel):
    id: int
    timestamp: datetime
    tilt_id: Optional[str]
    action: str
    wort_temp: Optional[float]
    ambient_temp: Optional[float]
    target_temp: Optional[float]

    class Config:
        from_attributes = True


class CalibrationPointCreate(BaseModel):
    type: str  # 'sg' or 'temp'
    raw_value: float
    actual_value: float


class CalibrationPointResponse(BaseModel):
    id: int
    type: str
    raw_value: float
    actual_value: float

    class Config:
        from_attributes = True


class ConfigUpdate(BaseModel):
    temp_units: Optional[str] = None  # "F" or "C"
    sg_units: Optional[str] = None  # "sg", "plato", "brix"
    local_logging_enabled: Optional[bool] = None
    local_interval_minutes: Optional[int] = None
    min_rssi: Optional[int] = None
    smoothing_enabled: Optional[bool] = None
    smoothing_samples: Optional[int] = None
    id_by_mac: Optional[bool] = None
    # Home Assistant settings
    ha_enabled: Optional[bool] = None
    ha_url: Optional[str] = None
    ha_token: Optional[str] = None
    ha_ambient_temp_entity_id: Optional[str] = None
    ha_ambient_humidity_entity_id: Optional[str] = None
    # Temperature control
    temp_control_enabled: Optional[bool] = None
    temp_target: Optional[float] = None
    temp_hysteresis: Optional[float] = None
    ha_heater_entity_id: Optional[str] = None
    # Weather
    ha_weather_entity_id: Optional[str] = None
    # Alerts
    weather_alerts_enabled: Optional[bool] = None
    alert_temp_threshold: Optional[float] = None

    @field_validator("temp_units")
    @classmethod
    def validate_temp_units(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("F", "C"):
            raise ValueError("temp_units must be 'F' or 'C'")
        return v

    @field_validator("sg_units")
    @classmethod
    def validate_sg_units(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("sg", "plato", "brix"):
            raise ValueError("sg_units must be 'sg', 'plato', or 'brix'")
        return v

    @field_validator("local_interval_minutes")
    @classmethod
    def validate_interval(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 1 or v > 60):
            raise ValueError("local_interval_minutes must be between 1 and 60")
        return v

    @field_validator("min_rssi")
    @classmethod
    def validate_rssi(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < -100 or v > 0):
            raise ValueError("min_rssi must be between -100 and 0")
        return v

    @field_validator("smoothing_samples")
    @classmethod
    def validate_samples(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 1 or v > 20):
            raise ValueError("smoothing_samples must be between 1 and 20")
        return v

    @field_validator("ha_url")
    @classmethod
    def validate_ha_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v and not v.startswith(("http://", "https://")):
            raise ValueError("ha_url must start with http:// or https://")
        return v.rstrip("/") if v else v

    @field_validator("temp_target")
    @classmethod
    def validate_temp_target(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 32 or v > 100):
            raise ValueError("temp_target must be between 32 and 100 (Fahrenheit)")
        return v

    @field_validator("temp_hysteresis")
    @classmethod
    def validate_temp_hysteresis(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.5 or v > 10):
            raise ValueError("temp_hysteresis must be between 0.5 and 10")
        return v

    @field_validator("alert_temp_threshold")
    @classmethod
    def validate_alert_temp_threshold(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 1 or v > 20):
            raise ValueError("alert_temp_threshold must be between 1 and 20")
        return v


class ConfigResponse(BaseModel):
    temp_units: str = "C"
    sg_units: str = "sg"
    local_logging_enabled: bool = True
    local_interval_minutes: int = 15
    min_rssi: int = -100
    smoothing_enabled: bool = False
    smoothing_samples: int = 5
    id_by_mac: bool = False
    # Home Assistant settings
    ha_enabled: bool = False
    ha_url: str = ""
    ha_token: str = ""
    ha_ambient_temp_entity_id: str = ""
    ha_ambient_humidity_entity_id: str = ""
    # Temperature control
    temp_control_enabled: bool = False
    temp_target: float = 68.0
    temp_hysteresis: float = 1.0
    ha_heater_entity_id: str = ""
    # Weather
    ha_weather_entity_id: str = ""
    # Alerts
    weather_alerts_enabled: bool = False
    alert_temp_threshold: float = 5.0
