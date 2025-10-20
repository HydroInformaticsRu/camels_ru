from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import pandas as pd
from pydantic import BaseModel
from starlette.templating import Jinja2Templates

from app.src.analysis.classification import classify_series
from app.src.plots.series_plot import plot_series_html
from app.src.plots.spatial_map import render_spatial_map_html
from app.src.review.counts import compute_review_counts
from app.src.review.metrics import fetch_metrics
from app.src.state.persistence import load_state, save_state
from app.src.storage.directories import ensure_review_dirs, remove_existing_copies

# App setup
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPDATE_DIR = BASE_DIR / "update"
STATE_PATH = UPDATE_DIR / "review_state.json"
METRICS_PATH = BASE_DIR / "Handof_2803_adjusted_metric.csv"
GAUGE_GPKG_PATH = (
    DATA_DIR / "Geometry/GaugeGeomCAMELS.gpkg"
)
WATERSHED_GPKG_PATH = (
    DATA_DIR / "Geometry/WatershedGeomCAMELS.gpkg"
)

# shorter path aliases for mounting
STATIC_DIR = BASE_DIR / "app" / "static"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"

app = FastAPI(title="CSV Gauge Inspector")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Prefer project logger if available. Use a project-local rotating file under
# update/logs/app.log as a fallback destination.
LOG_FILE_PATH = UPDATE_DIR / "logs" / "app.log"
_logger_initialized = False
try:
    # Try primary package path
    from src.utils.logger import setup_logger

    log = setup_logger("app.main", log_file=LOG_FILE_PATH)
    _logger_initialized = True
except Exception:
    try:
        # Try alternate relative package path
        from app.src.utils.logger import setup_logger

        log = setup_logger("app.main", log_file=LOG_FILE_PATH)
        _logger_initialized = True
    except Exception:
        import logging
        from logging.handlers import RotatingFileHandler

        logging.basicConfig(level=logging.INFO)
        log = logging.getLogger("app.main")
        # Ensure log directory exists and attach rotating file handler
        try:
            LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
            if not any(isinstance(h, RotatingFileHandler) for h in log.handlers):
                rfh = RotatingFileHandler(
                    str(LOG_FILE_PATH),
                    maxBytes=10 * 1024 * 1024,
                    backupCount=5,
                    encoding="utf-8",
                )
                fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
                rfh.setFormatter(fmt)
                log.addHandler(rfh)
        except Exception:
            # Best-effort: if filesystem writes fail, continue with console logging
            log.debug("Failed to attach rotating file handler", exc_info=True)
            log.warning(
                "Project logger not available; using basic logging; file=%s",
                LOG_FILE_PATH,
            )


@app.on_event("startup")
async def _startup_event() -> None:
    log.info("Starting CSV Gauge Inspector; data_dir=%s", DATA_DIR)


@app.on_event("shutdown")
async def _shutdown_event() -> None:
    log.info("Shutting down CSV Gauge Inspector")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, file: str | None = None) -> HTMLResponse:
    """Render the index page for CSV review.

    Picks the next unreviewed file by default and renders the plot and controls.
    """
    ensure_review_dirs(UPDATE_DIR, logger=log)
    csv_files = sorted([p.name for p in DATA_DIR.glob("*.csv")])
    if not csv_files:
        raise HTTPException(status_code=404, detail="No CSV files found in data/")

    state = load_state(STATE_PATH, UPDATE_DIR, logger=log)
    reviewed = set(state.get("reviewed", []))
    csv_set = set(csv_files)
    reviewed_in_scope = reviewed.intersection(csv_set)
    unreviewed = [f for f in csv_files if f not in reviewed_in_scope]

    total = len(csv_files)
    reviewed_count = len(reviewed_in_scope)
    percent = round(100 * reviewed_count / total, 1) if total else 0.0

    # Default file selection: first unreviewed. If none remain, show completion screen.
    if file is None:
        if unreviewed:
            file = unreviewed[0]
        else:
            resume_file = state.get("last_file")
            if resume_file not in csv_set:
                resume_file = None

            counts = compute_review_counts(UPDATE_DIR, logger=log)

            context = {
                "request": request,
                "progress": {"reviewed": reviewed_count, "total": total, "percent": percent},
                "resume_file": resume_file,
                "category_counts": counts,
            }
            return templates.TemplateResponse("done.html", context)

    path = DATA_DIR / file
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file}")

    try:
        df = pd.read_csv(path)
    except Exception as e:
        log.exception("Failed to read CSV %s", file)
        detail = f"Failed to read CSV {file}: {e}"
        raise HTTPException(status_code=400, detail=detail) from e
    status, is_empty, has_nans, has_data = classify_series(df, logger=log)

    # Compute NaN count for the main numeric series (used in the UI)
    try:
        num_df = df.select_dtypes(include=["number"])  # type: ignore[arg-type]
        has_zeros = False
        zero_count = 0
        if num_df.shape[1] == 0:
            nan_count = 0
            has_negatives = False
            zero_count = 0
        else:
            series = num_df.iloc[:, -1]
            nan_count = int(series.isna().sum())
            has_negatives = bool((series < 0).any())
            zero_count = int((series == 0).sum())
            has_zeros = zero_count > 0
    except Exception:
        nan_count = 0
        has_negatives = False
        has_zeros = False
        zero_count = 0

    gauge_id = Path(file).stem
    plot_html = plot_series_html(df, title=file, logger=log)
    map_render = render_spatial_map_html(
        gauge_id,
        GAUGE_GPKG_PATH,
        WATERSHED_GPKG_PATH,
        logger=log,
    )
    map_html = map_render.html
    gauge_metrics = fetch_metrics(METRICS_PATH, gauge_id, logger=log)

    # Determine next/prev for quick navigation (based on total list)
    idx = csv_files.index(file)
    prev_file = csv_files[idx - 1] if idx > 0 else None
    next_file = csv_files[idx + 1] if idx < len(csv_files) - 1 else None

    category_counts = compute_review_counts(UPDATE_DIR, logger=log)

    context = {
        "request": request,
        "file": file,
        "csv_files": csv_files,
        "plot_html": plot_html,
        "map_html": map_html,
        "watershed_name": map_render.watershed_name,
        "watershed_area": map_render.watershed_area,
        "status": status,
        "is_empty": is_empty,
        "has_nans": has_nans,
        "has_negatives": has_negatives,
        "has_zeros": has_zeros,
        "nan_count": nan_count,
        "zero_count": zero_count,
        "has_data": has_data,
        "metrics": gauge_metrics,
        "prev_file": prev_file,
        "next_file": next_file,
        "progress": {"reviewed": reviewed_count, "total": total, "percent": percent},
        "category_counts": category_counts,
    }

    return templates.TemplateResponse("index.html", context)


class ReviewForm(BaseModel):
    """Pydantic model for the review form payload."""

    file: str
    poor: bool = False
    shifted: bool = False
    negatives: bool = False
    zeros: bool = False


@app.post("/review")
async def review(
    file: str = Form(...),
    poor: str | None = Form(None),
    shifted: str | None = Form(None),
    negatives: str | None = Form(None),
    zeros: str | None = Form(None),
) -> RedirectResponse:
    """Handle the review submission and persist the classification decision.

    Rules:
    - If "shifted" is selected the file is copied only to update/shifted/
    - Otherwise choose the base folder: empty/no data → update/freezing/<poor|decent>/,
      has NaNs → update/partial/<poor|decent>/, else → update/full/<poor|decent>/
    - "poor" checkbox selects the <poor|decent> subfolder for base/auxiliary copies
    - "negatives" checkbox copies to update/negatives/<poor|decent>/ in addition to the base
    - "zeros" checkbox copies to update/freezing/<poor|decent>/ (no dedicated zeros folder)
    """
    ensure_review_dirs(UPDATE_DIR, logger=log)

    path = DATA_DIR / file
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file}")

    try:
        df = pd.read_csv(path)
    except Exception as e:
        log.exception("Failed to read CSV %s during review", file)
        detail = f"Failed to read CSV {file}: {e}"
        raise HTTPException(status_code=400, detail=detail) from e

    status, is_empty, has_nans, has_data = classify_series(df, logger=log)

    # Interpret checkbox
    poor_checked = poor is not None
    shifted_checked = shifted is not None
    negatives_checked = negatives is not None
    zeros_checked = zeros is not None

    # Remove any previous classification copies so the latest decision wins
    remove_existing_copies(UPDATE_DIR, path.name, logger=log)

    # Determine base folder
    destinations: list[Path] = []
    if shifted_checked:
        destinations.append(UPDATE_DIR / "shifted" / path.name)
        poor_checked = False
        negatives_checked = False
        zeros_checked = False
    else:
        quality_label = "poor" if poor_checked else "decent"
        base_category = "freezing" if (is_empty or not has_data) else ("partial" if has_nans else "full")
        base_dir = UPDATE_DIR / base_category / quality_label
        destinations.append(base_dir / path.name)

        if negatives_checked:
            destinations.append(UPDATE_DIR / "negatives" / quality_label / path.name)

        if base_category != "freezing" and zeros_checked:
            destinations.append(UPDATE_DIR / "freezing" / quality_label / path.name)

    # Ensure destination directories exist and copy file to each unique location
    unique_destinations = []
    seen = set()
    for dest in destinations:
        if dest not in seen:
            unique_destinations.append(dest)
            seen.add(dest)

    payload = path.read_bytes()

    for dest in unique_destinations:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload)
        log.info(
            "Copied %s -> %s (poor=%s, shifted=%s, negatives=%s, zeros=%s)",
            path.name,
            dest,
            poor_checked,
            shifted_checked,
            negatives_checked,
            zeros_checked,
        )

    # Update persistent state
    state = load_state(STATE_PATH, UPDATE_DIR, logger=log)
    reviewed = set(state.get("reviewed", []))
    reviewed.add(file)
    state["reviewed"] = sorted(reviewed)

    # Determine next unreviewed for faster workflow
    csv_files = sorted([p.name for p in DATA_DIR.glob("*.csv")])
    unreviewed = [f for f in csv_files if f not in reviewed]
    next_file = unreviewed[0] if unreviewed else None
    state["last_file"] = next_file or file
    save_state(STATE_PATH, UPDATE_DIR, state, logger=log)

    redirect_url = "/" if next_file is None else f"/?file={next_file}"
    return RedirectResponse(url=redirect_url, status_code=303)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
