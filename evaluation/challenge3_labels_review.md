# Challenge 3 — review the 15 labels

Assistant-drafted annotations. Recorded review status: pending.
Check every label against its source email before approving ground truth.
Read each source, correct the draft JSON and synonyms, then record an actual
reviewer/date and approved status in provenance.human_review after all labels
are checked. Checkboxes here do not automatically approve ground truth.

## EM-002

[Open source email](<C:/Users/suganeshwaran/Desktop/AI Agents/data/emails/EM-002.txt>)

Customer: Alder Packaging LLC.
Intent: other.
Requested date: None; urgency: None.

| SKU | Description | Quantity | Unit |
| --- | --- | ---: | --- |
| MS-VLV0211 | Bronze Check Valve 2 in NPT | 60 | unit |

Ambiguity/review note: No purchase order yet. Shutdown is not an explicit requested calendar date; do not use the email date.

- [ ] Human checked against the source and corrected the draft JSON if needed.

## EM-004

[Open source email](<C:/Users/suganeshwaran/Desktop/AI Agents/data/emails/EM-004.txt>)

Customer: Beacon Water Systems LLC.
Intent: other.
Requested date: None; urgency: None.

| SKU | Description | Quantity | Unit |
| --- | --- | ---: | --- |
| null | blue thread sealing paste, medium cartridge uncertain | null | null |

Ambiguity/review note: Maybe 6 is explicitly unconfirmed; quantity and unit are null. Identification is not an order or stock-status request.

- [ ] Human checked against the source and corrected the draft JSON if needed.

## EM-006

[Open source email](<C:/Users/suganeshwaran/Desktop/AI Agents/data/emails/EM-006.txt>)

Customer: Dunefield Fabrication LLC.
Intent: other.
Requested date: None; urgency: None.

| SKU | Description | Quantity | Unit |
| --- | --- | ---: | --- |
| MS-FST0215 | Socket Cap Screw Box 1/2-13 Zinc plated | 20 | unit |

Ambiguity/review note: The source says 20 units of a box product. Do not replace the requested selling unit with an inferred pack size.

- [ ] Human checked against the source and corrected the draft JSON if needed.

## EM-008

[Open source email](<C:/Users/suganeshwaran/Desktop/AI Agents/data/emails/EM-008.txt>)

Customer: Evercrest Plant Services LLC.
Intent: other.
Requested date: None; urgency: None.

| SKU | Description | Quantity | Unit |
| --- | --- | ---: | --- |
| null | large nitrile work gloves; ten selling units conditional on single-item selling unit | 10 | selling unit |
| null | impact goggles, tentative separate quote line, not full face shields | 4 | null |

Ambiguity/review note: Quantities 10 and 4 are proposed quote quantities, not purchase authorization. Human review must retain the conditional/tentative wording; unit for goggles is absent.

- [ ] Human checked against the source and corrected the draft JSON if needed.

## EM-010

[Open source email](<C:/Users/suganeshwaran/Desktop/AI Agents/data/emails/EM-010.txt>)

Customer: Oakridge Plant Services LLC.
Intent: status.
Requested date: None; urgency: None.

Line items: none identifiable from the email.

Ambiguity/review note: Order number is not a SKU. No products or requested delivery date are supplied.

- [ ] Human checked against the source and corrected the draft JSON if needed.

## EM-012

[Open source email](<C:/Users/suganeshwaran/Desktop/AI Agents/data/emails/EM-012.txt>)

Customer: Northgrove Water Systems LLC.
Intent: status.
Requested date: None; urgency: None.

Line items: none identifiable from the email.

Ambiguity/review note: Receiving appointment context does not specify a requested calendar date. An address-change restriction is not purchase authorization.

- [ ] Human checked against the source and corrected the draft JSON if needed.

## EM-014

[Open source email](<C:/Users/suganeshwaran/Desktop/AI Agents/data/emails/EM-014.txt>)

Customer: Granite Water Systems LLC.
Intent: status.
Requested date: None; urgency: None.

Line items: none identifiable from the email.

Ambiguity/review note: Do not infer SKU or quantity from an order ID. No replacement/payment action is requested; new-purchase authorization is not addressed.

- [ ] Human checked against the source and corrected the draft JSON if needed.

## EM-016

[Open source email](<C:/Users/suganeshwaran/Desktop/AI Agents/data/emails/EM-016.txt>)

Customer: Northgrove Fabrication LLC.
Intent: status.
Requested date: None; urgency: None.

Line items: none identifiable from the email.

Ambiguity/review note: Three distinct information requests. No product identity, quantity, or new purchase instruction.

- [ ] Human checked against the source and corrected the draft JSON if needed.

## EM-017

[Open source email](<C:/Users/suganeshwaran/Desktop/AI Agents/data/emails/EM-017.txt>)

Customer: Oakridge Water Systems LLC.
Intent: other.
Requested date: None; urgency: None.

| SKU | Description | Quantity | Unit |
| --- | --- | ---: | --- |
| MS-VLV0200 | not supplied | null | null |

Ambiguity/review note: Pricing clarification does not assert a proven price error; classify other rather than inventing a complaint/refund. Quantity and selling unit are asked about, not provided.

- [ ] Human checked against the source and corrected the draft JSON if needed.

## EM-019

[Open source email](<C:/Users/suganeshwaran/Desktop/AI Agents/data/emails/EM-019.txt>)

Customer: Evercrest Mechanical LLC.
Intent: complaint.
Requested date: None; urgency: None.

Line items: none identifiable from the email.

Ambiguity/review note: Two complaint topics of the same kind. Missing product and quantity remain absent. No automatic replacement/refund or new purchase is authorized.

- [ ] Human checked against the source and corrected the draft JSON if needed.

## EM-021

[Open source email](<C:/Users/suganeshwaran/Desktop/AI Agents/data/emails/EM-021.txt>)

Customer: Millstone Plant Services LLC.
Intent: complaint.
Requested date: None; urgency: None.

Line items: none identifiable from the email.

Ambiguity/review note: Affected SKU and quantity will be confirmed later, so line_items is empty; do not infer products from the order database.

- [ ] Human checked against the source and corrected the draft JSON if needed.

## EM-023

[Open source email](<C:/Users/suganeshwaran/Desktop/AI Agents/data/emails/EM-023.txt>)

Customer: Oakridge Water Systems LLC.
Intent: return.
Requested date: None; urgency: None.

| SKU | Description | Quantity | Unit |
| --- | --- | ---: | --- |
| null | unopened half-inch brass valve | 1 | unit |

Ambiguity/review note: 2025-08-04 is delivery history and 2025-09-08 is today, neither a requested date. Do not look up policy eligibility or fabricate a SKU.

- [ ] Human checked against the source and corrected the draft JSON if needed.

## EM-025

[Open source email](<C:/Users/suganeshwaran/Desktop/AI Agents/data/emails/EM-025.txt>)

Customer: Juniper Packaging LLC.
Intent: return.
Requested date: None; urgency: None.

| SKU | Description | Quantity | Unit |
| --- | --- | ---: | --- |
| MS-VLV0206 | not supplied | 1 | unit |

Ambiguity/review note: Product name is not supplied. RMA and policy questions are explicit secondary requests, not permission to execute a return.

- [ ] Human checked against the source and corrected the draft JSON if needed.

## EM-027

[Open source email](<C:/Users/suganeshwaran/Desktop/AI Agents/data/emails/EM-027.txt>)

Customer: Alder Mechanical LLC.
Intent: return.
Requested date: None; urgency: None.

Line items: none identifiable from the email.

Ambiguity/review note: Products, count and carton condition are not confirmed. Return is primary under the documented priority policy; replacement-quote workflow remains secondary.

- [ ] Human checked against the source and corrected the draft JSON if needed.

## EM-030

[Open source email](<C:/Users/suganeshwaran/Desktop/AI Agents/data/emails/EM-030.txt>)

Customer: Beacon Mechanical LLC.
Intent: other.
Requested date: None; urgency: None.

| SKU | Description | Quantity | Unit |
| --- | --- | ---: | --- |
| MS-PTL0219 | Reciprocating Saw Extended Runtime 18V kit | 200 | selling unit |

Ambiguity/review note: Pricing question explicitly denies purchase authorization. Quantity 200 is known; do not infer tier, price or discount values.

- [ ] Human checked against the source and corrected the draft JSON if needed.
