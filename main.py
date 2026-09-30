import json
import os
import sys

import yfinance as yf

from gex import compute_gex
from notify import send_discord_message
from forex_factory import fetch_calendar, filter_events, due_reminders, IMPACT_TO_FOLDER

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_state(path):
    if os.path.exists(path):
        with open(path) as f:
            state = json.load(f)
    else:
        state = {}
    state.setdefault("fired_levels", [])
    state.setdefault("fired_news", [])
    state.setdefault("last_gamma_flip", None)
    return state


def save_state(path, state):
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def check_price_alerts(config, state, webhook_url):
    if not webhook_url:
        return
    ticker = yf.Ticker(config["price_ticker"])
    price = float(ticker.fast_info["last_price"])

    for level in config["price_alert_levels"]:
        key = f"{level['label']}:{level['price']}:{level['direction']}"
        already_fired = key in state["fired_levels"]

        crossed = (
            level["direction"] == "above" and price >= level["price"]
        ) or (
            level["direction"] == "below" and price <= level["price"]
        )

        if crossed and not already_fired:
            send_discord_message(
                webhook_url,
                content=None,
                embed_title=f"🔔 Price Alert: {level['label']}",
                embed_fields={
                    "Ticker": config["price_ticker"],
                    "Current Price": round(price, 2),
                    "Level": level["price"],
                    "Direction": level["direction"],
                },
            )
            state["fired_levels"].append(key)
        elif not crossed and already_fired:
            state["fired_levels"].remove(key)  # allow it to re-fire later


def post_gex_update(config, state, webhook_url):
    if not webhook_url:
        return
    result = compute_gex(
        config["gex_ticker"],
        risk_free_rate=config.get("risk_free_rate", 0.05),
        num_expirations=config.get("gex_expirations_to_use", 2),
    )

    state["last_gamma_flip"] = result["gamma_flip"]
    regime = "unknown"
    if result["gamma_flip"] is not None:
        regime = "POSITIVE (calmer)" if result["spot"] > result["gamma_flip"] else "NEGATIVE (choppier)"

    send_discord_message(
        webhook_url,
        content=None,
        embed_title=f"📊 GEX Update: {config['gex_ticker']}",
        embed_fields={
            "Spot": round(result["spot"], 2),
            "Regime": regime,
            "Gamma Flip": round(result["gamma_flip"], 2) if result["gamma_flip"] else "n/a",
            "Call Wall": result["call_wall"],
            "Put Wall": result["put_wall"],
            "Net GEX": f"{result['total_gex']:.3e}",
            "Expirations used": config.get("gex_expirations_to_use", 2),
        },
    )


def post_news_reminders(config, state, webhook_url):
    if not webhook_url:
        return
    ff_config = config.get("forex_factory", {})

    events = fetch_calendar()
    filtered = filter_events(
        events,
        impact_filters=ff_config.get("impact_filters"),
        currency_filters=ff_config.get("currency_filters"),
    )
    due = due_reminders(
        filtered,
        hours_before=ff_config.get("hours_before_reminder", 2),
        remind_day_of=ff_config.get("remind_day_of", True),
    )

    for event, reminder_type in due:
        key = f"{event.get('title')}|{event.get('country')}|{event.get('date')}|{reminder_type}"
        if key in state["fired_news"]:
            continue

        folder = IMPACT_TO_FOLDER.get(event.get("impact"), "unknown")
        label = "Today" if reminder_type == "day_of" else f"In ~{ff_config.get('hours_before_reminder', 2)}h"
        send_discord_message(
            webhook_url,
            content=None,
            embed_title=f"🗞️ {label}: {event.get('title')}",
            embed_fields={
                "Currency": event.get("country"),
                "Impact": f"{event.get('impact')} ({folder} folder)",
                "Time (UTC)": event.get("date"),
                "Forecast": event.get("forecast") or "n/a",
                "Previous": event.get("previous") or "n/a",
            },
        )
        state["fired_news"].append(key)


def main():
    config = load_config()

    webhook_price = os.environ.get("DISCORD_WEBHOOK_PRICE")
    webhook_news = os.environ.get("DISCORD_WEBHOOK_NEWS")
    webhook_gex = os.environ.get("DISCORD_WEBHOOK_GEX")

    if not any([webhook_price, webhook_news, webhook_gex]):
        print("ERROR: set at least one of DISCORD_WEBHOOK_PRICE / _NEWS / _GEX.")
        sys.exit(1)

    state_path = config.get("poll_state_file", "state.json")
    state = load_state(state_path)

    check_price_alerts(config, state, webhook_price)
    post_gex_update(config, state, webhook_gex)
    post_news_reminders(config, state, webhook_news)

    save_state(state_path, state)


if __name__ == "__main__":
    main()
