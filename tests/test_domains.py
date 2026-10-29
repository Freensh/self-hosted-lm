import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

import configure_domains as domains


def fixture(domain="example.com"):
    labels = {
        "inference": "astra",
        "litellm": "litellm",
        "argocd": "argocd",
        "mlflow": "mlflow",
        "k8s_assistant": "k8sassistant",
        "aws_assistant": "awsassistant",
        "grafana": "grafana",
    }
    return {
        "domain_name": domain,
        "hosts": {key: value + "." + domain for key, value in labels.items()},
        "zone_id": "Z123456",
        "cluster_name": "astra-test",
        "cluster_endpoint": "https://test.eks.amazonaws.com",
        "acm_certificate_arn": "arn:aws:acm:us-east-1:123456789012:certificate/0123-abcd",
        "allowed_cidrs": ["203.0.113.10/32", "198.51.100.20/32"],
        "external_dns_role_arn": "arn:aws:iam::123456789012:role/astra-test-dns",
        "txt_owner_id": "astra-astra-test",
        "browser_auth": {
            "type": "cognito",
            "parameters": {
                "userPoolARN": "arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_TEST",
                "userPoolClientID": "test-client",
                "userPoolDomain": "astra-test-0123",
            },
        },
    }


class DomainTests(unittest.TestCase):
    def test_domain_change_reaches_all_routes_and_chart_values(self):
        for domain in ("example.com", "platform.example.org"):
            with self.subTest(domain=domain), tempfile.TemporaryDirectory() as temp:
                config = fixture(domain)
                routes = domains.render_bundle(config, list(domains.catalog()), temp)
                self.assertEqual(
                    {r["spec"]["rules"][0]["host"] for r in routes},
                    set(config["hosts"].values()),
                )
                for route in routes:
                    self.assertEqual(
                        route["metadata"]["annotations"][domains.DNS + "hostname"],
                        route["spec"]["rules"][0]["host"],
                    )
                for filename in (
                    "argocd-domain-values.yaml",
                    "monitoring-domain-values.yaml",
                    "endpoints.json",
                ):
                    self.assertIn(domain, (Path(temp) / filename).read_text())
                controller = list(
                    yaml.safe_load_all((Path(temp) / "external-dns.yaml").read_text())
                )[-1]
                args = controller["spec"]["template"]["spec"]["containers"][0]["args"]
                self.assertIn("--domain-filter=" + domain, args)
                self.assertIn("--zone-id-filter=Z123456", args)

    def test_custom_label_propagates_without_changing_other_services(self):
        config = fixture()
        config["hosts"]["mlflow"] = "models.example.com"
        routes = domains.build_ingresses(config, ["mlflow", "argocd"])
        self.assertEqual(
            {r["spec"]["rules"][0]["host"] for r in routes},
            {"models.example.com", "argocd.example.com"},
        )

    def test_inference_uses_application_auth_and_never_exposes_admin_root(self):
        config = fixture()
        config["browser_auth"] = None
        route = domains.build_ingresses(config, ["inference"])[0]
        self.assertNotIn(domains.ALB + "auth-type", route["metadata"]["annotations"])
        self.assertEqual(route["spec"]["rules"][0]["http"]["paths"][0]["path"], "/v1")
        self.assertEqual(
            route["spec"]["rules"][0]["http"]["paths"][0]["backend"]["service"]["name"],
            "litellm",
        )

    def test_every_browser_route_requires_cognito(self):
        routes = domains.build_ingresses(fixture(), list(domains.catalog()))
        for route in routes:
            if route["metadata"]["name"] != "astra-inference":
                self.assertEqual(
                    route["metadata"]["annotations"][domains.ALB + "auth-type"],
                    "cognito",
                )

    def test_missing_browser_auth_stops_before_creating_files(self):
        config = fixture()
        config["browser_auth"] = None
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "output"
            with self.assertRaisesRegex(ValueError, "browser_auth"):
                domains.render_bundle(config, ["mlflow"], output)
            self.assertFalse(output.exists())

    def test_rejects_duplicate_nested_or_foreign_hosts(self):
        for host in (
            "argocd.example.com",
            "one.two.example.com",
            "mlflow.other.example",
            "bad\n.example.com",
        ):
            config = fixture()
            config["hosts"]["mlflow"] = host
            with self.subTest(host=host), self.assertRaises(ValueError):
                domains.validate(config)

    def test_unrestricted_or_ipv6_cidrs_rejected(self):
        for cidr in ("0.0.0.0/0", "::/0", "2001:db8::/32", "bad"):
            config = fixture()
            config["allowed_cidrs"] = [cidr]
            with self.subTest(cidr=cidr), self.assertRaises(ValueError):
                domains.validate(config)

    def test_no_public_vllm_route(self):
        with self.assertRaises(ValueError):
            domains.build_ingresses(fixture(), ["vllm"])

    def test_certificate_must_be_issued_and_cover_hosts(self):
        config = fixture()
        good = {"Status": "ISSUED", "DomainName": "*.example.com"}
        domains.assert_certificate(config, good, list(domains.catalog()))
        for bad in (
            {"Status": "PENDING_VALIDATION", "DomainName": "*.example.com"},
            {"Status": "ISSUED", "DomainName": "*.other.com"},
        ):
            with self.assertRaises(ValueError):
                domains.assert_certificate(config, bad, ["mlflow"])

    def test_wrong_cluster_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            domains.assert_context(
                fixture(),
                {
                    "clusters": [
                        {
                            "cluster": {
                                "server": "https://existing-aip.eks.amazonaws.com"
                            }
                        }
                    ]
                },
            )

    def test_matching_cluster_cannot_disable_tls(self):
        with self.assertRaisesRegex(ValueError, "TLS"):
            domains.assert_context(
                fixture(),
                {
                    "clusters": [
                        {
                            "cluster": {
                                "server": fixture()["cluster_endpoint"],
                                "insecure-skip-tls-verify": True,
                            }
                        }
                    ]
                },
            )

    def test_existing_unowned_dns_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "already in use"):
            domains.assert_dns_ownership(
                fixture(), [{"Name": "astra.example.com.", "Type": "A"}], ["inference"]
            )

    def test_existing_owned_dns_is_idempotent(self):
        records = [
            {"Name": "astra.example.com.", "Type": "A"},
            {
                "Name": "_astra-a.astra.example.com.",
                "Type": "TXT",
                "ResourceRecords": [
                    {
                        "Value": '"heritage=external-dns,external-dns/owner=astra-astra-test,external-dns/resource=ingress/gateway/astra-inference"'
                    }
                ],
            },
        ]
        domains.assert_dns_ownership(fixture(), records, ["inference"])
        records[1]["ResourceRecords"][0][
            "Value"
        ] = '"external-dns/owner=astra-astra-test-other"'
        with self.assertRaises(ValueError):
            domains.assert_dns_ownership(fixture(), records, ["inference"])

    def test_failed_preflight_performs_no_mutation(self):
        with patch.object(
            domains, "preflight", side_effect=ValueError("collision")
        ), patch.object(domains, "command") as command:
            with self.assertRaises(ValueError):
                domains.apply_bundle(fixture(), ["inference"], Path("unused"), "test")
            command.assert_not_called()

    def test_argocd_keeps_https_backend(self):
        route = domains.build_ingresses(fixture(), ["argocd"])[0]
        self.assertEqual(
            route["metadata"]["annotations"][domains.ALB + "backend-protocol"], "HTTPS"
        )


if __name__ == "__main__":
    unittest.main()
