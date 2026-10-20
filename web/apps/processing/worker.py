"""Worker do pipeline: consome os streams, roda as etapas, recupera mensagens perdidas e documentos parados."""

import logging
import os
import signal
import socket
import threading
import time
from datetime import timedelta

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError

from apps.core import redis as r
from apps.library.models import Document
from apps.processing import queue, stages

log = logging.getLogger("worker")

HEARTBEAT_KEY = "workers:{}"
HEARTBEAT_TTL = 30


class Worker:
    def __init__(self, stage_names=("extract", "describe"), threads: int | None = None):
        self.stage_names = list(stage_names)
        self.threads = threads or settings.PIPELINE["worker_threads"]
        self.name = f"{socket.gethostname()}-{os.getpid()}"
        self.stop = threading.Event()
        self.busy = 0
        self.processed = 0
        self.failed = 0
        self.lock = threading.Lock()
        self.started = time.time()

    # ---- ciclo de vida -------------------------------------------------------------------------------
    def run(self) -> None:
        signal.signal(signal.SIGTERM, lambda *_: self.stop.set())
        signal.signal(signal.SIGINT, lambda *_: self.stop.set())
        queue.ensure_groups()
        log.info("Worker %s iniciado: etapas %s, %s threads", self.name, ",".join(self.stage_names), self.threads)
        pool = [threading.Thread(target=self.consume, args=(i,), daemon=True) for i in range(self.threads)]
        for thread in pool:
            thread.start()
        last_maintenance = 0.0
        while not self.stop.is_set():
            self.heartbeat()
            if time.time() - last_maintenance > 30:
                self.maintenance()
                last_maintenance = time.time()
            self.stop.wait(5)
        log.info("Encerrando: esperando as tarefas em andamento terminarem")
        for thread in pool:
            thread.join(timeout=60)
        r.client().delete(HEARTBEAT_KEY.format(self.name))

    def consume(self, index: int) -> None:
        consumer = f"{self.name}-{index}"
        streams = {queue.STREAMS[s]: ">" for s in self.stage_names}
        stage_of = {v: k for k, v in queue.STREAMS.items()}
        conn = r.client()
        while not self.stop.is_set():
            try:
                queue.release_due(conn)
                batch = conn.xreadgroup(queue.GROUP, consumer, streams, count=1, block=2000)
                for stream, messages in batch or []:
                    for message_id, fields in messages:
                        self.execute(stage_of[stream], fields.get("document_id"), consumer)
                        conn.xack(stream, queue.GROUP, message_id)
            except RedisConnectionError:
                log.warning("Redis indisponível; tentando de novo em 3 s")
                self.stop.wait(3)
            except ResponseError as exc:
                if "NOGROUP" not in str(exc):
                    raise
                # Redis reiniciado sem persistência ou apagado: recria os grupos; a varredura recupera o resto.
                log.warning("Filas sumiram do Redis; recriando os grupos de consumidores")
                queue.ensure_groups(conn)
            except Exception:
                log.exception("Erro no laço de consumo; continuando em 2 s")
                self.stop.wait(2)

    def execute(self, stage: str, document_id: str | None, consumer: str) -> None:
        if not document_id:
            return
        close_old_connections()
        with self.lock:
            self.busy += 1
        started = time.monotonic()
        try:
            outcome = stages.handle(stage, document_id, consumer)
            if outcome.status != "skipped":
                log.info(
                    "%s %s: %s em %d ms%s",
                    stage,
                    document_id,
                    outcome.status,
                    (time.monotonic() - started) * 1000,
                    f" ({outcome.detail})" if outcome.detail else "",
                )
            with self.lock:
                self.processed += outcome.status == "done"
                self.failed += outcome.status == "failed"
        except Exception:
            log.exception("Erro inesperado em %s %s", stage, document_id)
            with self.lock:
                self.failed += 1
        finally:
            with self.lock:
                self.busy -= 1
            close_old_connections()

    # ---- manutenção ----------------------------------------------------------------------------------
    def heartbeat(self) -> None:
        try:
            key = HEARTBEAT_KEY.format(self.name)
            conn = r.client()
            conn.hset(
                key,
                mapping={
                    "name": self.name,
                    "stages": ",".join(self.stage_names),
                    "threads": self.threads,
                    "busy": self.busy,
                    "processed": self.processed,
                    "failed": self.failed,
                    "started": int(self.started),
                    "seen": int(time.time()),
                },
            )
            conn.expire(key, HEARTBEAT_TTL)
        except RedisConnectionError:
            pass

    def maintenance(self) -> None:
        try:
            reclaimed = self.reclaim()
            requeued = recover_stale()
            if reclaimed or requeued:
                log.info("Recuperação: %s mensagens reassumidas, %s documentos de volta à fila", reclaimed, requeued)
        except Exception:
            log.exception("Falha na manutenção")
        finally:
            close_old_connections()

    def reclaim(self) -> int:
        """Mensagens entregues a um worker que morreu: reassume e processa de novo."""
        conn = r.client()
        idle_ms = settings.PIPELINE["visibility_timeout"] * 1000
        count = 0
        queue.ensure_groups(conn)
        for stage in self.stage_names:
            stream = queue.STREAMS[stage]
            _, messages, _ = conn.xautoclaim(stream, queue.GROUP, f"{self.name}-reclaim", idle_ms, "0-0", count=50)
            for message_id, fields in messages:
                if fields:
                    queue.enqueue(stage, fields.get("document_id"), conn)
                conn.xack(stream, queue.GROUP, message_id)
                count += 1
        return count


def recover_stale() -> int:
    """Documentos parados há muito tempo (Redis apagado, worker morto antes de confirmar): voltam para a fila."""
    limit = timezone.now() - timedelta(seconds=settings.PIPELINE["stale_after"])
    count = 0
    stale = Document.objects.filter(
        status__in=[Document.Status.QUEUED, Document.Status.EXTRACTING, Document.Status.DESCRIBING],
        updated_at__lt=limit,
    ).only("id", "status")[:200]
    for document in stale:
        stage = "describe" if document.status == Document.Status.DESCRIBING else "extract"
        target = Document.Status.DESCRIBING if stage == "describe" else Document.Status.QUEUED
        updated = Document.objects.filter(pk=document.pk, status=document.status, updated_at__lt=limit).update(
            status=target, updated_at=timezone.now()
        )
        if updated:
            queue.enqueue(stage, document.id)
            count += 1
    return count


def workers_online() -> list[dict]:
    conn = r.client()
    result = []
    for key in conn.scan_iter("workers:*", count=100):
        data = conn.hgetall(key)
        if data:
            for field in ("threads", "busy", "processed", "failed", "started", "seen"):
                data[field] = int(data.get(field, 0))
            result.append(data)
    return sorted(result, key=lambda w: w["name"])
