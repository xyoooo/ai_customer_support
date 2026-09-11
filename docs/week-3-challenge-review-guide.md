# Week 3 challenge-set human review guide

- **Dataset:** `week3-apple-challenge-v1-provisional`
- **Cases:** 20 total; 19 answerable and one unanswerable
- **Purpose:** Validate realistic difficult retrieval cases before using them for selection
- **Restriction:** Review without looking at candidate rankings or scores

## Review each case in this order

1. Write the shortest correct answer using only the approved corpus.
2. Break that answer into independently necessary claims.
3. Confirm that every claim has authoritative evidence in an active document version.
4. Mark the smallest sufficient source passage for each claim.
5. Confirm that the complete evidence set is sufficient to answer the question.
6. Decide whether the wording is realistic, understandable, and free of accidental answer clues.
7. Record the case as `keep`, `revise`, or `reject`, with a short reason.

Do not change a label because one candidate failed to retrieve it. Labels describe the source
truth, not the behavior of a particular model.

## Evidence rules

- A required evidence unit represents one logical claim, not one physical parser span.
- If one sentence crosses two canonical blocks, treat those spans as one logical requirement.
- If two passages are interchangeable support for the same claim, record them as alternatives;
  do not require both.
- Require multiple evidence units only when the final answer genuinely needs all of them.
- Prefer body text containing the claim over a table of contents or heading-only match.
- Keep evidence minimal but sufficient; avoid whole pages when one paragraph or list item works.
- Verify the document version, workspace, page, block, and character bounds.
- Do not use inactive or superseded content as positive evidence for a current-answer case.

The current provisional schema lists physical spans directly. Before the dataset is declared
reviewed, cases with cross-block claims or alternative valid passages should move to grouped
evidence requirements so `Complete@K` does not over-count them.

## Question-quality rules

- The question should resemble something a real user might ask.
- Background details may be irrelevant, but they must not introduce an unsupported condition.
- A compound question should have a coherent user goal, not two unrelated facts joined only to
  make retrieval difficult.
- Avoid copying distinctive source wording unless the case intentionally tests an identifier or
  quotation.
- Version-conflict cases must state which version or time frame controls the answer.
- Safety questions must not promise that the product can diagnose spyware, identify an attacker,
  or verify a device's current state from documentation alone.
- An unanswerable case must remain unanswerable after reviewing every approved document.

## Cases needing extra scrutiny

| Cases | Review focus |
|---|---|
| 001-006 | Confirm that every condition is necessary and that multi-section wording still expresses one user goal. |
| 007 | Four evidence units may be excessive; separate device-loss protection from evidence preservation if the answer feels incoherent. |
| 008 | Confirm that biometric authentication and digital-sharing review form a plausible combined support request. |
| 009 | Decide whether photo metadata and data-at-rest encryption are one realistic request or a synthetic stress case. |
| 010 | Scanning documents and Secure Enclave protection may be artificially coupled; label as stress-only or split it. |
| 011-013 | Verify active versions and ensure the obsolete claim cannot become positive evidence. |
| 014 | Poor reception is background noise; remove it if the corpus does not support any network-related implication. |
| 015-016 | Check that all requested outputs appear in the reference answer and each has one evidence requirement. |
| 017 | Verify both false-premise corrections independently: device availability and the effect of the emergency option. |
| 018 | Confirm that neither the spyware identity nor installation date is present; the safe answer must state that the documents cannot determine them. |
| 019-020 | Preserve cautious safety language and separate documentation guidance from claims about the user's actual danger or device state. |

## Review record template

For each case, record:

```yaml
case_id: challenge-000
verdict: keep | revise | reject
reference_answer: ""
required_claims:
  - requirement_id: r1
    claim: ""
    accepted_evidence:
      - version_id: ""
        block_id: ""
        char_start: 0
        char_end: 0
answerable: true
realistic_user_goal: true
unsupported_assumptions: []
review_notes: ""
```

The dataset becomes selection-grade only after every case has a completed record and every
`revise` or `reject` decision has been applied consistently to all candidate comparisons.
