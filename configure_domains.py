"""Render and apply service routes from the applied Terraform configuration.

Render is local only. Apply requires the matching private EKS API, deployed
backend Services and a ready AWS Load Balancer Controller.
"""
import argparse
import ipaddress
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

from render_manifest import render

ROOT = Path(__file__).resolve().parent
ALB = "alb.ingress.kubernetes.io/"
DNS = "external-dns.alpha.kubernetes.io/"


def command(argv):
    return subprocess.run(argv, check=True, capture_output=True, text=True).stdout


def read_config(path=None):
    raw = Path(path).read_text(encoding="utf-8-sig") if path else command(
        ["terraform", f"-chdir={ROOT / 'infra'}", "output", "-json", "domain_configuration"]
    )
    return json.loads(raw)


def catalog():
    return yaml.safe_load((ROOT / "k8s/edge/services.yaml").read_text(encoding="utf-8"))


def validate(config):
    if set(config["hosts"]) != set(catalog()):
        raise ValueError("Terraform hosts must contain exactly the seven supported services")
    domain = config["domain_name"]
    label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    if not re.fullmatch(rf"{label}(?:\.{label})+", domain) or len(domain) > 180:
        raise ValueError("Invalid base domain")
    if len(set(config["hosts"].values())) != len(catalog()):
        raise ValueError("Each service must have a different hostname")
    for host in config["hosts"].values():
        if not re.fullmatch(rf"{label}\.{re.escape(domain)}", host):
            raise ValueError(f"Hostname must be one label beneath {domain}: {host}")
    if not config["allowed_cidrs"]:
        raise ValueError("An approved source CIDR is required")
    for cidr in config["allowed_cidrs"]:
        network = ipaddress.ip_network(cidr, strict=True)
        if network.version != 4 or network.prefixlen == 0:
            raise ValueError("Only explicit IPv4 source CIDRs are supported")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,40}", config["cluster_name"]):
        raise ValueError("Use a lowercase cluster name, at most 41 characters")
    if not re.fullmatch(r"arn:aws:acm:us-east-1:\d{12}:certificate/[a-f0-9-]+", config["acm_certificate_arn"]):
        raise ValueError("The ACM certificate must be in us-east-1")
    auth = config.get("browser_auth")
    if auth:
        required = {
            "cognito": {"userPoolARN", "userPoolClientID", "userPoolDomain"},
            "oidc": {"issuer", "authorizationEndpoint", "tokenEndpoint", "userInfoEndpoint", "secretName"},
        }
        if auth["type"] not in required or set(auth["parameters"]) != required[auth["type"]]:
            raise ValueError("Invalid browser sign-in settings; do not put secrets in tfvars")
        if any(not isinstance(v, str) or not v.strip() for v in auth["parameters"].values()):
            raise ValueError("Browser sign-in settings cannot be empty")
        if auth["type"] == "oidc" and any(not v.startswith("https://") for k, v in auth["parameters"].items() if k != "secretName"):
            raise ValueError("OIDC endpoints must use HTTPS")


def build_ingresses(config, services):
    validate(config)
    routes = catalog()
    if not services or not set(services) <= set(routes):
        raise ValueError("Select supported service keys")
    if set(services) - {"inference"} and not config.get("browser_auth"):
        raise ValueError("Set approved browser_auth in terraform.tfvars before publishing browser services")
    ingresses = []
    for key in sorted(set(services)):
        route = routes[key]
        annotations = {
            ALB + "scheme": "internet-facing", ALB + "target-type": "ip",
            ALB + "group.name": config["cluster_name"] + "-public",
            ALB + "listen-ports": '[{"HTTPS":443}]', ALB + "ip-address-type": "ipv4",
            ALB + "ssl-policy": "ELBSecurityPolicy-TLS13-1-2-2021-06",
            ALB + "certificate-arn": config["acm_certificate_arn"],
            ALB + "inbound-cidrs": ",".join(config["allowed_cidrs"]),
            ALB + "backend-protocol": route.get("protocol", "HTTP"),
            ALB + "healthcheck-protocol": route.get("protocol", "HTTP"),
            ALB + "healthcheck-path": route["health_path"], DNS + "hostname": config["hosts"][key],
        }
        if key != "inference":
            auth = config["browser_auth"]
            annotations.update({
                ALB + "auth-type": auth["type"],
                ALB + "auth-idp-" + auth["type"]: json.dumps(auth["parameters"], separators=(",", ":")),
                ALB + "auth-on-unauthenticated-request": "authenticate",
                ALB + "auth-session-cookie": "Astra-" + key.replace("_", "-"),
                ALB + "auth-session-timeout": "1800", ALB + "auth-scope": "openid",
            })
        ingresses.append({
            "apiVersion": "networking.k8s.io/v1", "kind": "Ingress",
            "metadata": {"name": "astra-" + key.replace("_", "-"), "namespace": route["namespace"],
                         "labels": {"astra/platform": config["cluster_name"]}, "annotations": annotations},
            "spec": {"ingressClassName": "alb", "rules": [{"host": config["hosts"][key], "http": {"paths": [{
                "path": route["path"], "pathType": "Prefix",
                "backend": {"service": {"name": route["service"], "port": {"number": route["port"]}}},
            }]}}]},
        })
    return ingresses


def render_bundle(config, services, directory):
    ingresses = build_ingresses(config, services)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    values = {key.upper(): str(config[key]) for key in (
        "domain_name", "zone_id", "cluster_name", "txt_owner_id", "external_dns_role_arn"
    )}
    controller = render((ROOT / "k8s/edge/external-dns.yaml").read_text(encoding="utf-8"), values)
    (directory / "external-dns.yaml").write_text(controller, encoding="utf-8")
    (directory / "ingresses.yaml").write_text(yaml.safe_dump_all(ingresses, sort_keys=False), encoding="utf-8")
    argocd = {"global": {"domain": config["hosts"]["argocd"]},
              "configs": {"cm": {"url": "https://" + config["hosts"]["argocd"]}},
              "server": {"ingress": {"enabled": False}}}
    monitoring = {"grafana": {"ingress": {"enabled": False}, "grafana.ini": {"server": {
        "domain": config["hosts"]["grafana"], "root_url": "https://" + config["hosts"]["grafana"]
    }}}}
    for name, data in (("argocd-domain-values.yaml", argocd), ("monitoring-domain-values.yaml", monitoring)):
        (directory / name).write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    endpoints = {key: "https://" + host + ("/v1" if key == "inference" else "") for key, host in config["hosts"].items()}
    (directory / "endpoints.json").write_text(json.dumps(endpoints, indent=2) + "\n", encoding="utf-8")
    return ingresses


def assert_context(config, kube_config):
    clusters = kube_config.get("clusters", [])
    if len(clusters) != 1 or clusters[0]["cluster"]["server"].rstrip("/") != config["cluster_endpoint"].rstrip("/"):
        raise ValueError("Kubernetes context does not match this Terraform stack; nothing was applied")
    if clusters[0]["cluster"].get("insecure-skip-tls-verify"):
        raise ValueError("Kubernetes API TLS verification must stay enabled")


def assert_certificate(config, cert, services):
    if cert["Status"] != "ISSUED":
        raise ValueError("The selected ACM certificate is not issued")
    names = set(cert.get("SubjectAlternativeNames", [])) | {cert["DomainName"]}
    for key in services:
        host = config["hosts"][key]
        if host not in names and "*." + host.split(".", 1)[1] not in names:
            raise ValueError(f"The ACM certificate does not cover {host}")


def assert_dns_ownership(config, records, services):
    by_name = {}
    for record in records:
        by_name.setdefault(record["Name"].rstrip("."), []).append(record)
    owner = "external-dns/owner=" + config["txt_owner_id"]
    for key in services:
        host = config["hosts"][key]
        ownership = [r for kind in ("a", "aaaa", "cname") for r in by_name.get(f"_astra-{kind}.{host}", [])]
        owned = ownership and all(r["Type"] == "TXT" and r.get("ResourceRecords") and all(
            owner in value["Value"].strip('"').split(",") for value in r["ResourceRecords"]
        ) for r in ownership)
        if (by_name.get(host) or ownership) and not owned:
            raise ValueError(f"DNS name is already in use without this stack's ownership: {host}")


def preflight(config, services, context, run=command):
    kube = ["kubectl", "--context", context]
    assert_context(config, json.loads(run(kube + ["config", "view", "--minify", "-o", "json"])))
    aws = ["aws", "--region", "us-east-1", "--output", "json"]
    cert = json.loads(run(aws + ["acm", "describe-certificate", "--certificate-arn", config["acm_certificate_arn"]]))["Certificate"]
    assert_certificate(config, cert, services)
    zone = json.loads(run(aws + ["route53", "get-hosted-zone", "--id", config["zone_id"]]))["HostedZone"]
    if zone["Name"].rstrip(".") != config["domain_name"] or zone["Config"].get("PrivateZone"):
        raise ValueError("Route 53 zone is not the configured public domain")
    records = json.loads(run(aws + ["route53", "list-resource-record-sets", "--hosted-zone-id", config["zone_id"]]))["ResourceRecordSets"]
    assert_dns_ownership(config, records, services)
    controller = json.loads(run(kube + ["-n", "kube-system", "get", "deployment", "aws-load-balancer-controller", "-o", "json"]))
    if controller.get("status", {}).get("availableReplicas", 0) < 1:
        raise ValueError("AWS Load Balancer Controller is not ready")
    for key in services:
        route = catalog()[key]
        service = json.loads(run(kube + ["-n", route["namespace"], "get", "service", route["service"], "-o", "json"]))
        if service["spec"].get("type", "ClusterIP") != "ClusterIP" or route["port"] not in [p["port"] for p in service["spec"]["ports"]]:
            raise ValueError(f"{key} needs its expected ClusterIP service and port before exposure")
        if key != "inference" and config["browser_auth"]["type"] == "oidc":
            secret = config["browser_auth"]["parameters"]["secretName"]
            run(kube + ["-n", route["namespace"], "get", "secret", secret, "-o", "name"])
    if set(services) - {"inference"} and config["browser_auth"]["type"] == "cognito":
        parameters = config["browser_auth"]["parameters"]
        # Filter client metadata: never capture or print the client secret.
        client = json.loads(run(aws + ["cognito-idp", "describe-user-pool-client", "--user-pool-id", parameters["userPoolARN"].split("/")[-1],
                                      "--client-id", parameters["userPoolClientID"], "--query", "UserPoolClient.{CallbackURLs:CallbackURLs,AllowedOAuthFlows:AllowedOAuthFlows}"]))
        required = {f"https://{config['hosts'][key]}/oauth2/idpresponse" for key in services if key != "inference"}
        if not required <= set(client.get("CallbackURLs", [])) or "code" not in client.get("AllowedOAuthFlows", []):
            raise ValueError("Cognito client needs generated callback URLs and authorization-code flow")
    return kube


def apply_bundle(config, services, directory, context):
    kube = preflight(config, services, context)
    print(command(kube + ["apply", "-f", str(Path(directory) / "external-dns.yaml")]), end="")
    print(command(kube + ["-n", "external-dns", "rollout", "status", "deployment/external-dns", "--timeout=180s"]), end="")
    if "argocd" in services:
        patch = json.dumps({"data": {"url": "https://" + config["hosts"]["argocd"]}})
        command(kube + ["-n", "argocd", "patch", "configmap", "argocd-cm", "--type=merge", "-p", patch])
    if "litellm" in services:
        command(kube + ["-n", "gateway", "set", "env", "deployment/litellm", "PROXY_BASE_URL=https://" + config["hosts"]["litellm"]])
    if "grafana" in services:
        command(kube + ["-n", "monitoring", "set", "env", "deployment/monitoring-grafana",
                       "GF_SERVER_DOMAIN=" + config["hosts"]["grafana"], "GF_SERVER_ROOT_URL=https://" + config["hosts"]["grafana"]])
    print(command(kube + ["apply", "-f", str(Path(directory) / "ingresses.yaml")]), end="")
    print("Routes applied. DNS, HTTPS, sign-in and inference still require live verification.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="Saved domain output; otherwise read local Terraform state")
    parser.add_argument("--services", nargs="+", choices=list(catalog()), default=list(catalog()))
    parser.add_argument("--output", default=str(ROOT / "k8s/generated/edge"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--context", help="Explicit kubectl context for this stack")
    parser.add_argument("--host", choices=list(catalog()), help="Print one configured hostname without applying anything")
    args = parser.parse_args()
    if args.apply and not args.context:
        parser.error("--apply requires --context")
    config = read_config(args.config)
    if args.host:
        validate(config)
        print(config["hosts"][args.host])
        return
    render_bundle(config, args.services, args.output)
    print(f"Rendered domain configuration into {args.output}")
    if args.apply:
        apply_bundle(config, args.services, args.output, args.context)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        print(f"Domain setup failed: {error}", file=sys.stderr)
        sys.exit(1)
