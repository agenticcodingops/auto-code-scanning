# Use the shared validator so every entry point enforces the same contract.
[CmdletBinding()]
param([string]$SuppressionFile = '.scan-suppressions.yaml', [int]$WarningDays = 30,
      [switch]$Strict, [switch]$AllowLegacyExceptions)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/../hooks/lib/common.ps1"
$python = Find-WorkingPython
if (-not $python) { throw 'Suppression validation requires Python and PyYAML' }
$arguments = @("$PSScriptRoot/validate-suppressions.py", '--ci', '--warning-days', [string]$WarningDays)
if ($Strict) { $arguments += '--strict' }
if ($AllowLegacyExceptions) { $arguments += '--allow-legacy-exceptions' }
$arguments += @('--', $SuppressionFile)
& $python @arguments
exit $LASTEXITCODE
