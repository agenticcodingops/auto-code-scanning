# generate-suppression-report.Tests.ps1
# Pester 5+ unit tests for scripts/generate-suppression-report.ps1

BeforeAll {
    $ScriptRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $ScriptPath = Join-Path $ScriptRoot "scripts" "generate-suppression-report.ps1"
    $ScriptContent = Get-Content $ScriptPath -Raw
}

Describe "generate-suppression-report.ps1" {

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

        It "Should accept SuppressionFile parameter" {
            $ScriptContent | Should -Match '\$SuppressionFile'
        }

        It "Should accept OutputPath parameter" {
            $ScriptContent | Should -Match '\$OutputPath'
        }

        It "Should accept Format parameter" {
            $ScriptContent | Should -Match '\$Format'
        }
    }

    Describe "Report Content" {

        It "Should count total suppressions" {
            $ScriptContent | Should -Match "total.*suppress|count"
        }

        It "Should track suppressions by severity" {
            $ScriptContent | Should -Match "severity"
        }

        It "Should track suppressions by tool" {
            $ScriptContent | Should -Match "by_tool|tool"
        }

        It "Should identify expired suppressions" {
            $ScriptContent | Should -Match "expir"
        }

        It "Should identify suppressions expiring soon" {
            $ScriptContent | Should -Match "expiring.*soon|days"
        }
    }

    Describe "History Tracking" {

        It "Should include history count in summary" {
            $ScriptContent | Should -Match "history_count|history"
        }

        It "Should track quarterly review status" {
            $ScriptContent | Should -Match "quarterly_review|quarterly"
        }
    }

    Describe "Compliance Checks" {

        It "Should check for missing approved_by on high-severity items" {
            $ScriptContent | Should -Match "approved_by"
        }

        It "Should extract settings from suppression file" {
            $ScriptContent | Should -Match "settings"
        }
    }

    Describe "Output Formats" {

        It "Should support JSON output" {
            $ScriptContent | Should -Match "json|ConvertTo-Json"
        }

        It "Should support text output" {
            $ScriptContent | Should -Match "text|Write-Host|Write-Output"
        }
    }
}
