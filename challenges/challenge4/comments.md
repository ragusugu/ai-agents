Terminal (PowerShell)

```powershell
.\desk.cmd ingest "data\policies"
.\desk.cmd ingest --source "data\policies\returns-2025-10.md"
.\desk.cmd ask "For orders placed after October 1, 2025, what is the unopened stock return window and restocking fee?" --debug
.\desk.cmd ask "What is the favorite color of the CEO of Meridian Supply Co.?"
.\desk.cmd ask "What bulk discount applies to 250 selling units of one SKU?" --debug
.\desk.cmd ask "How do the January and October 2025 returns policies differ in return window and restocking fee?"
.\desk.cmd ask "Say hello." --no-rag
.\desk.cmd chat
```

Desk chat

```text
/ingest "data\policies"
/ingest "data\policies\returns-2025-10.md"
/ask For orders placed after October 1, 2025, what is the unopened stock return window and restocking fee? --debug
/ask what about for bulk? --debug
/exit
```
