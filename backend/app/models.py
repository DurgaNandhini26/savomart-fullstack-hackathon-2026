"""Data model.

Spatial strategy: every located row carries lat/lng plus H3 cell ids
(res 9 ≈ 0.1 km², res 8 ≈ 0.74 km²). H3 gives us a uniform, non-overlapping
grid that doubles as (a) the spatial index for radius / area queries,
(b) the "pick grid cells" selection unit on the map, and (c) the unit used to
split catchments into fair, non-overlapping survey work.
"""
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------- people

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(30))  # bd_manager | bd_exec | survey_manager | survey_exec
    phone: Mapped[str | None] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------------------------------------------------------------- reference / public data

class DataSnapshot(Base):
    """One row per ingestion run so every report can say exactly what data it used."""
    __tablename__ = "data_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50))  # osm_pois | osm_roads | osm_buildings | stores | pincodes | baseline
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    source_timestamp: Mapped[str | None] = mapped_column(String(40))  # e.g. Overpass osm_base timestamp
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)


class Store(Base):
    __tablename__ = "stores"
    id: Mapped[int] = mapped_column(primary_key=True)
    store_code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(Text)
    zone: Mapped[str | None] = mapped_column(String(10))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    h3_9: Mapped[str] = mapped_column(String(16), index=True)
    is_operational: Mapped[bool] = mapped_column(Boolean, default=True)


class Poi(Base):
    __tablename__ = "pois"
    id: Mapped[int] = mapped_column(primary_key=True)
    osm_ref: Mapped[str] = mapped_column(String(30), unique=True)  # n123 / w456
    category: Mapped[str] = mapped_column(String(30), index=True)  # our taxonomy (see ingest)
    tag: Mapped[str] = mapped_column(String(60))                   # raw key=value
    name: Mapped[str | None] = mapped_column(String(200))
    brand: Mapped[str | None] = mapped_column(String(100))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    h3_9: Mapped[str] = mapped_column(String(16), index=True)
    h3_8: Mapped[str] = mapped_column(String(16), index=True)


class Road(Base):
    __tablename__ = "roads"
    id: Mapped[int] = mapped_column(primary_key=True)
    osm_id: Mapped[int] = mapped_column(Integer, index=True)
    seg: Mapped[int] = mapped_column(Integer, default=0)  # long ways are split per H3 cell
    name: Mapped[str | None] = mapped_column(String(200))
    highway: Mapped[str] = mapped_column(String(30))
    length_m: Mapped[float] = mapped_column(Float)
    coords: Mapped[list] = mapped_column(JSON)  # [[lng, lat], ...]
    mid_lat: Mapped[float] = mapped_column(Float)
    mid_lng: Mapped[float] = mapped_column(Float)
    h3_9: Mapped[str] = mapped_column(String(16), index=True)
    h3_8: Mapped[str] = mapped_column(String(16), index=True)


class CellStat(Base):
    """Pre-aggregated public-data features per H3 res-9 cell (the city baseline)."""
    __tablename__ = "cell_stats"
    h3_9: Mapped[str] = mapped_column(String(16), primary_key=True)
    h3_8: Mapped[str] = mapped_column(String(16), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    buildings: Mapped[int] = mapped_column(Integer, default=0)
    res_buildings: Mapped[int] = mapped_column(Integer, default=0)  # house/apartments/residential/...
    apartments: Mapped[int] = mapped_column(Integer, default=0)
    commercial_buildings: Mapped[int] = mapped_column(Integer, default=0)
    road_m: Mapped[float] = mapped_column(Float, default=0)
    res_road_m: Mapped[float] = mapped_column(Float, default=0)
    major_road_m: Mapped[float] = mapped_column(Float, default=0)
    est_population: Mapped[float] = mapped_column(Float, default=0)
    est_households: Mapped[float] = mapped_column(Float, default=0)
    poi_counts: Mapped[dict] = mapped_column(JSON, default=dict)


class BaselineMeta(Base):
    """City-wide reference distributions (sorted samples) used to turn raw metrics into percentiles."""
    __tablename__ = "baseline_meta"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict | list] = mapped_column(JSON)


class OpportunityCell(Base):
    """City-wide opportunity score per H3 res-8 cell (bonus: opportunity map)."""
    __tablename__ = "opportunity_cells"
    h3_8: Mapped[str] = mapped_column(String(16), primary_key=True)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    score: Mapped[float] = mapped_column(Float)
    pillars: Mapped[dict] = mapped_column(JSON)
    features: Mapped[dict] = mapped_column(JSON)
    locality: Mapped[str | None] = mapped_column(String(120))


class Place(Base):
    """Searchable localities and pincodes."""
    __tablename__ = "places"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)  # locality | pincode
    name: Mapped[str] = mapped_column(String(200), index=True)
    pincode: Mapped[str | None] = mapped_column(String(10), index=True)
    place_type: Mapped[str | None] = mapped_column(String(30))  # suburb / neighbourhood / ...
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    geometry: Mapped[dict | None] = mapped_column(JSON)  # GeoJSON polygon if known
    source: Mapped[str] = mapped_column(String(40))


# ---------------------------------------------------------------- background jobs

class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))  # area_analysis | property_evaluation | catchment_rollup
    ref_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|succeeded|failed
    progress: Mapped[float] = mapped_column(Float, default=0)
    steps: Mapped[list] = mapped_column(JSON, default=list)  # [{key,label,status,detail}]
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


# ---------------------------------------------------------------- M1: area intelligence

class AreaReport(Base):
    __tablename__ = "area_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    selection_type: Mapped[str] = mapped_column(String(20))  # pincode | locality | cells
    selection_input: Mapped[str | None] = mapped_column(String(200))
    cells: Mapped[list] = mapped_column(JSON)  # H3 res-8 cells that make up the area
    center_lat: Mapped[float] = mapped_column(Float)
    center_lng: Mapped[float] = mapped_column(Float)
    area_km2: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"))
    score: Mapped[float | None] = mapped_column(Float)
    band: Mapped[str | None] = mapped_column(String(30))
    confidence: Mapped[str | None] = mapped_column(String(20))
    pillars: Mapped[dict | None] = mapped_column(JSON)
    indicators: Mapped[list | None] = mapped_column(JSON)
    profile: Mapped[dict | None] = mapped_column(JSON)
    hotspots: Mapped[list | None] = mapped_column(JSON)
    narrative: Mapped[dict | None] = mapped_column(JSON)
    data_versions: Mapped[dict | None] = mapped_column(JSON)
    ground_truth: Mapped[dict | None] = mapped_column(JSON)  # catchment roll-up, when available
    error: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    created_by: Mapped[User] = relationship()


# ---------------------------------------------------------------- M2: scouting & properties

class ScoutMission(Base):
    __tablename__ = "scout_missions"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    report_id: Mapped[int | None] = mapped_column(ForeignKey("area_reports.id"))
    hotspot_rank: Mapped[int | None] = mapped_column(Integer)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    radius_m: Mapped[int] = mapped_column(Integer, default=600)
    brief: Mapped[str | None] = mapped_column(Text)
    assignee_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | in_progress | done | cancelled
    due_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    assignee: Mapped[User] = relationship(foreign_keys=[assignee_id])
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id])
    report: Mapped[AreaReport | None] = relationship()


class Property(Base):
    __tablename__ = "properties"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    client_uuid: Mapped[str | None] = mapped_column(String(40), unique=True)  # idempotent offline submits
    mission_id: Mapped[int | None] = mapped_column(ForeignKey("scout_missions.id"))
    submitted_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    h3_9: Mapped[str] = mapped_column(String(16), index=True)
    gps_accuracy_m: Mapped[float | None] = mapped_column(Float)
    device_lat: Mapped[float | None] = mapped_column(Float)
    device_lng: Mapped[float | None] = mapped_column(Float)
    address: Mapped[str | None] = mapped_column(Text)
    locality: Mapped[str | None] = mapped_column(String(120))
    pincode: Mapped[str | None] = mapped_column(String(10))

    property_type: Mapped[str] = mapped_column(String(40))
    carpet_area_sqft: Mapped[float | None] = mapped_column(Float)
    frontage_ft: Mapped[float | None] = mapped_column(Float)
    floor: Mapped[str | None] = mapped_column(String(20))  # ground | first | ground+first | basement
    ceiling_height_ft: Mapped[float | None] = mapped_column(Float)
    rent_monthly: Mapped[float | None] = mapped_column(Float)
    rent_negotiable: Mapped[bool] = mapped_column(Boolean, default=False)
    deposit_months: Mapped[float | None] = mapped_column(Float)
    lease_years: Mapped[float | None] = mapped_column(Float)
    parking_2w: Mapped[int | None] = mapped_column(Integer)
    parking_4w: Mapped[int | None] = mapped_column(Integer)
    road_facing: Mapped[str | None] = mapped_column(String(20))  # main_road | secondary | interior
    road_width_ft: Mapped[float | None] = mapped_column(Float)
    visibility: Mapped[int | None] = mapped_column(Integer)  # 1..5
    power_kw: Mapped[float | None] = mapped_column(Float)
    truck_access: Mapped[bool | None] = mapped_column(Boolean)
    available_from: Mapped[date | None] = mapped_column(Date)
    owner_name: Mapped[str | None] = mapped_column(String(120))
    owner_phone: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)
    data_quality: Mapped[list] = mapped_column(JSON, default=list)  # warnings raised at capture

    stage: Mapped[str] = mapped_column(String(30), default="submitted", index=True)
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("properties.id"))
    latest_score: Mapped[float | None] = mapped_column(Float)
    latest_recommendation: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    submitted_by: Mapped[User] = relationship(foreign_keys=[submitted_by_id])
    mission: Mapped[ScoutMission | None] = relationship()
    photos: Mapped[list["PropertyPhoto"]] = relationship(back_populates="property", cascade="all, delete-orphan")


class PropertyPhoto(Base):
    __tablename__ = "property_photos"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(300))
    caption: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    property: Mapped[Property] = relationship(back_populates="photos")


class PropertyEvaluation(Base):
    __tablename__ = "property_evaluations"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    trigger: Mapped[str] = mapped_column(String(30))  # onboarding | catchment_study | details_updated | manual
    status: Mapped[str] = mapped_column(String(20), default="queued")
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"))
    score: Mapped[float | None] = mapped_column(Float)
    recommendation: Mapped[str | None] = mapped_column(String(20))  # go | consider | no_go
    pillars: Mapped[dict | None] = mapped_column(JSON)
    facts: Mapped[dict | None] = mapped_column(JSON)
    insights: Mapped[list | None] = mapped_column(JSON)
    risks: Mapped[list | None] = mapped_column(JSON)
    narrative: Mapped[dict | None] = mapped_column(JSON)
    catchment_study_id: Mapped[int | None] = mapped_column(ForeignKey("catchment_studies.id"))
    data_versions: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("property_id", "version"),)


class PropertyEvent(Base):
    """Immutable audit trail: who did what to a property, and why."""
    __tablename__ = "property_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(40))
    from_stage: Mapped[str | None] = mapped_column(String(30))
    to_stage: Mapped[str | None] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    actor: Mapped[User | None] = relationship()


# ---------------------------------------------------------------- M3: catchment studies

class CatchmentStudy(Base):
    __tablename__ = "catchment_studies"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    target_type: Mapped[str] = mapped_column(String(20))  # property | area
    property_id: Mapped[int | None] = mapped_column(ForeignKey("properties.id"))
    report_id: Mapped[int | None] = mapped_column(ForeignKey("area_reports.id"))
    title: Mapped[str] = mapped_column(String(200))
    center_lat: Mapped[float] = mapped_column(Float)
    center_lng: Mapped[float] = mapped_column(Float)
    radius_m: Mapped[int | None] = mapped_column(Integer)
    cells: Mapped[list] = mapped_column(JSON)  # H3 res-9 cells to survey (after reuse subtraction)
    requested_cells: Mapped[list] = mapped_column(JSON)  # full catchment as requested
    reused: Mapped[list] = mapped_column(JSON, default=list)  # [{study_id, cells, coverage}]
    status: Mapped[str] = mapped_column(String(20), default="requested")
    # requested -> planned -> in_progress -> completed | reused (fully satisfied by earlier data) | cancelled
    priority: Mapped[str] = mapped_column(String(10), default="normal")
    due_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    insights: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    requested_by: Mapped[User] = relationship()
    property: Mapped[Property | None] = relationship()
    report: Mapped[AreaReport | None] = relationship()
    work_units: Mapped[list["WorkUnit"]] = relationship(back_populates="study", cascade="all, delete-orphan")


class WorkUnit(Base):
    __tablename__ = "work_units"
    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("catchment_studies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    color: Mapped[str] = mapped_column(String(10))
    cells: Mapped[list] = mapped_column(JSON)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="unassigned")  # unassigned|assigned|in_progress|done
    lane_count: Mapped[int] = mapped_column(Integer, default=0)
    lane_m: Mapped[float] = mapped_column(Float, default=0)
    due_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    study: Mapped[CatchmentStudy] = relationship(back_populates="work_units")
    assignee: Mapped[User | None] = relationship()
    lanes: Mapped[list["SurveyLane"]] = relationship(back_populates="work_unit")


class SurveyLane(Base):
    __tablename__ = "survey_lanes"
    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("catchment_studies.id", ondelete="CASCADE"), index=True)
    work_unit_id: Mapped[int | None] = mapped_column(ForeignKey("work_units.id", ondelete="SET NULL"), index=True)
    road_id: Mapped[int | None] = mapped_column(ForeignKey("roads.id"))
    name: Mapped[str | None] = mapped_column(String(200))
    highway: Mapped[str] = mapped_column(String(30))
    coords: Mapped[list] = mapped_column(JSON)
    length_m: Mapped[float] = mapped_column(Float)
    h3_9: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | done | inaccessible

    work_unit: Mapped[WorkUnit | None] = relationship(back_populates="lanes")


class LaneObservation(Base):
    __tablename__ = "lane_observations"
    id: Mapped[int] = mapped_column(primary_key=True)
    lane_id: Mapped[int] = mapped_column(ForeignKey("survey_lanes.id", ondelete="CASCADE"), index=True)
    client_uuid: Mapped[str] = mapped_column(String(40), unique=True)  # offline outbox idempotency key
    surveyor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    data: Mapped[dict] = mapped_column(JSON)
    captured_at: Mapped[datetime] = mapped_column(DateTime)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    surveyor: Mapped[User] = relationship()


# ---------------------------------------------------------------- notifications

class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(200))
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


Index("ix_poi_cat_h3_8", Poi.category, Poi.h3_8)
