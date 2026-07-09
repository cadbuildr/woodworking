"""Wood joinery one-liners: each call positions two beams AND shapes them.

Every joint here is a foundation ``Connection``: one anchor-to-anchor
``RigidJoint`` for placement plus ``PartModifier`` cuts that form the actual
joinery (tenons, mortises, notches) on the connected beams::

    mortise_and_tenon(assembly, rail, leg, face="px", at=300)
    cross_lap(assembly, sleeper, joist, at_a=200, at_b=100)
    dado_joint(assembly, shelf, wall, face="px", at=300)
    box_joint(assembly, side_a, side_b, n_fingers=5)
    through_dovetail(assembly, tail_board, pin_board, n_tails=3)

Implemented taxonomy: butt (plain / screwed / doweled / mitered), dado,
rabbet, laps (cross / end), mortise & tenon, edge joints (plain, tongue &
groove, sliding dovetail), box joint, through dovetail. Planned on the same
pattern: half-blind dovetail, biscuit, pocket-hole, tambour.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from cadbuildr.foundation import (
    Connection,
    Extrusion,
    PartModifier,
    Point,
    Rectangle,
    RigidJoint,
    Sketch,
    anchor_plane,
)

# Cuts extend slightly past the stock surfaces so coincident faces don't
# leave zero-thickness slivers.
_CUT_MARGIN = 0.5


def _pocket_cut(anchor: Any, size_x: float, size_y: float, depth: float) -> Extrusion:
    """A rectangular cut sketched on the anchor plane, going into the part."""
    sketch = Sketch(anchor_plane(anchor))
    pocket = Rectangle.from_center_and_sides(sketch.origin, size_x, size_y)
    return Extrusion(pocket, 0.0, -depth, cut=True)


def _shoulder_cuts(
    end_anchor: Any,
    stock_w: float,
    stock_h: float,
    tenon_w: float,
    tenon_h: float,
    depth: float,
) -> list[Extrusion]:
    """Four strip cuts around the tenon on the beam end plane."""
    sketch = Sketch(anchor_plane(end_anchor))
    strip_x = (stock_w - tenon_w) / 2.0
    strip_y = (stock_h - tenon_h) / 2.0
    cuts = []
    if strip_x > 0:
        for side in (1.0, -1.0):
            center = Point(
                sketch, side * (tenon_w / 2.0 + strip_x / 2.0 + _CUT_MARGIN / 2.0), 0.0
            )
            rect = Rectangle.from_center_and_sides(
                center, strip_x + _CUT_MARGIN, stock_h + 2 * _CUT_MARGIN
            )
            cuts.append(Extrusion(rect, 0.0, -depth, cut=True))
    if strip_y > 0:
        for side in (1.0, -1.0):
            center = Point(
                sketch, 0.0, side * (tenon_h / 2.0 + strip_y / 2.0 + _CUT_MARGIN / 2.0)
            )
            rect = Rectangle.from_center_and_sides(
                center, tenon_w, strip_y + _CUT_MARGIN
            )
            cuts.append(Extrusion(rect, 0.0, -depth, cut=True))
    return cuts


def mortise_and_tenon(
    assembly: Any,
    tenon_beam: Any,
    mortise_beam: Any,
    face: str = "px",
    at: Optional[float] = None,
    end: str = "b",
    depth: Optional[float] = None,
    shoulder: Optional[float] = None,
    fit: float = 0.2,
    through: bool = False,
) -> Connection:
    """Join ``tenon_beam``'s end into ``mortise_beam``'s side face (T-joint).

    One line does all of it: forms the tenon (shoulder cuts on the end), cuts
    the matching mortise pocket into the face, and places the beams
    perpendicular with the shoulder seated on the face.

    Args:
        face: which side of the mortise beam (``px``/``nx``/``py``/``ny``).
        at: millimeters along the mortise beam (default: mid-length).
        end: which end of the tenon beam carries the tenon (``a``/``b``).
        depth: tenon length (default: 60% of the mortise beam's thickness;
            with ``through=True`` the full thickness, tenon flush).
        shoulder: shoulder width all around (default: quarter of the smaller
            tenon-beam cross dimension).
        fit: clearance added around the mortise pocket.
        through: pierce the mortise beam so the tenon end shows on the far
            face (the exposed-tenon look).
    """
    if at is None:
        at = mortise_beam.length / 2.0
    thickness = mortise_beam.face_thickness(face)
    if depth is None:
        depth = thickness if through else 0.6 * thickness
    if through:
        if depth > thickness:
            raise ValueError(
                f"Through tenon depth {depth} exceeds the mortise beam "
                f"thickness {thickness} (the tenon would protrude)"
            )
    elif depth >= thickness:
        raise ValueError(
            f"Tenon depth {depth} would pierce the mortise beam (thickness {thickness})"
        )
    if shoulder is None:
        shoulder = min(tenon_beam.width, tenon_beam.height) / 4.0
    tenon_w = tenon_beam.width - 2.0 * shoulder
    tenon_h = tenon_beam.height - 2.0 * shoulder
    if tenon_w <= 0 or tenon_h <= 0:
        raise ValueError("Shoulder too large: no tenon material left")

    end_anchor = tenon_beam.anchor(f"end_{end}")
    shoulder_anchor = end_anchor.offset([0.0, 0.0, -depth], name=f"mt_shoulder_{face}")
    pocket_anchor = mortise_beam.anchor(f"face_{face}").offset(
        [at, 0.0, 0.0], name=f"mt_pocket_{at:g}"
    )

    connection = Connection(
        joint=RigidJoint(parent_anchor=pocket_anchor, child_anchor=shoulder_anchor),
        modifiers=[
            PartModifier(
                anchor=end_anchor,
                operations=_shoulder_cuts(
                    end_anchor,
                    tenon_beam.width,
                    tenon_beam.height,
                    tenon_w,
                    tenon_h,
                    depth,
                ),
            ),
            PartModifier(
                anchor=pocket_anchor,
                operations=[
                    _pocket_cut(
                        pocket_anchor,
                        tenon_w + 2.0 * fit,
                        tenon_h + 2.0 * fit,
                        # Through mortises pierce the far face cleanly.
                        depth + (_CUT_MARGIN if through else fit),
                    )
                ],
            ),
        ],
    )
    assembly.add_connection(connection)
    return connection


def cross_lap(
    assembly: Any,
    beam_a: Any,
    beam_b: Any,
    at_a: Optional[float] = None,
    at_b: Optional[float] = None,
    fit: float = 0.2,
) -> Connection:
    """Half-lap two beams crossing at a right angle.

    Both beams get a notch half their height deep on their ``py`` face; the
    rigid mate flips the child over (anchor-to-anchor joints mate with a 180°
    flip), so the notches face each other and interlock with coincident
    mid-planes — equal-height beams end up flush.

    Args:
        at_a / at_b: notch centers, millimeters along each beam
            (default: mid-length).
    """
    if at_a is None:
        at_a = beam_a.length / 2.0
    if at_b is None:
        at_b = beam_b.length / 2.0

    depth_a = beam_a.height / 2.0
    depth_b = beam_b.height / 2.0

    face_a = beam_a.anchor("face_py").offset([at_a, 0.0, 0.0], name=f"lap_a_{at_a:g}")
    face_b = beam_b.anchor("face_py").offset([at_b, 0.0, 0.0], name=f"lap_b_{at_b:g}")

    import math

    connection = Connection(
        joint=RigidJoint(
            # Sink each anchor to its beam's mid-plane; rotate 90° so the
            # beams cross instead of lying parallel.
            parent_anchor=face_a.offset([0.0, 0.0, -depth_a], name="lap_a_mid").rotated(
                math.pi / 2.0, name="lap_a_cross"
            ),
            child_anchor=face_b.offset([0.0, 0.0, -depth_b], name="lap_b_mid"),
        ),
        modifiers=[
            PartModifier(
                anchor=face_a,
                operations=[
                    _pocket_cut(
                        face_a,
                        beam_b.width + fit,
                        beam_a.width + 2 * _CUT_MARGIN,
                        depth_a,
                    )
                ],
            ),
            PartModifier(
                anchor=face_b,
                operations=[
                    _pocket_cut(
                        face_b,
                        beam_a.width + fit,
                        beam_b.width + 2 * _CUT_MARGIN,
                        depth_b,
                    )
                ],
            ),
        ],
    )
    assembly.add_connection(connection)
    return connection


def _offset_pocket_cut(
    anchor: Any,
    center: tuple[float, float],
    size_x: float,
    size_y: float,
    depth: float,
) -> Extrusion:
    """Rectangular cut on the anchor plane at an off-center position."""
    sketch = Sketch(anchor_plane(anchor))
    rect = Rectangle.from_center_and_sides(
        Point(sketch, center[0], center[1]), size_x, size_y
    )
    return Extrusion(rect, 0.0, -depth, cut=True)


def _polygon_cut(
    anchor: Any, points: list[tuple[float, float]], depth: float
) -> Extrusion:
    """Polygonal cut (pencil polyline) on the anchor plane, into the part."""
    sketch = Sketch(anchor_plane(anchor))
    pencil = sketch.pencil
    pencil.move_to(points[0][0], points[0][1])
    for x, y in points[1:]:
        pencil.line_to(x, y)
    shape = pencil.close()
    return Extrusion(shape, 0.0, -depth, cut=True)


def _length_profile_cut(beam: Any, shape_builder) -> Extrusion:
    """Cut a 2D profile through the beam's whole length (edge-joint idiom)."""
    sketch = Sketch(beam.xy())
    shape = shape_builder(sketch)
    return Extrusion(shape, beam.length + _CUT_MARGIN, -_CUT_MARGIN, cut=True)


def butt_joint(
    assembly: Any,
    end_beam: Any,
    face_beam: Any,
    face: str = "px",
    at: Optional[float] = None,
    end: str = "b",
) -> Connection:
    """Plain butt: one beam's end against another's face (T), no shaping.

    Reinforce with :func:`doweled_butt` or ``connect_with_screw`` from the
    stdlib fasteners library.
    """
    if at is None:
        at = face_beam.length / 2.0
    seat = face_beam.anchor(f"face_{face}").offset([at, 0.0, 0.0], name=f"butt_{at:g}")
    connection = Connection(
        joint=RigidJoint(parent_anchor=seat, child_anchor=end_beam.anchor(f"end_{end}"))
    )
    assembly.add_connection(connection)
    return connection


def mitered_butt(
    assembly: Any,
    beam_a: Any,
    beam_b: Any,
    end_a: str = "b",
    end_b: str = "b",
) -> Connection:
    """Mitered corner: both ends cut 45° and mated into an L-frame.

    The miter runs across each beam's height (the wedge toward ``face_ny`` is
    removed), hiding the end grain on the outside of the corner.
    """

    def _miter_cut(beam, end, sign):
        # Opposite tilt signs on the two beams: mating the 45° planes
        # face-to-face then yields a 90° corner (same sign gives 180°).
        anchor = beam.anchor(f"end_{end}").rotated(
            sign * math.pi / 4.0, axis=[1.0, 0.0, 0.0], name=f"miter_{end}"
        )
        span = 2.0 * max(beam.width, beam.height, 10.0)
        sketch = Sketch(anchor_plane(anchor))
        rect = Rectangle.from_center_and_sides(sketch.origin, span, span)
        # Remove the wedge on the +normal side of the 45° plane.
        return anchor, Extrusion(rect, span, 0.0, cut=True)

    anchor_a, cut_a = _miter_cut(beam_a, end_a, +1.0)
    anchor_b, cut_b = _miter_cut(beam_b, end_b, -1.0)
    connection = Connection(
        joint=RigidJoint(parent_anchor=anchor_a, child_anchor=anchor_b),
        modifiers=[
            PartModifier(anchor=beam_a.anchor(f"end_{end_a}"), operations=[cut_a]),
            PartModifier(anchor=beam_b.anchor(f"end_{end_b}"), operations=[cut_b]),
        ],
    )
    assembly.add_connection(connection)
    return connection


def dado_joint(
    assembly: Any,
    shelf: Any,
    wall: Any,
    face: str = "px",
    at: Optional[float] = None,
    end: str = "b",
    depth: Optional[float] = None,
    fit: float = 0.2,
) -> Connection:
    """Dado: a three-sided slot across ``wall``'s face houses ``shelf``'s end.

    Unlike a mortise & tenon the whole end sits in the slot — no tenon is
    formed on the shelf.
    """
    if at is None:
        at = wall.length / 2.0
    thickness = wall.face_thickness(face)
    if depth is None:
        depth = 0.3 * thickness
    if depth >= thickness:
        raise ValueError(f"Dado depth {depth} would pierce the wall (thickness {thickness})")

    slot_span = (wall.height if face in ("px", "nx") else wall.width) + 2 * _CUT_MARGIN
    face_at = wall.anchor(f"face_{face}").offset([at, 0.0, 0.0], name=f"dado_{at:g}")
    connection = Connection(
        joint=RigidJoint(
            parent_anchor=face_at.offset([0.0, 0.0, -depth], name="dado_seat"),
            child_anchor=shelf.anchor(f"end_{end}"),
        ),
        modifiers=[
            PartModifier(
                anchor=face_at,
                operations=[_pocket_cut(face_at, shelf.width + fit, slot_span, depth + fit)],
            )
        ],
    )
    assembly.add_connection(connection)
    return connection


def rabbet_joint(
    assembly: Any,
    board: Any,
    edge_board: Any,
    recess: Optional[float] = None,
    fit: float = 0.2,
) -> Connection:
    """Rabbet corner: a two-sided step at ``edge_board``'s end (``end_b``,
    opening toward ``face_py``) seats ``board``'s end flush in the corner."""
    t_v = board.height + fit
    if recess is None:
        recess = edge_board.height / 2.0
    if recess >= edge_board.height:
        raise ValueError("Rabbet recess deeper than the board")
    length = edge_board.length
    x_at = length - t_v / 2.0

    face_py = edge_board.anchor("face_py")
    seat = face_py.offset([x_at, 0.0, -recess], name="rabbet_seat").rotated(
        math.pi / 2.0, name="rabbet_seat_cross"
    )
    cut_anchor = face_py.offset(
        [x_at + _CUT_MARGIN / 2.0, 0.0, 0.0], name="rabbet_cut"
    )
    connection = Connection(
        joint=RigidJoint(parent_anchor=seat, child_anchor=board.anchor("end_b")),
        modifiers=[
            PartModifier(
                anchor=cut_anchor,
                operations=[
                    _pocket_cut(
                        cut_anchor,
                        t_v + _CUT_MARGIN,
                        edge_board.width + 2 * _CUT_MARGIN,
                        recess,
                    )
                ],
            )
        ],
    )
    assembly.add_connection(connection)
    return connection


def end_lap(
    assembly: Any,
    beam_a: Any,
    beam_b: Any,
    lap: Optional[float] = None,
    fit: float = 0.2,
) -> Connection:
    """Corner half-lap: both ends notched half-depth and overlapped at 90°."""
    if lap is None:
        lap = max(beam_a.width, beam_b.width)
    depth_a = beam_a.height / 2.0
    depth_b = beam_b.height / 2.0
    at_a = beam_a.length - lap / 2.0
    at_b = beam_b.length - lap / 2.0

    # Both notches on py: the rigid mate flips the child, so they interlock.
    face_a = beam_a.anchor("face_py").offset([at_a, 0.0, 0.0], name="endlap_a")
    face_b = beam_b.anchor("face_py").offset([at_b, 0.0, 0.0], name="endlap_b")
    connection = Connection(
        joint=RigidJoint(
            parent_anchor=face_a.offset([0.0, 0.0, -depth_a], name="endlap_a_mid").rotated(
                math.pi / 2.0, name="endlap_a_cross"
            ),
            child_anchor=face_b.offset([0.0, 0.0, -depth_b], name="endlap_b_mid"),
        ),
        modifiers=[
            PartModifier(
                anchor=face_a,
                operations=[
                    _offset_pocket_cut(
                        face_a,
                        (_CUT_MARGIN / 2.0, 0.0),
                        lap + fit + _CUT_MARGIN,
                        beam_a.width + 2 * _CUT_MARGIN,
                        depth_a,
                    )
                ],
            ),
            PartModifier(
                anchor=face_b,
                operations=[
                    _offset_pocket_cut(
                        face_b,
                        (_CUT_MARGIN / 2.0, 0.0),
                        lap + fit + _CUT_MARGIN,
                        beam_b.width + 2 * _CUT_MARGIN,
                        depth_b,
                    )
                ],
            ),
        ],
    )
    assembly.add_connection(connection)
    return connection


def doweled_butt(
    assembly: Any,
    end_beam: Any,
    face_beam: Any,
    face: str = "px",
    at: Optional[float] = None,
    end: str = "b",
    n_dowels: int = 2,
    dowel_diameter: float = 8.0,
    dowel_length: float = 40.0,
    fit: float = 0.2,
) -> Connection:
    """Butt joint reinforced with dowel pins: matching holes are drilled in
    both pieces and real dowel parts are placed spanning the interface."""
    from .beam import Dowel
    from cadbuildr.foundation import Circle

    if at is None:
        at = face_beam.length / 2.0
    seat = face_beam.anchor(f"face_{face}").offset(
        [at, 0.0, 0.0], name=f"dbutt_{at:g}"
    )
    end_anchor = end_beam.anchor(f"end_{end}")

    spread = end_beam.width / 2.0
    offsets = [
        (i - (n_dowels - 1) / 2.0) * (spread / max(1, (n_dowels - 1) / 2.0) / 2.0)
        if n_dowels > 1
        else 0.0
        for i in range(n_dowels)
    ]
    hole_r = dowel_diameter / 2.0 + fit
    hole_depth = dowel_length / 2.0 + fit

    def _bore(anchor, dx):
        sketch = Sketch(anchor_plane(anchor))
        return Extrusion(
            Circle(Point(sketch, dx, 0.0), hole_r), 0.0, -hole_depth, cut=True
        )

    connection = Connection(
        joint=RigidJoint(parent_anchor=seat, child_anchor=end_anchor),
        modifiers=[
            PartModifier(anchor=seat, operations=[_bore(seat, dx) for dx in offsets]),
            PartModifier(
                anchor=end_anchor,
                operations=[_bore(end_anchor, dx) for dx in offsets],
            ),
        ],
    )
    assembly.add_connection(connection)

    for i, dx in enumerate(offsets):
        dowel = Dowel(diameter=dowel_diameter, length=dowel_length)
        assembly.add_joint(
            RigidJoint(
                parent_anchor=seat.offset([dx, 0.0, 0.0], name=f"dowel_{i}"),
                child_anchor=dowel.anchor("mid"),
            )
        )
    return connection


def edge_joint(
    assembly: Any, board_a: Any, board_b: Any
) -> Connection:
    """Plain glued edge joint: two boards side by side forming a wider panel."""
    mid = board_a.length / 2.0
    connection = Connection(
        joint=RigidJoint(
            parent_anchor=board_a.anchor("face_px").offset([mid, 0.0, 0.0], name="edge_a"),
            child_anchor=board_b.anchor("face_nx").offset(
                [board_b.length / 2.0, 0.0, 0.0], name="edge_b"
            ),
        )
    )
    assembly.add_connection(connection)
    return connection


def tongue_and_groove(
    assembly: Any,
    tongue_board: Any,
    groove_board: Any,
    tongue: Optional[float] = None,
    thickness: Optional[float] = None,
    fit: float = 0.15,
) -> Connection:
    """Edge joint with an interlocking tongue: two full-length rabbets form
    the tongue on one board, a matching full-length groove on the other."""
    if thickness is None:
        thickness = tongue_board.height / 3.0
    if tongue is None:
        tongue = tongue_board.height / 2.0
    w_t, h_t = tongue_board.width, tongue_board.height
    w_g, h_g = groove_board.width, groove_board.height
    if thickness >= min(h_t, h_g):
        raise ValueError("Tongue thickness leaves no shoulder")

    tongue_cuts = []
    for side in (1.0, -1.0):
        # Shoulder strip: from the tongue face out past the board surface,
        # spanning x from the shoulder line past the edge.
        y_lo = thickness / 2.0
        y_hi = h_t / 2.0 + _CUT_MARGIN
        y_c = side * (y_lo + y_hi) / 2.0
        size_y = y_hi - y_lo
        x_c = w_t / 2.0 - tongue / 2.0 + _CUT_MARGIN / 2.0

        def _builder(sketch, x_c=x_c, y_c=y_c, size_y=size_y):
            return Rectangle.from_center_and_sides(
                Point(sketch, x_c, y_c), tongue + _CUT_MARGIN, size_y
            )

        tongue_cuts.append(_length_profile_cut(tongue_board, _builder))

    def _groove_builder(sketch):
        return Rectangle.from_center_and_sides(
            Point(sketch, -w_g / 2.0 + (tongue + fit) / 2.0 - _CUT_MARGIN / 2.0, 0.0),
            tongue + fit + _CUT_MARGIN,
            thickness + 2.0 * fit,
        )

    groove_cut = _length_profile_cut(groove_board, _groove_builder)

    connection = Connection(
        joint=RigidJoint(
            parent_anchor=tongue_board.anchor("face_px").offset(
                [tongue_board.length / 2.0, 0.0, -tongue], name="tng_shoulder"
            ),
            child_anchor=groove_board.anchor("face_nx").offset(
                [groove_board.length / 2.0, 0.0, 0.0], name="tng_edge"
            ),
        ),
        modifiers=[
            PartModifier(anchor=tongue_board.anchor("face_px"), operations=tongue_cuts),
            PartModifier(anchor=groove_board.anchor("face_nx"), operations=[groove_cut]),
        ],
    )
    assembly.add_connection(connection)
    return connection


def sliding_dovetail(
    assembly: Any,
    tail_board: Any,
    groove_board: Any,
    tail: Optional[float] = None,
    root: Optional[float] = None,
    flare: float = 0.25,
    fit: float = 0.15,
) -> Connection:
    """Edge joint with a dovetail-profile tongue: like tongue-and-groove but
    the tongue flares (wider at its tip), mechanically locking the boards.

    ``flare`` is the half-width increase per unit of tongue length
    (tan of the dovetail angle, ~14°)."""
    h = tail_board.height
    if tail is None:
        tail = tail_board.height / 2.0
    if root is None:
        root = tail_board.height / 3.0
    tip = root + 2.0 * flare * tail
    if tip >= h:
        raise ValueError("Dovetail tip exceeds board thickness")
    w_t = tail_board.width
    w_g = groove_board.width

    tail_cuts = []
    x_root = w_t / 2.0 - tail
    x_tip = w_t / 2.0 + _CUT_MARGIN
    for side in (1.0, -1.0):
        points = [
            (x_root, side * root / 2.0),
            (x_tip, side * (tip / 2.0 + flare * _CUT_MARGIN)),
            (x_tip, side * (h / 2.0 + _CUT_MARGIN)),
            (x_root, side * (h / 2.0 + _CUT_MARGIN)),
        ]

        def _builder(sketch, points=points):
            pencil = sketch.pencil
            pencil.move_to(points[0][0], points[0][1])
            for x, y in points[1:]:
                pencil.line_to(x, y)
            return pencil.close()

        tail_cuts.append(_length_profile_cut(tail_board, _builder))

    gx_open = -w_g / 2.0 - _CUT_MARGIN
    gx_bottom = -w_g / 2.0 + tail + fit
    groove_points = [
        (gx_open, -(root / 2.0 + fit + flare * _CUT_MARGIN)),
        (gx_bottom, -(tip / 2.0 + fit)),
        (gx_bottom, tip / 2.0 + fit),
        (gx_open, root / 2.0 + fit + flare * _CUT_MARGIN),
    ]

    def _groove_builder(sketch):
        pencil = sketch.pencil
        pencil.move_to(groove_points[0][0], groove_points[0][1])
        for x, y in groove_points[1:]:
            pencil.line_to(x, y)
        return pencil.close()

    groove_cut = _length_profile_cut(groove_board, _groove_builder)

    connection = Connection(
        joint=RigidJoint(
            parent_anchor=tail_board.anchor("face_px").offset(
                [tail_board.length / 2.0, 0.0, -tail], name="sdt_shoulder"
            ),
            child_anchor=groove_board.anchor("face_nx").offset(
                [groove_board.length / 2.0, 0.0, 0.0], name="sdt_edge"
            ),
        ),
        modifiers=[
            PartModifier(anchor=tail_board.anchor("face_px"), operations=tail_cuts),
            PartModifier(anchor=groove_board.anchor("face_nx"), operations=[groove_cut]),
        ],
    )
    assembly.add_connection(connection)
    return connection


def _corner_seat(beam_a: Any, other_thickness: float) -> Any:
    """Parent anchor for box/dovetail corners: the child board's end mates
    here, perpendicular to ``beam_a`` with the end regions interleaved."""
    return (
        beam_a.anchor("end_b")
        .rotated(-math.pi / 2.0, axis=[1.0, 0.0, 0.0], name="corner_tilt")
        .offset([0.0, other_thickness / 2.0, -beam_a.height / 2.0], name="corner_seat")
    )


def box_joint(
    assembly: Any,
    beam_a: Any,
    beam_b: Any,
    n_segments: int = 5,
    fit: float = 0.15,
) -> Connection:
    """Box (finger) corner: alternating square fingers interlock at 90°.

    ``n_segments`` is the total finger count across the width (odd counts
    look traditional). ``beam_a`` keeps the even segments, ``beam_b`` the odd.
    """
    if beam_a.width != beam_b.width:
        raise ValueError("Box joint requires equal board widths")
    if n_segments < 2:
        raise ValueError("Need at least 2 segments")
    w = beam_a.width
    fw = w / n_segments

    def _socket_cuts(beam, keep_even, depth):
        cuts = []
        for i in range(n_segments):
            if (i % 2 == 0) == keep_even:
                continue
            x_c = -w / 2.0 + (i + 0.5) * fw
            cuts.append(
                _offset_pocket_cut(
                    beam.anchor("end_b"),
                    (x_c, 0.0),
                    fw + fit,
                    beam.height + 2 * _CUT_MARGIN,
                    depth + fit,
                )
            )
        return cuts

    connection = Connection(
        joint=RigidJoint(
            parent_anchor=_corner_seat(beam_a, beam_b.height),
            child_anchor=beam_b.anchor("end_b"),
        ),
        modifiers=[
            PartModifier(
                anchor=beam_a.anchor("end_b"),
                operations=_socket_cuts(beam_a, True, beam_b.height),
            ),
            PartModifier(
                anchor=beam_b.anchor("end_b"),
                operations=_socket_cuts(beam_b, False, beam_a.height),
            ),
        ],
    )
    assembly.add_connection(connection)
    return connection


def through_dovetail(
    assembly: Any,
    tail_board: Any,
    pin_board: Any,
    n_tails: int = 3,
    angle: float = math.radians(14.0),
    fit: float = 0.15,
) -> Connection:
    """Through dovetail corner: flared tails on one board interlock with pins
    on the other, visible from both faces.

    Tails flare in the board plane (cut through the thickness from the face),
    which is what makes the joint mechanically locked, unlike a box joint.
    """
    if tail_board.width != pin_board.width:
        raise ValueError("Dovetail requires equal board widths")
    w = tail_board.width
    pitch = w / n_tails
    tail_len = pin_board.height  # tails span the pin board's thickness
    root = pitch * 0.6
    flare = math.tan(angle)
    tip = root + 2.0 * flare * tail_len

    tail_centers = [-w / 2.0 + (i + 0.5) * pitch for i in range(n_tails)]

    def _face_polygon_cuts(beam, sockets, depth):
        """Trapezoid cuts through the board thickness near end_b, sketched on
        face_py (plane X = along the beam, Y = across the width)."""
        anchor = beam.anchor("face_py")
        length = beam.length
        cuts = []
        for x_end_lo, x_end_hi, x_root_lo, x_root_hi, socket_depth in sockets:
            points = [
                (length - socket_depth, x_root_lo),
                (length + _CUT_MARGIN, x_end_lo),
                (length + _CUT_MARGIN, x_end_hi),
                (length - socket_depth, x_root_hi),
            ]
            cuts.append(_polygon_cut(anchor, points, depth))
        return cuts

    # Sockets on the tail board = the gaps between tails (pins slide in):
    # narrow at the end face, wide at the root — the complement of the tails.
    tail_sockets = []
    edges = [-w / 2.0 - _CUT_MARGIN] + [
        c for center in tail_centers for c in (center, center)
    ] + [w / 2.0 + _CUT_MARGIN]
    for i in range(n_tails + 1):
        lo_center = edges[2 * i]
        hi_center = edges[2 * i + 1]
        end_lo = lo_center + (tip / 2.0 if i > 0 else 0.0)
        end_hi = hi_center - (tip / 2.0 if i < n_tails else 0.0)
        root_lo = lo_center + (root / 2.0 if i > 0 else 0.0) - (fit if i > 0 else 0.0)
        root_hi = hi_center - (root / 2.0 if i < n_tails else 0.0) + (
            fit if i < n_tails else 0.0
        )
        end_lo -= fit if i > 0 else 0.0
        end_hi += fit if i < n_tails else 0.0
        tail_sockets.append((end_lo, end_hi, root_lo, root_hi, tail_len))

    # Sockets on the pin board = the tail passages. The mating flank planes
    # contain the pin board's LENGTH axis and flare across its THICKNESS
    # (tail tips at the outer face, roots at the inner face), so they are
    # trapezoid prisms cut from the end face — NOT length-wise polygons.
    def _pin_socket_cuts(outer_sign: float) -> list[Extrusion]:
        anchor = pin_board.anchor("end_b")
        h = pin_board.height
        y_out = outer_sign * (h / 2.0 + _CUT_MARGIN)
        y_in = -outer_sign * (h / 2.0 + _CUT_MARGIN)
        # Extrapolate the flare past both faces by the margin.
        half_out = tip / 2.0 + fit + flare * _CUT_MARGIN
        half_in = root / 2.0 + fit - flare * _CUT_MARGIN
        cuts = []
        for center in tail_centers:
            points = [
                (center - half_out, y_out),
                (center + half_out, y_out),
                (center + half_in, y_in),
                (center - half_in, y_in),
            ]
            cuts.append(_polygon_cut(anchor, points, tail_board.height + fit))
        return cuts

    connection = Connection(
        joint=RigidJoint(
            parent_anchor=_corner_seat(tail_board, pin_board.height),
            child_anchor=pin_board.anchor("end_b"),
        ),
        modifiers=[
            PartModifier(
                anchor=tail_board.anchor("end_b"),
                operations=_face_polygon_cuts(
                    tail_board, tail_sockets, tail_board.height + 2 * _CUT_MARGIN
                ),
            ),
            PartModifier(
                anchor=pin_board.anchor("end_b"),
                operations=_pin_socket_cuts(1.0),
            ),
        ],
    )
    assembly.add_connection(connection)
    return connection
