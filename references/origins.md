# Design Origins and Architectural Foundations

Agent Swarm emerged from practical lessons learned while operating complex, autonomous multi-agent pipelines on demanding engineering and research problems.

## The Problem with Flat Multi-Agent Systems

Early multi-agent designs often default to flat topologies—either a shared group chat where all agents see every message, or an ad-hoc peer-to-peer network. In practice, these topologies suffer from well-documented failure modes:

1. **Context Window Pollution**: Sharing entire conversation histories across all agents burns tokens exponentially and dilutes critical task instructions with irrelevant chit-chat.
2. **Circular Validation and Sycophancy**: Without independent validation lanes, agents frequently praise and rubber-stamp each other's flawed outputs, mistaking conversational agreement for verified correctness.
3. **Diffusion of Responsibility**: When everyone is responsible for everything, no single agent owns task completion, leading to dropped dependencies and duplicated labor.
4. **Unconstrained Scope Creep**: Agents left to negotiate their own boundaries frequently attempt tasks outside their capabilities, edit shared files concurrently, or diverge into unhelpful tangents.
5. **Lack of Human Governance**: Systems either require exhausting manual micromanagement of every sub-step or run completely unmonitored until budgets are exhausted or breaking errors occur.

## The Organizational Solution

Agent Swarm addresses these failure modes by adapting battle-tested organizational design principles to autonomous agent systems:

- **Strict Hierarchical Accountability**: The user acts as the executive owner. A Chief Director translates high-level user goals into departmental objectives. Managers own work queues and task decomposition. Workers execute strictly bounded artifact contracts.
- **Independent Validation Lanes**: Quality control is never left to the producer. Dedicated validation roles independently verify outputs against observable criteria before management accepts work.
- **Capability-Based Role Matching**: Agents are assigned to roles based on verifiable tool permissions and model capabilities, eliminating mismatched assignments.
- **Bounded Task Contracts**: Every assignment defines an explicit objective, read-only inputs, owned output paths, reserved budget, and stop conditions.
- **Evidence-Backed 360° Governance**: Supervisory, peer, and upward reviews evaluate agents over multiple cycles. Performance scores directly inform structured promotions, coaching, and demotions.
- **Human Executive Sovereignty**: Reorganizations, promotions, and scope expansions require user approval via cryptographic proposal digests. The system recommends; the human decides.

## Core Architectural Invariants

Regardless of domain, Agent Swarm enforces five system invariants:

1. **Deterministic Offline Toolchain**: Core org planning, validation, diagram compilation, and review calculations operate purely in standard Python with zero external API dependencies.
2. **Immutable Snapshots vs. Mutable State**: Active specifications (`org.json`) remain strictly separated from compiled point-in-time snapshots (`snapshot/`).
3. **Atomic State Transactions**: Specifications are updated under POSIX file locks using temporary staging and atomic replacements, preventing race conditions and corrupted states.
4. **Cryptographic State Integrity**: Dual SHA-256 fingerprints bind task contracts to operating rosters and verify that user-approved change proposals have not drifted.
5. **Zero Phantom Permissions**: Role titles or org-chart edges never grant external permissions or filesystem access. Permissions remain host-enforced allowlists.
