# Captured Terraform module records

These JSON files contain trimmed **real Checkov 3.3.19 output**, generated on
Windows with the sibling HCL fixtures. `capture.py` asserts the installed version
and executes the scanner with `--framework terraform --download-external-modules
false --skip-download --check <rule> -o json`. All three scans exited 0.

Run `python tests/fixtures/checkov-module-records/capture.py` from an isolated
environment with `checkov==3.3.19`. JSON ordering can vary between runs. The capture
retains skipped/failed record identity and location fields plus the scanner
summary; absolute machine paths, source excerpts and descriptive metadata are
discarded. Tests translate Windows path separators for Linux without changing
the captured addresses.

| Field | Module call | Two-level resource |
| --- | --- | --- |
| `resource` | `plain`, `each["blue"]`, `counted[0]` (no `module.` prefix) | `module.outer["blue"].module.inner.azurerm_key_vault.example` (full module path) |
| `file_path` | `\main.tf` | `\modules\b\main.tf` (declaration file) |
| `caller_file_path` | `null` | `\modules\a\main.tf` (immediate caller, not root caller) |
| `caller_file_line_range` | `null` | `[1, 4]` (inner call) |
| `definition_context_file_path` (discarded) | Absolute declaration path | Absolute declaration path, without caller ancestry |

The nested root module is in `entry/main.tf`, and both `blue` and `green` instances
load the same `modules/a` -> `modules/b` chain. Scanning the parent directory is
essential: a chain starting exactly at the scan directory already worked before
this regression fix. Matching must locate the root while anchoring the final hop
to the reported caller and checking the entire trusted source chain.

`nested-module-calls.json` captures module checks on that same nested fixture.
The root calls have bare `outer["blue"]`/`outer["green"]` addresses; the inner calls
use `module.outer["blue"].inner`/`module.outer["green"].inner`. Each inner call's
`caller_file_path` is `\entry\main.tf`, while its `file_path` is
`\modules\a\main.tf`. This verifies that module policies keep the bare final
call label even when the address includes a parent module path.
