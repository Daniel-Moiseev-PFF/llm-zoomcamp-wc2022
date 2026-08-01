# World Cup 2026 — LLM Knowledge Base

A question-answering system over everything that happened at the 2022 FIFA World Cup — from hard facts (*who advanced to the quarter-finals?*) to open-ended, narrative questions (*what was the biggest scandal involving Switzerland?*).

It combines a **relational database** (structured match data), a **vector index** (tournament prose), and an **agent** that routes each question to the right source — or both.

---

## How it works

The user asks a question in a chat UI. An agent decides which of two surfaces to query:

- **Relational DB** — structured facts, via SQL tool calls (results, standings, lineups, venues…)
- **Prose index** — narrative/semantic questions, via vector search over encoded Wikipedia articles

```mermaid
flowchart TD
    U([User]) -->|question| AGENT[Agent]
    AGENT -->|SQL tool| SQL[(Relational DB<br/>match data)]
    AGENT -->|vector search| VEC[(Prose index<br/>article chunks)]
    SQL --> AGENT
    VEC --> AGENT
    AGENT -->|answer| U
    AGENT -. log .-> MON[(Interactions<br/>+ feedback)]
    MON --> GRAF[Grafana dashboard]
```

---

## Data sources

### Structured — API-Football

Ingested **once** from API-Football (World Cup = `league id 1`). Entities pulled:

- leagues, standings, teams, venues, coaches, players
- fixtures / matches, lineups

Lineups are the key table: they power relational questions like *"did players X and Y play against each other?"* — a self-join on appearances in the same match on opposite teams.

**Ingestion:** dlt (REST-API source → Postgres destination), re-runnable.

*Data-source reference: [API-Football data model](https://www.api-football.com/public/img/news/archi-beta.jpg)*

### Unstructured — Wikipedia

A small, curated **manifest** of *tournament-level* articles (Qatar 2022, matching the structured data):

- `2022 FIFA World Cup` — the main article, and the workhorse of the corpus
- `2022 FIFA World Cup final`
- `2022 FIFA World Cup knockout stage`
- `2022 FIFA World Cup opening ceremony`
- `List of 2022 FIFA World Cup controversies`

Each article is pinned to a specific **revision id** (`ingestion/prose/manifest.py`) so the corpus is reproducible and doesn't drift as Wikipedia keeps updating.

Table-shaped sections (group standings, squads, base camps) are **not** ingested as prose — that data comes from the structured side. The rule: *sentences → prose index; cells → SQL.*

---

## Ingestion flows

### Prose (Wikipedia → vector index)

```
read pinned-revision manifest
  → fetch each article        (MediaWiki Action API, by oldid)
  → split into sections       (mwparserfromhell — strip markup, get sections)
  → tag chunk {source_article, section, teams_mentioned}
  → embed
  → write to vector index
```

### Structured (API-Football → SQL)

```
dlt REST-API pipeline → Postgres
  (leagues, teams, venues, coaches, players, fixtures, lineups, standings)
```

---

## Storage

- **Relational:** Postgres (dockerized)
- **Prose / vector index:** Postgres + `pgvector` extension for embeddings (`pgvector/pgvector:pg16` image)

---

## Interface

A simple **Streamlit** chat app. Each answer carries a 👍 / 👎 feedback control.

---

## Monitoring

Online evaluation on live traffic:

- Every interaction logged — question, answer, model, tokens, cost, latency, tools used, feedback
- **LLM-as-judge** scores answer relevance on real traffic
- **Grafana dashboard** (≥ 5 charts): feedback rate, response time, cost/tokens, judge relevance, tool-routing breakdown, feedback split by tool path

---

## Evaluation

> **TODO** — offline evaluation (distinct from monitoring above):
> - **Retrieval:** compare lexical vs. vector vs. hybrid (Hit Rate, MRR); best one is used
> - **Answer quality:** LLM-as-judge across multiple prompt variants

---

## Setup

> **TODO**
> - `docker-compose up` — app + database + Grafana
> - Environment variables — API-Football key, LLM API key
> - Ingestion commands — structured (dlt) and prose (manifest) pipelines
> - Pinned dependency versions

---

## Ingestion (API-Football → Postgres)

One dlt pipeline loads teams, standings, fixtures, and lineups for the FIFA World Cup
(league 1). The season is pinned to 2022 (Qatar) because API-Football's free plan only
exposes seasons 2022–2024 — season 2026 requires a paid plan; flip `SEASON` in
`ingestion/football/__init__.py` if that changes. Lineups cost 1 API call per fixture, so the pipeline is
budgeted (`MAX_REQUESTS_PER_RUN`, default 90) and resumable — re-run it daily until
complete; finished runs are no-ops on the expensive endpoint.

```bash
docker compose up -d                              # start Postgres
uv run python -m ingestion.football.pipeline      # run the pipeline (re-runnable)
uv run pytest                                     # tests (never hit the live API)
uv run python scripts/smoke_test.py               # MANUAL: 1 real API call to /status
```

Required in `.env`: `FOOTBALL_API_KEY`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
`POSTGRES_DB` (optional: `POSTGRES_HOST`, `POSTGRES_PORT`, `MAX_REQUESTS_PER_RUN`).

## Ingestion (Wikipedia → pgvector)

The prose pipeline fetches the 5 pinned articles, splits them into per-section
chunks (≤256 tokens, tables and boilerplate dropped), tags each chunk with the
teams it mentions, embeds with `all-MiniLM-L6-v2` (ONNX, 384-dim), and writes to
`prose.chunks` in the same Postgres. Full refresh on every run — no API keys or
quotas involved. Embedding code follows the llm-zoomcamp course (ONNX Runtime
instead of PyTorch).

```bash
uv run python scripts/download_model.py           # one-time: fetch the ONNX model
uv run python -m ingestion.prose.pipeline         # fetch + chunk + embed + load
uv run python -m ingestion.prose.search "Who scored in the final?"          # smoke search
uv run python -m ingestion.prose.search "biggest scandal?" Switzerland      # team-filtered
```

Requires the structured pipeline to have run first (`football.teams` powers the
team tagging).