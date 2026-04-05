# Generic Multi-Language Scanning Framework
## Architecture Design & Implementation Guide

**Version**: 1.0  
**Date**: February 2026  
**Purpose**: Extensible local scanning solution supporting multiple languages and technologies

---

# Executive Summary

This document presents an extensible, configuration-driven scanning framework designed to support shift-left testing across multiple languages and technologies. The framework is based on research findings that emphasize:

- **Hook speed under 5 seconds** (10-15 seconds maximum)
- **Defense in depth** (pre-commit + CI validation)
- **Gradual adoption** (90-day phased rollout)
- **Developer experience first** (bypass capabilities, clear error messages)

## Design Principles

1. **Plugin Architecture**: Easy to add new language scanners without core changes
2. **Configuration-Driven**: Enable/disable tools via YAML without code changes
3. **Speed-Optimized**: Parallel execution, caching, staged-files-only scanning
4. **Unified Output**: Consistent result format across all tools
5. **Suppression Management**: Centralized handling of false positives

---

# Section A: Architecture Design Document

## A.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SCANNING FRAMEWORK                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────────┐  │
│  │   Config     │    │   Scanner    │    │     Results              │  │
│  │   Loader     │───▶│   Engine     │───▶│     Aggregator           │  │
│  └──────────────┘    └──────────────┘    └──────────────────────────┘  │
│         │                   │                        │                  │
│         ▼                   ▼                        ▼                  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    LANGUAGE PLUGINS                               │  │
│  ├──────────┬──────────┬──────────┬──────────┬──────────┬──────────┤  │
│  │Terraform │ Python   │ C#/.NET  │PowerShell│ Docker   │  YAML    │  │
│  │  Plugin  │  Plugin  │  Plugin  │  Plugin  │  Plugin  │  Plugin  │  │
│  └──────────┴──────────┴──────────┴──────────┴──────────┴──────────┘  │
│         │         │         │         │         │         │            │
│         ▼         ▼         ▼         ▼         ▼         ▼            │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                       TOOL ADAPTERS                               │  │
│  ├──────────┬──────────┬──────────┬──────────┬──────────┬──────────┤  │
│  │ Trivy    │ pylint   │ dotnet   │PSScript  │ hadolint │ yamllint │  │
│  │ Checkov  │ black    │ format   │Analyzer  │ trivy    │ jsonlint │  │
│  │ tflint   │ bandit   │ Roslyn   │          │ dockle   │          │  │
│  └──────────┴──────────┴──────────┴──────────┴──────────┴──────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         INTEGRATION LAYER                                │
├──────────────────┬──────────────────┬───────────────────────────────────┤
│   Pre-commit     │   Pre-push       │   CI/CD Pipeline                  │
│   Hooks          │   Hooks          │   Integration                     │
└──────────────────┴──────────────────┴───────────────────────────────────┘
```

## A.2 Component Specifications

### A.2.1 Config Loader

**Purpose**: Parse and validate configuration files

**Responsibilities**:
- Load global configuration (`scan-config.yaml`)
- Merge with project-specific overrides (`.scan-config.local.yaml`)
- Validate configuration schema
- Resolve tool paths and versions

**Interface**:
```python
class ConfigLoader:
    def load_config(self, config_path: str) -> ScanConfig
    def validate_config(self, config: ScanConfig) -> ValidationResult
    def merge_overrides(self, base: ScanConfig, override: ScanConfig) -> ScanConfig
```

### A.2.2 Scanner Engine

**Purpose**: Orchestrate tool execution with parallelization and caching

**Responsibilities**:
- Determine which languages/tools to run based on changed files
- Execute tools in parallel (respecting dependencies)
- Manage tool caching for performance
- Handle timeouts and failures gracefully

**Key Features**:
- **File-type detection**: Automatic language identification
- **Parallel execution**: Run independent tools simultaneously
- **Caching**: Skip unchanged files, cache tool databases
- **Timeout handling**: Kill slow tools, report partial results

**Interface**:
```python
class ScannerEngine:
    def scan(self, files: List[str], config: ScanConfig) -> ScanResult
    def scan_staged_files(self, config: ScanConfig) -> ScanResult
    def scan_all_files(self, config: ScanConfig) -> ScanResult
```

### A.2.3 Results Aggregator

**Purpose**: Normalize and combine results from all tools

**Responsibilities**:
- Convert tool-specific output to unified format
- Apply suppression rules
- Calculate severity scores
- Generate reports in multiple formats

**Unified Result Schema**:
```json
{
  "scan_id": "uuid",
  "timestamp": "ISO-8601",
  "duration_ms": 1234,
  "summary": {
    "total_findings": 10,
    "by_severity": {"CRITICAL": 1, "HIGH": 3, "MEDIUM": 4, "LOW": 2},
    "by_tool": {"trivy": 5, "checkov": 3, "tflint": 2},
    "suppressed": 2
  },
  "findings": [
    {
      "id": "finding-uuid",
      "tool": "trivy",
      "rule_id": "AVD-AWS-0057",
      "severity": "HIGH",
      "file": "main.tf",
      "line": 42,
      "message": "S3 bucket has public access enabled",
      "remediation": "Set block_public_acls = true",
      "suppressed": false,
      "suppression_reason": null
    }
  ]
}
```

### A.2.4 Language Plugin Interface

**Purpose**: Define contract for language-specific scanning

**Interface**:
```python
class LanguagePlugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin identifier (e.g., 'terraform', 'python')"""
        pass
    
    @property
    @abstractmethod
    def file_patterns(self) -> List[str]:
        """Glob patterns for files this plugin handles"""
        pass
    
    @property
    @abstractmethod
    def tools(self) -> List[ToolAdapter]:
        """List of tool adapters for this language"""
        pass
    
    @abstractmethod
    def detect_files(self, root_path: str) -> List[str]:
        """Find all relevant files in directory"""
        pass
    
    @abstractmethod
    def validate_environment(self) -> EnvironmentCheck:
        """Check if required tools are installed"""
        pass
```

### A.2.5 Tool Adapter Interface

**Purpose**: Wrap individual scanning tools with consistent interface

**Interface**:
```python
class ToolAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Tool identifier (e.g., 'trivy', 'checkov')"""
        pass
    
    @property
    @abstractmethod
    def tool_type(self) -> ToolType:
        """FORMATTER, LINTER, SECURITY, VALIDATOR"""
        pass
    
    @abstractmethod
    def execute(self, files: List[str], config: ToolConfig) -> RawToolResult:
        """Run the tool and return raw output"""
        pass
    
    @abstractmethod
    def parse_output(self, raw_output: str) -> List[Finding]:
        """Convert tool output to unified findings"""
        pass
    
    @abstractmethod
    def get_version(self) -> str:
        """Return installed tool version"""
        pass
```

## A.3 Plugin Implementation Examples

### A.3.1 Terraform Plugin

```python
class TerraformPlugin(LanguagePlugin):
    name = "terraform"
    file_patterns = ["*.tf", "*.tfvars"]
    
    tools = [
        TerraformFmtAdapter(),      # Formatter
        TerraformValidateAdapter(), # Validator
        TflintAdapter(),            # Linter
        TrivyIaCAdapter(),          # Security
        CheckovAdapter(),           # Security/Policy
    ]
    
    def detect_files(self, root_path: str) -> List[str]:
        return glob.glob(f"{root_path}/**/*.tf", recursive=True)
    
    def validate_environment(self) -> EnvironmentCheck:
        checks = []
        for tool in self.tools:
            try:
                version = tool.get_version()
                checks.append(ToolCheck(tool.name, True, version))
            except Exception as e:
                checks.append(ToolCheck(tool.name, False, str(e)))
        return EnvironmentCheck(self.name, checks)
```

### A.3.2 Python Plugin

```python
class PythonPlugin(LanguagePlugin):
    name = "python"
    file_patterns = ["*.py"]
    
    tools = [
        BlackAdapter(),         # Formatter
        IsortAdapter(),         # Import sorting
        PylintAdapter(),        # Linter
        MypyAdapter(),          # Type checker
        BanditAdapter(),        # Security
        PipAuditAdapter(),      # Dependency security
    ]
```

### A.3.3 C#/.NET Plugin

```python
class DotNetPlugin(LanguagePlugin):
    name = "dotnet"
    file_patterns = ["*.cs", "*.csproj", "*.sln"]
    
    tools = [
        DotnetFormatAdapter(),    # Formatter
        RoslynAnalyzerAdapter(),  # Linter/Analyzer
        SecurityCodeScanAdapter(), # Security
        DotnetOutdatedAdapter(),  # Dependency updates
    ]
```

## A.4 Execution Model

### A.4.1 Pre-commit Integration

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: unified-scan
        name: "Local Security Scan"
        entry: scan-framework scan --staged --fail-on=HIGH
        language: system
        pass_filenames: false
        always_run: true
```

### A.4.2 Manual/On-Demand Scanning

```bash
# Scan specific files
scan-framework scan file1.tf file2.py

# Scan entire directory
scan-framework scan --all

# Scan with specific severity threshold
scan-framework scan --all --fail-on=CRITICAL

# Generate report
scan-framework scan --all --output=json --output-file=scan-results.json
```

### A.4.3 CI/CD Pipeline Integration

**GitHub Actions**:
```yaml
- name: Run Security Scan
  uses: your-org/scan-framework-action@v1
  with:
    fail-on: HIGH
    output-format: sarif
    upload-results: true
```

**Azure DevOps**:
```yaml
- task: ScanFramework@1
  inputs:
    failOn: 'HIGH'
    outputFormat: 'junit'
    publishResults: true
```

### A.4.4 Parallel Execution Strategy

```python
class ParallelExecutor:
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
    
    def execute_tools(self, tools: List[ToolAdapter], files: List[str]) -> List[ToolResult]:
        # Group tools by type for dependency ordering
        formatters = [t for t in tools if t.tool_type == ToolType.FORMATTER]
        others = [t for t in tools if t.tool_type != ToolType.FORMATTER]
        
        # Run formatters first (sequential - they modify files)
        formatter_results = []
        for tool in formatters:
            formatter_results.append(tool.execute(files))
        
        # Run others in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(tool.execute, files): tool for tool in others}
            other_results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        return formatter_results + other_results
```

## A.5 Results Management

### A.5.1 Severity Normalization

Different tools use different severity levels. The framework normalizes to:

| Framework Level | Description | Action |
|-----------------|-------------|--------|
| **CRITICAL** | Immediate security risk | Block commit |
| **HIGH** | Significant issue | Block commit (configurable) |
| **MEDIUM** | Should be addressed | Warning only |
| **LOW** | Minor improvement | Info only |
| **INFO** | Informational | Info only |

**Mapping Examples**:

| Tool | Tool Severity | Framework Level |
|------|---------------|-----------------|
| Trivy | CRITICAL | CRITICAL |
| Trivy | HIGH | HIGH |
| Checkov | FAILED (CIS Critical) | CRITICAL |
| Checkov | FAILED | HIGH |
| pylint | error | HIGH |
| pylint | warning | MEDIUM |
| ESLint | error | HIGH |
| ESLint | warn | MEDIUM |

### A.5.2 Suppression Management

**Centralized Suppression File** (`.scan-suppressions.yaml`):

```yaml
suppressions:
  # Global suppressions (apply to all tools)
  global:
    - rule_id: "AVD-AWS-0057"
      reason: "S3 lifecycle managed at composition layer"
      owner: "jane.smith@example.com"
      expires: "2026-08-01"
    
  # Tool-specific suppressions
  trivy:
    - rule_id: "AVD-AWS-0089"
      files: ["modules/legacy/**/*.tf"]
      reason: "Legacy module - scheduled for refactoring Q3"
      owner: "platform-team"
      expires: "2026-09-30"
  
  checkov:
    - rule_id: "CKV_AWS_20"
      files: ["modules/public-website/*.tf"]
      reason: "Intentionally public S3 bucket for static assets"
      owner: "security-team"
      approved: "2026-01-15"

  # File-level suppressions
  files:
    "tests/**/*":
      - all: true
        reason: "Test files excluded from security scanning"
```

### A.5.3 Baseline Management

**Purpose**: Track known issues to focus on new findings

```bash
# Create baseline from current state
scan-framework baseline create --output=.scan-baseline.json

# Scan comparing against baseline (only show new issues)
scan-framework scan --all --baseline=.scan-baseline.json

# Update baseline after addressing issues
scan-framework baseline update --input=scan-results.json --output=.scan-baseline.json
```

---

# Section B: Configuration Schema

## B.1 Complete Configuration Example

```yaml
# scan-config.yaml
# Global configuration for the multi-language scanning framework

version: "1.0"

# Global settings
global:
  # Output configuration
  output:
    format: "text"  # text, json, sarif, junit
    colors: true
    verbose: false
  
  # Severity thresholds
  severity:
    fail_on: ["CRITICAL", "HIGH"]  # Block commit on these
    warn_on: ["MEDIUM"]            # Show warning only
    ignore: ["LOW", "INFO"]        # Don't display
  
  # Performance settings
  performance:
    parallel_tools: 4              # Max parallel tool executions
    timeout_seconds: 60            # Per-tool timeout
    cache_enabled: true            # Cache tool databases
    cache_ttl_hours: 24            # Cache expiration
  
  # Bypass configuration
  bypass:
    allow_no_verify: true          # Allow --no-verify flag
    require_justification: false   # Require reason in commit message
    audit_bypasses: true           # Log all bypasses

# Language-specific configurations
languages:
  # ============================================
  # TERRAFORM / IaC
  # ============================================
  terraform:
    enabled: true
    file_patterns:
      - "**/*.tf"
      - "**/*.tfvars"
    exclude_patterns:
      - ".terraform/**"
      - "**/.terraform/**"
    
    tools:
      terraform_fmt:
        enabled: true
        auto_fix: true
        stage: "pre-commit"
      
      terraform_validate:
        enabled: true
        stage: "pre-commit"
      
      tflint:
        enabled: true
        stage: "pre-commit"
        config_file: ".tflint.hcl"
        init_plugins: true
        severity_map:
          error: "HIGH"
          warning: "MEDIUM"
          notice: "LOW"
      
      trivy:
        enabled: true
        stage: "pre-commit"
        scanners: ["config", "secret"]
        severity: ["CRITICAL", "HIGH", "MEDIUM"]
        ignore_file: ".trivyignore"
        skip_dirs: [".terraform"]
        severity_map:
          CRITICAL: "CRITICAL"
          HIGH: "HIGH"
          MEDIUM: "MEDIUM"
          LOW: "LOW"
      
      checkov:
        enabled: true
        stage: "pre-push"  # Slower, run on push
        config_file: ".checkov.yaml"
        frameworks: ["terraform"]
        compact: true
        skip_checks: []
        severity_map:
          CRITICAL: "CRITICAL"
          HIGH: "HIGH"
          MEDIUM: "MEDIUM"
          LOW: "LOW"

  # ============================================
  # PYTHON
  # ============================================
  python:
    enabled: true
    file_patterns:
      - "**/*.py"
    exclude_patterns:
      - "venv/**"
      - ".venv/**"
      - "__pycache__/**"
      - "*.pyc"
    
    tools:
      black:
        enabled: true
        auto_fix: true
        stage: "pre-commit"
        line_length: 100
        target_version: ["py310", "py311"]
      
      isort:
        enabled: true
        auto_fix: true
        stage: "pre-commit"
        profile: "black"
      
      pylint:
        enabled: true
        stage: "pre-commit"
        config_file: ".pylintrc"
        disable: ["C0114", "C0115", "C0116"]  # Missing docstrings
        severity_map:
          fatal: "CRITICAL"
          error: "HIGH"
          warning: "MEDIUM"
          convention: "LOW"
          refactor: "INFO"
      
      mypy:
        enabled: false  # Type checking can be slow
        stage: "pre-push"
        strict: false
        config_file: "mypy.ini"
      
      bandit:
        enabled: true
        stage: "pre-commit"
        severity: ["HIGH", "MEDIUM"]
        confidence: ["HIGH", "MEDIUM"]
        skip: ["B101"]  # assert_used
        severity_map:
          HIGH: "HIGH"
          MEDIUM: "MEDIUM"
          LOW: "LOW"
      
      pip_audit:
        enabled: true
        stage: "pre-push"
        requirements_file: "requirements.txt"

  # ============================================
  # C# / .NET
  # ============================================
  dotnet:
    enabled: true
    file_patterns:
      - "**/*.cs"
      - "**/*.csproj"
      - "**/*.sln"
    exclude_patterns:
      - "**/bin/**"
      - "**/obj/**"
    
    tools:
      dotnet_format:
        enabled: true
        auto_fix: true
        stage: "pre-commit"
        severity: "warn"
      
      roslyn_analyzers:
        enabled: true
        stage: "pre-commit"
        analyzers:
          - "Microsoft.CodeAnalysis.NetAnalyzers"
          - "StyleCop.Analyzers"
        severity_map:
          Error: "HIGH"
          Warning: "MEDIUM"
          Info: "LOW"
      
      security_code_scan:
        enabled: true
        stage: "pre-push"
        config_file: ".security-code-scan.config"

  # ============================================
  # POWERSHELL
  # ============================================
  powershell:
    enabled: true
    file_patterns:
      - "**/*.ps1"
      - "**/*.psm1"
      - "**/*.psd1"
    
    tools:
      psscriptanalyzer:
        enabled: true
        stage: "pre-commit"
        settings_file: "PSScriptAnalyzerSettings.psd1"
        include_rules:
          - "PSAvoidUsingPlainTextForPassword"
          - "PSAvoidUsingConvertToSecureStringWithPlainText"
        severity_map:
          Error: "HIGH"
          Warning: "MEDIUM"
          Information: "LOW"

  # ============================================
  # SHELL / BASH
  # ============================================
  shell:
    enabled: true
    file_patterns:
      - "**/*.sh"
      - "**/*.bash"
    
    tools:
      shellcheck:
        enabled: true
        stage: "pre-commit"
        shell: "bash"
        severity: "warning"
        exclude: ["SC1090", "SC1091"]  # Can't follow sourced files
        severity_map:
          error: "HIGH"
          warning: "MEDIUM"
          info: "LOW"
          style: "INFO"
      
      shfmt:
        enabled: true
        auto_fix: true
        stage: "pre-commit"
        indent: 2
        binary_next_line: true

  # ============================================
  # DOCKER
  # ============================================
  docker:
    enabled: true
    file_patterns:
      - "**/Dockerfile"
      - "**/Dockerfile.*"
      - "**/*.dockerfile"
    
    tools:
      hadolint:
        enabled: true
        stage: "pre-commit"
        config_file: ".hadolint.yaml"
        ignore: ["DL3008", "DL3009"]  # apt-get version pinning
        severity_map:
          error: "HIGH"
          warning: "MEDIUM"
          info: "LOW"
          style: "INFO"
      
      trivy_image:
        enabled: true
        stage: "pre-push"  # Slower
        severity: ["CRITICAL", "HIGH"]
        ignore_unfixed: true

  # ============================================
  # KUBERNETES
  # ============================================
  kubernetes:
    enabled: true
    file_patterns:
      - "**/k8s/**/*.yaml"
      - "**/k8s/**/*.yml"
      - "**/kubernetes/**/*.yaml"
      - "**/manifests/**/*.yaml"
    
    tools:
      kubelinter:
        enabled: true
        stage: "pre-commit"
        config_file: ".kube-linter.yaml"
      
      kube_score:
        enabled: true
        stage: "pre-push"
      
      pluto:
        enabled: true
        stage: "pre-push"
        target_versions:
          k8s: "v1.28.0"

  # ============================================
  # YAML / JSON
  # ============================================
  yaml:
    enabled: true
    file_patterns:
      - "**/*.yaml"
      - "**/*.yml"
    exclude_patterns:
      - "**/k8s/**"  # Handled by kubernetes plugin
      - "**/kubernetes/**"
    
    tools:
      yamllint:
        enabled: true
        stage: "pre-commit"
        config_file: ".yamllint.yaml"
        strict: false
  
  json:
    enabled: true
    file_patterns:
      - "**/*.json"
    exclude_patterns:
      - "**/node_modules/**"
      - "**/package-lock.json"
    
    tools:
      jsonlint:
        enabled: true
        stage: "pre-commit"

# Custom rules (extend built-in tools)
custom_rules:
  # Example: Require specific tags on all AWS resources
  terraform_custom:
    - id: "CUSTOM_TF_001"
      name: "Required tags missing"
      description: "All AWS resources must have Environment and Owner tags"
      pattern: |
        resource "aws_.*" {
          (?!.*tags\s*=)
        }
      severity: "MEDIUM"
      files: ["**/*.tf"]
      message: "AWS resource missing required tags (Environment, Owner)"

# Team overrides (applied after global config)
team_overrides:
  # Allow specific teams to disable certain checks
  platform_team:
    languages:
      terraform:
        tools:
          checkov:
            skip_checks: ["CKV_AWS_144"]  # S3 cross-region replication
  
  data_science_team:
    languages:
      python:
        tools:
          pylint:
            disable: ["C0114", "C0115", "C0116", "R0914"]  # Disable docstrings, too-many-locals
```

## B.2 Per-Tool Configuration Files

### B.2.1 tflint Configuration (`.tflint.hcl`)

```hcl
plugin "aws" {
  enabled = true
  version = "0.31.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}

plugin "azurerm" {
  enabled = true
  version = "0.26.0"
  source  = "github.com/terraform-linters/tflint-ruleset-azurerm"
}

config {
  format = "compact"
  plugin_dir = "~/.tflint.d/plugins"
}

rule "terraform_naming_convention" {
  enabled = true
  format  = "snake_case"
}

rule "terraform_documented_outputs" {
  enabled = true
}

rule "terraform_documented_variables" {
  enabled = true
}
```

### B.2.2 Checkov Configuration (`.checkov.yaml`)

```yaml
soft-fail: false
compact: true
framework:
  - terraform
skip-check:
  # Documented suppressions with justifications
  - CKV_AWS_144  # S3 cross-region replication - using single-region design
  - CKV2_AWS_6   # S3 bucket has no lifecycle - managed at account level
download-external-modules: true
evaluate-variables: true
```

### B.2.3 Trivy Configuration (`.trivy.yaml`)

```yaml
severity:
  - CRITICAL
  - HIGH
  - MEDIUM
ignorefile: .trivyignore
timeout: 5m
cache-dir: ~/.trivy-cache
skip-dirs:
  - .terraform
  - node_modules
  - vendor
scanners:
  - vuln
  - config
  - secret
```

---

# Section C: Implementation Roadmap

Based on research findings about adoption patterns and the 90-day phased rollout:

## Phase 1: Core Framework + Terraform (Months 1-2)

**Focus**: Establish foundation with highest-value, lowest-friction tools

### Month 1: Core Infrastructure

| Week | Deliverable | Success Criteria |
|------|-------------|------------------|
| 1 | Config loader + schema validation | Config files parse correctly |
| 2 | Scanner engine with parallel execution | Tools run in parallel |
| 3 | Results aggregator + unified output | Consistent JSON output |
| 4 | Pre-commit integration | Hooks trigger on commit |

### Month 2: Terraform Plugin Complete

| Week | Tool | Priority | Notes |
|------|------|----------|-------|
| 1 | terraform fmt | P0 | Auto-fix, near-zero friction |
| 2 | terraform validate | P0 | Essential syntax checking |
| 3 | tflint | P0 | AWS/Azure rules |
| 4 | Trivy + Checkov | P0 | Security scanning |

**Pilot Group**: 3-5 advocates, low-risk projects

---

## Phase 2: High-Value Additions (Months 3-4)

**Focus**: Languages with high security value and common usage

### Month 3: Python + PowerShell

| Week | Tool | Priority | Notes |
|------|------|----------|-------|
| 1 | black + isort | P0 | Auto-fix formatting |
| 2 | pylint | P1 | Linting |
| 3 | bandit | P0 | Security scanning |
| 4 | PSScriptAnalyzer | P1 | PowerShell security |

### Month 4: Shell + Docker

| Week | Tool | Priority | Notes |
|------|------|----------|-------|
| 1 | ShellCheck | P0 | Bash/shell linting |
| 2 | shfmt | P1 | Shell formatting |
| 3 | hadolint | P0 | Dockerfile linting |
| 4 | Trivy image | P0 | Container security |

**Expand Pilot**: Additional teams (50%+ adoption target)

---

## Phase 3: Enterprise Languages (Months 5-6)

**Focus**: Full language coverage for enterprise environments

### Month 5: C#/.NET + Java

| Week | Tool | Priority | Notes |
|------|------|----------|-------|
| 1 | dotnet format | P0 | .NET formatting |
| 2 | Roslyn analyzers | P1 | .NET linting |
| 3 | Checkstyle | P1 | Java style |
| 4 | SpotBugs + OWASP | P0 | Java security |

### Month 6: JavaScript/TypeScript + Go

| Week | Tool | Priority | Notes |
|------|------|----------|-------|
| 1 | ESLint + Prettier | P0 | JS/TS formatting/linting |
| 2 | npm audit | P0 | Dependency security |
| 3 | gofmt + golint | P0 | Go formatting/linting |
| 4 | gosec | P0 | Go security |

**Organization-Wide**: 90%+ adoption target

---

## Phase 4: Kubernetes + Advanced Features (Months 7-8)

**Focus**: Cloud-native tooling and advanced features

### Month 7: Kubernetes Tools

| Week | Tool | Priority | Notes |
|------|------|----------|-------|
| 1 | kubelinter | P0 | K8s manifest linting |
| 2 | kube-score | P1 | K8s best practices |
| 3 | pluto | P1 | API deprecation checking |
| 4 | Trivy K8s | P0 | K8s security |

### Month 8: Advanced Features

| Week | Feature | Priority | Notes |
|------|---------|----------|-------|
| 1 | Baseline management | P1 | Track known issues |
| 2 | Custom rule engine | P2 | Organization-specific rules |
| 3 | Metrics dashboard | P1 | Track adoption/effectiveness |
| 4 | IDE integrations | P2 | VS Code, JetBrains |

---

## Priority Legend

| Priority | Meaning | Timeline |
|----------|---------|----------|
| **P0** | Must have for phase completion | Block phase if not done |
| **P1** | Should have for full value | Complete within phase |
| **P2** | Nice to have | Can defer to next phase |

---

# Section D: Tool Comparison Matrix

## D.1 Terraform/IaC Tools

| Tool | Purpose | False Positive Rate | Speed | Customization | Maintenance | Status |
|------|---------|---------------------|-------|---------------|-------------|--------|
| **terraform fmt** | Formatting | ~0% | <1 sec | Low | Built-in | ✅ Active |
| **terraform validate** | Syntax | ~0% | 1-2 sec | None | Built-in | ✅ Active |
| **tflint** | Linting | Low (5-10%) | 2-5 sec | High (HCL rules) | MPL 2.0, active | ✅ Active |
| **Trivy** | Security | Low-Medium (10-20%) | 5-15 sec | Medium (Rego) | Apache 2.0, very active | ✅ Active |
| **Checkov** | Policy | Medium (15-25%) | 10-30 sec | High (Python/YAML) | Apache 2.0, active | ✅ Active |
| **KICS** | Security | Medium (15-25%) | 5-15 sec | High (Rego) | Apache 2.0, active | ✅ Active |
| ~~Terrascan~~ | ~~Security~~ | - | - | - | - | ❌ **ARCHIVED** |
| ~~tfsec~~ | ~~Security~~ | - | - | - | - | ❌ **Merged into Trivy** |

## D.2 Python Tools

| Tool | Purpose | False Positive Rate | Speed | Customization | Maintenance | Status |
|------|---------|---------------------|-------|---------------|-------------|--------|
| **black** | Formatting | ~0% | <1 sec | Low (opinionated) | Very active | ✅ Active |
| **isort** | Import sorting | ~0% | <1 sec | Medium | Active | ✅ Active |
| **pylint** | Linting | Medium (20-30%) | 5-15 sec | Very high | Very active | ✅ Active |
| **mypy** | Type checking | Low (5-10%) | 10-60 sec | High | Very active | ✅ Active |
| **bandit** | Security | Medium (15-25%) | 2-5 sec | Medium | Active | ✅ Active |
| **pip-audit** | Dependencies | Low (5%) | 5-10 sec | Low | Active | ✅ Active |
| **ruff** | Linting (fast) | Low (10-15%) | <1 sec | High | Very active | ✅ Active |

## D.3 C#/.NET Tools

| Tool | Purpose | False Positive Rate | Speed | Customization | Maintenance | Status |
|------|---------|---------------------|-------|---------------|-------------|--------|
| **dotnet format** | Formatting | ~0% | 2-10 sec | Medium (.editorconfig) | Built-in | ✅ Active |
| **Roslyn analyzers** | Linting | Low (10-15%) | Build-integrated | Very high | Microsoft | ✅ Active |
| **StyleCop.Analyzers** | Style | Low (5-10%) | Build-integrated | High | Active | ✅ Active |
| **Security Code Scan** | Security | Medium (20-30%) | Build-integrated | Medium | Active | ✅ Active |
| **CSharpier** | Formatting | ~0% | <1 sec | Low (opinionated) | Active | ✅ Active |

## D.4 PowerShell Tools

| Tool | Purpose | False Positive Rate | Speed | Customization | Maintenance | Status |
|------|---------|---------------------|-------|---------------|-------------|--------|
| **PSScriptAnalyzer** | Linting + Security | Low (10-15%) | 1-5 sec | High | Microsoft | ✅ Active |

## D.5 Shell/Bash Tools

| Tool | Purpose | False Positive Rate | Speed | Customization | Maintenance | Status |
|------|---------|---------------------|-------|---------------|-------------|--------|
| **ShellCheck** | Linting | Low (5-10%) | <1 sec | Medium | Very active | ✅ Active |
| **shfmt** | Formatting | ~0% | <1 sec | Low | Active | ✅ Active |

## D.6 Docker Tools

| Tool | Purpose | False Positive Rate | Speed | Customization | Maintenance | Status |
|------|---------|---------------------|-------|---------------|-------------|--------|
| **hadolint** | Dockerfile linting | Low (5-10%) | <1 sec | Medium | Active | ✅ Active |
| **Trivy** | Container security | Medium (15-25%) | 10-60 sec | Medium | Very active | ✅ Active |
| **dockle** | Best practices | Low (10%) | 5-10 sec | Low | Active | ✅ Active |

## D.7 Kubernetes Tools

| Tool | Purpose | False Positive Rate | Speed | Customization | Maintenance | Status |
|------|---------|---------------------|-------|---------------|-------------|--------|
| **kubelinter** | Manifest linting | Low (10-15%) | <1 sec | High | Active | ✅ Active |
| **kube-score** | Best practices | Low (5-10%) | <1 sec | Low | Active | ✅ Active |
| **pluto** | API deprecation | ~0% | <1 sec | Low | Active | ✅ Active |

## D.8 Secrets Detection Tools

| Tool | Purpose | False Positive Rate | Speed | Customization | Maintenance | Status |
|------|---------|---------------------|-------|---------------|-------------|--------|
| **Gitleaks** | Secrets | Low (10-15%) | 1-5 sec | High (TOML) | Very active | ✅ Active |
| **detect-secrets** | Secrets | Medium (15-25%) | 2-5 sec | High | Yelp, active | ✅ Active |
| **Trivy secrets** | Secrets | Medium (15-20%) | Part of scan | Medium | Very active | ✅ Active |

---

# Section E: Best Practices Integration

## E.1 Research-Backed Adoption Strategies

### From DORA Research

| Practice | Impact | Implementation |
|----------|--------|----------------|
| Trunk-based development | 50% higher delivery performance | Small PRs, fast feedback |
| Automated testing | Core capability for elite teams | Pre-commit + CI layers |
| High-quality documentation | 12.8x performance impact | README, inline comments |
| Fast code reviews | 50% higher performance | Keep PRs small |

### From Forrester ROI Studies

| Success Factor | Measurement | Target |
|---------------|-------------|--------|
| Scan time reduction | Developer hours saved | 80% faster scans |
| Vulnerability reduction | Critical/High findings | 65% reduction |
| Time to fix | Hours from detection | 75% reduction |

## E.2 Developer Experience Checklist

- [ ] **Hooks complete in <5 seconds** (10 sec max for all hooks)
- [ ] **Clear error messages** with remediation guidance
- [ ] **Bypass available** for emergencies (`--no-verify`)
- [ ] **Auto-fix where possible** (formatters, simple issues)
- [ ] **Documentation accessible** (inline links, README)
- [ ] **Suppression process documented** (how to handle false positives)

## E.3 Metrics for Measuring Success

### Leading Indicators (Track Weekly)

| Metric | Target | Red Flag |
|--------|--------|----------|
| Hook pass rate (first attempt) | >80% | <60% (too many issues) |
| Hook execution time | <5 sec average | >15 sec (too slow) |
| Developer satisfaction | Trending positive | Complaints increasing |

### Lagging Indicators (Track Monthly)

| Metric | Target | Calculation |
|--------|--------|-------------|
| Production incidents | 60% reduction | Compare to baseline period |
| CI build failures | 40% reduction | Failures from code issues |
| Security findings | 50% reduction | Production vulnerabilities |
| Bypass rate | <5% | `--no-verify` commits / total |

## E.4 Common Pitfalls Checklist

| Pitfall | Warning Sign | Prevention |
|---------|--------------|------------|
| Too many hooks at once | High bypass rate | Start minimal, add gradually |
| Slow hooks | Complaints, bypasses | Profile and optimize |
| No CI backup | Issues slip through | Mirror hooks in CI |
| False positive fatigue | Alert dismissals | Tune aggressively, maintain suppressions |
| Inadequate training | Developer confusion | Clear docs, champion network |

---

**Document Version**: 1.0  
**Last Updated**: February 2026  
**Framework Repository**: [To be published on GitHub]
