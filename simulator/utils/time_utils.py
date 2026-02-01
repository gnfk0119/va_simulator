from datetime import datetime, timedelta


def add_minutes(hhmm: str, minutes: int) -> str:
    base = datetime.strptime(hhmm, "%H:%M")
    new_time = base + timedelta(minutes=minutes)
    return new_time.strftime("%H:%M")
