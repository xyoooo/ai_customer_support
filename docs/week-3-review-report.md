# SupportPilot Week 3 Review Report

- **Stage:** RAG strategy evaluation and baseline
- **Status:** In progress; final delivery evidence pending
- **Document type:** Weekly review report
- **Working note date:** September 1, 2026
- **Project:** Enterprise-style AI customer support platform

## Carry-forward evaluation work

### Separate complex-question challenge set

The initial human-reviewed 50-case dataset remains the stable Week 3 retrieval baseline for comparing chunking and embedding strategies. It should not be repeatedly expanded or rewritten after candidate evaluation begins, because changing the benchmark would weaken comparisons between experiment runs and future regressions.

After the initial retrieval strategy is selected, create a separate challenge set of approximately 20-30 complex questions. This work is deferred to the Week 4 grounded-answer and citation-validation stage, when the system can evaluate both evidence retrieval and answer construction.

The challenge set should cover:

- Multi-document and multi-section synthesis.
- Conditional troubleshooting with several user constraints.
- Comparisons whose evidence appears in distant sections.
- Conflicting, superseded, or version-sensitive information.
- Questions containing an incorrect premise.
- Vague requests that require clarification before answering.
- Long conversational questions containing irrelevant details.
- Answers that require multiple citations or are only partially supported.
- Safety-sensitive cases where the system must avoid overconfidence.

Keep challenge-set results separate from the 50-case baseline metrics. Report retrieval quality, answer groundedness, citation completeness, clarification or abstention behavior, and representative failure cases rather than combining everything into one aggregate score.

This item is carry-forward work and must not be described as delivered in the final Week 3 report unless the challenge set is actually reviewed and executed.
