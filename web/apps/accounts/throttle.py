"""Bloqueio progressivo de login por IP + e-mail, guardado no Redis."""

from apps.core import redis as r

LIMIT = 5
WINDOW = 15 * 60


def _key(ip: str, email: str) -> str:
    return f"login:fail:{ip}:{email.lower()}"


def blocked(ip: str, email: str) -> bool:
    try:
        return int(r.client().get(_key(ip, email)) or 0) >= LIMIT
    except Exception:
        return False


def fail(ip: str, email: str) -> None:
    try:
        conn = r.client()
        key = _key(ip, email)
        if conn.incr(key) == 1:
            conn.expire(key, WINDOW)
    except Exception:
        pass


def reset(ip: str, email: str) -> None:
    try:
        r.client().delete(_key(ip, email))
    except Exception:
        pass


def client_ip(request) -> str:
    return request.META.get("REMOTE_ADDR", "") or "?"
