"""Modelos ORM. Importar este paquete registra todas las tablas en Base.metadata."""

from app.models.activity import (
    Activity,
    ActivityStream,
    BestEffort,
    ComputedActivityMetrics,
    Gear,
    Lap,
    PersonalRecord,
    SwimLength,
)
from app.models.athlete import AiReport, AppSetting, AthleteThresholds, Goal, Insight, Race
from app.models.base import Base
from app.models.daily import DailyLoad, DailyMetrics
from app.models.sync import GarminToken, RawDocument, SyncJob, SyncLog, SyncState

__all__ = [
    "Activity",
    "ActivityStream",
    "AiReport",
    "AppSetting",
    "AthleteThresholds",
    "Base",
    "BestEffort",
    "ComputedActivityMetrics",
    "DailyLoad",
    "DailyMetrics",
    "GarminToken",
    "Gear",
    "Goal",
    "Insight",
    "Lap",
    "PersonalRecord",
    "Race",
    "RawDocument",
    "SwimLength",
    "SyncJob",
    "SyncLog",
    "SyncState",
]
