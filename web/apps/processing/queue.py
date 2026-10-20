"""Filas do processamento sobre Redis Streams.

Cada etapa tem um stream com um grupo de consumidores. Retentativas com espera ficam num ZSET e voltam para o
stream quando vencem. O estado de verdade fica no PostgreSQL: se o Redis for apagado, a varredura do worker
encontra documentos parados e os coloca na fila de novo.
"""

import json
import time

from redis.exceptions import ResponseError

from apps.core import redis as r

EXTRACT = "docs:extract"
DESCRIBE = "docs:describe"
STREAMS = {"extract": EXTRACT, "describe": DESCRIBE}
DELAYED = "docs:delayed"
GROUP = "workers"
MAXLEN = 10_000


def ensure_groups(conn=None) -> None:
    conn = conn or r.client()
    for stream in STREAMS.values():
        try:
            conn.xgroup_create(stream, GROUP, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise


def enqueue(stage: str, document_id, conn=None) -> str:
    conn = conn or r.client()
    return conn.xadd(STREAMS[stage], {"document_id": str(document_id)}, maxlen=MAXLEN, approximate=True)


def enqueue_later(stage: str, document_id, delay_seconds: float, conn=None) -> None:
    conn = conn or r.client()
    member = json.dumps({"stage": stage, "document_id": str(document_id)})
    conn.zadd(DELAYED, {member: time.time() + delay_seconds})


def release_due(conn=None, now: float | None = None, limit: int = 100) -> int:
    """Move para o stream as retentativas cuja espera já venceu. Seguro com vários workers ao mesmo tempo."""
    conn = conn or r.client()
    now = now or time.time()
    moved = 0
    for member in conn.zrangebyscore(DELAYED, "-inf", now, start=0, num=limit):
        if conn.zrem(DELAYED, member):  # só quem conseguiu remover publica
            item = json.loads(member)
            enqueue(item["stage"], item["document_id"], conn)
            moved += 1
    return moved


def backoff(attempt: int, base: float = 5.0, cap: float = 300.0) -> float:
    return min(cap, base * (3 ** max(attempt - 1, 0)))


def stats(conn=None) -> dict:
    conn = conn or r.client()
    result = {}
    for stage, stream in STREAMS.items():
        try:
            length = conn.xlen(stream)
            pending = conn.xpending(stream, GROUP)["pending"]
            groups = conn.xinfo_groups(stream)
            lag = next((g.get("lag") for g in groups if g["name"] == GROUP), None)
        except ResponseError:
            length, pending, lag = 0, 0, None
        result[stage] = {"length": length, "pending": pending, "waiting": lag}
    result["delayed"] = conn.zcard(DELAYED)
    return result
