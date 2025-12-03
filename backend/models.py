import json
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, field_validator, field_serializer
from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def serialize_datetime_to_utc(dt: Optional[datetime]) -> Optional[str]:
    """Serialize datetime to ISO format with 'Z' suffix to indicate UTC.

    This ensures JavaScript Date() correctly interprets timestamps as UTC rather
    than local time, preventing timezone display bugs.

    Handles three cases defensively:
    - None: Returns None (for optional fields)
    - Naive datetime: Assumes UTC (database stores all times in UTC)
    - Timezone-aware non-UTC: Converts to UTC (defensive, should not occur in practice)
    """
    if dt is None:
        return None
    # Ensure datetime is in UTC
    if dt.tzinfo is None:
        # Naive datetime - assume UTC since database stores everything in UTC
        dt = dt.replace(tzinfo=timezone.utc)
    elif dt.tzinfo != timezone.utc:
        # Non-UTC timezone - convert to UTC (defensive, should not happen)
        dt = dt.astimezone(timezone.utc)
    # Format as ISO with 'Z' suffix per RFC 3339
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# SQLAlchemy Models
class Tilt(Base):
    __tablename__ = "tilts"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    color: Mapped[str] = mapped_column(String(20), nullable=False)
    mac: Mapped[Optional[str]] = mapped_column(String(17))
    beer_name: Mapped[str] = mapped_column(String(100), default="Untitled")
    original_gravity: Mapped[Optional[float]] = mapped_column()
    last_seen: Mapped[Optional[datetime]] = mapped_column()
    paired: Mapped[bool] = mapped_column(default=False, server_default=false(), index=True)
    paired_at: Mapped[Optional[datetime]] = mapped_column()

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
    paired: Mapped[bool] = mapped_column(default=False, server_default=false(), index=True)
    paired_at: Mapped[Optional[datetime]] = mapped_column()

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

    # Expanded BeerXML fields
    brewer: Mapped[Optional[str]] = mapped_column(String(100))
    asst_brewer: Mapped[Optional[str]] = mapped_column(String(100))

    # Boil
    boil_size_l: Mapped[Optional[float]] = mapped_column()  # Pre-boil volume (liters)
    boil_time_min: Mapped[Optional[int]] = mapped_column()  # Total boil time

    # Efficiency
    efficiency_percent: Mapped[Optional[float]] = mapped_column()  # Brewhouse efficiency (0-100)

    # Fermentation stages
    primary_age_days: Mapped[Optional[int]] = mapped_column()
    primary_temp_c: Mapped[Optional[float]] = mapped_column()
    secondary_age_days: Mapped[Optional[int]] = mapped_column()
    secondary_temp_c: Mapped[Optional[float]] = mapped_column()
    tertiary_age_days: Mapped[Optional[int]] = mapped_column()
    tertiary_temp_c: Mapped[Optional[float]] = mapped_column()

    # Aging
    age_days: Mapped[Optional[int]] = mapped_column()
    age_temp_c: Mapped[Optional[float]] = mapped_column()

    # Carbonation
    carbonation_vols: Mapped[Optional[float]] = mapped_column()  # CO2 volumes
    forced_carbonation: Mapped[Optional[bool]] = mapped_column()
    priming_sugar_name: Mapped[Optional[str]] = mapped_column(String(50))
    priming_sugar_amount_kg: Mapped[Optional[float]] = mapped_column()

    # Tasting
    taste_notes: Mapped[Optional[str]] = mapped_column(Text)
    taste_rating: Mapped[Optional[float]] = mapped_column()  # BJCP scale (0-50)

    # Dates
    date: Mapped[Optional[str]] = mapped_column(String(50))  # Brew date from BeerXML

    # Metadata
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    style: Mapped[Optional["Style"]] = relationship(back_populates="recipes")
    batches: Mapped[list["Batch"]] = relationship(back_populates="recipe")
    fermentables: Mapped[list["RecipeFermentable"]] = relationship(back_populates="recipe", cascade="all, delete-orphan")
    hops: Mapped[list["RecipeHop"]] = relationship(back_populates="recipe", cascade="all, delete-orphan")
    yeasts: Mapped[list["RecipeYeast"]] = relationship(back_populates="recipe", cascade="all, delete-orphan")
    miscs: Mapped[list["RecipeMisc"]] = relationship(back_populates="recipe", cascade="all, delete-orphan")


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

    # Soft delete timestamp
    deleted_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Relationships
    recipe: Mapped[Optional["Recipe"]] = relationship(back_populates="batches")
    device: Mapped[Optional["Device"]] = relationship()
    readings: Mapped[list["Reading"]] = relationship(back_populates="batch")

    @property
    def is_deleted(self) -> bool:
        """Check if batch is soft-deleted."""
        return self.deleted_at is not None


class RecipeFermentable(Base):
    """Fermentable ingredients (grains, extracts, sugars) in a recipe."""
    __tablename__ = "recipe_fermentables"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    # BeerXML fields
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50))  # Grain, Sugar, Extract, Dry Extract, Adjunct
    amount_kg: Mapped[float] = mapped_column(nullable=False)  # Amount in kilograms
    yield_percent: Mapped[Optional[float]] = mapped_column()  # % yield (0-100)
    color_lovibond: Mapped[Optional[float]] = mapped_column()  # SRM/Lovibond

    # Additional metadata
    origin: Mapped[Optional[str]] = mapped_column(String(50))
    supplier: Mapped[Optional[str]] = mapped_column(String(100))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Advanced BeerXML fields (optional)
    add_after_boil: Mapped[Optional[bool]] = mapped_column(default=False)
    coarse_fine_diff: Mapped[Optional[float]] = mapped_column()  # %
    moisture: Mapped[Optional[float]] = mapped_column()  # %
    diastatic_power: Mapped[Optional[float]] = mapped_column()  # Lintner
    protein: Mapped[Optional[float]] = mapped_column()  # %
    max_in_batch: Mapped[Optional[float]] = mapped_column()  # %
    recommend_mash: Mapped[Optional[bool]] = mapped_column()

    # Relationship
    recipe: Mapped["Recipe"] = relationship(back_populates="fermentables")


class RecipeHop(Base):
    """Hop additions in a recipe."""
    __tablename__ = "recipe_hops"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    # BeerXML fields
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    alpha_percent: Mapped[Optional[float]] = mapped_column()  # AA% (0-100)
    amount_kg: Mapped[float] = mapped_column(nullable=False)  # Amount in kilograms
    use: Mapped[str] = mapped_column(String(20))  # Boil, Dry Hop, Mash, First Wort, Aroma
    time_min: Mapped[Optional[float]] = mapped_column()  # Minutes (0 for dry hop timing, or days)

    # Hop characteristics
    form: Mapped[Optional[str]] = mapped_column(String(20))  # Pellet, Plug, Leaf
    type: Mapped[Optional[str]] = mapped_column(String(20))  # Bittering, Aroma, Both
    origin: Mapped[Optional[str]] = mapped_column(String(50))
    substitutes: Mapped[Optional[str]] = mapped_column(String(200))

    # Advanced BeerXML fields
    beta_percent: Mapped[Optional[float]] = mapped_column()  # Beta acids %
    hsi: Mapped[Optional[float]] = mapped_column()  # Hop Storage Index
    humulene: Mapped[Optional[float]] = mapped_column()  # %
    caryophyllene: Mapped[Optional[float]] = mapped_column()  # %
    cohumulone: Mapped[Optional[float]] = mapped_column()  # %
    myrcene: Mapped[Optional[float]] = mapped_column()  # %

    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Relationship
    recipe: Mapped["Recipe"] = relationship(back_populates="hops")


class RecipeYeast(Base):
    """Yeast strains in a recipe."""
    __tablename__ = "recipe_yeasts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    # BeerXML fields
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    lab: Mapped[Optional[str]] = mapped_column(String(100))
    product_id: Mapped[Optional[str]] = mapped_column(String(50))
    type: Mapped[Optional[str]] = mapped_column(String(20))  # Ale, Lager, Wheat, Wine, Champagne
    form: Mapped[Optional[str]] = mapped_column(String(20))  # Liquid, Dry, Slant, Culture

    # Fermentation characteristics
    attenuation_percent: Mapped[Optional[float]] = mapped_column()  # % (0-100)
    temp_min_c: Mapped[Optional[float]] = mapped_column()  # Celsius
    temp_max_c: Mapped[Optional[float]] = mapped_column()  # Celsius
    flocculation: Mapped[Optional[str]] = mapped_column(String(20))  # Low, Medium, High, Very High

    # Pitching
    amount_l: Mapped[Optional[float]] = mapped_column()  # Liters (if liquid)
    amount_kg: Mapped[Optional[float]] = mapped_column()  # Kg (if dry)
    add_to_secondary: Mapped[Optional[bool]] = mapped_column(default=False)

    # Advanced fields
    best_for: Mapped[Optional[str]] = mapped_column(Text)
    times_cultured: Mapped[Optional[int]] = mapped_column()
    max_reuse: Mapped[Optional[int]] = mapped_column()
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Relationship
    recipe: Mapped["Recipe"] = relationship(back_populates="yeasts")


class RecipeMisc(Base):
    """Misc ingredients (spices, finings, water agents, etc)."""
    __tablename__ = "recipe_miscs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # Spice, Fining, Water Agent, Herb, Flavor, Other
    use: Mapped[str] = mapped_column(String(20), nullable=False)  # Boil, Mash, Primary, Secondary, Bottling
    time_min: Mapped[Optional[float]] = mapped_column()  # Minutes
    amount_kg: Mapped[Optional[float]] = mapped_column()  # Kg or L (check amount_is_weight)
    amount_is_weight: Mapped[Optional[bool]] = mapped_column(default=True)
    use_for: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    recipe: Mapped["Recipe"] = relationship(back_populates="miscs")


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
    paired: Optional[bool] = None

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
    paired: bool = False
    paired_at: Optional[datetime] = None

    @field_serializer('last_seen', 'paired_at')
    def serialize_dt(self, dt: Optional[datetime]) -> Optional[str]:
        return serialize_datetime_to_utc(dt)


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
    paired: bool

    @field_serializer('last_seen')
    def serialize_dt(self, dt: datetime) -> str:
        return serialize_datetime_to_utc(dt)


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

    @field_serializer('timestamp')
    def serialize_dt(self, dt: datetime) -> str:
        return serialize_datetime_to_utc(dt)


class AmbientReadingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    temperature: Optional[float]
    humidity: Optional[float]

    @field_serializer('timestamp')
    def serialize_dt(self, dt: datetime) -> str:
        return serialize_datetime_to_utc(dt)


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

    @field_serializer('timestamp')
    def serialize_dt(self, dt: datetime) -> str:
        return serialize_datetime_to_utc(dt)


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

    @field_serializer('created_at')
    def serialize_dt(self, dt: datetime) -> str:
        return serialize_datetime_to_utc(dt)


class FermentableResponse(BaseModel):
    """Pydantic response model for fermentable ingredients."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: Optional[str] = None
    amount_kg: Optional[float] = None
    yield_percent: Optional[float] = None
    color_lovibond: Optional[float] = None
    origin: Optional[str] = None
    supplier: Optional[str] = None


class HopResponse(BaseModel):
    """Pydantic response model for hop additions."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    alpha_percent: Optional[float] = None
    amount_kg: Optional[float] = None
    use: Optional[str] = None
    time_min: Optional[float] = None
    form: Optional[str] = None
    type: Optional[str] = None


class YeastResponse(BaseModel):
    """Pydantic response model for yeast strains."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    lab: Optional[str] = None
    product_id: Optional[str] = None
    type: Optional[str] = None
    attenuation_percent: Optional[float] = None
    temp_min_c: Optional[float] = None
    temp_max_c: Optional[float] = None
    flocculation: Optional[str] = None


class MiscResponse(BaseModel):
    """Pydantic response model for misc ingredients."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: Optional[str] = None
    use: Optional[str] = None
    time_min: Optional[float] = None
    amount_kg: Optional[float] = None
    amount_is_weight: Optional[bool] = None


class RecipeDetailResponse(BaseModel):
    """Full recipe with all ingredients."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    author: Optional[str] = None
    style_id: Optional[str] = None
    type: Optional[str] = None
    og_target: Optional[float] = None
    fg_target: Optional[float] = None
    ibu_target: Optional[float] = None
    srm_target: Optional[float] = None
    abv_target: Optional[float] = None
    batch_size: Optional[float] = None
    notes: Optional[str] = None
    created_at: datetime
    style: Optional[StyleResponse] = None

    # Ingredient lists
    fermentables: list[FermentableResponse] = []
    hops: list[HopResponse] = []
    yeasts: list[YeastResponse] = []
    miscs: list[MiscResponse] = []

    @field_serializer('created_at')
    def serialize_dt(self, dt: datetime) -> str:
        return serialize_datetime_to_utc(dt)


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
    recipe_id: Optional[int] = None
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
    deleted_at: Optional[datetime] = None
    recipe: Optional[RecipeResponse] = None
    # Temperature control
    heater_entity_id: Optional[str] = None
    temp_target: Optional[float] = None
    temp_hysteresis: Optional[float] = None

    @field_serializer('brew_date', 'start_time', 'end_time', 'created_at', 'deleted_at')
    def serialize_dt(self, dt: Optional[datetime]) -> Optional[str]:
        return serialize_datetime_to_utc(dt)


class BatchProgressResponse(BaseModel):
    """Fermentation progress response."""
    batch_id: int
    recipe_name: Optional[str] = None
    status: str
    targets: dict  # og, fg, attenuation, abv
    measured: dict  # og, current_sg, attenuation, abv
    progress: dict  # percent_complete, sg_remaining, estimated_days_remaining
    temperature: dict  # current, yeast_min, yeast_max, status
