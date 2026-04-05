# Contributing

## How to Contribute

1. Fork this repository
2. Create a feature branch
3. Make your changes
4. Ensure all tests pass
5. Submit a pull request

## Adding a New Hook

1. Add the hook definition to `.pre-commit-hooks.yaml`
2. Add test fixtures in `tests/fixtures/`
3. Update `tests/` with integration tests
4. Update `docs/HOOK-REFERENCE.md`
5. Update relevant templates

## Adding a New Cloud Provider

1. Create `configs/{provider}/.checkov.yaml` with CIS Benchmark checks
2. Create `configs/{provider}/.tflint.hcl` with provider plugin
3. Create `templates/{provider}/pre-commit-config.yaml`
4. Add test fixture `tests/fixtures/terraform-{provider}-fail/`
5. Update `docs/MULTI-CLOUD.md`

## Release Process

1. Ensure all tests pass
2. Update `CHANGELOG.md`
3. Create a semver tag: `git tag -a v1.x.0 -m "description"`
4. Push tag: `git push origin v1.x.0`
5. Consuming repos update via `pre-commit autoupdate`

## Code Standards

- PowerShell scripts follow PSScriptAnalyzer rules
- YAML files must be valid
- All hooks must complete in <5 seconds
- Documentation required for all features
