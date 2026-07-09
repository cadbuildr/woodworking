"""Tests for wood joinery one-liners: placement AND geometry from one call."""

import math

import pytest

from cadbuildr.foundation import Assembly
from cadbuildr.foundation.dag_utils import show_dag
from cadbuildr.foundation.math_utils import (
    quaternion_rotate_vector,
    tf_relative_to_frame,
)

from cadbuildr_projects.woodworking import Beam, cross_lap, mortise_and_tenon


def _beam_axis(assembly, beam):
    """The beam's +Z axis expressed in assembly space."""
    _, q = tf_relative_to_frame(beam.frame, assembly.frame)
    return quaternion_rotate_vector(q, [0, 0, 1])


def test_beam_anchors():
    beam = Beam(40, 60, 500)
    assert beam.anchor("end_b").frame.position[2] == pytest.approx(500)
    assert beam.anchor("face_px").frame.position[0] == pytest.approx(20)
    assert beam.anchor("face_ny").frame.position[1] == pytest.approx(-30)
    assert beam.face_thickness("px") == pytest.approx(40)
    assert beam.face_thickness("ny") == pytest.approx(60)


def test_mortise_and_tenon_is_one_line():
    leg = Beam(45, 45, 700)
    rail = Beam(45, 45, 400)
    assembly = Assembly()
    assembly.add_component(leg)

    leg_ops = len(leg.operations)
    rail_ops = len(rail.operations)
    mortise_and_tenon(assembly, rail, leg, face="px", at=550)

    # Geometry: mortise pocket cut into the leg, 4 shoulder cuts on the rail.
    assert len(leg.operations) == leg_ops + 1
    assert len(rail.operations) == rail_ops + 4
    # Placement: both beams in the assembly, one joint.
    assert len(assembly.components) == 2
    assert len(assembly.joints) == 1


def test_mortise_and_tenon_geometry():
    leg = Beam(45, 45, 700)
    rail = Beam(45, 45, 400)
    assembly = Assembly()
    assembly.add_component(leg)
    mortise_and_tenon(assembly, rail, leg, face="px", at=550, depth=25.0)

    # Rail is perpendicular to the leg: its axis runs along the leg's +X face
    # normal (pointing away from the leg — the tenon goes IN, so the beam
    # axis at the tenon end points -X... end_b tenon means beam +Z points
    # toward the joint: axis = -face normal).
    axis = _beam_axis(assembly, rail)
    assert axis == pytest.approx([-1, 0, 0], abs=1e-9)

    # The shoulder plane seats on the leg face (x = 22.5), so the rail's far
    # end (end_a, z=0 of the rail) is at x = 22.5 + (400 - 25).
    t_end_a, _ = tf_relative_to_frame(rail.anchor("end_a").frame, assembly.frame)
    assert t_end_a[0] == pytest.approx(22.5 + 375.0)
    # And the tenon tip reaches 25 mm into the leg.
    t_end_b, _ = tf_relative_to_frame(rail.anchor("end_b").frame, assembly.frame)
    assert t_end_b[0] == pytest.approx(22.5 - 25.0)
    # Centered on the mortise position along the leg.
    assert t_end_b[2] == pytest.approx(550.0)


def test_mortise_depth_validation():
    leg = Beam(45, 45, 700)
    rail = Beam(45, 45, 400)
    assembly = Assembly()
    assembly.add_component(leg)
    with pytest.raises(ValueError, match="pierce"):
        mortise_and_tenon(assembly, rail, leg, face="px", depth=60.0)


def test_shoulder_validation():
    leg = Beam(45, 45, 700)
    rail = Beam(45, 45, 400)
    assembly = Assembly()
    assembly.add_component(leg)
    with pytest.raises(ValueError, match="Shoulder too large"):
        mortise_and_tenon(assembly, rail, leg, shoulder=30.0)


def test_cross_lap_interlocks_at_right_angle():
    a = Beam(45, 45, 600)
    b = Beam(45, 45, 600)
    assembly = Assembly()
    assembly.add_component(a)

    a_ops, b_ops = len(a.operations), len(b.operations)
    cross_lap(assembly, a, b, at_a=200, at_b=300)

    # One notch cut on each beam.
    assert len(a.operations) == a_ops + 1
    assert len(b.operations) == b_ops + 1

    # Perpendicular axes.
    axis_a = _beam_axis(assembly, a)
    axis_b = _beam_axis(assembly, b)
    dot = sum(x * y for x, y in zip(axis_a, axis_b))
    assert dot == pytest.approx(0.0, abs=1e-9)

    # Coincident mid-planes: equal-height beams sit flush (both axes at y=0).
    t_b, _ = tf_relative_to_frame(b.frame, assembly.frame)
    assert t_b[1] == pytest.approx(0.0, abs=1e-9)

    # The notch centers coincide in space: point at_a along beam a equals
    # point at_b along beam b.
    pa, _ = tf_relative_to_frame(a.frame, assembly.frame)
    cross_point_a = [pa[i] + axis_a[i] * 200 for i in range(3)]
    cross_point_b = [t_b[i] + axis_b[i] * 300 for i in range(3)]
    assert cross_point_a[0] == pytest.approx(cross_point_b[0], abs=1e-9)
    assert cross_point_a[2] == pytest.approx(cross_point_b[2], abs=1e-9)


def test_joinery_serializes():
    leg = Beam(45, 45, 700)
    rail = Beam(45, 45, 400)
    assembly = Assembly()
    assembly.add_component(leg)
    mortise_and_tenon(assembly, rail, leg, face="px", at=550)

    dag = show_dag(assembly)
    root = dag["DAG"][dag["rootNodeId"]]
    assert len(root["deps"].get("joints", [])) == 1
    # Both beams' roots carry their joinery cuts.
    comp_ids = root["deps"]["components"]
    op_counts = [len(dag["DAG"][cid]["deps"]["operations"]) for cid in comp_ids]
    assert sorted(op_counts) == [2, 5]  # leg: body+mortise, rail: body+4 shoulders
