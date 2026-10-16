// WorkBuddy 网关启动器
//
// 干什么：双击它 = 双击同目录下的 start-wb-proxy.bat，但窗口直接以"最小化"打开。
//
// 为什么编译成 winexe（图形程序）而不是 console（控制台程序）：
//   控制台程序启动时 Windows 会先给它分配一个黑窗口，那一下"闪黑框"就是这么来的。
//   winexe 根本不分配控制台，所以外壳本身完全不闪；
//   它再用 ShellExecuteEx 把真正的黑窗口按"最小化"建出来。
//
// 为什么用 UseShellExecute = true：
//   只有走 shell 这条路，WindowStyle 才会作为 nShow 传给新进程，
//   新控制台窗口才会"生下来就是最小化的"，而不是先正常显示再被压下去。
//   （UseShellExecute = false 时 WindowStyle 对控制台程序不生效。）
//
// 为什么不自己找 python：找 Python 的逻辑留在 bat 里，以后原作者更新 bat，
//   这个 exe 不用重新编译。exe 只负责"带图标 + 最小化"这一件事。

using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;

internal static class Launcher
{
    private const string BatName = "start-wb-proxy.bat";
    private const string Title = "WorkBuddy 网关";

    private const uint MB_OK = 0x00000000;
    private const uint MB_ICONERROR = 0x00000010;
    private const uint MB_TOPMOST = 0x00040000;

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int MessageBoxW(IntPtr hWnd, string text, string caption, uint type);

    private static void Show(string text, uint icon)
    {
        MessageBoxW(IntPtr.Zero, text, Title, MB_OK | icon | MB_TOPMOST);
    }

    private static string ExeDir()
    {
        try
        {
            string loc = Assembly.GetExecutingAssembly().Location;
            if (!string.IsNullOrEmpty(loc))
            {
                return Path.GetDirectoryName(loc);
            }
        }
        catch (Exception)
        {
            // 忽略，走下面的兜底
        }
        try
        {
            return Path.GetDirectoryName(Process.GetCurrentProcess().MainModule.FileName);
        }
        catch (Exception)
        {
            return Directory.GetCurrentDirectory();
        }
    }

    private static string QuoteArgs(string[] args)
    {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < args.Length; i++)
        {
            if (i > 0)
            {
                sb.Append(' ');
            }
            sb.Append('"');
            sb.Append(args[i].Replace("\"", "\\\""));
            sb.Append('"');
        }
        return sb.ToString();
    }

    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            string dir = ExeDir();
            string bat = Path.Combine(dir, BatName);

            if (!File.Exists(bat))
            {
                Show("找不到启动脚本，无法启动。\r\n\r\n它应该在：\r\n" + bat +
                     "\r\n\r\n请把本程序和 " + BatName + " 放在同一个文件夹里。",
                     MB_ICONERROR);
                return 2;
            }

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = bat;
            psi.WorkingDirectory = dir;
            psi.UseShellExecute = true;
            psi.WindowStyle = ProcessWindowStyle.Minimized;
            if (args != null && args.Length > 0)
            {
                psi.Arguments = QuoteArgs(args);
            }

            Process.Start(psi);
            return 0;
        }
        catch (Exception ex)
        {
            Show("启动失败：\r\n\r\n" + ex.GetType().Name + ": " + ex.Message, MB_ICONERROR);
            return 1;
        }
    }
}
