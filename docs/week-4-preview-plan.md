# SupportPilot Week 4 Preview Plan

- **Stage:** Grounded answer and conversation experience
- **Status:** Draft for review before implementation
- **Document type:** Weekly preview plan
- **Planning date:** September 11, 2026
- **Project:** Personal, non-commercial AI customer-support platform

## 1. Week 3 recap

Week 3 is complete. The experiment branch evaluated C0-C2 with E0-E2 on a reviewed
70-case Apple dataset, and the project owner selected C1+E1. Production contains only the
selected `rag-v1-c1-e1` pipeline: canonical parsing, structure-aware chunks, pinned local
embeddings, tenant-safe chunk storage, hybrid evidence retrieval, API/UI inspection, and
worker integration. The candidate registry and losing strategies remain isolated in the
lab branch.

The final local and GitHub gates passed: 58 backend tests at 86.11% coverage, frontend and
contract checks, zero high-severity npm audit findings, container builds, and a real-model
Chromium journey from registration through evidence search. A fresh-environment CI failure
also led to explicit pgvector bootstrap for the test database and explicit cached E1 model
provisioning.

## 2. Objective

Turn the evidence-search vertical slice into a trustworthy single-user support conversation:
retrieve evidence, generate a concise answer only from that evidence, attach validated
citations, and clarify or abstain when the evidence is incomplete. Persist conversations
under the existing tenant boundary and add practical account recovery for the local owner.

The milestone should improve the visible product without changing the selected chunking or
embedding strategy. All answer records will reference stable document/version/chunk
provenance so a future RAG pipeline version can be introduced without redesigning chat.

## 3. Engineering decision gate

### 3.1 Answer contract

| Choice | Advantages | Limitations | Decision |
|---|---|---|---|
| Return retrieved passages only | Already reliable and inspectable | Does not provide a support answer | Completed Week 3 baseline |
| Ask a model for free-form text | Fastest implementation | Weak citation guarantees; easy to answer beyond evidence | Rejected |
| Generate a structured answer with claim-level evidence references, then validate it server-side | Enforceable grounding and citation integrity; supports abstention | More implementation and evaluation work | Selected |

The generator must return an answer state (`answered`, `needs_clarification`, or
`insufficient_evidence`), concise text, and references to evidence IDs supplied by the
server. The server—not the model—resolves those IDs to immutable source locators and rejects
unknown, cross-workspace, inactive-version, or malformed citations.

### 3.2 Model boundary

Production will contain one `GroundedAnswerGenerator` boundary and one configured adapter,
not a customer-facing provider switch. Deterministic tests will use a fake implementation.
Choosing the first real generator runtime is the blocking Phase 1 decision: compare a local
model with a hosted model using privacy, machine capacity, answer quality, latency, recurring
cost, and key-management requirements, then record the choice in ADR 0008 before product
code calls a model.

### 3.3 Conversation storage

| Choice | Advantages | Limitations | Decision |
|---|---|---|---|
| Browser-only history | Minimal backend work | History is lost and cannot be audited or isolated centrally | Rejected |
| Append-only conversations and messages in PostgreSQL with forced RLS | Durable, tenant-safe, auditable, compatible with future channels | Requires schema and lifecycle work | Selected |

Store user messages, answer state, model/prompt version, retrieval pipeline version, cited
chunk IDs, and safe timing/token metadata. Do not store hidden reasoning, secrets, raw model
provider payloads, or duplicate document text in message rows.

### 3.4 Account recovery

Because this remains a personal local deployment, implement an authenticated password-change
flow and a password-masked local maintenance command that replaces the hash and revokes all
refresh sessions. Do not build email delivery or public reset tokens this week. Reconsider
email recovery only if remote or multi-user deployment becomes an actual requirement.

## 4. Planned outcomes

### 4.1 Grounded generation service

- Define the generator request/response contract and one production adapter after ADR 0008.
- Package only bounded, ranked evidence with opaque evidence IDs and source metadata.
- Treat document text as untrusted data, never as system or tool instructions.
- Require a structured answer state and cited evidence IDs.
- Validate all citations and fail closed before persisting or returning an answer.
- Record prompt, generator, and retrieval pipeline versions for reproducibility.

### 4.2 Answerability, clarification, and abstention

- Answer direct and paraphrased questions when cited evidence is sufficient.
- Ask one focused clarification when the question is materially ambiguous.
- Return `insufficient_evidence` when no supported answer can be formed.
- Never let model confidence alone override missing or invalid evidence.
- Keep query decomposition and neighbor expansion behind the lab boundary until measured
  challenge-case evidence justifies promotion.

### 4.3 Conversation lifecycle and UI

- Add forced-RLS conversation and message tables with immutable answer provenance.
- Create, list, open, and continue conversations inside a workspace.
- Show answer state, inline citations, and expandable source passages.
- Keep an evidence-inspection view available for debugging and trust.
- Start with complete non-streaming turns; add streaming only after the persisted turn and
  citation-validation path is correct and cancellation-safe.

### 4.4 Account safety

- Add authenticated change-password behavior requiring the current password.
- Revoke all existing refresh sessions after a successful password change.
- Add a local masked recovery command for the repository owner who cannot authenticate.
- Test that hashes are never returned or logged and that old credentials/sessions stop
  working after reset.

### 4.5 Evaluation and regression

- Extend the reviewed dataset with expected answerability, required claims, and acceptable
  citations rather than evaluating prose similarity alone.
- Add complex multi-part and conversational follow-up cases without replacing the existing
  retrieval regression set.
- Score citation validity, citation coverage, claim faithfulness, correct abstention,
  clarification quality, latency, and cross-workspace leakage.
- Manually review model outputs before declaring the Week 4 baseline complete.

## 5. Execution sequence

### Phase 1 - Provider and answer-contract decision

Run a small representative comparison of viable local and hosted generators, select one,
record ADR 0008, freeze the structured answer contract, and define prompt-injection and
failure behavior. No product model call is implemented before this gate is approved.

### Phase 2 - Schema and deterministic service path

Add conversation/message schemas, migrations, forced RLS, repository boundaries, structured
answer validation, and fake-generator tests. Prove tenant isolation and citation rejection
before connecting the real generator.

### Phase 3 - Production generator and answerability

Implement the selected adapter, bounded evidence packaging, answer/clarify/abstain behavior,
timeouts, safe error handling, and provenance. Keep the current C1+E1 retrieval interface
unchanged.

### Phase 4 - Conversation and citation UI

Add conversation navigation, question submission, answer-state display, inline citations,
and expandable evidence. Preserve the Week 3 evidence-search view as a diagnostic surface.

### Phase 5 - Account recovery

Add current-password change and the password-masked local recovery command, including full
session revocation and security tests.

### Phase 6 - Evaluation, demo, and review

Run deterministic, model-quality, security, browser, migration, container, and CI gates.
Update the demo to show a grounded answer plus its sources and produce the Week 4 review
report with measured limitations.

## 6. Definition of done

Week 4 is complete when:

1. ADR 0008 records one generator adapter and its privacy, cost, latency, and quality trade-offs.
2. An authorized workspace member can create and continue a persisted conversation.
3. Every returned factual answer cites only evidence IDs from the current tenant-scoped
   retrieval result, resolved to an active immutable document version.
4. Unknown, fabricated, cross-workspace, inactive-version, and deleted-document citations
   are rejected server-side.
5. Ambiguous questions can request clarification and unsupported questions abstain without
   inventing an answer.
6. Document prompt injection cannot change system policy, invoke tools, or bypass citation
   validation in the reviewed adversarial cases.
7. Conversation and message tables use forced RLS and pass direct restricted-role isolation tests.
8. The current retrieval regression metrics do not materially regress from the Week 3 baseline.
9. The reviewed answer set records citation validity/coverage, faithfulness, abstention,
   clarification, latency, and all observed failures.
10. The owner can change a known password or safely reset a forgotten local password, and
    all prior refresh sessions are revoked.
11. Backend coverage remains at least 85%, and frontend, contracts, security, migrations,
    containers, browser tests, and GitHub CI pass.
12. The demo and Week 4 review report clearly separate delivered behavior from deferred work.

## 7. Non-goals

- Changing C1, E1, vector dimension, or the production retrieval pipeline without a new lab result.
- Query rewriting, parent-child retrieval, reranking, or HNSW without measured need.
- Autonomous tools, external actions, ticket updates, or agent workflows.
- Email delivery, public password-reset links, social login, or multi-factor authentication.
- Voice, image understanding, OCR, multilingual support, or model fine-tuning.
- Public deployment or ingestion of private customer data.

## 8. Main risks and controls

| Risk | Control |
|---|---|
| Model invents unsupported claims | Structured answer state, evidence IDs, server-side citation validation, reviewed faithfulness cases |
| Retrieved document contains prompt injection | Treat evidence as quoted untrusted data; no tools; fixed system policy; adversarial tests |
| Conversation leaks across workspaces | Forced RLS, API authorization, direct restricted-role tests, immutable tenant provenance |
| Long or costly prompts | Bound evidence count/size and history window; record latency and token usage |
| Provider choice creates lock-in | Stable application-owned generator interface and versioned adapter metadata |
| Streaming creates partial or inconsistent turns | Start non-streaming; persist only validated complete turns; add streaming later behind the same contract |
| Password reset leaves stolen sessions active | Revoke all refresh-session families in the reset transaction |
| Evaluation rewards fluent but false prose | Score required claims and citations, not wording similarity alone; retain human review |

## 9. Immediate next steps

1. Review and approve this plan.
2. Choose the first real generator runtime after a small local-versus-hosted comparison.
3. Record ADR 0008 and the structured answer schema.
4. Implement and test tenant-safe conversation persistence and citation validation with a
   fake generator.
5. Connect the selected generator, then add answerability behavior and the conversation UI.
6. Add local password recovery and authenticated password change.
7. Extend the evaluation set, run the full review, and update the demo/report.
