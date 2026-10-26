import json

import pytest

from anchor.cache import CachingSynthesizer, SegmentStore, cache_key, normalize_text
from anchor.config import load_settings
from anchor.tts.fake import FakeTTSAdapter

IDENT = FakeTTSAdapter().identity(speed=1.0)


# -- 4.1 key + normalization -------------------------------------------------------------------


def test_same_input_same_key():
    assert cache_key("Atme ruhig.", IDENT) == cache_key("Atme ruhig.", IDENT)


def test_speed_changes_key():
    fake = FakeTTSAdapter()
    assert cache_key("Atme ruhig.", fake.identity(speed=1.0)) != cache_key(
        "Atme ruhig.", fake.identity(speed=0.9))


def test_model_changes_key():
    a = FakeTTSAdapter(model="piper-1").identity()
    b = FakeTTSAdapter(model="piper-2").identity()
    assert cache_key("Atme ruhig.", a) != cache_key("Atme ruhig.", b)


@pytest.mark.parametrize("field,value", [("voice", "other"), ("sample_rate", 16000),
                                         ("id", "other-backend")])
def test_other_identity_fields_change_key(field, value):
    other = FakeTTSAdapter(**{field: value}).identity()
    assert cache_key("x", IDENT) != cache_key("x", other)


def test_style_and_seed_change_key():
    fake = FakeTTSAdapter()
    base = cache_key("x", fake.identity())
    assert base != cache_key("x", fake.identity(style="calm"))
    assert base != cache_key("x", fake.identity(seed=1))


def test_whitespace_differences_hit_same_entry():
    assert normalize_text("Atme  ruhig.") == normalize_text("Atme ruhig. ") == "Atme ruhig."
    assert cache_key(normalize_text("Atme  ruhig."), IDENT) == cache_key(
        normalize_text("\tAtme ruhig. "), IDENT)


def test_nfc_normalization():
    decomposed = "Schließe die Augen, rühig"  # u + combining diaeresis
    assert normalize_text(decomposed) == "Schließe die Augen, rühig"


# -- 4.2 storage -------------------------------------------------------------------------------


KEY = "ab" + "0" * 62


def test_put_get_roundtrip(tmp_path):
    store = SegmentStore(tmp_path)
    store.put(KEY, b"RIFFdata", {"text": "x"})
    assert store.get(KEY) == b"RIFFdata"
    assert (tmp_path / "ab" / f"{KEY}.wav").is_file()
    assert json.loads((tmp_path / "ab" / f"{KEY}.json").read_text())["text"] == "x"


def test_wav_without_json_is_miss(tmp_path):
    (tmp_path / "ab").mkdir()
    (tmp_path / "ab" / f"{KEY}.wav").write_bytes(b"partial")
    store = SegmentStore(tmp_path)
    assert store.get(KEY) is None and not store.contains(KEY)


def test_leftover_temp_file_is_miss(tmp_path):
    (tmp_path / "ab").mkdir()
    (tmp_path / "ab" / f".{KEY}.wav.x1y2.tmp").write_bytes(b"interrupted")
    assert SegmentStore(tmp_path).get(KEY) is None


def test_interrupted_write_leaves_no_valid_entry(tmp_path, monkeypatch):
    import anchor.cache.store as store_mod

    store = SegmentStore(tmp_path)
    real_replace = store_mod.os.replace

    def crash_on_json(src, dst):
        if str(dst).endswith(".json"):
            raise KeyboardInterrupt  # killed while writing
        real_replace(src, dst)

    monkeypatch.setattr(store_mod.os, "replace", crash_on_json)
    with pytest.raises(KeyboardInterrupt):
        store.put(KEY, b"RIFF", {})
    assert store.get(KEY) is None
    assert not list((tmp_path / "ab").glob("*.tmp"))


# -- 4.3 caching wrapper -----------------------------------------------------------------------


def test_second_lookup_makes_no_adapter_call(tmp_path):
    fake = FakeTTSAdapter()
    synth = CachingSynthesizer(fake, SegmentStore(tmp_path))
    first = synth.synthesize("Atme ruhig.", language="de-DE")
    second = synth.synthesize("Atme  ruhig. ", language="de-DE")
    assert len(fake.calls) == 1
    assert first.wav == second.wav
    assert (synth.stats.hits, synth.stats.misses) == (1, 1)


def test_stored_audio_is_raw_backend_output(tmp_path):
    fake = FakeTTSAdapter()
    store = SegmentStore(tmp_path)
    result = CachingSynthesizer(fake, store).synthesize("Roh.", language="de-DE")
    key = cache_key("Roh.", fake.identity())
    assert store.get(key) == result.wav


def test_bypass_synthesizes_again_and_replaces_entry(tmp_path):
    store = SegmentStore(tmp_path)
    CachingSynthesizer(FakeTTSAdapter(level_dbfs=-30), store).synthesize("Neu.",
                                                                          language="de-DE")
    louder = FakeTTSAdapter(level_dbfs=-20)
    bypass = CachingSynthesizer(louder, store, bypass=True)
    result = bypass.synthesize("Neu.", language="de-DE")
    assert len(louder.calls) == 1 and bypass.stats.misses == 1
    assert store.get(bypass.key_for("Neu.")) == result.wav
    assert not bypass.is_cached(bypass.key_for("Neu."))


def test_is_cached(tmp_path):
    synth = CachingSynthesizer(FakeTTSAdapter(), SegmentStore(tmp_path))
    key = synth.key_for("Ja.")
    assert not synth.is_cached(key)
    synth.synthesize("Ja.", language="de-DE")
    assert synth.is_cached(key)


# -- 4.4 configured location -------------------------------------------------------------------


def test_configured_directory_is_used(tmp_path):
    cfg = tmp_path / "anchor.toml"
    cfg.write_text(f'[cache]\ndir = "{tmp_path / "my-cache"}"\n')
    store = SegmentStore.from_settings(load_settings(cfg).cache)
    CachingSynthesizer(FakeTTSAdapter(), store).synthesize("Hier.", language="de-DE")
    assert list((tmp_path / "my-cache").glob("*/*.json"))
