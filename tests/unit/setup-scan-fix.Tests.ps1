$ErrorActionPreference = 'Stop'

BeforeAll {
    $root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $content = Get-Content (Join-Path $root 'scripts/setup-scan-fix.ps1') -Raw
    $installedTool = (Get-Command git -CommandType Application | Where-Object {
        -not ((Get-Item -LiteralPath $_.Source).Attributes -band [IO.FileAttributes]::ReparsePoint)
    } | Select-Object -First 1).Source
    $savedCommonLoaded = $global:_CommonPS1Loaded
    $global:_CommonPS1Loaded = $false
    . (Join-Path $root 'hooks/lib/common.ps1')
    # Load the actual preflight without running installation or account operations.
    $preflight = [scriptblock]::Create($content.Substring(0, $content.IndexOf('# Resolve every executable')))
    $resolutionStart = $content.IndexOf('# Resolve every executable')
    $eagerResolution = [scriptblock]::Create($content.Substring($resolutionStart, $content.IndexOf('function Info') - $resolutionStart))
    if ([Environment]::OSVersion.Platform -eq 'Win32NT') {
        Add-Type @'
using System.Runtime.InteropServices;
using System.Text;
public static class SetupShortPathFixture {
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern uint GetShortPathName(string path, StringBuilder output, uint size);
}

'@
    }
    function Get-FixtureShortPath([string]$Path) {
        $buffer = [Text.StringBuilder]::new(32768)
        $length = [SetupShortPathFixture]::GetShortPathName($Path, $buffer, $buffer.Capacity)
        if (-not $length -or $length -ge $buffer.Capacity -or $buffer.ToString() -eq $Path) {
            Set-ItResult -Skipped -Because 'Short names are unavailable on this volume'
            return $null
        }
        return $buffer.ToString()
    }
}

AfterAll { $global:_CommonPS1Loaded = $savedCommonLoaded }

Describe 'Setup Python discovery' {
    BeforeEach {
        $destination = New-Item -ItemType Directory -Path (Join-Path $TestDrive 'repo') -Force
        $PSScriptRoot = Join-Path $root 'scripts'
        . $preflight -RepoPath $destination.FullName
        $tokens = $null
        $parseErrors = $null
        $ast = [Management.Automation.Language.Parser]::ParseInput($content, [ref]$tokens, [ref]$parseErrors)
        $discovery = $ast.Find({ param($node)
            $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Find-Py'
        }, $true)
        . ([scriptblock]::Create($discovery.Extent.Text))
        $script:launcher = Join-Path $TestDrive 'launcher.ps1'
        Set-Content -LiteralPath $script:launcher -Value '$global:LASTEXITCODE = 0'
    }

    It 'Continues past unresolved external Python aliases to the launcher' {
        Mock Get-Command {
            [pscustomobject]@{ Source = $(if ($Name -eq 'py') { $script:launcher } else { Join-Path $TestDrive "$Name.exe" }) }
        }
        Mock Resolve-SetupRealPath {
            if ($Path.EndsWith('.exe')) { throw 'Cannot resolve trusted path link' }
            return $Path
        }
        Find-Py | Should -Be $script:launcher
    }

    It 'Still rejects an unresolved Python executable inside the repository' {
        Mock Get-Command { [pscustomobject]@{ Source = Join-Path $RepoPath 'python.exe' } }
        Mock Resolve-SetupRealPath { throw 'Cannot resolve trusted path link' }
        { Find-Py } | Should -Throw '*must resolve outside*'
    }

    It 'Blocks an unresolved external <Tool> identity' -TestCases @(
        @{ Tool = 'lefthook' }
        @{ Tool = 'pre-commit' }
        @{ Tool = 'gh' }
    ) {
        param($Tool)
        $script:unresolvedTool = $Tool
        Mock Get-Command {
            if ($Name -eq $script:unresolvedTool) { [pscustomobject]@{ Source = Join-Path $TestDrive 'external-tool.exe' } }
        }
        Mock Resolve-SetupRealPath { throw 'Cannot resolve trusted path link' }
        { & $eagerResolution } | Should -Throw '*Cannot resolve trusted path link*'
    }
}

Describe 'Setup executable identity' -Skip:([Environment]::OSVersion.Platform -ne 'Win32NT') {
    It 'Rejects an internal tool with the existing short <Side> alias' -TestCases @(
        @{ Side = 'repository' }
        @{ Side = 'executable' }
    ) {
        param($Side)
        $repo = $env:ProgramFiles
        $alias = Get-FixtureShortPath $repo
        if (-not $alias) { return }
        $toolPath = $installedTool
        if (-not $toolPath -or -not $toolPath.StartsWith($repo + '\', [StringComparison]::OrdinalIgnoreCase)) {
            Set-ItResult -Skipped -Because 'No installed executable under the short-path fixture'
            return
        }
        $destination = if ($Side -eq 'repository') { $alias } else { $repo }
        $script:fixtureToolPath = if ($Side -eq 'executable') { $alias + $toolPath.Substring($repo.Length) } else { $toolPath }
        $PSScriptRoot = Join-Path $root 'scripts'
        . $preflight -RepoPath $destination
        Mock Get-Command { [pscustomobject]@{ Source = $script:fixtureToolPath } }
        { Resolve-SetupTool 'lefthook' } | Should -Throw '*must resolve outside*'
    }

    It 'Rejects an internal <Tool> with a short <Side> path' -TestCases @(
        @{ Tool = 'lefthook'; Side = 'repository' }
        @{ Tool = 'lefthook'; Side = 'executable' }
        @{ Tool = 'python'; Side = 'repository' }
        @{ Tool = 'python'; Side = 'executable' }
    ) {
        param($Tool, $Side)
        $repo = New-Item -ItemType Directory -Path (Join-Path $TestDrive 'repository with a long name') -Force
        $toolPath = Join-Path $repo.FullName "$Tool.ps1"
        Set-Content -LiteralPath $toolPath -Value "throw 'tool must not run'"
        $alias = Get-FixtureShortPath $repo.FullName
        if (-not $alias) { return }
        $destination = if ($Side -eq 'repository') { $alias } else { $repo.FullName }
        $script:fixtureToolPath = if ($Side -eq 'executable') { Join-Path $alias "$Tool.ps1" } else { $toolPath }
        # PSScriptRoot is needed by the preflight's shared-library import.
        $PSScriptRoot = Join-Path $root 'scripts'
        . $preflight -RepoPath $destination
        Mock Get-Command { [pscustomobject]@{ Source = $script:fixtureToolPath } }
        { Resolve-SetupTool $Tool } | Should -Throw '*must resolve outside*'
        Test-Path (Join-Path $repo.FullName 'scan-config.yaml') | Should -BeFalse
    }

    It 'Returns the long identity of an external tool given by a short path' {
        $repo = New-Item -ItemType Directory -Path (Join-Path $TestDrive 'destination') -Force
        $external = $env:ProgramFiles
        $alias = Get-FixtureShortPath $external
        if (-not $alias) { return }
        $toolPath = $installedTool
        if (-not $toolPath -or -not $toolPath.StartsWith($external + '\', [StringComparison]::OrdinalIgnoreCase)) {
            Set-ItResult -Skipped -Because 'No installed executable under the short-path fixture'
            return
        }
        $script:fixtureToolPath = $alias + $toolPath.Substring($external.Length)
        $PSScriptRoot = Join-Path $root 'scripts'
        . $preflight -RepoPath $repo.FullName
        Mock Get-Command { [pscustomobject]@{ Source = $script:fixtureToolPath } }
        Resolve-SetupTool 'lefthook' | Should -Be $toolPath
    }
}
