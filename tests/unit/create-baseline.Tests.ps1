# create-baseline.Tests.ps1
# Pester 5+ unit tests for scripts/create-baseline.ps1

$ErrorActionPreference = 'Stop'

BeforeAll {
    $ScriptRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $ScriptPath = Join-Path $ScriptRoot "scripts" "create-baseline.ps1"
    $ScriptContent = Get-Content $ScriptPath -Raw
}

Describe 'Baseline Python discovery' {
    BeforeAll {
        $savedCommonLoaded = $global:_CommonPS1Loaded
        $global:_CommonPS1Loaded = $false
        . (Join-Path $ScriptRoot 'hooks/lib/common.ps1')
        $ast = [Management.Automation.Language.Parser]::ParseInput($ScriptContent, [ref]$null, [ref]$null)
        $discovery = $ast.Find({ param($node)
            $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Find-BaselinePython'
        }, $true)
        . ([scriptblock]::Create($discovery.Extent.Text))
    }

    AfterAll { $global:_CommonPS1Loaded = $savedCommonLoaded }

    BeforeEach {
        $onWindows = [Environment]::OSVersion.Platform -eq 'Win32NT'
        $sourceRoot = $ScriptRoot
        $TerraformDir = '.'
        $scopedDirs = @()
        $script:aliasDirectory = New-Item -ItemType Directory -Path (Join-Path $TestDrive 'aliases') -Force
        $script:opaqueAlias = Join-Path $script:aliasDirectory.FullName $(if ($onWindows) { 'python.exe' } else { 'python' })
        Set-Content -LiteralPath $script:opaqueAlias -Value 'must never execute'
        if (-not $onWindows) { & chmod +x $script:opaqueAlias }
        $nextApplication = Join-Path $script:aliasDirectory.FullName $(if ($onWindows) { 'python3.exe' } else { 'python3' })
        Set-Content -LiteralPath $nextApplication -Value 'must only execute the verified path'
        if (-not $onWindows) { & chmod +x $nextApplication }
        $script:fallback = Join-Path $TestDrive 'verified-python.ps1'
        Set-Content -LiteralPath $script:fallback -Value '$global:LASTEXITCODE = 0'
        $script:savedPath = $env:PATH
        $env:PATH = $script:aliasDirectory.FullName + [IO.Path]::PathSeparator + $env:PATH
        Mock Resolve-VerifiedPython {
            if ($Name -eq 'python') {
                Write-Error 'Cannot resolve trusted path link' -ErrorId UnresolvableTrustedPathLink -ErrorAction Stop
            }
            return $script:fallback
        }
    }

    AfterEach { $env:PATH = $script:savedPath }

    It 'Skips an unresolvable alias first on PATH and tries the next application' {
        (Get-Command python -CommandType Application | Select-Object -First 1).Source | Should -Be $script:opaqueAlias
        Find-BaselinePython | Should -Be $script:fallback
        Should -Invoke Resolve-VerifiedPython -Times 1 -Exactly -ParameterFilter { $Name -eq 'python' }
        Should -Invoke Resolve-VerifiedPython -Times 1 -Exactly -ParameterFilter { $Name -eq 'python3' }
    }

    It 'Still stops on every other verification failure' {
        Mock Resolve-VerifiedPython { throw 'Python must resolve outside the scanned and consumer checkouts' }
        { Find-BaselinePython } | Should -Throw '*must resolve outside*'
        Should -Invoke Resolve-VerifiedPython -Times 1 -Exactly
    }
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

    Describe "Occurrence Identity" {
        It "Uses the shared baseline finalizer" {
            $ScriptContent | Should -Match "finalize_baseline.py"
        }
        It "Preserves location and resource metadata" {
            $ScriptContent | Should -Match "end_line"
            $ScriptContent | Should -Match "resource"
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

        It "Should include file in each entry" {
            $ScriptContent | Should -Match "file ="
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
