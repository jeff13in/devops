# RDS PostgreSQL instance for pgvector (agent memory + vector store).
# The pgvector extension is enabled via a custom parameter group.

resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnet-group"
  subnet_ids = [for s in aws_subnet.private : s.id]
}

resource "aws_security_group" "rds" {
  name   = "${var.project_name}-rds-sg"
  vpc_id = aws_vpc.main.id

  # Allow inbound Postgres only from within the VPC
  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Custom parameter group to allow the pgvector extension
resource "aws_db_parameter_group" "postgres" {
  name   = "${var.project_name}-pg16"
  family = "postgres16"

  parameter {
    name  = "shared_preload_libraries"
    value = "pg_stat_statements"
  }
}

resource "aws_db_instance" "main" {
  identifier        = "${var.project_name}-postgres"
  engine            = "postgres"
  engine_version    = "16.2"
  instance_class    = var.db_instance_class
  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = "opsbrain"
  username = "opsbrain"
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.postgres.name

  multi_az            = true   # HA failover
  skip_final_snapshot = false
  final_snapshot_identifier = "${var.project_name}-final-snapshot"

  backup_retention_period = 7
  deletion_protection     = true
}

output "rds_endpoint" {
  description = "RDS PostgreSQL connection endpoint"
  value       = aws_db_instance.main.endpoint
  sensitive   = true
}
