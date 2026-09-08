"""Infra agent utilities for AWS, Kubernetes, and Terraform state."""

from __future__ import annotations

import json
import os
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from shutil import which
from typing import Any

try:
    import boto3
    from botocore.exceptions import BotoCoreError
    from botocore.exceptions import ClientError as BotoClientError
except ImportError:  # pragma: no cover - handled at runtime by capability checks
    boto3 = None
    BotoCoreError = BotoClientError = Exception

try:
    from kubernetes import client as k8s_client
    from kubernetes import config as k8s_config
    from kubernetes.client.exceptions import ApiException as K8sApiException
except ImportError:  # pragma: no cover - handled at runtime by capability checks
    k8s_client = k8s_config = None
    K8sApiException = Exception


class InfraClientError(RuntimeError):
    """Raised when an infrastructure backend cannot be queried successfully."""


@dataclass(slots=True)
class InfraConfig:
    aws_region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))
    kubeconfig_path: str | None = field(
        default_factory=lambda: os.getenv("KUBECONFIG") or None
    )
    kube_in_cluster: bool = field(
        default_factory=lambda: os.getenv("KUBE_IN_CLUSTER", "false").lower() == "true"
    )
    terraform_dir: str = field(
        default_factory=lambda: os.getenv("TERRAFORM_DIR", "./infra/terraform")
    )
    terraform_binary: str = field(
        default_factory=lambda: os.getenv("TERRAFORM_BINARY", "terraform")
    )
    timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("INFRA_TIMEOUT_SECONDS", "20"))
    )


class InfraAgent:
    """Check AWS resource state, Kubernetes pod/node health, and Terraform plan status."""

    def __init__(self, config: InfraConfig | None = None) -> None:
        self.config = config or InfraConfig()
        self._k8s_loaded = False

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "capabilities": {
                "aws": self._aws_available(),
                "kubernetes": self._k8s_available(),
                "terraform": self._terraform_available(),
            },
        }

    # ── AWS ──────────────────────────────────────────────────────────────

    def _aws_available(self) -> bool:
        return boto3 is not None

    def list_ec2_instances(self, *, state: str | None = None) -> dict[str, Any]:
        if boto3 is None:
            raise InfraClientError("boto3 is not installed; AWS queries are unavailable.")
        try:
            ec2 = boto3.client("ec2", region_name=self.config.aws_region)
            filters = [{"Name": "instance-state-name", "Values": [state]}] if state else []
            response = ec2.describe_instances(Filters=filters)
        except (BotoCoreError, BotoClientError) as exc:
            raise InfraClientError(f"Could not query AWS EC2: {exc}") from exc

        instances = []
        for reservation in response.get("Reservations", []):
            for inst in reservation.get("Instances", []):
                name = next(
                    (tag["Value"] for tag in inst.get("Tags", []) if tag["Key"] == "Name"),
                    None,
                )
                instances.append(
                    {
                        "instance_id": inst.get("InstanceId"),
                        "name": name,
                        "state": inst.get("State", {}).get("Name"),
                        "instance_type": inst.get("InstanceType"),
                        "availability_zone": inst.get("Placement", {}).get("AvailabilityZone"),
                        "private_ip": inst.get("PrivateIpAddress"),
                        "public_ip": inst.get("PublicIpAddress"),
                    }
                )
        return {
            "region": self.config.aws_region,
            "count": len(instances),
            "instances": instances,
        }

    def summarize_ec2(self) -> dict[str, Any]:
        data = self.list_ec2_instances()
        by_state = Counter(inst["state"] for inst in data["instances"])
        return {
            "region": data["region"],
            "total": data["count"],
            "state_breakdown": dict(by_state),
        }

    # ── Kubernetes ───────────────────────────────────────────────────────

    def _k8s_available(self) -> bool:
        return k8s_client is not None

    def _load_k8s(self) -> Any:
        if k8s_client is None:
            raise InfraClientError("kubernetes client library is not installed.")
        if not self._k8s_loaded:
            try:
                if self.config.kube_in_cluster:
                    k8s_config.load_incluster_config()
                else:
                    k8s_config.load_kube_config(config_file=self.config.kubeconfig_path)
            except Exception as exc:
                raise InfraClientError(f"Could not load Kubernetes config: {exc}") from exc
            self._k8s_loaded = True
        return k8s_client.CoreV1Api()

    def get_pod_health(self, *, namespace: str | None = None) -> dict[str, Any]:
        api = self._load_k8s()
        try:
            pods = (
                api.list_namespaced_pod(namespace)
                if namespace
                else api.list_pod_for_all_namespaces()
            )
        except K8sApiException as exc:
            raise InfraClientError(f"Could not list Kubernetes pods: {exc}") from exc

        results = []
        for pod in pods.items:
            statuses = pod.status.container_statuses or []
            restarts = sum(status.restart_count for status in statuses)
            ready = bool(statuses) and all(status.ready for status in statuses)
            results.append(
                {
                    "namespace": pod.metadata.namespace,
                    "pod": pod.metadata.name,
                    "phase": pod.status.phase,
                    "ready": ready,
                    "restarts": restarts,
                    "node": pod.spec.node_name,
                }
            )
        counts = Counter(
            "healthy" if pod["ready"] and pod["phase"] == "Running" else "degraded"
            for pod in results
        )
        return {
            "namespace": namespace,
            "total_pods": len(results),
            "status_breakdown": dict(counts),
            "pods": results,
        }

    def list_nodes(self) -> dict[str, Any]:
        api = self._load_k8s()
        try:
            nodes = api.list_node()
        except K8sApiException as exc:
            raise InfraClientError(f"Could not list Kubernetes nodes: {exc}") from exc

        results = []
        for node in nodes.items:
            conditions = {c.type: c.status for c in (node.status.conditions or [])}
            results.append(
                {
                    "name": node.metadata.name,
                    "ready": conditions.get("Ready") == "True",
                    "capacity": dict(node.status.capacity or {}),
                }
            )
        return {"total_nodes": len(results), "nodes": results}

    # ── Terraform ────────────────────────────────────────────────────────

    def _terraform_available(self) -> bool:
        return which(self.config.terraform_binary) is not None

    def get_terraform_plan_summary(self, *, plan_file: str | None = None) -> dict[str, Any]:
        if not self._terraform_available():
            raise InfraClientError(
                f"Terraform binary '{self.config.terraform_binary}' was not found on PATH."
            )
        args = [self.config.terraform_binary, "show", "-json"]
        if plan_file:
            args.append(plan_file)
        try:
            result = subprocess.run(
                args,
                cwd=self.config.terraform_dir,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise InfraClientError(f"Could not run terraform show: {exc}") from exc

        if result.returncode != 0:
            raise InfraClientError(
                f"terraform show exited {result.returncode}: {result.stderr.strip()}"
            )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise InfraClientError("terraform show returned invalid JSON.") from exc

        changes = payload.get("resource_changes", [])
        actions = Counter(
            action
            for change in changes
            for action in change.get("change", {}).get("actions", [])
        )
        return {
            "terraform_dir": self.config.terraform_dir,
            "resource_change_count": len(changes),
            "action_breakdown": dict(actions),
        }

    # ── Question routing ─────────────────────────────────────────────────

    def ask(self, question: str) -> dict[str, Any]:
        """Best-effort natural-language entry point used by the orchestrator's /query contract."""
        q = question.lower()
        try:
            if "node" in q:
                data = self.list_nodes()
                return {"answer": self._format_nodes(data), "sources": ["kubernetes:nodes"], "data": data}
            if "pod" in q or "kubernetes" in q or "k8s" in q:
                data = self.get_pod_health()
                return {"answer": self._format_pods(data), "sources": ["kubernetes:pods"], "data": data}
            if "terraform" in q or "plan" in q:
                data = self.get_terraform_plan_summary()
                return {"answer": self._format_terraform(data), "sources": ["terraform:plan"], "data": data}
            data = self.summarize_ec2()
            return {"answer": self._format_ec2_summary(data), "sources": ["aws:ec2"], "data": data}
        except InfraClientError as exc:
            return {"answer": str(exc), "sources": []}

    @staticmethod
    def _format_ec2_summary(data: dict[str, Any]) -> str:
        if data["total"] == 0:
            return f"No EC2 instances found in {data['region']}."
        breakdown = ", ".join(f"{k}: {v}" for k, v in data["state_breakdown"].items())
        return f"{data['total']} EC2 instance(s) in {data['region']} — {breakdown}."

    @staticmethod
    def _format_pods(data: dict[str, Any]) -> str:
        if data["total_pods"] == 0:
            return "No pods found."
        breakdown = ", ".join(f"{k}: {v}" for k, v in data["status_breakdown"].items())
        return f"{data['total_pods']} pod(s) — {breakdown}."

    @staticmethod
    def _format_nodes(data: dict[str, Any]) -> str:
        ready = sum(1 for node in data["nodes"] if node["ready"])
        return f"{ready}/{data['total_nodes']} node(s) ready."

    @staticmethod
    def _format_terraform(data: dict[str, Any]) -> str:
        if data["resource_change_count"] == 0:
            return "Terraform plan shows no pending resource changes."
        breakdown = ", ".join(f"{k}: {v}" for k, v in data["action_breakdown"].items())
        return f"Terraform plan has {data['resource_change_count']} change(s) — {breakdown}."
