# Reviews, promotion and demotion

The user sets policy and has the final decision. The script's assessment is a recommendation. User approval of a structural proposal never authorizes external posting, submission, execution, trading, or credential access.

## Review relationships

- Highest director: formal review by `user`; direct reports can supply upward feedback.
- Other roles: formal review by the assigned immediate supervisor; peers with the same reporting parent and direct reports can supply peer/upward feedback.
- An agent cannot review itself. Workers cannot pose as the user. Reviews bind subject agent, subject role, cycle and current operating-roster fingerprint. Both subject and reviewer must be assigned at recording time.
- Each reviewer can record one review of an agent per cycle. Recorded reviews also bind the role contract and current appointment; old appointments or changed contracts do not count toward current assessments or personnel changes. Historical reviews remain attributable to the role occupied when the review was recorded. Assessments for a new role do not silently reuse old-role scores.

Review scores are 1–5: quality, reliability, collaboration, initiative. Evidence references, strengths, concerns and a concrete improvement plan are required. A score is not proof: the supervisor or user must inspect the referenced artifacts. Independent checks matter more than persuasive review prose. Never include secrets or account identifiers.

Default policy is configurable in `org.json`: promotion score ≥4.2; demotion score ≤2.5; at least two cycles containing a formal review. Formal reviews carry 70% and peer/upward feedback together 30% in a cycle; absent feedback leaves the formal review at 100%. Missing a formal review makes that cycle INCONCLUSIVE and contributes no decision score. Each cycle has equal weight. Threshold suggestions do not force a decision.

High-quality work can justify more responsibility; promotion also needs the target role's capabilities and an actual vacancy. Bad work should usually trigger specific coaching and a bounded improvement period before demotion. Inadequate context, unavailable tools, impossible budgets, or contradictory goals are organizational problems, not automatically poor performance. Reassign scope or correct the structure when appropriate.

The user may override the suggested outcome, including acting early, but a promotion/demotion proposal must reference at least one recorded review for the agent's current role contract and appointment and explain the judgment. A user review of the highest director remains mandatory before moving that director. Never fabricate another review cycle to satisfy thresholds.

## Proposal and decision

`digest` prints a SHA-256 of the canonical proposal JSON. The decision file contains `actor: "user"`, `approved: true`, `proposal_id`, exact `proposal_sha256`, and `rationale`. `apply` rejects stale base fingerprints, mismatched approvals, invalid trees, occupied targets, missing capabilities, permission expansion beyond the project allowlist, and a personnel movement with the wrong tier/reporting-depth direction.

The JSON actor field is **not authentication**. This is a local workflow and audit aid, not a security boundary: a host must ensure only the human-authorized controller can write a decision file or invoke `apply`. Likewise, claimed agent capabilities and evidence references are supplied metadata; the host must validate them. No cryptographic identity, signed human review, sandbox or runtime budget enforcement is claimed.

Every accepted decision becomes a hash-linked event inside `org.json`. Spec writes use an advisory lock and atomic replacement. Keep previous generated snapshots outside the mutable spec. Pause affected tasks before any move; transferring a title while the previous assignment is still executing is not a completed handoff.
