using System;
using System.Diagnostics;
using System.IO;
using System.Management;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading;
using Microsoft.Win32.SafeHandles;

public static class OffGridSafeEjectExe {
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    public static extern SafeFileHandle CreateFile(
        string lpFileName, uint dwDesiredAccess, uint dwShareMode,
        IntPtr lpSecurityAttributes, uint dwCreationDisposition,
        uint dwFlagsAndAttributes, IntPtr hTemplateFile);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool FlushFileBuffers(SafeFileHandle hFile);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool DeviceIoControl(
        SafeFileHandle hDevice, uint dwIoControlCode,
        IntPtr lpInBuffer, uint nInBufferSize,
        IntPtr lpOutBuffer, uint nOutBufferSize,
        out uint lpBytesReturned, IntPtr lpOverlapped);

    private static string LogPath;

    private static void Log(string msg) {
        try {
            File.AppendAllText(LogPath, DateTime.UtcNow.ToString("o") + " [EXE] " + msg + Environment.NewLine);
        } catch {}
    }

    private static void CloseExplorerWindows(string driveLetter) {
        try {
            Type shellType = Type.GetTypeFromProgID("Shell.Application");
            if (shellType == null) return;
            object shell = Activator.CreateInstance(shellType);
            object windows = shellType.InvokeMember("Windows", BindingFlags.InvokeMethod, null, shell, null);
            var enumerable = windows as System.Collections.IEnumerable;
            if (enumerable == null) return;
            string prefixUrl = "file:///" + driveLetter + ":";
            foreach (object win in enumerable) {
                try {
                    Type wt = win.GetType();
                    string locUrl = Convert.ToString(wt.InvokeMember("LocationURL", BindingFlags.GetProperty, null, win, null) ?? "");
                    if (locUrl.StartsWith(prefixUrl, StringComparison.OrdinalIgnoreCase)) {
                        Log("Closing Explorer window: " + locUrl);
                        wt.InvokeMember("Quit", BindingFlags.InvokeMethod, null, win, null);
                    }
                } catch {}
            }
        } catch {}
    }

    private static void KillDriveProcesses(string driveLetter) {
        int selfPid = Process.GetCurrentProcess().Id;
        string prefix = driveLetter + ":\\";
        try {
            using (var searcher = new ManagementObjectSearcher(
                "SELECT ProcessId, Name, ExecutablePath, CommandLine FROM Win32_Process")) {
                foreach (ManagementObject obj in searcher.Get()) {
                    try {
                        int pid = Convert.ToInt32(obj["ProcessId"]);
                        if (pid == selfPid || pid <= 4) continue;
                        string exe = Convert.ToString(obj["ExecutablePath"] ?? "");
                        string cmd = Convert.ToString(obj["CommandLine"] ?? "");
                        string name = Convert.ToString(obj["Name"] ?? "");
                        if (exe.StartsWith(prefix, StringComparison.OrdinalIgnoreCase) ||
                            cmd.IndexOf(prefix, StringComparison.OrdinalIgnoreCase) >= 0) {
                            Log("Killing process PID=" + pid + " Name=" + name);
                            try {
                                Process p = Process.GetProcessById(pid);
                                p.Kill();
                                p.WaitForExit(1500);
                            } catch {}
                        }
                    } catch {}
                }
            }
        } catch {}

        try {
            foreach (Process p in Process.GetProcesses()) {
                try {
                    if (p.Id == selfPid || p.Id <= 4) continue;
                    string path = p.MainModule != null ? (p.MainModule.FileName ?? "") : "";
                    if (path.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)) {
                        Log("Killing process via MainModule PID=" + p.Id + " Name=" + p.ProcessName);
                        p.Kill();
                        p.WaitForExit(1500);
                    }
                } catch {}
            }
        } catch {}
    }

    private static void ShellEject(string driveLetter) {
        try {
            Type shellType = Type.GetTypeFromProgID("Shell.Application");
            if (shellType == null) return;
            object shell = Activator.CreateInstance(shellType);
            object ns = shellType.InvokeMember("Namespace", BindingFlags.InvokeMethod, null, shell, new object[] { 17 });
            if (ns == null) return;
            object item = ns.GetType().InvokeMember("ParseName", BindingFlags.InvokeMethod, null, ns, new object[] { driveLetter + ":" });
            if (item == null) return;
            Log("Invoking Shell.Application Eject on " + driveLetter + ":");
            item.GetType().InvokeMember("InvokeVerb", BindingFlags.InvokeMethod, null, item, new object[] { "Eject" });
        } catch (Exception ex) {
            Log("ShellEject exception: " + ex.Message);
        }
    }

    private static bool Win32DismountAndEject(string driveLetter) {
        const uint GENERIC_READ = 0x80000000;
        const uint GENERIC_WRITE = 0x40000000;
        const uint FILE_SHARE_READ = 0x1;
        const uint FILE_SHARE_WRITE = 0x2;
        const uint OPEN_EXISTING = 3;
        const uint FSCTL_LOCK_VOLUME = 0x00090018;
        const uint FSCTL_DISMOUNT_VOLUME = 0x00090020;
        const uint IOCTL_STORAGE_MEDIA_REMOVAL = 0x002D4804;
        const uint IOCTL_STORAGE_EJECT_MEDIA = 0x002D4808;

        string volPath = "\\\\.\\" + driveLetter + ":";
        using (SafeFileHandle h = CreateFile(volPath, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, IntPtr.Zero, OPEN_EXISTING, 0, IntPtr.Zero)) {
            if (h.IsInvalid) {
                using (SafeFileHandle h2 = CreateFile(volPath, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, IntPtr.Zero, OPEN_EXISTING, 0, IntPtr.Zero)) {
                    if (h2.IsInvalid) return false;
                    uint br2;
                    return DeviceIoControl(h2, IOCTL_STORAGE_EJECT_MEDIA, IntPtr.Zero, 0, IntPtr.Zero, 0, out br2, IntPtr.Zero);
                }
            }
            try { FlushFileBuffers(h); } catch {}
            uint br;
            bool locked = false;
            for (int i = 0; i < 8; i++) {
                if (DeviceIoControl(h, FSCTL_LOCK_VOLUME, IntPtr.Zero, 0, IntPtr.Zero, 0, out br, IntPtr.Zero)) {
                    locked = true;
                    break;
                }
                Thread.Sleep(250);
            }
            bool dismounted = DeviceIoControl(h, FSCTL_DISMOUNT_VOLUME, IntPtr.Zero, 0, IntPtr.Zero, 0, out br, IntPtr.Zero);
            IntPtr pmr = Marshal.AllocHGlobal(1);
            Marshal.WriteByte(pmr, 0);
            DeviceIoControl(h, IOCTL_STORAGE_MEDIA_REMOVAL, pmr, 1, IntPtr.Zero, 0, out br, IntPtr.Zero);
            Marshal.FreeHGlobal(pmr);
            bool ejected = DeviceIoControl(h, IOCTL_STORAGE_EJECT_MEDIA, IntPtr.Zero, 0, IntPtr.Zero, 0, out br, IntPtr.Zero);
            Log("Win32DismountAndEject locked=" + locked + " dismounted=" + dismounted + " ejected=" + ejected);
            return dismounted || ejected;
        }
    }

    [STAThread]
    public static int Main(string[] args) {
        string tempDir = Path.GetTempPath();
        try { Directory.SetCurrentDirectory(tempDir); } catch {}
        LogPath = Path.Combine(tempDir, "offgridusb_safe_eject.log");

        if (args == null || args.Length < 1) return 1;
        string clean = args[0].Trim().ToUpperInvariant().Replace(":", "").Replace("\\", "").Replace("/", "");
        int delayMs = 800;
        if (args.Length >= 2) int.TryParse(args[1], out delayMs);

        string sysDrive = (Environment.GetEnvironmentVariable("SystemDrive") ?? "C:").Trim().ToUpperInvariant().Replace(":", "");
        if (clean.Length != 1 || clean == "C" || clean == sysDrive) {
            return 1;
        }

        bool createdNew;
        using (var mutex = new Mutex(true, "Local\\OffGridUsbSafeEjectExe_" + clean, out createdNew)) {
            if (!createdNew) return 0;

            try {
                File.WriteAllText(LogPath, DateTime.UtcNow.ToString("o") + " [EXE] Starting safe eject for " + clean + ": (DelayMs=" + delayMs + ", PID=" + Process.GetCurrentProcess().Id + ")" + Environment.NewLine);
            } catch {}

            if (delayMs > 0) Thread.Sleep(delayMs);

            if (!Directory.Exists(clean + ":\\")) {
                Log("ALREADY_DISMOUNTED: " + clean + ":\\ not mounted");
                return 0;
            }

            CloseExplorerWindows(clean);
            KillDriveProcesses(clean);
            Thread.Sleep(250);

            for (int attempt = 0; attempt < 3; attempt++) {
                if (!Directory.Exists(clean + ":\\")) break;
                Win32DismountAndEject(clean);
                if (!Directory.Exists(clean + ":\\")) break;
                ShellEject(clean);
                Thread.Sleep(500);
                KillDriveProcesses(clean);
            }

            Log("Completed safe eject. StillMounted=" + Directory.Exists(clean + ":\\"));
            return 0;
        }
    }
}
