"""Declarative joinery interfaces with validation.

The old one-liners guessed which end, which direction, and never looked at
each other. Here an interface is a value object over explicit
:mod:`~.sites`, and a :class:`Joinery` builder applies them in phases::

    j = Joinery()
    j.box_corner(a.end("b").inside("ny"), b.end("a").inside("ny"), FingerSpec(6))
    ...
    assembly = j.build(ground=a)

``build()`` then:

1. checks site bookkeeping (a beam end hosts at most one interface),
2. checks interface occupancy volumes for collisions inside shared beams
   (crossing tenons in a table leg raise instead of silently overlapping),
3. applies all cuts to the still-unplaced parts,
4. solves placement from the interface graph (any ends, any order), and
5. verifies loop-closing interfaces geometrically instead of failing —
   a four-corner box is a first-class citizen.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from cadbuildr.foundation import Assembly, RigidJoint
from cadbuildr.foundation.math_utils import (
    compose_tf,
    invert_tf,
    tf_relative_to_frame,
)

from .joints import _CUT_MARGIN, _offset_pocket_cut, _pocket_cut, _shoulder_cuts
from .sites import EndSite, FaceSite, _seq
from .specs import FingerSpec, MiterSpec, TenonSpec


class JoineryError(ValueError):
    """Base class for joinery validation failures."""


class SiteConflictError(JoineryError):
    """The same beam end was claimed by two interfaces."""


class JointCollisionError(JoineryError):
    """Two interfaces occupy overlapping wood inside the same beam."""


class ClosureError(JoineryError):
    """A loop-closing interface does not geometrically close."""


class PlacementError(JoineryError):
    """The interface graph cannot place every part."""


# --------------------------------------------------------------------------- #
# Oriented bounding boxes (part-local): the "occupancy" every interface claims
# inside each beam it touches, used for cross-interface collision checks.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class OBB:
    """Oriented box in beam-local coordinates: center, unit axes, half-extents."""

    center: np.ndarray  # (3,)
    axes: np.ndarray  # (3, 3), columns are unit axes
    half: np.ndarray  # (3,)


def obb_intersects(a: OBB, b: OBB, margin: float = 0.05) -> bool:
    """Separating-axis test; ``margin`` shrinks both boxes so surface contact
    and fit clearances don't count as collisions."""
    ha = np.maximum(a.half - margin, 0.0)
    hb = np.maximum(b.half - margin, 0.0)
    r = a.axes.T @ b.axes
    t = a.axes.T @ (b.center - a.center)
    abs_r = np.abs(r) + 1e-9
    for i in range(3):  # a's axes
        if abs(t[i]) > ha[i] + hb @ abs_r[i]:
            return False
    for j in range(3):  # b's axes
        if abs(t @ r[:, j]) > ha @ abs_r[:, j] + hb[j]:
            return False
    for i in range(3):  # cross products
        for j in range(3):
            axis = np.cross(a.axes[:, i], b.axes[:, j])
            norm = np.linalg.norm(axis)
            if norm < 1e-9:
                continue
            axis /= norm
            ta = ha @ np.abs(a.axes.T @ axis)
            tb = hb @ np.abs(b.axes.T @ axis)
            if abs((b.center - a.center) @ axis) > ta + tb:
                return False
    return True


def _rot_about(axis: np.ndarray, angle: float) -> np.ndarray:
    axis = axis / np.linalg.norm(axis)
    k = np.array(
        [[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]]
    )
    return np.eye(3) + math.sin(angle) * k + (1 - math.cos(angle)) * (k @ k)


# --------------------------------------------------------------------------- #
# Interfaces
# --------------------------------------------------------------------------- #


class Interface:
    """A joinery interface between two beams.

    Subclasses provide: consumed end sites, occupancy OBBs per beam, cut
    operations per beam, and the two mate anchors (either may act as the
    rigid-joint parent — a rigid mate with flip is symmetric).
    """

    label: str

    @property
    def parts(self) -> tuple[Any, Any]:
        raise NotImplementedError

    def consumed_ends(self) -> list[EndSite]:
        return []

    def occupancies(self) -> list[tuple[Any, OBB]]:
        raise NotImplementedError

    def cuts(self) -> list[tuple[Any, list[Any]]]:
        """(beam, [cut operations]) — applied before any placement."""
        raise NotImplementedError

    def mate_anchors(self) -> tuple[Any, Any]:
        """(anchor on parts[0], anchor on parts[1]); mated with flip."""
        raise NotImplementedError


class MortiseTenon(Interface):
    """``tenon`` (an end site) into ``mortise`` (a pinned face site)."""

    def __init__(self, tenon: EndSite, mortise: FaceSite, spec: Optional[TenonSpec] = None):
        if tenon.beam is mortise.beam:
            raise JoineryError("A mortise & tenon cannot join a beam to itself")
        self.tenon = tenon
        self.mortise = mortise
        self.spec = spec or TenonSpec()
        self.resolved = self.spec.resolve(tenon, mortise)
        self.label = f"mortise_tenon({tenon.label} -> {mortise.label})"

    @property
    def parts(self) -> tuple[Any, Any]:
        return (self.mortise.beam, self.tenon.beam)

    def consumed_ends(self) -> list[EndSite]:
        return [self.tenon]

    def occupancies(self) -> list[tuple[Any, OBB]]:
        r = self.resolved
        # Pocket volume behind the mortise face, rotated by the site clocking.
        face = self.mortise
        normal = face.normal
        along = np.array([0.0, 0.0, 1.0])
        rot = _rot_about(normal, face.clock_rad)
        x_ax = rot @ along
        z_ax = normal
        y_ax = np.cross(z_ax, x_ax)
        pocket = OBB(
            center=face.center_local() - normal * (r.length / 2.0),
            axes=np.column_stack([x_ax, y_ax, z_ax]),
            half=np.array(
                [r.width / 2.0 + r.fit, r.thickness / 2.0 + r.fit, r.length / 2.0]
            ),
        )
        # Tenon stub at the beam end (always aligned with the beam axes).
        end = self.tenon
        stub = OBB(
            center=np.array([0.0, 0.0, end.z_at]) - end.outward * (r.length / 2.0),
            axes=np.eye(3),
            half=np.array([r.width / 2.0, r.thickness / 2.0, r.length / 2.0]),
        )
        return [(face.beam, pocket), (end.beam, stub)]

    def cuts(self) -> list[tuple[Any, list[Any]]]:
        r = self.resolved
        beam = self.tenon.beam
        end_anchor = self.tenon.anchor()
        shoulder_ops = _shoulder_cuts(
            end_anchor, beam.width, beam.height, r.width, r.thickness, r.length
        )
        pocket_op = _pocket_cut(
            self._pocket_anchor(),
            r.width + 2.0 * r.fit,
            r.thickness + 2.0 * r.fit,
            r.length + (_CUT_MARGIN if r.through else r.fit),
        )
        return [(beam, shoulder_ops), (self.mortise.beam, [pocket_op])]

    def _pocket_anchor(self) -> Any:
        if not hasattr(self, "_pocket_anchor_cache"):
            self._pocket_anchor_cache = self.mortise.anchor()
        return self._pocket_anchor_cache

    def mate_anchors(self) -> tuple[Any, Any]:
        shoulder = self.tenon.anchor().offset(
            [0.0, 0.0, -self.resolved.length], name=f"mt_shoulder_{_seq()}"
        )
        return (self._pocket_anchor(), shoulder)


class _CornerInterface(Interface):
    """Shared machinery for 90° end-to-end corners (box joint, miter).

    Both sites must declare their inside face (`.inside('py'|'ny')`) — the
    corner folds so those faces meet at the interior. ``s_a``/``s_b`` are the
    inside directions expressed in each site's END-ANCHOR coordinates; ``m``
    decides whether the child anchor needs a 180° clock so its inside face
    lands on the interior.
    """

    def __init__(self, site_a: EndSite, site_b: EndSite):
        if site_a.beam is site_b.beam:
            raise JoineryError("A corner cannot join a beam to itself")
        self.site_a = site_a
        self.site_b = site_b
        self.s_a = site_a.inside_y_sign() * site_a.y_sign
        self.s_b = site_b.inside_y_sign() * site_b.y_sign
        # With no clock the child's anchor +Y lands on the parent's -Y_p
        # (= s_a * along-parent): its inside normal points at s_b * that.
        # Interior is at -z of the parent anchor, so clock 180° about the
        # mate axis whenever the signs multiply the wrong way.
        self.child_clock = 0.0 if self.s_a * self.s_b > 0 else math.pi

    @property
    def parts(self) -> tuple[Any, Any]:
        return (self.site_a.beam, self.site_b.beam)

    def consumed_ends(self) -> list[EndSite]:
        return [self.site_a, self.site_b]

    def _child_anchor(self) -> Any:
        child = self.site_b.anchor()
        if self.child_clock:
            child = child.rotated(self.child_clock, name=f"corner_clk_{_seq()}")
        return child

    def _end_zone(self, site: EndSite, depth: float) -> OBB:
        beam = site.beam
        return OBB(
            center=np.array([0.0, 0.0, site.z_at]) - site.outward * (depth / 2.0),
            axes=np.eye(3),
            half=np.array([beam.width / 2.0, beam.height / 2.0, depth / 2.0]),
        )

    def _x_mirror(self) -> float:
        """Map of the child's anchor X onto the parent's anchor X."""
        return -1.0 if self.child_clock == 0.0 else 1.0


class BoxCorner(_CornerInterface):
    """Box (finger) corner between two beam ends, fold direction explicit."""

    def __init__(self, site_a: EndSite, site_b: EndSite, spec: Optional[FingerSpec] = None):
        super().__init__(site_a, site_b)
        self.spec = spec or FingerSpec()
        if site_a.beam.width != site_b.beam.width:
            raise JoineryError(
                f"box_corner({site_a.label}, {site_b.label}): boards must share "
                f"width across the fingers "
                f"({site_a.beam.width:g} != {site_b.beam.width:g})"
            )
        self.label = f"box_corner({site_a.label}, {site_b.label})"

    def occupancies(self) -> list[tuple[Any, OBB]]:
        return [
            (self.site_a.beam, self._end_zone(self.site_a, self.site_b.beam.height)),
            (self.site_b.beam, self._end_zone(self.site_b, self.site_a.beam.height)),
        ]

    def cuts(self) -> list[tuple[Any, list[Any]]]:
        n = self.spec.count
        fit = self.spec.fit
        w = self.site_a.beam.width
        fw = w / n
        mirror = self._x_mirror()

        # Parent keeps even-indexed segments (in its own anchor X). The child
        # must keep exactly the complement, expressed in ITS anchor X.
        parent_keeps = {i for i in range(n) if i % 2 == 0}

        def child_keeps(j: int) -> bool:
            i = j if mirror > 0 else n - 1 - j
            return i not in parent_keeps

        def socket_ops(site: EndSite, keep, depth: float) -> list[Any]:
            anchor = site.anchor()
            ops = []
            for i in range(n):
                if keep(i):
                    continue
                x_c = -w / 2.0 + (i + 0.5) * fw
                ops.append(
                    _offset_pocket_cut(
                        anchor,
                        (x_c, 0.0),
                        fw + fit,
                        site.beam.height + 2 * _CUT_MARGIN,
                        depth + fit,
                    )
                )
            return ops

        return [
            (
                self.site_a.beam,
                socket_ops(
                    self.site_a, lambda i: i in parent_keeps, self.site_b.beam.height
                ),
            ),
            (
                self.site_b.beam,
                socket_ops(self.site_b, child_keeps, self.site_a.beam.height),
            ),
        ]

    def mate_anchors(self) -> tuple[Any, Any]:
        s = self.s_a
        t_b = self.site_b.beam.height
        t_a = self.site_a.beam.height
        parent = (
            self.site_a.anchor()
            .rotated(-s * math.pi / 2.0, axis=[1.0, 0.0, 0.0], name=f"corner_tilt_{_seq()}")
            .rotated(math.pi, name=f"corner_spin_{_seq()}")
            .offset([0.0, -s * t_b / 2.0, -t_a / 2.0], name=f"corner_seat_{_seq()}")
        )
        return (parent, self._child_anchor())


class MiterCorner(_CornerInterface):
    """Mitered 90° corner: both ends cut 45° across the thickness.

    The mate plane is the shared 45° miter surface: the parent anchor tilts
    ``-s_a·π/4`` about its X, the child clocks 180° when the inside signs
    multiply positive (opposite of the box-corner rule — miters mate face
    planes, fingers interleave volumes) and tilts ``+s_a·π/4``. Both mate
    anchors' +Z is then the wedge-removal side on their own beam.
    """

    def __init__(self, site_a: EndSite, site_b: EndSite, spec: Optional[MiterSpec] = None):
        super().__init__(site_a, site_b)
        self.spec = spec or MiterSpec()
        if site_a.beam.height != site_b.beam.height:
            raise JoineryError(
                f"miter({site_a.label}, {site_b.label}): a 45° miter needs "
                f"equal thicknesses ({site_a.beam.height:g} != "
                f"{site_b.beam.height:g})"
            )
        self.child_clock = math.pi if self.s_a * self.s_b > 0 else 0.0
        self.label = f"miter({site_a.label}, {site_b.label})"

    def occupancies(self) -> list[tuple[Any, OBB]]:
        # Conservative: the whole 45° end zone (one thickness deep).
        return [
            (self.site_a.beam, self._end_zone(self.site_a, self.site_a.beam.height)),
            (self.site_b.beam, self._end_zone(self.site_b, self.site_b.beam.height)),
        ]

    def _wedge_cut(self, site: EndSite, anchor: Any, span_bump: float) -> Any:
        from cadbuildr.foundation import Extrusion, Rectangle, Sketch, anchor_plane

        beam = site.beam
        # span_bump keeps the (oversized, geometry-irrelevant) cut rectangles
        # content-distinct: the kernel intermittently drops one of two
        # content-identical cut subtrees on the same part (see the
        # kernel-api render-nondeterminism bug), which left uncut corners.
        span = 2.0 * max(beam.width, beam.height, 10.0) + span_bump
        sketch = Sketch(anchor_plane(anchor))
        rect = Rectangle.from_center_and_sides(sketch.origin, span, span)
        return Extrusion(rect, span, 0.0, cut=True)

    def cuts(self) -> list[tuple[Any, list[Any]]]:
        pa, ca = self.mate_anchors()
        return [
            (self.site_a.beam, [self._wedge_cut(self.site_a, pa, 0.25)]),
            (self.site_b.beam, [self._wedge_cut(self.site_b, ca, 0.5)]),
        ]

    def mate_anchors(self) -> tuple[Any, Any]:
        if not hasattr(self, "_mates"):
            t = self.site_a.beam.height
            parent = (
                self.site_a.anchor()
                .offset([0.0, 0.0, -t / 2.0], name=f"miter_mid_{_seq()}")
                .rotated(-self.s_a * math.pi / 4.0, axis=[1.0, 0.0, 0.0], name=f"miter_tilt_{_seq()}")
            )
            child = self.site_b.anchor().offset(
                [0.0, 0.0, -t / 2.0], name=f"miter_mid_{_seq()}"
            )
            if self.child_clock:
                child = child.rotated(self.child_clock, name=f"miter_clk_{_seq()}")
            child = child.rotated(
                self.s_a * math.pi / 4.0, axis=[1.0, 0.0, 0.0], name=f"miter_tilt_{_seq()}"
            )
            self._mates = (parent, child)
        return self._mates


# --------------------------------------------------------------------------- #
# Builder
# --------------------------------------------------------------------------- #


class Joinery:
    """Collects interfaces, validates them as a set, then builds the assembly.

    Parts must not be placed before ``build()`` — the builder owns cutting
    (before placement, so every part keeps live geometry) and placement
    (solved from the interface graph, loop closures verified).
    """

    def __init__(self) -> None:
        self.interfaces: list[Interface] = []

    def add(self, interface: Interface) -> Interface:
        self.interfaces.append(interface)
        return interface

    # sugar ----------------------------------------------------------------
    def mortise_and_tenon(
        self, tenon: EndSite, mortise: FaceSite, spec: Optional[TenonSpec] = None
    ) -> MortiseTenon:
        return self.add(MortiseTenon(tenon, mortise, spec))  # type: ignore[return-value]

    def box_corner(
        self, site_a: EndSite, site_b: EndSite, spec: Optional[FingerSpec] = None
    ) -> BoxCorner:
        return self.add(BoxCorner(site_a, site_b, spec))  # type: ignore[return-value]

    def miter(
        self, site_a: EndSite, site_b: EndSite, spec: Optional[MiterSpec] = None
    ) -> MiterCorner:
        return self.add(MiterCorner(site_a, site_b, spec))  # type: ignore[return-value]

    # build ----------------------------------------------------------------
    def build(
        self,
        ground: Any,
        assembly: Optional[Assembly] = None,
        pos_tol: float = 0.05,
        angle_tol_deg: float = 0.1,
    ) -> Assembly:
        if not self.interfaces:
            raise JoineryError("No interfaces to build")

        self._check_sites()
        self._check_collisions()

        for beam, ops in self._all_cuts():
            if getattr(beam, "_placed_in", None) is not None:
                raise PlacementError(
                    "Parts must not be placed before Joinery.build(): pass the "
                    "grounded part via build(ground=...) and let the builder "
                    "place the rest"
                )
            if ops:
                beam.add_operations(ops)

        assembly = assembly or Assembly()
        assembly.add_component(ground)
        placed = {id(ground)}
        pending = list(self.interfaces)
        closures: list[tuple[Interface, Any, Any]] = []

        progress = True
        while pending and progress:
            progress = False
            for interface in list(pending):
                part_a, part_b = interface.parts
                a_placed, b_placed = id(part_a) in placed, id(part_b) in placed
                if not a_placed and not b_placed:
                    continue
                anchor_a, anchor_b = interface.mate_anchors()
                pending.remove(interface)
                progress = True
                if a_placed and b_placed:
                    closures.append((interface, anchor_a, anchor_b))
                    continue
                parent, child, child_part = (
                    (anchor_a, anchor_b, part_b)
                    if a_placed
                    else (anchor_b, anchor_a, part_a)
                )
                assembly.add_joint(RigidJoint(parent_anchor=parent, child_anchor=child))
                placed.add(id(child_part))

        if pending:
            labels = ", ".join(i.label for i in pending)
            raise PlacementError(
                f"Interfaces not reachable from the grounded part: {labels}"
            )

        for interface, anchor_a, anchor_b in closures:
            self._check_closure(assembly, interface, anchor_a, anchor_b, pos_tol, angle_tol_deg)

        return assembly

    # internals --------------------------------------------------------------
    def _check_sites(self) -> None:
        used: dict[tuple[int, str], Interface] = {}
        for interface in self.interfaces:
            for site in interface.consumed_ends():
                prior = used.get(site.key)
                if prior is not None:
                    raise SiteConflictError(
                        f"{site.label} is claimed by both '{prior.label}' and "
                        f"'{interface.label}' — a beam end hosts at most one "
                        "interface"
                    )
                used[site.key] = interface

    def _check_collisions(self) -> None:
        per_part: dict[int, list[tuple[Interface, OBB, Any]]] = {}
        for interface in self.interfaces:
            for beam, obb in interface.occupancies():
                per_part.setdefault(id(beam), []).append((interface, obb, beam))
        for entries in per_part.values():
            for i in range(len(entries)):
                for j in range(i + 1, len(entries)):
                    ia, obb_a, beam = entries[i]
                    ib, obb_b, _ = entries[j]
                    if ia is ib:
                        continue
                    if obb_intersects(obb_a, obb_b):
                        from .sites import _beam_label

                        raise JointCollisionError(
                            f"'{ia.label}' and '{ib.label}' occupy overlapping "
                            f"wood inside {_beam_label(beam)} — offset their "
                            "positions, shorten the joints, or miter the "
                            "meeting ends"
                        )

    def _all_cuts(self) -> list[tuple[Any, list[Any]]]:
        return [entry for interface in self.interfaces for entry in interface.cuts()]

    def _check_closure(
        self,
        assembly: Assembly,
        interface: Interface,
        anchor_a: Any,
        anchor_b: Any,
        pos_tol: float,
        angle_tol_deg: float,
    ) -> None:
        t_a, q_a = tf_relative_to_frame(anchor_a.frame, assembly.frame)
        t_b, q_b = tf_relative_to_frame(anchor_b.frame, assembly.frame)
        # Mate condition: B = A ∘ flip(π about X).
        t_exp, q_exp = compose_tf(t_a, q_a, [0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0])
        dt, dq = compose_tf(*invert_tf(t_exp, q_exp), t_b, q_b)
        pos_err = float(np.linalg.norm(dt))
        angle_err = math.degrees(2.0 * math.atan2(np.linalg.norm(dq[1:]), abs(dq[0])))
        if pos_err > pos_tol or angle_err > angle_tol_deg:
            raise ClosureError(
                f"'{interface.label}' closes a loop but the parts don't meet: "
                f"position off by {pos_err:.3f} mm, orientation by "
                f"{angle_err:.3f}° — check the beam lengths around the loop"
            )
