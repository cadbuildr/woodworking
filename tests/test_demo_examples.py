"""Every github-io demo snippet must execute and produce a non-empty DAG.

The demo page (github-io/src/examples.json) and this test share the same
manifest, so a broken snippet fails CI before it breaks the page.
"""

import json
from pathlib import Path

import pytest

import cadbuildr.foundation as foundation
import cadbuildr.foundation.dag_utils as dag_utils

MANIFEST = (
    Path(__file__).resolve().parents[1] / "github-io" / "src" / "examples.json"
)
EXAMPLES = json.loads(MANIFEST.read_text())["examples"]


@pytest.mark.parametrize("example", EXAMPLES, ids=[e["id"] for e in EXAMPLES])
def test_demo_example_builds(example, monkeypatch):
    captured = {}

    def _capture_show(obj, *args, **kwargs):
        captured["dag"] = dag_utils.show_dag(obj)

    monkeypatch.setattr(foundation, "show", _capture_show)
    monkeypatch.setattr(dag_utils, "show", _capture_show)

    exec(compile(example["python"], f"<demo:{example['id']}>", "exec"), {})

    dag = captured.get("dag")
    assert dag, f"example '{example['id']}' never called show()"
    assert dag["DAG"], f"example '{example['id']}' produced an empty DAG"
    # Joint provenance made it into the serialized assembly.
    root = dag["DAG"][dag["rootNodeId"]]
    assert "joints" in root.get("deps", {}) or "joints" in root.get("params", {})


def test_manifest_covers_every_exported_joint():
    """Each joinery one-liner exported by the package appears in the demo."""
    import cadbuildr_projects.woodworking as wood

    # Only the legacy one-liners (module .joints) are demo material; the
    # interfaces API (sites/specs/Joinery) is exercised by test_interfaces.py.
    joint_fns = [
        name
        for name in wood.__all__
        if getattr(wood, name).__module__.endswith(".joints")
    ]
    corpus = " ".join(e["python"] for e in EXAMPLES)
    missing = [name for name in joint_fns if name not in corpus]
    assert not missing, f"joints missing from the demo page: {missing}"
