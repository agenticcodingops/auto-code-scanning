# ============================================================================
# TFLINT CONFIGURATION - GCP
# auto-code-scanning
#
# tflint with Google Cloud ruleset for Terraform
#
# Manual run:
#   tflint --recursive --config=.scanning/configs/.tflint.hcl
#
# Initialize plugins:
#   tflint --init --config=.scanning/configs/.tflint.hcl
#
# Documentation:
#   https://github.com/terraform-linters/tflint
#   https://github.com/terraform-linters/tflint-ruleset-google
# ============================================================================

config {
  call_module_type = "local"
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
# GCP PLUGIN
# Provides Google Cloud-specific rules and best practices
# ============================================================================
plugin "google" {
  enabled = true
  version = "0.27.1"
  source  = "github.com/terraform-linters/tflint-ruleset-google"
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
