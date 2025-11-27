from datetime import datetime
from typing import Optional

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
    last_seen: Mapped[Optional[datetime]] = mapped_column()

    readings: Mapped[list["Reading"]] = relationship(back_populates="tilt", cascade="all, delete-orphan")
    calibration_points: Mapped[list["CalibrationPoint"]] = relationship(
        back_populates="tilt", cascade="all, delete-orphan"
    )


class Reading(Base):
    __tablename__ = "readings"
    __table_args__ = (
        Index("ix_readings_tilt_timestamp", "tilt_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tilt_id: Mapped[str] = mapped_column(ForeignKey("tilts.id"), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(default=datetime.utcnow, index=True)
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


class TiltResponse(TiltBase):
    id: str
    mac: Optional[str]
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


class ConfigResponse(BaseModel):
    temp_units: str = "C"
    sg_units: str = "sg"
    local_logging_enabled: bool = True
    local_interval_minutes: int = 15
    min_rssi: int = -100
    smoothing_enabled: bool = False
    smoothing_samples: int = 5
    id_by_mac: bool = False
