import httpx
import pytest
from typer.testing import CliRunner

from anchor.cli import app
from anchor.tts.speaches import SpeachesAdapter

MODEL = "speaches-ai/piper-de_DE-thorsten-medium"
MODELS = {"data": [
    {"id": MODEL, "voices": [{"name": "thorsten", "language": "de", "id": "thorsten"}]},
    {"id": "speaches-ai/piper-en_US-amy-medium",
     "voices": [{"name": "amy", "language": "en", "id": "amy"}]},
]}


def server(installed=True, auth_ok=True):
    def handler(request: httpx.Request):
        if not auth_ok:
            return httpx.Response(403, json={"detail": "Invalid API key"})
        path = request.url.path
        if path == "/health":
            return httpx.Response(200, text="OK")
        if path == f"/v1/models/{MODEL}":
            return httpx.Response(200, json=MODELS["data"][0]) if installed else httpx.Response(
                404, json={"detail": "not found"})
        if path == "/v1/models":
            return httpx.Response(200, json=MODELS)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def adapter(voice="thorsten", **kw):
    return SpeachesAdapter(base_url="http://sp.test", model=MODEL, voice=voice,
                           transport=server(**kw), sleep=lambda s: None)


def test_health_all_available():
    status = adapter().health()
    assert status.ok and status.model_available and status.voice_available


def test_health_model_missing():
    status = adapter(installed=False).health()
    assert status.reachable and status.model_available is False and not status.ok


def test_health_voice_missing():
    status = adapter(voice="karl").health()
    assert status.model_available and status.voice_available is False


def test_health_unreachable():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    a = SpeachesAdapter(base_url="http://sp.test", model=MODEL, voice="thorsten",
                        transport=httpx.MockTransport(handler))
    assert not a.health().reachable


def test_health_rejected_api_key():
    status = adapter(auth_ok=False).health()
    assert status.reachable and not status.authorized and not status.ok


@pytest.mark.parametrize("language", ["de-DE", "de", "de_DE"])
def test_voices_filtered_by_language(language):
    voices = adapter().list_voices(language)
    assert [v.id for v in voices] == ["thorsten"]
    assert voices[0].model == MODEL


def test_voices_unfiltered():
    assert {v.id for v in adapter().list_voices()} == {"thorsten", "amy"}


def test_cli_health_unreachable_exits_nonzero(tmp_path, monkeypatch):
    monkeypatch.setenv("ANCHOR_TTS__BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("ANCHOR_TTS__RETRIES", "0")
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["tts", "health"])
    assert result.exit_code == 1
    assert "reachable: NO" in result.output
