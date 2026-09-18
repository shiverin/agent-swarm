# Release readiness and validation

## Supported product

Agent Swarm is an offline skill package, organization compiler and local governance workflow. Readiness applies to that scope in a trusted macOS/Linux workspace. It does not establish production readiness of a financial system or an autonomous agent-execution service.

The release supports Python 3.11–3.14 without third-party runtime dependencies. CI exercises the documented matrix on Ubuntu and macOS. Local evidence below names the actual tested platform and interpreter; pending CI is not a verified result.

## Verified release checks

- 20 behavioral tests pass locally on macOS with Python 3.12.14. The full dependency-free `scripts/check_release.py` pass includes fresh generation, snapshot verification, documentation links, SVG parsing and synthetic example staffing.
- Independent audit reproduced four original defects: conflicting generated review IDs, whole-proposal personnel review bypass, invalid text producing invalid SVG, and uncaught malformed-object errors. Each defect was corrected and receives a regression check.
- Additional checks cover appointment-specific review relevance, duplicate/non-finite JSON rejection, snapshot integrity, compilation and state locks, failure before atomic replacement, wrong-direction movement, exact-hash decisions, invalid permissions, and transactional rejection.
- A fresh-directory run generates and verifies the lean and company examples without credentials, APIs, source repository state or a model account.
- Skill frontmatter/naming validation passes. Internal documentation links and CLI examples are checked during packaging.
- Generated SVG diagrams are XML-parsed and rendered for visual inspection. Mermaid sources contain the same reporting edges.
- Repository readback and distribution archive integrity are checked as the final publication steps.

For executable check evidence, run:

```bash
python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 scripts/swarm.py compile --spec assets/example-lean-org.json --out ./build/fresh-check
python3 scripts/swarm.py verify --snapshot ./build/fresh-check
```

Use a new output directory on subsequent runs. Published CI is visible in [GitHub Actions](https://github.com/shiverin/agent-swarm/actions). Its status is authoritative for that commit; the existence of a workflow file is not proof of a passing run.

## Host requirements before real agent deployment

The integrating host must verify available agents, isolate their write scopes, keep human approval files out of untrusted agent access, reserve task ownership and compute/spend budgets centrally, inspect cited evidence, arrange independent validation, and stop or transfer workers during personnel changes. System prompts express this contract; they cannot grant or enforce tools.

Without those host controls, this release remains a design/governance aid. No automated human authentication, cryptographic signatures, multi-tenant isolation, external authorization, actual budget enforcement or runtime cleanup is claimed by the script.

## State and recovery

Maintain one canonical mutable `org.json` outside historical snapshots. Cooperating writers acquire advisory locks and fail fast on conflicts. Changes are validated on a copy before atomic replacement, preserving the previous spec if validation or replacement fails. Snapshot generation stages artifacts and locks the output namespace before publication.

Locks are local coordination for cooperating processes. Non-cooperating writers, shared/network filesystems and filesystem or host failures are outside these guarantees. Hash-linked events detect ordinary consistency errors; a party with state-write access can rewrite the chain, so it is not an authenticated audit trail. Back up canonical state and snapshots and test your host's recovery procedure.

Historical reviews retain their original role and appointment. Scope changes or a new appointment make old reviews ineligible for current assessments and rank-change evidence. An organization change affecting assigned rank requires relevant reviews for each affected person, including descendants. The user decides whether that evidence supports the proposal.

## Design references

The implementation uses strict JSON hooks and finite serialization as described in [Python's JSON documentation](https://docs.python.org/3/library/json.html). Local file replacement and filesystem behavior follow [Python's OS documentation](https://docs.python.org/3/library/os.html). CI uses commit-pinned [checkout](https://github.com/actions/checkout) and [setup-python](https://github.com/actions/setup-python) with read-only repository permissions.
