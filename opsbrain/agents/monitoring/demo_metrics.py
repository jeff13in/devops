"""Expose deterministic kube-state-metrics-shaped data for local development."""

from http.server import BaseHTTPRequestHandler, HTTPServer


METRICS = b"""# HELP kube_pod_status_phase The pods current phase.
# TYPE kube_pod_status_phase gauge
kube_pod_status_phase{namespace="demo",pod="api-0",phase="Running"} 1
kube_pod_status_phase{namespace="demo",pod="worker-0",phase="Running"} 1
# HELP kube_pod_status_ready The pod readiness condition.
# TYPE kube_pod_status_ready gauge
kube_pod_status_ready{namespace="demo",pod="api-0",condition="true"} 1
kube_pod_status_ready{namespace="demo",pod="worker-0",condition="true"} 0
# HELP kube_pod_container_status_restarts_total Container restart count.
# TYPE kube_pod_container_status_restarts_total counter
kube_pod_container_status_restarts_total{namespace="demo",pod="api-0",container="api"} 0
kube_pod_container_status_restarts_total{namespace="demo",pod="worker-0",container="worker"} 3
# HELP kube_pod_container_status_ready Container readiness.
# TYPE kube_pod_container_status_ready gauge
kube_pod_container_status_ready{namespace="demo",pod="api-0",container="api"} 1
kube_pod_container_status_ready{namespace="demo",pod="worker-0",container="worker"} 0
# HELP kube_pod_container_status_waiting_reason Container waiting reason.
# TYPE kube_pod_container_status_waiting_reason gauge
kube_pod_container_status_waiting_reason{namespace="demo",pod="worker-0",container="worker",reason="CrashLoopBackOff"} 1
"""


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if self.path != "/metrics":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(METRICS)))
        self.end_headers()
        self.wfile.write(METRICS)

    def log_message(self, format: str, *args: object) -> None:
        return


HTTPServer(("0.0.0.0", 9100), MetricsHandler).serve_forever()
