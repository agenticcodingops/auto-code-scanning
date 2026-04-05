# WARNING: This file intentionally contains hardcoded secrets for testing
# Expected: trivy-secrets=Exit1, gitleaks=Exit1
# All other hooks should return Exit 0

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

resource "aws_instance" "example" {
  ami           = "ami-12345678"
  instance_type = "t3.micro"

  # Hardcoded AWS access key - triggers trivy-secrets and gitleaks
  user_data = <<-EOF
    #!/bin/bash
    export AWS_ACCESS_KEY_ID="AKIAQFAKEKEY4TESTING1"
    export AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI/K7MDENG/bPxRfiCYzFAKE40CHAR"
  EOF

  tags = {
    Environment = "test"
  }
}
