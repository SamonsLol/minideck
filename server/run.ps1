# MiniDeck para Windows: arranca el servidor sin consola visible y pone un
# icono en la bandeja del sistema (clic derecho -> Mostrar QR / Salir).
# Se lanza con "Mini Desk.bat" (doble clic) o:
#   powershell -ExecutionPolicy Bypass -File server\run.ps1

$ErrorActionPreference = "Stop"
$ServerDir = $PSScriptRoot
$RootDir   = Split-Path $ServerDir -Parent

# Ocultar la ventana de consola de este propio script
Add-Type -Name Window -Namespace Win -MemberDefinition '[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);'
[Win.Window]::ShowWindow((Get-Process -Id $PID).MainWindowHandle, 0) | Out-Null

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# Python: primero el venv del proyecto (.venv), si no, el del sistema
$python = $null
foreach ($candidate in @("$RootDir\.venv\Scripts\pythonw.exe", "$RootDir\.venv\Scripts\python.exe")) {
    if (Test-Path $candidate) { $python = $candidate; break }
}
if (-not $python) {
    $cmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if (-not $cmd) { $cmd = Get-Command python.exe -ErrorAction SilentlyContinue }
    if ($cmd) { $python = $cmd.Source }
}
if (-not $python) {
    [System.Windows.Forms.MessageBox]::Show("No se encontró Python. Instálalo desde python.org o crea el venv .venv (ver README).", "MiniDeck") | Out-Null
    exit 1
}

# Icono de bandeja
$tray = New-Object System.Windows.Forms.NotifyIcon
$iconPath = Join-Path $RootDir "assets\minideck.ico"
if (Test-Path $iconPath) {
    $tray.Icon = New-Object System.Drawing.Icon($iconPath)
} else {
    $tray.Icon = [System.Drawing.SystemIcons]::Application
}
$tray.Text = "MiniDeck"
$tray.BalloonTipText = "MiniDeck se está ejecutando"
$tray.Visible = $true
$tray.ShowBalloonTip(3000)

# Servidor en segundo plano (asíncrono, para no congelar el icono)
$processInfo = New-Object System.Diagnostics.ProcessStartInfo
$processInfo.FileName = $python
$processInfo.Arguments = "main.py"
$processInfo.WorkingDirectory = $ServerDir
$processInfo.CreateNoWindow = $true
$processInfo.UseShellExecute = $false
$pythonProcess = [System.Diagnostics.Process]::Start($processInfo)

# Menú contextual
$menu = New-Object System.Windows.Forms.ContextMenuStrip
$qrItem = $menu.Items.Add("Mostrar QR")
$qrItem.add_Click({ Start-Process "http://localhost:8765/qr" })
$openItem = $menu.Items.Add("Abrir en este PC")
$openItem.add_Click({ Start-Process "http://localhost:8765" })
$exitItem = $menu.Items.Add("Salir")
$exitItem.add_Click({
    if ($pythonProcess -and -not $pythonProcess.HasExited) { $pythonProcess.Kill() }
    $tray.Visible = $false
    $tray.Dispose()
    Stop-Process -Id $PID
})
$tray.ContextMenuStrip = $menu
$tray.add_DoubleClick({ Start-Process "http://localhost:8765/qr" })

# Mantener vivo el icono mientras el servidor trabaje
while (-not $pythonProcess.HasExited) {
    [System.Windows.Forms.Application]::DoEvents()
    Start-Sleep -Milliseconds 100
}

$tray.Visible = $false
$tray.Dispose()
