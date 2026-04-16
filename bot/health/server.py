from __future__ import annotations
import asyncio
import time
from aiohttp import web

_start_time = time.monotonic()


async def health_handler(request: web.Request) -> web.Response:
    uptime = int(time.monotonic() - _start_time)
    return web.json_response({"status": "ok", "uptime_seconds": uptime})


async def run_health_server(port: int = 8080) -> None:
    app = web.Application()
    app.router.add_get("/health", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    try:
        await site.start()
    except OSError as e:
        import logging
        logging.getLogger(__name__).error("Health server failed to start on port %d: %s", port, e)
        await runner.cleanup()
        return
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
