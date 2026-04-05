# setup-scanning.Tests.ps1
# Pester 5+ unit tests for scripts/setup-scanning.ps1

BeforeAll {
    $ScriptRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $ScriptPath = Join-Path $ScriptRoot "scripts" "setup-scanning.ps1"
}

Describe "setup-scanning.ps1" {

    Describe "Parameter Validation" {

        It "Should accept valid CloudProvider values: <Provider>" -TestCases @(
            @{ Provider = "aws" }
            @{ Provider = "azure" }
            @{ Provider = "gcp" }
        ) {
            param($Provider)
            # Validate the parameter set accepts these values
            $cmd = Get-Command $ScriptPath
            $param = $cmd.Parameters["CloudProvider"]
            $param | Should -Not -BeNullOrEmpty
            $validateSet = $param.Attributes | Where-Object { $_ -is [System.Management.Automation.ValidateSetAttribute] }
            $validateSet.ValidValues | Should -Contain $Provider
        }

        It "Should accept valid Tier values: <Tier>" -TestCases @(
            @{ Tier = "starter" }
            @{ Tier = "standard" }
            @{ Tier = "strict" }
        ) {
            param($Tier)
            $cmd = Get-Command $ScriptPath
            $param = $cmd.Parameters["Tier"]
            $validateSet = $param.Attributes | Where-Object { $_ -is [System.Management.Automation.ValidateSetAttribute] }
            $validateSet.ValidValues | Should -Contain $Tier
        }

        It "Should default Tier to 'starter'" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match '\$Tier\s*=\s*"starter"'
        }

        It "Should have SkipTools as a switch parameter" {
            $cmd = Get-Command $ScriptPath
            $param = $cmd.Parameters["SkipTools"]
            $param | Should -Not -BeNullOrEmpty
            $param.ParameterType.Name | Should -Be "SwitchParameter"
        }

        It "Should require CloudProvider parameter" {
            $cmd = Get-Command $ScriptPath
            $param = $cmd.Parameters["CloudProvider"]
            $mandatory = $param.Attributes | Where-Object { $_ -is [System.Management.Automation.ParameterAttribute] }
            $mandatory.Mandatory | Should -Be $true
        }
    }

    Describe "Script Configuration" {

        It "Should define minimum versions for required tools" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "trivy.*0\.48\.0"
            $content | Should -Match "checkov.*3\.0\.0"
            $content | Should -Match "tflint.*0\.50\.0"
            $content | Should -Match "pre-commit.*3\.0\.0"
        }

        It "Should track 5 total tools" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'TotalTools\s*=\s*5'
        }
    }

    Describe "Helper Functions" {

        It "Should define Write-Step function" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "function Write-Step"
        }

        It "Should define Write-Success function" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "function Write-Success"
        }

        It "Should define Test-CommandExists function" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "function Test-CommandExists"
        }

        It "Should define Get-ToolVersion function" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "function Get-ToolVersion"
        }

        It "Should define Test-ToolMeetsMinimum function" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "function Test-ToolMeetsMinimum"
        }

        It "Should define Install-ChocolateyPackage function" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "function Install-ChocolateyPackage"
        }
    }

    Describe "Exit Codes" {

        It "Should use exit 0 for full success" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "exit 0"
        }

        It "Should use exit 1 for complete failure" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "exit 1"
        }

        It "Should use exit 2 for partial success" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "exit 2"
        }
    }

    Describe "Config Copying" {

        It "Should create .scanning/configs/ directory structure" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match '\.scanning.*configs'
        }

        It "Should look for configs in pre-commit cache" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'pre-commit'
            $content | Should -Match '\.cache'
        }

        It "Should copy suppression template to repo root" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match '\.scan-suppressions\.yaml'
        }
    }

    Describe "Hook Installation" {

        It "Should install pre-commit hooks" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "pre-commit install"
        }

        It "Should install pre-push hooks" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "pre-commit install --hook-type pre-push"
        }
    }

    Describe "Tier Template" {

        It "Should copy tier template for the selected tier" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "templates.*Tier"
        }

        It "Should not overwrite existing .pre-commit-config.yaml" {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "\.pre-commit-config\.yaml.*already exists"
        }
    }
}
