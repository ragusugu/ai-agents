# Challenge 2: Conversation — Test Results and Documentation

## Overview
- **Goal:** Turn the stateless one-shot tool into an interactive multi-turn chat with streaming output and message-history management.
- **Shortfall of Challenge 1:** Every call was stateless (no memory between calls), and the terminal stayed blank until the whole reply arrived (20.60s in the Challenge 1 Break-It test).
- **CLI command:** `desk chat` or `.venv\Scripts\python.exe src\desk.py chat` (`desk ask` from Challenge 1 is unchanged).
- **Model used:** `us.moonshotai.kimi-k3.1` via Amazon Bedrock (ConverseStream API), raw boto3, no agent framework.
- **Files (in `src/`):** `desk.py` (CLI, chat loop, commands), `model.py` (Bedrock calls, streaming, retries), `session.py` (save/load, sliding window, token accounting), `constants.py` (`CHAT_SYSTEM_PROMPT`, `MAX_HISTORY_TOKENS`).

---

## 1. Requirements Implemented

| Requirement (from the challenge) | Where | How |
|---|---|---|
| `desk chat` keeps a message list and sends all of it each turn | `desk.py` `cmd_chat` | `state["messages"]` grows by one user + one assistant message per turn; the full list is sent on every call. |
| Stream tokens as they arrive | `model.py` `stream_model`, `_render_stream` | `client.converse_stream()`; each `contentBlockDelta` text chunk is printed with `flush=True`. Kimi's hidden reasoning chunks show as `(thinking....)` instead of a blank screen. Retries only happen before any answer text is printed. |
| Proper system prompt: role, tone, "if you don't know, say so" | `constants.py` `CHAT_SYSTEM_PROMPT` | Separate from Challenge 1's `SYSTEM_PROMPT`, so `desk ask` is unchanged. |
| `/reset`, `/save <name>`, `/load <name>` (JSON) | `desk.py` `handle_command`; `session.py` `save_session`, `load_session`, `_session_path` | Saved to `save/<name>.json` (gitignored). Names limited to `[A-Za-z0-9_-]` so `../x` cannot escape the folder. Clear errors for missing name, missing file, corrupt file, unknown command. |
| Tokens per turn and a running total | `desk.py` footer; `session.py` `_sent_tokens` | Counts `inputTokens + cacheReadInputTokens + cacheWriteInputTokens`, because Bedrock reports the cached part of the resent history separately. |
| Sliding window: drop oldest turns over a token limit | `session.py` `trim_history`, `_estimate_tokens` | Before each send, drops the oldest user/assistant **pair** until history fits `MAX_HISTORY_TOKENS` (6000; override with `DESK_HISTORY_TOKENS`). Prints `[window: dropped N ...]`. |
| **Stretch:** pin system prompt and first user message | `session.py` `trim_history` | The first user/assistant pair is never dropped (pinning only the user message would break Bedrock's user/assistant alternation). The system prompt is sent separately via `system=` every call, so it is always kept. |

---

## 2. How These Tests Were Run
- Date: 2026-11-22, Windows 11, live calls to Amazon Bedrock.
- Chat tests were fed scripted input lines; each typed line is echoed after the `>` prompt so the transcript reads like a real terminal session. All output below is pasted exactly as produced.
- Streaming cannot be seen in a pasted transcript; it is evidenced by the `first token` vs `total` timings and by chunk counts. A visual check in an interactive `desk chat` session is still to be done.

---

## 3. Test Verification & Actual Observed Outputs

### Test 0: Offline unit checks (no model calls)
**Command:**
```powershell
.venv\Scripts\python.exe offline_checks.py "<project>\src"
```
A scratch test script (not part of the repo) that checks `trim_history`, `_sent_tokens`, `_session_path`, `save_session` / `load_session` directly, using a temporary folder for files.

**Output:**
```text
PASS window dropped 3 pairs
PASS first pair pinned
PASS newest user message kept last
PASS roles still alternate user/assistant
PASS under limit or at minimum
PASS short history untouched
PASS sent tokens = input + cacheRead + cacheWrite
PASS sent tokens without cache fields
PASS refuse '../evil'
PASS refuse 'a/b'
PASS refuse ''
PASS refuse 'x y'
PASS refuse '..\\evil'
PASS round trip keeps messages (incl. unicode)
PASS round trip keeps totals
PASS missing file error
PASS corrupt file error
PASS round trip wrote to temp folder, not save/
PASS corrupt file reports 'not valid JSON'
```
- **Status:** PASS (19/19).

---
### Test 1: Memory, follow-up question and the honesty rule
**Command:**
```powershell
.venv\Scripts\python.exe src\desk.py chat
```
**Typed in the chat (one line per prompt):**
```text
My name is Ravi. List 3 valve types, one line each.
and what about the second one? Two sentences.
What is my name?
What is Meridian's return window for opened items?
/save ch2-demo
/exit
```
**Output:**
```text
Desk Chat (Meridian Supply Co.)
Commands: /reset (clear history) | /save <name> | /load <name> | /help | /exit

> My name is Ravi. List 3 valve types, one line each.

(thinking.)
Ball valve  
Gate valve  
Globe valve

--
Turn: in 238 tok | out 177 tok | first token: 2.74s | total: 2.74s | Session Total: in 238 tok | out 177 tok | history: ~23/6000 tok

> and what about the second one? Two sentences.

(thinking.)
A gate valve uses a sliding gate to start or stop fluid flow, making it well suited for on/off isolation with minimal pressure loss when fully open. It is generally not recommended for throttling, as partial opening can cause vibration and wear.

--
Turn: in 291 tok | out 209 tok | first token: 1.93s | total: 1.98s | Session Total: in 529 tok | out 386 tok | history: ~95/6000 tok

> What is my name?

(thinking)
Your name is Ravi.

--
Turn: in 378 tok (284 cached) | out 72 tok | first token: 1.53s | total: 1.53s | Session Total: in 907 tok | out 458 tok | history: ~104/6000 tok

> What is Meridian's return window for opened items?

(thinking.)
I don’t have Meridian’s return-window policy for opened items. Please check the current return policy or confirm with the returns/customer service team before quoting a timeframe.

--
Turn: in 428 tok (371 cached) | out 198 tok | first token: 1.72s | total: 1.74s | Session Total: in 1335 tok | out 656 tok | history: ~161/6000 tok

> /save ch2-demo
[saved 8 messages to C:\Users\suganeshwaran\Desktop\AI Agents\save\ch2-demo.json]
> /exit
Goodbye!
```
- **What this proves:** "and what about the second one?" resolved to the gate valve; the name from turn 1 was remembered; the return-window question got "I don't have" instead of an invented policy. Input tokens grow each turn (238 → 291 → 378 → 428) because the whole history is resent; part of it is served from Bedrock's cache.
- **Status:** PASS

---
**Saved session file `save/ch2-demo.json`:**
```json
{
  "model": "us.moonshotai.kimi-k3.1",
  "saved_at": "2026-11-22 21:17:16",
  "total_in": 1335,
  "total_out": 656,
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "text": "My name is Ravi. List 3 valve types, one line each."
        }
      ]
    },
    {
      "role": "assistant",
      "content": [
        {
          "text": "Ball valve  \nGate valve  \nGlobe valve"
        }
      ]
    },
    {
      "role": "user",
      "content": [
        {
          "text": "and what about the second one? Two sentences."
        }
      ]
    },
    {
      "role": "assistant",
      "content": [
        {
          "text": "A gate valve uses a sliding gate to start or stop fluid flow, making it well suited for on/off isolation with minimal pressure loss when fully open. It is generally not recommended for throttling, as partial opening can cause vibration and wear."
        }
      ]
    },
    {
      "role": "user",
      "content": [
        {
          "text": "What is my name?"
        }
      ]
    },
    {
      "role": "assistant",
      "content": [
        {
          "text": "Your name is Ravi."
        }
      ]
    },
    {
      "role": "user",
      "content": [
        {
          "text": "What is Meridian's return window for opened items?"
        }
      ]
    },
    {
      "role": "assistant",
      "content": [
        {
          "text": "I don’t have Meridian’s return-window policy for opened items. Please check the current return policy or confirm with the returns/customer service team before quoting a timeframe."
        }
      ]
    }
  ]
}
```

---
### Test 2: Load in a new process, command handling and /reset
**Command:**
```powershell
.venv\Scripts\python.exe src\desk.py chat
```
**Typed in the chat (one line per prompt):**
```text
/load nope
/load ../x
/load
/foo
/help
/load ch2-demo
Which valve did we discuss second, and what is my name? One line.
/reset
What is my name?
/quit
```
**Output:**
```text
Desk Chat (Meridian Supply Co.)
Commands: /reset (clear history) | /save <name> | /load <name> | /help | /exit

> /load nope
desk: No saved session named 'nope' (looked in C:\Users\suganeshwaran\Desktop\AI Agents\save\nope.json).
> /load ../x
desk: Session name may only use letters, digits, '_' and '-'.
> /load
usage: /load <name>
> /foo
Unknown command: /foo. Commands: /reset (clear history) | /save <name> | /load <name> | /help | /exit
> /help
Commands: /reset (clear history) | /save <name> | /load <name> | /help | /exit
> /load ch2-demo
[loaded 'ch2-demo': 8 messages, saved 2026-11-22 21:17:16]
[last assistant message: I don’t have Meridian’s return-window policy for opened items. Please check the current return policy or confirm with th]
> Which valve did we discuss second, and what is my name? One line.

(thinking)
We discussed the gate valve second, and your name is Ravi.

--
Turn: in 511 tok (421 cached) | out 84 tok | first token: 2.20s | total: 2.20s | Session Total: in 1846 tok | out 740 tok | history: ~192/6000 tok

> /reset
[history cleared; the next message starts a fresh conversation]
> What is my name?

(thinking.)
I don’t have your name in this conversation. What should I call you?

--
Turn: in 227 tok | out 199 tok | first token: 1.85s | total: 1.85s | Session Total: in 227 tok | out 199 tok | history: ~22/6000 tok

> /quit
Goodbye!
```
- **What this proves:** A brand-new process loaded the saved session and continued it (recalled the gate valve and the name). Bad inputs got clear messages. After `/reset` the model no longer knew the name and totals restarted.
- **Status:** PASS

---
### Test 3: Sliding window with pinned first exchange
**Command:**
```powershell
$env:DESK_HISTORY_TOKENS="80"; .venv\Scripts\python.exe src\desk.py chat
```
**Typed in the chat (one line per prompt):**
```text
My name is Ravi. Reply in one short sentence.
My order number is ORD-7788. Reply in one short sentence.
I also like gate valves. Reply in one short sentence.
We ship to Chennai. Reply in one short sentence.
What is my name, my order number, and where do we ship? One line.
/exit
```
**Output:**
```text
Desk Chat (Meridian Supply Co.)
Commands: /reset (clear history) | /save <name> | /load <name> | /help | /exit

> My name is Ravi. Reply in one short sentence.

(thinking)
Nice to meet you, Ravi—how can I help you today?

--
Turn: in 234 tok | out 119 tok | first token: 2.25s | total: 2.25s | Session Total: in 234 tok | out 119 tok | history: ~24/80 tok

> My order number is ORD-7788. Reply in one short sentence.

(thinking.)
Thanks, Ravi—what would you like help with regarding order ORD-7788?

--
Turn: in 299 tok (292 cached) | out 170 tok | first token: 1.66s | total: 1.66s | Session Total: in 533 tok | out 289 tok | history: ~55/80 tok

> I also like gate valves. Reply in one short sentence.

(thinking..)
Thanks, Ravi—I’ve noted your interest in gate valves.

--
Turn: in 364 tok (292 cached) | out 313 tok | first token: 2.29s | total: 2.29s | Session Total: in 897 tok | out 602 tok | history: ~82/80 tok

> We ship to Chennai. Reply in one short sentence.
[window: dropped 1 oldest turn(s); kept first exchange + 3 recent messages, ~62 tok]

(thinking.)
Thanks, Ravi—I’ve noted that you ship to Chennai.

--
Turn: in 353 tok | out 195 tok | first token: 1.69s | total: 1.69s | Session Total: in 1250 tok | out 797 tok | history: ~75/80 tok

> What is my name, my order number, and where do we ship? One line.
[window: dropped 1 oldest turn(s); kept first exchange + 3 recent messages, ~64 tok]

(thinking.)
Your name is Ravi, I don’t have your order number, and you ship to Chennai.

--
Turn: in 359 tok | out 206 tok | first token: 1.76s | total: 1.78s | Session Total: in 1609 tok | out 1003 tok | history: ~83/80 tok

> /exit
Goodbye!
```
- **What this proves:** Once history passed 80 tokens, the oldest unpinned pair was dropped. The ORD-7788 turn was removed, so the model said it doesn't have the order number; the pinned first turn (Ravi) and the latest turn (Chennai) were kept. Input per turn levels off (~355-365 tokens) instead of growing forever.
- **Status:** PASS

---
### Test 4: Long answer streaming
**Command:**
```powershell
.venv\Scripts\python.exe src\desk.py chat
```
**Typed in the chat (one line per prompt):**
```text
Write a 400-word guide to selecting industrial valves.
/exit
```
**Output:**
```text
Desk Chat (Meridian Supply Co.)
Commands: /reset (clear history) | /save <name> | /load <name> | /help | /exit

> Write a 400-word guide to selecting industrial valves.

(thinking...........................)
Selecting the right industrial valve starts with the process, not the catalog. A valve that works well in clean water may fail quickly in slurry, steam, corrosive chemicals, or hygienic service.

**1. Define the duty.** Identify whether the valve must isolate flow, throttle it, prevent reverse flow, divert media, or protect equipment. Isolation valves prioritize tight shutoff; control valves need predictable response across the required operating range. Do not assume an isolation valve is suitable for continuous throttling.

**2. Record operating conditions.** Document the fluid, solids content, viscosity, temperature, pressure, flow range, and cleaning method. Include startup, shutdown, upset, and emergency conditions, not just normal operation. Check whether cavitation, flashing, erosion, water hammer, or thermal expansion could occur.

**3. Compare valve designs.** Ball and plug valves often suit quick quarter-turn isolation. Gate valves are commonly used for straight-through isolation, while butterfly valves can be compact options for larger lines. Globe valves are frequently considered for throttling. Diaphragm and pinch designs may be useful for corrosive media or slurries. Check valves limit reverse flow, but their type and orientation must match the application.

**4. Specify materials and connections.** Confirm compatibility of the body, trim, seats, seals, and packing with the media and temperature. Consider corrosion, abrasion, permeation, fire-safety needs, and contamination limits. Match pressure-temperature ratings, end connections, dimensions, and applicable ASME, API, ISO, or other project standards.

**5. Size and automate carefully.** Use process calculations and manufacturer data to assess flow capacity, pressure drop, rangeability, shutoff capability, and actuator torque. For automated valves, define fail position, power supply, control signal, cycle frequency, response time, and local manual override requirements. Allow for accessories such as positioners, limit switches, and solenoids where needed.

**6. Evaluate lifecycle needs.** Review leakage requirements, testing, certification, installation space, orientation, accessibility, spare-parts availability, and maintenance intervals. A lower purchase price may be offset by downtime, difficult repairs, or frequent seal replacement.

For critical applications, request drawings, material certificates, test reports, and a statement of exclusions. Verify that the selected assembly, not just the valve body, meets site requirements. Keep the datasheet with maintenance records so replacements can be matched accurately and changes to process conditions trigger a review.

Before ordering, have the datasheet reviewed by the responsible process or mechanical engineer, especially for hazardous, high-pressure, oxygen, steam, or safety-related service. Ask the supplier to confirm the complete specification in writing, including materials, ratings, actuation, testing, and delivery documentation.

--
Turn: in 233 tok | out 3311 tok | first token: 11.68s | total: 12.78s | Session Total: in 233 tok | out 3311 tok | history: ~765/6000 tok

> /exit
Goodbye!
```
- **What this proves:** `(thinking...)` dots appear while the model reasons, then the answer streams from 11.68s to 12.78s. In Challenge 1 the same kind of request showed a blank terminal for 20.60s.
- **Status:** PASS

---
### Test 5: `desk ask` from Challenge 1 still works
**Command:**
```powershell
.venv\Scripts\python.exe src\desk.py ask "What is a gate valve? One sentence."
```
**Output:**
```text
A gate valve is a shutoff valve that starts or stops fluid flow by raising or lowering a gate into the flow path, typically used fully open or fully closed rather than for throttling.

--
model: us.moonshotai.kimi-k3.1 | in: 146 tok | out: 220 tok | latency: 2.55s | cost: n/a (set DESK_PRICE_IN / DESK_PRICE_OUT, USD per 1M tokens)
```
- **Status:** PASS (unchanged behavior and footer).

---
### Test 6: Forced 429 inside chat
**Command:**
```powershell
$env:DESK_SIMULATE="429"; .venv\Scripts\python.exe src\desk.py chat
```
**Typed in the chat (one line per prompt):**
```text
hello
/exit
```
**Output:**
```text
Desk Chat (Meridian Supply Co.)
Commands: /reset (clear history) | /save <name> | /load <name> | /help | /exit

> hello

[attempt 1/3 failed: ThrottlingException: Simulated 429: too many requests; retrying in 1.1s]
[attempt 2/3 failed: ThrottlingException: Simulated 429: too many requests; retrying in 2.1s]
desk: Giving up after 3 attempts. Last error: ThrottlingException: Simulated 429: too many requests. Check your network and AWS credentials, or wait a minute if you are being rate limited.
> /exit
Goodbye!
```
- **What this proves:** Three attempts with 1s/2s backoff, then a clear message; the chat stays open instead of crashing.
- **Status:** PASS

---
### Test 7: Forced timeout inside chat
**Command:**
```powershell
$env:DESK_SIMULATE="timeout"; .venv\Scripts\python.exe src\desk.py chat
```
**Typed in the chat (one line per prompt):**
```text
hello
/exit
```
**Output:**
```text
Desk Chat (Meridian Supply Co.)
Commands: /reset (clear history) | /save <name> | /load <name> | /help | /exit

> hello

[attempt 1/3 failed: ReadTimeoutError: Read timeout on endpoint URL: "simulated"; retrying in 1.2s]
[attempt 2/3 failed: ReadTimeoutError: Read timeout on endpoint URL: "simulated"; retrying in 2.1s]
desk: Giving up after 3 attempts. Last error: ReadTimeoutError: Read timeout on endpoint URL: "simulated". Check your network and AWS credentials, or wait a minute if you are being rate limited.
> /exit
Goodbye!
```
- **What this proves:** Same retry/backoff path for network timeouts; the chat stays open.
- **Status:** PASS

---
### Test 8: No arguments shows help
**Command:**
```powershell
.venv\Scripts\python.exe src\desk.py
```
**Output:**
```text
usage: desk [-h] {ask,chat} ...

Desk: Meridian Supply Co. assistant

positional arguments:
  {ask,chat}
    ask       send one question to the model
    chat      start an interactive conversation session

options:
  -h, --help  show this help message and exit

Example:
  desk ask "What is a ball valve?"
```
- **Status:** PASS (`chat` listed alongside `ask`).

---

## 4. Done-When Summary

| Done when | Evidence | Status |
|---|---|---|
| Follow-ups such as "and what about the second one?" work | Test 1 | PASS |
| Output visibly streams | Test 4 timings (answer arrives over 11.68s → 12.78s in ~560 chunks) | PASS by timing; visual check in an interactive terminal pending |
| A saved session can be reloaded and continued | Tests 1 → 2 | PASS |
| Stretch: system prompt and first message pinned when the window slides | Test 3 | PASS |

## Observations
- **Cached tokens:** Bedrock automatically caches the repeated start of the conversation and reports it as `cacheReadInputTokens`, separate from `inputTokens`. Counting only `inputTokens` made the footer look like input was shrinking (299 → 72) while history grew; the footer now counts everything sent and shows the cached part.
- **Reasoning time:** Kimi K3.1 spends most of a long reply's wait on hidden reasoning (about 3,000 reasoning chunks vs about 560 answer chunks in one measured reply). Streaming the answer alone would still leave ~11s of blank screen, hence the `(thinking....)` indicator.
- **Window cost of forgetting:** dropped turns are gone for good (Test 3 lost the order number). This is the problem the challenge says to park until Challenge 9.

## Conclusion
All acceptance criteria and the stretch goal for Challenge 2 passed in the tests above. The one item left is watching the streaming live in an interactive terminal.

---

## Break it using this

Once Challenge 2 is built, run these experiments to expose the shortfalls that Challenge 3 and Challenge 9 will address:

### 1. Break code consumption (Unstructured Prose vs. Machine Data)
- **Action:** Paste five customer emails and ask the model for the order line items. Try to parse or load that answer programmatically into Python. Do it three times and compare the output formats.
- **What to observe:** Free-form prose and markdown tables vary unpredictably each run; downstream code cannot reliably consume them without validation schemas.
- **What fixes it:** Challenge 3 introduces Structured Outputs (JSON Schemas, Pydantic/Zod validation, and automated repair).

### 2. Break context limits (Long Session Forgetting / Amnesia)
- **Action:** Chat interactively for 40 turns, then ask about a detail mentioned back in Turn 2.
- **What to observe:** The sliding window had to drop older turns to stay within token budgets, so the model forgot the initial context.
- **What fixes it:** Challenge 9 introduces Context Engineering, Compaction, and Long-Term Memory.
