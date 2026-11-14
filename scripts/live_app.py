"""Live practice app: replay a case's webhook deliveries against the original code or the agent's verified fix.

    uv run python scripts/live_app.py [--port 8100] [--traceback http://127.0.0.1:8000]

POST /api/replay {"case": "B", "mode": "before" | "after", "runId": "run_..." | null}
  before: the case's practice app as shipped (plus the case overlay) -> the real bug happens.
  after:  the same copy with the latest patch from the run whose attempt passed verification.
Each replay runs in a subprocess against a throwaway fixture database (local MongoDB, never Atlas),
with a stripped environment, then the database and the temp copy are deleted.
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "trusted_tests"))

from apps import APPS  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from runner.sandbox import CASES, IGNORE, SAFE_ENV_KEYS, fixture_uri, load_manifest  # noqa: E402

WEB = ROOT / "web"
TIMEOUT_S = 30
LOCAL_MONGODB = "mongodb://localhost:27017"
TEAM_KEYS = {"team-payments": "key-payments-eng", "team-platform": "key-platform-eng"}
TRACEBACK_URL = os.environ.get("TRACEBACK_URL", "http://127.0.0.1:8000")

# Runs inside the temp app copy. Reads its config as JSON on stdin, prints one JSON line.
SNIPPET = r"""
import json, sys
cfg = json.loads(sys.stdin.read())
from fastapi.testclient import TestClient
from app.main import app
from app.db import get_db
n = cfg["names"]
results = []
try:
    with TestClient(app, raise_server_exceptions=True) as client:
        for i, d in enumerate(cfg["deliveries"], 1):
            try:
                r = client.post(cfg["path"], json=d)
                results.append({"n": i, "status": r.status_code, "body": r.text[:200], "error": None})
            except Exception as exc:
                first = (str(exc).splitlines() or [type(exc).__name__])[0].split(", full error:")[0]
                results.append({"n": i, "status": 500, "body": "Internal Server Error", "error": first[:300]})
    db = get_db()
    ids = sorted({d["id"] for d in cfg["deliveries"]})
    customer = cfg["customer"]
    credited = sum(int(doc.get(n["ledger_amount_field"], 0) or 0)
                   for doc in db[n["ledger"]].find({n["ledger_customer_field"]: customer}))
    rows = db[n["payments"]].count_documents({n["event_field"]: {"$in": ids}})
    replays = None
    if n.get("replays"):
        replays = db[n["replays"]].count_documents({n["replay_event_field"]: {"$in": ids}})
    print(json.dumps({"deliveries": results, "credited": credited, "paymentRows": rows, "replays": replays}))
finally:
    try:
        get_db().client.drop_database(cfg["db"])
    except Exception:
        pass
"""


class ReplayBody(BaseModel):
    case: str
    mode: str
    runId: str | None = None  # noqa: N815 - camelCase on the wire


app = FastAPI(title="Traceback live practice app")


@functools.lru_cache(maxsize=1)
def _fixture_uri() -> str:
    """The runner's fixture URI if it answers a ping, else the local MongoDB on 27017. Never Atlas."""
    from pymongo import MongoClient

    try:
        uri = fixture_uri()
        MongoClient(uri, serverSelectionTimeoutMS=1500).admin.command("ping")
        return uri
    except Exception:
        return LOCAL_MONGODB


def fetch_events(traceback: str, run_id: str, api_key: str) -> list[dict]:
    """GET {traceback}/runs/{run_id}/events?after=0. Monkeypatched in tests."""
    url = f"{traceback.rstrip('/')}/runs/{run_id}/events?after=0"
    req = urllib.request.Request(url, headers={"X-API-Key": api_key})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def verified_patch(events: list[dict]) -> dict | None:
    """The latest patch_proposed payload whose attempt has a passed verification, else None."""
    passed = {
        e["payload"].get("attempt")
        for e in events
        if e.get("type") == "verification" and (e.get("payload", {}).get("result") or {}).get("status") == "passed"
    }
    patches = [e for e in events if e.get("type") == "patch_proposed" and e.get("payload", {}).get("attempt") in passed]
    if not patches:
        return None
    return max(patches, key=lambda e: e.get("seq", 0))["payload"]


def run_deliveries(case_id: str, manifest, patch_path: str | None, new_content: str | None) -> dict:
    """Copy the app (plus overlay), optionally write the patch, post the deliveries in a subprocess."""
    tmp = Path(tempfile.mkdtemp(prefix=f"traceback_live_{case_id}_"))
    app_dir = tmp / "app_root"
    db_name = f"fixture_live_{uuid.uuid4().hex[:8]}"
    try:
        shutil.copytree(ROOT / manifest.fixture_path, app_dir, ignore=IGNORE)
        overlay = CASES / case_id / "overlay"
        if overlay.is_dir():
            shutil.copytree(overlay, app_dir, dirs_exist_ok=True, ignore=IGNORE)
        if patch_path and new_content is not None:
            (app_dir / patch_path).write_text(new_content, encoding="utf-8")
        deliveries = manifest.request["deliveries"]
        cfg = {
            "deliveries": deliveries,
            "path": manifest.request.get("path", "/webhooks/provider"),
            "names": APPS[manifest.repository_id],
            "customer": deliveries[0]["customer_id"],
            "db": db_name,
        }
        env = {key: os.environ[key] for key in SAFE_ENV_KEYS if key in os.environ}
        env.update(FIXTURE_MONGODB_URI=_fixture_uri(), FIXTURE_DB=db_name, PYTHONDONTWRITEBYTECODE="1")
        try:
            proc = subprocess.run(
                [sys.executable, "-c", SNIPPET], cwd=app_dir, env=env, input=json.dumps(cfg),
                capture_output=True, text=True, timeout=TIMEOUT_S,
            )
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(504, f"replay timed out after {TIMEOUT_S}s") from exc
        lines = [line for line in proc.stdout.splitlines() if line.startswith("{")]
        if proc.returncode != 0 or not lines:
            tail = (proc.stderr or proc.stdout).strip().splitlines()[-1:] or ["no output"]
            raise HTTPException(500, f"replay failed: {tail[0][:300]}")
        out = json.loads(lines[-1])
        out["deliveriesIn"] = deliveries
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _summary(verdict: str, mode: str, deliveries: list[dict], credited: int, expected: int) -> str:
    who = "The original code" if mode == "before" else "The agent's verified fix"
    if verdict == "crashed":
        bad = next(d for d in deliveries if d["status"] >= 500)
        return (f"{who} crashed on delivery {bad['n']} ({bad['eventId']}) with a server error, "
                "so the provider keeps retrying.")
    if verdict == "double-credited":
        return f"{who} credited {credited} instead of {expected}: the customer's balance is wrong."
    return f"{who} answered every delivery and credited {credited}, exactly once per event."


@app.post("/api/replay")
def replay(body: ReplayBody) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", body.case or "") or not (CASES / body.case / "manifest.json").is_file():
        raise HTTPException(400, f"unknown case: {body.case}")
    if body.mode not in ("before", "after"):
        raise HTTPException(400, "mode must be 'before' or 'after'")
    try:
        manifest = load_manifest(body.case)
        if not manifest.request.get("deliveries") or manifest.repository_id not in APPS:
            raise ValueError("no deliveries")
    except Exception as exc:
        raise HTTPException(400, f"unknown case: {body.case}") from exc

    patchable = [p.replace("\\", "/") for p in manifest.patchable_files]
    code = {"source": "original", "runId": None, "attempt": None, "verified": False,
            "path": patchable[0] if patchable else None, "newContent": None, "fromMemoryLines": []}
    if body.mode == "after":
        if not body.runId:
            raise HTTPException(400, "mode 'after' needs a runId")
        key = TEAM_KEYS.get(manifest.team_id, "key-payments-eng")
        try:
            events = fetch_events(getattr(app.state, "traceback", TRACEBACK_URL),
                                  body.runId, key)
        except Exception as exc:
            raise HTTPException(502, f"could not read run {body.runId} from Traceback: {exc}") from exc
        payload = verified_patch(events)
        if payload is None:
            raise HTTPException(409, "this run has no verified fix")
        patch = payload.get("patch") or {}
        path = (patch.get("path") or "").replace("\\", "/")
        if path not in patchable:
            raise HTTPException(409, f"the verified patch touches a file that is not patchable: {path}")
        code = {"source": "agent-fix", "runId": body.runId, "attempt": payload.get("attempt"), "verified": True,
                "path": path, "newContent": patch.get("newContent"),
                "fromMemoryLines": payload.get("fromMemoryLines") or []}

    out = run_deliveries(body.case, manifest, code["path"] if body.mode == "after" else None, code["newContent"])
    delivered = []
    for d, r in zip(out["deliveriesIn"], out["deliveries"], strict=False):
        delivered.append({"n": r["n"], "eventId": d["id"], "customerId": d["customer_id"], "amount": d["amount"],
                          "status": r["status"], "body": r["body"], "error": r["error"]})
    expected = sum({d["id"]: int(d["amount"]) for d in out["deliveriesIn"]}.values())
    credited = int(out["credited"])
    if any(d["status"] >= 500 for d in delivered):
        verdict = "crashed"
    elif credited != expected:
        verdict = "double-credited"
    else:
        verdict = "ok"
    return {
        "case": body.case,
        "mode": body.mode,
        "code": code,
        "deliveries": delivered,
        "ledger": {"customerId": out["deliveriesIn"][0]["customer_id"], "credited": credited,
                   "expectedCredit": expected, "paymentRows": out["paymentRows"], "replaysRecorded": out["replays"]},
        "verdict": verdict,
        "summary": _summary(verdict, body.mode, delivered, credited, expected),
    }


@app.get("/")
def index():
    page = WEB / "live.html"
    if not page.is_file():
        raise HTTPException(404, "web/live.html not written yet")
    return FileResponse(page)


app.mount("/", StaticFiles(directory=str(WEB), check_dir=False), name="web")


def main() -> int:
    parser = argparse.ArgumentParser(description="Traceback live practice app.")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--traceback", default=TRACEBACK_URL)
    args = parser.parse_args()
    app.state.traceback = args.traceback

    import uvicorn

    print(f"Live practice app: open http://127.0.0.1:{args.port}   (Traceback API: {args.traceback})")
    uvicorn.run(app, host="127.0.0.1", port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
