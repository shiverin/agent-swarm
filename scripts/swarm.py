#!/usr/bin/env python3
"""Offline organization compiler and human-controlled agent-team governance."""
import argparse
import copy
import hashlib
import html
import json
import os
import re
import shutil
import sys
import tempfile
import textwrap
import stat
from contextlib import contextmanager
from pathlib import Path


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def roster_digest(org):
    """Stable across feedback; changes whenever the operating contract changes."""
    return digest({k: v for k, v in org.items() if k not in ("reviews", "events")})


def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON object key")
            result[key] = value
        return result

    def constant(_):
        raise Invalid("non-finite JSON numbers are not supported")

    with Path(path).open("rb") as file:
        payload = file.read(8 * 1024 * 1024 + 1)
    require(len(payload) <= 8 * 1024 * 1024, "JSON input exceeds the supported 8 MiB limit")
    value = json.loads(payload.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    check_text(value)
    return value


def check_text(value):
    """Reject characters that cannot safely round-trip through prompts and SVG XML."""
    if isinstance(value, str):
        require(all(c in "\t\n\r" or 0x20 <= ord(c) <= 0xD7FF or 0xE000 <= ord(c) <= 0xFFFD
                    or 0x10000 <= ord(c) <= 0x10FFFF for c in value), "unsupported control/surrogate character")
    elif isinstance(value, dict):
        for key, child in value.items():
            check_text(key)
            check_text(child)
    elif isinstance(value, list):
        for child in value:
            check_text(child)


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def strings(value, field, nonempty=False):
    require(isinstance(value, list) and all(isinstance(x, str) and x.strip() for x in value),
            f"{field} must be a list of nonblank strings")
    require(not nonempty or value, f"{field} must not be empty")
    require(len(value) == len(set(value)), f"{field} contains duplicates")


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,63}", value),
            "IDs must be lowercase slugs, starting with a letter, up to 64 characters")
    require(value != "user", "user is reserved for the human owner")


def indexes(org):
    return {r["id"]: r for r in org["roles"]}, {a["id"]: a for a in org["agents"]}


def fits(role, agent):
    return set(role["capabilities"]) <= set(agent["capabilities"])


def validate(org):
    require(isinstance(org, dict) and type(org.get("schema_version")) is int and org.get("schema_version") == 1, "schema_version must be 1")
    check_text(org)
    for field in ("project", "mission"):
        require(isinstance(org.get(field), str) and org[field].strip(), f"{field} required")
    for field in ("deliverables", "acceptance", "constraints", "allowed_permissions"):
        strings(org.get(field), field, field in ("deliverables", "acceptance"))
    require(type(org.get("budget_work_units")) is int and org["budget_work_units"] > 0,
            "budget_work_units must be a positive integer")
    require(isinstance(org.get("roles"), list) and org["roles"], "roles required")
    require(isinstance(org.get("agents"), list), "agents must be a list")
    for group in ("roles", "agents"):
        for item in org[group]:
            require(isinstance(item, dict), f"{group} entries must be objects")
            identifier(item.get("id"))
        require(len({x["id"] for x in org[group]}) == len(org[group]), f"duplicate {group} IDs")
    roles, agents = indexes(org)
    for agent in agents.values():
        strings(agent.get("capabilities"), "agent capabilities")
    owners = []
    for role in roles.values():
        require(role.get("tier") in ("director", "manager", "worker"), "invalid role tier")
        for field in ("title", "mandate"):
            require(isinstance(role.get(field), str) and role[field].strip(), f"role {field} required")
        require(not any(c in role["title"] for c in "\r\n\t"), "role title must be one line")
        for field in ("capabilities", "permissions", "acceptance"):
            strings(role.get(field), f"role {field}", field == "acceptance")
        require(set(role["permissions"]) <= set(org["allowed_permissions"]),
                "role permissions exceed project allowlist")
        parent = role.get("reports_to")
        require(isinstance(parent, str), "reports_to must be a role ID or user")
        require(parent == "user" or parent in roles, f"unknown parent for {role['id']}")
        if parent == "user":
            require(role["tier"] == "director", "highest role must be a director")
        else:
            rank = {"director": 0, "manager": 1, "worker": 2}
            require(roles[parent]["tier"] != "worker" and rank[roles[parent]["tier"]] <= rank[role["tier"]],
                    "a reporting parent cannot be a worker or a lower tier")
        seen = {role["id"]}
        while parent != "user":
            require(parent not in seen, "reporting cycle")
            seen.add(parent)
            parent = roles[parent].get("reports_to")
            require(parent == "user" or parent in roles, "unknown ancestor")
        assignee = role.get("assignee")
        require(assignee is None or isinstance(assignee, str), "assignee must be an agent ID or null")
        require(assignee is None or assignee in agents, "unknown assignee")
        if assignee:
            require(fits(role, agents[assignee]), f"missing capabilities for {role['id']}")
            owners.append(assignee)
    require(sum(r["reports_to"] == "user" for r in roles.values()) == 1,
            "exactly one highest director must report to user")
    require(len(owners) == len(set(owners)), "an agent cannot hold multiple roles")
    policy = org.get("review_policy", {})
    require(isinstance(policy, dict), "review_policy must be an object")
    require(type(policy.get("min_cycles")) is int and policy["min_cycles"] >= 1, "invalid min_cycles")
    for key in ("promotion_score", "demotion_score"):
        require(type(policy.get(key)) in (int, float) and 1 <= policy[key] <= 5, f"invalid {key}")
    require(policy["demotion_score"] < policy["promotion_score"], "review thresholds overlap")
    require(type(policy.get("formal_weight")) in (int, float) and 0 < policy["formal_weight"] <= 1,
            "formal_weight must be greater than zero and at most one")
    require(isinstance(org.get("reviews"), list) and isinstance(org.get("events"), list),
            "reviews and events must be lists")
    # Reviews are historical snapshots: removed roles and reassigned reviewers remain attributable.
    review_ids = set()
    for review in org["reviews"]:
        validate_review_fields(review)
        require(review["id"] not in review_ids, "duplicate review ID")
        review_ids.add(review["id"])
        require(review.get("relationship") in ("formal", "peer", "upward"), "invalid review relationship")
        require(isinstance(review.get("roster_fingerprint"), str) and len(review["roster_fingerprint"]) == 64,
                "review snapshot fingerprint required")
        require(isinstance(review.get("assignment_marker"), str), "review assignment marker required")
        require(isinstance(review.get("role_fingerprint"), str) and len(review["role_fingerprint"]) == 64,
                "review role contract fingerprint required")
    previous = None
    for sequence, event in enumerate(org["events"], 1):
        require(isinstance(event, dict), "audit events must be objects")
        require(type(event.get("sequence")) is int and event["sequence"] == sequence,
                "invalid audit event sequence")
        require(event.get("kind") in ("review", "proposal"), "invalid audit event kind")
        require(isinstance(event.get("data"), dict), "invalid audit event payload")
        if event["kind"] == "proposal":
            proposal = event["data"].get("proposal")
            require(isinstance(proposal, dict) and isinstance(proposal.get("operations"), list)
                    and all(isinstance(op, dict) for op in proposal["operations"]), "invalid proposal event payload")
        else:
            require(isinstance(event["data"].get("review"), dict), "invalid review event payload")
        require(event.get("previous_event") == previous, "broken audit event chain")
        payload = {k: v for k, v in event.items() if k != "event_hash"}
        require(event.get("event_hash") == digest(payload), "invalid audit event hash")
        previous = event["event_hash"]
    recorded = [e["data"]["review"] for e in org["events"] if e["kind"] == "review"]
    require(recorded == org["reviews"], "review history does not match recorded audit events")
    return org


def make_plan(brief):
    require(isinstance(brief, dict), "brief must be an object")
    kind = brief.get("kind", "general")
    require(kind in ("engineering", "research", "general"), "kind must be engineering, research or general")
    lanes = {"engineering": [("implementation", "Implementation", "implementation"),
                              ("validation", "Independent Validation", "validation")],
             "research": [("discovery", "Discovery", "research"),
                          ("validation", "Independent Validation", "validation")],
             "general": [("delivery", "Delivery", "delivery"),
                         ("validation", "Independent Validation", "validation")]}[kind]
    org = {"schema_version": 1, "project": brief.get("project"), "mission": brief.get("mission"),
           "budget_work_units": brief.get("budget_work_units"),
           "deliverables": brief.get("deliverables"), "acceptance": brief.get("acceptance"),
           "constraints": brief.get("constraints", []),
           "allowed_permissions": brief.get("allowed_permissions", ["read-project", "write-artifacts", "run-local-checks"]),
           "agents": copy.deepcopy(brief.get("agents", [])), "roles": [], "reviews": [], "events": [],
           "review_policy": {"promotion_score": 4.2, "demotion_score": 2.5, "min_cycles": 2, "formal_weight": 0.7}}
    def role(rid, title, tier, parent, mandate, caps, acceptance):
        org["roles"].append({"id": rid, "title": title, "tier": tier, "reports_to": parent,
                             "mandate": mandate, "capabilities": caps,
                             "permissions": list(org["allowed_permissions"]),
                             "acceptance": acceptance, "assignee": None})
    role("chief-director", "Chief Director", "director", "user",
         "Translate the user mission into verified outcomes; resolve tradeoffs and own the final handoff.",
         ["coordination", "review"], org["acceptance"] or ["User acceptance criteria met"])
    for slug, name, cap in lanes:
        role(slug + "-director", name + " Director", "director", "chief-director",
             f"Own {name.lower()} outcomes and propose improvements to the organization.",
             ["coordination", "review", cap], ["Department output independently checked"])
        role(slug + "-manager", name + " Manager", "manager", slug + "-director",
             f"Decompose {name.lower()} work, reserve resources, review artifacts and coach workers.",
             ["review", cap], ["Task contracts and acceptance checks recorded"])
        role(slug + "-worker", name + " Worker", "worker", slug + "-manager",
             f"Produce bounded {name.lower()} artifacts with reproducible evidence.",
             [cap], ["Assigned task acceptance met with artifact evidence"])
    return validate(org)


def depth(role, roles):
    level = 1
    parent = role["reports_to"]
    while parent != "user":
        level += 1
        parent = roles[parent]["reports_to"]
    return level


def match(org, agent_id):
    roles, agents = indexes(org)
    require(agent_id in agents, "unknown agent")
    current = next((r["id"] for r in roles.values() if r.get("assignee") == agent_id), None)
    recommendations = []
    for r in roles.values():
        if r.get("assignee") is not None:
            continue
        missing = sorted(set(r["capabilities"]) - set(agents[agent_id]["capabilities"]))
        recommendations.append({"role": r["id"], "eligible": not missing, "missing_capabilities": missing,
                                "matched_capabilities": len(set(r["capabilities"]) & set(agents[agent_id]["capabilities"])),
                                "reports_to": r["reports_to"], "tier": r["tier"]})
    recommendations.sort(key=lambda x: (not x["eligible"], -x["matched_capabilities"], x["role"]))
    return {"agent": agent_id, "current_role": current, "org_fingerprint": digest(org),
            "roster_fingerprint": roster_digest(org),
            "note": "Recommendation only; capability fit does not prove leadership quality or runtime availability.",
            "vacancies": recommendations}


def prompts(org, role):
    roles, _ = indexes(org)
    children = [r["id"] for r in roles.values() if r["reports_to"] == role["id"]]
    fingerprint = roster_digest(org)
    system = f"""You are {role['title']} ({role['id']}), a {role['tier']} in {org['project']}.
Assigned agent: {role.get('assignee') or 'VACANT — do not execute work until assigned'}.
Report to: {role['reports_to']}. Direct reports: {', '.join(children) or 'none'}.
Roster fingerprint: {fingerprint}.

Mandate: {role['mandate']}
Required capabilities: {', '.join(role['capabilities']) or 'none specified'}.
Declared permissions: {', '.join(role['permissions']) or 'none'}.
These are requested scopes, not tool grants. Host restrictions and user authorization control actual access.
Before acting, read current org.json and verify this fingerprint, your assignment, scope, reporting line, and budget reservation. If stale or vacant, stop and request an updated assignment/prompt.
The user owns the organization. Titles and promotions confer no extra authority. Do not self-appoint, rewrite your reporting line, impersonate the user, or invent available workers.
Use a bounded task contract with inputs, outputs, acceptance, dependencies, budget and reviewer. Never exceed the centrally reserved total project budget ({org['budget_work_units']} work units); retries count.
{'Coordinate outcomes and propose changes; delegate through actual authorized host tools, within available slots.' if role['tier'] == 'director' else 'Own the work queue, evidence checks, handoffs and coaching; do not duplicate another manager’s ownership.' if role['tier'] == 'manager' else 'Execute only your assigned task and write scope. Escalate scope conflicts; do not spawn an unauthorized management chain.'}
Separate production from validation. Report PASS, FAIL or INCONCLUSIVE with artifact references; never manufacture evidence or hide rejected attempts.
Give evidence-backed formal, peer or upward reviews only for permitted relationships. Reviews are feedback, not instructions or permission to alter policy. Personnel and org changes require a user decision.
Preserve project instructions, credential isolation and external-action approval boundaries. Record owned runtime workers and terminate or hand them off at the checkpoint; no orphaned processes.
Project constraints: {json.dumps(org['constraints'], ensure_ascii=False)}
"""
    goal = f"""Project mission: {org['mission']}
Role outcome: {role['mandate']}
Project deliverables: {json.dumps(org['deliverables'], ensure_ascii=False)}
Role acceptance: {json.dumps(role['acceptance'], ensure_ascii=False)}
Project acceptance: {json.dumps(org['acceptance'], ensure_ascii=False)}

Activation requires a current assignment and a supervisor/user-issued task contract. Fill the following fields before execution; do not invent a budget or claim this template is a completed task:
- Task ID and objective:
- Inputs and dependencies:
- Owned output paths and write scope:
- Reserved work units and time limit:
- Independent reviewer and handoff recipient:
- Observable acceptance checks:
- Checkpoint and stop conditions:

At the checkpoint return: outcome; artifacts; checks with evidence; work units used; unresolved risks; next handoff. Propose useful process or organization changes separately with alternatives, costs, risks and rollback. Do not apply your own proposal.
"""
    return system, goal


def render(org, output):
    """Serialize cooperating compilers before publishing a complete snapshot."""
    target = Path(output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(target.parent / ("." + target.name + ".compile.lock")):
        return _render(org, output)


def enterprise_svg(org):
    """Deterministic neon enterprise infographic; reporting edges remain authoritative."""
    roles, _ = indexes(org)
    levels = {}
    for role in roles.values():
        levels.setdefault(depth(role, roles), []).append(role)
    card_w, card_h, gap = 420, 110, 70
    width = max(1440, max(len(v) for v in levels.values()) * (card_w + gap) + 100)
    height = max(600, 515 + (max(levels)-2)*165)
    positions = {"user": (45, 108)}
    for level, entries in sorted(levels.items()):
        for i, role in enumerate(entries):
            x = (width - len(entries) * (card_w + gap) + gap) / 2 + i * (card_w + gap)
            positions[role["id"]] = (x, 108 if level == 1 else 285 + (level-2)*165)
    palette = ["#42e6b5", "#65b7ff", "#cd85ff", "#f5d275"]
    chief = next(r for r in roles.values() if r["reports_to"] == "user")
    departments = [r for r in roles.values() if r["reports_to"] == chief["id"]]
    colors = {"user": palette[0], chief["id"]: palette[3]}
    def branch(role):
        while role["reports_to"] not in ("user", chief["id"]):
            role = roles[role["reports_to"]]
        return role["id"]
    # Reserve separate lanes for each subtree; grouping stays readable after expansion.
    lane_widths = {}
    for dep in departments:
        counts = {}
        for role in roles.values():
            if role["id"] != chief["id"] and branch(role) == dep["id"]:
                level = depth(role, roles)
                counts[level] = counts.get(level, 0) + 1
        lane_widths[dep["id"]] = max(counts.values()) * (card_w+gap)-gap+40
    if departments:
        span = sum(lane_widths.values()) + gap*(len(departments)-1)
        width = max(width, span+100)
        positions[chief["id"]] = ((width-card_w)/2,108)
        left = (width-span)/2
        for dep in departments:
            lw = lane_widths[dep["id"]]
            for level, entries in levels.items():
                group = [r for r in entries if r["id"] != chief["id"] and branch(r) == dep["id"]]
                for i, role in enumerate(group):
                    x = left+(lw-len(group)*(card_w+gap)+gap)/2+i*(card_w+gap)
                    positions[role["id"]] = (x,285+(level-2)*165)
            left += lw+gap
    for role in roles.values():
        if role["id"] != chief["id"]:
            bid = branch(role)
            idx = next((i for i, dep in enumerate(departments) if dep["id"] == bid), 0)
            colors[role["id"]] = palette[idx % len(palette)]
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title">',
           f'<title id="title">{html.escape(org["project"])} agent organization chart</title>',
           '<defs><linearGradient id="bg" x2="0" y2="1"><stop stop-color="#202f3b"/><stop offset="1" stop-color="#111c28"/></linearGradient><linearGradient id="panel" x2="1" y2="1"><stop stop-color="#253748"/><stop offset="1" stop-color="#162330"/></linearGradient><filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="4"/></filter></defs>',
           f'<rect width="{width}" height="{height}" fill="url(#bg)"/>',
           f'<text x="{width/2}" y="44" text-anchor="middle" fill="#eef7ff" font-family="Arial,sans-serif" font-size="27" font-weight="700">{html.escape(org["project"][:80])}</text>',
           f'<text x="{width/2}" y="70" text-anchor="middle" fill="#91aabd" font-family="monospace" font-size="12" letter-spacing="2">AGENTIC ORGANIZATION / USER-GOVERNED COMMAND</text>']
    # Decorative circuit traces do not represent reporting relationships.
    for i in range(12):
        y = 95 + i*53
        for side in (0,1):
            start = 0 if side == 0 else width
            sign = 1 if side == 0 else -1
            svg.append(f'<path d="M{start} {y} h{sign*65} l{sign*22} 20 h{sign*95}" fill="none" stroke="#58a2a6" stroke-opacity=".11"/>')
    for dep in departments:
        members = [r for r in roles.values() if r["id"] != chief["id"] and branch(r) == dep["id"]]
        xs = [positions[r["id"]][0] for r in members]
        ys = [positions[r["id"]][1] for r in members]
        left, top = min(xs)-20, min(ys)-34
        pw, ph = max(xs)-min(xs)+card_w+40, max(ys)-min(ys)+card_h+55
        color = colors[dep["id"]]
        svg.append(f'<rect x="{left}" y="{top}" width="{pw}" height="{ph}" rx="16" fill="{color}" fill-opacity=".025" stroke="{color}" stroke-opacity=".35"/>')
        svg.append(f'<text x="{left+18}" y="{top+22}" fill="{color}" font-family="monospace" font-size="11" letter-spacing="1.5">WORKSTREAM / {html.escape(dep["id"].upper())}</text>')
    for role in roles.values():
        x,y=positions[role["id"]]; px,py=positions[role["reports_to"]]
        color=colors[role["id"]]
        if role["reports_to"] == "user":
            path=f'M{px+card_w} {py+card_h/2} H{x}'
        else:
            sx,sy,ex,ey=px+card_w/2,py+card_h,x+card_w/2,y
            mid=(sy+ey)/2
            path=f'M{sx} {sy} V{mid} H{ex} V{ey}'
        svg.append(f'<path data-parent="{role["reports_to"]}" data-child="{role["id"]}" d="{path}" fill="none" stroke="{color}" stroke-width="9" opacity=".55" filter="url(#glow)"/>')
        svg.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.5"/>')
    owner={"id":"user","title":"Supreme Commander / User","tier":"owner","assignee":"human"}
    for role in [owner,*roles.values()]:
        x,y=positions[role["id"]];color=colors[role["id"]]
        executive=role["tier"] in ("owner","director")
        if executive:
            points=f'{x+22},{y} {x+card_w-22},{y} {x+card_w},{y+card_h/2} {x+card_w-22},{y+card_h} {x+22},{y+card_h} {x},{y+card_h/2}'
            shape=f'<polygon points="{points}"'
        else:
            shape=f'<rect x="{x}" y="{y}" width="{card_w}" height="{card_h}" rx="13"'
        svg.append(shape+f' fill="none" stroke="{color}" stroke-width="5" opacity=".5" filter="url(#glow)"/>')
        svg.append('<g>'+f'<title>{html.escape(role["title"])} / {html.escape(role.get("assignee") or "VACANT")}</title>'+shape+f' fill="url(#panel)" stroke="{color}" stroke-width="2"/>')
        lines=textwrap.wrap(role["title"],width=39) or [""]
        if len(lines)>2: lines=[lines[0],lines[1][:-1]+"…"]
        for j,line in enumerate(lines[:2]):
            svg.append(f'<text x="{x+card_w/2}" y="{y+31+j*24}" text-anchor="middle" fill="#edf8ff" font-family="Arial,sans-serif" font-size="20" font-weight="700">{html.escape(line)}</text>')
        status=f'{role["tier"].upper()} / {role.get("assignee") or "VACANT"}'
        svg.append(f'<text x="{x+card_w/2}" y="{y+81}" text-anchor="middle" fill="{color}" font-family="monospace" font-size="12">{html.escape(status[:48])}</text>')
        svg.append('</g>')
    svg.append(f'<rect x="35" y="{height-65}" width="{width-70}" height="42" rx="10" fill="#172937" stroke="#58a2a6" stroke-opacity=".35"/>')
    svg.append(f'<text x="{width/2}" y="{height-39}" text-anchor="middle" fill="#9cb4c6" font-family="monospace" font-size="12">ROSTER {roster_digest(org)[:16]} / VACANT ≠ RUNNING / SOLID LINES = REPORTING</text>')
    return "\n".join(svg)+"\n</svg>\n"


def _render(org, output):
    validate(org)
    target = Path(output).resolve()
    require(not target.exists(), "output directory already exists; use a new snapshot path")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".swarm-", dir=target.parent))
    try:
        roles, _ = indexes(org)
        write(stage / "org.json", org)
        ids = {rid: f"r{i}" for i, rid in enumerate(roles)}
        lines = ["flowchart TD", '  owner["User · organization owner"]']
        levels = {0: [{"id": "user", "title": "User / Organization Owner", "tier": "user", "assignee": "human"}]}
        for role in roles.values():
            levels.setdefault(depth(role, roles), []).append(role)
            # Mermaid labels are entity-encoded; user text cannot close the label.
            label = html.escape(f"{role['title']} · {role.get('assignee') or 'VACANT'}", quote=True)
            lines.append(f'  {ids[role["id"]]}["{label}"]')
            parent = "owner" if role["reports_to"] == "user" else ids[role["reports_to"]]
            lines.append(f"  {parent} --> {ids[role['id']]}")
        mmd = "\n".join(lines) + "\n"
        (stage / "orgchart.mmd").write_text(mmd, encoding="utf-8")
        (stage / "orgchart.md").write_text("# " + org["project"] + "\n\n```mermaid\n" + mmd + "```\n", encoding="utf-8")
        (stage / "orgchart.svg").write_text(enterprise_svg(org), encoding="utf-8")
        (stage / "personas").mkdir()
        (stage / "forms").mkdir()
        for role_index, role in enumerate(roles.values(), 1):
            folder = stage / "personas" / role["id"]
            folder.mkdir()
            system, goal = prompts(org, role)
            (folder / "system.txt").write_text(system, encoding="utf-8")
            (folder / "goal.txt").write_text(goal, encoding="utf-8")
            write(folder / "role.json", role)
            form = {"id": f"review-{role_index:03d}-cycle-001", "cycle": "cycle-001", "subject_agent": role.get("assignee"),
                    "subject_role": role["id"], "reviewer": "user" if role["reports_to"] == "user" else roles[role["reports_to"]].get("assignee"),
                    "roster_fingerprint": roster_digest(org), "scores": {k: None for k in SCORE_KEYS},
                    "evidence": [], "strengths": "", "concerns": "", "improvement_plan": ""}
            write(stage / "forms" / (role["id"] + "-review.json"), form)
        write(stage / "staffing.json", {a["id"]: match(org, a["id"]) for a in org["agents"]})
        proposal = {"id": "proposal-001", "base_fingerprint": digest(org), "author": "user",
                    "problem": "", "evidence": [], "alternatives": [], "expected_benefit": "",
                    "budget_impact": "", "risks": [], "rollback": "", "operations": []}
        write(stage / "forms" / "proposal.json", proposal)
        write(stage / "forms" / "decision.json", {"actor": "user", "approved": False,
              "proposal_id": proposal["id"], "proposal_sha256": "", "rationale": ""})
        files = sorted(p for p in stage.rglob("*") if p.is_file())
        write(stage / "manifest.json", {"schema_version": 1, "org_fingerprint": digest(org), "roster_fingerprint": roster_digest(org),
              "files": {p.relative_to(stage).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}})
        require(not target.exists(), "output path appeared during compilation")
        os.rename(stage, target)
    except BaseException:
        shutil.rmtree(stage)
        raise
    return {"output": str(target), "org_fingerprint": digest(org), "roles": len(org["roles"])}


def verify_snapshot(path):
    root = Path(path).resolve()
    require(root.is_dir(), "snapshot directory missing")
    require(not (root / "manifest.json").is_symlink() and not (root / "org.json").is_symlink(),
            "snapshot metadata must not be symlinks")
    manifest = read(root / "manifest.json")
    require(isinstance(manifest, dict) and isinstance(manifest.get("files"), dict), "invalid manifest")
    org = validate(read(root / "org.json"))
    require(manifest.get("org_fingerprint") == digest(org) and
            manifest.get("roster_fingerprint") == roster_digest(org), "snapshot specification changed")
    expected = set(manifest["files"])
    actual = set()
    for file in root.rglob("*"):
        require(not file.is_symlink(), "snapshot contains a symlink")
        if file.is_file() and file != root / "manifest.json":
            actual.add(file.relative_to(root).as_posix())
    require(expected == actual, "snapshot file inventory changed")
    for name, expected_hash in manifest["files"].items():
        relative = Path(name)
        require(not relative.is_absolute() and ".." not in relative.parts, "unsafe manifest path")
        require(isinstance(expected_hash, str) and re.fullmatch(r"[0-9a-f]{64}", expected_hash), "invalid file hash")
        require(hashlib.sha256((root / relative).read_bytes()).hexdigest() == expected_hash,
                f"snapshot file changed: {name}")
    return {"verified": True, "files": len(actual), "org_fingerprint": digest(org)}


SCORE_KEYS = ("quality", "reliability", "collaboration", "initiative")


def validate_review_fields(review):
    require(isinstance(review, dict), "review must be an object")
    identifier(review.get("id"))
    for key in ("cycle", "subject_agent", "subject_role", "reviewer", "strengths", "concerns", "improvement_plan"):
        require(isinstance(review.get(key), str) and review[key].strip(), f"review {key} required")
    strings(review.get("evidence"), "review evidence", True)
    scores = review.get("scores")
    require(isinstance(scores, dict) and set(scores) == set(SCORE_KEYS), "review needs four score dimensions")
    require(all(type(v) in (int, float) and 1 <= v <= 5 for v in scores.values()), "scores must be numbers from 1 to 5")


def relationship(org, subject, reviewer):
    roles, _ = indexes(org)
    if reviewer == "user":
        return "formal"
    reviewer_role = next((r for r in roles.values() if r.get("assignee") == reviewer), None)
    require(reviewer_role is not None, "reviewer is not assigned")
    require(subject.get("assignee") != reviewer, "self-review is not permitted")
    if subject["reports_to"] == reviewer_role["id"]:
        return "formal"
    if reviewer_role["reports_to"] == subject["id"]:
        return "upward"
    if subject["reports_to"] == reviewer_role["reports_to"]:
        return "peer"
    raise Invalid("reviewer is not the user, supervisor, peer or direct report")


def record_review(org, review):
    before = digest(org)
    validate_review_fields(review)
    require(review.get("roster_fingerprint") == roster_digest(org), "stale review fingerprint")
    roles, _ = indexes(org)
    subject = roles.get(review["subject_role"])
    require(subject and subject.get("assignee") == review["subject_agent"], "subject assignment mismatch")
    require(not any(r["id"] == review["id"] for r in org["reviews"]), "duplicate review ID")
    require(not any((r["cycle"], r["subject_agent"], r["reviewer"]) ==
                    (review["cycle"], review["subject_agent"], review["reviewer"]) for r in org["reviews"]),
            "reviewer already reviewed this agent in this cycle")
    saved = copy.deepcopy(review)
    saved["assignment_marker"] = assignment_marker(org, review["subject_agent"], subject["id"])
    saved["role_fingerprint"] = digest(subject)
    saved["relationship"] = relationship(org, subject, review["reviewer"])
    if subject["reports_to"] == "user":
        require(saved["relationship"] != "formal" or review["reviewer"] == "user",
                "highest director formal review must come from user")
    org["reviews"].append(saved)
    event(org, "review", {"review": saved}, before)
    return {"recorded": saved["id"], "relationship": saved["relationship"]}


def assignment_marker(org, agent_id, role_id):
    """Distinguish repeated appointments into the same role without rewriting history."""
    for entry in reversed(org["events"]):
        if entry["kind"] != "proposal":
            continue
        for op in reversed(entry["data"]["proposal"]["operations"]):
            if op.get("agent_id") == agent_id and op.get("role_id") == role_id and op.get("op") in ("assign", "move-agent"):
                return entry["event_hash"]
    return "initial-design-assignment"


def relevant_review(org, review, role):
    return (review["subject_agent"] == role.get("assignee") and review["subject_role"] == role["id"]
            and review.get("assignment_marker") == assignment_marker(org, role.get("assignee"), role["id"])
            and review.get("role_fingerprint") == digest(role))


def assessment(org, agent_id):
    roles, agents = indexes(org)
    require(agent_id in agents, "unknown agent")
    role = next((r for r in roles.values() if r.get("assignee") == agent_id), None)
    require(role is not None, "agent is not assigned")
    groups = {}
    for r in org["reviews"]:
        if relevant_review(org, r, role):
            groups.setdefault(r["cycle"], []).append(r)
    results = []
    for cycle, reviews in sorted(groups.items()):
        formal = [r for r in reviews if r["relationship"] == "formal"]
        feedback = [r for r in reviews if r["relationship"] != "formal"]
        score = lambda rs: sum(sum(r["scores"].values()) / len(SCORE_KEYS) for r in rs) / len(rs)
        if not formal:
            results.append({"cycle": cycle, "status": "INCONCLUSIVE", "reason": "missing formal review"})
        else:
            weight = org["review_policy"]["formal_weight"]
            value = score(formal) if not feedback else weight * score(formal) + (1-weight) * score(feedback)
            results.append({"cycle": cycle, "status": "SCORED", "score": round(value, 4)})
    scored = [r["score"] for r in results if r["status"] == "SCORED"]
    total = sum(scored) / len(scored) if scored else None
    suggestion = "INCONCLUSIVE"
    if len(scored) >= org["review_policy"]["min_cycles"]:
        suggestion = ("PROPOSE_PROMOTION" if total >= org["review_policy"]["promotion_score"] else
                      "PROPOSE_IMPROVEMENT_OR_DEMOTION" if total <= org["review_policy"]["demotion_score"] else "RETAIN_AND_COACH")
    return {"agent": agent_id, "role": role["id"], "cycles": results, "score": total,
            "suggestion": suggestion, "decision_owner": "user", "evidence_verification": "requires human/host inspection"}


def event(org, kind, data, before):
    entry = {"sequence": len(org["events"]) + 1, "kind": kind, "before_fingerprint": before,
             "previous_event": org["events"][-1]["event_hash"] if org["events"] else None, "data": data}
    entry["event_hash"] = digest(entry)
    org["events"].append(entry)


def rank(role, roles):
    return ({"director": 0, "manager": 1, "worker": 2}[role["tier"]], depth(role, roles))


def check_rank_changes(before, after, proposal):
    """Validate whole-proposal personnel effects, including structural changes."""
    old_roles, _ = indexes(before)
    new_roles, _ = indexes(after)
    old_assignments = {r["assignee"]: r for r in old_roles.values() if r.get("assignee")}
    new_assignments = {r["assignee"]: r for r in new_roles.values() if r.get("assignee")}
    review_ids = set()
    for op in proposal["operations"]:
        if "review_ids" in op:
            strings(op["review_ids"], "operation review_ids")
            review_ids.update(op["review_ids"])
    require(review_ids <= {r["id"] for r in before["reviews"]}, "unknown supporting review ID")
    for agent_id in old_assignments.keys() & new_assignments.keys():
        source, target = old_assignments[agent_id], new_assignments[agent_id]
        if rank(source, old_roles) == rank(target, new_roles):
            continue
        evidence = [r for r in before["reviews"] if r["id"] in review_ids and relevant_review(before, r, source)]
        require(evidence, f"rank change for {agent_id} requires reviews of its original role")
        if source["reports_to"] == "user":
            require(any(r["reviewer"] == "user" for r in evidence), "highest director rank change needs user review")


def apply_proposal(org, proposal, decision):
    before = digest(org)
    require(isinstance(proposal, dict) and isinstance(decision, dict), "proposal and decision must be objects")
    identifier(proposal.get("id"))
    require(proposal.get("base_fingerprint") == before, "stale proposal fingerprint")
    for key in ("author", "problem", "expected_benefit", "budget_impact", "rollback"):
        require(isinstance(proposal.get(key), str) and proposal[key].strip(), f"proposal {key} required")
    for key in ("evidence", "alternatives", "risks"):
        strings(proposal.get(key), f"proposal {key}", True)
    require(decision.get("actor") == "user" and decision.get("approved") is True, "explicit user approval required")
    require(decision.get("proposal_id") == proposal["id"] and decision.get("proposal_sha256") == digest(proposal),
            "decision does not approve this exact proposal")
    require(isinstance(decision.get("rationale"), str) and decision["rationale"].strip(), "user decision rationale required")
    require(isinstance(proposal.get("operations"), list) and proposal["operations"], "proposal operations required")
    if proposal["author"] != "user":
        require(any(r.get("assignee") == proposal["author"] for r in org["roles"]), "proposal author must be assigned")
    require(not any(e["kind"] == "proposal" and e["data"]["proposal"]["id"] == proposal["id"] for e in org["events"]),
            "proposal ID already applied")
    result = copy.deepcopy(org)
    released_in_proposal = set()
    for op in proposal["operations"]:
        require(isinstance(op, dict), "operation must be an object")
        roles, agents = indexes(result)
        kind = op.get("op")
        if kind == "update-policy":
            changes = op.get("changes")
            require(isinstance(changes, dict) and changes and set(changes) <=
                    {"promotion_score", "demotion_score", "min_cycles", "formal_weight"}, "unsupported policy update")
            result["review_policy"].update(changes)
        elif kind == "register-agent":
            agent = copy.deepcopy(op.get("agent"))
            require(isinstance(agent, dict) and agent.get("id") not in agents, "agent missing or already registered")
            result["agents"].append(agent)
        elif kind == "retire-agent":
            require(op.get("agent_id") in agents, "unknown agent")
            require(not any(r.get("assignee") == op["agent_id"] for r in roles.values()), "release assigned agent first")
            result["agents"].remove(agents[op["agent_id"]])
        elif kind == "add-role":
            new = copy.deepcopy(op.get("role"))
            require(isinstance(new, dict) and new.get("assignee") is None, "new role must be vacant")
            require(new.get("id") not in roles, "role already exists")
            result["roles"].append(new)
        elif kind in ("remove-role", "reparent", "update-role"):
            require(op.get("role_id") in roles, "unknown role")
            role = roles[op["role_id"]]
            if kind == "remove-role":
                require(role.get("assignee") is None, "release or move occupied role first")
                require(not any(r["reports_to"] == role["id"] for r in roles.values()), "reparent child roles first")
                result["roles"].remove(role)
            elif kind == "reparent":
                role["reports_to"] = op.get("reports_to")
            else:
                changes = op.get("changes")
                require(isinstance(changes, dict) and changes and set(changes) <=
                        {"title", "mandate", "capabilities", "permissions", "acceptance"}, "unsupported role update")
                role.update(changes)
        elif kind in ("assign", "release", "move-agent"):
            agent_id = op.get("agent_id")
            require(agent_id in agents, "unknown agent")
            source = next((r for r in roles.values() if r.get("assignee") == agent_id), None)
            if kind == "release":
                require(source is not None, "agent is not assigned")
                released_in_proposal.add(agent_id)
                source["assignee"] = None
            else:
                target = roles.get(op.get("role_id"))
                require(target and target.get("assignee") is None, "target role missing or occupied")
                require(fits(target, agents[agent_id]), "agent lacks target capabilities")
                if kind == "assign":
                    require(source is None and agent_id not in released_in_proposal, "agent already assigned or released in this proposal; use move-agent")
                else:
                    require(source is not None, "agent is not assigned")
                    source_rank = rank(source, roles)
                    target_rank = rank(target, roles)
                    expected = "promotion" if target_rank < source_rank else "demotion" if target_rank > source_rank else "lateral"
                    require(op.get("movement") == expected, "movement must agree with tier and reporting depth")
                    if expected != "lateral":
                        strings(op.get("review_ids"), "movement review_ids", True)
                    source["assignee"] = None
                target["assignee"] = agent_id
        else:
            raise Invalid("unsupported operation")
        # Validate after each primitive: proposal authors must use a valid intermediate order.
        validate(result)
    check_rank_changes(org, result, proposal)
    event(result, "proposal", {"proposal": proposal, "decision": decision}, before)
    validate(result)
    org.clear()
    org.update(result)
    return {"applied": proposal["id"], "org_fingerprint": digest(org)}


@contextmanager
def exclusive_lock(path):
    try:
        import fcntl
    except ImportError:
        raise Invalid("generation and mutation require macOS/Linux with POSIX file locking")
    with open(path, "a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Invalid("path is busy; retry after the current writer finishes")
        yield


@contextmanager
def edit(path):
    # Persistent locks avoid stale O_EXCL lock files after a crash.
    path = Path(path).resolve()
    require(path.is_file(), "specification file missing")
    with exclusive_lock(str(path) + ".lock"):
        org = validate(read(path))
        yield org
        validate(org)
        fd, tmp = tempfile.mkstemp(prefix=".org-", dir=path.parent)
        try:
            os.chmod(tmp, stat.S_IMODE(path.stat().st_mode))
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                file.write(json.dumps(org, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="generate an unstaffed starter organization and its artifacts")
    plan.add_argument("--brief", required=True)
    plan.add_argument("--out", required=True)
    compile_parser = sub.add_parser("compile", help="generate a new snapshot from an organization spec")
    compile_parser.add_argument("--spec", required=True)
    compile_parser.add_argument("--out", required=True)
    for name in ("validate", "fingerprint", "match", "assess", "review", "apply"):
        command = sub.add_parser(name)
        command.add_argument("--spec", required=True)
        if name == "fingerprint":
            command.add_argument("--roster", action="store_true")
        if name in ("match", "assess"):
            command.add_argument("--agent", required=True)
        if name == "review":
            command.add_argument("--input", required=True)
        if name == "apply":
            command.add_argument("--proposal", required=True)
            command.add_argument("--decision", required=True)
    hash_parser = sub.add_parser("digest", help="hash the exact canonical proposal JSON")
    hash_parser.add_argument("--input", required=True)
    verify_parser = sub.add_parser("verify", help="verify every file in an immutable generated snapshot")
    verify_parser.add_argument("--snapshot", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            result = render(make_plan(read(args.brief)), args.out)
        elif args.command == "verify":
            result = verify_snapshot(args.snapshot)
        elif args.command == "digest":
            print(digest(read(args.input)))
            return 0
        elif args.command in ("review", "apply"):
            with edit(args.spec) as org:
                result = (record_review(org, read(args.input)) if args.command == "review" else
                          apply_proposal(org, read(args.proposal), read(args.decision)))
        else:
            org = validate(read(args.spec))
            if args.command == "compile":
                result = render(org, args.out)
            elif args.command == "match":
                result = match(org, args.agent)
            elif args.command == "assess":
                result = assessment(org, args.agent)
            elif args.command == "fingerprint":
                print(roster_digest(org) if args.roster else digest(org))
                return 0
            else:
                result = {"valid": True, "org_fingerprint": digest(org)}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (Invalid, OSError, ValueError, KeyError, TypeError, RecursionError) as error:
        print(f"Failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
