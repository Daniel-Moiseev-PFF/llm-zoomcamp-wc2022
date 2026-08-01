"""Streamlit chat UI over the routing agent.

Run: uv run streamlit run app/main.py
Reference: llm-zoomcamp 05-monitoring/code/app.py, adapted to a real chat
transcript (st.chat_input/st.chat_message) with per-answer feedback keyed by
each answer's conversation id.
"""

import os

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

from agent import DEFAULT_MODEL
from agent.cli import build_tools
from agent.loop import run_agent_loop
from agent.tools import TOOL_SCHEMAS
from app.helpers import answer_or_fallback, format_caption, thumbs_to_score
from ingestion.prose import MODEL_PATH
from ingestion.prose.embedder import Embedder
from ingestion.prose.store import connect
from monitoring.db import init_db, save_conversation, save_feedback
from monitoring.metrics import cost_from_metadata


@st.cache_resource
def get_resources():
    load_dotenv()
    model = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
    client = OpenAI()
    tool_conn = connect()
    tool_conn.read_only = True  # the agent writes its own SQL; never let it write data
    tools = build_tools(tool_conn, Embedder(MODEL_PATH))
    log_conn = connect()  # logging needs writes, so it can't share the tools conn
    init_db(log_conn)
    return client, model, tools, log_conn


client, model, tools, log_conn = get_resources()

st.title("World Cup 2022 agent")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "history" not in st.session_state:
    st.session_state.history = None


def record_feedback(conversation_id):
    value = st.session_state[f"fb_{conversation_id}"]
    save_feedback(log_conn, conversation_id, "user", score=thumbs_to_score(value))


for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant":
            st.caption(message["caption"])
            st.feedback(
                "thumbs",
                key=f"fb_{message['conversation_id']}",
                on_change=record_feedback,
                args=(message["conversation_id"],),
            )

if question := st.chat_input("Ask about the 2022 World Cup"):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"), st.spinner("Thinking..."):
        answer, history, metadata = run_agent_loop(
            client,
            model,
            tools,
            TOOL_SCHEMAS,
            question,
            history=st.session_state.history,
        )
    st.session_state.history = history
    cost = cost_from_metadata(model, metadata)
    answer_text = answer_or_fallback(answer)
    conversation_id = save_conversation(log_conn, question, answer_text, metadata, cost)
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer_text,
            "caption": format_caption(metadata, cost),
            "conversation_id": conversation_id,
        }
    )
    st.rerun()
