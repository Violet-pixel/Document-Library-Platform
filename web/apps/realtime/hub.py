"""Distribuidor de eventos por processo: uma única assinatura no Redis atende todas as conexões WebSocket."""

import asyncio
import json
import logging

from apps.core import redis as r

log = logging.getLogger(__name__)


class Hub:
    def __init__(self):
        self.listeners: dict[str, set[asyncio.Queue]] = {}
        self.task: asyncio.Task | None = None

    def subscribe(self, channels: list[str]) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        for channel in channels:
            self.listeners.setdefault(channel, set()).add(q)
        if self.task is None or self.task.done():
            self.task = asyncio.get_running_loop().create_task(self.listen())
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        for channel in list(self.listeners):
            self.listeners[channel].discard(q)
            if not self.listeners[channel]:
                del self.listeners[channel]

    async def listen(self) -> None:
        delay = 1
        while True:
            conn = r.async_client()
            try:
                async with conn.pubsub() as pubsub:
                    await pubsub.psubscribe("events:*")
                    delay = 1
                    async for message in pubsub.listen():
                        if message.get("type") == "pmessage":
                            self.dispatch(message["channel"], message["data"])
            except asyncio.CancelledError:
                raise
            except Exception:
                log.warning("Conexão de eventos com o Redis caiu; reconectando em %s s", delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)
            finally:
                await conn.aclose()

    def dispatch(self, channel: str, data: str) -> None:
        try:
            payload = json.loads(data)
        except ValueError:
            return
        for q in list(self.listeners.get(channel, ())):
            if q.full():
                continue  # cliente lento: perde o aviso, mas recarrega ao reconectar
            q.put_nowait(payload)


hub = Hub()
