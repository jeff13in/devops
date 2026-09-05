# OpsBrain — Terraform root module
# Provisions all AWS infrastructure for the platform.
#
# Usage:
#   terraform init
#   terraform plan -var="db_password=<secret>"
#   terraform apply -var="db_password=<secret>"

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
  }

  # Remote state — create the S3 bucket manually before the first apply
  backend "s3" {
    bucket = "opsbrain-terraform-state"
    key    = "opsbrain/terraform.tfstate"
    region = "us-east-1"
    # Enable state locking via DynamoDB
    dynamodb_table = "opsbrain-terraform-lock"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
