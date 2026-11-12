"""Bound incoming JSON/multipart bytes before parsers allocate or spool them."""
from fastapi import HTTPException
from starlette.responses import JSONResponse


class BodyLimit:
    def __init__(self, app, *, upload_bytes):
        self.app, self.upload_bytes = app, upload_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        limit = self.upload_bytes+2_000_000 if scope['path'] == '/api/drone/import' else 6_000_000
        if scope['path'].startswith('/api/drone/agent/'):
            limit = 262144
        elif scope['path'].rstrip('/').startswith('/api/drone/disk-pressure/'):
            # Preserve the disk-pressure transport's independent 16 MiB cap.
            limit = 16777216
        headers = dict(scope['headers'])
        declared = headers.get(b'content-length')
        try:
            if declared and (int(declared) < 0 or int(declared) > limit):
                return await JSONResponse({'detail': 'request byte budget exceeded'}, status_code=413)(scope, receive, send)
        except ValueError:
            return await JSONResponse({'detail': 'invalid content length'}, status_code=400)(scope, receive, send)
        total = 0

        async def bounded_receive():
            nonlocal total
            message = await receive()
            if message['type'] == 'http.request':
                total += len(message.get('body', b''))
                if total > limit:
                    raise HTTPException(413, 'request byte budget exceeded')
            return message

        return await self.app(scope, bounded_receive, send)
