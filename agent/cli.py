"""CLI chat for the routing agent.

Interactive: uv run python -m agent.cli
One-shot:    uv run python -m agent.cli "Did Messi and Mbappé play against each other?"
"""

import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

from agent import DEFAULT_MODEL
from agent.loop import run_agent_loop
from agent.tools import TOOL_SCHEMAS, execute_sql, read_section, search_prose
from ingestion.prose import MODEL_PATH
from ingestion.prose.embedder import Embedder
from ingestion.prose.store import connect


def build_tools(conn, embedder) -> dict:
    return {
        "execute_sql": lambda query: execute_sql(conn, query),
        "search_prose": lambda query, team=None: search_prose(conn, embedder, query, team),
        "read_section": lambda article, section: read_section(conn, article, section),
    }


def print_result(answer, meta) -> None:
    print()
    print(answer if answer is not None else "(no answer — iteration cap reached)")
    tool_trace = ", ".join(c["name"] for c in meta["tool_calls"]) or "none"
    print(
        f"\n[{meta['model_used']} | {meta['iterations']} calls | tools: {tool_trace} | "
        f"{meta['total_tokens']} tokens | {meta['response_time']:.1f}s]"
    )


def main() -> None:
    load_dotenv()
    model = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
    client = OpenAI()
    conn = connect()
    conn.read_only = True  # the agent writes its own SQL; never let it write data
    tools = build_tools(conn, Embedder(MODEL_PATH))

    if len(sys.argv) > 1:
        answer, _, meta = run_agent_loop(client, model, tools, TOOL_SCHEMAS, sys.argv[1])
        print_result(answer, meta)
        return

    print("World Cup 2022 agent — ask away ('exit' or Ctrl-D to quit)")
    history = None
    while True:
        try:
            question = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question or question.lower() in {"exit", "quit"}:
            break
        answer, history, meta = run_agent_loop(
            client, model, tools, TOOL_SCHEMAS, question, history=history
        )
        print_result(answer, meta)


if __name__ == "__main__":
    main()
