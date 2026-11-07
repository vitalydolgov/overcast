WEEKDAY = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
WEEKDAY_SHORT = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]
MONTH = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
MONTH_SHORT = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def shift_day(day: str, delta: int) -> str:
    year, month, date = map(int, day.split("-"))
    from datetime import datetime, timedelta
    utc = datetime(year, month, date) + timedelta(days=delta)
    return f"{utc.year:04d}-{utc.month:02d}-{utc.day:02d}"


def local_today() -> str:
    from datetime import datetime
    now = datetime.now()
    return f"{now.year}-{now.month:02d}-{now.day:02d}"


def parts(day: str):
    year, month, date = map(int, day.split("-"))
    from datetime import datetime
    utc = datetime(year, month, date)
    dow = utc.weekday()
    # Python weekday: Mon=0, Sun=6; original: Sun=0, Sat=6. Adjust.
    dow_sun = (dow + 1) % 7
    return {
        "year": year,
        "month": month,
        "date": date,
        "weekday": WEEKDAY[dow_sun],
        "short": WEEKDAY_SHORT[dow_sun],
        "monday_index": (dow_sun + 6) % 7,
    }


def long_date(day: str) -> str:
    p = parts(day)
    return f"{p['date']} {MONTH[p['month'] - 1]} {p['year']}"


def short_date(day: str) -> str:
    p = parts(day)
    return f"{p['date']} {MONTH_SHORT[p['month'] - 1]}"


def streak_ending(today: str, marks: list[dict]) -> int:
    map_ = {m["day"]: m["cloudy"] for m in marks}
    cursor = today
    if cursor not in map_:
        cursor = shift_day(today, -1)
    elif not map_.get(cursor, False):
        return 0
    count = 0
    for _ in range(20000):
        if map_.get(cursor) is True:
            count += 1
            cursor = shift_day(cursor, -1)
        else:
            break
    return count


def days_from(from_day: str, to_day: str) -> list[str]:
    days = []
    cursor = from_day
    for _ in range(48):
        if cursor > to_day:
            break
        days.append(cursor)
        cursor = shift_day(cursor, 1)
    return days


PAGE_SPAN = 21


def page_range(today: str, page: int) -> dict:
    to_day = shift_day(today, -page * PAGE_SPAN)
    from_day = shift_day(to_day, -(PAGE_SPAN - 1))
    return {"from": from_day, "to": to_day}
