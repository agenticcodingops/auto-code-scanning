# ============================================================================
# TFLINT CONFIGURATION - AWS
# auto-code-scanning
#
# tflint is a Terraform linter that checks for:
# - AWS-specific best practices
# - Terraform coding conventions
# - Potential errors and deprecations
#
# All checks run LOCALLY - no code is uploaded to external services.
#
# Manual run:
#   tflint --recursive --config=.scanning/configs/.tflint.hcl
#
# Initialize plugins:
#   tflint --init --config=.scanning/configs/.tflint.hcl
#
# Documentation:
#   https://github.com/terraform-linters/tflint
#   https://github.com/terraform-linters/tflint-ruleset-aws
# ============================================================================

config {
  # Module inspection mode
  call_module_type = "local"

  # Force mode - don't fail on warnings
  force = false
}

# ============================================================================
# TERRAFORM PLUGIN (shared across all providers)
# Provides general Terraform best practice rules
# ============================================================================
plugin "terraform" {
  enabled = true
  version = "0.5.0"
  source  = "github.com/terraform-linters/tflint-ruleset-terraform"
}

# ============================================================================
# AWS PLUGIN
# Provides AWS-specific rules and best practices
# ============================================================================
plugin "aws" {
  enabled = true
  version = "0.29.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"

  # Deep checking requires AWS credentials - disabled for local scanning
  deep_check = false
}

# ============================================================================
# TERRAFORM RULES - Best Practices
# ============================================================================

rule "terraform_deprecated_interpolation" {
  enabled = true
}

rule "terraform_deprecated_index" {
  enabled = true
}

rule "terraform_unused_declarations" {
  enabled = true
}

rule "terraform_comment_syntax" {
  enabled = true
}

rule "terraform_documented_outputs" {
  enabled = true
}

rule "terraform_documented_variables" {
  enabled = true
}

rule "terraform_typed_variables" {
  enabled = true
}

rule "terraform_module_pinned_source" {
  enabled = true
}

rule "terraform_naming_convention" {
  enabled = true
  format  = "snake_case"
}

rule "terraform_standard_module_structure" {
  enabled = true
}

rule "terraform_workspace_remote" {
  enabled = true
}

# ============================================================================
# AWS RULES - Security & Best Practices
# ============================================================================

rule "aws_resource_missing_tags" {
  enabled = true
  tags = [
    "Environment",
    "Project",
    "Owner",
    "ManagedBy"
  ]
}
