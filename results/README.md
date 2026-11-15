# Results

Each folder holds the scored output of one set of runs: `evaluation.json` and `evaluation.md` from `benchmark/evaluate.py`, and the summary each run command wrote (settings, statuses, token usage, estimated cost). These files hold counts only.

Run files and prompt logs are not stored here because they contain SAP text whose redistribution status is unverified. Each run file records its settings and the fingerprint of the code that produced it.

| Folder | What ran |
| --- | --- |
| `development-2026-11-15/` | The agent, the general-purpose LLM, and keyword search on the three development families. First runs against the live API. |
