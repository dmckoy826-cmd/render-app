"""Pydantic request schemas. Responses are built as dicts in routers (they add media URLs)."""
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class AssignmentIn(BaseModel):
    target_kind: str = Field(pattern="^(layer|block|part)$")
    target_name: str
    finish_id: Optional[int] = None  # None removes the assignment
    scale_multiplier: float = Field(default=1.0, gt=0, allow_inf_nan=False)


class AutoMatchApplyIn(BaseModel):
    threshold: float = 0.45
    overwrite: bool = False


class PresetRuleIn(BaseModel):
    match: str = Field(default="contains", pattern="^(contains|starts_with|exact|regex)$")
    pattern: str
    finish_id: int
    target_kind: str = Field(default="layer", pattern="^(layer|block|part)$")
    target_property: str = Field(default="name", pattern="^(name|identity)$")
    scale_multiplier: float = Field(default=1.0, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def identity_is_exact_part(self):
        if self.target_property == "identity" and (self.target_kind != "part" or self.match != "exact"):
            raise ValueError("Geometry identity rules must match an exact part ID")
        return self


class PresetIn(BaseModel):
    name: str
    description: str = ""
    rules: list[PresetRuleIn] = []


class PresetApplyIn(BaseModel):
    overwrite: bool = True


class PresetFromModelIn(BaseModel):
    model_id: int
    name: str
    description: str = ""


class RenderSettings(BaseModel):
    width: int = Field(default=1920, ge=1, le=8192)
    height: int = Field(default=1080, ge=1, le=8192)
    quality: str = Field(default="standard", pattern="^(draft|standard|high|current)$")
    camera: str = Field(default="iso", pattern="^(iso|front|top)$")
    camera_pose: Optional[dict] = None
    named_view: Optional[str] = None
    keep_file_view: bool = False
    use_file_vray_settings: bool = False
    batch: Optional[dict] = None


class RenderJobIn(BaseModel):
    model_id: int
    settings: RenderSettings = RenderSettings()


class AgentProgressIn(BaseModel):
    progress: int = 0
    stage: str = ""


class AgentFailIn(BaseModel):
    error: str
