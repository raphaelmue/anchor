"""Render a validated Session Script into a final Audio Asset."""

from anchor.render.errors import RenderError
from anchor.render.pipeline import RenderResult, render

__all__ = ["RenderError", "RenderResult", "render"]
