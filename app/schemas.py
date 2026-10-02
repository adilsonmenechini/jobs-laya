from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class JobSearchRequest(BaseModel):
    keywords: list[str] = Field(min_length=1, max_length=20)
    location: str = "Brazil"
    limit: int = Field(default=25, ge=1, le=100)
    fetch_details: bool = True
    source: Literal["linkedin", "geekhunter", "gupy", "indeed", "glassdoor", "all"] = "all"
    # recency window in hours (0 = keep everything); the front presets are
    # 1d=24 · 72h=72 · 7d=168 · 30d=720 (default) · sem filtro=0
    hours_old: int = Field(default=720, ge=0, le=8760)


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    source_id: str
    title: str
    company: str | None
    location: str | None
    remote: bool
    url: str | None
    description: str
    posted_at: str | None
    match: str | None
    score: float | None
    decision: dict | None
    reasons: list | None
    gaps: list | None


class JobList(BaseModel):
    total: int
    items: list[JobOut]


class ProfileOut(BaseModel):
    name: str
    titles: list[str]
    seniority: list[str]
    locations: list[str]
    remote_required: bool
    skills: list[str]
    focus: list[str]
    exclusions: list[str] = Field(default_factory=list)


class ToolDescriptorOut(BaseModel):
    name: str
    description: str
    input_schema: dict


class ToolList(BaseModel):
    tools: list[ToolDescriptorOut]


class ToolSearchRequest(BaseModel):
    keywords: str = Field(min_length=1, max_length=200)
    location: str = "Brazil"
    limit: int = Field(default=25, ge=1, le=100)


class LinkedInJobItem(BaseModel):
    linkedin_id: str
    title: str
    company: str | None = None
    location: str | None = None
    remote: bool = False
    url: str | None = None
    description: str = ""
    posted_at: str | None = None
    raw: dict | None = None


class ToolItems(BaseModel):
    tool: str
    count: int
    items: list[LinkedInJobItem]


class ToolItem(BaseModel):
    tool: str
    item: LinkedInJobItem
