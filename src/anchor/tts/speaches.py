"""Speaches-specific extensions: health with model/voice availability, voice listing."""

import httpx

from anchor.tts.base import HealthStatus, Voice
from anchor.tts.openai_compat import OpenAICompatibleAdapter


def _language_matches(voice_language: str, wanted: str) -> bool:
    """Speaches reports bare language codes ("de"); accept "de-DE", "de_DE" or "de" as filter."""
    norm = lambda code: code.replace("_", "-").lower()  # noqa: E731
    voice_language, wanted = norm(voice_language), norm(wanted)
    return voice_language == wanted or voice_language == wanted.split("-")[0] or (
        wanted == voice_language.split("-")[0]
    )


class SpeachesAdapter(OpenAICompatibleAdapter):
    def health(self) -> HealthStatus:
        try:
            response = self._client.get("/health")
        except httpx.TransportError as exc:
            return HealthStatus(reachable=False, detail=f"{self.base_url} unreachable: {exc}")
        if response.status_code in (401, 403):
            return HealthStatus(reachable=True, authorized=False,
                                detail="API key rejected (check tts.api_key)")
        if response.status_code != 200:
            return HealthStatus(reachable=False,
                                detail=f"/health returned HTTP {response.status_code}")

        model = self._client.get(f"/v1/models/{self.model}")
        if model.status_code == 404:
            return HealthStatus(
                reachable=True, model_available=False,
                detail=f"model {self.model} not installed; download it with "
                       "`curl -X POST -H \"Authorization: Bearer $ANCHOR_TTS__API_KEY\" "
                       f"{self.base_url}/v1/models/{self.model}`")
        if model.status_code != 200:
            return HealthStatus(reachable=True, detail=f"model lookup: HTTP {model.status_code}")
        voices = [v.get("name") for v in model.json().get("voices", [])]
        voice_ok = self.voice in voices
        detail = "" if voice_ok else f"voice {self.voice!r} not in model voices {voices}"
        return HealthStatus(True, True, voice_ok, detail)

    def list_voices(self, language: str | None = None) -> list[Voice]:
        response = self._request("GET", "/v1/models", params={"task": "text-to-speech"})
        voices = [
            Voice(id=v["id"] if "id" in v else v["name"], name=v["name"],
                  language=v.get("language", ""), model=m["id"])
            for m in response.json().get("data", [])
            for v in m.get("voices", [])
        ]
        if language:
            voices = [v for v in voices if _language_matches(v.language, language)]
        return voices
