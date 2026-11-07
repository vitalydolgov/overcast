from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sqlite3
import os
import json
from datetime import datetime

from streak import local_today, shift_day, streak_ending, parts, days_from

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "overcast.db"))

app = FastAPI()
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

SPANS = 7


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.on_event("startup")
async def startup():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cloudy_days (day TEXT PRIMARY KEY, cloudy INTEGER NOT NULL)"
    )
    conn.commit()
    conn.close()


def window_for(today: str):
    from streak import shift_day
    return {"today": today, "from": shift_day(today, -(SPANS - 1)), "to": today}


def read_view(today: str, from_day: str, to_day: str):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT day, cloudy FROM cloudy_days").fetchall()
    conn.close()
    marks = [{"day": row[0], "cloudy": int(row[1]) if row[1] is not None else None} for row in rows]
    by_day = {m["day"]: m["cloudy"] for m in marks}
    days = []
    cursor = from_day
    for _ in range(48):
        if cursor > to_day:
            break
        days.append({
            "day": cursor,
            "cloudy": by_day.get(cursor) if cursor in by_day else None,
        })
        cursor = shift_day(cursor, 1)
    streak = streak_ending(today, marks)
    return {
        "streak": streak,
        "today": today,
        "days": [
            {
                "day": d["day"],
                "cloudy": d["cloudy"],
                "meta": parts(d["day"]),
                "next": {None: 0, 0: 1, 1: 2, 2: None}[d["cloudy"]],
            }
            for d in days
        ],
        "view_today": today,
        "error": None,
    }


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    today = local_today()
    w = window_for(today)
    view = read_view(w["today"], w["from"], w["to"])
    return templates.TemplateResponse(request, "index.html", view)


@app.post("/save", response_class=HTMLResponse)
async def save(
    request: Request,
    today: str = Form(...),
    day: str = Form(...),
    cloudy: str = Form(...),
):
    # Parse cloudy: "0" / "1" / "2" / anything else (None => delete)
    cloud_val = None
    if cloudy in ("0", "1", "2"):
        cloud_val = int(cloudy)
    else:
        cloud_val = None

    conn = sqlite3.connect(DB_PATH)
    if cloud_val is None:
        conn.execute("DELETE FROM cloudy_days WHERE day = ?", (day,))
    else:
        conn.execute(
            "INSERT INTO cloudy_days (day, cloudy) VALUES (?, ?) ON CONFLICT(day) DO UPDATE SET cloudy = excluded.cloudy",
            (day, cloud_val),
        )
    conn.commit()
    conn.close()

    w = window_for(today)
    view = read_view(w["today"], w["from"], w["to"])
    return templates.TemplateResponse(request, "index.html", view)


MCP_INT_TO_VALUE = {0: "cloudy", 1: "okay", 2: "good"}
MCP_VALUE_TO_INT = {"cloudy": 0, "okay": 1, "good": 2}
MCP_PROTOCOL_VERSION = "2025-06-18"
MCP_SERVER_INFO = {"name": "overcast", "version": "1.0.0"}


def mcp_status_days():
    today = local_today()
    from_day = shift_day(today, -6)
    conn = get_db()
    rows = conn.execute(
        "SELECT day, cloudy FROM cloudy_days WHERE day BETWEEN ? AND ?",
        (from_day, today),
    ).fetchall()
    conn.close()
    by_day = {row["day"]: row["cloudy"] for row in rows}
    result = []
    for day in days_from(from_day, today):
        raw = by_day.get(day)
        result.append({
            "date": day,
            "value": MCP_INT_TO_VALUE.get(int(raw)) if raw is not None else None,
        })
    return result


def mcp_record(arguments):
    date = arguments.get("date")
    value = arguments.get("value")
    if not isinstance(date, str) or not isinstance(value, str):
        return None, "date and value are required strings"
    try:
        parsed = datetime.strptime(date, "%Y-%m-%d")
        if parsed.strftime("%Y-%m-%d") != date:
            raise ValueError
    except ValueError:
        return None, f"invalid date: {date!r} (expected YYYY-MM-DD)"
    if value not in MCP_VALUE_TO_INT:
        return None, f"invalid value: {value!r} (expected one of 'cloudy', 'okay', 'good')"
    cloudy = MCP_VALUE_TO_INT[value]
    conn = get_db()
    conn.execute(
        "INSERT INTO cloudy_days (day, cloudy) VALUES (?, ?) ON CONFLICT(day) DO UPDATE SET cloudy = excluded.cloudy",
        (date, cloudy),
    )
    conn.commit()
    conn.close()
    return {"date": date, "value": value}, None


def mcp_tool_result(payload, is_error=False):
    return {
        "content": [{"type": "text", "text": json.dumps(payload) if not isinstance(payload, str) else payload}],
        "isError": is_error,
    }


def mcp_handle(message):
    if not isinstance(message, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}, True
    msg_id = message.get("id")
    is_notification = "id" not in message
    method = message.get("method")
    params = message.get("params") or {}

    def reply(result):
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}, False

    def error(code, text):
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": text}}, False

    if method == "initialize":
        client_version = params.get("protocolVersion") if isinstance(params, dict) else None
        return reply({
            "protocolVersion": client_version or MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": MCP_SERVER_INFO,
        })
    if method == "ping":
        return reply({})
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None, True
    if method == "tools/list":
        return reply({
            "tools": [
                {
                    "name": "status",
                    "description": "Return the last 7 days of data ending today, as [{\"date\": ..., \"value\": ...}, ...] with value one of 'cloudy', 'okay', 'good' (null when no record exists).",
                    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                },
                {
                    "name": "record",
                    "description": "Insert or update the record for a date. value must be exactly 'cloudy', 'okay', or 'good'.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                            "value": {"type": "string", "enum": ["cloudy", "okay", "good"]},
                        },
                        "required": ["date", "value"],
                        "additionalProperties": False,
                    },
                },
            ]
        })
    if method == "tools/call":
        if not isinstance(params, dict):
            return error(-32602, "Invalid params")
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return error(-32602, "Invalid params: arguments must be an object")
        if name == "status":
            days = mcp_status_days()
            result = mcp_tool_result(days)
            result["structuredContent"] = {"days": days}
            return reply(result)
        if name == "record":
            payload, err = mcp_record(arguments)
            if err:
                return reply(mcp_tool_result(f"Error: {err}", is_error=True))
            result = mcp_tool_result(payload)
            result["structuredContent"] = payload
            return reply(result)
        return error(-32602, f"Unknown tool: {name}")
    if is_notification:
        return None, True
    return error(-32601, f"Method not found: {method}")


@app.post("/mcp")
async def mcp(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
            status_code=400,
        )
    messages = body if isinstance(body, list) else [body]
    responses = []
    for message in messages:
        response, _ = mcp_handle(message)
        if response is not None:
            responses.append(response)
    if not responses:
        return JSONResponse(None, status_code=202)
    if isinstance(body, list):
        return JSONResponse(responses)
    return JSONResponse(responses[0])
