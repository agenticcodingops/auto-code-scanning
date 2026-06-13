// Fixture: planted Semgrep p/csharp finding (insecure hash algorithm: MD5).
// Used by tests to prove the semgrep-csharp hook + CI scanner detect app-code issues.
using System;
using System.Security.Cryptography;
using System.Text;

namespace Fixtures
{
    public static class Vulnerable
    {
        // Semgrep rule: csharp.lang.security.insecure-hashalgorithm.*-md5
        public static byte[] WeakHash(string input)
        {
            using var md5 = MD5.Create();
            return md5.ComputeHash(Encoding.UTF8.GetBytes(input));
        }
    }
}
