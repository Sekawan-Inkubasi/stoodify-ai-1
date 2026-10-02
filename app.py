"""Halaman uji tunggal (Flask). Jalankan: python app.py"""
import time
from flask import Flask, jsonify, render_template, request
from data import NOW, STUDENT
from llm import ai_schedule, get_api_key, load_env
from priority import WEIGHTS
from scheduler import fallback_schedule
from slots import find_free_slots, fmt

load_env()
app = Flask(__name__)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/data")
def api_data():
    return jsonify({"now": NOW.strftime("%Y-%m-%d %H:%M"), "student": STUDENT,
                    "weights": WEIGHTS, "has_key": bool(get_api_key())})


@app.post("/api/run")
def api_run():
    body = request.get_json(silent=True) or {}
    weights = {k: float(body.get("weights", {}).get(k, v)) for k, v in WEIGHTS.items()}
    if body.get("mode") == "ai":
        result = ai_schedule(STUDENT, NOW, weights)
    else:
        t0 = time.time()
        result = fallback_schedule(STUDENT, NOW, weights)
        result.update(source="fallback", fallback_reason=None, dropped=[], model=None,
                      latency_ms=int((time.time() - t0) * 1000))
    result["slots"] = [{"date": s["date"], "start": fmt(s["start"]), "end": fmt(s["end"])}
                       for s in find_free_slots(STUDENT, NOW)]
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
