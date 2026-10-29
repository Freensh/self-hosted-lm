import os
import mlflow

mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_ARN"])
mlflow.set_experiment("carecart-kubernetes-assistant")

@mlflow.trace(name="synthetic_kubernetes_tool", span_type="TOOL")
def read_fixture():
    return {"namespace": "synthetic", "pod": "demo", "status": "Pending"}

@mlflow.trace(name="synthetic_assistant_request", span_type="CHAIN")
def exercise():
    mlflow.update_current_trace(tags={"environment": "validation"})
    with mlflow.start_span(name="astra_call_fixture", span_type="LLM") as span:
        span.set_inputs({"model": "astra", "message": "Inspect the demo pod"})
        span.set_outputs({"requested_tool": "read_fixture"})
    result = read_fixture()
    return {"answer": f"The demo pod is {result['status']}.", "synthetic": True}

exercise()
mlflow.flush_trace_async_logging()
print("Inspect the validation trace and its child spans in MLflow.")
