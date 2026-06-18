from __future__ import annotations

from pydantic import BaseModel, Field


class Goal(BaseModel):
    id: str
    purpose: str
    object: str
    issue: str
    viewpoint: str = ""


class Question(BaseModel):
    id: str
    goal_id: str
    text: str


class Metric(BaseModel):
    id: str
    question_id: str
    name: str
    unit: str = ""
    data_source: str = ""
    baseline: float | None = None
    target: float | None = None
