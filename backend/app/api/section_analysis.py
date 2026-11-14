import asyncio
import json
import logging
from threading import Event

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.schemas.section_analysis import SectionAnalysisRequest, SectionAnalysisResponse
from app.services.section_analysis import AnalysisCancelled, AnalysisUnavailable

logger = logging.getLogger(__name__)
NDJSON = "application/x-ndjson"

router = APIRouter(tags=["section analysis"])


@router.post(
    "/maps/sections/analyze",
    response_model=SectionAnalysisResponse,
    description="Runs SAM2 on the submitted map PNG and positive point prompts. Runs trained TempCNN on 16 clear Sentinel-2 observations downloaded on demand per field. Fields with insufficient observations are reported as skipped. Crop names follow the trained class mapping. Does not save fields.",
    responses={
        200: {"content": {NDJSON: {"schema": {"type": "string"}}}},
        422: {"description": "Invalid map image or points"},
        503: {"description": "Model unavailable or busy"},
    },
)
async def analyze_section(payload: SectionAnalysisRequest, request: Request):
    if NDJSON in request.headers.get("accept", ""):
        return StreamingResponse(
            analysis_events(payload, request),
            media_type=NDJSON,
            headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"},
        )
    cancelled = Event()
    work = asyncio.create_task(
        run_in_threadpool(request.app.state.section_analyzer.analyze, payload, cancelled)
    )
    try:
        while not work.done():
            done, _ = await asyncio.wait({work}, timeout=0.5)
            if not done and await request.is_disconnected():
                cancelled.set()
        return await work
    except asyncio.CancelledError:
        cancelled.set()
        # A native model operation cannot be interrupted; consume the eventual result.
        work.add_done_callback(lambda task: task.exception() if not task.cancelled() else None)
        raise
    except AnalysisCancelled as error:
        raise HTTPException(status_code=499, detail="Analysis canceled") from error
    except AnalysisUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


async def analysis_events(payload, request):
    cancelled = Event()
    loop = asyncio.get_running_loop()
    updates = asyncio.Queue(maxsize=1)

    def publish(update):
        if updates.full():
            updates.get_nowait()
        updates.put_nowait(update)

    def report(update):
        if not cancelled.is_set():
            loop.call_soon_threadsafe(publish, update)

    def line(event):
        return json.dumps(event) + "\n"

    def consume_result(task):
        if not task.cancelled():
            task.exception()

    work = asyncio.create_task(
        run_in_threadpool(request.app.state.section_analyzer.analyze, payload, cancelled, report)
    )
    pending_update = None
    try:
        while not work.done():
            pending_update = asyncio.create_task(updates.get())
            done, _ = await asyncio.wait(
                {pending_update, work}, timeout=10, return_when=asyncio.FIRST_COMPLETED
            )
            if pending_update in done:
                yield line({"type": "progress", **pending_update.result()})
            else:
                pending_update.cancel()
                if work not in done:
                    yield line({"type": "heartbeat"})
        result = SectionAnalysisResponse.model_validate(await work)
        yield line({"type": "result", "result": result.model_dump(mode="json")})
    except (AnalysisCancelled, AnalysisUnavailable, ValueError) as error:
        yield line({"type": "error", "message": str(error) or "Analysis canceled"})
    except Exception:
        logger.exception("Streaming section analysis failed")
        yield line({"type": "error", "message": "Unable to analyze this section."})
    finally:
        cancelled.set()
        if pending_update is not None:
            pending_update.cancel()
        work.add_done_callback(consume_result)
