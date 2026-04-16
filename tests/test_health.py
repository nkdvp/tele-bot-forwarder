import pytest
import json
from unittest.mock import MagicMock
from bot.health.server import health_handler


@pytest.mark.asyncio
async def test_health_handler_returns_ok():
    request = MagicMock()
    response = await health_handler(request)
    assert response.status == 200
    body = json.loads(response.body)
    assert body["status"] == "ok"
    assert isinstance(body["uptime_seconds"], int)
    assert body["uptime_seconds"] >= 0
