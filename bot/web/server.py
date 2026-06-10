from __future__ import annotations

import asyncio
from aiohttp import web


async def run_admin_server(
    *,
    app: web.Application,
    host: str = "0.0.0.0",
    port: int = 8090,
) -> None:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    try:
        await site.start()
    except OSError:
        await runner.cleanup()
        return

    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
