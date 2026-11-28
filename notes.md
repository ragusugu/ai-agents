# BREAK IT — Challenge 4 Naive RAG

Run: **28 November 2026, 18:32:00–18:33:29 IST**. Existing answer model: `global.anthropic.claude-sonnet-5-5`.

[challenge4.md](challenges/challenge4/challenge4.md) owns Build/Done When/Stretch, stages and demos. This notebook records every original Break It experiment, expected versus actual results and learning observations. API answers below are actual captures; the retrieval baseline used genuine local BGE embeddings and the persisted policy index. Sources were unchanged.

## 1. Exact SKU: MS-VLV-0200

Question:

```text
What are the specifications and stock availability of SKU MS-VLV-0200?
```

Actual answer:

```text
not in the documents
```

**Expected/observed:** the index covers policies, not the catalog; no policy contains this exact SKU. Dense retrieval still returned approximate policy matches, but the API refused to invent specifications/stock. Refusal PASS for this run; exact-SKU lookup itself is not demonstrated.

Retrieved IDs: `bulk-pricing.md#1`, `warranty.md#1`, `damaged-goods.md#1`, `price-adjustments-and-refunds.md#1`. Capture: [exact-sku.txt](.desk/challenge4-verification/20261128T130200Z/exact-sku.txt).

## 2. Answer inside a Markdown table

Question:

```text
What bulk discount applies to 250 selling units of one SKU?
```

Actual answer:

```text
A quantity of 250 selling units of one SKU falls in the 200-499 tier, which has a 10% base discount [bulk-pricing.md#1]. The discount applies per order line, using the quantity of that SKU in its selling unit [bulk-pricing.md#1].
```

**Expected:** 250 selling units falls in the 200–499 tier, giving a 10% per-line base discount. **Observed:** correct tier/value and `bulk-pricing.md#1` citation. PASS. Original Markdown table text reached the context; this example does not establish success for every table/window boundary.

## 3. Two policy versions disagree

Question:

```text
How do the January and October 2025 returns policies differ in return window and restocking fee?
```

Actual answer:

```text
**Return window**
- The January policy (Returns Policy, POL-001, v1.0, effective 2025-01-01) allows returns within 30 calendar days after delivery. It applies to orders placed January 1 through September 30, 2025 [returns-2025-01.md#1].
- The October policy (Returns Policy Update, POL-011, v2.0, effective 2025-10-01) allows returns within 45 calendar days after delivery. It applies to orders placed on or after October 1, 2025 [returns-2025-10.md#1].

**Restocking fee** (for discretionary returns of conforming goods)
- January: 15% [returns-2025-01.md#1].
- October: 10% [returns-2025-10.md#1].

In both versions, the fee is calculated on the net merchandise value paid for the returned quantity after the original bulk discount [returns-2025-01.md#1][returns-2025-10.md#1].

**Which version applies:** The order placement date selects the version, and delivery starts the clock. An earlier order is assessed under the version in force on its order date, even if delivery or the return request happens after October 1 [returns-2025-10.md#1].
```

**Expected:** January has 30 days / 15% discretionary restocking; October has 45 days / 10%, with order-placement date selecting the version. **Observed:** both versions compared and correctly cited. PASS for this comparison. The apparent contradiction is conditional on order date, not grounds to discard the older document automatically.

**Retrieval weakness:** the separate post-October-order question ranked `returns-2025-01.md#1` first, then `returns-2025-10.md#1`. Top four recovered the correct version and the live answer used it, but rank one alone would favor the older policy. No application-level version filter was added.

## 4. Vague follow-up in real Desk chat

Previous user question:

```text
/ask For orders placed after October 1, 2025, what is the unopened stock return window and restocking fee? --debug
```

Follow-up:

```text
/ask what about for bulk? --debug
```

Actual assistant response:

```text
Assuming you're asking about bulk pricing, the policy is Bulk Pricing (POL-005), version 1.0, effective 2025-01-01 [bulk-pricing.md#1].

- Discounts apply separately to each order line, based on the quantity of that SKU in its selling unit. Unrelated SKUs and multiple orders can't be combined to reach a tier [bulk-pricing.md#1].
- Tiers for one SKU [bulk-pricing.md#1]:
  - 1-49: 0%
  - 50-199: 5%
  - 200-499: 10%
  - 500 or more: 15%
- Line total is quantity × charged base unit price × (1 − discount % / 100), rounded once at the end of the line to two decimals, half-up [bulk-pricing.md#1].
- A box counts as one selling unit, even if it contains one hundred fasteners [bulk-pricing.md#1].
- Quotes expire after thirty calendar days, and no quote reserves inventory until an order is accepted [bulk-pricing.md#1].

If you meant bulk in another context, such as returns or shipping, please say which.
```

**Expected if conversational intent were preserved:** resolve bulk in the preceding returns context, or clarify. **Observed:** Desk assumed bulk pricing, returned its tiers and only then invited clarification. Pricing facts were cited, but intent was not preserved. **Limitation reproduced / context continuity FAIL.**

Cause: `/ask` retrieval and answering receive only the raw latest question and fetched context, without earlier chat messages or a rewritten question. History remains saved for ordinary chat. This observation is for later learning; no Challenge 5 rewriting/hybrid search/reranking was implemented.

Full terminal capture: [chat.txt](.desk/challenge4-verification/20261128T130200Z/chat.txt). The saved session has four messages (two user/assistant exchanges); save/exit made no model calls.

## 5. Honest numeric retrieval baseline

**Hit@4 = 10/10 (100%)** on ten assistant-defined answerable topic questions over ten policy documents / fifteen chunks. All expected sources were present, including both returns versions in the comparison. This is a small diagnostic set, not human-certified ground truth, production accuracy, answer accuracy or proof of correct first-rank/version selection. Out-of-scope and vague queries are excluded from this answerable-source denominator and discussed above.

| Question | Expected sources | Actual top four IDs | Hit@4 |
| --- | --- | --- | --- |
| For orders placed after October 1, 2025, what is the unopened stock return window and restocking fee? | `returns-2025-10.md` | `returns-2025-01.md#1`, `returns-2025-10.md#1`, `price-adjustments-and-refunds.md#1`, `order-cancellation.md#1` | 1 |
| How do January and October 2025 return policies differ in window and restocking fee? | `returns-2025-01.md`, `returns-2025-10.md` | `returns-2025-01.md#1`, `returns-2025-10.md#1`, `price-adjustments-and-refunds.md#1`, `bulk-pricing.md#1` | 1 |
| What bulk discount applies to a line of 250 selling units of one SKU? | `bulk-pricing.md` | `bulk-pricing.md#1`, `price-adjustments-and-refunds.md#1`, `credit-terms.md#1`, `order-cancellation.md#1` | 1 |
| Which standard carriers, transit times and below-threshold shipping rates are listed? | `shipping.md` | `shipping.md#1`, `bulk-pricing.md#1`, `damaged-goods.md#1`, `hazardous-goods.md#1` | 1 |
| Who can raise a credit limit and what does Net 30 mean? | `credit-terms.md` | `credit-terms.md#1`, `price-adjustments-and-refunds.md#1`, `bulk-pricing.md#1`, `hazardous-goods.md#2` | 1 |
| How long is the limited warranty for stock tools and what manufacturing defects does it cover? | `warranty.md` | `warranty.md#1`, `returns-2025-10.md#1`, `returns-2025-01.md#1`, `damaged-goods.md#1` | 1 |
| How soon must visible transit damage or a short shipment be reported? | `damaged-goods.md` | `damaged-goods.md#1`, `shipping.md#1`, `hazardous-goods.md#1`, `price-adjustments-and-refunds.md#2` | 1 |
| Can opened hazardous chemicals be returned or shipped by USPS? | `hazardous-goods.md` | `hazardous-goods.md#1`, `returns-2025-01.md#1`, `returns-2025-10.md#1`, `damaged-goods.md#1` | 1 |
| Can a delivered order be cancelled and is there a cancellation fee before dispatch? | `order-cancellation.md` | `order-cancellation.md#1`, `price-adjustments-and-refunds.md#1`, `shipping.md#1`, `credit-terms.md#1` | 1 |
| Who must approve a refund over $500 and does a one-dollar refund need approval? | `price-adjustments-and-refunds.md` | `price-adjustments-and-refunds.md#1`, `credit-terms.md#1`, `returns-2025-10.md#1`, `returns-2025-01.md#1` | 1 |

The assistant wrote these straightforward questions after reading the policies; no independent human label review occurred. Queries/IDs/unrounded scores/provenance: [report.json](.desk/challenge4-verification/20261128T130200Z/report.json). A perfect small-set result or one lookup does not establish general semantic accuracy.

## Learning observations

- Correct vector shape and citation IDs establish plumbing, not per-claim entailment. A test intentionally shows that a false claim with an allowed citation passes the format guard.
- Top-four retrieval recovered both dated policies, while rank one favored the wrong version for a post-October query. Read source conditions; similarity is not authority/confidence.
- The SKU experiment exposes corpus coverage: a policy index cannot supply catalog specifications just because a token looks like a SKU.
- The complete tier table worked; fixed windows can still separate headers/rows/conditions elsewhere.
- Raw latest-turn retrieval lost follow-up intent. Recording the failure is part of the challenge; silently adding future-challenge features would hide it.

All policy byte hashes matched before/after verification. No email batch, verifier redesign, model/credential switch or future-challenge implementation occurred.


## Streaming recheck

**28 November 2026, 19:27:40–19:28:58 IST.** These are the original BREAK IT experiments rechecked against the current streaming implementation. Earlier observations above are retained. General Build/Done/Stretch demos remain only in [challenge4.md](challenges/challenge4/challenge4.md).

The exact single-question argv was executed by the real Desk CLI dispatcher with genuine existing-provider I/O; equivalent launcher input is shown for typing. Answers below are copied verbatim from the captured result. The vague follow-up ran in an actual Desk chat subprocess.

### Exact SKU MS-VLV-0200

Input:

```powershell
.\desk.cmd ask "What are the specifications and stock availability of SKU MS-VLV-0200?" --debug
```

Actual answer:

```text
not in the documents
```

[Full actual capture](.desk/challenge4-verification/20261128T135740Z/exact-sku.txt).

### Answer in a table

Input:

```powershell
.\desk.cmd ask "What bulk discount applies to 250 selling units of one SKU?" --debug
```

Actual answer:

```text
A quantity of 250 selling units of one SKU falls in the 200-499 tier, which has a 10% base discount [bulk-pricing.md#1]. The discount applies separately to each order line, using the quantity of that SKU in its selling unit [bulk-pricing.md#1].

This is from Bulk Pricing (POL-005), Version 1.0, effective 2025-01-01 [bulk-pricing.md#1].
```

[Full actual capture](.desk/challenge4-verification/20261128T135740Z/table.txt).

### Two dated policies disagree

Input:

```powershell
.\desk.cmd ask "How do the January and October 2025 returns policies differ in return window and restocking fee?" --debug
```

Actual answer:

```text
**Return window**
- January policy (POL-001, v1.0, effective 2025-01-01): 30 calendar days after delivery. It applies to orders placed January 1 through September 30, 2025 [returns-2025-01.md#1].
- October policy (POL-011, v2.0, effective 2025-10-01): 45 calendar days after delivery. It applies to orders placed on or after October 1, 2025 [returns-2025-10.md#1].

**Restocking fee** (for a discretionary return of conforming goods)
- January policy: 15% [returns-2025-01.md#1].
- October policy: 10% [returns-2025-10.md#1].

**Same in both versions:** The order placement date selects the version, and delivery starts the clock [returns-2025-01.md#1][returns-2025-10.md#1]. The fee is calculated on the net merchandise value paid for the returned quantity after the original bulk discount [returns-2025-01.md#1][returns-2025-10.md#1].

**Day-limit handling:**
- January policy: requests received on day 30 are inside the window [returns-2025-01.md#1].
- October policy: requests on day 45 qualify for review, and a request on day 46 requires an exception decision [returns-2025-10.md#1].
```

[Full actual capture](.desk/challenge4-verification/20261128T135740Z/conflict.txt).

### Vague follow-up

Actual chat inputs in order:

```text
/ask For orders placed after October 1, 2025, what is the unopened stock return window and restocking fee? --debug
/ask what about for bulk? --debug
```

Actual follow-up response:

```text
Assuming you're asking about bulk pricing, here is what Meridian's Bulk Pricing policy (POL-005, version 1.0, effective 2025-01-01) says [bulk-pricing.md#1]:

- Discounts apply separately to each order line, based on the quantity of that SKU in its selling unit. Unrelated SKUs and multiple orders can't be combined to reach a tier [bulk-pricing.md#1].
- A box counts as one selling unit, even if it contains one hundred fasteners [bulk-pricing.md#1].
- Discount tiers per SKU [bulk-pricing.md#1]:
  - 1-49: 0%
  - 50-199: 5%
  - 200-499: 10%
  - 500 or more: 15%
- Line total is quantity × charged base unit price × (1 − discount % ÷ 100). It is rounded once at the end of the line to two decimals, half-up [bulk-pricing.md#1].
- A return uses the original line discount and does not reprice the other units on the original order [bulk-pricing.md#1].
- Quotes expire after thirty calendar days, and no quote reserves inventory until an order is accepted [bulk-pricing.md#1].

If you meant something else by "bulk", such as shipping or returns, please say so. The supplied documents don't address that.
```

**Observed limitation:** the answer again assumed bulk pricing after a returns question. Context continuity FAIL; its invitation to clarify came after the assumed topic answer. Its final statement about what the supplied documents do not address is not a certified global-corpus fact. Citation formatting cannot prove such an absence claim. No rewriting/version filtering/hybrid retrieval was introduced to hide this result. [Actual chat capture](.desk/challenge4-verification/20261128T135740Z/chat.txt).

### Retrieval number

Current genuine local retrieval **hit@4 = 10/10 (100%)** on the same ten assistant-defined answerable topic questions. Both dated returns documents were present, but the post-October question still ranked the January policy first. This is a small diagnostic source-hit rate, not human-certified labels, general answer accuracy or guaranteed first-rank correctness. The original question/expected-source table above remains the benchmark definition. [Current queries, IDs and unrounded scores](.desk/challenge4-verification/20261128T135740Z/report.json).
