# AI sessions

This project was built with **Claude Code** (Anthropic) running in the Claude desktop app.

* `claude-code-session-*.zip` — exported Claude Code session(s) (`transcript.jsonl` inside) of the build session(s): the prompts, the agent's reasoning summaries, every tool call (shell commands, file edits, browser checks) and their results.

How the AI was used is summarised in the main README (§13). Highlights you'll find in the transcript:

* probing the real data sources before designing (Stores API needed GET not POST; Overpass mirrors returning 406/429/504; OGD API timing out → Nominatim fallback);
* the SQLite + H3 decision (no Docker/Postgres on the build machine) and the Windows Application Control workaround for SQLAlchemy;
* calibration passes on the scoring model after sanity-checking known neighbourhoods (T. Nagar, Velachery, Anna Nagar…);
* bugs found by clicking through the UI in a browser and fixed (map container CSS, basemap API key watermark, unbalanced survey splits → segment-level wedges, ground truth picked from the wrong study, deal-breaker scores).
