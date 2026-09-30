"""
Forex Factory economic calendar - via their free public JSON feed.

This is the same feed Forex Factory's own calendar widget uses internally.
No API key, no login, no scraping of HTML - just a JSON GET request.
Feed refreshes on FF's side throughout the week as events/forecasts update.

Folder color -> impact field mapping (this is FF's own convention):
  red    = High
  orange = Medium
  yellow = Low
  gray   = Holiday / non-economic
"""

from datetime import datetime, timezone

import requests
from dateutil import parser as date_parser

FF_FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

IMPACT_TO_FOLDER = {
    "High": "red",
    "Medium": "orange",
    "Low": "yellow",
    "Holiday": "gray",
}


def fetch_calendar():
    headers = {"User-Agent": "Mozilla/5.0 (compatible; personal-alert-bot/1.0)"}
    resp = requests.get(FF_FEED_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _parse_event_time(event):
    dt = date_parser.parse(event["date"])
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def filter_events(events, impact_filters=None, currency_filters=None):
    """impact_filters: e.g. ["High", "Medium"] to only keep red/orange folders."""
    impact_filters = set(impact_filters) if impact_filters else None
    currency_filters = set(currency_filters) if currency_filters else None
    out = []
    for e in events:
        if impact_filters and e.get("impact") not in impact_filters:
            continue
        if currency_filters and e.get("country") not in currency_filters:
            continue
        out.append(e)
    return out


def due_reminders(events, hours_before=2, remind_day_of=True):
    """
    Returns [(event, reminder_type), ...] for events that should be reminded
    about RIGHT NOW. reminder_type is "day_of" or "hours_before".
    Caller de-duplicates repeats via state (a day_of reminder and an
    hours_before reminder for the same event are treated as distinct so
    both can fire).
    """
    now = datetime.now(timezone.utc)
    due = []
    for e in events:
        try:
            event_time = _parse_event_time(e)
        except Exception:
            continue

        seconds_until = (event_time - now).total_seconds()
        if seconds_until < 0:
            continue  # already happened

        if remind_day_of and event_time.date() == now.date():
            due.append((e, "day_of"))
        if 0 <= seconds_until <= hours_before * 3600:
            due.append((e, "hours_before"))
    return due
