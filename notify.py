"""
Posts messages to Discord via a webhook URL.

This is NOT a Discord bot (no bot token, no gateway connection, no hosting
required) - it's the simplest possible way to get messages into a channel.
Create one at: Server Settings -> Integrations -> Webhooks -> New Webhook.
"""

import requests


def send_discord_message(webhook_url, content, embed_title=None, embed_fields=None):
    if embed_title or embed_fields:
        embed = {"title": embed_title or "", "fields": []}
        for name, value in (embed_fields or {}).items():
            embed["fields"].append({"name": name, "value": str(value), "inline": True})
        payload = {"embeds": [embed]}
        if content:
            payload["content"] = content
    else:
        payload = {"content": content}

    response = requests.post(webhook_url, json=payload, timeout=10)
    response.raise_for_status()
