import asyncio
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from utils.storage import save_giveaway, load_all_giveaways


@dataclass
class Giveaway:
    message_id: str
    channel_id: str
    guild_id: str
    prize: str
    winners_count: int
    ends_at: datetime
    hosted_by: str
    entries: set = field(default_factory=set)
    ended: bool = False
    cancelled: bool = False
    paused: bool = False
    paused_at: Optional[datetime] = None
    remaining_ms: Optional[int] = None
    task: Optional[asyncio.Task] = None


_giveaways: dict[str, Giveaway] = {}


def create_giveaway(
    message_id: str,
    channel_id: str,
    guild_id: str,
    prize: str,
    winners_count: int,
    ends_at: datetime,
    hosted_by: str,
) -> Giveaway:
    g = Giveaway(
        message_id=message_id,
        channel_id=channel_id,
        guild_id=guild_id,
        prize=prize,
        winners_count=winners_count,
        ends_at=ends_at,
        hosted_by=hosted_by,
    )
    _giveaways[message_id] = g
    return g


def get_giveaway(message_id: str) -> Optional[Giveaway]:
    return _giveaways.get(message_id)


def update_message_id(old_id: str, new_id: str) -> None:
    g = _giveaways.pop(old_id, None)
    if g:
        g.message_id = new_id
        _giveaways[new_id] = g
        save_giveaway(g)


def get_all_giveaways() -> list[Giveaway]:
    return list(_giveaways.values())


def get_active_by_guild(guild_id: str) -> list[Giveaway]:
    return [
        g for g in _giveaways.values()
        if g.guild_id == guild_id and not g.ended and not g.cancelled
    ]


def add_entry(message_id: str, user_id: str) -> bool:
    g = _giveaways.get(message_id)
    if not g or g.ended or g.cancelled or g.paused:
        return False
    if user_id in g.entries:
        return False
    g.entries.add(user_id)
    save_giveaway(g)
    return True


def remove_entry(message_id: str, user_id: str) -> bool:
    g = _giveaways.get(message_id)
    if not g or g.ended or g.cancelled:
        return False
    if user_id not in g.entries:
        return False
    g.entries.discard(user_id)
    save_giveaway(g)
    return True


def mark_ended(message_id: str) -> None:
    g = _giveaways.get(message_id)
    if not g:
        return
    g.ended = True
    if g.task and not g.task.done():
        g.task.cancel()
    g.task = None
    save_giveaway(g)


def cancel_giveaway(message_id: str) -> bool:
    g = _giveaways.get(message_id)
    if not g or g.ended or g.cancelled:
        return False
    g.cancelled = True
    if g.task and not g.task.done():
        g.task.cancel()
    g.task = None
    save_giveaway(g)
    return True


def pause_giveaway(message_id: str) -> bool:
    g = _giveaways.get(message_id)
    if not g or g.ended or g.cancelled or g.paused:
        return False
    g.paused = True
    g.paused_at = datetime.utcnow()
    g.remaining_ms = max(0, int((g.ends_at - datetime.utcnow()).total_seconds() * 1000))
    if g.task and not g.task.done():
        g.task.cancel()
    g.task = None
    save_giveaway(g)
    return True


def resume_giveaway(message_id: str, on_end, loop: asyncio.AbstractEventLoop) -> bool:
    g = _giveaways.get(message_id)
    if not g or not g.paused or g.ended or g.cancelled:
        return False
    remaining_s = (g.remaining_ms or 0) / 1000
    g.ends_at = datetime.utcnow() + timedelta(seconds=remaining_s)
    g.paused = False
    g.paused_at = None
    g.remaining_ms = None

    async def _wait_and_end():
        await asyncio.sleep(remaining_s)
        await on_end(message_id)

    g.task = loop.create_task(_wait_and_end())
    save_giveaway(g)
    return True


def pick_winners(message_id: str, count: Optional[int] = None) -> list[str]:
    g = _giveaways.get(message_id)
    if not g:
        return []
    pool = list(g.entries)
    n = count if count is not None else g.winners_count
    if not pool:
        return []
    return random.sample(pool, min(n, len(pool)))


def restore_giveaways(on_end, loop: asyncio.AbstractEventLoop) -> int:
    """Load persisted giveaways from disk. Returns number restored."""
    records = load_all_giveaways()
    restored = 0
    now = datetime.utcnow()

    for r in records:
        ends_at = datetime.fromisoformat(r["ends_at"])
        g = Giveaway(
            message_id=r["message_id"],
            channel_id=r["channel_id"],
            guild_id=r["guild_id"],
            prize=r["prize"],
            winners_count=r["winners_count"],
            ends_at=ends_at,
            hosted_by=r["hosted_by"],
            entries=set(r.get("entries", [])),
            ended=r.get("ended", False),
            cancelled=r.get("cancelled", False),
            paused=r.get("paused", False),
            remaining_ms=r.get("remaining_ms"),
        )
        _giveaways[g.message_id] = g

        if not g.ended and not g.cancelled and not g.paused:
            remaining_s = (g.ends_at - now).total_seconds()
            if remaining_s <= 0:
                remaining_s = 0.1

            async def _wait_and_end(mid=g.message_id, delay=remaining_s):
                await asyncio.sleep(delay)
                await on_end(mid)

            g.task = loop.create_task(_wait_and_end())

        restored += 1

    return restored


def parse_duration(duration_str: str) -> Optional[int]:
    """Parse duration strings like 10s, 5m, 2h, 1d into milliseconds."""
    duration_str = duration_str.strip().lower()
    units = {"s": 1000, "m": 60_000, "h": 3_600_000, "d": 86_400_000}
    if not duration_str:
        return None
    unit = duration_str[-1]
    if unit not in units:
        return None
    try:
        value = int(duration_str[:-1])
    except ValueError:
        return None
    if value <= 0:
        return None
    return value * units[unit]


def format_duration(ms: int) -> str:
    seconds = ms // 1000
    days = seconds // 86400
    seconds %= 86400
    hours = seconds // 3600
    seconds %= 3600
    minutes = seconds // 60
    seconds %= 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)
