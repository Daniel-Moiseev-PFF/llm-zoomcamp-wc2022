from types import SimpleNamespace

from agent.instructions import INSTRUCTIONS
from agent.loop import MAX_ITERATIONS, run_agent_loop


def usage(input_tokens, output_tokens):
    return SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )


def function_call(name, arguments, call_id):
    return SimpleNamespace(
        type="function_call", name=name, arguments=arguments, call_id=call_id
    )


def message(text):
    return SimpleNamespace(type="message", content=[SimpleNamespace(text=text)])


class FakeResponses:
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.requests = []

    def create(self, model, input, tools):
        self.requests.append({"model": model, "input": list(input), "tools": tools})
        if self.scripted:
            return self.scripted.pop(0)
        # Keep returning a tool call forever (for the iteration-cap test).
        return SimpleNamespace(
            output=[function_call("lookup", '{"q": "again"}', f"c{len(self.requests)}")],
            usage=usage(1, 1),
        )


class FakeClient:
    def __init__(self, scripted):
        self.responses = FakeResponses(scripted)


TOOLS = {"lookup": lambda q: {"found": q}}
SCHEMAS = [{"type": "function", "name": "lookup"}]


def test_direct_answer_without_tools():
    client = FakeClient([SimpleNamespace(output=[message("The answer.")], usage=usage(10, 5))])
    answer, messages, meta = run_agent_loop(client, "test-model", TOOLS, SCHEMAS, "Q?")
    assert answer == "The answer."
    assert meta["iterations"] == 1
    assert meta["tool_calls"] == []


def test_first_messages_are_developer_then_user():
    client = FakeClient([SimpleNamespace(output=[message("Hi.")], usage=usage(1, 1))])
    _, messages, _ = run_agent_loop(client, "test-model", TOOLS, SCHEMAS, "Q?")
    assert messages[0]["role"] == "developer"
    assert messages[1] == {"role": "user", "content": "Q?"}


def test_custom_instructions_reach_the_developer_message():
    # The offline evaluation runs the same loop under several instruction
    # variants; without this it could only ever score the shipped prompt.
    client = FakeClient([SimpleNamespace(output=[message("Hi.")], usage=usage(1, 1))])
    _, messages, _ = run_agent_loop(
        client, "test-model", TOOLS, SCHEMAS, "Q?", instructions="Be terse."
    )
    assert messages[0] == {"role": "developer", "content": "Be terse."}


def test_the_shipped_instructions_are_the_default():
    client = FakeClient([SimpleNamespace(output=[message("Hi.")], usage=usage(1, 1))])
    _, messages, _ = run_agent_loop(client, "test-model", TOOLS, SCHEMAS, "Q?")
    assert messages[0]["content"] == INSTRUCTIONS


def test_history_still_suppresses_the_developer_message_with_custom_instructions():
    client = FakeClient([SimpleNamespace(output=[message("Hi.")], usage=usage(1, 1))])
    history = [{"role": "developer", "content": "Be terse."}]
    _, messages, _ = run_agent_loop(
        client, "test-model", TOOLS, SCHEMAS, "Q?", history=history,
        instructions="Be terse.",
    )
    assert sum(1 for m in messages if isinstance(m, dict) and m.get("role") == "developer") == 1


def test_tool_call_is_dispatched_and_result_sent_back():
    client = FakeClient(
        [
            SimpleNamespace(output=[function_call("lookup", '{"q": "x"}', "c1")], usage=usage(10, 5)),
            SimpleNamespace(output=[message("Found it.")], usage=usage(20, 7)),
        ]
    )
    answer, messages, meta = run_agent_loop(client, "test-model", TOOLS, SCHEMAS, "Q?")
    assert answer == "Found it."
    # The second API request must contain the model's call AND our tool output.
    second_input = client.responses.requests[1]["input"]
    outputs = [m for m in second_input if isinstance(m, dict) and m.get("type") == "function_call_output"]
    assert outputs and outputs[0]["call_id"] == "c1"
    assert meta["tool_calls"] == [{"name": "lookup", "arguments": {"q": "x"}}]
    assert meta["iterations"] == 2


def test_token_usage_is_summed_across_iterations():
    client = FakeClient(
        [
            SimpleNamespace(output=[function_call("lookup", '{"q": "x"}', "c1")], usage=usage(10, 5)),
            SimpleNamespace(output=[message("Done.")], usage=usage(20, 7)),
        ]
    )
    _, _, meta = run_agent_loop(client, "test-model", TOOLS, SCHEMAS, "Q?")
    assert meta["prompt_tokens"] == 30
    assert meta["completion_tokens"] == 12
    assert meta["total_tokens"] == 42
    assert meta["model_used"] == "test-model"
    assert meta["response_time"] >= 0


def test_stops_at_max_iterations_when_model_keeps_calling_tools():
    client = FakeClient([])  # FakeResponses returns a tool call forever
    answer, _, meta = run_agent_loop(client, "test-model", TOOLS, SCHEMAS, "Q?")
    assert len(client.responses.requests) == MAX_ITERATIONS
    assert meta["iterations"] == MAX_ITERATIONS
    assert answer is None


def test_history_enables_multi_turn_without_duplicating_instructions():
    client = FakeClient([SimpleNamespace(output=[message("First.")], usage=usage(1, 1))])
    _, history, _ = run_agent_loop(client, "test-model", TOOLS, SCHEMAS, "Q1?")

    client2 = FakeClient([SimpleNamespace(output=[message("Second.")], usage=usage(1, 1))])
    answer, messages, _ = run_agent_loop(
        client2, "test-model", TOOLS, SCHEMAS, "Q2?", history=history
    )
    assert answer == "Second."
    developer_count = sum(
        1 for m in messages if isinstance(m, dict) and m.get("role") == "developer"
    )
    assert developer_count == 1
    users = [m for m in messages if isinstance(m, dict) and m.get("role") == "user"]
    assert [u["content"] for u in users] == ["Q1?", "Q2?"]
