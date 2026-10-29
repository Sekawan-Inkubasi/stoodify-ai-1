"""Service HTTP untuk backend Go. Jalankan: uvicorn service:app --port 8000
URL yang diisi di AI_SCHEDULER_URL milik backend: http://<host>:<port>/schedule"""
import hmac
import logging
import os
import time

from fastapi import FastAPI, Header, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from adapter import PayloadError, adapt_request, to_backend_sessions
from llm import ai_schedule, load_env

load_env()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("stoodify")

app = FastAPI(title="Stoodify AI Engine", version="1.0")


def check_auth(authorization):
    key = os.getenv("AI_API_KEY")
    if not key:
        if os.getenv("ALLOW_NO_AUTH", "").lower() == "true":
            return  # hanya untuk pengembangan lokal
        raise HTTPException(503, "AI_API_KEY belum diatur di server engine")
    token = authorization or ""
    if not token.startswith("Bearer ") or not hmac.compare_digest(token[7:].encode(), key.encode()):
        raise HTTPException(401, "API key tidak valid")


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
    log.info("schedule user=%s tasks=%d sessions=%d source=%s ms=%d",
             payload.get("user_id"), meta["tasks_used"], len(sessions),
             result["source"], int((time.time() - t0) * 1000))
    return {
        "sessions": sessions,
        "warnings": warnings + result["warnings"],
        "source": result["source"],
        "fallback_reason": result.get("fallback_reason"),
        "model": result.get("model"),
        "latency_ms": int((time.time() - t0) * 1000),
    }
