"""
parametricus.viewer_backend.pyvista
===================
Backend 3D utilizando PyVista (VTK).
"""

from __future__ import annotations

import numpy as np
import pyvista as pv
from ..mesher import Mesh
from .._log import logger

# Install PyVista:
# pip install 'pyvista[all]'
def show_pyvista(mesh: Mesh, title: str = "parametricus", color: str = "#4a90d9",
    save_path: str | None = None, show: bool = True) -> None:

    vertices = mesh.vertices

    faces = np.hstack(
        (
            np.full((mesh.faces.shape[0], 1), 3, dtype=np.int32),
            mesh.faces.astype(np.int32),
        )
    ).ravel()

    surface = pv.PolyData(vertices, faces)

    plotter = pv.Plotter(off_screen=save_path is not None and not show, title=title)

    plotter.add_mesh(
        surface,
        color=color,
        smooth_shading=True,
        show_edges=False,
        specular=0.2,
        ambient=0.25,
    )

    plotter.add_axes()

    plotter.show_grid(
        xtitle="X (mm)",
        ytitle="Y (mm)",
        ztitle="Z (mm)",
    )

    plotter.camera_position = "iso"

    if save_path:
        plotter.screenshot(save_path)
        logger.info("Imagem salva em: %s", save_path)

    if show:
        plotter.show()
    else:
        plotter.close()
