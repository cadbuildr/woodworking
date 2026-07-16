"""Acceptance tests for the precise joinery interfaces API.

These are the assemblies the legacy one-liners could not express or got
silently wrong: a four-corner finger-jointed box, a table corner with two
tenons in one leg, and a closed mitered frame.
"""

import math

import numpy as np
import pytest

from cadbuildr.foundation import Assembly
from cadbuildr.foundation.math_utils import (
    quaternion_rotate_vector,
    tf_relative_to_frame,
)

from cadbuildr.woodworking import (
    Beam,
    ClosureError,
    FingerSpec,
    Joinery,
    JointCollisionError,
    PlacementError,
    SiteConflictError,
    TenonSpec,
)


def _world_axis(assembly, beam, axis=(0, 0, 1)):
    _, q = tf_relative_to_frame(beam.frame, assembly.frame)
    return np.array(quaternion_rotate_vector(q, list(axis)))


def _world_point(assembly, beam, p_local):
    t, q = tf_relative_to_frame(beam.frame, assembly.frame)
    return np.array(quaternion_rotate_vector(q, list(p_local))) + np.array(t)


# --------------------------------------------------------------------------- #
# The box: four corners, the last one closes the loop.
# --------------------------------------------------------------------------- #


def _make_box(l_ab=300.0, l_bc=200.0, l_cd=300.0, l_da=200.0):
    a = Beam(120, 18, l_ab, color="#c9a36a")
    b = Beam(120, 18, l_bc, color="#8a6a45")
    c = Beam(120, 18, l_cd, color="#d2b48c")
    d = Beam(120, 18, l_da, color="#a97c50")
    j = Joinery()
    spec = FingerSpec(count=6)
    j.box_corner(a.end("b").inside("ny"), b.end("a").inside("ny"), spec)
    j.box_corner(b.end("b").inside("ny"), c.end("a").inside("ny"), spec)
    j.box_corner(c.end("b").inside("ny"), d.end("a").inside("ny"), spec)
    j.box_corner(d.end("b").inside("ny"), a.end("a").inside("ny"), spec)
    return (a, b, c, d), j


def test_box_four_corners_closes():
    (a, b, c, d), j = _make_box()
    assembly = j.build(ground=a)

    assert len(assembly.components) == 4
    # Three placing joints; the fourth corner closes the loop (cuts only).
    assert len(assembly.joints) == 3

    # Consecutive boards are perpendicular, opposite boards antiparallel.
    axes = [_world_axis(assembly, beam) for beam in (a, b, c, d)]
    for i in range(4):
        assert abs(np.dot(axes[i], axes[(i + 1) % 4])) == pytest.approx(0.0, abs=1e-9)
    assert np.dot(axes[0], axes[2]) == pytest.approx(-1.0, abs=1e-9)

    # Every corner got finger cuts on both boards (6 segments -> 3 sockets
    # per board per corner, both ends of every board cut).
    for beam in (a, b, c, d):
        # Beam base ops: extrusion + paint; each corner adds 3 sockets per end.
        assert len(beam.operations) >= 6


def test_box_wrong_length_raises_closure_error():
    boards, j = _make_box(l_da=210.0)  # 10mm too long: the loop cannot close
    with pytest.raises(ClosureError, match="position off by 10"):
        j.build(ground=boards[0])


def test_box_end_reuse_raises():
    a = Beam(120, 18, 300)
    b = Beam(120, 18, 200)
    c = Beam(120, 18, 200)
    j = Joinery()
    j.box_corner(a.end("b").inside("ny"), b.end("a").inside("ny"))
    with pytest.raises(SiteConflictError, match="end_b is claimed by both"):
        j.box_corner(a.end("b").inside("ny"), c.end("a").inside("ny"))
        j.build(ground=a)


def test_box_requires_explicit_fold_direction():
    a = Beam(120, 18, 300)
    b = Beam(120, 18, 200)
    j = Joinery()
    with pytest.raises(ValueError, match="inside"):
        j.box_corner(a.end("b"), b.end("a"))


def test_box_disconnected_part_raises():
    a = Beam(120, 18, 300)
    b = Beam(120, 18, 200)
    c = Beam(120, 18, 200)
    d = Beam(120, 18, 200)
    j = Joinery()
    j.box_corner(a.end("b").inside("ny"), b.end("a").inside("ny"))
    j.box_corner(c.end("b").inside("ny"), d.end("a").inside("ny"))
    with pytest.raises(PlacementError, match="not reachable"):
        j.build(ground=a)


# --------------------------------------------------------------------------- #
# The table corner: two tenons in one leg.
# --------------------------------------------------------------------------- #


def _table_corner(height_x=650.0, height_y=650.0, spec=None):
    leg = Beam(45, 45, 700)
    rail_x = Beam(45, 45, 300)
    rail_y = Beam(45, 45, 300)
    j = Joinery()
    j.mortise_and_tenon(
        rail_x.end("b"), leg.face("px").at(height_x, from_="a"), spec
    )
    j.mortise_and_tenon(
        rail_y.end("b"), leg.face("py").at(height_y, from_="a"), spec
    )
    return leg, j


def test_table_corner_same_height_collides():
    leg, j = _table_corner()
    with pytest.raises(JointCollisionError, match="overlapping wood"):
        j.build(ground=leg)


def test_table_corner_offset_heights_passes():
    leg, j = _table_corner(height_x=650.0, height_y=610.0)
    assembly = j.build(ground=leg)
    assert len(assembly.components) == 3
    assert len(assembly.joints) == 2


def test_table_corner_short_tenons_pass_at_same_height():
    # 22.5mm-wide pockets from adjacent faces of a 45mm leg stay clear of
    # each other only below ~11mm depth: 22.5 - depth - fit > width/2 + fit.
    leg, j = _table_corner(spec=TenonSpec(length=10.0))
    assembly = j.build(ground=leg)
    assert len(assembly.joints) == 2


def test_table_corner_medium_tenons_still_collide():
    # 15mm tenons look safe (15+15 < 45) but the POCKETS still cross:
    # pocket A reaches x > 7.3 while pocket B spans |x| < 11.45.
    leg, j = _table_corner(spec=TenonSpec(length=15.0))
    with pytest.raises(JointCollisionError):
        j.build(ground=leg)


# --------------------------------------------------------------------------- #
# Mortise & tenon precision: explicit datum, explicit clocking.
# --------------------------------------------------------------------------- #


def test_mt_at_measured_from_either_end():
    leg_a = Beam(45, 45, 700)
    rail_a = Beam(45, 45, 300)
    j1 = Joinery()
    j1.mortise_and_tenon(rail_a.end("b"), leg_a.face("px").at(650, from_="a"))
    asm1 = j1.build(ground=leg_a)

    leg_b = Beam(45, 45, 700)
    rail_b = Beam(45, 45, 300)
    j2 = Joinery()
    j2.mortise_and_tenon(rail_b.end("b"), leg_b.face("px").at(50, from_="b"))
    asm2 = j2.build(ground=leg_b)

    p1 = _world_point(asm1, rail_a, [0, 0, 0])
    p2 = _world_point(asm2, rail_b, [0, 0, 0])
    np.testing.assert_allclose(p1, p2, atol=1e-9)


def test_mt_at_middle_named_default():
    leg = Beam(45, 45, 700)
    rail = Beam(45, 45, 300)
    j = Joinery()
    j.mortise_and_tenon(rail.end("b"), leg.face("px").at_middle())
    assembly = j.build(ground=leg)
    # Same as an explicit at(350, from_="a").
    rail_origin = _world_point(assembly, rail, [0, 0, 0])
    assert rail_origin[2] == pytest.approx(350.0, abs=1e-9)


def test_mt_requires_explicit_datum():
    leg = Beam(45, 45, 700)
    rail = Beam(45, 45, 300)
    j = Joinery()
    with pytest.raises(ValueError, match="at\\(dist, from_"):
        j.mortise_and_tenon(rail.end("b"), leg.face("px"))
        j.build(ground=leg)


def test_mt_clocking_rotates_rail():
    # Clocking reference: the face anchor X runs ALONG the mortise beam, so
    # at clock 0 the rail's local X (its width) aligns with the leg axis;
    # clocked(90) turns it across.
    def build(clock):
        leg = Beam(45, 45, 700)
        rail = Beam(30, 60, 300)  # asymmetric cross-section
        j = Joinery()
        site = leg.face("px").at(650, from_="a")
        if clock:
            site = site.clocked(clock)
        j.mortise_and_tenon(rail.end("b"), site, TenonSpec(width=16, thickness=16, length=20))
        return j.build(ground=leg), rail

    asm0, rail0 = build(0)
    assert abs(_world_axis(asm0, rail0, (1, 0, 0))[2]) == pytest.approx(1.0, abs=1e-9)

    asm90, rail90 = build(90)
    x_world = _world_axis(asm90, rail90, (1, 0, 0))
    assert x_world[2] == pytest.approx(0.0, abs=1e-9)
    assert abs(x_world[1]) == pytest.approx(1.0, abs=1e-9)


def test_mt_end_a_and_end_b_both_work():
    leg = Beam(45, 45, 700)
    rail = Beam(45, 45, 300)
    j = Joinery()
    j.mortise_and_tenon(rail.end("a"), leg.face("px").at(650, from_="a"))
    assembly = j.build(ground=leg)
    # The rail's end_a is at the leg; the beam extends outward along +X.
    rail_far_end = _world_point(assembly, rail, [0, 0, 300])
    assert rail_far_end[0] > 100


# --------------------------------------------------------------------------- #
# The mitered frame: four corners, closed.
# --------------------------------------------------------------------------- #


def test_miter_frame_closes():
    beams = [
        Beam(60, 20, 400, color="#c9a36a"),
        Beam(60, 20, 300, color="#8a6a45"),
        Beam(60, 20, 400, color="#d2b48c"),
        Beam(60, 20, 300, color="#a97c50"),
    ]
    ops_before = [len(beam.operations) for beam in beams]
    j = Joinery()
    for i in range(4):
        j.miter(
            beams[i].end("b").inside("ny"),
            beams[(i + 1) % 4].end("a").inside("ny"),
        )
    assembly = j.build(ground=beams[0])
    assert len(assembly.components) == 4
    assert len(assembly.joints) == 3  # fourth corner closes the loop

    axes = [_world_axis(assembly, beam) for beam in beams]
    for i in range(4):
        assert abs(np.dot(axes[i], axes[(i + 1) % 4])) == pytest.approx(0.0, abs=1e-9)

    # Every corner cut: one wedge per beam end -> 2 extra ops per beam.
    for beam, before in zip(beams, ops_before):
        assert len(beam.operations) == before + 2


def test_miter_frame_wrong_length_raises():
    beams = [Beam(60, 20, 400), Beam(60, 20, 300), Beam(60, 20, 400), Beam(60, 20, 320)]
    j = Joinery()
    for i in range(4):
        j.miter(
            beams[i].end("b").inside("ny"),
            beams[(i + 1) % 4].end("a").inside("ny"),
        )
    with pytest.raises(ClosureError):
        j.build(ground=beams[0])
