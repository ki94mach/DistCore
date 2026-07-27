"""Pydantic request/response schemas for the web MVP."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from src.optimization.data import OptimizationSettings


class OptimizationSettingsModel(BaseModel):
    coverage_ratio: float = Field(default=1.5, ge=0)
    target_coverage_ratio: float = Field(default=1.5, ge=0)
    sales_window: int = 3
    delivery_lower_bound: float = Field(default=0.9, ge=0)
    delivery_upper_bound: float = Field(default=1.2, ge=0)
    weight_demand: float = Field(default=1.0, ge=0)
    weight_target_units: float = Field(default=2.0, ge=0)
    weight_smoothing: float = Field(default=1.0, ge=0)
    weight_shipment: float = Field(default=1.0, ge=0)

    @field_validator("sales_window")
    @classmethod
    def _validate_sales_window(cls, value: int) -> int:
        if value not in {3, 6}:
            raise ValueError("sales_window must be 3 or 6")
        return value

    @model_validator(mode="after")
    def _validate_bounds(self) -> "OptimizationSettingsModel":
        if self.delivery_lower_bound > self.delivery_upper_bound:
            raise ValueError(
                "delivery_lower_bound must be <= delivery_upper_bound"
            )
        return self

    def to_dataclass(self) -> OptimizationSettings:
        return OptimizationSettings(**self.model_dump())


class RefreshBody(BaseModel):
    snapshot_date: date


class OptimizeBody(BaseModel):
    snapshot_date: date
    solver: str
    settings_preset: Optional[str] = None
    settings: Optional[OptimizationSettingsModel] = None
    solver_options: Optional[dict[str, dict[str, Any]]] = None
    include_export_variables: bool = False

    @model_validator(mode="after")
    def _reject_dual_settings(self) -> "OptimizeBody":
        if self.settings is not None and self.settings_preset is not None:
            raise ValueError("Specify either settings or settings_preset, not both")
        return self


class JobAccepted(BaseModel):
    job_id: str
    kind: str
    status: str = "queued"


class JobProgress(BaseModel):
    current: int
    total: int
    pipeline: str
    pipeline_name: str
    percent: int
    message: str


class JobStatus(BaseModel):
    job_id: str
    kind: str
    status: str
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    request: dict[str, Any]
    error: Optional[str] = None
    message: Optional[str] = None
    progress: Optional[JobProgress] = None
    result: Optional[dict[str, Any]] = None


class HealthResponse(BaseModel):
    status: str
    database: Optional[dict[str, Any]] = None
