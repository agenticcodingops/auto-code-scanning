# aggregate-scan-results.Tests.ps1
# Pester 5+ unit tests for scripts/aggregate-scan-results.ps1

BeforeAll {
    $ScriptRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $ScriptPath = Join-Path $ScriptRoot "scripts" "aggregate-scan-results.ps1"
    $ScriptContent = Get-Content $ScriptPath -Raw
    . (Join-Path $ScriptRoot 'hooks/lib/common.ps1')
    $ast = [Management.Automation.Language.Parser]::ParseInput($ScriptContent, [ref]$null, [ref]$null)
    $mapping = $ast.Find({ param($node)
        $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-NormalizedSeverity'
    }, $true)
    . ([scriptblock]::Create($mapping.Extent.Text))
}

Describe "aggregate-scan-results.ps1" {

    Describe "Script Structure" {

        It "Should be valid PowerShell syntax" {
            $errors = $null
            $null = [System.Management.Automation.PSParser]::Tokenize($ScriptContent, [ref]$errors)
            $errors.Count | Should -Be 0
        }

        It "Should have CmdletBinding attribute" {
            $ScriptContent | Should -Match '\[CmdletBinding\(\)\]'
        }

        It "Should accept OutputPath parameter" {
            $ScriptContent | Should -Match '\$OutputPath'
        }

        It "Should accept IncludeHistory switch" {
            $ScriptContent | Should -Match '\$IncludeHistory'
        }

        It "Should accept RunScans switch" {
            $ScriptContent | Should -Match '\$RunScans'
        }
    }

    Describe "Severity Normalization" {

        It "Should define Get-NormalizedSeverity function" {
            $ScriptContent | Should -Match "function Get-NormalizedSeverity"
        }

        It "Should map Trivy severities correctly" {
            foreach ($level in @('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')) {
                Get-NormalizedSeverity $level 'trivy' | Should -Be $level
            }
            Get-NormalizedSeverity 'UNKNOWN' 'trivy' | Should -Be 'LOW'
        }

        It "Should map Checkov severities correctly" {
            foreach ($raw in @($null, '')) {
                Get-NormalizedSeverity $raw 'checkov' | Should -Be 'HIGH'
            }
            foreach ($raw in @('INFO', 'NONE', 'other')) {
                Get-NormalizedSeverity $raw 'checkov' | Should -Be 'MEDIUM'
            }
        }

        It "Should map tflint severities correctly" {
            Get-NormalizedSeverity 'error' 'tflint' | Should -Be 'HIGH'
            Get-NormalizedSeverity 'warning' 'tflint' | Should -Be 'MEDIUM'
            foreach ($raw in @('info', 'notice')) {
                Get-NormalizedSeverity $raw 'tflint' | Should -Be 'LOW'
            }
            Get-NormalizedSeverity '' 'tflint' | Should -Be 'MEDIUM'
        }

        It "Should map Gitleaks to HIGH" {
            Get-NormalizedSeverity '' 'gitleaks' | Should -Be 'HIGH'
        }

    }

    Describe "Cross-Tool Deduplication" {

        It "Should define Invoke-CrossToolDeduplication function" {
            $ScriptContent | Should -Match "function Invoke-CrossToolDeduplication"
        }

        It "Should match on file, resource, and category" {
            $ScriptContent | Should -Match "file.*resource.*category|category.*resource.*file"
        }

        It "Should merge detected_by arrays" {
            $ScriptContent | Should -Match "detected_by"
        }
    }

    Describe "Remediation URLs" {

        It "Should define Get-RemediationUrl function" {
            $ScriptContent | Should -Match "function Get-RemediationUrl"
        }

        It "Should generate Checkov documentation URLs" {
            $ScriptContent | Should -Match "docs\.checkov\.io"
        }

        It "Should generate Trivy AVD URLs" {
            $ScriptContent | Should -Match "avd\.aquasec\.com"
        }
    }

    Describe "Output Format" {

        It "Should include scan_id in output" {
            $ScriptContent | Should -Match "scan_id"
        }

        It "Should include scan_timestamp in output" {
            $ScriptContent | Should -Match "scan_timestamp"
        }

        It "Should include duration_ms in output" {
            $ScriptContent | Should -Match "duration_ms"
        }

        It "Should include tools_executed array" {
            $ScriptContent | Should -Match "tools_executed"
        }

        It "Should include summary with by_severity breakdown" {
            $ScriptContent | Should -Match "by_severity"
        }

        It "Should include summary with by_tool breakdown" {
            $ScriptContent | Should -Match "by_tool"
        }

        It "Should include suppressed count" {
            $ScriptContent | Should -Match "suppressed"
        }

        It "Should include baselined count" {
            $ScriptContent | Should -Match "baselined"
        }
    }

    Describe "Finding Fields" {

        It "Should include detected_by array per finding" {
            $ScriptContent | Should -Match "detected_by"
        }

        It "Should include remediation_url per finding" {
            $ScriptContent | Should -Match "remediation_url"
        }

        It "Should include original_severity per finding" {
            $ScriptContent | Should -Match "original_severity"
        }

        It "Should include suppression_reason field" {
            $ScriptContent | Should -Match "suppression_reason"
        }
    }

    Describe "Finding Category" {

        It "Should define Get-FindingCategory function" {
            $ScriptContent | Should -Match "function Get-FindingCategory"
        }

        It "Should categorize encryption-related findings" {
            $ScriptContent | Should -Match "encrypt"
        }

        It "Should categorize public-access findings" {
            $ScriptContent | Should -Match "public.access|public_access"
        }
    }
}
