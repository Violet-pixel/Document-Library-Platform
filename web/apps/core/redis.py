"""Conexões Redis compartilhadas (uma por processo)."""

from functools import lru_cache

import redis
import redis.asyncio as aioredis
from django.conf import settings


@lru_cache(maxsize=1)
def client() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True, health_check_interval=30)


def async_client() -> aioredis.Redis:
    return aioredis.Redis.from_url(settings.REDIS_URL, decode_responses=True, health_check_interval=30)
