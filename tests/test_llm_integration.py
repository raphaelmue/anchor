"""Opt-in integration test against the configured LLM Provider.

Costs real tokens (one generation of the `short` example request with review), so it is excluded
from plain `pytest` and runs only with `uv run pytest -m llm`; it is skipped without the
provider's credentials.
"""

import pytest
from typer.testing import CliRunner

from anchor.cli import app
from anchor.config import load_settings
from anchor.generate.loop import generate
from anchor.generate.request import load_request
from anchor.llm.litellm_adapter import build_llm_adapter
from anchor.script.domain import DomainContext
from domain_helpers import EXAMPLE_REQUESTS

pytestmark = pytest.mark.llm


def test_generate_short_example_with_review(tmp_path):
    settings = load_settings()
    request_path = EXAMPLE_REQUESTS / "short.yaml"
    request, errors = load_request(request_path)
    assert not errors
    out = tmp_path / "short.json"

    result = generate(request, out, adapter=build_llm_adapter(settings.llm),
                      settings=settings.llm, ctx=DomainContext.from_settings(settings),
                      review=True)

    assert result.ok, [str(e) for e in result.errors]
    assert result.record_path.is_file()
    checked = CliRunner().invoke(app, ["validate", str(out), "--request", str(request_path)])
    assert checked.exit_code == 0, checked.output
