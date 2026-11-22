import logging
from urllib.parse import urlsplit

from fastapi import HTTPException
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

from app.auth.config import get_settings
from app.services.card_images import MAX_IMAGE_DATA_URL_LENGTH

AUTH_BODY_LIMIT = 16 * 1024
API_BODY_LIMIT = 64 * 1024
CARD_BODY_LIMIT = 2 * MAX_IMAGE_DATA_URL_LENGTH + 256 * 1024
logger = logging.getLogger(__name__)


def is_card_write(method, path):
    parts = path.strip('/').split('/')
    return (method == 'POST' and len(parts) == 4 and parts[:2] == ['api', 'decks'] and parts[3] == 'cards'
            or method == 'PATCH' and len(parts) == 3 and parts[:2] == ['api', 'cards'])


class PrivateResponseHeaders:
    """Apply limits before parsing and keep raw request data out of server errors."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        path = scope['path'].rstrip('/')
        headers = Headers(scope=scope)
        settings = get_settings()
        started = False

        async def send_private(message):
            nonlocal started
            if message['type'] == 'http.response.start':
                started = True
                outgoing = MutableHeaders(scope=message)
                if path.startswith('/api/'):
                    outgoing['Cache-Control'] = 'no-store'
                    outgoing.add_vary_header('Cookie')
                outgoing['X-Content-Type-Options'] = 'nosniff'
                outgoing['Referrer-Policy'] = 'same-origin'
            await send(message)

        async def reject(status, message):
            await JSONResponse({'error': {'message': message}}, status_code=status)(scope, receive, send_private)

        if settings.environment == 'production':
            if path in {'/docs', '/docs/oauth2-redirect', '/redoc', '/openapi.json',
                        '/gwa/docs', '/gwa/docs/oauth2-redirect',
                        '/gwa/redoc', '/gwa/openapi.json'}:
                await reject(404, 'Not found.')
                return
            if (path not in {'/api/health', '/api/gwa/health'} and
                    headers.get('host', '').lower() not in {urlsplit(origin).netloc.lower() for origin in settings.trusted_origins}):
                await reject(400, 'Invalid request host.')
                return

        if len(scope.get('query_string', b'')) > 8192:
            await reject(414, 'Request query is too large.')
            return

        limit = AUTH_BODY_LIMIT if path.startswith('/api/auth/') else (
            CARD_BODY_LIMIT if is_card_write(scope['method'], path) else API_BODY_LIMIT)
        length = headers.get('content-length')
        if length is not None and (not length.isascii() or not length.isdecimal() or len(length) > 12):
            await reject(400, 'Invalid request length.')
            return
        if length is not None and int(length) > limit:
            await reject(413, 'Request body is too large.')
            return

        received = 0

        async def receive_bounded():
            nonlocal received
            message = await receive()
            if message['type'] == 'http.request':
                received += len(message.get('body', b''))
                if received > limit:
                    raise HTTPException(413, 'Request body is too large.')
            return message

        try:
            await self.app(scope, receive_bounded, send_private)
        except Exception:
            # ServerErrorMiddleware re-raises after handling 500s; handle here so
            # the ASGI server cannot log tracebacks with SQL or request values.
            logger.error('Unhandled HTTP request error')
            if started:
                raise RuntimeError('HTTP response interrupted') from None
            await reject(500, 'An unexpected server error occurred.')
