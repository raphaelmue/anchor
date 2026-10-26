"""Command-line interface."""

from pathlib import Path
from typing import Annotated

import typer

from anchor.audio.pacing import PacingError
from anchor.config import ConfigError, Settings, load_settings
from anchor.ffmpeg import FFmpegError
from anchor.render import RenderError, render
from anchor.script import load_script
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


@app.command()
def validate(
    script: Annotated[Path, typer.Argument(help="Session Script JSON file.")],
) -> None:
    """Validate a Session Script and print all structural errors."""
    result = load_script(script)
    if not result.ok:
        lines = [f"{script}: {len(result.errors)} validation error(s)"]
        lines += [f"  {issue}" for issue in result.errors]
        raise _fail("\n".join(lines))
    s = result.script
    typer.echo(f"{script}: valid ({s.session_type}, {len(s.segments)} segments)")


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
    app()
