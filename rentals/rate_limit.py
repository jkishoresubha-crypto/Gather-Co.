import logging

from django.core.cache import cache


logger = logging.getLogger('rentals')


def limited(request, scope, limit=10, seconds=60):
    ip = request.META.get('REMOTE_ADDR', 'unknown')
    key = f'rate:{scope}:{ip}'
    try:
        if cache.add(key, 1, timeout=seconds):
            return False
        return cache.incr(key) > limit
    except (ValueError, NotImplementedError):
        logger.exception('Rate limiter cache backend does not support atomic counters.')
        return False
