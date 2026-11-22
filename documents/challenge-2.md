# Challenge 2: Conversation — Requirements and Plan

## Overview
- **Goal:** Turn the stateless one-shot tool into an interactive multi-turn conversation with streaming tokens and message history management.
- **Shortfall of Challenge 1:** Every call is stateless (no memory of previous turns) and waits for the full response before displaying anything.

---

## 1. Requirements to Build
1. **Interactive CLI Loop (`desk chat`):**
   - Keeps a running conversation message history.
   - Resends conversation history each turn so the model remembers context.
2. **Streaming Tokens:**
   - Stream tokens directly to the terminal as they are generated using Bedrock's ConverseStream API (`client.converse_stream`).
3. **Session Commands:**
   - `/reset`: Clears conversation history.
   - `/save <name>`: Persists current session history as JSON.
   - `/load <name>`: Reloads a saved session to continue conversation.
4. **Token Management & Sliding Window:**
   - Track tokens per turn and running total.
   - Implement a sliding window: drop oldest turns when history exceeds token limits, keeping system prompt intact.

---

## 2. Test Verification Plan
- [ ] Test follow-up context recall (e.g., "My name is Ravi" followed by "What is my name?").
- [ ] Verify streaming token visual output on terminal.
- [ ] Verify session save and reload (`/save test`, `/load test`).
- [ ] Test sliding window context limits.

---

## Status
Ready for implementation.

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

