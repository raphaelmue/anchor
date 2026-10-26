"""Build the configured TTS Adapter."""

from anchor.config import TTSSettings
from anchor.tts.openai_compat import OpenAICompatibleAdapter
from anchor.tts.speaches import SpeachesAdapter


def build_adapter(settings: TTSSettings) -> OpenAICompatibleAdapter:
    cls = SpeachesAdapter if settings.kind == "speaches" else OpenAICompatibleAdapter
    return cls(
        base_url=settings.base_url,
        model=settings.model,
        voice=settings.voice,
        backend_id=settings.backend_id,
        api_key=settings.api_key.get_secret_value() if settings.api_key else None,
        sample_rate=settings.sample_rate,
        timeout_sec=settings.timeout_sec,
        retries=settings.retries,
        backoff_sec=settings.backoff_sec,
    )
