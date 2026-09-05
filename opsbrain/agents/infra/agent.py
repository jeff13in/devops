"""Infra Agent logic — Stage 2.

Will use boto3 (AWS), the Kubernetes Python client, and python-hcl2
to inspect live infrastructure state and Terraform plans.
Stub: returns a placeholder until Stage 2 is built.
"""


def run_infra_agent(question: str) -> dict:
    """Check AWS/K8s state and answer infrastructure questions."""
    # TODO Stage 2: kubectl get pods, describe nodes, aws ec2 describe-instances, etc.
    return {
        "answer": "Infra agent not yet implemented (Stage 2).",
        "sources": [],
    }
