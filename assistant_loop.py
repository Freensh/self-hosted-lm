"""Ask Astra, run an approved tool when requested, then return its answer."""

import json
from contextlib import nullcontext


def run_loop(
    client, tools, dispatch, prompt, question, user, span_factory=None, max_rounds=5
):
    allowed_tools = {tool["function"]["name"] for tool in tools}
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": question},
    ]
    tools_used = []
    # With no MLflow tracer, the same loop runs without recording spans.
    span_factory = span_factory or (lambda **kwargs: nullcontext(None))
    for round_number in range(max_rounds):
        # 1. Send the conversation to Astra.
        with span_factory(name="astra_call", span_type="LLM") as span:
            if span:
                span.set_inputs({"model": "astra", "round": round_number})
            response = client.chat.completions.create(
                model="astra",
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0,
                max_tokens=1024,
                user=user,
            )
            message = response.choices[0].message
            if span:
                span.set_outputs(
                    {
                        "has_tool_calls": bool(message.tool_calls),
                        "tokens": (
                            response.usage.total_tokens if response.usage else None
                        ),
                    }
                )
        if not message.tool_calls:
            if not message.content:
                raise ValueError("Model returned neither an answer nor a tool call")
            return {"answer": message.content, "tools_used": tools_used}
        if len(message.tool_calls) > 8:
            raise ValueError("Too many tool calls in one response")
        messages.append(message.model_dump(exclude_none=True))
        # 2. Run only tools that the application has explicitly allowed.
        for call in message.tool_calls:
            name = call.function.name
            if name not in allowed_tools:
                raise ValueError("Unapproved tool name")
            arguments = json.loads(call.function.arguments or "{}")
            if not isinstance(arguments, dict):
                raise ValueError("Tool arguments must be a JSON object")
            with span_factory(name="tool_call", span_type="TOOL") as span:
                if span:
                    span.set_inputs({"tool": name})
                result = dispatch(name, arguments)
                encoded = json.dumps(result, default=str)
                if len(encoded) > 8000:
                    raise ValueError("Tool result exceeds context allowance")
                if span:
                    span.set_outputs({"tool": name, "result_chars": len(encoded)})
            tools_used.append(name)
            # 3. Give Astra the tool result so it can finish the answer.
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": encoded}
            )
    raise RuntimeError("Tool round limit reached; no completed answer")
