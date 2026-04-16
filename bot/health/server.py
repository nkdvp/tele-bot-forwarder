from __future__ import annotations
import asyncio
import logging
import time
from aiohttp import web

_start_time: float = 0.0


async def health_handler(request: web.Request) -> web.Response:
    uptime = int(time.monotonic() - _start_time)
    return web.json_response({"status": "ok", "uptime_seconds": uptime})


async def run_health_server(port: int = 8080) -> None:
    global _start_time
    app = web.Application()
    app.router.add_get("/health", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    try:
        await site.start()
        _start_time = time.monotonic()
    except OSError as e:
        logging.getLogger(__name__).error("Health server failed to start on port %d: %s", port, e)
        await runner.cleanup()
        return
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
