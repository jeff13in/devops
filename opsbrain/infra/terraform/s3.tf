# S3 buckets: document store, Terraform state, and ArgoCD artifact storage.

# ── Document / runbook storage ────────────────────────────────────────────────

resource "aws_s3_bucket" "docs" {
  bucket = "${var.project_name}-docs-${var.environment}"
}

resource "aws_s3_bucket_versioning" "docs" {
  bucket = aws_s3_bucket.docs.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "docs" {
  bucket = aws_s3_bucket.docs.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "docs" {
  bucket                  = aws_s3_bucket.docs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ── Terraform remote state bucket (bootstrapped manually) ────────────────────
# This bucket is NOT managed here — it must exist before `terraform init`.
# Listed for documentation purposes only.

# ── Artifact bucket (CI/CD build outputs) ────────────────────────────────────

resource "aws_s3_bucket" "artifacts" {
  bucket = "${var.project_name}-artifacts-${var.environment}"
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    id     = "expire-old-artifacts"
    status = "Enabled"
    expiration { days = 30 }
  }
}

output "docs_bucket_name" {
  value = aws_s3_bucket.docs.bucket
}
