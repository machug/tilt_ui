import json
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, false
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
    paired: Mapped[bool] = mapped_column(default=False, server_default=false())

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
    paired: Mapped[bool] = mapped_column(default=False, server_default=false())

    # Relationships
    readings: Mapped[list["Reading"]] = relationship(back_populates="device", cascade="all, delete-orphan")

class Reading(Base):
    __tablename__ = "readings"
    __table_args__ = (
        Index("ix_readings_tilt_timestamp", "tilt_id", "timestamp"),
        Index("ix_readings_device_timestamp", "device_id", "timestamp"),
        Index("ix_readings_batch_timestamp", "batch_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Legacy Tilt FK - nullable for non-Tilt devices
    tilt_id: Mapped[Optional[str]] = mapped_column(ForeignKey("tilts.id"), nullable=True, index=True)
    # Universal device FK - for all device types including Tilt
    device_id: Mapped[Optional[str]] = mapped_column(ForeignKey("devices.id"), nullable=True, index=True)
    # Batch FK - for tracking readings per batch
    batch_id: Mapped[Optional[int]] = mapped_column(ForeignKey("batches.id"), nullable=True, index=True)
    device_type: Mapped[str] = mapped_column(String(20), default="tilt")
    timestamp: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), index=True)

    # Gravity readings
    sg_raw: Mapped[Optional[float]] = mapped_column()
    sg_calibrated: Mapped[Optional[float]] = mapped_column()

    # Temperature readings
    temp_raw: Mapped[Optional[float]] = mapped_column()
    temp_calibrated: Mapped[Optional[float]] = mapped_column()

    # Signal/battery
    rssi: Mapped[Optional[int]] = mapped_column()
    battery_voltage: Mapped[Optional[float]] = mapped_column()
    battery_percent: Mapped[Optional[int]] = mapped_column()

    # iSpindel-specific
    angle: Mapped[Optional[float]] = mapped_column()

    # Processing metadata
    source_protocol: Mapped[str] = mapped_column(String(20), default="ble")
    status: Mapped[str] = mapped_column(String(20), default="valid")
    is_pre_filtered: Mapped[bool] = mapped_column(default=False)

    # Relationships
    tilt: Mapped[Optional["Tilt"]] = relationship(back_populates="readings")
    device: Mapped[Optional["Device"]] = relationship(back_populates="readings")
    batch: Mapped[Optional["Batch"]] = relationship(back_populates="readings")


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
    batch_id: Mapped[Optional[int]] = mapped_column()  # Batch that triggered this control event
    action: Mapped[str] = mapped_column(String(20))  # heat_on, heat_off, cool_on, cool_off
    wort_temp: Mapped[Optional[float]] = mapped_column()
    ambient_temp: Mapped[Optional[float]] = mapped_column()
    target_temp: Mapped[Optional[float]] = mapped_column()


class Config(Base):
    __tablename__ = "config"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text)  # JSON encoded


class Style(Base):
    """BJCP Style Guidelines reference data."""
    __tablename__ = "styles"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # e.g., "bjcp-2021-18b"
    guide: Mapped[str] = mapped_column(String(50), nullable=False)  # "BJCP 2021"
    category_number: Mapped[str] = mapped_column(String(10), nullable=False)  # "18"
    style_letter: Mapped[Optional[str]] = mapped_column(String(5))  # "B"
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # "American Pale Ale"
    category: Mapped[str] = mapped_column(String(100), nullable=False)  # "Pale American Ale"
    type: Mapped[Optional[str]] = mapped_column(String(20))  # "Ale", "Lager", etc.
    og_min: Mapped[Optional[float]] = mapped_column()
    og_max: Mapped[Optional[float]] = mapped_column()
    fg_min: Mapped[Optional[float]] = mapped_column()
    fg_max: Mapped[Optional[float]] = mapped_column()
    ibu_min: Mapped[Optional[float]] = mapped_column()
    ibu_max: Mapped[Optional[float]] = mapped_column()
    srm_min: Mapped[Optional[float]] = mapped_column()
    srm_max: Mapped[Optional[float]] = mapped_column()
    abv_min: Mapped[Optional[float]] = mapped_column()
    abv_max: Mapped[Optional[float]] = mapped_column()
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    # Relationships
    recipes: Mapped[list["Recipe"]] = relationship(back_populates="style")


class Recipe(Base):
    """Recipes imported from BeerXML or created manually."""
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    author: Mapped[Optional[str]] = mapped_column(String(100))
    style_id: Mapped[Optional[str]] = mapped_column(ForeignKey("styles.id"))
    type: Mapped[Optional[str]] = mapped_column(String(50))  # "All Grain", "Extract", etc.

    # Gravity targets
    og_target: Mapped[Optional[float]] = mapped_column()
    fg_target: Mapped[Optional[float]] = mapped_column()

    # Yeast info (extracted from BeerXML)
    yeast_name: Mapped[Optional[str]] = mapped_column(String(100))
    yeast_lab: Mapped[Optional[str]] = mapped_column(String(100))
    yeast_product_id: Mapped[Optional[str]] = mapped_column(String(50))
    yeast_temp_min: Mapped[Optional[float]] = mapped_column()  # Celsius
    yeast_temp_max: Mapped[Optional[float]] = mapped_column()  # Celsius
    yeast_attenuation: Mapped[Optional[float]] = mapped_column()  # Percent

    # Other targets
    ibu_target: Mapped[Optional[float]] = mapped_column()
    srm_target: Mapped[Optional[float]] = mapped_column()
    abv_target: Mapped[Optional[float]] = mapped_column()
    batch_size: Mapped[Optional[float]] = mapped_column()  # Liters

    # Raw BeerXML for future re-parsing
    beerxml_content: Mapped[Optional[str]] = mapped_column(Text)

    # Metadata
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    style: Mapped[Optional["Style"]] = relationship(back_populates="recipes")
    batches: Mapped[list["Batch"]] = relationship(back_populates="recipe")


class Batch(Base):
    """Instances of brewing a recipe on a device."""
    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[Optional[int]] = mapped_column(ForeignKey("recipes.id"))
    device_id: Mapped[Optional[str]] = mapped_column(ForeignKey("devices.id"))

    # Batch identification
    batch_number: Mapped[Optional[int]] = mapped_column()
    name: Mapped[Optional[str]] = mapped_column(String(200))  # Optional override

    # Status tracking
    status: Mapped[str] = mapped_column(String(20), default="planning")  # planning, fermenting, conditioning, completed, archived

    # Timeline
    brew_date: Mapped[Optional[datetime]] = mapped_column()
    start_time: Mapped[Optional[datetime]] = mapped_column()  # Fermentation start
    end_time: Mapped[Optional[datetime]] = mapped_column()  # Fermentation end

    # Measured values
    measured_og: Mapped[Optional[float]] = mapped_column()
    measured_fg: Mapped[Optional[float]] = mapped_column()
    measured_abv: Mapped[Optional[float]] = mapped_column()
    measured_attenuation: Mapped[Optional[float]] = mapped_column()

    # Temperature control - per-batch heater assignment
    heater_entity_id: Mapped[Optional[str]] = mapped_column(String(100))
    temp_target: Mapped[Optional[float]] = mapped_column()  # Override target temp for this batch
    temp_hysteresis: Mapped[Optional[float]] = mapped_column()  # Override hysteresis for this batch

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    recipe: Mapped[Optional["Recipe"]] = relationship(back_populates="batches")
    device: Mapped[Optional["Device"]] = relationship()
    readings: Mapped[list["Reading"]] = relationship(back_populates="batch")


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

    def is_field_set(self, field_name: str) -> bool:
        """Check if a field was explicitly provided in the request."""
        return field_name in self.model_fields_set


class TiltResponse(TiltBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    mac: Optional[str]
    original_gravity: Optional[float]
    last_seen: Optional[datetime]


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
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    sg_raw: Optional[float]
    sg_calibrated: Optional[float]
    temp_raw: Optional[float]
    temp_calibrated: Optional[float]
    rssi: Optional[int]
    status: Optional[str] = None  # 'valid', 'invalid', 'uncalibrated', 'incomplete'


class AmbientReadingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    temperature: Optional[float]
    humidity: Optional[float]


class ControlEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    tilt_id: Optional[str]
    batch_id: Optional[int]
    action: str
    wort_temp: Optional[float]
    ambient_temp: Optional[float]
    target_temp: Optional[float]


class CalibrationPointCreate(BaseModel):
    type: str  # 'sg' or 'temp'
    raw_value: float
    actual_value: float


class CalibrationPointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    raw_value: float
    actual_value: float


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


# Recipe & Batch Pydantic Schemas
class StyleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    guide: str
    category_number: str
    style_letter: Optional[str] = None
    name: str
    category: str
    type: Optional[str] = None
    og_min: Optional[float] = None
    og_max: Optional[float] = None
    fg_min: Optional[float] = None
    fg_max: Optional[float] = None
    ibu_min: Optional[float] = None
    ibu_max: Optional[float] = None
    srm_min: Optional[float] = None
    srm_max: Optional[float] = None
    abv_min: Optional[float] = None
    abv_max: Optional[float] = None
    description: Optional[str] = None


class RecipeCreate(BaseModel):
    name: str
    author: Optional[str] = None
    style_id: Optional[str] = None
    type: Optional[str] = None
    og_target: Optional[float] = None
    fg_target: Optional[float] = None
    yeast_name: Optional[str] = None
    yeast_temp_min: Optional[float] = None
    yeast_temp_max: Optional[float] = None
    yeast_attenuation: Optional[float] = None
    ibu_target: Optional[float] = None
    abv_target: Optional[float] = None
    batch_size: Optional[float] = None
    notes: Optional[str] = None


class RecipeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    author: Optional[str] = None
    style_id: Optional[str] = None
    type: Optional[str] = None
    og_target: Optional[float] = None
    fg_target: Optional[float] = None
    yeast_name: Optional[str] = None
    yeast_lab: Optional[str] = None
    yeast_product_id: Optional[str] = None
    yeast_temp_min: Optional[float] = None
    yeast_temp_max: Optional[float] = None
    yeast_attenuation: Optional[float] = None
    ibu_target: Optional[float] = None
    srm_target: Optional[float] = None
    abv_target: Optional[float] = None
    batch_size: Optional[float] = None
    notes: Optional[str] = None
    created_at: datetime
    style: Optional[StyleResponse] = None


class BatchCreate(BaseModel):
    recipe_id: Optional[int] = None
    device_id: Optional[str] = None
    name: Optional[str] = None
    status: str = "planning"
    brew_date: Optional[datetime] = None
    measured_og: Optional[float] = None
    notes: Optional[str] = None
    # Temperature control
    heater_entity_id: Optional[str] = None
    temp_target: Optional[float] = None
    temp_hysteresis: Optional[float] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        valid = ["planning", "fermenting", "conditioning", "completed", "archived"]
        if v not in valid:
            raise ValueError(f"status must be one of: {', '.join(valid)}")
        return v

    @field_validator("heater_entity_id")
    @classmethod
    def validate_heater_entity(cls, v: Optional[str]) -> Optional[str]:
        if v and not v.startswith(("switch.", "input_boolean.")):
            raise ValueError("heater_entity_id must be a valid HA entity (e.g., switch.heater_1 or input_boolean.heater_1)")
        return v

    @field_validator("temp_target")
    @classmethod
    def validate_temp_target(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            if v < 32.0 or v > 212.0:  # Fahrenheit range (0-100°C)
                raise ValueError("temp_target must be between 32°F and 212°F (0-100°C)")
        return v

    @field_validator("temp_hysteresis")
    @classmethod
    def validate_temp_hysteresis(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            if v < 0.1 or v > 10.0:
                raise ValueError("temp_hysteresis must be between 0.1 and 10.0 degrees")
        return v


class BatchUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    device_id: Optional[str] = None
    brew_date: Optional[datetime] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    measured_og: Optional[float] = None
    measured_fg: Optional[float] = None
    notes: Optional[str] = None
    # Temperature control
    heater_entity_id: Optional[str] = None
    temp_target: Optional[float] = None
    temp_hysteresis: Optional[float] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        valid = ["planning", "fermenting", "conditioning", "completed", "archived"]
        if v not in valid:
            raise ValueError(f"status must be one of: {', '.join(valid)}")
        return v

    @field_validator("heater_entity_id")
    @classmethod
    def validate_heater_entity(cls, v: Optional[str]) -> Optional[str]:
        if v and not v.startswith(("switch.", "input_boolean.")):
            raise ValueError("heater_entity_id must be a valid HA entity (e.g., switch.heater_1 or input_boolean.heater_1)")
        return v

    @field_validator("temp_target")
    @classmethod
    def validate_temp_target(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            if v < 32.0 or v > 212.0:  # Fahrenheit range (0-100°C)
                raise ValueError("temp_target must be between 32°F and 212°F (0-100°C)")
        return v

    @field_validator("temp_hysteresis")
    @classmethod
    def validate_temp_hysteresis(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            if v < 0.1 or v > 10.0:
                raise ValueError("temp_hysteresis must be between 0.1 and 10.0 degrees")
        return v


class BatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    recipe_id: Optional[int] = None
    device_id: Optional[str] = None
    batch_number: Optional[int] = None
    name: Optional[str] = None
    status: str
    brew_date: Optional[datetime] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    measured_og: Optional[float] = None
    measured_fg: Optional[float] = None
    measured_abv: Optional[float] = None
    measured_attenuation: Optional[float] = None
    notes: Optional[str] = None
    created_at: datetime
    recipe: Optional[RecipeResponse] = None
    # Temperature control
    heater_entity_id: Optional[str] = None
    temp_target: Optional[float] = None
    temp_hysteresis: Optional[float] = None


class BatchProgressResponse(BaseModel):
    """Fermentation progress response."""
    batch_id: int
    recipe_name: Optional[str] = None
    status: str
    targets: dict  # og, fg, attenuation, abv
    measured: dict  # og, current_sg, attenuation, abv
    progress: dict  # percent_complete, sg_remaining, estimated_days_remaining
    temperature: dict  # current, yeast_min, yeast_max, status
