"""Joint sites: precise sub-selection of WHERE an interface lands on a beam.

A site pins down everything the old one-liners guessed: which end, which
face, measured from which datum, and how the mating part is clocked around
the mate axis::

    rail.end("b")                                  # an end face
    leg.face("px").at(650, from_=leg.end("a"))     # a point on a side face,
                                                   # with an explicit datum
    leg.face("px").at(650, from_="a").clocked(90)  # mating part turned 90°
    side.end("b").inside("ny")                     # which face of this board
                                                   # faces the corner interior

Sites are immutable value objects; deriving (`at`, `clocked`, `inside`)
returns a new site. Interfaces consume sites — a beam end can host at most
one interface, enforced by the :class:`~.interfaces.Joinery` builder.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Optional, Union

import numpy as np

_ENDS = ("a", "b")
_FACES = ("px", "nx", "py", "ny")

# Unique-name counter for derived anchors (foundation derives anchors by name).
_ANCHOR_SEQ = [0]


def _seq() -> int:
    _ANCHOR_SEQ[0] += 1
    return _ANCHOR_SEQ[0]


@dataclass(frozen=True)
class EndSite:
    """One of a beam's two end faces, optionally with a declared inside face.

    ``inside`` names the side face of THIS beam that must face the interior
    of a corner (box corner, miter). Corner interfaces require it — that is
    the fold direction the old API guessed.
    """

    beam: Any
    which: str
    inside_face: Optional[str] = None

    def __post_init__(self) -> None:
        if self.which not in _ENDS:
            raise ValueError(f"Unknown end '{self.which}': expected 'a' or 'b'")
        if self.inside_face is not None and self.inside_face not in _FACES:
            raise ValueError(
                f"Unknown inside face '{self.inside_face}': expected one of {_FACES}"
            )

    # -- fluent derivation -------------------------------------------------
    def inside(self, face: Union[str, "FaceSite"]) -> "EndSite":
        """Declare which face of this beam faces the corner interior."""
        key = face.which if isinstance(face, FaceSite) else str(face)
        if isinstance(face, FaceSite) and face.beam is not self.beam:
            raise ValueError("inside() face must belong to the same beam")
        return replace(self, inside_face=key)

    # -- geometry ----------------------------------------------------------
    @property
    def key(self) -> tuple[int, str]:
        return (id(self.beam), f"end_{self.which}")

    @property
    def label(self) -> str:
        return f"{_beam_label(self.beam)}.end_{self.which}"

    @property
    def z_at(self) -> float:
        """The end plane's position along the beam's local Z."""
        return 0.0 if self.which == "a" else float(self.beam.length)

    @property
    def outward(self) -> np.ndarray:
        """Outward normal in beam-local coordinates."""
        return np.array([0.0, 0.0, -1.0 if self.which == "a" else 1.0])

    @property
    def y_sign(self) -> float:
        """Anchor-local +Y expressed as a beam-local Y sign.

        ``end_a`` anchors are flipped 180° about X (z_down), so their +Y is
        the beam's -Y.
        """
        return 1.0 if self.which == "b" else -1.0

    def anchor(self) -> Any:
        """The beam's built-in end anchor (+Z = outward normal)."""
        return self.beam.anchor(f"end_{self.which}")

    def inside_y_sign(self) -> float:
        """The declared inside face as a beam-local Y sign (corner folds
        happen across the beam's thickness, so only py/ny are valid)."""
        if self.inside_face is None:
            raise ValueError(
                f"{self.label}: corner interfaces need an explicit fold "
                "direction — declare it with .inside('py') or .inside('ny')"
            )
        if self.inside_face not in ("py", "ny"):
            raise ValueError(
                f"{self.label}: inside('{self.inside_face}') — corners fold "
                "across the beam thickness, so the inside face must be 'py' "
                "or 'ny'"
            )
        return 1.0 if self.inside_face == "py" else -1.0


@dataclass(frozen=True)
class FaceSite:
    """A side face of a beam, optionally pinned to a point along it.

    ``at(dist, from_=...)`` measures ``dist`` millimeters from an explicit
    end — there is no default datum on purpose. ``clocked(deg)`` rotates the
    mating part around the face normal.
    """

    beam: Any
    which: str
    at_mm: Optional[float] = None
    from_end: Optional[str] = None
    clock_rad: float = 0.0

    def __post_init__(self) -> None:
        if self.which not in _FACES:
            raise ValueError(f"Unknown face '{self.which}': expected one of {_FACES}")

    # -- fluent derivation -------------------------------------------------
    def at(self, dist: float, from_: Union[str, EndSite]) -> "FaceSite":
        """Pin the site ``dist`` mm along the beam, measured from an end.

        ``from_`` is required: pass ``'a'``/``'b'`` or ``beam.end(...)``.
        The distance locates the CENTER of whatever the interface puts here
        (mortise pocket, dado slot...).
        """
        end = from_.which if isinstance(from_, EndSite) else str(from_)
        if isinstance(from_, EndSite) and from_.beam is not self.beam:
            raise ValueError("at(from_=...) end must belong to the same beam")
        if end not in _ENDS:
            raise ValueError(f"Unknown end '{end}': expected 'a' or 'b'")
        if not 0.0 <= float(dist) <= float(self.beam.length):
            raise ValueError(
                f"{self.label}: at({dist:g}) is outside the beam "
                f"(length {self.beam.length:g})"
            )
        return replace(self, at_mm=float(dist), from_end=end)

    def at_middle(self) -> "FaceSite":
        """Pin the site at the beam's mid-length.

        The named shortcut for the most common position — defaults are fine
        when the name says what they do (prefer this over a silent fallback).
        """
        return replace(self, at_mm=float(self.beam.length) / 2.0, from_end="a")

    def clocked(self, deg: float) -> "FaceSite":
        """Rotate the mating part ``deg`` degrees around the face normal."""
        return replace(self, clock_rad=math.radians(deg))

    # -- geometry ----------------------------------------------------------
    @property
    def key(self) -> tuple[int, str]:
        return (id(self.beam), f"face_{self.which}")

    @property
    def label(self) -> str:
        pos = f"@{self.at_mm:g}from{self.from_end}" if self.at_mm is not None else ""
        return f"{_beam_label(self.beam)}.face_{self.which}{pos}"

    @property
    def thickness(self) -> float:
        """Material depth behind this face (mortise/dado depth cap)."""
        return float(self.beam.face_thickness(self.which))

    @property
    def normal(self) -> np.ndarray:
        return {
            "px": np.array([1.0, 0.0, 0.0]),
            "nx": np.array([-1.0, 0.0, 0.0]),
            "py": np.array([0.0, 1.0, 0.0]),
            "ny": np.array([0.0, -1.0, 0.0]),
        }[self.which]

    @property
    def z_along(self) -> float:
        """The pinned point's position along the beam's local Z."""
        if self.at_mm is None or self.from_end is None:
            raise ValueError(
                f"{self.label}: this interface needs a point on the face — "
                "pin it with .at(dist, from_='a'|'b')"
            )
        return (
            self.at_mm if self.from_end == "a" else float(self.beam.length) - self.at_mm
        )

    def center_local(self) -> np.ndarray:
        """The pinned point in beam-local coordinates (on the face plane)."""
        half = self.thickness / 2.0
        return self.normal * half + np.array([0.0, 0.0, self.z_along])

    def anchor(self) -> Any:
        """Derived anchor at the pinned point, clocking applied.

        Face anchors put local X along the beam (from end_a) and +Z on the
        outward normal, so the offset is ``[z_along, 0, 0]``.
        """
        base = self.beam.anchor(f"face_{self.which}")
        out = base.offset([self.z_along, 0.0, 0.0], name=f"site_{_seq()}")
        if self.clock_rad:
            out = out.rotated(self.clock_rad, name=f"siteclk_{_seq()}")
        return out


def _beam_label(beam: Any) -> str:
    name = getattr(beam, "name", None)
    value = getattr(name, "value", None)
    return str(value) if value else type(beam).__name__


def end_site(beam: Any, which: str) -> EndSite:
    return EndSite(beam=beam, which=which)


def face_site(beam: Any, which: str) -> FaceSite:
    return FaceSite(beam=beam, which=which)
