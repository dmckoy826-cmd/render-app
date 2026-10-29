"""Pydantic request schemas. Responses are built as dicts in routers (they add media URLs)."""
from typing import Optional

from pydantic import BaseModel, Field


class AssignmentIn(BaseModel):
    target_kind: str = Field(pattern="^(layer|block|part)$")
    target_name: str
    finish_id: Optional[int] = None  # None removes the assignment
    scale_multiplier: float = 1.0


class AutoMatchApplyIn(BaseModel):
    threshold: float = 0.45
    overwrite: bool = False


class PresetRuleIn(BaseModel):
    match: str = Field(default="contains", pattern="^(contains|starts_with|exact|regex)$")
    pattern: str
    finish_id: int
    target_kind: str = Field(default="layer", pattern="^(layer|block|part)$")


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
    width: int = 1920
    height: int = 1080
    quality: str = Field(default="standard", pattern="^(draft|standard|high)$")
    camera: str = Field(default="iso", pattern="^(iso|front|top)$")


class RenderJobIn(BaseModel):
    model_id: int
    settings: RenderSettings = RenderSettings()


class AgentProgressIn(BaseModel):
    progress: int = 0
    stage: str = ""


class AgentFailIn(BaseModel):
    error: str
