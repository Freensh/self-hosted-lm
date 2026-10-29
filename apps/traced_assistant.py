"""Record the assistant request and its model/tool calls in MLflow."""

import os
import mlflow
from assistant_loop import run_loop

mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_ARN"])
mlflow.set_experiment("carecart-kubernetes-assistant")


def traced_ask(client, tools, dispatch, prompt_text, question, user):
    with mlflow.start_span(name="kubernetes_assistant", span_type="CHAIN") as trace:
        # Record release identifiers, not the user's question or tool output.
        trace.set_inputs(
            {
                "application_version": os.environ["APP_VERSION"],
                "prompt_uri": os.environ["PROMPT_URI"],
                "astra_release": os.environ["ASTRA_RELEASE_ID"],
            }
        )
        result = run_loop(
            client,
            tools,
            dispatch,
            prompt_text,
            question,
            user,
            span_factory=mlflow.start_span,
        )
        trace.set_outputs({"completed": True, "tools_used": result["tools_used"]})
        return result
