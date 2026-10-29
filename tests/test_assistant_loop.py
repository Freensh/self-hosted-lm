import unittest
from types import SimpleNamespace as NS
from assistant_loop import run_loop

TOOLS = [{"type": "function", "function": {"name": "list_pods"}}]


class Message:
    def __init__(self, content=None, name=None, arguments='{"namespace":"synthetic"}'):
        self.content = content
        self.tool_calls = [NS(id="t1", function=NS(name=name, arguments=arguments))] if name else []

    def model_dump(self, **kwargs):
        return {"role": "assistant", "tool_calls": [
            {"id": c.id, "type": "function", "function": {"name": c.function.name,
             "arguments": c.function.arguments}} for c in self.tool_calls]}


def client_for(messages, seen):
    iterator = iter(messages)
    def create(**kwargs):
        seen.append(list(kwargs["messages"]))
        return NS(choices=[NS(message=next(iterator))], usage=NS(total_tokens=20))
    return NS(chat=NS(completions=NS(create=create)))


class AssistantTests(unittest.TestCase):
    def test_tool_result_is_returned_to_model(self):
        seen = []
        client = client_for([Message(name="list_pods"), Message(content="demo is Pending")], seen)
        result = run_loop(client, TOOLS, lambda n,a: [{"name": "demo", "phase": "Pending"}],
                          "Use evidence", "Inspect demo", "synthetic-user")
        self.assertEqual(result["tools_used"], ["list_pods"])
        self.assertEqual(seen[1][-1]["tool_call_id"], "t1")
        self.assertIn("Pending", seen[1][-1]["content"])

    def test_unknown_tool_never_executes(self):
        client = client_for([Message(name="delete_cluster")], [])
        with self.assertRaises(ValueError):
            run_loop(client, TOOLS, lambda n,a: self.fail("Executed unknown tool"), "", "", "")

    def test_invalid_arguments_never_execute(self):
        for arguments in ("[]", "not-json"):
            client = client_for([Message(name="list_pods", arguments=arguments)], [])
            with self.assertRaises(ValueError):
                run_loop(client, TOOLS, lambda n,a: self.fail("Executed invalid arguments"), "", "", "")

    def test_loop_is_bounded(self):
        client = client_for([Message(name="list_pods")]*2, [])
        with self.assertRaises(RuntimeError):
            run_loop(client, TOOLS, lambda n,a: [], "", "", "", max_rounds=2)

    def test_empty_answer_fails(self):
        with self.assertRaises(ValueError):
            run_loop(client_for([Message()], []), TOOLS, lambda n,a: [], "", "", "")

    def test_oversized_result_is_not_sliced_into_invalid_json(self):
        with self.assertRaises(ValueError):
            run_loop(client_for([Message(name="list_pods")], []), TOOLS,
                     lambda n,a: {"data": "x"*9000}, "", "", "")


if __name__ == "__main__":
    unittest.main()
