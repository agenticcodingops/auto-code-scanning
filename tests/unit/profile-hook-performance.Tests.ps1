# profile-hook-performance.Tests.ps1
# Pester 5+ unit tests for scripts/profile-hook-performance.ps1

BeforeAll {
    $ScriptRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $ScriptPath = Join-Path $ScriptRoot "scripts" "profile-hook-performance.ps1"
    $ScriptContent = Get-Content $ScriptPath -Raw
}

Describe "profile-hook-performance.ps1" {

    Describe "Script Structure" {

        It "Should be valid PowerShell syntax" {
            $errors = $null
            $null = [System.Management.Automation.PSParser]::Tokenize($ScriptContent, [ref]$errors)
            $errors.Count | Should -Be 0
        }

        It "Should have CmdletBinding attribute" {
            $ScriptContent | Should -Match '\[CmdletBinding\(\)\]'
        }
    }

    Describe "Parameters" {

        It "Should accept FixtureDir parameter" {
            $ScriptContent | Should -Match '\$FixtureDir'
        }
    }

    Describe "Hook Coverage" {

        It "Should profile trivy-iac-critical hook" {
            $ScriptContent | Should -Match "trivy-iac-critical"
        }

        It "Should profile trivy-iac-full hook" {
            $ScriptContent | Should -Match "trivy-iac-full"
        }

        It "Should profile trivy-secrets hook" {
            $ScriptContent | Should -Match "trivy-secrets"
        }

        It "Should profile checkov hook" {
            $ScriptContent | Should -Match '"checkov"'
        }

        It "Should profile checkov-strict hook" {
            $ScriptContent | Should -Match "checkov-strict"
        }

        It "Should profile validate-suppressions hook" {
            $ScriptContent | Should -Match "validate-suppressions"
        }

        It "Should profile tflint hook" {
            $ScriptContent | Should -Match '"tflint"'
        }

        It "Should profile gitleaks hook" {
            $ScriptContent | Should -Match "gitleaks"
        }
    }

    Describe "Stage Grouping" {

        It "Should group hooks by pre-commit stage" {
            $ScriptContent | Should -Match "pre-commit"
        }

        It "Should group hooks by pre-push stage" {
            $ScriptContent | Should -Match "pre-push"
        }
    }

    Describe "Performance Targets" {

        It "Should check pre-commit total against 10s target" {
            $ScriptContent | Should -Match "10.*second|10s|10000"
        }

        It "Should check pre-push total against 60s target" {
            $ScriptContent | Should -Match "60.*second|60s|60000"
        }
    }

    Describe "Output" {

        It "Should report per-hook timing" {
            $ScriptContent | Should -Match "duration|time|Measure"
        }

        It "Should report pass/fail for each hook" {
            $ScriptContent | Should -Match "PASS|FAIL|pass|fail"
        }

        It "Should report stage totals" {
            $ScriptContent | Should -Match "total"
        }
    }
}
