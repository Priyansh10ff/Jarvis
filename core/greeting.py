"""Build the startup greeting from the clock and system state."""
from __future__ import annotations

from datetime import datetime


def _part_of_day(hour: int) -> str:
    if 5 <= hour < 12:
        return "Good morning"
    if 12 <= hour < 17:
        return "Good afternoon"
    if 17 <= hour < 22:
        return "Good evening"
    return "Working late"


def _battery_line() -> str | None:
    try:
        import psutil

        battery = psutil.sensors_battery()
    except Exception:
        return None
    if battery is None:  # desktop, no battery
        return None
    pct = round(battery.percent)
    if battery.power_plugged:
        return f"Battery at {pct} percent, charging."
    if pct <= 20:
        return f"Battery is low, {pct} percent. You may want to plug in."
    return f"Battery at {pct} percent."


def build_greeting(user: str, assistant: str, now: datetime | None = None) -> str:
    now = now or datetime.now()
    clock = now.strftime("%I:%M %p").lstrip("0")
    parts = [
        f"{_part_of_day(now.hour)}, {user}.",
        f"It's {clock}, {now.strftime('%A')}.",
    ]
    battery = _battery_line()
    if battery:
        parts.append(battery)
    parts.append(f"{assistant} is online.")
    return " ".join(parts)
