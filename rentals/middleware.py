import logging
import time


logger = logging.getLogger('rentals.requests')


class RequestTimingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.monotonic()
        response = self.get_response(request)
        elapsed_ms = round((time.monotonic() - started) * 1000, 2)
        logger.info(
            '%s %s %s %.2fms',
            request.method,
            request.path,
            response.status_code,
            elapsed_ms,
        )
        response['X-Response-Time-ms'] = str(elapsed_ms)
        return response
