# CRITICAL-only AWS Terraform failure fixture
# Must trigger CRITICAL findings from trivy-iac-critical and checkov
# Expected: trivy-iac-critical=Exit1, trivy-iac-full=Exit1, checkov=Exit1

terraform {
  required_version = ">= 1.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0.0"
    }
  }
}

provider "aws" {
  region = "eu-west-1"
}

# CRITICAL: Security group allowing SSH from anywhere (0.0.0.0/0:22)
# Trivy: AVD-AWS-0107 (CRITICAL) - ingress from 0.0.0.0/0 on port 22
# Checkov: CKV_AWS_24 (CRITICAL) - Ensure no security group allows ingress from 0.0.0.0/0 to port 22
resource "aws_security_group" "open_ssh" {
  name        = "critical-open-ssh"
  description = "CRITICAL: SSH open to the world"

  ingress {
    description = "SSH from anywhere"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Environment = "test"
  }
}

# CRITICAL: Security group allowing RDP from anywhere (0.0.0.0/0:3389)
# Trivy: AVD-AWS-0107 (CRITICAL) - ingress from 0.0.0.0/0 on port 3389
# Checkov: CKV_AWS_25 (CRITICAL) - Ensure no security group allows ingress from 0.0.0.0/0 to port 3389
resource "aws_security_group" "open_rdp" {
  name        = "critical-open-rdp"
  description = "CRITICAL: RDP open to the world"

  ingress {
    description = "RDP from anywhere"
    from_port   = 3389
    to_port     = 3389
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Environment = "test"
  }
}
