from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.enums import AccessStatus
from src.service.access import AccessService
from src.service.errors import ForbiddenError, ValidationError
from src.service.scheduler import SchedulerService
from src.service.user import UserService
from tests.conftest import FakeNotifier, World

RUN = datetime(2026, 10, 18, 4, 0, tzinfo=UTC)


async def test_request_is_created_once(session: AsyncSession) -> None:
    service = AccessService(session)
    first = await service.request(555, "Иван", "ivan")
    again = await service.request(555, "Иван", "ivan")
    assert first.created and not again.created
    assert first.entry.status is AccessStatus.PENDING
    assert first.entry.label == "Иван (@ivan)"
    assert not await service.is_allowed(555)


async def test_allow_by_chat_id_before_any_message(session: AsyncSession) -> None:
    entry = await AccessService(session).allow(777, by_chat_id=1)
    assert entry.is_allowed and entry.decided_by_chat_id == 1
    assert entry.label == "без имени"


async def test_admins(session: AsyncSession) -> None:
    service = AccessService(session)
    await service.set_admin(1, True)
    assert await service.admin_chat_ids() == [1]
    with pytest.raises(ValidationError):
        await service.set_admin(1, False)  # the last admin
    await service.set_admin(2, True)
    await service.set_admin(1, False)
    assert await service.admin_chat_ids() == [2]


async def test_deny_rules(session: AsyncSession) -> None:
    service = AccessService(session)
    await service.set_admin(1, True)
    await service.allow(5, by_chat_id=1)
    with pytest.raises(ForbiddenError):
        await service.deny(1, by_chat_id=1)  # yourself
    await service.set_admin(2, True)
    with pytest.raises(ForbiddenError):
        await service.deny(2, by_chat_id=1)  # another admin
    entry = await service.deny(5, by_chat_id=1)
    assert entry.status is AccessStatus.DENIED


async def test_revoked_user_is_hidden_and_gets_nothing(
    session: AsyncSession, world: World, notifier: FakeNotifier
) -> None:
    await AccessService(session).deny(111, by_chat_id=1)
    assert await UserService(session).list_users() == []
    assert await UserService(session).get(world.user.id) is None

    report = await SchedulerService(session, notifier, timedelta(hours=2)).tick(RUN)
    assert report.sent == 0 and notifier.sent == []

    await AccessService(session).allow(111, by_chat_id=1)
    report = await SchedulerService(session, notifier, timedelta(hours=2)).tick(RUN)
    assert report.sent == 1
