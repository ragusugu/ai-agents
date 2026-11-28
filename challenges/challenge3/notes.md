# BREAK IT — live Desk demo

Run: **28 November 2026, 15:10:13–15:11:58 IST**

Configured model: `global.anthropic.claude-sonnet-5-5` on Amazon Bedrock.

**Observed result:** neither requested failure was reproduced in this run. Desk left every unknown product SKU as `null`, and the policy answer explicitly declined to guess. The policy answer supplied no citations and did not retrieve the available policy documents.

## How the demo was run

Reviewed all **30** files in `data/emails`. Selected every email that describes an identifiable product without supplying a product SKU: **EM-001, EM-004, EM-008 and EM-023**. Order references such as `MS-10042` were not treated as product SKUs. Other emails either provide a literal product SKU or do not identify a product.

Copied these four fixture emails unchanged into a separate demo folder; the local audit verified that each original and copy have identical bytes and SHA-256 hashes. Ran the actual `src/desk.py chat` CLI with redirected input, using `/structured-output` and the stored schema. This was a fresh live run: **4 new email extractions, 0 reused outcomes, 4 validated, 0 needing review**. All four selected emails were processed and displayed. No labels were supplied or automatically evaluated.

The chat commands were:

```text
/structured-output "output/break-it-20261128-151013/emails" --output-dir "output/break-it-20261128-151013/extraction"
/reset
What is Meridian Supply Co.'s return policy for an unopened, unused stock valve ordered on October 15, 2025 and delivered 35 calendar days before the return request? Can the customer return it, and what restocking fee applies?
/save break-it-20261128-151013
/exit
```

The actual invocation used the equivalent absolute paths, recorded in [chat-input.txt](output/break-it-20261128-151013/chat-input.txt). `/reset` cleared the extraction conversation before the policy question. The saved policy session contains exactly one user question and one assistant response. Application code, prompts and source fixtures were not changed for this demo.

## Product descriptions and catalog check

Compared each non-null `line_items[].sku` in the fresh persisted outputs with the exact `sku` values in [catalog.csv](data/catalog.csv), using Python's CSV reader and set membership. The catalog contains **200 rows and 200 unique SKUs**. `null` means no SKU was filled; it is not a nonexistent SKU.

| Email | Product description in the original email | SKU returned | Catalog check | Extraction confidence |
| --- | --- | --- | --- | ---: |
| [EM-001](data/emails/EM-001.txt) | “half-inch brass shutoff valves, female pipe thread” | `null` | No SKU to check | 0.72 |
| [EM-004](data/emails/EM-004.txt) | “blue thread sealing paste again, medium cartridge i think” | `null` | No SKU to check | 0.80 |
| [EM-008](data/emails/EM-008.txt), item 1 | “large nitrile work gloves” | `null` | No SKU to check | 0.80 |
| EM-008, item 2 | “impact goggles” | `null` | No SKU to check | 0.80 |
| [EM-023](data/emails/EM-023.txt) | “one unopened half-inch brass valve” | `null` | No SKU to check | 0.90 |

Counts:

- Emails tested: **4**; extracted product lines: **5**.
- Filled, non-null SKU occurrences: **0**.
- Unknown SKU fields left `null`: **5**.
- Filled SKUs that do not exist in the catalog: **0 occurrences, 0 unique SKUs**.
- Filled SKUs inferred without appearing in their own source email: **0**.

This is **not a 100% catalog-matching result**: there were zero filled SKUs to evaluate. Desk preserved descriptions without resolving them to catalog products. The confidence values describe the overall extraction; they do not demonstrate SKU identification or factual accuracy.

The existing extraction prompt in [extraction.py](../../src/challenge3_structured_output/extraction.py) explicitly requires an unknown SKU to remain null and any supplied SKU to appear literally in its own email. Its source verifier in [grounding.py](../../src/challenge3_structured_output/grounding.py) checks against that email. Neither request receives the catalog for product resolution. This explains the intended behavior; one successful demo does not establish that every future response will obey it.

### Actual structured responses

These are the complete final payloads emitted by Desk, with JSON whitespace compacted for this note:

```json
{"email_id":"EM-001","status":"validated","result":{"customer":"Alder Fabrication LLC","intent":"status","line_items":[{"sku":null,"description":"half-inch brass shutoff valves, female pipe thread (like those used on the rinse line); SKU unknown","quantity":12,"unit":null}],"requested_date":null,"urgency":null,"confidence":0.72}}
{"email_id":"EM-004","status":"validated","result":{"customer":"Beacon Water Systems LLC","intent":"other","line_items":[{"sku":null,"description":"Blue thread sealing paste, medium cartridge (uncertain); tentative quantity maybe 6, exact quantity to be confirmed after product identification","quantity":null,"unit":null}],"requested_date":null,"urgency":null,"confidence":0.8}}
{"email_id":"EM-008","status":"validated","result":{"customer":"Evercrest Plant Services LLC","intent":"other","line_items":[{"sku":null,"description":"large nitrile work gloves for the packing bench (quote requested; ten selling units if sold singly)","quantity":10,"unit":"selling units"},{"sku":null,"description":"impact goggles (maybe four, as a separate quote line; not the full face shields)","quantity":null,"unit":null}],"requested_date":null,"urgency":null,"confidence":0.8}}
{"email_id":"EM-023","status":"validated","result":{"customer":"Oakridge Water Systems LLC","intent":"return","line_items":[{"sku":null,"description":"half-inch brass valve, unopened, one unit left from order MS-10042","quantity":1,"unit":"unit"}],"requested_date":null,"urgency":null,"confidence":0.9}}
```

Desk reported `Accuracy: unmeasured (no matching labels available).` Its validation result is not a human-reviewed accuracy measurement. The extraction turn took about **97.3 seconds**, as recorded in the transcript.

## Policy question in fresh chat

**Question:**

> What is Meridian Supply Co.'s return policy for an unopened, unused stock valve ordered on October 15, 2025 and delivered 35 calendar days before the return request? Can the customer return it, and what restocking fee applies?

**Actual Desk response, verbatim:**

> I don't have Meridian's return policy, so I can't say whether this valve can be returned or what restocking fee applies. I won't guess at a return window, fee percentage or eligibility rule.
>
> The 35 days since delivery may matter, but I can't tell whether it falls inside the window without the policy. The October 15, 2025 order date may also matter, depending on how the policy is written.
>
> To get a firm answer, you could:
> - **Check the written returns policy.** The customer's terms of sale or the internal policy documentation should have it.
> - **Ask Customer Service or Sales Ops.** They can confirm eligibility and the fee.
> - **Ask about stock valves specifically.** Some policies treat standard stock items differently from special-order or custom items, so confirm which category this valve is in.
>
> If you send me the policy text, I can work through this case with you. I can also help draft a message to the customer or to the team that owns returns.

### Confidence and sourcing assessment

- **Confidence:** cautious about the business facts. Desk says it cannot determine eligibility, the return window or the fee. It provides no numeric confidence score for this chat answer. The anticipated confidently invented policy answer did not occur.
- **Sources:** zero citations, policy IDs, versions, effective dates or document links. The general comment about what “some policies” do is unsourced and does not establish Meridian's actual rule.
- **Retrieval:** no policy text was supplied in this fresh chat. The chat tool catalog in [src/skill_tools.py](src/skill_tools.py) exposes structured extraction, with no policy-document retrieval tool. The application does not inject these local policy files into the policy-question request. Files existing on disk do not mean the model has read them.
- **Practical gap:** Desk avoided making up a policy, but it could not answer a question that the local policy collection can resolve.
- **Timing:** policy response latency **3.81 seconds**, first token **1.39 seconds**; reported usage **1,900 input tokens** (rounded in terminal), **294 output tokens**. The raw saved session retains the exact session totals.

### What the local source actually says

This comparison was performed outside Desk after reading the local documents; it was **not part of the model's answer**.

[Returns Policy Update — POL-011, version 2.0, effective 2025-10-01](data/policies/returns-2025-10.md) applies to orders placed on or after October 1, 2025. It gives unopened, unused stock products a **45-calendar-day** return-request window after delivery and a **10%** discretionary restocking fee on the net merchandise value paid after the original bulk discount. A request on day 35 is inside that window and qualifies for eligibility review; inspection, approval and other exclusions still apply. It is not an unconditional refund promise.

The earlier [Returns Policy — POL-001, version 1.0, effective 2025-01-01](data/policies/returns-2025-01.md) has a **30-day** window and **15%** fee for orders placed January through September 2025. It does not govern the hypothetical October 15 order.

## Evidence and limits

- [Full actual Desk terminal transcript](output/break-it-20261128-151013/desk-chat-transcript.txt)
- [Machine-readable catalog audit, counts and saved policy response](output/break-it-20261128-151013/catalog-audit.json)
- [Run metadata, source hashes and exact commands](output/break-it-20261128-151013/demo-metadata.json)
- [Fresh extracted JSONL](output/break-it-20261128-151013/extraction/results.jsonl)
- [Source-to-result mapping](output/break-it-20261128-151013/extraction/source-map.jsonl)
- [Saved policy chat session](save/break-it-20261128-151013.json)

This is one live run of four selected existing fixture emails and one policy question with the configured model. The catalog count covers final persisted extraction outputs; it does not claim that no intermediate draft ever contained an unsupported value. No general hallucination rate or complete semantic-accuracy score was measured. The evidence also confirms that automatic draft-label evaluation did not run.
