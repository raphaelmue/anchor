import json

import pytest


@pytest.fixture
def write_json(tmp_path):
    def write(doc, name="script.json"):
        path = tmp_path / name
        path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return path

    return write
