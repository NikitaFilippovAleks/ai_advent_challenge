"""Репозиторий для CRUD-операций с профилями."""

import uuid

from sqlalchemy import select, update

from app.core.database import _now_iso, async_session
from app.models import UserProfile


async def create_profile(name: str, system_prompt: str, is_default: bool = False) -> dict:
    """Создаёт профиль. Если is_default=True — снимает флаг с остальных в одной транзакции."""
    now = _now_iso()
    profile = UserProfile(
        id=str(uuid.uuid4()),
        name=name,
        system_prompt=system_prompt,
        is_default=is_default,
        created_at=now,
        updated_at=now,
    )
    async with async_session() as session:
        if is_default:
            await session.execute(
                update(UserProfile).where(UserProfile.is_default == True).values(is_default=False)
            )
        session.add(profile)
        await session.commit()
    return _profile_to_dict(profile)


async def list_profiles() -> list[dict]:
    """Возвращает все профили, отсортированные по имени."""
    async with async_session() as session:
        result = await session.execute(
            select(UserProfile).order_by(UserProfile.name)
        )
        rows = result.scalars().all()
    return [_profile_to_dict(r) for r in rows]


async def get_profile(profile_id: str) -> dict | None:
    """Возвращает профиль по ID или None."""
    async with async_session() as session:
        profile = await session.get(UserProfile, profile_id)
    if profile is None:
        return None
    return _profile_to_dict(profile)


async def get_default_profile() -> dict | None:
    """Возвращает дефолтный профиль или None."""
    async with async_session() as session:
        result = await session.execute(
            select(UserProfile).where(UserProfile.is_default == True)
        )
        profile = result.scalar_one_or_none()
    if profile is None:
        return None
    return _profile_to_dict(profile)


async def update_profile(profile_id: str, **fields) -> dict | None:
    """Обновляет поля профиля. Если is_default=True — снимает флаг с остальных в одной транзакции."""
    async with async_session() as session:
        profile = await session.get(UserProfile, profile_id)
        if profile is None:
            return None

        if fields.get("is_default"):
            await session.execute(
                update(UserProfile).where(UserProfile.is_default == True).values(is_default=False)
            )

        for key, value in fields.items():
            if value is not None:
                setattr(profile, key, value)
        profile.updated_at = _now_iso()
        await session.commit()
    return _profile_to_dict(profile)


async def delete_profile(profile_id: str) -> bool:
    """Удаляет профиль. Возвращает True если удалён."""
    async with async_session() as session:
        profile = await session.get(UserProfile, profile_id)
        if profile is None:
            return False
        await session.delete(profile)
        await session.commit()
    return True


def _profile_to_dict(profile: UserProfile) -> dict:
    """Конвертирует ORM-объект в словарь."""
    return {
        "id": profile.id,
        "name": profile.name,
        "system_prompt": profile.system_prompt,
        "is_default": bool(profile.is_default),
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }
