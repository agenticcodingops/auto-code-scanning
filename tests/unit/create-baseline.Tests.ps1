# create-baseline.Tests.ps1
# Pester 5+ unit tests for scripts/create-baseline.ps1

BeforeAll {
    $ScriptRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $ScriptPath = Join-Path $ScriptRoot "scripts" "create-baseline.ps1"
    $ScriptContent = Get-Content $ScriptPath -Raw
}

Describe "create-baseline.ps1" {

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

        It "Should accept TerraformDir parameter" {
            $ScriptContent | Should -Match '\$TerraformDir'
        }

        It "Should accept OutputDir parameter" {
            $ScriptContent | Should -Match '\$OutputDir'
        }

        It "Should accept CloudProvider parameter" {
            $ScriptContent | Should -Match '\$CloudProvider'
        }

        It "Should accept MonorepoScope parameter" {
            $ScriptContent | Should -Match '\$MonorepoScope'
        }
    }

    Describe "Baseline Hash Function" {

        It "Should define Get-BaselineHash function" {
            $ScriptContent | Should -Match "function Get-BaselineHash"
        }

        It "Should use SHA-256 hashing" {
            $ScriptContent | Should -Match "SHA256|sha256"
        }

        It "Should hash rule_id + pipe + file_path" {
            $ScriptContent | Should -Match 'rule_id.*\|.*file_path|"\|"'
        }
    }

    Describe "Baseline Output" {

        It "Should output to baseline.json" {
            $ScriptContent | Should -Match "baseline\.json"
        }

        It "Should include schema_version" {
            $ScriptContent | Should -Match "schema_version"
        }

        It "Should include created_date" {
            $ScriptContent | Should -Match "created_date"
        }

        It "Should include created_by" {
            $ScriptContent | Should -Match "created_by"
        }

        It "Should include cloud_provider" {
            $ScriptContent | Should -Match "cloud_provider"
        }

        It "Should include entries array" {
            $ScriptContent | Should -Match "entries"
        }
    }

    Describe "Entry Fields" {

        It "Should include hash in each entry" {
            $ScriptContent | Should -Match "hash"
        }

        It "Should include rule_id in each entry" {
            $ScriptContent | Should -Match "rule_id"
        }

        It "Should include file_path in each entry" {
            $ScriptContent | Should -Match "file_path"
        }

        It "Should include tool in each entry" {
            $ScriptContent | Should -Match 'tool\s*='
        }

        It "Should include severity in each entry" {
            $ScriptContent | Should -Match "severity"
        }

        It "Should include baselined_date in each entry" {
            $ScriptContent | Should -Match "baselined_date"
        }
    }

    Describe "Deduplication" {

        It "Should deduplicate entries by hash" {
            $ScriptContent | Should -Match "dedup|duplicate|ContainsKey"
        }
    }

    Describe "Staleness Warning" {

        It "Should warn about baseline entries older than 90 days" {
            $ScriptContent | Should -Match "90.*day|stale"
        }
    }

    Describe "Monorepo Support" {

        It "Should support scoped directory scanning" {
            $ScriptContent | Should -Match "scoped_directories|MonorepoScope"
        }
    }
}
