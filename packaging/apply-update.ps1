param(
    [Parameter(Mandatory=$true)][int]$ParentId,
    [Parameter(Mandatory=$true)][string]$Installer,
    [Parameter(Mandatory=$true)][string]$ExpectedHash,
    [Parameter(Mandatory=$true)][string]$InstallDir,
    [Parameter(Mandatory=$true)][int]$Port,
    [Parameter(Mandatory=$true)][string]$ReadyFile
)
$ErrorActionPreference = 'Stop'
# A launcher may inherit PowerShell 7's PSModulePath; use Windows' own modules.
Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Utility/Microsoft.PowerShell.Utility.psd1')
Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Management/Microsoft.PowerShell.Management.psd1')

function Quote-Argument([string]$Value) {
    # Windows CommandLineToArgvW quoting, including spaces and trailing slashes.
    return '"' + [regex]::Replace([regex]::Replace($Value, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1') + '"'
}

$program = Join-Path $InstallDir 'Ai4PDF.exe'
$resultFile = Join-Path (Split-Path -LiteralPath $Installer) 'result.json'
$parent = $null
try {
    if ($Port -lt 1024 -or $Port -gt 65535 -or $ExpectedHash -notmatch '^[a-fA-F0-9]{64}$') { throw 'Invalid update parameters.' }
    if (!(Test-Path -LiteralPath $program -PathType Leaf)) { throw 'Installed program not found.' }
    if ((Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash -ne $ExpectedHash) { throw 'Installer verification failed.' }
    $parent = Get-Process -Id $ParentId -ErrorAction Stop
    [IO.File]::WriteAllText($ReadyFile, 'ready')
    # Wait for THIS process handle, not a reused process ID. Never kill the app.
    if (!$parent.WaitForExit(300000)) { throw 'The application did not exit; update cancelled.' }
    if ((Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash -ne $ExpectedHash) { throw 'Installer verification failed.' }
    $arguments = '/SP- /SILENT /NORESTART /NOCLOSEAPPLICATIONS /DIR=' + (Quote-Argument $InstallDir)
    # This progress window is requested by the user's Install update button.
    $setup = Start-Process -FilePath $Installer -ArgumentList $arguments -PassThru -Wait
    $status = if ($setup.ExitCode -eq 0) { 'completed' } else { 'cancelled' }
    [IO.File]::WriteAllText($resultFile, (@{status=$status;exitCode=$setup.ExitCode} | ConvertTo-Json -Compress))
    # Keep the same origin/port so browser preferences and saved API settings remain.
    Start-Process -FilePath $program -ArgumentList @('--port', "$Port", '--no-browser') -WorkingDirectory $InstallDir -WindowStyle Hidden
} catch {
    [IO.File]::WriteAllText($resultFile, '{"status":"failed"}')
    # If Setup failed after shutdown, make the existing installation usable again.
    if ($parent -and $parent.HasExited -and (Test-Path -LiteralPath $program -PathType Leaf)) {
        Start-Process -FilePath $program -ArgumentList @('--port', "$Port", '--no-browser') -WorkingDirectory $InstallDir -WindowStyle Hidden
    }
    exit 1
}
