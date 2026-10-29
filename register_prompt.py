import os
import mlflow

TEMPLATE = (
        "You are CareCart's Kubernetes diagnostic assistant. "
        "Use the approved read-only tools to inspect the requested namespace. "
        "Ground findings in returned tool evidence. "
        "Report missing evidence and failed tool calls explicitly."
)


def register_template(name="carecart-kubernetes-system", template=TEMPLATE):
    # SageMaker tracking server 3.0 uses the MLflow 3.0 top-level prompt API.
    return mlflow.register_prompt(name=name, template=template,
                                  commit_message="Reviewed diagnostic prompt")


if __name__ == "__main__":
    tracking_arn = os.environ["MLFLOW_TRACKING_ARN"]
    mlflow.set_tracking_uri(tracking_arn)
    mlflow.set_registry_uri(tracking_arn)
    mlflow.set_experiment("carecart-kubernetes-assistant")
    prompt = register_template()
    print(f"prompts:/{prompt.name}/{prompt.version}")
