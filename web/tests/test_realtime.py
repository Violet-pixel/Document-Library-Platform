import asyncio

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser

from apps.core import events
from apps.realtime.consumers import EventsConsumer
from apps.realtime.hub import hub

pytestmark = pytest.mark.django_db(transaction=True)


async def connect(user):
    communicator = WebsocketCommunicator(EventsConsumer.as_asgi(), "/ws/events")
    communicator.scope["user"] = user
    connected, code = await communicator.connect()
    return communicator, connected, code


async def test_anonymous_is_rejected():
    communicator, connected, code = await connect(AnonymousUser())
    assert not connected and code == 4401


async def test_user_receives_own_and_shared_events(user, other):
    communicator, connected, _ = await connect(user)
    assert connected
    assert (await communicator.receive_json_from())["type"] == "hello"
    await asyncio.sleep(0.3)  # assinatura no Redis
    await database_sync_to_async(events.publish)(user.id, "document.updated", id="1", status="ready")
    await database_sync_to_async(events.publish)(other.id, "document.updated", id="2", status="ready")
    await database_sync_to_async(events.publish)(other.id, "document.created", shared=True, id="3")
    first = await communicator.receive_json_from(timeout=3)
    second = await communicator.receive_json_from(timeout=3)
    assert {first["id"], second["id"]} == {"1", "3"}
    assert await communicator.receive_nothing(timeout=0.5)
    await communicator.send_to(text_data="ping")
    assert (await communicator.receive_json_from())["type"] == "pong"
    await communicator.disconnect()
    if hub.task:
        hub.task.cancel()
