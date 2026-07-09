"""Joint specs: WHAT an interface cuts, separated from WHERE it lands.

Every dimension a woodworker would put on a joint drawing is a named field
with visible resolution rules — no arithmetic buried in function bodies.
``resolve(...)`` turns the user's partial spec plus the two sites into a
fully-dimensioned, validated record.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .sites import EndSite, FaceSite


@dataclass(frozen=True)
class ResolvedTenon:
    """A fully-dimensioned tenon: what actually gets cut."""

    width: float  # across the tenon beam's local X
    thickness: float  # across the tenon beam's local Y
    length: float  # how deep the tenon enters the mortise beam
    fit: float
    through: bool


@dataclass(frozen=True)
class TenonSpec:
    """Mortise & tenon dimensions.

    Give either explicit ``width``/``thickness`` or a uniform ``shoulder``;
    unset values fall back to documented rules:

    - ``shoulder`` default: a quarter of the smaller tenon-beam cross dimension
    - ``length`` default: 60% of the mortise beam's thickness behind the face
      (the full thickness when ``through=True``)
    """

    width: Optional[float] = None
    thickness: Optional[float] = None
    length: Optional[float] = None
    shoulder: Optional[float] = None
    fit: float = 0.2
    through: bool = False

    def resolve(self, tenon: EndSite, mortise: FaceSite) -> ResolvedTenon:
        beam = tenon.beam
        wall = mortise.thickness

        shoulder = self.shoulder
        if shoulder is None:
            shoulder = min(beam.width, beam.height) / 4.0
        width = self.width if self.width is not None else beam.width - 2.0 * shoulder
        thickness = (
            self.thickness if self.thickness is not None else beam.height - 2.0 * shoulder
        )
        if width <= 0 or thickness <= 0:
            raise ValueError(
                f"TenonSpec on {tenon.label}: no tenon material left "
                f"(width={width:g}, thickness={thickness:g})"
            )
        if width > beam.width or thickness > beam.height:
            raise ValueError(
                f"TenonSpec on {tenon.label}: tenon {width:g}×{thickness:g} exceeds "
                f"the beam cross-section {beam.width:g}×{beam.height:g}"
            )

        length = self.length
        if length is None:
            length = wall if self.through else 0.6 * wall
        if self.through:
            if length > wall:
                raise ValueError(
                    f"Through tenon length {length:g} exceeds the mortise wall "
                    f"{wall:g} (the tenon would protrude)"
                )
        elif length >= wall:
            raise ValueError(
                f"Tenon length {length:g} would pierce the mortise beam "
                f"(wall {wall:g}); use through=True for an exposed tenon"
            )
        if length > beam.length:
            raise ValueError(
                f"Tenon length {length:g} exceeds the tenon beam length {beam.length:g}"
            )
        return ResolvedTenon(
            width=float(width),
            thickness=float(thickness),
            length=float(length),
            fit=float(self.fit),
            through=bool(self.through),
        )


@dataclass(frozen=True)
class FingerSpec:
    """Box (finger) corner dimensions.

    ``count`` is the total number of segments across the shared width; odd
    counts look traditional. The board named first in the interface keeps the
    outermost (even-indexed) fingers.
    """

    count: int = 5
    fit: float = 0.15

    def __post_init__(self) -> None:
        if self.count < 2:
            raise ValueError("FingerSpec.count must be at least 2")


@dataclass(frozen=True)
class MiterSpec:
    """Mitered corner parameters (45° across the beam thickness)."""

    fit: float = 0.0
