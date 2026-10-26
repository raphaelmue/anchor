import io
import json

import httpx
import numpy as np
import pytest
import soundfile as sf

from anchor.tts import TTSAdapter, TTSError
from anchor.tts.fake import FakeTTSAdapter
from anchor.tts.openai_compat import OpenAICompatibleAdapter


def wav_bytes(seconds=0.5, sr=22050):
    buf = io.BytesIO()
    sf.write(buf, np.full(int(seconds * sr), 0.1, dtype=np.float32), sr, format="WAV")
    return buf.getvalue()


# -- FakeTTSAdapter ---------------------------------------------------------------------------


def test_fake_is_a_tts_adapter():
    assert isinstance(FakeTTSAdapter(), TTSAdapter)


def test_fake_result_identity():
    result = FakeTTSAdapter(model="m1", voice="v1").synthesize("Hallo.", language="de-DE",
                                                               speed=0.9)
    ident = result.identity
    assert (ident.backend_id, ident.model, ident.voice, ident.speed, ident.sample_rate) == (
        "fake", "m1", "v1", 0.9, 22050)


def test_different_model_different_identity():
    a = FakeTTSAdapter(model="m1").synthesize("Hallo.", language="de-DE")
    b = FakeTTSAdapter(model="m2").synthesize("Hallo.", language="de-DE")
    assert a.identity.model != b.identity.model


def test_fake_output_properties():
    fake = FakeTTSAdapter(lead_silence_sec=0.1, trail_silence_sec=0.4, level_dbfs=-20)
    audio, sr = sf.read(io.BytesIO(fake.synthesize("Atme ruhig ein.", language="de-DE").wav))
    assert sr == 22050
    lead, trail = int(0.1 * sr), int(0.4 * sr)
    assert np.all(audio[:lead] == 0) and np.all(audio[-trail:] == 0)
    voiced = audio[lead:-trail]
    assert len(voiced) == pytest.approx(fake.voiced_duration("Atme ruhig ein.") * sr, abs=2)
    rms_db = 20 * np.log10(np.sqrt(np.mean(voiced**2)))
    assert rms_db == pytest.approx(-20, abs=0.5)


def test_fake_is_deterministic_and_counts_calls():
    fake = FakeTTSAdapter()
    a = fake.synthesize("Gleich.", language="de-DE").wav
    b = fake.synthesize("Gleich.", language="de-DE").wav
    assert a == b and fake.calls == ["Gleich.", "Gleich."]


def test_fake_slower_speed_is_longer():
    fake = FakeTTSAdapter()
    assert fake.voiced_duration("Langsam.", 0.85) > fake.voiced_duration("Langsam.", 1.0)


def test_fake_failure_injection():
    fake = FakeTTSAdapter(fail_on_call=2)
    fake.synthesize("eins", language="de-DE")
    with pytest.raises(TTSError):
        fake.synthesize("zwei", language="de-DE")


# -- OpenAICompatibleAdapter -----------------------------------------------------------------


def make_adapter(handler, **kwargs):
    sleeps: list[float] = []
    adapter = OpenAICompatibleAdapter(
        base_url="http://tts.test:8000", model="m", voice="v", backend_id="speaches",
        api_key="k", transport=httpx.MockTransport(handler), sleep=sleeps.append, **kwargs)
    return adapter, sleeps


def test_success_sends_expected_request():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=wav_bytes())

    adapter, _ = make_adapter(handler)
    result = adapter.synthesize("Hallo Welt.", language="de-DE", speed=0.85)
    assert seen["path"] == "/v1/audio/speech"
    assert seen["auth"] == "Bearer k"
    assert seen["body"] == {"model": "m", "voice": "v", "input": "Hallo Welt.",
                            "response_format": "wav", "speed": 0.85, "sample_rate": 22050}
    assert result.identity.speed == 0.85 and result.sample_rate == 22050


def test_5xx_then_success_retries_with_backoff():
    responses = iter([httpx.Response(503, text="busy"), httpx.Response(502, text="busy"),
                      httpx.Response(200, content=wav_bytes())])
    adapter, sleeps = make_adapter(lambda r: next(responses), backoff_sec=0.5)
    adapter.synthesize("Hallo.", language="de-DE")
    assert sleeps == [0.5, 1.0]


def test_400_not_retried_and_includes_message():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400, json={"detail": "Speed must be between 0.25 and 4.0"})

    adapter, sleeps = make_adapter(handler)
    with pytest.raises(TTSError, match="Speed must be between") as exc:
        adapter.synthesize("Hallo.", language="de-DE", speed=9)
    assert len(calls) == 1 and sleeps == []
    assert "speaches" in str(exc.value)


def test_unreachable_fails_after_retries_naming_url():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    adapter, sleeps = make_adapter(handler, retries=3)
    with pytest.raises(TTSError, match=r"http://tts\.test:8000") as exc:
        adapter.synthesize("Hallo.", language="de-DE")
    assert "4 attempts" in str(exc.value) and len(sleeps) == 3


@pytest.mark.parametrize("content", [b"", b"not a wav file"])
def test_empty_or_undecodable_audio(content):
    adapter, _ = make_adapter(lambda r: httpx.Response(200, content=content))
    with pytest.raises(TTSError):
        adapter.synthesize("Hallo.", language="de-DE")


def test_unexpected_sample_rate_is_explicit():
    adapter, _ = make_adapter(lambda r: httpx.Response(200, content=wav_bytes(sr=24000)))
    with pytest.raises(TTSError, match="24000 Hz"):
        adapter.synthesize("Hallo.", language="de-DE")
