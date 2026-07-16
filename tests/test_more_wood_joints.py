"""Tests for the extended wood joint taxonomy (placement + cut counts)."""

import math

import pytest

from cadbuildr.foundation import Assembly
from cadbuildr.foundation.dag_utils import show_dag
from cadbuildr.foundation.math_utils import (
    quaternion_rotate_vector,
    tf_relative_to_frame,
)

from cadbuildr.woodworking import (
    Beam,
    box_joint,
    butt_joint,
    dado_joint,
    doweled_butt,
    edge_joint,
    end_lap,
    mitered_butt,
    rabbet_joint,
    sliding_dovetail,
    through_dovetail,
    tongue_and_groove,
)


def _axis(assembly, beam):
    _, q = tf_relative_to_frame(beam.frame, assembly.frame)
    return quaternion_rotate_vector(q, [0, 0, 1])


def _pos(assembly, beam):
    t, _ = tf_relative_to_frame(beam.frame, assembly.frame)
    return t


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _board(w=100.0, t=20.0, length=300.0):
    return Beam(w, t, length)


def test_butt_joint_places_perpendicular_no_cuts():
    wall = Beam(45, 45, 600)
    rail = Beam(45, 45, 300)
    assembly = Assembly()
    assembly.add_component(wall)
    ops = (len(wall.operations), len(rail.operations))
    butt_joint(assembly, rail, wall, face="px", at=200)
    assert (len(wall.operations), len(rail.operations)) == ops  # no shaping
    assert _dot(_axis(assembly, rail), _axis(assembly, wall)) == pytest.approx(0.0, abs=1e-9)
    # The rail's end face sits ON the wall face (x = 22.5).
    t_end, _ = tf_relative_to_frame(rail.anchor("end_b").frame, assembly.frame)
    assert t_end[0] == pytest.approx(22.5)
    assert t_end[2] == pytest.approx(200.0)


def test_mitered_butt_corner():
    a = Beam(40, 40, 300)
    b = Beam(40, 40, 300)
    assembly = Assembly()
    assembly.add_component(a)
    mitered_butt(assembly, a, b)
    # One miter wedge cut on each beam.
    assert len(a.operations) == 2
    assert len(b.operations) == 2
    # Perpendicular corner.
    assert _dot(_axis(assembly, a), _axis(assembly, b)) == pytest.approx(0.0, abs=1e-9)
    # The two end-anchor centers coincide at the corner.
    ta, _ = tf_relative_to_frame(a.anchor("end_b").frame, assembly.frame)
    tb, _ = tf_relative_to_frame(b.anchor("end_b").frame, assembly.frame)
    assert ta == pytest.approx(tb, abs=1e-9)


def test_dado_houses_full_end():
    wall = Beam(45, 200, 800)   # tall wall board
    shelf = Beam(45, 200, 400)
    assembly = Assembly()
    assembly.add_component(wall)
    dado_joint(assembly, shelf, wall, face="px", at=400, depth=12.0)
    assert len(wall.operations) == 2  # body + dado slot
    assert len(shelf.operations) == 1  # untouched
    # Shelf end sits 12mm inside the wall face (face at x=22.5).
    t_end, _ = tf_relative_to_frame(shelf.anchor("end_b").frame, assembly.frame)
    assert t_end[0] == pytest.approx(22.5 - 12.0)
    assert _dot(_axis(assembly, shelf), _axis(assembly, wall)) == pytest.approx(0.0, abs=1e-9)


def test_dado_depth_validation():
    wall = Beam(45, 45, 600)
    shelf = Beam(45, 45, 300)
    assembly = Assembly()
    assembly.add_component(wall)
    with pytest.raises(ValueError, match="pierce"):
        dado_joint(assembly, shelf, wall, depth=50.0)


def test_rabbet_corner_flush():
    edge = _board(w=100, t=20, length=300)
    board = _board(w=100, t=20, length=250)
    assembly = Assembly()
    assembly.add_component(edge)
    rabbet_joint(assembly, board, edge)
    assert len(edge.operations) == 2  # body + rabbet step
    assert len(board.operations) == 1
    assert _dot(_axis(assembly, edge), _axis(assembly, board)) == pytest.approx(0.0, abs=1e-9)
    # The board rises from the step: its end face center sits at the step
    # floor (y = t/2 - recess = 0 for the default half-thickness recess),
    # inside the edge board's end region.
    t_end, _ = tf_relative_to_frame(board.anchor("end_b").frame, assembly.frame)
    assert t_end[1] == pytest.approx(0.0, abs=1e-9)
    assert 300 - 20.2 <= t_end[2] <= 300
    # Body rises from the step: the +Z axis points toward the seated end,
    # i.e. downward, so the body extends upward.
    assert _axis(assembly, board)[1] == pytest.approx(-1.0, abs=1e-9)


def test_end_lap_corner():
    a = Beam(45, 45, 400)
    b = Beam(45, 45, 400)
    assembly = Assembly()
    assembly.add_component(a)
    end_lap(assembly, a, b)
    assert len(a.operations) == 2
    assert len(b.operations) == 2
    assert _dot(_axis(assembly, a), _axis(assembly, b)) == pytest.approx(0.0, abs=1e-9)
    # Mid-planes coincide: b's axis line passes through y=0.
    assert _pos(assembly, b)[1] == pytest.approx(0.0, abs=1e-9)


def test_doweled_butt_drills_and_places_dowels():
    wall = Beam(60, 60, 600)
    rail = Beam(60, 60, 300)
    assembly = Assembly()
    assembly.add_component(wall)
    doweled_butt(assembly, rail, wall, face="px", at=300, n_dowels=2)
    # Holes drilled in both parts.
    assert len(wall.operations) == 1 + 2
    assert len(rail.operations) == 1 + 2
    # wall + rail + 2 dowels placed.
    assert len(assembly.components) == 4
    # Dowels straddle the interface plane x = 30.
    for root in assembly.components[2:]:
        t, q = root.frame.position, root.frame.quaternion
        axis = quaternion_rotate_vector(q, [0, 0, 1])
        assert abs(axis[0]) == pytest.approx(1.0, abs=1e-9)
        ends = (t[0], t[0] + axis[0] * 40.0)
        assert min(ends) < 30.0 < max(ends)


def test_edge_joint_makes_flat_panel():
    a = _board()
    b = _board()
    assembly = Assembly()
    assembly.add_component(a)
    edge_joint(assembly, a, b)
    # Parallel, coplanar, edges touching: b's center is one width over.
    assert _dot(_axis(assembly, a), _axis(assembly, b)) == pytest.approx(1.0, abs=1e-9)
    t_b = _pos(assembly, b)
    assert t_b[0] == pytest.approx(100.0)
    assert t_b[1] == pytest.approx(0.0, abs=1e-9)
    assert t_b[2] == pytest.approx(0.0, abs=1e-9)


def test_tongue_and_groove_panel():
    a = _board(w=100, t=21)
    b = _board(w=100, t=21)
    assembly = Assembly()
    assembly.add_component(a)
    tongue_and_groove(assembly, a, b, tongue=10.0, thickness=7.0)
    assert len(a.operations) == 3  # body + two shoulder strips
    assert len(b.operations) == 2  # body + groove
    # Parallel and coplanar; the panel is narrower than two loose boards by
    # the tongue engagement (tongue tip gap = fit is inside the groove).
    assert _dot(_axis(assembly, a), _axis(assembly, b)) == pytest.approx(1.0, abs=1e-9)
    t_b = _pos(assembly, b)
    assert t_b[1] == pytest.approx(0.0, abs=1e-9)
    assert t_b[0] == pytest.approx(100.0 - 10.0)


def test_sliding_dovetail_panel():
    a = _board(w=100, t=24)
    b = _board(w=100, t=24)
    assembly = Assembly()
    assembly.add_component(a)
    sliding_dovetail(assembly, a, b, tail=10.0, root=8.0)
    assert len(a.operations) == 3  # body + two flared shoulders
    assert len(b.operations) == 2  # body + dovetail groove
    assert _dot(_axis(assembly, a), _axis(assembly, b)) == pytest.approx(1.0, abs=1e-9)
    assert _pos(assembly, b)[0] == pytest.approx(100.0 - 10.0)


def test_box_joint_corner():
    a = _board(w=100, t=18, length=300)
    b = _board(w=100, t=18, length=240)
    assembly = Assembly()
    assembly.add_component(a)
    box_joint(assembly, a, b, n_segments=5)
    # 5 segments: a keeps even (3 fingers, 2 sockets), b keeps odd (2 fingers, 3 sockets).
    assert len(a.operations) == 1 + 2
    assert len(b.operations) == 1 + 3
    assert _dot(_axis(assembly, a), _axis(assembly, b)) == pytest.approx(0.0, abs=1e-9)
    # Corner interleave: b's end face is flush with a's outer face (y=-9),
    # and b's thickness region overlaps a's end region.
    t_end, _ = tf_relative_to_frame(b.anchor("end_b").frame, assembly.frame)
    assert t_end[1] == pytest.approx(-9.0)
    assert t_end[2] == pytest.approx(300.0 - 9.0)
    # End seated at the corner, body rising: axis points toward the end.
    assert _axis(assembly, b)[1] == pytest.approx(-1.0, abs=1e-9)


def test_box_joint_requires_equal_widths():
    assembly = Assembly()
    a, b = _board(w=100), _board(w=80)
    assembly.add_component(a)
    with pytest.raises(ValueError, match="equal board widths"):
        box_joint(assembly, a, b)


def test_through_dovetail_corner():
    a = _board(w=120, t=18, length=300)  # tails
    b = _board(w=120, t=18, length=240)  # pins
    assembly = Assembly()
    assembly.add_component(a)
    through_dovetail(assembly, a, b, n_tails=3)
    # Tail board: 4 sockets (2 edge + 2 inner); pin board: 3 tail sockets.
    assert len(a.operations) == 1 + 4
    assert len(b.operations) == 1 + 3
    assert _dot(_axis(assembly, a), _axis(assembly, b)) == pytest.approx(0.0, abs=1e-9)
    t_end, _ = tf_relative_to_frame(b.anchor("end_b").frame, assembly.frame)
    assert t_end[1] == pytest.approx(-9.0)


def test_all_new_joints_serialize():
    assembly = Assembly()
    wall = Beam(45, 200, 800)
    shelf = Beam(45, 200, 300)
    assembly.add_component(wall)
    dado_joint(assembly, shelf, wall, at=250)
    boards = [_board(), _board()]
    # A second, independent sub-structure in the same assembly.
    sub = Assembly()
    sub.add_component(boards[0])
    tongue_and_groove(sub, boards[0], boards[1])
    assembly.add_component(sub)

    dag = show_dag(assembly)
    assert dag["DAG"]
    root = dag["DAG"][dag["rootNodeId"]]
    assert len(root["deps"].get("joints", [])) == 1
