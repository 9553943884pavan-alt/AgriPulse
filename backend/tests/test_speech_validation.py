"""Input validation that must complete before the external TTS call."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.parametrize("speed", ["fast", True, 0, -1, "nan", "inf"])
def test_speak_rejects_invalid_speed_before_calling_tts(speed):
    response = TestClient(app).post(
        "/api/speak",
        json={"text": "hello", "speed": speed},
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"] == {"field": "speed"}


@pytest.mark.parametrize("text", [0, ["hello"], {"value": "hello"}])
def test_speak_rejects_non_string_text(text):
    response = TestClient(app).post("/api/speak", json={"text": text})

    assert response.status_code == 422
    assert response.json()["error"]["details"] == {"field": "text"}
