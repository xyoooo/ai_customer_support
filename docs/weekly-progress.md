# Weekly Progress Records

Use two documents for each development week:

1. **Preview plan** - written before implementation. It records the prior-week recap, objective, planned outcomes, execution sequence, definition of done, non-goals, and risks.
2. **Review report** - written after validation. It records delivered scope, evidence and test outcomes, deviations from the preview, known limitations, carry-forward work, and the next-week handoff.

## Naming convention

- `week-N-preview-plan.md`
- `week-N-review-report.md`

The review report is the source of truth for what actually shipped. Items not completed should be marked `Partial` or `Deferred` rather than described as delivered.

## Required development routine

Every material implementation starts with a short engineering decision gate in the preview plan or an ADR. No product code should be written until the gate answers these questions:

1. **Why is this needed now?** Define the user, product, security, or operational problem and explain why it belongs in the current milestone.
2. **What choices are available?** List realistic alternatives, including the option to defer the work. Compare them using security, correctness, reliability, delivery effort, operating cost, portability, and fit with the current architecture.
3. **What is the final decision?** State the selected approach, why it fits the current constraints, and which trade-offs are being accepted.
4. **How will it be verified?** Define observable acceptance criteria and the failure cases that automated tests must cover.
5. **How can it improve later?** Record likely evolution paths and the measurable triggers that would justify extra infrastructure or complexity.

During implementation, new information that changes the decision must be recorded in the preview plan or a new ADR before the design diverges. At the end of the week, the review report compares actual delivery and evidence with the preview rather than rewriting the original intent.

## Current records

| Week | Preview plan | Review report | Stage |
|---|---|---|---|
| 1 | Created before this record format | [Week 1 review report](week-1-review-report.md) | Foundation - complete |
| 2 | [Week 2 preview plan](week-2-preview-plan.md) | [Week 2 review report](week-2-review-report.md) | Document lifecycle - core milestone complete |
| 3 | [Week 3 preview plan](week-3-preview-plan.md) | Pending | RAG strategy evaluation and baseline - planned |

## End-of-week review checklist

- Revisit the engineering decision gate and record whether its assumptions remained valid.
- Compare every definition-of-done item with actual evidence.
- Record exact test counts, coverage, builds, migrations, and manual checks.
- Separate `Complete`, `Partial`, and `Deferred` scope.
- Note architecture decisions or plan changes and why they were made.
- Record accepted trade-offs, technical debt, and the trigger for each proposed future improvement.
- List known limitations and risks without turning targets into claims.
- End with a clear handoff for the next preview plan.
