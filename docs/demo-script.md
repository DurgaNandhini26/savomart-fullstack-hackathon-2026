# 5-minute demo script

Setup: `python -m scripts.bootstrap --fresh`, then run the API and `npm run dev`. Use a desktop browser for the managers and the browser's device toolbar (iPhone size) for the executives. The login page's one-tap persona cards make switching instant.

| Time | Persona | Show | Say |
|---|---|---|---|
| 0:00 | — | Login page | "SiteScout covers Savomart's expansion loop — area → property → catchment — for four teams. Built with FastAPI, React, SQLite + H3 and OpenStreetMap data for Chennai." |
| 0:20 | **Priya** (BD Mgr) | Home → **Explore**: opportunity layer, Savomart stores (yellow S) | "Every populated neighbourhood of Chennai is pre-scored from public data. Here are the un-scouted pockets." |
| 0:45 | Priya | Search **Velachery** (or tap hexes in *Grid cells*) → *Run virtual analysis* | "The analysis runs as a background job — you see each step, and it survives a reload or a failure." |
| 1:05 | Priya | Report: score ring, confidence, **How the score was reached** (formula), indicators + sources, hotspots map | "Each pillar is a percentile against the city; the formula and every source are on the page. The AI only writes the explanation, and every number it writes is checked against the data — otherwise we fall back to a template." |
| 1:35 | Priya | Hotspot #1 → **Send an executive** | "Hotspots come with reasons; one click turns one into a mission." |
| 1:50 | **Arun** (phone) | Missions → mission → **Add property here**: pin, details, photo, review | "Built for a phone on the street: GPS or drag the pin, big inputs, photos are compressed on the device, and it works offline. Before submitting we check for duplicates within 40 m and odd inputs like annual rent typed as monthly." |
| 2:30 | Priya | **Pipeline** board → new property: decision card | "Everything to decide in 30 seconds: score, go/consider, rent vs benchmark (mock), nearest store, residents, top reasons and risks, photos." |
| 2:50 | Priya | *Shortlist* (note) → **Catchment study** preview | "Every move needs a why and lands in the audit trail. The study preview already knows which parts of this catchment were surveyed before." |
| 3:10 | **Lakshmi** (Survey Mgr) | Studies → **CS-004** → *Split into 3 sectors* → assign; **Team** | "Streets are weighted by length and cut into wedges of equal lane-km — non-overlapping, and every surveyor starts near the centre." |
| 3:35 | **Suresh** (phone) | Assignments → **CS-003** → *Next lane* → fill → Save | "Lane by lane: households, SEC, kiranas, brands. Drafts autosave; with no signal it goes to an outbox and syncs later — duplicates are harmless." |
| 4:05 | Priya | **PR-0001** → evaluation v2 *ground-truthed* by CS-001; **CS-002** reused; **Decision pack** | "When the survey completes, insights roll up and the property is re-evaluated — here the survey came within 1 % of our model. A nearby property reused the same survey with no new fieldwork. The decision pack prints to PDF for leadership." |
| 4:30 | Priya | **Analyst**: "compare Velachery and Tambaram" | "The analyst computes facts first, then answers — grounded in the same model." |
| 4:45 | — | README architecture diagram | "Architecture: FastAPI services + persistent job runner, SQLite with H3 indexing, committed OSM snapshot for reproducibility, 14 tests in CI. Trade-offs and next steps are in the README." |
