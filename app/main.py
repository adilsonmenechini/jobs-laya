from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.classifier.engine import peek_engine
from app.config import settings
from app.db import get_db, init_db
from app.linkedin.browser import close_session
from app.linkedin.tools import TOOLS, LinkedInTools, ToolError, ToolNotFoundError, get_tools
from app.models import Job
from app.schemas import (
    JobList,
    JobOut,
    JobSearchRequest,
    ProfileOut,
    ToolItem,
    ToolItems,
    ToolList,
    ToolSearchRequest,
)
from app.services.jobs import list_jobs, load_profile, sync_jobs
from app.sources import SourceUnavailableError, source_names

DbSession = Annotated[Session, Depends(get_db)]
ToolsService = Annotated[LinkedInTools, Depends(get_tools)]

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield
    await close_session()


app = FastAPI(
    title="Job Classifier",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    engine = peek_engine()
    return {
        "status": "ok",
        "sources": source_names(),
        "classifier": {
            "backend": settings.classifier_backend,
            "laya_ready": engine.ready if engine else None,
            "device": engine.device if engine else None,
        },
    }


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/profile", response_model=ProfileOut)
def profile():
    return load_profile(settings.profile_path)


@app.post("/jobs/sync")
async def sync(request: JobSearchRequest, db: DbSession):
    try:
        outcome = await sync_jobs(
            db=db,
            keywords=request.keywords,
            location=request.location,
            limit=request.limit,
            fetch_details=request.fetch_details,
            profile_path=settings.profile_path,
            source=request.source,
        )
    except SourceUnavailableError as exc:
        # Requested a source the registry does not have (e.g. geekhunter
        # without config): explicit 503, never silently sync another provider.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"synced": outcome.count, "errors": outcome.errors}


@app.get("/jobs", response_model=JobList)
def jobs(
    db: DbSession,
    match: Annotated[str | None, Query(pattern="^(high|medium|low)$")] = None,
    remote: bool | None = None,
    query: str | None = None,
    min_score: Annotated[float | None, Query(ge=0, le=100)] = None,
    source: Annotated[str | None, Query(pattern="^(linkedin|geekhunter)$")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    items, total = list_jobs(db, match, remote, query, min_score, source, limit, offset)
    return {"total": total, "items": items}


@app.get("/jobs/{job_id}", response_model=JobOut)
def job(job_id: int, db: DbSession):
    item = db.get(Job, job_id)
    if not item:
        raise HTTPException(status_code=404, detail="Job not found")
    return item


async def run_tool(awaitable):
    """Map tool failures to HTTP status codes: 404 for missing, 502 for upstream."""
    try:
        return await awaitable
    except ToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ToolError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/tools", response_model=ToolList)
def list_tools():
    return {"tools": TOOLS}


@app.post("/tools/search_jobs", response_model=ToolItems)
async def tool_search_jobs(request: ToolSearchRequest, tools: ToolsService):
    items = await run_tool(tools.search_jobs(request.keywords, request.location, request.limit))
    return {"tool": "search_jobs", "count": len(items), "items": items}


@app.get("/tools/get_job_details/{job_id}", response_model=ToolItem)
async def tool_get_job_details(job_id: str, tools: ToolsService):
    item = await run_tool(tools.get_job_details(job_id))
    return {"tool": "get_job_details", "item": item}


@app.get("/tools/get_saved_jobs", response_model=ToolItems)
async def tool_get_saved_jobs(
    tools: ToolsService,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
):
    items = await run_tool(tools.get_saved_jobs(limit))
    return {"tool": "get_saved_jobs", "count": len(items), "items": items}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
