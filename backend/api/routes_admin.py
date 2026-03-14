"""
Admin routes for triggering re-ingestion and health checks.
POST /admin/ingest — run the ingestion pipeline
GET  /admin/health/sources — check MOM URL health
"""
import json
import asyncio

import httpx
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from backend.config import RAW_SCRAPED_DIR
from backend.ingestion.scraper_mom import SEED_URLS, HEADERS

router = APIRouter(prefix="/admin")


class IngestRequest(BaseModel):
    force_rescrape: bool = False


def _run_ingest(force_rescrape: bool):
    if force_rescrape:
        # Remove cached files to force re-scrape
        for fname in ["employment_act.json", "mom_pages.json"]:
            path = RAW_SCRAPED_DIR / fname
            if path.exists():
                path.unlink()

    from backend.ingestion.ingest_pipeline import run
    run()


@router.post("/ingest")
async def trigger_ingest(req: IngestRequest, background_tasks: BackgroundTasks):
    """
    Trigger the ingestion pipeline in the background.
    Check /admin/health/sources first to validate MOM URLs.
    """
    background_tasks.add_task(_run_ingest, req.force_rescrape)
    return {
        "status": "started",
        "message": "Ingestion pipeline started in background. Check server logs for progress.",
        "force_rescrape": req.force_rescrape,
    }


@router.get("/health/sources")
async def check_source_health():
    """Validate all MOM seed URLs are reachable before ingestion."""
    results = []
    async with httpx.AsyncClient(headers=HEADERS) as client:
        for url in SEED_URLS:
            try:
                r = await client.head(url, timeout=10, follow_redirects=True)
                results.append({"url": url, "status": r.status_code, "ok": r.status_code == 200})
            except Exception as e:
                results.append({"url": url, "status": None, "ok": False, "error": str(e)})

    ok_count = sum(1 for r in results if r["ok"])
    return {
        "total": len(results),
        "ok": ok_count,
        "failed": len(results) - ok_count,
        "results": results,
    }


@router.get("/collections")
async def collection_counts():
    """Return current document counts in ChromaDB collections."""
    from backend.retrieval.vector_store import get_collection
    try:
        ea = get_collection("employment_act").count()
        mom = get_collection("mom_guidelines").count()
        return {"employment_act": ea, "mom_guidelines": mom}
    except Exception as e:
        return {"error": str(e)}
