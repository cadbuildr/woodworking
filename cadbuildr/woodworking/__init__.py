"""Wood joinery library: beams + joinery interfaces built on foundation anchors.

Two API levels:

- :mod:`interfaces` — the precise API: explicit sites (``beam.end("b")``,
  ``beam.face("px").at(650, from_="a")``), spec objects, and a validating
  :class:`Joinery` builder (site bookkeeping, collision checks, loop closing).
- :mod:`joints` — legacy one-liners kept for the demo gallery; they guess
  ends/faces/directions and cannot express closed loops. Prefer the
  interfaces API for anything beyond a single-joint illustration.
"""

from .beam import Beam, Dowel
from .interfaces import (
    BoxCorner,
    ClosureError,
    Interface,
    JoineryError,
    Joinery,
    JointCollisionError,
    MiterCorner,
    MortiseTenon,
    PlacementError,
    SiteConflictError,
)
from .sites import EndSite, FaceSite
from .specs import FingerSpec, MiterSpec, TenonSpec
from .joints import (
    box_joint,
    butt_joint,
    cross_lap,
    dado_joint,
    doweled_butt,
    edge_joint,
    end_lap,
    mitered_butt,
    mortise_and_tenon,
    rabbet_joint,
    sliding_dovetail,
    through_dovetail,
    tongue_and_groove,
)

__all__ = [
    "Beam",
    "Dowel",
    # precise interfaces API
    "BoxCorner",
    "ClosureError",
    "EndSite",
    "FaceSite",
    "FingerSpec",
    "Interface",
    "Joinery",
    "JoineryError",
    "JointCollisionError",
    "MiterCorner",
    "MiterSpec",
    "MortiseTenon",
    "PlacementError",
    "SiteConflictError",
    "TenonSpec",
    # legacy one-liners
    "box_joint",
    "butt_joint",
    "cross_lap",
    "dado_joint",
    "doweled_butt",
    "edge_joint",
    "end_lap",
    "mitered_butt",
    "mortise_and_tenon",
    "rabbet_joint",
    "sliding_dovetail",
    "through_dovetail",
    "tongue_and_groove",
]
