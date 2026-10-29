# Platform addresses

## A. Configure the names once

Set the base domain in infra/terraform.tfvars. Use a public Route 53 zone you control and an issued wildcard ACM certificate in us-east-1. Override only the subdomain labels you want to change.

```hcl
domain_name = "afriqhome.com"
subdomains = {
  inference     = "astra"
  litellm       = "litellm"
  argocd        = "argocd"
  mlflow        = "mlflow"
  k8s_assistant = "k8sassistant"
  aws_assistant = "awsassistant"
  grafana       = "grafana"
}
create_cognito = true
```

For your implementation, replace the domain with your own. The resulting addresses are astra, litellm, argocd, mlflow, k8sassistant, awsassistant and grafana under that domain. The Astra API uses /v1. The LiteLLM dashboard uses /ui. Both reach the same gateway Service, while vLLM remains private.

Set public_client_cidrs to your approved public egress addresses. Terraform also includes the platform's NAT addresses for applications calling from private subnets. Set acm_certificate_arn to use a particular existing certificate; otherwise Terraform finds the issued wildcard. The certificate stays in ACM. This ALB listener does not need cert-manager.

Terraform creates a Cognito user pool, a client and a sign-in domain. It derives all six browser callback URLs from the service names. Public self-registration is disabled. Create approved users through Cognito administration; do not put their passwords in Terraform or Git. Cognito protects the browser entry points. Application permissions inside Argo CD, Grafana and LiteLLM still apply. The model API uses its application key.

MLflow opens through the configured mlflow hostname, then redirects the authorized browser to SageMaker's managed UI. The browser address changes after that redirect.

## B. Generate and apply the routes

Apply the AWS foundation first. Install AWS Load Balancer Controller and deploy the backend Services before publishing their routes. Run from a workstation with access to the private EKS API.

```bash
source .venv/bin/activate
python configure_domains.py
```

This reads the applied Terraform output directly. It creates the ExternalDNS manifest, HTTPS Ingress rules, Argo CD and Grafana domain values, and endpoints.json under k8s/generated/edge. No hostname needs to be copied into YAML. Use the generated domain values with the corresponding Helm releases. Keep these settings in the environment's reviewed GitOps configuration so Argo CD preserves them.

After the selected services are deployed, apply the routes. Use the context created for this stack.

```bash
python configure_domains.py --apply --context "$CLUSTER_CONTEXT"
```

The script checks the cluster endpoint, certificate coverage, existing DNS ownership, backend Service ports and browser sign-in configuration before changing Kubernetes. It installs ExternalDNS and applies the routes. AWS Load Balancer Controller creates the HTTPS listener; ExternalDNS creates the DNS records. All routes share one ALB. Only the platform team should be able to create or change Ingress rules in these namespaces.

During the gateway step, publish just the ready API service:

```bash
python configure_domains.py --services inference --apply --context "$CLUSTER_CONTEXT"
```

Selecting services only applies those routes. It does not remove previously published routes. Missing applications are reported as prerequisites, rather than treated as successful deployment.

## C. Verify the result

```bash
terraform -chdir=infra output -json domain_configuration
kubectl --context "$CLUSTER_CONTEXT" get ingress --all-namespaces
kubectl --context "$CLUSTER_CONTEXT" -n external-dns logs deployment/external-dns --tail=50
export ASTRA_HOST="$(python configure_domains.py --host inference)"
python verify_endpoint.py --expect allowed
```

Enter the application key using the hidden prompt in Application Onboarding before the endpoint test. Expect a real answer over verified HTTPS. Check that every published hostname has the expected ALB address in Route 53 and no ExternalDNS ownership error.

Open each browser hostname in a private window. Expect Cognito sign-in before application access. After approved sign-in, verify the intended application; for MLflow, verify the redirect to the managed UI. A generated YAML file, DNS record or HTTP redirect alone does not prove the application works.

If DNS is missing, inspect ExternalDNS logs and its IAM role. If a target is unhealthy, check the Service port, ready endpoints and health path. If Cognito rejects a callback, compare the URL with domain_configuration.browser_callback_urls. Do not disable TLS or sign-in to make a test pass.

## D. Change names or clean up

Before changing an existing domain or label, remove its old Ingress while the old Terraform DNS permissions still exist. Wait for ExternalDNS to remove that stack's address and ownership records. Then change terraform.tfvars, apply Terraform, regenerate and apply the routes. This avoids leaving old names behind after the IAM policy moves to the new names.

During final cleanup, delete the generated Ingress rules first and wait for their DNS records and ALB to disappear. Keep ExternalDNS running until that completes, then remove it and destroy the foundation. Retain the shared hosted zone and existing wildcard certificate.

```bash
kubectl --context "$CLUSTER_CONTEXT" delete -f k8s/generated/edge/ingresses.yaml
```

If routes were published in separate stages, the current file may contain only the last stage. List the Ingress resources with the astra/platform label for this cluster and remove the remaining routes before stopping ExternalDNS.
