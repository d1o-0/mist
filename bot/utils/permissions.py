import discord

from utils.storage import save_guild_roles, load_all_guild_roles

_guild_roles: dict[str, set[str]] = {}


def load_roles() -> None:
    """Load persisted guild roles from disk."""
    for guild_id, role_ids in load_all_guild_roles().items():
        _guild_roles[guild_id] = set(role_ids)


def add_giveaway_role(guild_id: str, role_id: str) -> None:
    roles = _guild_roles.setdefault(guild_id, set())
    roles.add(role_id)
    save_guild_roles(guild_id, list(roles))


def remove_giveaway_role(guild_id: str, role_id: str) -> bool:
    roles = _guild_roles.get(guild_id)
    if not roles:
        return False
    if role_id not in roles:
        return False
    roles.discard(role_id)
    if not roles:
        del _guild_roles[guild_id]
    save_guild_roles(guild_id, list(roles))
    return True


def get_giveaway_roles(guild_id: str) -> list[str]:
    return list(_guild_roles.get(guild_id, set()))


def clear_giveaway_roles(guild_id: str) -> None:
    _guild_roles.pop(guild_id, None)
    save_guild_roles(guild_id, [])


def can_manage_giveaways(member: discord.Member, guild_id: str) -> bool:
    if member.guild_permissions.administrator:
        return True
    if member.guild_permissions.manage_guild:
        return True
    roles = _guild_roles.get(guild_id)
    if not roles:
        return False
    return any(str(r.id) in roles for r in member.roles)


def can_configure_permissions(member: discord.Member) -> bool:
    return member.guild_permissions.administrator
