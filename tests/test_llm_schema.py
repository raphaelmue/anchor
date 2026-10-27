import json

from anchor.generate.llm_schema import LLMScript, script_document, to_script
from domain_helpers import make_request

GENERATED = {"segments": [
    {"type": "sound", "sound": "bell_soft"},
    {"type": "speech", "text": "Leg dich bequem hin.", "role": "induction", "strategy": None},
    {"type": "pause", "seconds": 20, "elastic": {"min": 10, "max": 40}},
    {"type": "silent_practice", "seconds": 60, "elastic": None, "prompt": "Atme weiter."},
    {"type": "speech", "text": "Du darfst schlafen.", "role": None,
     "strategy": "sleep_permission"},
]}


def test_metadata_from_request():
    request = make_request(session_type="sleep", method="pmr", stage_ref="stage-1",
                           guidance_level="semi_guided", target_duration_sec=900)
    result = to_script(LLMScript.model_validate(GENERATED), request)
    assert result.ok, result.errors
    s = result.script
    assert (s.session_type, s.method, s.guidance_level) == ("sleep", "pmr", "semi_guided")
    assert (s.target_duration_sec, s.language, s.stage_ref) == (900, "de-DE", "stage-1")
    assert (s.session_context, s.goal_pattern, s.goal_domain) == (
        "stage", "calm_in_situation", "stress")
    assert s.schema_version == "1.2"


def test_mapping_converts_elastic_and_drops_nulls():
    doc = script_document(LLMScript.model_validate(GENERATED), make_request())
    assert doc["segments"][2] == {"type": "pause", "seconds": 20, "elastic": [10, 40]}
    assert doc["segments"][1] == {"type": "speech", "text": "Leg dich bequem hin.",
                                  "role": "induction"}
    assert "elastic" not in doc["segments"][3]


def test_limits_are_left_to_script_validation():
    generated = LLMScript.model_validate({"segments": [
        {"type": "speech", "text": "x" * 301, "role": None, "strategy": None},
        {"type": "pause", "seconds": 5, "elastic": {"min": 6, "max": 8}},
    ]})
    result = to_script(generated, make_request())
    assert {e.location for e in result.errors} == {"segments[0].text", "segments[1]"}


def test_schema_is_strict_mode_compatible():
    schema = LLMScript.model_json_schema()
    text = json.dumps(schema)
    for unsupported in ("oneOf", "prefixItems", "maxLength", "minLength", "minimum",
                        "exclusiveMinimum", "discriminator"):
        assert unsupported not in text
    for definition in [schema, *schema["$defs"].values()]:
        if definition.get("type") == "object":
            assert definition["additionalProperties"] is False
            assert set(definition["required"]) == set(definition["properties"])


def test_only_builtin_sounds():
    schema = LLMScript.model_json_schema()
    assert schema["$defs"]["LLMSound"]["properties"]["sound"]["const"] == "bell_soft"
