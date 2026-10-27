"""Command-line interface."""

from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv

from anchor.audio.pacing import PacingError
from anchor.config import ConfigError, Settings, load_settings
from anchor.ffmpeg import FFmpegError
from anchor.generate.check import check_script
from anchor.generate.loop import generate
from anchor.generate.request import ScriptRequest, load_request
from anchor.llm import LLMAdapter, LLMError
from anchor.render import RenderError, render
from anchor.script import load_script
from anchor.script.domain import DomainContext
from anchor.tts.factory import build_adapter

app = typer.Typer(no_args_is_help=True, help="Anchor render pipeline.")
tts_app = typer.Typer(no_args_is_help=True, help="TTS Backend commands.")
app.add_typer(tts_app, name="tts")


@app.callback()
def _root(
    ctx: typer.Context,
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Config file (default: $ANCHOR_CONFIG or ./anchor.toml)."),
    ] = None,
) -> None:
    """Anchor render pipeline."""
    ctx.obj = config


def _fail(message: str) -> typer.Exit:
    typer.echo(message, err=True)
    return typer.Exit(code=1)


def _settings(ctx: typer.Context) -> Settings:
    try:
        return load_settings(ctx.obj)
    except ConfigError as exc:
        raise _fail(f"error: {exc}") from exc


def _llm_adapter(settings: Settings) -> LLMAdapter:
    """The configured LLM Adapter; tests replace this function with a fake."""
    from anchor.llm.litellm_adapter import build_llm_adapter

    return build_llm_adapter(settings.llm)


def _load_request_or_fail(path: Path) -> ScriptRequest:
    request, errors = load_request(path)
    if request is None:
        lines = [f"{path}: {len(errors)} request error(s)"] + [f"  {e}" for e in errors]
        raise _fail("\n".join(lines))
    return request


@app.command()
def validate(
    ctx: typer.Context,
    script: Annotated[Path, typer.Argument(help="Session Script JSON file.")],
    request: Annotated[
        Path | None,
        typer.Option("--request", help="Script Request YAML: also run domain validation."),
    ] = None,
    review: Annotated[
        bool, typer.Option("--review", help="With --request: also run the LLM Suggestion Review.")
    ] = False,
) -> None:
    """Validate a Session Script and print all errors.

    Without --request only structural validation runs. With --request the Script is also
    checked against the domain rules for that request, and the duration estimate is printed.
    """
    if review and request is None:
        raise _fail("error: --review requires --request")
    result = load_script(script)
    if not result.ok:
        lines = [f"{script}: {len(result.errors)} validation error(s)"]
        lines += [f"  {issue}" for issue in result.errors]
        raise _fail("\n".join(lines))
    s = result.script
    if request is None:
        typer.echo(f"{script}: valid ({s.session_type}, {len(s.segments)} segments)")
        return

    req = _load_request_or_fail(request)
    settings = _settings(ctx)
    try:
        checked = check_script(s, req, DomainContext.from_settings(settings),
                               reviewer=_llm_adapter(settings) if review else None,
                               review_model=settings.llm.effective_review_model)
    except PacingError as exc:
        raise _fail(f"error: {exc}") from exc
    except LLMError as exc:
        raise _fail(f"review failed: {exc}") from exc
    typer.echo(f"duration: {checked.estimate.describe()}")
    if review:
        r = checked.review
        typer.echo(f"review: skipped ({r.reason})" if r.skipped else
                   f"review: {len(r.issues)} finding(s), {len(r.anomalies)} anomaly(ies)")
    if checked.issues:
        lines = [f"{script}: {len(checked.issues)} validation error(s)"]
        lines += [f"  {issue}" for issue in checked.issues]
        raise _fail("\n".join(lines))
    passed = "domain rules and review passed" if review else "domain rules passed"
    typer.echo(f"{script}: valid ({s.session_type}, {len(s.segments)} segments, {passed})")


@app.command("generate")
def generate_cmd(
    ctx: typer.Context,
    request: Annotated[Path, typer.Argument(help="Script Request YAML file.")],
    output: Annotated[Path, typer.Option("-o", "--output", help="Output Session Script JSON.")],
    no_review: Annotated[
        bool, typer.Option("--no-review", help="Skip the LLM Suggestion Review.")
    ] = False,
) -> None:
    """Generate a Session Script from a Script Request with the configured LLM.

    The Script is written only if it passes structural and domain validation (and the review);
    a generation record is written next to it on every run.
    """
    req = _load_request_or_fail(request)
    settings = _settings(ctx)
    try:
        domain_ctx = DomainContext.from_settings(settings)
    except PacingError as exc:
        raise _fail(f"error: {exc}") from exc
    adapter = _llm_adapter(settings)
    models = [settings.llm.model] + ([] if no_review else [settings.llm.effective_review_model])
    try:
        if preflight := getattr(adapter, "preflight", None):
            preflight(*models)  # fails before any request, e.g. on a missing API key
    except LLMError as exc:
        raise _fail(f"error: {exc}") from exc
    result = generate(req, output, adapter=adapter, settings=settings.llm, ctx=domain_ctx,
                      review=not no_review)

    usage = result.record.totals()
    tokens = (f"{usage['input_tokens']} in / {usage['output_tokens']} out tokens "
              f"in {usage['calls']} call(s)")
    review = "review skipped" if no_review else f"reviewed by {settings.llm.effective_review_model}"
    if not result.ok:
        lines = [f"generation {result.outcome} after {result.attempts} attempt(s) "
                 f"({settings.llm.model}, {tokens}); errors of the last attempt:"]
        lines += [f"  {issue}" for issue in result.errors]
        lines.append(f"record: {result.record_path}")
        raise _fail("\n".join(lines))
    typer.echo(f"{output}: {result.attempts} attempt(s), {settings.llm.model}, {review}")
    typer.echo(f"duration: {result.estimate.describe()}")
    typer.echo(f"usage: {tokens}")
    typer.echo(f"record: {result.record_path}")


@app.command("render")
def render_cmd(
    ctx: typer.Context,
    script: Annotated[Path, typer.Argument(help="Session Script JSON file.")],
    output: Annotated[Path, typer.Option("-o", "--output", help="Output audio file.")],
    no_cache: Annotated[
        bool, typer.Option("--no-cache", help="Ignore cached speech and overwrite it.")
    ] = False,
    fmt: Annotated[
        str | None,
        typer.Option("--format", help="mp3 or opus (default: by extension, else mp3)."),
    ] = None,
) -> None:
    """Render a Session Script to an audio file plus a JSON render report."""
    if fmt is not None and fmt not in ("mp3", "opus"):
        raise _fail(f"error: unsupported format {fmt!r}; use mp3 or opus")
    result = load_script(script)
    if not result.ok:
        lines = [f"{script}: {len(result.errors)} validation error(s)"]
        lines += [f"  {issue}" for issue in result.errors]
        raise _fail("\n".join(lines))
    settings = _settings(ctx)
    try:
        rendered = render(result.script, output, settings=settings,
                          adapter=build_adapter(settings.tts), no_cache=no_cache, fmt=fmt,
                          script_path=script)
    except (RenderError, FFmpegError, PacingError) as exc:
        raise _fail(f"render failed: {exc}") from exc
    r = rendered.report
    typer.echo(
        f"{output}: {r['output_duration_sec']:.1f} s (target {r['target_duration_sec']:.0f} s), "
        f"{r['integrated_loudness_lufs']:.1f} LUFS, TP {r['true_peak_dbtp']:.1f} dBTP, "
        f"{r['cache_hits']} cache hit(s) / {r['cache_misses']} miss(es), "
        f"synthesis {r['synthesis_time_sec']:.1f} s, total {r['render_time_sec']:.1f} s")
    if r["loudnorm_dynamic_fallback"]:
        typer.echo("warning: loudnorm fell back to dynamic mode", err=True)
    typer.echo(f"report: {rendered.report_path}")


@tts_app.command("health")
def tts_health(ctx: typer.Context) -> None:
    """Check that the configured backend is reachable and has the model and Voice."""
    tts = _settings(ctx).tts
    status = build_adapter(tts).health()
    fmt = lambda v: "unknown" if v is None else ("yes" if v else "NO")  # noqa: E731
    typer.echo(f"backend:   {tts.backend_id} ({tts.base_url})")
    typer.echo(f"reachable: {fmt(status.reachable)}")
    if not status.authorized:
        typer.echo("authorized: NO")
    typer.echo(f"model:     {tts.model}: {fmt(status.model_available)}")
    typer.echo(f"voice:     {tts.voice}: {fmt(status.voice_available)}")
    if status.detail:
        typer.echo(f"detail:    {status.detail}")
    if not status.ok:
        raise typer.Exit(code=1)


@tts_app.command("voices")
def tts_voices(
    ctx: typer.Context,
    language: Annotated[str | None, typer.Option(help="Filter by language, e.g. de-DE.")] = None,
) -> None:
    """List the Voices the configured backend offers."""
    from anchor.tts import TTSError

    try:
        voices = build_adapter(_settings(ctx).tts).list_voices(language)
    except TTSError as exc:
        raise _fail(f"error: {exc}") from exc
    for voice in voices:
        typer.echo(f"{voice.id}\t{voice.language}\t{voice.model or ''}")
    if not voices:
        typer.echo("no voices found", err=True)


def main() -> None:
    # Secrets such as ANCHOR_TTS__API_KEY or LITELLM_PROXY_API_KEY may live in ./.env
    # (git-ignored). Variables already set in the environment take precedence.
    load_dotenv(Path.cwd() / ".env", override=False)
    app()
