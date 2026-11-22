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
