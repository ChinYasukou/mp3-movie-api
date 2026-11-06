"""Unexpected failures retain diagnostics in logs and hide them from clients."""

import asyncio
import logging
import re

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src import log_requests


def test_unexpected_exception_returns_generic_500_with_request_id(caplog):
    app = FastAPI()
    app.middleware("http")(log_requests)

    @app.get("/broken")
    def broken():
        raise RuntimeError("private diagnostic detail")

    with caplog.at_level(logging.ERROR, logger="src.middleware"):
        with TestClient(app) as client:
            response = client.get("/broken")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    request_id = response.headers["X-Request-ID"]
    assert re.fullmatch(r"[0-9a-f]{8}", request_id)
    records = [record for record in caplog.records if record.name == "src.middleware"]
    assert len(records) == 2
    assert records[0].exc_info is not None
    assert all(request_id in record.getMessage() for record in records)
    assert "GET /broken status=500 duration=" in records[1].getMessage()


def test_request_id_is_available_in_request_state():
    from fastapi.responses import JSONResponse

    request = Request({"type": "http", "method": "GET", "path": "/state", "headers": []})

    async def next_handler(received):
        return JSONResponse({"request_id": received.state.request_id})

    response = asyncio.run(log_requests(request, next_handler))
    assert response.headers["X-Request-ID"] == request.state.request_id
