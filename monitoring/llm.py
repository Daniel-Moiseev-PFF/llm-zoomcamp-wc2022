"""Structured LLM calls over the Responses API.

Copied from llm-zoomcamp 05-monitoring/code/evaluation_utils.py
(`llm_structured` + `llm_structured_retry`). The cost helpers that live
alongside them there are already covered by monitoring/metrics.py, and the
RAG/tqdm helpers have no counterpart in this project, so neither is copied.

Deviation: `sleep` is injectable, so tests can assert the backoff schedule
without spending three real seconds on it.

Kept separate from judge.py because the offline-evaluation milestone needs the
transport without the judge's domain prompt.
"""

import time

DEFAULT_MODEL = "gpt-5.4-mini"


def llm_structured(client, instructions, user_prompt, output_type, model=DEFAULT_MODEL):
    """One structured call; returns (parsed output_type instance, usage)."""
    messages = [
        {"role": "developer", "content": instructions},
        {"role": "user", "content": user_prompt},
    ]

    response = client.responses.parse(
        model=model,
        input=messages,
        text_format=output_type,
    )

    return response.output_parsed, response.usage


def llm_structured_retry(
    client,
    instructions,
    user_prompt,
    output_type,
    model=DEFAULT_MODEL,
    max_retries=3,
    sleep=time.sleep,
):
    """llm_structured, retried with exponential backoff.

    Models occasionally return JSON that doesn't match the requested structure;
    it's rare, but a retry costs far less than a lost verdict.
    """
    for attempt in range(max_retries):
        try:
            return llm_structured(
                client, instructions, user_prompt, output_type, model=model
            )
        except Exception:
            if attempt == max_retries - 1:
                raise
            sleep(2**attempt)
