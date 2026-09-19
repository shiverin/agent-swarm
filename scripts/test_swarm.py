"""Offline behavioral checks: python3 -m unittest discover -s scripts -p 'test_*.py'."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
from pathlib import Path

import swarm


class SwarmTests(unittest.TestCase):
    def setUp(self):
        self.org = swarm.make_plan({
            "project": "Documentation Engine", "mission": "Ship verifiable docs and code.",
            "kind": "engineering", "budget_work_units": 20,
            "deliverables": ["Docs and code"], "acceptance": ["Reproducible checks pass"],
            "agents": [{"id": "lead", "capabilities": ["coordination", "review", "implementation", "validation"]},
                       {"id": "builder", "capabilities": ["implementation", "review"]},
                       {"id": "peer", "capabilities": ["implementation"]},
                       {"id": "checker", "capabilities": ["validation", "review"]}]})

    def proposal(self, ops, pid="change-one"):
        return {"id": pid, "base_fingerprint": swarm.digest(self.org), "author": "user",
                "problem": "A measured bottleneck", "evidence": ["local/report.json"],
                "alternatives": ["Keep the current topology"], "expected_benefit": "Reduce rework",
                "budget_impact": "Within the existing work-unit cap", "risks": ["Handoff delay"],
                "rollback": "Propose a reverse move into the retained vacant role", "operations": ops}

    def approve(self, proposal):
        return {"actor": "user", "approved": True, "proposal_id": proposal["id"],
                "proposal_sha256": swarm.digest(proposal), "rationale": "Reviewed artifacts and change scope"}

    def apply(self, ops, pid="change-one"):
        proposal = self.proposal(ops, pid)
        return swarm.apply_proposal(self.org, proposal, self.approve(proposal))

    def staff(self):
        self.apply([{"op": "assign", "agent_id": "lead", "role_id": "chief-director"},
                    {"op": "assign", "agent_id": "builder", "role_id": "implementation-worker"},
                    {"op": "assign", "agent_id": "checker", "role_id": "validation-worker"}], "staff")

    def review(self, rid, cycle, reviewer="user", agent="builder", role="implementation-worker", score=5):
        return {"id": rid, "cycle": cycle, "subject_agent": agent, "subject_role": role,
                "reviewer": reviewer, "roster_fingerprint": swarm.roster_digest(self.org),
                "scores": {k: score for k in swarm.SCORE_KEYS}, "evidence": ["local/artifact.md"],
                "strengths": "Reproducible deliverable", "concerns": "No material concern",
                "improvement_plan": "Reduce handoff cost in the next cycle"}

    def test_generate_complete_snapshot_and_reject_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "snapshot"
            swarm.render(self.org, out)
            ET.parse(out / "orgchart.svg")
            manifest = swarm.read(out / "manifest.json")
            self.assertEqual(manifest["org_fingerprint"], swarm.digest(self.org))
            self.assertTrue(swarm.verify_snapshot(out)["verified"])
            for rel, expected in manifest["files"].items():
                self.assertEqual(swarm.hashlib.sha256((out / rel).read_bytes()).hexdigest(), expected)
            for role in self.org["roles"]:
                folder = out / "personas" / role["id"]
                self.assertTrue((folder / "system.txt").is_file())
                self.assertTrue((folder / "goal.txt").is_file())
            with self.assertRaises(swarm.Invalid):
                swarm.render(self.org, out)
            (out / "personas" / "chief-director" / "system.txt").write_text("Changed output")
            with self.assertRaises(swarm.Invalid):
                swarm.verify_snapshot(out)

    def test_generated_review_forms_record_without_id_conflicts(self):
        self.staff()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "snapshot"
            swarm.render(self.org, out)
            for rid in ("chief-director", "implementation-worker", "validation-worker"):
                form = swarm.read(out / "forms" / (rid + "-review.json"))
                form.update({"reviewer": "user", "scores": {k: 4 for k in swarm.SCORE_KEYS},
                             "evidence": ["local/verified-artifact"], "strengths": "Good result",
                             "concerns": "None", "improvement_plan": "Keep checks reproducible"})
                swarm.record_review(self.org, form)
            self.assertEqual(len(self.org["reviews"]), 3)

    def test_whole_proposal_rank_change_cannot_skip_review(self):
        self.staff()
        new = copy.deepcopy(swarm.indexes(self.org)[0]["implementation-worker"])
        new.update({"id": "alternate-worker", "assignee": None})
        before = swarm.digest(self.org)
        with self.assertRaises(swarm.Invalid):
            self.apply([{"op": "add-role", "role": new},
                        {"op": "move-agent", "agent_id": "builder", "role_id": "alternate-worker", "movement": "lateral"},
                        {"op": "reparent", "role_id": "alternate-worker", "reports_to": "chief-director"}], "rank-bypass")
        self.assertEqual(before, swarm.digest(self.org))

    def test_old_appointment_reviews_are_not_reused(self):
        self.staff()
        swarm.record_review(self.org, self.review("review-one", "one"))
        swarm.record_review(self.org, self.review("review-two", "two"))
        self.assertEqual(swarm.assessment(self.org, "builder")["suggestion"], "PROPOSE_PROMOTION")
        self.apply([{"op": "release", "agent_id": "builder"}], "release-builder")
        self.apply([{"op": "assign", "agent_id": "builder", "role_id": "implementation-worker"}], "return-builder")
        self.assertEqual(swarm.assessment(self.org, "builder")["suggestion"], "INCONCLUSIVE")
        with self.assertRaises(swarm.Invalid):
            self.apply([{"op": "move-agent", "agent_id": "builder", "role_id": "implementation-manager",
                         "movement": "promotion", "review_ids": ["review-one", "review-two"]}], "stale-tenure")

    def test_invalid_json_and_object_types_fail_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            for raw in ('{"x": 1, "x": 2}', '{"x": NaN}', '{"x":"\\u0000"}'):
                path.write_text(raw)
                result = subprocess.run([sys.executable, str(Path(swarm.__file__)), "digest", "--input", str(path)], capture_output=True)
                self.assertEqual(result.returncode, 1)
                self.assertNotIn(b"Traceback", result.stderr)
            for field, value in (("review_policy", []), ("events", ["not-an-event"])):
                invalid = copy.deepcopy(self.org)
                invalid[field] = value
                swarm.write(path, invalid)
                result = subprocess.run([sys.executable, str(Path(swarm.__file__)), "validate", "--spec", str(path)], capture_output=True)
                self.assertEqual(result.returncode, 1)
                self.assertNotIn(b"Traceback", result.stderr)

    def test_atomic_replace_failure_keeps_previous_spec(self):
        self.staff()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "org.json"
            swarm.write(path, self.org)
            before = path.read_bytes()
            with patch.object(swarm.os, "replace", side_effect=OSError("injected write failure")):
                with self.assertRaises(OSError):
                    with swarm.edit(path) as org:
                        swarm.record_review(org, self.review("fault-review", "one"))
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(tmp).glob(".org-*")), [])

    def test_compilation_lock_prevents_racing_publishers(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "snapshot"
            with swarm.exclusive_lock(Path(tmp) / ".snapshot.compile.lock"):
                with self.assertRaises(swarm.Invalid):
                    swarm.render(self.org, output)
            self.assertFalse(output.exists())

    def test_user_approved_policy_and_registry_updates(self):
        self.staff()
        self.apply([{"op": "register-agent", "agent": {"id": "new-worker", "capabilities": ["implementation"]}},
                    {"op": "update-policy", "changes": {"min_cycles": 3, "promotion_score": 4.5}}], "new-policy")
        self.assertIn("new-worker", swarm.indexes(self.org)[1])
        self.assertEqual(self.org["review_policy"]["min_cycles"], 3)
        with self.assertRaises(swarm.Invalid):
            self.apply([{"op": "retire-agent", "agent_id": "builder"}], "retire-assigned")
        before = swarm.digest(self.org)
        with self.assertRaises(swarm.Invalid):
            self.apply([{"op": "update-policy", "changes": {"demotion_score": 5}}], "bad-policy")
        self.assertEqual(before, swarm.digest(self.org))
        self.apply([{"op": "retire-agent", "agent_id": "new-worker"}], "retire-vacant")
        self.assertNotIn("new-worker", swarm.indexes(self.org)[1])

    def test_cycles_unknown_parents_and_duplicate_ownership_rejected(self):
        bad = copy.deepcopy(self.org)
        bad["roles"][0]["reports_to"] = "implementation-director"
        with self.assertRaises(swarm.Invalid):
            swarm.validate(bad)
        bad = copy.deepcopy(self.org)
        bad["roles"][1]["reports_to"] = "missing-role"
        with self.assertRaises(swarm.Invalid):
            swarm.validate(bad)
        bad = copy.deepcopy(self.org)
        bad["roles"][0]["assignee"] = "lead"
        bad["roles"][1]["assignee"] = "lead"
        with self.assertRaises(swarm.Invalid):
            swarm.validate(bad)

    def test_matching_is_read_only_and_capability_based(self):
        before = swarm.digest(self.org)
        match = swarm.match(self.org, "builder")
        choices = {v["role"]: v for v in match["vacancies"]}
        self.assertTrue(choices["implementation-manager"]["eligible"])
        self.assertFalse(choices["validation-worker"]["eligible"])
        self.assertEqual(before, swarm.digest(self.org))

    def test_failed_multi_operation_proposal_is_transactional(self):
        before = swarm.digest(self.org)
        proposal = self.proposal([{"op": "assign", "agent_id": "builder", "role_id": "implementation-worker"},
                                  {"op": "assign", "agent_id": "builder", "role_id": "implementation-manager"}])
        with self.assertRaises(swarm.Invalid):
            swarm.apply_proposal(self.org, proposal, self.approve(proposal))
        self.assertEqual(before, swarm.digest(self.org))

    def test_approval_exact_hash_and_current_state_required(self):
        proposal = self.proposal([{"op": "assign", "agent_id": "lead", "role_id": "chief-director"}])
        decision = self.approve(proposal)
        proposal["expected_benefit"] = "Changed after approval"
        with self.assertRaises(swarm.Invalid):
            swarm.apply_proposal(self.org, proposal, decision)
        proposal = self.proposal([{"op": "assign", "agent_id": "lead", "role_id": "chief-director"}])
        self.org["mission"] += " New scope."
        with self.assertRaises(swarm.Invalid):
            swarm.apply_proposal(self.org, proposal, self.approve(proposal))

    def test_self_review_and_unrelated_review_rejected(self):
        self.staff()
        with self.assertRaises(swarm.Invalid):
            swarm.record_review(self.org, self.review("self-review", "one", "builder"))
        with self.assertRaises(swarm.Invalid):
            swarm.record_review(self.org, self.review("unrelated-review", "one", "checker"))

    def test_multiple_review_forms_share_stable_roster(self):
        self.staff()
        first = self.review("review-one", "one")
        second = self.review("review-two", "two")
        old_roster = swarm.roster_digest(self.org)
        old_state = swarm.digest(self.org)
        swarm.record_review(self.org, first)
        self.assertEqual(old_roster, swarm.roster_digest(self.org))
        self.assertNotEqual(old_state, swarm.digest(self.org))
        self.assertEqual(swarm.assessment(self.org, "builder")["suggestion"], "INCONCLUSIVE")
        swarm.record_review(self.org, second)
        self.assertEqual(swarm.assessment(self.org, "builder")["suggestion"], "PROPOSE_PROMOTION")

    def test_promotion_needs_reviews_capabilities_and_correct_direction(self):
        self.staff()
        op = {"op": "move-agent", "agent_id": "builder", "role_id": "implementation-manager", "movement": "promotion", "review_ids": []}
        with self.assertRaises(swarm.Invalid):
            self.apply([op], "no-reviews")
        swarm.record_review(self.org, self.review("review-one", "one"))
        op["review_ids"] = ["review-one"]
        op["movement"] = "demotion"
        with self.assertRaises(swarm.Invalid):
            self.apply([op], "wrong-direction")
        op["movement"] = "promotion"
        self.apply([op], "promote")
        roles, _ = swarm.indexes(self.org)
        self.assertEqual(roles["implementation-manager"]["assignee"], "builder")
        self.assertIsNone(roles["implementation-worker"]["assignee"])
        self.assertEqual(swarm.assessment(self.org, "builder")["suggestion"], "INCONCLUSIVE")

    def test_feedback_weight_and_stale_roster_form(self):
        self.staff()
        swarm.record_review(self.org, self.review("builder-baseline", "baseline"))
        swarm.record_review(self.org, self.review("checker-baseline", "baseline", agent="checker", role="validation-worker"))
        self.apply([{"op": "reparent", "role_id": "implementation-worker", "reports_to": "chief-director", "review_ids": ["builder-baseline"]},
                    {"op": "reparent", "role_id": "validation-worker", "reports_to": "chief-director", "review_ids": ["checker-baseline"]}], "lean-review")
        formal = self.review("formal-one", "one", "lead", score=4)
        peer = self.review("peer-one", "one", "checker", score=2)
        swarm.record_review(self.org, formal)
        swarm.record_review(self.org, peer)
        result = swarm.assessment(self.org, "builder")
        self.assertAlmostEqual(result["score"], 3.4)
        stale = self.review("stale-one", "two")
        self.apply([{"op": "update-role", "role_id": "implementation-worker", "changes": {"mandate": "Changed scope"}}], "scope-change")
        with self.assertRaises(swarm.Invalid):
            swarm.record_review(self.org, stale)

    def test_concurrent_writer_fails_without_changing_spec(self):
        import fcntl
        self.staff()
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "org.json"
            inp = Path(tmp) / "review.json"
            swarm.write(spec, self.org)
            swarm.write(inp, self.review("locked-review", "one"))
            before = spec.read_bytes()
            with open(str(spec) + ".lock", "a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = subprocess.run([sys.executable, str(Path(swarm.__file__)), "review", "--spec", str(spec), "--input", str(inp)], capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn(b"busy", result.stderr)
            self.assertEqual(before, spec.read_bytes())

    def test_demotion_and_top_director_user_review(self):
        self.staff()
        swarm.record_review(self.org, self.review("builder-baseline", "baseline"))
        feedback = self.review("upward-one", "one", "builder", "lead", "chief-director")
        # Make builder a direct report for a valid upward review.
        self.apply([{"op": "reparent", "role_id": "implementation-worker", "reports_to": "chief-director", "review_ids": ["builder-baseline"]}], "lean")
        feedback["roster_fingerprint"] = swarm.roster_digest(self.org)
        swarm.record_review(self.org, feedback)
        op = {"op": "move-agent", "agent_id": "lead", "role_id": "implementation-director", "movement": "demotion", "review_ids": ["upward-one"]}
        with self.assertRaises(swarm.Invalid):
            self.apply([op], "feedback-only")
        formal = self.review("user-one", "one", "user", "lead", "chief-director", 2)
        swarm.record_review(self.org, formal)
        op["review_ids"].append("user-one")
        self.apply([op], "demote")
        self.assertEqual(swarm.indexes(self.org)[0]["implementation-director"]["assignee"], "lead")

    def test_permission_expansion_and_remove_occupied_parent_rejected(self):
        self.staff()
        with self.assertRaises(swarm.Invalid):
            self.apply([{"op": "update-role", "role_id": "chief-director", "changes": {"permissions": ["network-admin"]}}], "expand")
        with self.assertRaises(swarm.Invalid):
            self.apply([{"op": "remove-role", "role_id": "chief-director"}], "delete")
        with self.assertRaises(swarm.Invalid):
            self.apply([{"op": "release", "agent_id": "builder"},
                        {"op": "assign", "agent_id": "builder", "role_id": "implementation-manager"}], "bypass")

    def test_audit_tamper_and_invalid_cli_do_not_write_spec(self):
        self.staff()
        bad = copy.deepcopy(self.org)
        bad["events"][0]["data"]["decision"]["rationale"] = "Changed history"
        with self.assertRaises(swarm.Invalid):
            swarm.validate(bad)
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "org.json"
            swarm.write(spec, self.org)
            before = spec.read_bytes()
            review = self.review("invalid-review", "one", score=5)
            review["scores"]["quality"] = True
            inp = Path(tmp) / "review.json"
            swarm.write(inp, review)
            result = subprocess.run([sys.executable, str(Path(swarm.__file__)), "review", "--spec", str(spec), "--input", str(inp)], capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(before, spec.read_bytes())


if __name__ == "__main__":
    unittest.main()
