#!/usr/bin/env python3
"""Run dependency-free offline release checks from a fresh temporary workspace."""
import copy
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import swarm


def main():
    root = Path(__file__).resolve().parent.parent
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(root / "scripts"),
                    "-p", "test_*.py", "-v"], check=True)
    for doc in list(root.glob("*.md")) + list((root / "references").glob("*.md")) + list((root / "docs").glob("*.md")):
        for destination in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", doc.read_text(encoding="utf-8")):
            if "://" in destination or destination.startswith("#"):
                continue
            relative = destination.split("#", 1)[0]
            if relative:
                swarm.require((doc.parent / relative).exists(), f"broken documentation link in {doc.name}: {relative}")
    for svg in (root / "docs").glob("*.svg"):
        ET.parse(svg)
    brief = swarm.read(root / "assets" / "example-brief.json")
    with tempfile.TemporaryDirectory(prefix="agent-swarm-release-") as directory:
        tmp = Path(directory)
        for kind in ("engineering", "research", "general"):
            adapted = copy.deepcopy(brief)
            adapted["kind"] = kind
            out = tmp / kind
            swarm.render(swarm.make_plan(adapted), out)
            swarm.verify_snapshot(out)
            ET.parse(out / "orgchart.svg")
        org = swarm.validate(swarm.read(root / "assets" / "example-lean-org.json"))
        proposal = swarm.read(root / "assets" / "example-staffing-proposal.json")
        decision = swarm.read(root / "assets" / "example-staffing-decision.json")
        swarm.require(decision.get("approved") is False, "example must not grant human approval")
        # Only this isolated test supplies a synthetic decision; it is never operational approval.
        decision.update({"approved": True, "rationale": "Synthetic offline release test; no real workers or human decision"})
        swarm.apply_proposal(org, proposal, decision)
        swarm.render(org, tmp / "staffed")
        swarm.verify_snapshot(tmp / "staffed")
    print("Release checks passed: behavioral tests, documentation links, diagrams, fresh designs, and synthetic staffing.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (swarm.Invalid, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Failed: {error}", file=sys.stderr)
        sys.exit(1)
