$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw 'Run start.bat first to install the Python environment.'
}
$taskShell = New-Object -ComObject WScript.Shell
$taskDestinations = @(
    [Environment]::GetFolderPath('Desktop'),
    (Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs')
)
foreach ($taskDestination in $taskDestinations) {
    $taskLink = $taskShell.CreateShortcut((Join-Path $taskDestination 'Mandarin Studio.lnk'))
    $taskLink.TargetPath = $taskPython
    $taskLink.Arguments = '"' + (Join-Path $taskRoot 'launch.pyw') + '"'
    $taskLink.WorkingDirectory = $taskRoot
    $taskLink.IconLocation = (Join-Path $taskRoot 'artwork\mandarin_studio.ico') + ',0'
    $taskLink.Description = 'Mandarin Studio - Chinese podcast video maker'
    $taskLink.Save()
}
