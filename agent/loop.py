"""The agentic loop: keep calling the model and running tools until it answers.

Reference: llm-zoomcamp 01-agentic-rag/lessons/14-agentic-loop.md (agent_loop).
"""

import json
import logging
import time

from agent.instructions import INSTRUCTIONS
from agent.tools import make_call

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 10


def run_agent_loop(
    client, model, tools, tool_schemas, question, history=None, instructions=INSTRUCTIONS
):
    """Run the agent until it produces a final answer (or hits MAX_ITERATIONS).

    Args:
        client: OpenAI-like client; call ``client.responses.create(model=...,
            input=messages, tools=tool_schemas)``.
        model: model name string.
        tools: dict mapping tool name -> callable, for ``make_call``.
        tool_schemas: list of tool-schema dicts passed to the API.
        question: the user's question for this turn.
        history: full message list from a previous turn (multi-turn chat),
            or None for a fresh conversation.
        instructions: the developer message for a fresh conversation. Defaults
            to the shipped INSTRUCTIONS; the offline evaluation passes variants.

    Returns:
        (answer, messages, metadata) where
        - answer: text of the model's last message, or None if it never
          produced one (e.g. the iteration cap was hit);
        - messages: the full message list (pass back as ``history`` next turn);
        - metadata: {"model_used", "response_time" (seconds),
          "prompt_tokens", "completion_tokens", "total_tokens" (summed over
          all API calls), "tool_calls" (list of {"name", "arguments"-dict},
          in order), "iterations" (number of API calls made)}.

    Behavior (see the lesson-14 loop):
    - Fresh conversation: messages start with a ``developer`` message holding
      INSTRUCTIONS, then a ``user`` message with the question. With history:
      append only the new user message (instructions are already in there).
    - Each iteration: call the API, extend messages with ``response.output``;
      for every ``function_call`` item, run it via ``make_call(item, tools)``
      and append the result; for every ``message`` item, remember its text
      (``item.content[0].text``) as the latest answer.
    - Stop when a response contains no function calls, or after
      MAX_ITERATIONS API calls.
    """
    t0 = time.time()
    if history:
        messages = list(history)
    else:
        messages = [{"role": "developer", "content": instructions}]
    messages.append({"role": "user", "content": question})

    answer = None
    tool_calls = []
    prompt_tokens = 0
    completion_tokens = 0
    it = 0

    while True:
        print(f"iteration #{it + 1}...")
        has_function_calls = False

        response = client.responses.create(
            model=model,
            input=messages,
            tools=tool_schemas,
        )
        it += 1
        prompt_tokens += response.usage.input_tokens
        completion_tokens += response.usage.output_tokens

        messages.extend(response.output)

        for item in response.output:
            if item.type == "function_call":
                print("function_call:", item.name, item.arguments)
                tool_calls.append(
                    {"name": item.name, "arguments": json.loads(item.arguments)}
                )
                messages.append(make_call(item, tools))
                has_function_calls = True

            elif item.type == "message":
                answer = item.content[0].text

        if has_function_calls == False or it >= MAX_ITERATIONS:
            break

    metadata = {
        "model_used": model,
        "response_time": time.time() - t0,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "tool_calls": tool_calls,
        "iterations": it,
    }
    return answer, messages, metadata
