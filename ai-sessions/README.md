# AI sessions

This project was built with Claude Code (Anthropic) in the Claude desktop app.

`claude-code-session-1.zip` is the exported session. Open `transcript.jsonl` inside it to see every prompt I gave, Claude's replies, and each tool call it made (shell commands, file edits, browser checks) along with the results.

Section 11 of the main README summarises the conversation prompt by prompt. Some moments worth looking at in the transcript:

- testing the real data sources before designing anything: the Stores API rejected POST, Overpass servers kept returning 429/504, and the OGD pincode API timed out, so pincodes fall back to Nominatim;
- choosing SQLite + H3 because Docker and Postgres weren't available, and working around Windows blocking one of SQLAlchemy's compiled files;
- sanity-checking scores for well-known areas (T. Nagar, Velachery, Anna Nagar) and adjusting the model;
- bugs found by clicking through the app and fixed: the map not showing, a basemap that needed an API key, uneven survey splits, a property matched to the wrong survey, and mobile layouts spilling off the screen.
