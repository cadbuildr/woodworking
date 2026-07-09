# cadbuildr_projects.woodworking

## Summary

Wood joinery built on foundation anchors + joints, at two API levels:

- **Interfaces API** (preferred): explicit sites (`beam.end("b")`,
  `leg.face("px").at(650, from_="a")`, `.clocked(deg)`, `.inside(face)`),
  spec objects (`TenonSpec`, `FingerSpec`, `MiterSpec`), and a validating
  `Joinery` builder — site bookkeeping (a beam end hosts one interface),
  cross-interface collision detection inside shared beams, and loop closing
  (a four-corner box or mitered frame builds, and its last corner is
  geometrically verified instead of failing).
- **Legacy one-liners** (`mortise_and_tenon(assembly, rail, leg, face="px", at=280)`):
  kept for the demo gallery; they guess ends and fold directions and cannot
  express closed loops or detect colliding joints.

## Tags

cad, python, wood, joinery, joints, assembly

## Status

yellow

## Guidelines

- Be precise about the interface: joints consume explicit sites
  (`beam.end("b")`, `face.at(dist, from_=...)`) — never guess ends, datums,
  clocking, or fold directions inside a joint function.
- Separate WHERE (sites) from WHAT (spec dataclasses with documented
  defaults); an interface owns placement, cuts, and its occupancy volumes.
- Interfaces are validated as a set (`Joinery.build`): end reuse, collisions
  inside shared beams, and loop closure are errors, not silent geometry.
- Derive from the `Beam` anchors (ends and faces) instead of adding ad-hoc anchors.

## Dependencies

### Upstream

- [cadbuildr-foundation](https://pypi.org/project/cadbuildr-foundation/) (PyPI)

### Downstream

- the JOINERY demo site in [github-io/](github-io/)

## Usage

```python
from cadbuildr_projects.woodworking import Beam, FingerSpec, Joinery, TenonSpec

# A four-corner finger-jointed box — the last corner closes the loop and is
# verified geometrically (ClosureError if the board lengths don't add up).
a, c = Beam(120, 18, 300), Beam(120, 18, 300)
b, d = Beam(120, 18, 200), Beam(120, 18, 200)
j = Joinery()
spec = FingerSpec(count=6)
j.box_corner(a.end("b").inside("ny"), b.end("a").inside("ny"), spec)
j.box_corner(b.end("b").inside("ny"), c.end("a").inside("ny"), spec)
j.box_corner(c.end("b").inside("ny"), d.end("a").inside("ny"), spec)
j.box_corner(d.end("b").inside("ny"), a.end("a").inside("ny"), spec)
assembly = j.build(ground=a)  # validate -> cut -> place -> verify closure

# A table corner: two tenons in one leg. Same height would raise
# JointCollisionError (the pockets would cross inside the leg).
leg, rail_x, rail_y = Beam(45, 45, 700), Beam(45, 45, 300), Beam(45, 45, 300)
j = Joinery()
j.mortise_and_tenon(rail_x.end("b"), leg.face("px").at(650, from_="a"))
j.mortise_and_tenon(rail_y.end("b"), leg.face("py").at(610, from_="a"),
                    TenonSpec(length=30, fit=0.2))
assembly = j.build(ground=leg)
```

`mortise_and_tenon` forms the tenon (shoulder cuts), mortises the pocket into
the face, and seats the beams perpendicular. `cross_lap` interlocks two beams
with half-depth notches and coincident mid-planes.

## Implemented joints

T & corner joints: `butt_joint`, `doweled_butt` (+ `Dowel` pins),
`mitered_butt`, `mortise_and_tenon`, `dado_joint`, `rabbet_joint`,
`cross_lap`, `end_lap`, `box_joint` (fingers), `through_dovetail`
(flared tails/pins via pencil polygons).

Edge joints (full-length profiles): `edge_joint`, `tongue_and_groove`,
`sliding_dovetail`.

Planned (same `Connection` pattern): half-blind / secret dovetail, biscuit,
pocket-hole, tambour.
