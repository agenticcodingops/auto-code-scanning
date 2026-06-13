// Fixture: clean C# that should pass semgrep-csharp + dotnet-format.
using System.Security.Cryptography;
using System.Text;

namespace Fixtures
{
    public static class Clean
    {
        public static byte[] StrongHash(string input)
        {
            using var sha = SHA256.Create();
            return sha.ComputeHash(Encoding.UTF8.GetBytes(input));
        }
    }
}
