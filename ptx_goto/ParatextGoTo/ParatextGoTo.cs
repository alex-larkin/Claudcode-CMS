using System;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using Microsoft.Win32;

namespace ParatextGoTo
{
    /// <summary>
    /// Handler for "ptxgoto:MAT.1.5" links in CMS HTML reports. It sends the
    /// reference to Paratext through SantaFe focus sharing, the same way as
    /// Project Checker's ParatextFocusService: write the reference to
    /// HKCU\Software\SantaFe\Focus\ScriptureReference and broadcast the
    /// registered "SantaFeFocus" window message. Paratext follows it only when
    /// the window's scroll group accepts external references.
    /// Anything that is not a plain book.chapter.verse reference is ignored.
    /// </summary>
    internal static class Program
    {
        private const string FocusKey = @"Software\SantaFe\Focus\ScriptureReference";
        private static readonly IntPtr HWND_BROADCAST = new IntPtr(0xffff);
        private const int FocusScriptureReference = 1;

        // [0-9], not \d: .NET's \d also matches other scripts' digits, which int.Parse rejects.
        private static readonly Regex LinkRe = new Regex(
            @"^(?:ptxgoto:)?/*([A-Z0-9]{3})\.([0-9]{1,3})\.([0-9]{1,3})/?$", RegexOptions.IgnoreCase);

        // The ptxgoto: link type that ptx_goto.py registers for the current user.
        private const string ProtocolKey = @"Software\Classes\ptxgoto";

        [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern uint RegisterWindowMessage(string lpString);

        [DllImport("user32.dll", SetLastError = true)]
        private static extern bool PostMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);

        [STAThread]
        private static int Main(string[] args)
        {
            if (args.Length != 1) return 2;
            if (string.Equals(args[0], "--unregister", StringComparison.OrdinalIgnoreCase))
            {
                // Removes the ptxgoto: link type; the reports then show plain references
                // until a check registers it again.
                try { Registry.CurrentUser.DeleteSubKeyTree(ProtocolKey, false); return 0; }
                catch (Exception) { return 1; }
            }
            try
            {
                Match m = LinkRe.Match(Uri.UnescapeDataString(args[0].Trim()));
                if (!m.Success) return 2;
                string reference = m.Groups[1].Value.ToUpperInvariant() + " "
                    + int.Parse(m.Groups[2].Value) + ":" + int.Parse(m.Groups[3].Value);
                using (RegistryKey k = Registry.CurrentUser.CreateSubKey(FocusKey))
                    k.SetValue("", reference);
                uint msg = RegisterWindowMessage("SantaFeFocus");
                if (msg == 0) return 1;
                return PostMessage(HWND_BROADCAST, msg, new IntPtr(FocusScriptureReference), IntPtr.Zero) ? 0 : 1;
            }
            catch (Exception)
            {
                return 1;
            }
        }
    }
}
