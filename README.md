# World Cup 2026 — LLM Knowledge Base

A question-answering system over everything that happened at the 2026 FIFA World Cup — from hard facts (*who advanced to the quarter-finals?*) to open-ended, narrative questions (*what was the biggest scandal involving Switzerland?*).

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

A small, curated **manifest** of *tournament-level* articles. (Per-match reports are deliberately excluded — for a just-finished tournament they don't exist on Wikipedia yet; the narrative prose that does exist is tournament-level.) Candidate articles:

- `2026 FIFA World Cup` — the main article, and the workhorse of the corpus
- `2026 FIFA World Cup final`
- `2026 FIFA World Cup final halftime show`
- `2026 FIFA World Cup knockout stage`

Each article is pinned to a specific **revision id** so the corpus is reproducible and doesn't drift as Wikipedia keeps updating.

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
- **Prose / vector index:** Postgres + pgvector` extension for embeddings

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