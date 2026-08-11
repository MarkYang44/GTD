using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

[Flags]
public enum FileOpenOptions : uint
{
    NoChangeDirectory = 0x00000008,
    PickFolders = 0x00000020,
    ForceFileSystem = 0x00000040,
    PathMustExist = 0x00000800
}

public enum ShellDisplayName : uint
{
    FileSystemPath = 0x80058000
}

[ComImport]
[Guid("42F85136-DB7E-439C-85F1-E4075D135FC8")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IFileDialog
{
    [PreserveSig] int Show(IntPtr parent);
    void SetFileTypes(uint count, IntPtr filterSpec);
    void SetFileTypeIndex(uint index);
    void GetFileTypeIndex(out uint index);
    void Advise(IntPtr events, out uint cookie);
    void Unadvise(uint cookie);
    void SetOptions(FileOpenOptions options);
    void GetOptions(out FileOpenOptions options);
    void SetDefaultFolder(IShellItem shellItem);
    void SetFolder(IShellItem shellItem);
    void GetFolder(out IShellItem shellItem);
    void GetCurrentSelection(out IShellItem shellItem);
    void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string name);
    void GetFileName([MarshalAs(UnmanagedType.LPWStr)] out string name);
    void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string title);
    void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string text);
    void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string label);
    void GetResult(out IShellItem shellItem);
    void AddPlace(IShellItem shellItem, uint alignment);
    void SetDefaultExtension([MarshalAs(UnmanagedType.LPWStr)] string extension);
    void Close(int result);
    void SetClientGuid(ref Guid guid);
    void ClearClientData();
    void SetFilter(IntPtr filter);
}

[ComImport]
[Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IShellItem
{
    void BindToHandler(IntPtr context, ref Guid handler, ref Guid interfaceId, out IntPtr result);
    void GetParent(out IShellItem parent);
    void GetDisplayName(ShellDisplayName displayName, out IntPtr name);
    void GetAttributes(uint mask, out uint attributes);
    void Compare(IShellItem other, uint hint, out int order);
}

public static class ModernFolderPicker
{
    private const int CancelledHResult = unchecked((int)0x800704C7);
    private static readonly Guid ShellItemGuid = new Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE");
    private static readonly Guid FileOpenDialogClassId = new Guid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7");

    [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
    private static extern void SHCreateItemFromParsingName(
        [MarshalAs(UnmanagedType.LPWStr)] string path,
        IntPtr context,
        ref Guid interfaceId,
        out IShellItem shellItem
    );

    public static IFileDialog CreateDialog()
    {
        Type type = Type.GetTypeFromCLSID(FileOpenDialogClassId, true);
        return (IFileDialog)Activator.CreateInstance(type);
    }

    public static string Pick(string initialDirectory)
    {
        IFileDialog dialog = null;
        IShellItem initialItem = null;
        IShellItem selectedItem = null;
        try
        {
            dialog = CreateDialog();
            dialog.SetOptions(
                FileOpenOptions.PickFolders |
                FileOpenOptions.ForceFileSystem |
                FileOpenOptions.PathMustExist |
                FileOpenOptions.NoChangeDirectory
            );
            dialog.SetTitle("选择下载文件夹");
            dialog.SetOkButtonLabel("选择文件夹");
            if (!String.IsNullOrWhiteSpace(initialDirectory) && Directory.Exists(initialDirectory))
            {
                Guid guid = ShellItemGuid;
                SHCreateItemFromParsingName(initialDirectory, IntPtr.Zero, ref guid, out initialItem);
                dialog.SetFolder(initialItem);
            }

            // The picker runs in a dedicated STA helper process. Giving it the
            // browser's foreground HWND as a cross-process owner can deadlock
            // IFileDialog.Show before Windows creates a visible dialog. An
            // ownerless native dialog is correctly activated by the shell and
            // also avoids coupling the Flask request thread to Edge/Chrome.
            int result = dialog.Show(IntPtr.Zero);
            if (result == CancelledHResult) return null;
            if (result != 0) Marshal.ThrowExceptionForHR(result);

            dialog.GetResult(out selectedItem);
            IntPtr pointer = IntPtr.Zero;
            try
            {
                selectedItem.GetDisplayName(ShellDisplayName.FileSystemPath, out pointer);
                return Marshal.PtrToStringUni(pointer);
            }
            finally
            {
                if (pointer != IntPtr.Zero) Marshal.FreeCoTaskMem(pointer);
            }
        }
        finally
        {
            Release(selectedItem);
            Release(initialItem);
            Release(dialog);
        }
    }

    public static void Release(object value)
    {
        if (value != null && Marshal.IsComObject(value)) Marshal.FinalReleaseComObject(value);
    }
}

public static class Program
{
    [DllImport("user32.dll")]
    private static extern bool SetProcessDpiAwarenessContext(IntPtr value);

    [STAThread]
    public static int Main(string[] args)
    {
        try
        {
            try { SetProcessDpiAwarenessContext(new IntPtr(-4)); } catch { }
            if (args.Length == 1 && args[0] == "--validate")
            {
                IFileDialog dialog = ModernFolderPicker.CreateDialog();
                ModernFolderPicker.Release(dialog);
                return 0;
            }
            if (args.Length != 2) return 3;
            string selected = ModernFolderPicker.Pick(args[0]);
            if (selected == null) return 2;
            File.WriteAllText(args[1], selected, new UTF8Encoding(false));
            return 0;
        }
        catch (Exception error)
        {
            if (args.Length >= 2)
            {
                try { File.WriteAllText(args[1], "ERROR:" + error.Message, new UTF8Encoding(false)); }
                catch { }
            }
            return 1;
        }
    }
}
