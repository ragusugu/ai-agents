# Challenge 1: One Call — Test Results and Documentation

## Overview
- **Goal:** Single LLM question/answer CLI tool without any high-level agent frameworks.
- **CLI Command:** `desk ask "your question"` or `python desk.py ask "your question"`
- **Model Used:** `us.moonshotai.kimi-k3.1` via Amazon Bedrock (Converse API).
- **Credentials:** Automatically loaded from `.env` or standard AWS credential chain (`~/.aws/credentials`).

---

## 1. Requirements Implemented in `desk.py`
1. **Single Request CLI:** Sends user question along with Meridian Supply Co. system prompt.
2. **Environment Variables:** Credentials and model ID dynamically loaded (no hardcoded secrets).
3. **Usage Footer:** Displays model ID, input tokens, output tokens, latency (in seconds), and estimated cost.
4. **Retry & Exponential Backoff:** On network timeout or 429 Throttling, automatically retries up to 3 times with backoff (`1s * 2^(attempt-1) + jitter`).
5. **Stretch Features:** Added `--model` and `--temperature` arguments.
6. **Local Wrapper:** `desk.cmd` for convenient Windows terminal execution.

---

## 2. Test Verification & Actual Observed Outputs

### Test 1: General Question & Sensible Answer
**Command:**
```powershell
.venv\Scripts\python.exe desk.py ask "What is a ball valve?"
```
**Output:**
```text
A **ball valve** is a quarter-turn valve that controls fluid flow using a rotating ball with a hole, or bore, through its center.

- Open: The bore aligns with the pipe, allowing flow.
- Closed: A 90° turn places the solid side of the ball across the flow path, stopping it.

Ball valves provide fast operation, reliable shutoff, durability, and relatively low flow restriction. They’re commonly used for water, air, oil, and other industrial fluids when suitably rated. Standard designs are best for on/off service, while specialized V-port ball valves can be used for flow throttling.

--
model: us.moonshotai.kimi-k3.1 | in: 143 tok | out: 460 tok | latency: 3.65s | cost: n/a (set DESK_PRICE_IN / DESK_PRICE_OUT, USD per 1M tokens)
```
- **Status:** PASS (Sensible response and footer present).

---

### Test 2: Usage Footer Verification
- **Model:** `us.moonshotai.kimi-k3.1`
- **Input Tokens:** 143 tokens
- **Output Tokens:** 460 tokens
- **Latency:** 3.65s
- **Cost:** Displays `n/a` when pricing env vars are omitted; properly formatted when set.
- **Status:** PASS.

---

### Test 3: Forced Rate Limit / 429 Retry Test
**Command:**
```powershell
$env:DESK_SIMULATE="429"; .venv\Scripts\python.exe desk.py ask "Testing retry logic"
```
**Output:**
```text
[attempt 1/3 failed: ThrottlingException: Simulated 429: too many requests; retrying in 1.2s]
[attempt 2/3 failed: ThrottlingException: Simulated 429: too many requests; retrying in 2.0s]
desk: Giving up after 3 attempts. Last error: ThrottlingException: Simulated 429: too many requests. Check your network and AWS credentials, or wait a minute if you are being rate limited.
```
- **Status:** PASS (Exponential backoff executed cleanly, exited with clear message without crashing).

---

## Conclusion
All acceptance criteria for Challenge 1 have been verified and passed.

---

## Break it using this

Run these exact commands in your terminal to see the limitations of Challenge 1 in action:

### 1. Break memory (Exposing Statelessness)
```bash
desk ask "My name is Ravi"
desk ask "What is my name?"
```
- **What to observe:** The model in the second call will state that it does not know your name because the API calls are completely isolated and stateless.
- **What fixes it:** Challenge 2 introduces conversation history.

### 2. Break responsiveness (Exposing Lack of Streaming)
```bash
desk ask "Please explain in extensive detail the complete differences between gate valves, ball valves, globe valves, and butterfly valves, including their mechanical design, internal flow dynamics, pressure drop characteristics, sealing mechanisms, maintenance requirements, and typical industrial application scenarios."
```
- **What to observe:** The terminal remains completely blank and unresponsive for **~20.6 seconds** while the model generates tokens in the background, only printing the text after the entire completion arrives.
- **What fixes it:** Challenge 2 introduces live token streaming to the terminal.

### 3. Break company knowledge (Exposing Lack of RAG / Policy Hallucination)
```bash
desk ask "What is Meridian's return window for opened items?"
```
- **What to observe:** Since the model has no access to Meridian Supply Co.'s private internal policy documents, it will either guess/hallucinate a fictional policy or state it doesn't know.
- **What fixes it:** Challenge 4 introduces RAG (Retrieval-Augmented Generation).

