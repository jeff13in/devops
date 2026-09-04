"""Unit tests for monitoring agent aggregation helpers."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from monitoring.agent import MonitoringAgent


class MonitoringAgentTests(unittest.TestCase):
    def test_summarize_alerts_groups_by_state_and_severity(self) -> None:
        agent = MonitoringAgent()
        alerts = {
            "count": 3,
            "alerts": [
                {
                    "alertname": "HighCPU",
                    "severity": "critical",
                    "state": "active",
                },
                {
                    "alertname": "HighCPU",
                    "severity": "critical",
                    "state": "active",
                },
                {
                    "alertname": "PodCrashLooping",
                    "severity": "warning",
                    "state": "suppressed",
                },
            ],
        }

        with patch.object(agent, "get_alerts", return_value=alerts):
            summary = agent.summarize_alerts()

        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["active"], 2)
        self.assertEqual(summary["suppressed"], 1)
        self.assertEqual(summary["severity_breakdown"]["critical"], 2)
        self.assertEqual(summary["top_alerts"][0], {"alertname": "HighCPU", "count": 2})

    def test_build_pod_health_combines_phase_readiness_restarts_and_wait_reasons(self) -> None:
        agent = MonitoringAgent()

        pods = agent._build_pod_health(
            phase_result=[
                {
                    "metric": {"namespace": "prod", "pod": "api-123", "phase": "Running"},
                    "value": [0, "1"],
                },
                {
                    "metric": {"namespace": "prod", "pod": "worker-456", "phase": "Pending"},
                    "value": [0, "1"],
                },
            ],
            ready_result=[
                {
                    "metric": {"namespace": "prod", "pod": "api-123", "condition": "true"},
                    "value": [0, "1"],
                }
            ],
            restart_result=[
                {
                    "metric": {"namespace": "prod", "pod": "api-123", "container": "api"},
                    "value": [0, "2"],
                }
            ],
            container_ready_result=[
                {
                    "metric": {"namespace": "prod", "pod": "api-123", "container": "api"},
                    "value": [0, "1"],
                },
                {
                    "metric": {"namespace": "prod", "pod": "worker-456", "container": "worker"},
                    "value": [0, "0"],
                },
            ],
            waiting_reason_result=[
                {
                    "metric": {
                        "namespace": "prod",
                        "pod": "worker-456",
                        "container": "worker",
                        "reason": "ImagePullBackOff",
                    },
                    "value": [0, "1"],
                }
            ],
        )

        self.assertEqual(len(pods), 2)
        self.assertEqual(pods[0].pod, "api-123")
        self.assertEqual(pods[0].status, "healthy")
        self.assertEqual(pods[0].restarts, 2)
        self.assertEqual(pods[1].pod, "worker-456")
        self.assertEqual(pods[1].status, "pending")
        self.assertEqual(pods[1].waiting_reasons, ["ImagePullBackOff"])


if __name__ == "__main__":
    unittest.main()
