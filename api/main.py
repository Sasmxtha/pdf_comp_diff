"""FastAPI application for spec-diff web service."""

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiofiles
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from specdiff.config import get_config
from specdiff.engine import compare_pdfs
from specdiff.models import ComparisonResult
from specdiff.report import export_all

logger = logging.getLogger(__name__)

# Job storage
jobs: dict[str, dict[str, Any]] = {}

# Temp directories
UPLOAD_DIR = Path("uploads")
RESULT_DIR = Path("results")


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Startup and shutdown logic."""
    # Startup
    UPLOAD_DIR.mkdir(exist_ok=True)
    RESULT_DIR.mkdir(exist_ok=True)
    logger.info("API server started")

    yield

    # Shutdown
    logger.info("API server shutting down")


app = FastAPI(
    title="spec-diff API",
    description="Compare PDF specification revisions",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS - localhost only for desktop tool
config = get_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.api.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def run_comparison(job_id: str, old_pdf: Path, new_pdf: Path) -> None:
    """Background task to run PDF comparison."""
    try:
        jobs[job_id]["status"] = "processing"
        jobs[job_id]["progress"] = 0.0

        # Run comparison (blocking operation in thread pool)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, compare_pdfs, old_pdf, new_pdf)

        jobs[job_id]["progress"] = 0.9

        # Export results
        output_dir = RESULT_DIR / job_id
        await loop.run_in_executor(None, export_all, result, output_dir, "comparison")

        jobs[job_id]["status"] = "complete"
        jobs[job_id]["progress"] = 1.0
        jobs[job_id]["result"] = result

        logger.info(f"Job {job_id} completed: {len(result.changes)} changes")

    except Exception as e:
        logger.exception(f"Job {job_id} failed: {e}")
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)


@app.post("/compare")
async def compare_endpoint(
    old_pdf: UploadFile = File(...),
    new_pdf: UploadFile = File(...),
) -> JSONResponse:
    """
    Upload two PDFs and start comparison job.

    Returns job_id for polling progress.
    """
    # Validate file sizes
    max_size = config.api.max_file_size

    # Validate PDFs
    if not old_pdf.filename or not old_pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Old file must be a PDF")

    if not new_pdf.filename or not new_pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "New file must be a PDF")

    # Create job
    job_id = str(uuid.uuid4())
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Save uploaded files
    old_path = job_dir / "old.pdf"
    new_path = job_dir / "new.pdf"

    try:
        # Save files
        async with aiofiles.open(old_path, "wb") as f:
            content = await old_pdf.read()
            if len(content) > max_size:
                raise HTTPException(400, f"Old PDF exceeds max size ({max_size} bytes)")
            await f.write(content)

        async with aiofiles.open(new_path, "wb") as f:
            content = await new_pdf.read()
            if len(content) > max_size:
                raise HTTPException(400, f"New PDF exceeds max size ({max_size} bytes)")
            await f.write(content)

        # Create job record
        jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "progress": 0.0,
            "old_filename": old_pdf.filename,
            "new_filename": new_pdf.filename,
        }

        # Start comparison in background
        asyncio.create_task(run_comparison(job_id, old_path, new_path))

        logger.info(f"Started job {job_id}: {old_pdf.filename} vs {new_pdf.filename}")

        return JSONResponse(
            {
                "job_id": job_id,
                "status": "queued",
                "message": "Comparison started",
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to start comparison: {e}")
        raise HTTPException(500, f"Failed to start comparison: {e}")


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str) -> JSONResponse:
    """Get status and progress of a comparison job."""
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")

    job = jobs[job_id]

    return JSONResponse(
        {
            "job_id": job_id,
            "status": job["status"],
            "progress": job["progress"],
            "old_filename": job.get("old_filename"),
            "new_filename": job.get("new_filename"),
            "error": job.get("error"),
        }
    )


@app.get("/result/{job_id}")
async def get_result(job_id: str) -> JSONResponse:
    """Get comparison result as JSON."""
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")

    job = jobs[job_id]

    if job["status"] != "complete":
        raise HTTPException(400, f"Job status: {job['status']}")

    result: ComparisonResult = job["result"]

    return JSONResponse(result.model_dump())


@app.get("/export/{job_id}")
async def export_result(job_id: str, format: str = "html") -> FileResponse:
    """Download exported report in specified format."""
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")

    job = jobs[job_id]

    if job["status"] != "complete":
        raise HTTPException(400, f"Job status: {job['status']}")

    # Validate format
    if format not in ["html", "json", "docx"]:
        raise HTTPException(400, f"Invalid format: {format}")

    # Find export file
    result_dir = RESULT_DIR / job_id
    export_file = result_dir / f"comparison.{format}"

    if not export_file.exists():
        raise HTTPException(404, f"Export file not found: {format}")

    # Determine media type
    media_types = {
        "html": "text/html",
        "json": "application/json",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }

    return FileResponse(
        export_file,
        media_type=media_types[format],
        filename=f"comparison.{format}",
    )


@app.get("/health")
async def health() -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse({"status": "healthy", "version": "0.1.0"})


if __name__ == "__main__":
    import uvicorn

    # Setup logging
    config = get_config()
    config.setup_logging()

    uvicorn.run(app, host="127.0.0.1", port=8000)
