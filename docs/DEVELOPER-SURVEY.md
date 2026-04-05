# Developer Satisfaction Survey Template

Use this survey quarterly to measure developer experience with the security scanning solution. Results inform tool improvements and adoption strategy.

## Survey Questions

### Setup Experience (1-5 scale, 1=Very Difficult, 5=Very Easy)

1. How easy was it to install security scanning in your repository?
2. How clear were the setup instructions?
3. How long did the initial setup take? (Select: <5 min, 5-15 min, 15-30 min, 30+ min)

### Hook Performance

4. Pre-commit hooks run fast enough that they don't disrupt my workflow. (1=Strongly Disagree, 5=Strongly Agree)
5. Which hooks, if any, feel too slow? (Select all: trivy-iac-critical, trivy-secrets, validate-suppressions, gitleaks, trivy-iac-full, checkov, tflint, None)
6. How often do you bypass hooks with `--no-verify`? (Never, Rarely, Sometimes, Often, Always)

### False Positive Rate

7. How often do you encounter false positive findings? (Never, Rarely, Sometimes, Often, Always)
8. When you encounter a false positive, is the suppression process clear? (1-5 scale)
9. Which tool produces the most false positives? (Select: Trivy, Checkov, tflint, None, Unsure)

### Suppression Workflow

10. The suppression governance process is straightforward. (1=Strongly Disagree, 5=Strongly Agree)
11. The required fields for suppressions (rule_id, reason, owner, dates) are reasonable. (1-5 scale)
12. The 180-day expiry policy is appropriate. (1-5 scale)
13. How often do you need to create suppressions? (Never, Monthly, Weekly, Daily)

### Remediation Guidance

14. When a hook blocks my commit, the error message clearly tells me how to fix the issue. (1-5 scale)
15. The remediation URLs provided in scan output are helpful. (1-5 scale)
16. I feel confident fixing security findings without external help. (1-5 scale)

### Overall Satisfaction

17. Overall, security scanning makes our codebase more secure. (1=Strongly Disagree, 5=Strongly Agree)
18. Security scanning is worth the time it adds to my workflow. (1-5 scale)
19. I would recommend this scanning setup to other teams. (1=Strongly Disagree, 5=Strongly Agree)
20. What is your overall satisfaction with the security scanning solution? (1-5 scale)

### Open-Ended

21. What is the biggest pain point with the current scanning setup?
22. What improvement would have the most impact on your workflow?
23. Any additional comments or suggestions?

## Administration Guide

### Recommended Frequency
- Quarterly (aligned with suppression review cycle)
- After major tool updates or tier transitions

### Distribution
- Send via your organization's survey tool (Google Forms, SurveyMonkey, etc.)
- Target all developers with scanning installed
- Allow anonymous responses to encourage honesty

### Scoring Interpretation

| Average Score | Interpretation | Action |
|--------------|----------------|--------|
| 4.0-5.0 | Excellent | Maintain current approach |
| 3.0-3.9 | Good | Address specific pain points |
| 2.0-2.9 | Needs Improvement | Investigate and remediate systemic issues |
| 1.0-1.9 | Critical | Pause rollout, address fundamental problems |

### Key Metrics to Track

- **Setup satisfaction** (Q1-Q3): Target average >= 4.0
- **Performance perception** (Q4-Q5): Target: <10% reporting hooks as "too slow"
- **False positive rate** (Q7-Q9): Target: "Rarely" or "Never" from >80% of respondents
- **Bypass rate** (Q6): Target: "Never" or "Rarely" from >95% of respondents
- **Overall satisfaction** (Q17-Q20): Target average >= 3.5
- **Net Promoter Score** (Q19): Target: >60% scoring 4-5

### Reporting Template

After each survey, produce a summary with:
1. Response rate (target: >50% of developers)
2. Average scores per category
3. Trend comparison with previous quarter
4. Top 3 pain points (from open-ended responses)
5. Action items for the next quarter
