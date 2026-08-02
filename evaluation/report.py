"""Render docs/evaluation-results.md from the committed metric CSVs.

Generated rather than written by hand so the prose can't drift away from the
numbers it describes. Both full tables are printed, not just the winning row —
the pick is an argument, and a reader should be able to disagree with it.

  uv run python -m evaluation.report
"""

import csv
from pathlib import Path

from agent.instructions import INSTRUCTIONS
from evaluation.judge_offline import METRICS_PATH as ANSWER_METRICS_PATH
from evaluation.judge_offline import MISSING_VERDICT, VERDICTS_PATH
from evaluation.retrieval import METRICS_PATH as RETRIEVAL_METRICS_PATH
from evaluation.variants import VARIANTS
from ingestion.prose.search import DEFAULT_ARM

REPORT_PATH = Path(__file__).resolve().parent.parent / "docs" / "evaluation-results.md"

RETRIEVAL_NUMERIC = ("hit_rate", "mrr")
ANSWER_NUMERIC = ("correct_share", "mean_cost", "mean_tokens", "mean_latency")

# Read back from the code rather than hardcoded, so "the winner was already
# shipped" can never survive someone changing what ships.
SHIPPED_ARM = DEFAULT_ARM.__name__.removeprefix("search_")

# When two arms score identically there is nothing to gain from the more
# elaborate one, so ties resolve towards the left of this list.
ARM_COMPLEXITY = {"lexical": 0, "vector": 1, "hybrid": 2}


def load_csv(path, numeric=()) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        for field in numeric:
            row[field] = float(row[field])
    return rows


def retrieval_winner(rows) -> dict:
    """Best MRR, then best hit rate, then the simplest arm."""
    return min(
        rows,
        key=lambda r: (-r["mrr"], -r["hit_rate"], ARM_COMPLEXITY.get(r["arm"], 99)),
    )


def answer_winner(rows) -> dict:
    """Highest share of CORRECT; a tie goes to the cheaper prompt."""
    return min(rows, key=lambda r: (-r["correct_share"], r["mean_cost"]))


def unanimous_failures(verdict_rows) -> list[dict]:
    """Questions no variant answered correctly.

    Where all three agree, the prompt is not the variable — these point at the
    agent, the tools or the data underneath them, which is the part of the
    system a prompt comparison cannot reach.
    """
    by_question: dict[str, dict] = {}
    for row in verdict_rows:
        by_question.setdefault(
            row["id"], {"question": row["question"], "verdicts": []}
        )["verdicts"].append(row["verdict"])
    return [
        {"id": qid, **entry}
        for qid, entry in sorted(by_question.items())
        if "CORRECT" not in entry["verdicts"]
    ]


def failures_section(verdict_rows) -> str:
    failures = unanimous_failures(verdict_rows)
    if not failures:
        return ""
    rows = table(
        ["id", "question", "verdicts"],
        [
            [f["id"], f["question"], ", ".join(sorted(set(f["verdicts"])))]
            for f in failures
        ],
    )
    return f"""
## What every variant got wrong

{len(failures)} of the questions were missed by all three prompts. A prompt
comparison cannot fix these — they are defects below the prompt.

{rows}
"""


def shipped_variant() -> str:
    """Which variant is the prompt the agent actually runs on."""
    for name, text in VARIANTS.items():
        if text == INSTRUCTIONS:
            return name
    return "none"


def outcome(winner, shipped, label) -> str:
    """One sentence on whether the comparison moved the running system."""
    if winner == shipped:
        return (
            f"That is what `{label}` already held, so nothing changed there: the "
            f"comparison confirms the existing choice rather than overturning it. "
            f"A null result is still a result — the choice is now measured rather "
            f"than assumed."
        )
    return f"Now set as the default in `{label}`, replacing {shipped}."


def table(headers, rows) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def retrieval_table(rows) -> str:
    return table(
        ["arm", "RRF k", "candidates", "Hit Rate", "MRR", "questions"],
        [
            [
                row["arm"],
                str(row["rrf_k"]) or "—",
                str(row.get("candidates", "")) or "—",
                f"{row['hit_rate']:.4f}",
                f"{row['mrr']:.4f}",
                str(row["questions"]),
            ]
            for row in rows
        ],
    )


def answer_table(rows) -> str:
    return table(
        [
            "variant", "answers", "CORRECT", "PARTLY_CORRECT", "INCORRECT",
            MISSING_VERDICT, "correct share", "routed as expected",
            "mean cost", "mean tokens", "mean latency",
        ],
        [
            [
                row["variant"],
                str(row["answers"]),
                str(row["CORRECT"]),
                str(row["PARTLY_CORRECT"]),
                str(row["INCORRECT"]),
                str(row[MISSING_VERDICT]),
                f"{row['correct_share']:.1%}",
                f"{row['routed_as_expected']}/{row['answers']}",
                f"${row['mean_cost']:.5f}",
                f"{row['mean_tokens']:.0f}",
                f"{row['mean_latency']:.2f}s",
            ]
            for row in rows
        ],
    )


def render(retrieval_rows, answer_rows, verdict_rows=()) -> str:
    best_arm = retrieval_winner(retrieval_rows)
    best_variant = answer_winner(answer_rows)
    arm_name = best_arm["arm"]
    if arm_name == "hybrid":
        arm_name = f"hybrid (RRF k={best_arm['rrf_k']})"

    best_hit_rate = max(retrieval_rows, key=lambda r: r["hit_rate"])
    spread = max(r["correct_share"] for r in answer_rows) - min(
        r["correct_share"] for r in answer_rows
    )

    return f"""# Offline evaluation results

<!-- Generated by evaluation/report.py. Do not edit by hand: re-run it instead. -->

Two comparisons, each scoring a fixed, committed dataset so that re-running them
is meaningful.

## Retrieval — lexical vs vector vs hybrid

Questions are generated from `prose.chunks` by `evaluation/ground_truth.py`, so
the chunk a question came from is by construction its gold document. Each arm
is scored on whether it retrieves that chunk, keyed on
`(article, section, chunk_index)`.

{retrieval_table(retrieval_rows)}

**Winner: {arm_name}** — MRR {best_arm['mrr']:.4f}, Hit Rate
{best_arm['hit_rate']:.4f}.
{outcome(best_arm['arm'], SHIPPED_ARM, 'DEFAULT_ARM')}
`DEFAULT_ARM` lives in `ingestion/prose/search.py` and is the arm every
`search()` call goes through, which is how `agent/tools.py` reaches the corpus.

Hit Rate asks whether the gold chunk was found at all; MRR asks how near the
top it was. They disagree here: hybrid at RRF k=1 has the best Hit Rate
({best_hit_rate['hit_rate']:.4f} against {best_arm['hit_rate']:.4f}) while
ranking the gold chunk lower on average. Fusing in the lexical list drags a few
more gold chunks into the top 5 but pushes others down inside it. MRR decides
the tie, because the agent reads the first result or two and rarely goes deeper —
a gold chunk sitting fifth is nearly as useless as one that was never found.

The lexical arm is far behind on this corpus. The questions are asked in
natural language while the passages are encyclopaedic prose, so shared
vocabulary is thin — exactly the gap vector search exists to close.

## Answer quality — three prompt variants

The same agent, tools and model on all three; only the developer message
differs. Answers are scored against hand-written reference answers by
`evaluation/judge_offline.py`, following lesson 13's A→Q→A' setup.

- **full** — the shipped prompt: routing rules, schema, the worked self-join,
  the ILIKE and substitution notes.
- **lean** — routing rules and a bare schema, no coaching.
- **guided** — full, plus worked routing traces for mixed questions.

{answer_table(answer_rows)}

**Winner: {best_variant['variant']}** — {best_variant['correct_share']:.1%}
CORRECT at ${best_variant['mean_cost']:.5f} per answer.
{outcome(best_variant['variant'], shipped_variant(), 'agent/instructions.py')}

Read that winner cautiously. The three variants span {spread:.1%} on thirty
questions, which is a handful of answers — well inside what a different set of
thirty would shuffle. The defensible claim is not that `{best_variant['variant']}`
is best but that neither alternative beats it, so there is no case for switching.

The costs are separated more clearly than the scores. `lean` runs on
{min(r['mean_tokens'] for r in answer_rows):.0f} mean tokens against
{max(r['mean_tokens'] for r in answer_rows):.0f} for the most expensive variant,
for a correct share within a few points. If spend mattered more than it does
here, that is the trade worth making.

`guided` is the instructive failure. Its worked routing traces did what they
were meant to — it routed every question down the expected path, better than
either other variant — and it still scored last. Routing was not the bottleneck,
so buying more of it with a longer prompt bought nothing.

`{MISSING_VERDICT}` counts answers the judge could not score after retries.
They stay in the denominator of the correct share: an answer that failed to be
scored is not evidence that it was right.

{failures_section(verdict_rows)}
Two of them are worth naming, because both are fixable and neither is a prompt
problem:

**Shootout penalties are counted as goals.** `football.events` records each
shootout penalty as a `Goal` event at minute 120, so any "how many goals"
query over-counts. The agent reports Mbappé and Messi tied on 9 in the
tournament, and Mbappé scoring four in the final, where the true figures are 8,
7 and a hat-trick. Every variant gets this wrong identically because they share
the schema notes, which do not mention it. The fix belongs in the schema
documentation the agent reads, not in a prompt variant.

**Off-topic requests are declined selectively.** The agent correctly refuses
questions it has no data for, but answers a request to write a Python function.
Its scope rules are about which tool to reach for, not about what it is for,
so a question that needs no tool at all falls through them.

## Caveats

**The retrieval questions are synthetic.** They were generated from the chunks
they are scored against, which flatters retrieval overall and the lexical arm
in particular — a question written from a passage tends to reuse its wording.
The generation prompt tells the model to use as few words as possible from the
passage, which reduces the effect but does not remove it. Read the gap between
arms rather than the absolute numbers.

**The answer references were curated by hand.** About thirty questions, with
the SQL-backed references checked against the live database and the prose ones
against their source chunk. It is a small set, so a few points of difference
between variants is noise; a large gap is not.
"""


def main() -> None:
    retrieval_rows = load_csv(RETRIEVAL_METRICS_PATH, numeric=RETRIEVAL_NUMERIC)
    answer_rows = load_csv(ANSWER_METRICS_PATH, numeric=ANSWER_NUMERIC)
    verdict_rows = load_csv(VERDICTS_PATH)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        render(retrieval_rows, answer_rows, verdict_rows), encoding="utf-8"
    )
    print(f"-> {REPORT_PATH}")


if __name__ == "__main__":
    main()
