"""Eventos em tempo real: publicados no Redis e entregues aos navegadores pelo WebSocket.

O evento só avisa o que mudou; o navegador busca o documento de novo pela API, com as próprias permissões.
"""

import json
import logging

from apps.core import redis as r

log = logging.getLogger(__name__)

USER_CHANNEL = "events:user:{}"
SHARED_CHANNEL = "events:shared"


def publish(user_id, event_type: str, shared: bool = False, **data) -> None:
    payload = json.dumps({"type": event_type, **data}, default=str)
    try:
        conn = r.client()
        conn.publish(USER_CHANNEL.format(user_id), payload)
        if shared:
            conn.publish(SHARED_CHANNEL, payload)
    except Exception:  # o evento é um aviso; falhar aqui não pode derrubar a requisição
        log.warning("Falha ao publicar evento %s", event_type, exc_info=True)


def document_event(document, event_type: str = "document.updated") -> None:
    publish(
        document.owner_id,
        event_type,
        shared=document.visibility == "shared",
        id=str(document.id),
        status=document.status,
        owner_id=str(document.owner_id),
    )
