$ErrorActionPreference = "Stop"

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public static class LsaRightsReader {
    [StructLayout(LayoutKind.Sequential)]
    private struct LSA_OBJECT_ATTRIBUTES {
        public int Length;
        public IntPtr RootDirectory;
        public IntPtr ObjectName;
        public uint Attributes;
        public IntPtr SecurityDescriptor;
        public IntPtr SecurityQualityOfService;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct LSA_UNICODE_STRING {
        public ushort Length;
        public ushort MaximumLength;
        public IntPtr Buffer;
    }

    [DllImport("advapi32.dll")]
    private static extern uint LsaOpenPolicy(
        IntPtr SystemName,
        ref LSA_OBJECT_ATTRIBUTES ObjectAttributes,
        uint DesiredAccess,
        out IntPtr PolicyHandle);

    [DllImport("advapi32.dll")]
    private static extern uint LsaEnumerateAccountRights(
        IntPtr PolicyHandle,
        byte[] AccountSid,
        out IntPtr UserRights,
        out uint CountOfRights);

    [DllImport("advapi32.dll")]
    private static extern uint LsaClose(IntPtr ObjectHandle);

    [DllImport("advapi32.dll")]
    private static extern uint LsaFreeMemory(IntPtr Buffer);

    public static string[] GetRights(byte[] sid) {
        const uint POLICY_LOOKUP_NAMES = 0x00000800;
        var attrs = new LSA_OBJECT_ATTRIBUTES();
        attrs.Length = Marshal.SizeOf(attrs);
        IntPtr policy;
        uint status = LsaOpenPolicy(IntPtr.Zero, ref attrs, POLICY_LOOKUP_NAMES, out policy);
        if (status != 0) throw new InvalidOperationException("LsaOpenPolicy=" + status);
        try {
            IntPtr rights;
            uint count;
            status = LsaEnumerateAccountRights(policy, sid, out rights, out count);
            if (status == 0xC0000034) return new string[0];
            if (status != 0) throw new InvalidOperationException("LsaEnumerateAccountRights=" + status);
            try {
                var result = new string[count];
                int size = Marshal.SizeOf(typeof(LSA_UNICODE_STRING));
                for (int i = 0; i < count; i++) {
                    var item = (LSA_UNICODE_STRING)Marshal.PtrToStructure(
                        IntPtr.Add(rights, i * size), typeof(LSA_UNICODE_STRING));
                    result[i] = Marshal.PtrToStringUni(item.Buffer, item.Length / 2);
                }
                return result;
            } finally { LsaFreeMemory(rights); }
        } finally { LsaClose(policy); }
    }
}
"@

$sid = New-Object System.Security.Principal.SecurityIdentifier(
    "S-1-5-21-1664616495-3062778491-3524446278-1009"
)
$bytes = New-Object byte[] $sid.BinaryLength
$sid.GetBinaryForm($bytes, 0)
$rights = [LsaRightsReader]::GetRights($bytes)
Write-Output ("ACCOUNT=" + $sid.Translate([System.Security.Principal.NTAccount]).Value)
Write-Output ("RIGHTS=" + ($rights -join ","))
Write-Output ("SE_BATCH_LOGON_RIGHT=" + ($rights -contains "SeBatchLogonRight"))
Write-Output ("SE_DENY_BATCH_LOGON_RIGHT=" + ($rights -contains "SeDenyBatchLogonRight"))
