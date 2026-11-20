"""Serializable recipe contract for reproducible verification plots [M§24]."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PlotRecipe:
    plot_id: str
    field_id: str
    kind: str
    run_id: str
    source_sha256: str
    plane: dict | None
    units: str
    colormap: str
    range_policy: str
    vmin: float | None
    vmax: float | None
    mask: str
    caption: str
    overrides: tuple = ()
    renderer_version: str = "native_plot_v1"
