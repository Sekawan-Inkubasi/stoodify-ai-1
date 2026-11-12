"""Service HTTP untuk backend Go. Jalankan: uvicorn service:app --port 8000
Endpoint:
- POST /schedule : Smart Study Scheduler (AI Specialist 1)
- POST /predict  : Material & Topic Predictor (AI Specialist 2 terpadu)
- POST /feedback : Analisis feedback akurasi materi
- GET  /health   : Health check
"""
import hmac
import logging
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from adapter import PayloadError, adapt_request, to_backend_sessions
from feedback import analisis_feedback, analisis_feedback_per_mapel
from llm import ai_schedule, load_env
from predictor import predict_material

load_env()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("stoodify")

app = FastAPI(title="Stoodify AI Engine (Unified)", version="2.0")


def check_auth(authorization: Optional[str]) -> None:
    key = os.getenv("AI_API_KEY")
    if not key:
        if os.getenv("ALLOW_NO_AUTH", "").lower() == "true":
            return  # hanya untuk pengembangan lokal
        raise HTTPException(503, "AI_API_KEY belum diatur di server engine")
    token = authorization or ""
    if not token.startswith("Bearer ") or not hmac.compare_digest(token[7:].encode(), key.encode()):
        raise HTTPException(401, "API key tidak valid")


class PredictionPayload(BaseModel):
    subject: str = Field(..., description="Nama mata pelajaran")
    difficulty: Optional[int] = Field(default=3, description="Tingkat kesulitan (1-5)")
    history: List[Dict[str, Any]] = Field(default_factory=list, description="Daftar tugas lampau")
    class_level: Optional[str] = Field(default="", description="Jenjang kelas siswa (misal: XI, XII)")
    curriculum: Optional[str] = Field(default="", description="Kurikulum acuan (misal: Kurikulum Merdeka)")


class FeedbackPayload(BaseModel):
    data_feedback: List[Dict[str, Any]] = Field(default_factory=list)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/schedule")
async def schedule(request: Request, authorization: str | None = Header(default=None)):
    check_auth(authorization)
    t0 = time.time()
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "body harus JSON")
    try:
        student, now, warnings, meta = adapt_request(payload)
    except PayloadError as e:
        raise HTTPException(422, str(e))

    result = await run_in_threadpool(ai_schedule, student, now)
    sessions = to_backend_sessions(result["sessions"])
    latency = int((time.time() - t0) * 1000)
    log.info("schedule user=%s tasks=%d sessions=%d source=%s ms=%d",
             payload.get("user_id"), meta["tasks_used"], len(sessions),
             result["source"], latency)
    return {
        "sessions": sessions,
        "warnings": warnings + result["warnings"],
        "source": result["source"],
        "fallback_reason": result.get("fallback_reason"),
        "model": result.get("model"),
        "latency_ms": latency,
    }


@app.post("/predict")
async def predict(payload: PredictionPayload, authorization: str | None = Header(default=None)):
    check_auth(authorization)
    t0 = time.time()

    sub = payload.subject.strip()
    if not sub:
        raise HTTPException(400, "Field 'subject' wajib diisi")

    result = await run_in_threadpool(
        predict_material,
        subject=sub,
        difficulty=payload.difficulty,
        task_history=payload.history,
        class_level=payload.class_level or "",
        curriculum=payload.curriculum or "",
    )

    latency = int((time.time() - t0) * 1000)
    log.info("predict subject='%s' history=%d topic='%s' conf=%.1f source=%s ms=%d",
             sub, len(payload.history), result.get("predicted_topic"),
             result.get("confidence", 0), result.get("source"), latency)

    return {
        "predicted_topic": result.get("predicted_topic"),
        "confidence": result.get("confidence"),
        "reason": result.get("reason"),
        "prerequisites": result.get("prerequisites"),
        "preparation_suggestion": result.get("preparation_suggestion"),
        "syllabus_reference": result.get("syllabus_reference"),
        "source": result.get("source"),
        "latency_ms": latency,
    }


@app.post("/feedback")
async def feedback(payload: FeedbackPayload, authorization: str | None = Header(default=None)):
    check_auth(authorization)
    return analisis_feedback(payload.data_feedback)


@app.post("/feedback/per-mapel")
async def feedback_per_mapel(payload: FeedbackPayload, authorization: str | None = Header(default=None)):
    check_auth(authorization)
    return analisis_feedback_per_mapel(payload.data_feedback)
