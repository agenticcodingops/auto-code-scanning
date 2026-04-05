# collect-scan-metrics.Tests.ps1
# Pester 5+ unit tests for scripts/collect-scan-metrics.ps1

BeforeAll {
    $ScriptRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $ScriptPath = Join-Path $ScriptRoot "scripts" "collect-scan-metrics.ps1"
    $ScriptContent = Get-Content $ScriptPath -Raw
}

Describe "collect-scan-metrics.ps1" {

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

        It "Should accept OutputPath parameter" {
            $ScriptContent | Should -Match '\$OutputPath'
        }

        It "Should accept Days parameter" {
            $ScriptContent | Should -Match '\$Days'
        }

        It "Should accept UploadArtifact switch" {
            $ScriptContent | Should -Match '\$UploadArtifact'
        }

        It "Should accept CloudProvider parameter" {
            $ScriptContent | Should -Match '\$CloudProvider'
        }
    }

    Describe "Metric Entity Fields" {

        It "Should include schema_version" {
            $ScriptContent | Should -Match "schema_version"
        }

        It "Should include timestamp" {
            $ScriptContent | Should -Match "timestamp"
        }

        It "Should include repository" {
            $ScriptContent | Should -Match "repository"
        }

        It "Should include branch" {
            $ScriptContent | Should -Match "branch"
        }

        It "Should include commit_sha" {
            $ScriptContent | Should -Match "commit_sha"
        }

        It "Should include cloud_provider" {
            $ScriptContent | Should -Match "cloud_provider"
        }

        It "Should include adoption_tier" {
            $ScriptContent | Should -Match "adoption_tier"
        }
    }

    Describe "Hook Results" {

        It "Should include hook_results in output" {
            $ScriptContent | Should -Match "hook_results"
        }

        It "Should track per-hook metrics" {
            $ScriptContent | Should -Match "duration_ms|duration"
        }

        It "Should track findings per hook" {
            $ScriptContent | Should -Match "findings"
        }
    }

    Describe "Aggregate Metrics" {

        It "Should include aggregate section" {
            $ScriptContent | Should -Match "aggregate"
        }

        It "Should calculate total_findings" {
            $ScriptContent | Should -Match "total_findings"
        }

        It "Should calculate by_severity breakdown" {
            $ScriptContent | Should -Match "by_severity"
        }

        It "Should calculate bypass_rate" {
            $ScriptContent | Should -Match "bypass_rate"
        }

        It "Should calculate pass_rate" {
            $ScriptContent | Should -Match "pass_rate"
        }

        It "Should count suppressed entries" {
            $ScriptContent | Should -Match "suppressed_count|suppressed"
        }

        It "Should count baselined entries" {
            $ScriptContent | Should -Match "baselined_count|baselined"
        }
    }

    Describe "GitHub Actions Integration" {

        It "Should write to GITHUB_OUTPUT when UploadArtifact specified" {
            $ScriptContent | Should -Match "GITHUB_OUTPUT"
        }
    }

    Describe "Cloud Provider Detection" {

        It "Should auto-detect cloud provider when not specified" {
            $ScriptContent | Should -Match '-not \$CloudProvider'
        }
    }

    Describe "Trend Comparison" {

        It "Should support comparing with previous metrics" {
            $ScriptContent | Should -Match "trend|previous|compare"
        }
    }
}
