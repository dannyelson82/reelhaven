"""Space saved over the life of the install (ADR-0026). The aggregation is pure.

Every job that replaced a file records its size before and after; that
difference is the saving, dated when the job finished. Restoring an original
from the recycle bin takes that job's saving back out; restoring ReelHaven's
version again (a "restore-swap" item) puts the difference back. Weeks start on
Monday and both weeks and months use the server's local time.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

PERIODS = 12


@dataclass(frozen=True)
class Event:
    at: datetime  # naive local time
    library_id: int
    saved: int  # bytes; negative when a restore gives space back
    files: int  # +1 for a file made smaller, -1 when it is restored


@dataclass
class Period:
    start: date
    saved: int = 0
    files: int = 0


@dataclass
class LibrarySavings:
    library_id: int
    saved: int = 0
    files: int = 0


@dataclass
class Savings:
    total_saved: int
    files: int
    this_week: int
    this_month: int
    weekly: list[Period]  # oldest first, the current week last
    monthly: list[Period]
    libraries: list[LibrarySavings]


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def month_start(day: date) -> date:
    return day.replace(day=1)


def _months_back(start: date, n: int) -> date:
    year, month = divmod(start.year * 12 + start.month - 1 - n, 12)
    return date(year, month + 1, 1)


def summarise(events: list[Event], now: datetime) -> Savings:
    this_week = week_start(now.date())
    this_month = month_start(now.date())
    weekly = {
        this_week - timedelta(weeks=n): Period(this_week - timedelta(weeks=n))
        for n in range(PERIODS)
    }
    monthly = {
        _months_back(this_month, n): Period(_months_back(this_month, n)) for n in range(PERIODS)
    }
    libraries: dict[int, LibrarySavings] = {}
    total = files = 0
    for event in events:
        total += event.saved
        files += event.files
        lib = libraries.setdefault(event.library_id, LibrarySavings(event.library_id))
        lib.saved += event.saved
        lib.files += event.files
        for bucket in (
            weekly.get(week_start(event.at.date())),
            monthly.get(month_start(event.at.date())),
        ):
            if bucket is not None:
                bucket.saved += event.saved
                bucket.files += event.files
    return Savings(
        total_saved=total,
        files=files,
        this_week=weekly[this_week].saved,
        this_month=monthly[this_month].saved,
        weekly=sorted(weekly.values(), key=lambda p: p.start),
        monthly=sorted(monthly.values(), key=lambda p: p.start),
        libraries=sorted(libraries.values(), key=lambda lib: -lib.saved),
    )
