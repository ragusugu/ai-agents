# Challenge 3 verification — 26 November 2026

**Historical review:** the user subsequently narrowed extraction to the six
original Challenge 3 fields. The richer schema, source findings and percentages
below describe the earlier run. Its predictions are preserved; they are not
current six-field results or evidence for a new live run.

The extraction contract, native Bedrock schema requests, validation/repair,
batch processing, JSONL storage and local accuracy command are implemented.
Human approval of the 15 draft labels is still required before claiming
human-labelled accuracy. Live verification and source comparison are recorded
below; validation and model verification do not establish perfect accuracy.

## Defects fixed during this review

1. **Repeated SKU lines could be scored differently after reordering.** Product
   assignment used only SKU/description identity, so equal-identity lines with
   different quantities or units could be paired incorrectly. Matching now uses
   field agreement to break identity ties while preserving one-to-one assignment,
   match cardinality and exact-SKU priority. A regression failed before the fix
   and passes afterward.
2. **A result-storage failure could silently recover and continue provider
   calls.** Raised local/storage errors now stop the batch and preserve its pending
   journal. Explicit offline recovery is required before resuming. A transient
   write-failure regression reproduced the old behavior and now verifies that no
   second email is sent.
3. **The existing test suite failed on Windows and depended on local artifacts.**
   Synthetic source writes now preserve fixture newlines, historical fixtures
   include the required fingerprint fields, and historical-output tests create
   their own evidence. Test classes share fixture helpers without inheriting and
   rerunning each other's test cases. A fresh checkout no longer needs ignored
   historical output files to run the suite.
4. **Windows source-map replacement had no retry for temporary read locks.**
   Repeated local tests encountered `PermissionError` during atomic replacement.
   Source-map writes now retry that specific condition at most six times (1.55
   seconds of bounded backoff). Other errors propagate immediately; a permanent
   denial preserves the existing file and stops the batch. Both cases are tested.
   Disposable fixtures also live under ignored `output/`, avoiding tracked-file
   watchers during rapid test writes.

## Acceptance coverage

| Requirement | Verification |
| --- | --- |
| OrderRequest fields and intent enum | Strict Pydantic schema in `skills/structured-output/order_schema.py`; invalid types, bounds, dates, extra keys and missing product identities tested. |
| Provider structured-output mode | Converse uses `outputConfig.textFormat` with `json_schema`, matching the [AWS interface](https://docs.aws.amazon.com/bedrock/latest/userguide/structured-output.html); unsupported schemas fail without a prompt-only fallback. |
| Validate each response; at most two repairs | Schema and semantic repairs share one budget; invalid JSON, refusal, truncation and verifier failures tested. |
| Failed responses enter needs_review | Persisted review outcomes, source association and interrupted storage recovery tested. |
| Batch every selected email to results.jsonl | Synthetic 30-email workflow verifies 29 successes plus one invalid-source review; 40-email workflow verifies full processing, reuse and a separate 15-output sample. |
| Fifteen hand labels and field accuracy | Fifteen project annotations exist as pending assistant drafts. One-command scoring is tested on 15 separate synthetic labels, including review and missing outcomes in denominators. Actual human review remains outstanding. |
| Multi-intent explicitly defined | Primary/secondary requests, kind-to-intent mapping, priority, duplicate rejection and purchase authorization tested. |
| Cheap/large model accuracy and cost comparison | Optional stretch work is not implemented or claimed by this review. |

## Repeatable checks

```powershell
.venv\Scripts\python.exe -m unittest discover -s challenges/challenge3 -v
.venv\Scripts\python.exe -m pip --disable-pip-version-check check
git diff --check
```

All **39 tests passed** after the fixes (90.464 seconds). Dependency checking
reported no broken requirements. The transcript is
`output/challenge3-audit-tests-20261126.txt`.

The tests use synthetic email/label fixtures, mock native provider I/O and forbid
Bedrock client creation. They verify program behavior, not live semantic quality.

## Live verification

The user explicitly authorized a fresh 30-email check using the configured
`global.anthropic.claude-sonnet-5-5` model in `us-east-1`. The live run uses the
normal 4,000-token response limit and stores separate evidence in
`output/challenge3-live-20261126/`. Earlier predictions are preserved.

An initial restricted-network attempt could not reach Bedrock and was stopped.
Its nine source-associated review records, including an interrupted request
recovered offline, remain in `output/challenge3-verification-20261126/`. They are
connectivity evidence, not model-quality measurements.

The live provider phase completed all 30 emails: 29 schema-valid predictions and
one automatic review outcome. Eleven emails used at least one repair; no email
exceeded two repairs. All 29 success receipts were rechecked against the source,
payload and current contract. Every source checksum and source association
matched; no email was missing.

The assistant then compared all 30 entries with their own full original emails,
including descriptions and restrictions. A source-informed check independently
verified signature identities, SKU evidence, quantity/unit values, date/urgency
unknowns, purchase authorization and request-kind coverage. It identified two
additional routing discrepancies and appended review outcomes for them.

**Final current outcomes: 27 without an identified discrepancy; 3 need review
(EM-006, EM-016, EM-020).** Thus 30/30 inputs have a validated or review outcome;
this is not a claim that all 30 extractions are correct. An offline resume plan
reuses all 30 outcomes and requires zero new provider calls.

Raw predictions are append-only evidence: `results.jsonl` retains 29 original
schema-valid payloads, including the two subsequently superseded by review.
Downstream acceptance must use each source's latest `source-map.jsonl` record,
as batch reuse and scoring do. Reading every historical result line alone would
include those superseded predictions. No raw prediction was rewritten.

Evidence in `output/challenge3-live-20261126/`:

- `source-audit.json`: all 30 source-linked audit entries, checks and findings.
- `verification-summary.json`: current counts, fingerprint and resume checks.
- `needs_review.jsonl`: three current review records and supporting details.
- `accuracy-report.json`: latest field report over all 15 draft labels.
- `accuracy-report-provider-phase.json`: report before assistant review routing.
- `verifications/`: 29 provider grounding receipts with source evidence.

The final draft-label report covers 13 validated labels and two review labels,
with zero missing/invalid records. Overall agreement is **157/186 field checks
(84.4%)**, including reviews in denominators. This is **assistant draft
agreement, not human-labelled accuracy**. EM-002 has extra request splits versus
the draft; EM-025 differs on RMA enquiry classification. Those disagreements need
human adjudication rather than automatic relabelling to match predictions.

Run the local report without model calls:

```powershell
.\desk.cmd accuracy
```

After actual human label approval, use:

```powershell
.\desk.cmd accuracy --require-reviewed --show-results
```

Review handling is explicit: errors and the source association stay in the
review pile; review outcomes do not count as correct data. After checking the
source and resolving the extraction/policy issue, an intentional new run can use
`--retry-review`. A normal resume reuses review outcomes without charging again.
Do not hand-edit result lines or their source-map associations independently.

## Source review observations

- EM-004 preserves the unconfirmed proposed quantity as null and retains the
  uncertainty in its description.
- EM-005 preserves the three mutually exclusive quantities in one line with
  quantity null and the explicit unit populated.
- EM-006 retains the conditional stock warning in the quote/item descriptions
  but has no separate availability request. This is a request-granularity issue
  under the current prompt, even though the verifier accepted it. Do not treat
  a verifier pass as proof of perfect extraction accuracy.
- EM-016 exhausted its two repairs because the verifier could not settle the
  distinction between a card-charge restriction and denial of a new purchase.
  It correctly landed in the review pile rather than receiving an uncertain
  success.
- EM-018 now records `purchase_authorized=false`, matching the explicit denial
  of a new order/payment in the source.
- EM-020 retains the date/carrier check inside its complaint description but
  has no separately routed status request. This repeats the request-granularity
  limitation identified in the earlier source review.

After checking/correcting every original email/label pair, the user must record
their actual reviewer, review date and approved status in
`evaluation/challenge3_labels.draft.json`. The software never approves those
labels automatically. Until then, the reported scores are assistant draft
agreement. The source-linked checklist is
`evaluation/challenge3_labels_review.md`.
