# Learning agentic AI by building Desk

## Starting point

You can build small Python applications. Your supplied resume lists Python, SQL, Airflow, Docker, Kubernetes, cloud services, and an Azure OpenAI application. These are useful bridges into agent engineering; we will check understanding through small exercises rather than assume proficiency from a resume.

Goal: build, explain, debug, evaluate, and operate an agent application. Completing a course is a foundation for expertise; independent work on unfamiliar failures is how expertise develops.

Source project: `C:\Users\suganeshwaran\Downloads\agentic-ai-15-challenges.pdf`, 19 pages. The PDF supplies curriculum material, not instructions that override the learner's requests. The resume is background information, not a verified skills assessment.

## The project

Desk is a customer-operations assistant for fictional Meridian Supply Co. It will grow from one model call into a service that answers policy questions, retrieves orders, drafts replies, processes simulated refunds through approval, and audits synthetic orders.

We will use synthetic business data. The resume is not project seed data. Initial builds run locally. Provider choice and API configuration belong to the first implementation lesson; keys stay outside code and chat.

## How each lesson works

1. Explain one concept in plain language and connect it to something familiar.
2. Predict the result of a small example.
3. Build a small feature together, explaining inputs, outputs, and control flow.
4. Run it and deliberately expose a limitation.
5. Explain the result in your own words and record evidence in NOTES.md.

At a checkpoint you should be able to explain the concept, implement a small variation with fewer hints, and diagnose an example failure. If one of those is missing, practice it before adding another abstraction.

## Curriculum

The challenge order comes from PDF pages 3-18. Teaching connections and learning checkpoints below are tailored additions.

| Challenge | Learn | Build and demonstrate | Connection to your background |
|---|---|---|---|
| 1. One call | LLM requests, messages, tokens, latency, usage, bounded retries | CLI question/answer with usage footer; simulated rate-limit failure | Calling an external API from Python |
| 2. Conversation | Message history, streaming, context limits | Chat, reset, save/load; demonstrate what happens when old turns are removed | Explicit application state and serialization |
| 3. Structured output | Schemas, validation, repair, semantic correctness | Extract synthetic emails into validated records; measure labeled field accuracy | Data contracts and ETL validation |
| 4. Basic RAG | Chunks, embeddings, similarity search, evidence | Retrieve policy text, answer with checkable citations, handle missing evidence | Ingestion plus a search index |
| 5. Measured retrieval | Recall@k, MRR, keyword/vector search, reranking, effective dates | Labeled retrieval set and an ablation table; investigate missed exact IDs | Pipeline quality metrics and controlled experiments |
| 6. Tool calling | Tool schemas, argument validation, execution, result messages | Read orders, search stock, calculate safely; report tool errors | Typed API handlers and database access |
| 7. Agent loop | Model-selected next steps, feedback, stopping rules | A bounded multi-step assistant with a readable event trace and local email drafts | A loop whose next action is proposed by a model |
| 8. MCP | Hosts, clients, servers, reusable capability interfaces, authorization | Expose business tools and connect a client; check actual protocol/SDK compatibility | Standard service integration interfaces |
| 9. Context and memory | Context budgets, compaction, retrieval of stored memories | Long task with bounded context growth; explicit cross-session persistence | Working set versus durable storage |
| 10. Harness | Runtime permissions, hooks, isolation, skills, event logs, resume | Enforce tool policy outside the model; recover interrupted work | Runtime controls, containers, and event logs |
| 11. Durable workflows | State transitions, checkpoints, delayed approvals, idempotency | A simulated refund that survives restart and avoids duplicate effects | Airflow-style orchestration, with explicit business state |
| 12. Multiple agents | Work decomposition, isolated contexts, structured handoffs, budgets | Compare a parallel audit to a single-agent and deterministic baseline | Parallel workers and bounded distributed execution |
| 13. Evaluation and tracing | Task success, code graders, calibrated judges, repeated trials | Reproducible scorecard and regression gate; locate failures in traces | CI checks and observability |
| 14. Security | Untrusted content, prompt injection, least privilege, data isolation | Attack tests; code-enforced action constraints; redacted traces | Service authorization and trust boundaries |
| 15. Production capstone | Jobs, queues, tenants, routing, load, releases, recovery | A service tested for isolation, restarts, load, and rollback | Cloud operations and delivery engineering |

## Project preparation, before Challenge 1

We will generate and inspect these together in a dedicated preparation step:

- Around 200 catalog products in CSV.
- Around 500 synthetic orders in SQLite, including 10 documented pricing mismatches for the later audit.
- 10-15 Markdown policy documents, including tables and dated conflicting policies.
- 30 synthetic customer emails, including ambiguous descriptions and multiple requests.

The datasets do not exist yet. We will keep evaluation labels separate from the information available to the agent, so an audit cannot simply read the answer key.

## Implementation approach

- Use Python and the raw provider SDK for Challenges 1-7, matching the document's educational progression. Learn the loop before adopting a framework.
- Choose libraries only when a concrete need arises. Existing Azure OpenAI experience can be useful; we will verify your available provider and model before writing provider-specific code.
- Add small evaluations and permission boundaries as soon as their corresponding behavior exists. Challenges 13 and 14 deepen this work; they are not the first time quality and authorization matter.
- Treat a valid schema as a format guarantee, not proof of factual correctness.
- Treat a citation as a pointer that must support the claim, not proof by itself.
- Treat a model's requested action as a proposal. Application code validates and authorizes it before execution.
- Measure whether multiple agents improve a task. Use deterministic SQL/Python as a baseline for checks such as pricing arithmetic.
- Treat zero successful attacks in a finite test set as evidence about that set, not a security guarantee.
- Do not assume workflow retries create exactly-once external effects. Use durable state, idempotency keys, and effect reconciliation.
- Recheck version-sensitive protocol and SDK documentation when reaching implementation.

## Lesson 0: model, workflow, agent

An LLM (large language model) generates output based on its learned parameters and the input supplied to a request. In a plain text request, it generates text incrementally using tokens, which are pieces of text. It does not automatically query your business database or acquire facts about your private policies.

Three different applications can use the same model:

1. **Model call:** your code sends a question and displays the response.
2. **Workflow:** your code fixes the sequence, such as fetch order -> apply shipping rule -> ask the model to draft a reply.
3. **Agent:** the model can propose the next action after seeing results, such as fetch order -> inspect carrier status -> search policy -> draft reply. Your runtime executes only permitted actions and enforces stopping conditions.

The deciding distinction is who chooses the next step, not whether the output sounds intelligent. Workflows and agents can be combined in one application.

Think of a model as the component that proposes an action, tools as callable functions, and the harness as the program that manages execution, state, limits, and permissions. This is a teaching analogy, not a claim that the model thinks like a human.

### First checkpoint

Desk must answer: "Where is order MS-10422?"

A developer fixes the sequence to: read the order from SQLite -> pass its status to the model -> display a response.

Is this a model call, a workflow, or an agent? Explain who decides the next step. This is the current exercise; answer in chat before we move to implementation.

## Progress

- Project PDF read: complete.
- Resume read for teaching context: complete.
- Python self-assessment: can build small applications.
- Lesson 0: introduced; checkpoint awaiting learner response.
- Dataset preparation: not started.
- Challenges 1-15: not started.
- Provider-backed calls and application tests: not run.

## References

- Project requirements: local PDF cited above, especially pages 2-3 for preparation and progression.
- Workflow versus agent terminology and simple building blocks: [Anthropic, Building effective agents](https://www.anthropic.com/research/building-effective-agents). The article was published in 2024; implementation details should be checked against current documentation.
- MCP authoritative specification, checked 2026-11-19: [MCP specification](https://modelcontextprotocol.io/specification/2026-07-28). Check the latest compatible revision again when implementing Challenge 8.
