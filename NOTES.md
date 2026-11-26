# Desk learning journal

Record observed results here as we work. A planned check is not a passed check.
The source requirements are in [the challenge document](documents/references/agentic-ai-15-challenges.pdf),
page 2 (Git and journal rules), and pages 4-6 (Challenges 1-3).

## Git checkpoints

- `main` remains the Challenge 1 branch at `9bb7e63`.
- The existing `ch01` tag at `901ed9e` is preserved; `main` also includes subsequent Challenge 1 refactoring and documentation.
- `ch02` preserves the historical Challenge 2 branch tip, `9776250`, including its separate terminal changes. That tip is not an ancestor of the current Challenge 3 branch, so its tag must be retained when cleaning old branch names.
- `ch03` is the current Challenge 3 working branch, renamed from `challenge-3` without changing its history.
- Add completion tags `chNN` when the corresponding challenge is finished. A branch name alone does not certify completion. Challenge 3's completion tag remains pending the evidence listed below.
- Keep Break-it observations and outstanding checks in this file. Generated outputs, source data, credentials and saved sessions remain ignored.

## Lesson 0

Historical checkpoint: explanation introduced; no learner workflow-versus-agent answer was recorded in the earlier journal.

## Entry template

- Lesson or challenge:
- Concept in my own words:
- My prediction:
- What I built or ran:
- What actually happened:
- Evidence (command, output, or artifact):
- Failure and explanation:
- What I would change next:
- Checkpoint status and remaining questions:

## Challenge 1: One call

Restored from the journal on `main`; the observations below are historical, not fresh provider calls.

- Built: `desk.py` (`desk.cmd` wrapper), raw boto3 Bedrock Converse call, model `us.moonshotai.kimi-k3.1` via `DESK_MODEL`. The original command was `.venv\Scripts\python.exe desk.py ask "..."`; the current entry point is `desk.cmd ask "..."`.
- Done-when checks (observed):
  - General question answered sensibly (ball valve, about 2.5 seconds). Footer included model, input/output tokens, latency and cost.
  - Forced 429 (`DESK_SIMULATE=429`) and an unreachable endpoint both retried three times with backoff, then exited with a clear error.
- Cost showed `n/a` without configured prices; no prices were invented.
- Break it results:
  - Two separate calls, "My name is Ravi" then "What is my name?", lost the name. The calls were stateless; Challenge 2 adds conversation history.
  - The return-window question did not produce an invented number with the tested model. It declined to guess, but still had no access to the actual policy; Challenge 4 addresses grounding.
  - A long question produced **20.60 seconds** of blank terminal while generating 4,000 output tokens. Nothing appeared until completion; Challenge 2 adds streaming.
- Status: completed historical checkpoint, preserved as `ch01`.
- Evidence: [Challenge 1 results](documents/challenge-1.md) and the earlier `main:NOTES.md`.

## Challenge 2: Conversation

- Built: multi-turn message history, ConverseStream output, save/load/reset, token totals, a sliding window and a pinned first exchange, using the raw provider SDK.
- Recorded checks on 22 November 2026: follow-up questions resolved the second valve, a saved session reloaded in a new process, `/reset` cleared memory, and simulated 429/timeouts failed clearly while chat stayed open.
- Break it results:
  - With an 80-token window, the `ORD-7788` turn was dropped. The model retained the pinned name Ravi and recent shipping destination Chennai, but said it no longer had the order number. This is an observed small-window reproduction of forgetting, not the prescribed 40-turn experiment.
  - The long reply had a first-token time of 11.68 seconds and total time of 12.78 seconds. Timing/chunk evidence was recorded; the historical document still marks its interactive visual confirmation as pending.
  - The prescribed five-email, three-run free-form-output comparison has instructions but no recorded execution result in the existing document. Do not count it as passed.
- Evidence: [Challenge 2 results](documents/challenge-2.md), especially Tests 1-4 and the Break-it section.
- Git: the historical implementation checkpoint is preserved at tag `ch02`; the exact 40-turn and repeated five-email Break-it checks remain to be recorded.

## Challenge 3: Structured outputs

Current code checkpoint: 26 November 2026. Human-reviewed accuracy is not yet established.

- Built: the six-field `OrderRequest` skill schema, native Bedrock structured output, strict validation, at most two repairs, isolated per-email grounding checks, review outcomes, batch reuse and a one-command local accuracy report.
- Chat runs the same Python workflow through local slash commands or a typed native tool call. The menu remains seven commands. Shared telemetry includes extraction/verification usage, respects explicit model overrides, and presents compact counts such as `4k` and `64k`.
- Break it and regression results recorded in this session:
  - Malformed JSON, extra fields, invalid quantities, refusals and unavailable verification were exercised offline; outputs were repaired within the bound or routed to review.
  - Synthetic 30- and 40-email batches were processed completely while displayed samples remained limited to 15. Reused outcomes triggered no extraction requests.
  - A simulated storage failure stopped before the next email and preserved pending recovery data. Temporary Windows source-map replacement failures used bounded retries; permanent failures preserved the old file.
  - `desk ask` and chat `/ask` previously crashed because their parser lacked the command attribute. Regression checks reproduced and verified the fix with options before, inside and after the question.
  - Explicit model overrides previously called the requested model while reporting the session default. Both `/ask` and `/structured-output` now report the selected model, preserve the default for the next chat turn, and count usage once.
  - The compact details preview fit one content row at 170 columns and wrapped to two at 80 columns, retaining the values, colors and existing panel.
- Validation on 26 November 2026: the final pre-commit offline run passed **77 tests in 69.745 seconds**, including the compact layout and model-override fixes. The 14 presentation/usage checks and whitespace checks also passed. These checks mock provider I/O and do not certify live extraction accuracy.
- Historical richer-schema live observations are preserved in [the historical review](documents/challenge-3-review.md). Its percentages do not establish accuracy for the current six-field contract.
- Required remaining evidence:
  - Human review of the 15 source-linked labels. `evaluation/challenge3_labels.draft.json` still records `human_review.status` as `pending`; assistant draft agreement must not be called human-labelled accuracy.
  - A fresh documented current-contract run and the prescribed description-only SKU versus catalog check, with the count of nonexistent SKUs.
  - The prescribed policy-question Break-it observation for the current chat, including whether the answer is sourced. Earlier Challenge 1/2 policy observations remain historical evidence only.
- Completion tag `ch03` is deferred until these checks are completed and recorded; the `ch03` branch retains the current implementation work.
- Repeatable offline command: `.venv\Scripts\python.exe -m unittest discover -s challenges/challenge3 -q`.
