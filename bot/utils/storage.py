import json
import os
from datetime import datetime
from typing import Any

STORAGE_FILE = os.path.join(os.path.dirname(__file__), "..", "data.json")
STORAGE_FILE = os.path.abspath(STORAGE_FILE)


def _default() -> dict:
    return {"giveaways": {}, "guild_roles": {}}


def _load_raw() -> dict:
    if not os.path.exists(STORAGE_FILE):
        return _default()
    try:
        with open(STORAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return _default()


def _save_raw(data: dict) -> None:
    os.makedirs(os.path.dirname(STORAGE_FILE), exist_ok=True)
    with open(STORAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def save_giveaway(g: Any) -> None:
    data = _load_raw()
    data["giveaways"][g.message_id] = {
        "message_id": g.message_id,
        "channel_id": g.channel_id,
        "guild_id": g.guild_id,
        "prize": g.prize,
        "winners_count": g.winners_count,
        "ends_at": g.ends_at.isoformat(),
        "hosted_by": g.hosted_by,
        "entries": list(g.entries),
        "ended": g.ended,
        "cancelled": g.cancelled,
        "paused": g.paused,
        "remaining_ms": g.remaining_ms,
    }
    _save_raw(data)


def delete_giveaway(message_id: str) -> None:
    data = _load_raw()
    data["giveaways"].pop(message_id, None)
    _save_raw(data)


def load_all_giveaways() -> list[dict]:
    return list(_load_raw()["giveaways"].values())


def save_guild_roles(guild_id: str, role_ids: list[str]) -> None:
    data = _load_raw()
    if role_ids:
        data["guild_roles"][guild_id] = role_ids
    else:
        data["guild_roles"].pop(guild_id, None)
    _save_raw(data)


def load_all_guild_roles() -> dict[str, list[str]]:
    return _load_raw().get("guild_roles", {})
