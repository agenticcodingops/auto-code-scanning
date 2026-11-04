BeforeAll {
    $root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $savedCommonLoaded = $global:_CommonPS1Loaded
    $global:_CommonPS1Loaded = $false
    $fixtureScripts = Join-Path $root 'scripts'
    $content = (Get-Content (Join-Path $root 'scripts/verify-scanning.ps1') -Raw).Replace('$PSScriptRoot', '$fixtureScripts')
    $PSScriptRoot = Join-Path $root 'scripts'
    . ([scriptblock]::Create($content.Substring(0, $content.IndexOf('Write-Header "Terraform'))))
    $tokens = $null
    $parseErrors = $null
    $ast = [Management.Automation.Language.Parser]::ParseInput($content, [ref]$tokens, [ref]$parseErrors)
    $check = $ast.Find({ param($node)
        $node -is [Management.Automation.Language.TryStatementAst] -and
        $node.Extent.Text.Contains('$hookResult = &')
    }, $true)
    $verifyHooks = [scriptblock]::Create($check.Extent.Text)
    $setup = (Get-Content (Join-Path $root 'scripts/setup-scan-fix.ps1') -Raw).Replace('$PSScriptRoot', '$fixtureScripts')
    $preflight = [scriptblock]::Create($setup.Substring(0, $setup.IndexOf('# Resolve every executable')))
}

AfterAll { $global:_CommonPS1Loaded = $savedCommonLoaded }

Describe 'Hook verifier interpreter identity' {
    BeforeEach {
        $repo = New-Item -ItemType Directory -Path (Join-Path $TestDrive 'consumer') -Force
        Push-Location $repo.FullName
        $Script:FailedChecks = 0
        $Script:PassedChecks = 0
        $PSScriptRoot = Join-Path $root 'scripts'
        $HooksRunner = 'lefthook'
        $Tier = 'strict'
        $runnerConfig = 'lefthook.yml'
    }

    AfterEach { Pop-Location }

    It 'Invokes the original absolute interpreter after checking its canonical target' {
        $script:original = Join-Path $TestDrive 'environment-python.ps1'
        $script:canonical = Join-Path $TestDrive 'base-python.ps1'
        Set-Content $script:original '$global:LASTEXITCODE = 0; "ENVIRONMENT_REACHED"'
        Set-Content $script:canonical 'throw "Base interpreter loses environment packages"'
        Mock Get-Command { [pscustomobject]@{ Source = $script:original } }
        Mock Resolve-ExternalRealPath {
            if ($Path -eq $script:original) { return $script:canonical }
            return [IO.Path]::GetFullPath($Path)
        }
        & $verifyHooks
        $Script:FailedChecks | Should -Be 0
        $Script:PassedChecks | Should -Be 1
        Should -Invoke Resolve-ExternalRealPath -ParameterFilter { $Path -eq $script:original }
    }

    It 'Rejects a repository interpreter supplied through an existing Windows short path' -Skip:([Environment]::OSVersion.Platform -ne 'Win32NT') {
        $programs = $env:ProgramFiles
        if (-not ('VerifyShortPathFixture' -as [type])) {
            Add-Type @'
using System.Runtime.InteropServices;
using System.Text;
public static class VerifyShortPathFixture {
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    public static extern uint GetShortPathName(string path, StringBuilder output, uint size);
}
'@
        }
        $buffer = [Text.StringBuilder]::new(32768)
        $length = [VerifyShortPathFixture]::GetShortPathName($programs, $buffer, $buffer.Capacity)
        if (-not $length -or $buffer.ToString() -eq $programs) {
            Set-ItResult -Skipped -Because 'Short names unavailable'
            return
        }
        # Use a pre-existing alias; temporary volumes may have short names disabled.
        $tool = (Microsoft.PowerShell.Core\Get-Command git -CommandType Application | Where-Object {
            $_.Source.StartsWith($programs + '\', [StringComparison]::OrdinalIgnoreCase)
        } | Select-Object -First 1).Source
        if (-not $tool) { Set-ItResult -Skipped -Because 'No executable under the alias fixture'; return }
        $script:shortTool = $buffer.ToString() + $tool.Substring($programs.Length)
        Mock Get-Command { [pscustomobject]@{ Source = $script:shortTool } }
        # Link resolution alone may retain an ordinary directory's short alias.
        Mock Resolve-ExternalRealPath { $Path }
        Mock git { $programs }
        Mock Add-CheckResult {}
        & $verifyHooks
        Should -Invoke Add-CheckResult -Times 1 -Exactly -ParameterFilter {
            -not $Passed -and $Message -like '*outside*'
        }
    }
}

Describe 'Setup repository boundary casing' {
    It 'Uses <Platform> casing for both lexical and canonical tool paths (<Mode>)' -TestCases @(
        @{ Mode = 'lexical'; Platform = 'Win32NT' }
        @{ Mode = 'canonical'; Platform = 'Win32NT' }
        @{ Mode = 'lexical'; Platform = 'Unix' }
        @{ Mode = 'canonical'; Platform = 'Unix' }
    ) {
        param($Mode, $Platform)
        $repo = New-Item -ItemType Directory -Path (Join-Path $TestDrive 'CaseBoundary') -Force
        $PSScriptRoot = Join-Path $root 'scripts'
        # Exercise each platform branch even when this suite runs on Windows.
        $platformPreflight = [scriptblock]::Create($preflight.ToString().Replace(
            '[Environment]::OSVersion.Platform', "[PlatformID]::$Platform"))
        . $platformPreflight -RepoPath $repo.FullName
        $script:casePath = Join-Path (Join-Path $TestDrive 'caseboundary') 'tool.ps1'
        $script:sourcePath = if ($Mode -eq 'lexical') { $script:casePath } else { Join-Path $TestDrive 'external.ps1' }
        Mock Get-Command { [pscustomobject]@{ Source = $script:sourcePath } }
        Mock Resolve-SetupRealPath { $script:casePath }
        if ($Platform -eq 'Win32NT') {
            { Resolve-SetupTool 'fixture' } | Should -Throw '*must resolve outside*'
        } else {
            Resolve-SetupTool 'fixture' | Should -BeExactly $script:casePath
        }
    }
}

Describe 'Verifier tool boundary' {
    BeforeEach {
        $script:savedSnapshot = $env:SCAN_INDEX_SNAPSHOT
        $env:SCAN_INDEX_SNAPSHOT = '1'
        $script:repo = New-Item -ItemType Directory -Path (Join-Path $TestDrive 'tool-consumer') -Force
        Push-Location $script:repo.FullName
    }

    AfterEach {
        Pop-Location
        $env:SCAN_INDEX_SNAPSHOT = $script:savedSnapshot
    }

    It 'Refuses a tool that resolves inside the consumer checkout' {
        $inside = New-Item -ItemType File -Path (Join-Path $script:repo.FullName 'bin/tflint.ps1') -Force
        $script:toolPath = $inside.FullName
        Mock Get-Command { [pscustomobject]@{ Source = $script:toolPath } }
        { Resolve-VerifiedTool -Name tflint -Label TFLint } | Should -Throw '*TFLint must resolve outside*'
    }

    It 'Runs TFLint only through the verified absolute path' {
        $tflintCheck = $ast.Find({ param($node)
            $node -is [Management.Automation.Language.TryStatementAst] -and
            $node.Extent.Text.Contains('SCAN_TFLINT_CONFIG')
        }, $true).Extent.Text
        $tflintCheck | Should -Match 'Resolve-VerifiedTool -Name tflint'
        $tflintCheck | Should -Not -Match '(?m)^\s*tflint\s'
    }

    It 'Returns an external tool path unchanged' {
        $outside = New-Item -ItemType File -Path (Join-Path $TestDrive 'external/tflint.ps1') -Force
        $script:toolPath = $outside.FullName
        Mock Get-Command { [pscustomobject]@{ Source = $script:toolPath } }
        Resolve-VerifiedTool -Name tflint -Label TFLint | Should -BeExactly $script:toolPath
    }

    It 'Rejects an invoked checkout path even when the executable target is external' {
        $inside = New-Item -ItemType File -Path (Join-Path $script:repo.FullName 'bin/python.exe') -Force
        $outside = New-Item -ItemType File -Path (Join-Path $TestDrive 'base/python.exe') -Force
        $script:toolPath = $inside.FullName
        $script:targetPath = $outside.FullName
        Mock Get-Command { [pscustomobject]@{ Source = $script:toolPath } }
        Mock Resolve-ExternalRealPath {
            if ($Path -eq $script:toolPath) { return $script:targetPath }
            return [IO.Path]::GetFullPath($Path)
        }
        { Resolve-VerifiedTool -Name python -Label Python } | Should -Throw '*Python must resolve outside*'
    }
}
