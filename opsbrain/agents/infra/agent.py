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

    def list_eks_clusters(self) -> dict[str, Any]:
        if boto3 is None:
            raise InfraClientError("boto3 is not installed; AWS queries are unavailable.")
        try:
            eks = boto3.client("eks", region_name=self.config.aws_region)
            names = eks.list_clusters().get("clusters", [])
            clusters = [
                {
                    "name": name,
                    "status": eks.describe_cluster(name=name)["cluster"]["status"],
                }
                for name in names
            ]
        except (BotoCoreError, BotoClientError) as exc:
            raise InfraClientError(f"Could not query AWS EKS: {exc}") from exc
        return {
            "region": self.config.aws_region,
            "count": len(clusters),
            "clusters": clusters,
        }

    def list_rds_instances(self) -> dict[str, Any]:
        if boto3 is None:
            raise InfraClientError("boto3 is not installed; AWS queries are unavailable.")
        try:
            rds = boto3.client("rds", region_name=self.config.aws_region)
            response = rds.describe_db_instances()
        except (BotoCoreError, BotoClientError) as exc:
            raise InfraClientError(f"Could not query AWS RDS: {exc}") from exc

        instances = [
            {
                "identifier": inst.get("DBInstanceIdentifier"),
                "status": inst.get("DBInstanceStatus"),
                "engine": inst.get("Engine"),
                "instance_class": inst.get("DBInstanceClass"),
            }
            for inst in response.get("DBInstances", [])
        ]
        by_status = Counter(inst["status"] for inst in instances)
        return {
            "region": self.config.aws_region,
            "count": len(instances),
            "status_breakdown": dict(by_status),
            "instances": instances,
        }

    # ── Kubernetes ───────────────────────────────────────────────────────

    def _k8s_available(self) -> bool:
        return k8s_client is not None

    def _ensure_k8s_config(self) -> None:
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

    def _load_k8s(self) -> Any:
        self._ensure_k8s_config()
        return k8s_client.CoreV1Api()

    def _apps_api(self) -> Any:
        self._ensure_k8s_config()
        return k8s_client.AppsV1Api()

    def _metrics_api(self) -> Any:
        self._ensure_k8s_config()
        return k8s_client.CustomObjectsApi()

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

    def list_deployments(self, *, namespace: str | None = None) -> dict[str, Any]:
        api = self._apps_api()
        try:
            deployments = (
                api.list_namespaced_deployment(namespace)
                if namespace
                else api.list_deployment_for_all_namespaces()
            )
        except K8sApiException as exc:
            raise InfraClientError(f"Could not list Kubernetes deployments: {exc}") from exc

        results = []
        for dep in deployments.items:
            status = dep.status
            desired = dep.spec.replicas or 0
            ready = status.ready_replicas or 0
            results.append(
                {
                    "namespace": dep.metadata.namespace,
                    "name": dep.metadata.name,
                    "desired": desired,
                    "ready": ready,
                    "available": status.available_replicas or 0,
                    "updated": status.updated_replicas or 0,
                }
            )
        counts = Counter(
            "healthy" if dep["ready"] == dep["desired"] else "degraded" for dep in results
        )
        return {
            "namespace": namespace,
            "total_deployments": len(results),
            "status_breakdown": dict(counts),
            "deployments": results,
        }

    def get_node_resource_usage(self) -> dict[str, Any]:
        api = self._metrics_api()
        try:
            raw = api.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "nodes")
        except K8sApiException as exc:
            raise InfraClientError(
                f"Could not read node resource usage (metrics-server may not be installed): {exc}"
            ) from exc

        nodes = [
            {
                "name": item.get("metadata", {}).get("name"),
                "cpu": item.get("usage", {}).get("cpu"),
                "memory": item.get("usage", {}).get("memory"),
            }
            for item in raw.get("items", [])
        ]
        return {"total_nodes": len(nodes), "nodes": nodes}

    # ── Aggregate health ─────────────────────────────────────────────────

    def get_health_summary(self) -> dict[str, Any]:
        """Combine AWS, Kubernetes, and Terraform signals into one health snapshot.

        Each check runs independently so one unavailable backend (e.g. no AWS
        credentials in a local dev environment) doesn't block the others.
        """
        summary: dict[str, Any] = {"overall": "healthy", "checks": {}}

        def _run(name: str, fn: Any) -> None:
            try:
                summary["checks"][name] = {"ok": True, "data": fn()}
            except InfraClientError as exc:
                summary["checks"][name] = {"ok": False, "error": str(exc)}
                summary["overall"] = "degraded"

        _run("ec2", self.summarize_ec2)
        _run("eks", self.list_eks_clusters)
        _run("rds", self.list_rds_instances)
        _run("nodes", self.list_nodes)
        _run("pods", self.get_pod_health)
        _run("deployments", self.list_deployments)
        return summary

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
            if "health" in q or "summary" in q or "overall" in q:
                data = self.get_health_summary()
                return {"answer": self._format_health_summary(data), "sources": ["infra:health"], "data": data}
            if "deployment" in q:
                data = self.list_deployments()
                return {"answer": self._format_deployments(data), "sources": ["kubernetes:deployments"], "data": data}
            if "usage" in q or "resource" in q or "cpu" in q or "memory" in q:
                data = self.get_node_resource_usage()
                return {"answer": self._format_usage(data), "sources": ["kubernetes:metrics"], "data": data}
            if "node" in q:
                data = self.list_nodes()
                return {"answer": self._format_nodes(data), "sources": ["kubernetes:nodes"], "data": data}
            if "pod" in q or "kubernetes" in q or "k8s" in q:
                data = self.get_pod_health()
                return {"answer": self._format_pods(data), "sources": ["kubernetes:pods"], "data": data}
            if "terraform" in q or "plan" in q:
                data = self.get_terraform_plan_summary()
                return {"answer": self._format_terraform(data), "sources": ["terraform:plan"], "data": data}
            if "eks" in q:
                data = self.list_eks_clusters()
                return {"answer": self._format_eks(data), "sources": ["aws:eks"], "data": data}
            if "rds" in q or "database" in q:
                data = self.list_rds_instances()
                return {"answer": self._format_rds(data), "sources": ["aws:rds"], "data": data}
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

    @staticmethod
    def _format_deployments(data: dict[str, Any]) -> str:
        if data["total_deployments"] == 0:
            return "No deployments found."
        breakdown = ", ".join(f"{k}: {v}" for k, v in data["status_breakdown"].items())
        return f"{data['total_deployments']} deployment(s) — {breakdown}."

    @staticmethod
    def _format_usage(data: dict[str, Any]) -> str:
        if data["total_nodes"] == 0:
            return "No node metrics available."
        parts = ", ".join(f"{n['name']}: cpu={n['cpu']} mem={n['memory']}" for n in data["nodes"])
        return f"Node resource usage — {parts}."

    @staticmethod
    def _format_eks(data: dict[str, Any]) -> str:
        if data["count"] == 0:
            return f"No EKS clusters found in {data['region']}."
        breakdown = ", ".join(f"{c['name']}: {c['status']}" for c in data["clusters"])
        return f"{data['count']} EKS cluster(s) in {data['region']} — {breakdown}."

    @staticmethod
    def _format_rds(data: dict[str, Any]) -> str:
        if data["count"] == 0:
            return f"No RDS instances found in {data['region']}."
        breakdown = ", ".join(f"{k}: {v}" for k, v in data["status_breakdown"].items())
        return f"{data['count']} RDS instance(s) in {data['region']} — {breakdown}."

    @staticmethod
    def _format_health_summary(data: dict[str, Any]) -> str:
        failed = [name for name, check in data["checks"].items() if not check["ok"]]
        if not failed:
            return f"Infra health: {data['overall']} — all checks passed."
        return f"Infra health: {data['overall']} — failed checks: {', '.join(failed)}."
