// Fixture: planted Semgrep p/typescript finding (eval of user input).
// Used by tests to prove the semgrep-typescript hook + CI scanner detect issues.

export function runUserCode(userInput: string): unknown {
  // Semgrep rule: javascript.lang.security.audit.eval-detected
  // eslint rule: no-eval
  return eval(userInput);
}
