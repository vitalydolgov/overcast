from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sqlite3
import os

from streak import local_today, shift_day, streak_ending, parts, days_from

DB_PATH = os.path.join(os.path.dirname(__file__), "overcast.db")

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
