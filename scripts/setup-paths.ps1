# Canonical setup identities shared by onboarding and hook verification.
function Resolve-SetupRealPath {
    param([string]$Path)
    $full = Resolve-ExternalRealPath $Path
    if ([Environment]::OSVersion.Platform -eq 'Win32NT') {
        if (-not ('SetupPathNative' -as [type])) {
            Add-Type @'
using System.Runtime.InteropServices;
using System.Text;
public static class SetupPathNative {
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern uint GetLongPathName(string path, StringBuilder output, uint size);
}
'@
        }
        $buffer = [Text.StringBuilder]::new(32768)
        $length = [SetupPathNative]::GetLongPathName($full, $buffer, $buffer.Capacity)
        if (-not $length -or $length -ge $buffer.Capacity) {
            throw 'Cannot canonicalize setup path'
        }
        $full = $buffer.ToString()
        if ($full.StartsWith('\\?\UNC\', [StringComparison]::OrdinalIgnoreCase)) {
            $full = '\\' + $full.Substring(8)
        } elseif ($full.StartsWith('\\?\')) {
            $full = $full.Substring(4)
        }
    }
    return $full
}

