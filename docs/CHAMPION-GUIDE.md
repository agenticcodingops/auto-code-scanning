# Scanning Champion Guide

Guide for developers who champion security scanning adoption within their teams.

## What is a Scanning Champion?

A developer who:

- Uses the scanning tools daily
- Helps teammates with setup and troubleshooting
- Provides feedback to improve the scanning solution
- Advocates for the value of shift-left security

## Champion Selection Criteria

- Respected by peers (technical credibility)
- Uses Terraform regularly
- Comfortable with command-line tools
- Willing to spend 1-2 hours/week on champion activities

## Champion Responsibilities

### Week 1-2

- Install scanning tools in your repository
- Run through the full workflow (commit, fix findings, push)
- Document any issues or friction points

### Ongoing

- Help teammates install and configure
- Triage false positives (create suppressions when justified)
- Participate in monthly champion meetings
- Suggest improvements to hooks and documentation

## Common Issues and Solutions

1. **Hook too slow** - Move to pre-push stage, see [Performance Optimization](PERFORMANCE-OPTIMIZATION.md)
2. **False positive** - Create suppression in `.scan-suppressions.yaml`
3. **Tool not installed** - Re-run setup script
4. **Bypass needed** - Use `git commit --no-verify`, document reason

## Metrics to Track

- Bypass rate for your team (<5% target)
- Hook pass rate (>80% target)
- Time from finding to fix
- Developer satisfaction (quarterly survey)
