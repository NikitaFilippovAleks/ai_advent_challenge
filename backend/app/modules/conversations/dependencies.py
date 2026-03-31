"""DI-зависимости модуля conversations.

Единственное место для кросс-модульного импорта в этом модуле.
"""

from app.modules.profiles.repository import get_default_profile, get_profile


async def resolve_conversation_profile(profile_id: str | None) -> dict:
    """Определяет профиль диалога: явный, дефолтный или none."""
    if profile_id:
        profile = await get_profile(profile_id)
        if profile:
            return {"profile": profile, "source": "explicit"}

    default = await get_default_profile()
    if default:
        return {"profile": default, "source": "default"}

    return {"profile": None, "source": "none"}
