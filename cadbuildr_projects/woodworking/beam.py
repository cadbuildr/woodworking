"""Rectangular timber beam with joinery anchors."""

from __future__ import annotations

import numpy as np

from cadbuildr.foundation import (
    Circle,
    Extrusion,
    Part,
    Rectangle,
    Sketch,
    make_anchor,
)
from cadbuildr.foundation.math_utils import rotation_matrix_to_quaternion


def _face_quaternion(z_axis, x_axis):
    """Quaternion of a frame with the given local Z (outward normal) and X."""
    z = np.array(z_axis, dtype=float)
    x = np.array(x_axis, dtype=float)
    y = np.cross(z, x)
    return rotation_matrix_to_quaternion(np.column_stack([x, y, z]))


class Beam(Part):
    """A timber beam: cross-section ``width`` (X) × ``height`` (Y), extruded
    along +Z for ``length``.

    Joinery anchors (+Z = outward normal, X = clocking):

    - ``end_a`` / ``end_b`` — the two end faces (Z=0 / Z=length).
    - ``face_px`` / ``face_nx`` / ``face_py`` / ``face_ny`` — the four side
      faces, positioned at the beam start with the anchor X axis running along
      the beam, so ``beam.anchor("face_px").offset([at, 0, 0])`` is the point
      ``at`` millimeters down the beam on that face.
    """

    def __init__(
        self,
        width: float = 45.0,
        height: float = 45.0,
        length: float = 600.0,
        color: str | None = "#a97c50",
    ):
        super().__init__()
        if min(width, height, length) <= 0:
            raise ValueError("Beam dimensions must be positive")
        self.width = width
        self.height = height
        self.length = length

        sketch = Sketch(self.xy())
        section = Rectangle.from_center_and_sides(sketch.origin, width, height)
        self.add_operation(Extrusion(section, length))

        self.add_anchor(make_anchor("end_a", (0.0, 0.0, 0.0), z_down=True))
        self.add_anchor(make_anchor("end_b", (0.0, 0.0, length)))

        along = (0.0, 0.0, 1.0)
        for name, normal, position in (
            ("face_px", (1.0, 0.0, 0.0), (width / 2.0, 0.0, 0.0)),
            ("face_nx", (-1.0, 0.0, 0.0), (-width / 2.0, 0.0, 0.0)),
            ("face_py", (0.0, 1.0, 0.0), (0.0, height / 2.0, 0.0)),
            ("face_ny", (0.0, -1.0, 0.0), (0.0, -height / 2.0, 0.0)),
        ):
            self.add_anchor(
                make_anchor(name, position, quaternion=_face_quaternion(normal, along))
            )

        if color is not None:
            self.paint(color)

    def face_thickness(self, face: str) -> float:
        """Material thickness behind a side face (drilling/mortising depth cap)."""
        if face in ("px", "nx"):
            return self.width
        if face in ("py", "ny"):
            return self.height
        raise ValueError(f"Unknown face '{face}': expected px/nx/py/ny")

    def end(self, which: str):
        """Precise end selection for joinery interfaces: ``beam.end("b")``."""
        from .sites import EndSite

        return EndSite(beam=self, which=which)

    def face(self, which: str):
        """Precise face selection: ``beam.face("px").at(280, from_="a")``."""
        from .sites import FaceSite

        return FaceSite(beam=self, which=which)


class Dowel(Part):
    """A cylindrical dowel pin. Its ``mid`` anchor (at half length, mate axis
    along the pin) drops onto a hole anchor so the pin spans the interface."""

    def __init__(self, diameter: float = 8.0, length: float = 40.0, color: str = "#c9a36a"):
        self.diameter = float(diameter)
        self.length = float(length)

        sketch = Sketch(self.xy())
        self.add_operation(Extrusion(Circle(sketch.origin, self.diameter / 2.0), self.length))
        self.add_anchor(make_anchor("mid", (0.0, 0.0, self.length / 2.0), z_down=True))
        self.paint(color)
