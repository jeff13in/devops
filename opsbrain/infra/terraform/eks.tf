# EKS cluster + managed node group for OpsBrain agents.
# Agents are deployed via Helm charts (see /k8s) and managed by ArgoCD.

# ── IAM for EKS ───────────────────────────────────────────────────────────────

resource "aws_iam_role" "eks_cluster" {
  name               = "${var.project_name}-eks-cluster-role"
  assume_role_policy = data.aws_iam_policy_document.eks_assume.json
}

data "aws_iam_policy_document" "eks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  role       = aws_iam_role.eks_cluster.name
}

# ── EKS Cluster ───────────────────────────────────────────────────────────────

resource "aws_eks_cluster" "main" {
  name     = "${var.project_name}-cluster"
  role_arn = aws_iam_role.eks_cluster.arn
  version  = "1.29"

  vpc_config {
    subnet_ids = concat(
      [for s in aws_subnet.public : s.id],
      [for s in aws_subnet.private : s.id],
    )
    endpoint_private_access = true
    endpoint_public_access  = true
  }

  depends_on = [aws_iam_role_policy_attachment.eks_cluster_policy]
}

# ── Node Group IAM ────────────────────────────────────────────────────────────

resource "aws_iam_role" "eks_nodes" {
  name               = "${var.project_name}-eks-node-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy_attachment" "eks_worker_node_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
  role       = aws_iam_role.eks_nodes.name
}

resource "aws_iam_role_policy_attachment" "eks_cni_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
  role       = aws_iam_role.eks_nodes.name
}

resource "aws_iam_role_policy_attachment" "ecr_read_only" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
  role       = aws_iam_role.eks_nodes.name
}

# ── Managed Node Group ────────────────────────────────────────────────────────

resource "aws_eks_node_group" "main" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.project_name}-nodes"
  node_role_arn   = aws_iam_role.eks_nodes.arn
  subnet_ids      = [for s in aws_subnet.private : s.id]

  instance_types = [var.eks_node_instance_type]

  scaling_config {
    desired_size = var.eks_desired_nodes
    min_size     = 1
    max_size     = var.eks_max_nodes
  }

  update_config { max_unavailable = 1 }

  depends_on = [
    aws_iam_role_policy_attachment.eks_worker_node_policy,
    aws_iam_role_policy_attachment.eks_cni_policy,
    aws_iam_role_policy_attachment.ecr_read_only,
  ]
}

# ── ECR Repositories (one per agent) ─────────────────────────────────────────

locals {
  agents = ["rag", "monitoring", "infra", "code", "orchestrator"]
}

resource "aws_ecr_repository" "agents" {
  for_each             = toset(local.agents)
  name                 = "${var.project_name}-${each.key}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration { scan_on_push = true }
}
