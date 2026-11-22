# Desk learning journal

Record observed results here as we work. A planned check is not a passed check.

## Lesson 0

Status: explanation introduced; waiting for the learner's workflow-versus-agent answer.

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

- Built: `desk.py` (`desk.cmd` wrapper), raw boto3 Bedrock Converse call, model `us.moonshotai.kimi-k3.1` via `DESK_MODEL`. Run with `.venv\Scripts\python.exe desk.py ask "..."`.
- Done-when checks (observed):
  - General question answered sensibly (ball valve, 2.5s). Footer on every call: model, in/out tokens, latency, cost.
  - Forced 429 (`DESK_SIMULATE=429`) and unreachable endpoint both retried 3 times with 1s/2s backoff, then exited 1 with a clear message.
- Cost shows `n/a` until `DESK_PRICE_IN` / `DESK_PRICE_OUT` are set; I did not invent Kimi K3.1 prices.
- Break it:
  - "My name is Ravi" then "What is my name?": second call said it could not see the name. Calls are stateless (fixes in Challenge 2).
  - Return window question: this model declined to guess rather than invent a number. The expected invention did not happen with Kimi K3.1; the model still has no access to the real policy (fixes in Challenge 4).
  - Long-question blank-terminal wait: timed at **20.60 seconds** of blank terminal while generating 4,000 output tokens. No output appeared until the entire completion arrived at once. Directly highlights the need for streaming (fixed in Challenge 2 with ConverseStream).
- Status: Challenge 1 complete. Git repo initialized and tagged `ch01` on GitHub.

## Challenge 2: Conversation

### Plan & Architecture
- **Interactive REPL:** Add `desk chat` subcommand with message history loop.
- **Streaming Tokens:** Call `client.converse_stream()` to yield and render tokens live to the terminal.
- **Session Commands:** Implement `/reset`, `/save <name>`, and `/load <name>` persisting to `sessions/`.
- **Sliding Window Context:** Drop oldest middle conversational pairs when exceeding `MAX_HISTORY_TOKENS` while pinning system prompt and first turn.
- **Files Changing:** `constants.py`, `desk.py`, `.gitignore`, `documents/challenge-2.md`.

