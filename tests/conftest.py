import json

import pytest


def pytest_collection_modifyitems(config, items):
    """Skip `llm` tests unless the configured provider's API key is set."""
    llm_items = [item for item in items if "llm" in item.keywords]
    if not llm_items:
        return
    from anchor.config import load_settings
    from anchor.llm import LLMError
    from anchor.llm.litellm_adapter import check_environment

    model = load_settings().llm.model
    try:
        check_environment(model)
    except LLMError as exc:
        skip = pytest.mark.skip(reason=str(exc))
        for item in llm_items:
            item.add_marker(skip)


@pytest.fixture
def write_json(tmp_path):
    def write(doc, name="script.json"):
        path = tmp_path / name
        path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return path

    return write
