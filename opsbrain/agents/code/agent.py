"""Code agent utilities for GitHub pull requests and Actions CI status."""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(slots=True)
class CodeConfig:
    github_api_base_url: str = field(
        default_factory=lambda: os.getenv(
            "GITHUB_API_BASE_URL", "https://api.github.com"
        ).rstrip("/")
    )
    github_token: str = field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    github_repo: str = field(default_factory=lambda: os.getenv("GITHUB_REPO", ""))
    timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("CODE_TIMEOUT_SECONDS", "10"))
    )


class CodeClientError(RuntimeError):
    """Raised when GitHub cannot be queried successfully."""


class CodeAgent:
    """Answer questions about pull requests and CI/CD pipeline status via the GitHub API."""

    def __init__(self, config: CodeConfig | None = None) -> None:
        self.config = config or CodeConfig()

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "repo": self.config.github_repo or None,
            "github_token_configured": bool(self.config.github_token),
        }

    # ── Pull requests ────────────────────────────────────────────────────

    def list_pull_requests(
        self, *, state: str = "open", limit: int = 10
    ) -> dict[str, Any]:
        self._require_repo()
        payload = self._request_json(
            "GET",
            f"/repos/{self.config.github_repo}/pulls",
            params={"state": state, "per_page": min(limit, 100)},
        )
        pulls = [self._normalize_pr(pr) for pr in payload]
        return {"repo": self.config.github_repo, "state": state, "count": len(pulls), "pull_requests": pulls}

    def get_pull_request(self, number: int) -> dict[str, Any]:
        self._require_repo()
        payload = self._request_json(
            "GET", f"/repos/{self.config.github_repo}/pulls/{number}"
        )
        return self._normalize_pr(payload, detailed=True)

    def get_pull_request_status(self, number: int) -> dict[str, Any]:
        """Combined check-run + status summary for a PR's head commit."""
        pr = self.get_pull_request(number)
        sha = pr["head_sha"]
        checks_payload = self._request_json(
            "GET", f"/repos/{self.config.github_repo}/commits/{sha}/check-runs"
        )
        check_runs = [
            {
                "name": run.get("name"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
            }
            for run in checks_payload.get("check_runs", [])
        ]
        conclusions = Counter(run["conclusion"] or run["status"] for run in check_runs)
        overall = "success"
        if any(run["conclusion"] == "failure" for run in check_runs):
            overall = "failure"
        elif any(run["status"] != "completed" for run in check_runs):
            overall = "pending"
        elif not check_runs:
            overall = "unknown"
        return {
            "number": number,
            "head_sha": sha,
            "overall": overall,
            "breakdown": dict(conclusions),
            "check_runs": check_runs,
        }

    # ── GitHub Actions ───────────────────────────────────────────────────

    def list_workflow_runs(
        self, *, branch: str | None = None, status: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        self._require_repo()
        params: dict[str, Any] = {"per_page": min(limit, 100)}
        if branch:
            params["branch"] = branch
        if status:
            params["status"] = status
        payload = self._request_json(
            "GET",
            f"/repos/{self.config.github_repo}/actions/runs",
            params=params,
        )
        runs = [self._normalize_run(run) for run in payload.get("workflow_runs", [])]
        return {"repo": self.config.github_repo, "count": len(runs), "workflow_runs": runs}

    def summarize_ci(self, *, branch: str | None = None) -> dict[str, Any]:
        """Latest run per workflow, so you can see build/test/deploy health at a glance."""
        runs_payload = self.list_workflow_runs(branch=branch, limit=50)
        latest_by_workflow: dict[str, dict[str, Any]] = {}
        for run in runs_payload["workflow_runs"]:
            name = run["workflow_name"]
            if name not in latest_by_workflow:
                latest_by_workflow[name] = run
        return {
            "repo": self.config.github_repo,
            "branch": branch,
            "workflows": list(latest_by_workflow.values()),
        }

    # ── Question routing ─────────────────────────────────────────────────

    def ask(self, question: str) -> dict[str, Any]:
        """Best-effort natural-language entry point used by the orchestrator's /query contract."""
        if not self.config.github_repo:
            return {
                "answer": "No GitHub repo is configured (set GITHUB_REPO=owner/repo).",
                "sources": [],
            }

        q = question.lower()
        try:
            number_match = re.search(r"#?(\d+)", question)
            if number_match and ("pr" in q or "pull request" in q or "#" in question):
                number = int(number_match.group(1))
                status = self.get_pull_request_status(number)
                return {
                    "answer": (
                        f"PR #{number} CI status: {status['overall']} "
                        f"({', '.join(f'{k}: {v}' for k, v in status['breakdown'].items()) or 'no check runs'})."
                    ),
                    "sources": [f"github:pull/{number}"],
                    "data": status,
                }
            if "ci" in q or "pipeline" in q or "workflow" in q or "build" in q or "action" in q:
                summary = self.summarize_ci()
                lines = [
                    f"{wf['workflow_name']}: {wf['conclusion'] or wf['status']}"
                    for wf in summary["workflows"]
                ]
                answer = (
                    "Latest workflow runs — " + "; ".join(lines)
                    if lines
                    else "No workflow runs found."
                )
                return {"answer": answer, "sources": ["github:actions/runs"], "data": summary}

            # default: open PR count
            pulls = self.list_pull_requests(state="open")
            answer = f"{pulls['count']} open pull request(s) on {pulls['repo']}."
            return {"answer": answer, "sources": ["github:pulls"], "data": pulls}
        except CodeClientError as exc:
            return {"answer": str(exc), "sources": []}

    # ── internals ─────────────────────────────────────────────────────────

    def _require_repo(self) -> None:
        if not self.config.github_repo:
            raise CodeClientError("GITHUB_REPO is not configured (expected 'owner/repo').")

    def _normalize_pr(self, pr: dict[str, Any], *, detailed: bool = False) -> dict[str, Any]:
        base = {
            "number": pr.get("number"),
            "title": pr.get("title"),
            "state": pr.get("state"),
            "author": (pr.get("user") or {}).get("login"),
            "branch": (pr.get("head") or {}).get("ref"),
            "head_sha": (pr.get("head") or {}).get("sha"),
            "draft": pr.get("draft", False),
            "url": pr.get("html_url"),
        }
        if detailed:
            base["mergeable"] = pr.get("mergeable")
            base["merged"] = pr.get("merged", False)
        return base

    def _normalize_run(self, run: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": run.get("id"),
            "workflow_name": run.get("name"),
            "branch": run.get("head_branch"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "run_number": run.get("run_number"),
            "url": run.get("html_url"),
            "created_at": run.get("created_at"),
        }

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.config.github_api_base_url}{path}"
        if params:
            encoded = urlencode({k: v for k, v in params.items() if v is not None})
            url = f"{url}?{encoded}"

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.config.github_token:
            headers["Authorization"] = f"Bearer {self.config.github_token}"

        request = Request(url, method=method, headers=headers)
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            message = exc.read().decode("utf-8", errors="ignore").strip()
            raise CodeClientError(
                f"{method} {url} failed with HTTP {exc.code}: {message or exc.reason}"
            ) from exc
        except URLError as exc:
            raise CodeClientError(f"Could not reach GitHub at {url}: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise CodeClientError(f"GitHub returned invalid JSON for {url}.") from exc
