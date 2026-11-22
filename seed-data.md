Meridian Supply Co. is a fictional B2B distributor of industrial supplies. You are building Desk, its customer￾operations assistant. Desk starts as a one-line question answerer and ends as a multi-user agent service that
looks up orders, quotes policy, processes refunds with approval, and audits a quarter of orders in parallel.
2 Agentic AI Engineering: 15 Progressive Coding Challenges
Seed data (create once, before Challenge 1)
All synthetic. Generating it with an LLM is fine.
catalog.csv : about 200 products (sku, name, category, unit price, stock, specs). SKUs look like MS-VLV-
0200 .
orders.db (SQLite): about 500 orders (id like MS-10422 , customer, line items, status, dates, carrier,
total). Plant 10 pricing mismatches against the catalog and note where they are. You need them in
Challenge 12.
policies/ : 10 to 15 markdown documents (returns, warranty, shipping, hazardous goods, bulk pricing,
credit terms). Include at least two tables, and make two documents contradict each other with different
effective dates.
emails/ : 30 customer emails (order requests, status questions, complaints, returns). Make a few messy:
multiple intents, products described in words instead of SKUs.