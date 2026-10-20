import asyncio
import json

from channels.generic.websocket import AsyncWebsocketConsumer

from apps.core.events import SHARED_CHANNEL, USER_CHANNEL
from apps.realtime.hub import hub


class EventsConsumer(AsyncWebsocketConsumer):
    """Envia ao navegador os avisos de mudança dos documentos do usuário e dos compartilhados."""

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        self.user_id = str(user.id)
        self.queue = hub.subscribe([USER_CHANNEL.format(self.user_id), SHARED_CHANNEL])
        await self.accept()
        await self.send(text_data=json.dumps({"type": "hello"}))
        self.pump = asyncio.create_task(self.forward())

    async def forward(self):
        while True:
            payload = await self.queue.get()
            if payload.get("only_shared") and payload.get("owner_id") == self.user_id:
                continue
            await self.send(text_data=json.dumps(payload))

    async def receive(self, text_data=None, bytes_data=None):
        if text_data == "ping":
            await self.send(text_data='{"type":"pong"}')

    async def disconnect(self, code):
        if hasattr(self, "pump"):
            self.pump.cancel()
        if hasattr(self, "queue"):
            hub.unsubscribe(self.queue)
