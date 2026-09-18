# Organization design and operating flow

## Project brief to organization

Start with outputs and dependencies, not impressive titles. Identify separable workstreams, scarce expertise, shared write surfaces, independent validation needs, budget and available runtime slots. Every role needs a mandate, measurable outcome, owner, capabilities, permissions, acceptance criteria, and one reporting parent.

Default: **User → highest director → department directors → managers → workers**. The user is the owner, not an agent role. Small teams can use User → director → workers. Large, genuinely separable projects can use departments; avoid managers with nothing to manage. Keep cross-team collaboration as handoffs, not a second reporting parent.

Choose among:

| Topology | Suitable work | Main cost | Mutation trigger |
| --- | --- | --- | --- |
| Lean hierarchy | One deliverable, few available agents | Limited specialization | Repeated specialist bottleneck |
| Functional departments | Distinct research, implementation, validation streams | More handoffs | A queue repeatedly exceeds its budget |
| Product pods | Several independent features or products | Duplicated expertise | Pod work becomes tightly coupled |
| Temporary task force | Short cross-domain incident or experiment | Context-switching | Mission closes; retire the group |
| Hub with independent validation | Shared data/tool bottleneck, consequential results | Central queue pressure | Measured evidence supports another isolated lane |

The deterministic planner provides engineering, research, and general starting roles. Department names are defaults. The agent should invent project-specific alternatives, compare at least the minimal adequate design against a larger design, and justify the coordination cost. No external AI key is needed to generate artifacts.

## Pipeline and acceptance

Brief → propose structure → user selects structure → register agents → capability match → user approves staffing → generate chart and prompts → bounded task dispatch → artifact verification → reviews → user decision → updated snapshot.

At a task handoff, use this contract:

```json
{
  "task_id": "task-001",
  "owner_role": "implementation-worker",
  "roster_fingerprint": "current manifest hash",
  "objective": "One concrete deliverable",
  "inputs": ["Read-only reference artifact"],
  "outputs": ["Owned output path"],
  "acceptance": ["Observable pass condition"],
  "dependencies": ["task-000"],
  "budget": {"work_units": 5, "timeout_minutes": 20},
  "write_scope": ["Owned output path"],
  "reviewer_role": "validation-worker",
  "stop_conditions": ["Missing evidence", "Budget exhausted", "Scope conflict"]
}
```

Use an actual shared scheduler or ledger to reserve task ownership and budget before launch. Count retries and failed experiments. A project work-unit cap is a total envelope, not a fresh budget for every worker. Reviewers should not validate artifacts they authored. Separate sessions on the same model are not proof of independence.

Directors own outcomes, tradeoffs and escalation. Managers own decomposition, dependencies, resource reservations, acceptance and coaching. Workers own scoped execution and evidence. Validation roles reproduce the relevant checks and may report failure without needing the producer's permission.

## Mutation proposals

Use the generated proposal form and these required fields: ID, base fingerprint, author, problem, evidence, alternatives, expected benefit, budget impact, risks, rollback, operations. Propose one coherent change so the user can accept it as a whole. Compare the cost of adding a role with improving instructions or reducing work in progress.

Supported primitives: add a role, remove a vacant leaf role, reparent a role, update its contract, assign an agent, release an agent, move an agent with promotion/demotion/lateral classification. Compose primitives to split a department, merge teams, introduce a validation lane, or create a temporary task force. Removing occupied roles or hiding orphaned children is rejected.

Adding a new person is not the same as adding a role: agents must exist in the agent registry. Tool permission grants are constrained by the project allowlist and require a user-approved proposal. Promotions keep the same capability checks as initial staffing. Retiring a role preserves historical reviews in the specification.

Evaluate mutations at an agreed checkpoint using observed throughput, rework, acceptance failures, cost, and blocked dependencies. Record the prior fingerprint and rollback plan. Trial the new structure for a bounded cycle; if acceptance or cost worsens, propose rollback rather than silently rewriting history.
