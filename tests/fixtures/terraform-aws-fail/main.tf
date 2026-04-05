# WARNING: This file intentionally has AWS security issues for testing
# It should FAIL trivy-iac and checkov-terraform hooks
resource "aws_s3_bucket" "insecure" {
  bucket = "my-insecure-bucket"
  # Missing: encryption, public access block, versioning, logging
}

resource "aws_security_group" "open" {
  name = "open-sg"
  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"] # Open to the world
  }
}
