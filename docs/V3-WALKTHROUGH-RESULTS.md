# Local walkthrough evidence — 7 November 2026

Historical test evidence for [Getting started](SETUP-GUIDE.md), not a second installation guide.
The fresh Windows Terraform consumer had no remote and was never pushed. Its final working tree was clean.
The platform checkout was `8321adf7020025a5a7a6c7cd8d1780015b18a07a`, the post-release setup-output fix.
The test used standard tier, Lefthook and the three-file Terraform example now in the guide.

All 30 walkthrough command steps exited 0. Setup and separate verification each had zero failed checks.
The optional missing `.trivyignore` was the only verifier warning. The scanned commit ran both secret hooks,
the Terraform security hook, config validation and formatting. The on-demand report had zero findings and
`scan_complete: true`. The installed push hook then passed Checkov and TFLint with a real local transaction,
without making a network push. This does not prove hosted uploads or application-language scanners.

An earlier single-file example correctly failed push lint with an unused variable and a module-layout warning
(exit 1). Splitting the declaration into `variables.tf` and using it from `outputs.tf` removed both findings;
the corrected example passed the installed push hook (exit 0). No platform code changed.

## Command ledger

Paths use the guide variables; Git identity values are represented as `<clone identity>`.
Exact file writes and SHA substitutions followed the guide; no hook bypass was used.

| UTC completion | Command | Exit |
|---|---|---|
| 2026-11-07T01:56:18.0577708Z | `python -m venv "$HOME/.venvs/auto-code-scanning"` | 0 |
| 2026-11-07T01:56:18.2768487Z | `& "$HOME/.venvs/auto-code-scanning/Scripts/Activate.ps1"` | 0 |
| 2026-11-07T01:56:23.0780415Z | `python -m pip install PyYAML==6.0.3 jsonschema==4.25.1 checkov==3.3.19` | 0 |
| 2026-11-07T01:56:25.3062979Z | `git -c core.autocrlf=false clone https://github.com/agenticcodingops/auto-code-scanning.git $Platform` | 0 |
| 2026-11-07T01:56:26.0295493Z | `git -C $Platform fetch origin --tags` | 0 |
| 2026-11-07T01:56:26.2292227Z | `git -C $Platform checkout --detach $ScanSha` | 0 |
| 2026-11-07T01:56:30.4522776Z | `python "$Platform/scripts/install-scanner.py" trivy` | 0 |
| 2026-11-07T01:56:32.2878585Z | `python "$Platform/scripts/install-scanner.py" tflint` | 0 |
| 2026-11-07T01:56:33.4735033Z | `python "$Platform/scripts/install-scanner.py" gitleaks` | 0 |
| 2026-11-07T01:56:33.5674824Z | `git -C $Platform checkout --detach $ScanSha (documented Windows fix pin)` | 0 |
| 2026-11-07T01:56:33.5822668Z | `New-Item -ItemType Directory -Force $Trusted` | 0 |
| 2026-11-07T01:56:33.5926361Z | `Copy-Item "$Platform/configs/aws/.tflint.hcl" "$Trusted/tflint.hcl"` | 0 |
| 2026-11-07T01:56:33.6008284Z | `New-Item -ItemType Directory -Force $FormatTools` | 0 |
| 2026-11-07T01:56:38.1439045Z | `npm install --prefix $FormatTools prettier@3.6.2` | 0 |
| 2026-11-07T01:56:38.1517502Z | `'{}' \| Set-Content -Encoding utf8 "$FormatTools/prettier.json"` | 0 |
| 2026-11-07T01:56:38.1597366Z | `'**/schemas/**' \| Set-Content -Encoding utf8 "$FormatTools/.prettierignore"` | 0 |
| 2026-11-07T01:56:38.2855942Z | `git init -b main` | 0 |
| 2026-11-07T01:56:38.4490523Z | `git config user.name <clone identity>` | 0 |
| 2026-11-07T01:56:38.5093635Z | `git config user.email <clone identity>` | 0 |
| 2026-11-07T01:57:15.2715640Z | `python "$Platform/scripts/setup-scan-fix.py" --languages terraform --cloud-provider aws --tier standard --hooks-runner lefthook` | 0 |
| 2026-11-07T01:57:15.2836955Z | `Write consumer .gitattributes with documented LF rules` | 0 |
| 2026-11-07T01:57:30.2462831Z | `pwsh -NoProfile -File "$Platform/scripts/verify-scanning.ps1" -HooksRunner lefthook -Tier standard` | 0 |
| 2026-11-07T01:57:30.9168851Z | `python scripts/validate-scan-config.py` | 0 |
| 2026-11-07T01:57:31.4639382Z | `git add .` | 0 |
| 2026-11-07T01:57:31.5371600Z | `git diff --cached --name-only` | 0 |
| 2026-11-07T01:57:46.4694932Z | `git commit -m "chore: adopt security scanning"` | 0 |
| 2026-11-07T01:57:50.2757421Z | `python scripts/scan.py . --tools trivy --format json` | 0 |
| 2026-11-07T01:57:50.3314754Z | `git remote -v` | 0 |
| 2026-11-07T01:57:50.3991404Z | `git log -1 --format="%H %s"` | 0 |
| 2026-11-07T01:58:55.7338318Z | `$Transaction \| bash $PushHook origin local-test` | 0 |

## Selected captured output

Temporary consumer paths and its local-only commit identifier are replaced with placeholders.

```text
Total checks:  17
Passed:        16
Failed:        0
Warnings:      1
Overall Status: PASSED
Total checks:  17
Passed:        16
Failed:        0
Warnings:      1
Overall Status: PASSED
[validate-scan-config] VALID: <temporary-consumer>\scan-config.yaml conforms to scan-config.schema.json
[validate-scan-config] VALID: C:\Users\hasan\AppData\Local\Temp\scan-config-yjp5928b\scan-config.yaml conforms to scan-config.schema.json
[prettier] PASS: Prettier formatted (1672ms)
[gitleaks] PASS: No findings above threshold
[trivy-iac-critical] PASS: No findings above threshold
[trivy-secrets] PASS: No findings above threshold
[pre-push] checkov: scanning object <local-commit>
[pre-push] PASS: No findings above threshold
[pre-push] tflint: scanning object <local-commit>
[pre-push] PASS: No findings above threshold
```

## Vendored-file comparison

All 61 files below matched the external platform checkout after the scanned commit and local push-hook test.
These SHA-256 values describe working-tree bytes, including Windows PowerShell line endings selected by
the platform `.gitattributes`; Git blob bytes can use different line endings. Python caches are excluded.

| File | SHA-256 (consumer and external checkout) |
|---|---|
| `hooks/checkov-strict.ps1` | `3974b738454fa01dce0b3fb0117e0ffcdeafa8d2fee605cdf53d158ae304e496` |
| `hooks/checkov-strict.sh` | `342a8f2864e4ab7dac63a19d6d6497bca05a5581c06cd63f42113a4089744d62` |
| `hooks/checkov.ps1` | `f2d2124152eceb4b263a7981bcfacdef8de677e5ecd648f6b7288c771abdc6d8` |
| `hooks/checkov.sh` | `833952a12e30aa938438c97734cef809035fb60191d000b622faf4f8d6187205` |
| `hooks/dispatcher.sh` | `9fb04ebb46d99aef8ae2bb18cfe35827a1f11172730c8951c16678a3f76a5502` |
| `hooks/dotnet-build.ps1` | `61e85ed9778a0cd5a4b8b60e8de631a78a0063fc6f4c0dab58fafd7bfff4cd9a` |
| `hooks/dotnet-build.sh` | `016a8281d1900533dc07047ddb19f0d5df53a73f1eb3e4c694e70236a4f8dc7c` |
| `hooks/dotnet-format.ps1` | `f5a2edee359b56c8a59ad8995c8be4071e81771200b527d11e465af88751dcf6` |
| `hooks/dotnet-format.sh` | `57ebc57e4cdc48867a1d79d385006f1473ee01778c88995a9f2db1937e06ec26` |
| `hooks/eslint.ps1` | `2f8c24d6ebdfb35f721d0de669575bed1cb18c29f9abf490632f331e831b32d7` |
| `hooks/eslint.sh` | `e03814211f3f53dec368ddfa4fb291010b33fa9c12a583d6bef92bdc80242b91` |
| `hooks/gitleaks.ps1` | `1b92df401105d7d235c2be693db36ab13beab243b3baad0dbb3d986f094d122a` |
| `hooks/gitleaks.sh` | `202e63cf8c37ccb440cf193c25cf4f46f3fd0780ded4521f5c37ac0f8d16b244` |
| `hooks/lib/checkov_policy.py` | `f7e0e96c2ce93fa7e36b1edbbd8d67aa9097dd192da72f5644ced59fffb4421b` |
| `hooks/lib/common.ps1` | `e00de8f505a4c27c6b441ecdd707ce5487e0fc7aba22cff40a3d0b7a824f7093` |
| `hooks/lib/common.sh` | `da253f43b48aa62f23dd2dd8b5208cb0fee41ff782d51df16fa93df02bbe6c69` |
| `hooks/lib/push-hook-ids.txt` | `44ccace688558ef88a7e6f4beb3cd2b7fdef2667141928a82149e79f97ecc321` |
| `hooks/lib/scan_config.py` | `0fc76510cb9eab7e5f3206ca52949e72c45181f5fbf59f21fb4d6c6cc7603a2b` |
| `hooks/lib/tool-paths.ps1` | `2af88b62757b8810e6dfdd28c96b70079e1dbecb92820236f85b861690a6f7a6` |
| `hooks/lib/tool-paths.sh` | `99ef7595b681c295d21cc11e32de59f53437f3f95157453b6643fb620be5e274` |
| `hooks/lib/trivy_selected.py` | `e3ad6308ce46447e50014536dc5f8fcb09285560755643690f55e233fee36f99` |
| `hooks/pre-commit.py` | `eb493fe507a172d6a1f331919253e376210d99082f021a0a821a4097aa15640f` |
| `hooks/pre-push.py` | `7575e254241217dd5e54401711817e7607d75678ef5b1bf4d397872b8f9efb37` |
| `hooks/prettier.ps1` | `8bfea07ee35fae921b0ab2e5fa6efd943cc706be9252f4aed4a818d723f33f6e` |
| `hooks/prettier.sh` | `4fe32a8f9aced16b61f8876cacad8f09567976cb01f2201f24c9651a818609ca` |
| `hooks/semgrep-csharp.ps1` | `f9c051b4813b8df4041788382930d19e903c78f0c98e4dfe062cecade9f7606f` |
| `hooks/semgrep-csharp.sh` | `14cd584e80a0fcf0bb19e26813de25936d36b5d9a18435a347ff0a6faf9b7862` |
| `hooks/semgrep-typescript.ps1` | `71b4aaf7ad0ab02074822a2b9c53bea368ba97b5b2ad440088679573b7006406` |
| `hooks/semgrep-typescript.sh` | `f453a4917ffd68fca8360870d83d894841ad134566fe9660a1e444b7cb73cdd4` |
| `hooks/snyk-iac.ps1` | `1895479403197f7e0efb8ff8e31ee1514a5bd1199525d589c66381b43436df1f` |
| `hooks/snyk-iac.sh` | `01979c865b53316b5eff7b6820564a6fca17be42683527901883f317eb3b3b10` |
| `hooks/sqlfluff.ps1` | `ef772f5f8ef36b61bfb13ac41966077f10ffbd2d883801d237ad08edd7a82dc7` |
| `hooks/sqlfluff.sh` | `e613e359d398e91a863169dac016b1145a99fb0d9ad1dd41b0effe34a45d4ba8` |
| `hooks/tflint.ps1` | `abe7f44f0c70ebf9cdd96338435956b874e4fee1381335f05805ac511cd61102` |
| `hooks/tflint.sh` | `9aea96abc3e1287a393afe4919d758f01523cd8dfe5c80c2da52ab74cc6c38fd` |
| `hooks/trivy-iac-critical.ps1` | `5d673c7fdb12de80f09c3dc74607530c0abb1c20946631c1b0467a2546d4dcbe` |
| `hooks/trivy-iac-critical.sh` | `dcd16a8576d0c49bcd6323adbfa7a37ff7bfdebdb85733fba3edc145bf4141b1` |
| `hooks/trivy-iac-full.ps1` | `b9dfab6e9693052f5747a52a9e39bc435c258cf3b3fed4d770c191fb33e2686f` |
| `hooks/trivy-iac-full.sh` | `bf33c22b6b4c90eb423df671313f5497b40a63efcfea17b5d5d9e95031e3b603` |
| `hooks/trivy-secrets.ps1` | `2a41364c1884685328f27bc9d2b39387494f3578d9cfddc88ea6097429e8a125` |
| `hooks/trivy-secrets.sh` | `d0e08cd3de2fa4acdde6b9e8eed09e6521ddddcdcfb5569794c03b6383c53ecb` |
| `hooks/validate-scan-config.ps1` | `5f4a3b8e2081a713974c569a1ff3868f35d5450187e9dc4e686e9e0b0bd5a410` |
| `hooks/validate-scan-config.sh` | `663497712bbaf8098bc430a59d75a9307774a620d37915572a973873b80f96a6` |
| `hooks/validate-suppressions.ps1` | `48b592daac43679a839489db59aad1aad19a263ae63061f3b7d6bf8796bfdd6b` |
| `hooks/validate-suppressions.py` | `b68801b8099c46f373059bea91aafaa2372702f6a00ba4224025d78bdab45813` |
| `hooks/validate-suppressions.sh` | `aa34c6b348c87aa3aa9504ddb9d7cbf1bfe691dd5633ee617a1d3d0870879a9c` |
| `schemas/last-scan.schema.json` | `c92a491e7f237c622eb31686ba85a255fba799b7b22ea04a774aa50fa3c22d62` |
| `schemas/scan-config.schema.json` | `12c75f29ea7f64f783fc809caa9968a195ef0f02192840cf8f40845c6c972868` |
| `schemas/unified-results.schema.json` | `c5c7077261b6792823e18e33c732b213186b2d30c15633156539debf9c8dcd02` |
| `scripts/check-fix-allowlist.py` | `5d69357442f52789a1324b9bc0f582bc4a76881ecb7c04c4cec55abc86ce67df` |
| `scripts/create-baseline.ps1` | `43728042a86752b1458a3619a56b98419f7701568ebb1f81da07d4a7f30edccc` |
| `scripts/finalize_baseline.py` | `2dcb9ec84f5832f8970469f0399353530ae627619f3f0c07bd7a7f84f895d1be` |
| `scripts/render-scan-config.py` | `cd7ea5571ef523ecae48a74e23c6248a6de618e60a516c2ef29306e65afa2fe4` |
| `scripts/safe_io.py` | `c16580d9c3adcfaaa28b5f92eccb371c30eac06829d4f188df8a3218a4d8bb47` |
| `scripts/scan-and-fix.ps1` | `ace493a98c2e369f9bce90beeaa40c1aa4aae3ca7118c23bc058a81e5041b406` |
| `scripts/scan-and-fix.sh` | `2285719be92c6b54fb17a00751841c83001f96cf934b1f1dfe6d3d6c85da1d49` |
| `scripts/scan.py` | `8d3353c045308e7a27499d6e1dffcfdfab07707b5b36f8ddfcc7a04e09037447` |
| `scripts/scan_policy.py` | `a64888ae512b598c53a4ad23d628ff06480708edd71d70dd73c365ee629b3bf2` |
| `scripts/scan_reports.py` | `f3aad2b32fb1a64a6806bfb63ef52706fb40ccfbb2f2ca91b3d1c670ad9e7893` |
| `scripts/validate-scan-config.py` | `8668d087b74a995364b74c3f21828020653b4383a5dedc0042af3b461710f52c` |
| `scripts/validate-suppressions.py` | `98ca24768d478977edee68a2e36895b4783be6cbcea5ad63dad0f198fba558e8` |
