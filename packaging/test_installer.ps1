param([string]$InnoCompiler = '')
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$version = (Get-Content (Join-Path $projectRoot 'package.json') -Raw | ConvertFrom-Json).version
$testAppId = '{750F8334-7480-4F46-8EF2-432EE24FB2B0}'
$uninstallKey = 'HKCU:/Software/Microsoft/Windows/CurrentVersion/Uninstall/' + $testAppId + '_is1'
if (Test-Path -LiteralPath $uninstallKey) { throw 'A previous test install is still present; it will not be overwritten.' }
$testRoot = Join-Path $projectRoot ('tmp/installer-' + [guid]::NewGuid().ToString('N'))
$installRoot = Join-Path $testRoot 'program'
$profileRoot = Join-Path $testRoot 'profile'
New-Item -ItemType Directory -Force $testRoot,$profileRoot | Out-Null
if (!$InnoCompiler) { $InnoCompiler = & "$PSScriptRoot/bootstrap_inno.ps1" }
# The exact installer code is tested with a separate AppId to leave any real installation alone.
& $InnoCompiler /Q "/DAppVersion=$version" ('/DInstallerAppId={' + $testAppId) /DInstallerFilename=Ai4PDF-installer-test ("/O" + $testRoot) (Join-Path $PSScriptRoot 'installer.iss')
if ($LASTEXITCODE -ne 0) { throw 'Test installer compilation failed' }
$Installer = Join-Path $testRoot 'Ai4PDF-installer-test.exe'
$configRoot = Join-Path $profileRoot 'Ai4PDF'
$personalData = Join-Path $testRoot '论文库 Selected library'
$sentinel = Join-Path $personalData 'keep-personal-data.txt'
$savedLocalAppData = $env:LOCALAPPDATA
$savedAppHome = $env:AI4PDF_HOME
$savedData = $env:AI4PDF_DATA
$savedLegacyData = $env:PAPERDESK_DATA
$env:LOCALAPPDATA = $profileRoot
$env:AI4PDF_HOME = $configRoot
$env:AI4PDF_DATA = $null
$env:PAPERDESK_DATA = $null
$installed = $false
try {
    $arguments = @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/NOICONS','/TASKS=""',('/DIR="' + $installRoot + '"'),('/LOG="' + (Join-Path $testRoot 'install.log') + '"'))
    $invalidArguments = $arguments + ('/LIBRARYDIR="' + (Join-Path $installRoot 'data') + '"')
    $process = Start-Process -FilePath $Installer -ArgumentList $invalidArguments -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -eq 0 -or (Test-Path -LiteralPath (Join-Path $configRoot 'library-location.json'))) { throw 'Invalid destination was not rejected safely' }
    $selectedArguments = $arguments + ('/LIBRARYDIR="' + $personalData + '"')
    $process = Start-Process -FilePath $Installer -ArgumentList $selectedArguments -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Installer failed: $($process.ExitCode)" }
    $installed = $true
    $executable = Join-Path $installRoot 'Ai4PDF.exe'
    if (!(Test-Path -LiteralPath $executable)) { throw 'Installed executable missing' }
    $pointer = Join-Path $configRoot 'library-location.json'
    $savedPointer = Get-Content -LiteralPath $pointer -Raw -Encoding utf8 | ConvertFrom-Json
    if ($savedPointer.path -ne $personalData) { throw 'Installer did not persist the selected Unicode library path' }
    # Before any documents exist, re-running setup can save the chosen location again.
    $process = Start-Process -FilePath $Installer -ArgumentList $selectedArguments -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw 'Reinstall with an empty configured library failed' }
    & (Join-Path $projectRoot '.build-venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'check_installed_library.py') $executable $configRoot $personalData
    if ($LASTEXITCODE -ne 0) { throw 'Installed app did not use the selected library' }
    Set-Content -LiteralPath $sentinel -Value 'Keep this document after upgrade and uninstall.'
    $sentinelHash = (Get-FileHash -LiteralPath $sentinel).Hash
    $pointerHash = (Get-FileHash -LiteralPath $pointer).Hash
    & (Join-Path $projectRoot '.build-venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'smoke_release.py') $executable
    if ($LASTEXITCODE -ne 0) { throw 'Installed EXE smoke test failed' }
    $switchArguments = $arguments + ('/LIBRARYDIR="' + (Join-Path $testRoot 'do-not-switch') + '"')
    $process = Start-Process -FilePath $Installer -ArgumentList $switchArguments -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -eq 0) { throw 'Upgrade unexpectedly switched an existing library' }
    # Reinstall to the same destination to exercise the upgrade path.
    $process = Start-Process -FilePath $Installer -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw 'Reinstall failed' }
    if ((Get-FileHash -LiteralPath $sentinel).Hash -ne $sentinelHash) { throw 'Upgrade changed personal data' }
    if ((Get-FileHash -LiteralPath $pointer).Hash -ne $pointerHash) { throw 'Upgrade overwrote library settings' }
    & (Join-Path $projectRoot '.build-venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'check_installed_library.py') $executable $configRoot $personalData
    if ($LASTEXITCODE -ne 0) { throw 'Upgraded app lost the chosen library' }
    & (Join-Path $projectRoot '.build-venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'smoke_update_install.py') $executable $configRoot $personalData $Installer
    if ($LASTEXITCODE -ne 0) { throw 'Update helper did not preserve the selected library or restart correctly' }
} finally {
    if ($installed) {
        # Only execute the uninstaller belonging to this verified temporary installation.
        $resolvedInstall = [IO.Path]::GetFullPath($installRoot)
        $resolvedTest = [IO.Path]::GetFullPath($testRoot) + [IO.Path]::DirectorySeparatorChar
        if (!$resolvedInstall.StartsWith($resolvedTest, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe test path' }
        $uninstaller = Join-Path $resolvedInstall 'unins000.exe'
        if (Test-Path -LiteralPath $uninstaller) {
            $process = Start-Process -FilePath $uninstaller -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',('/LOG="' + (Join-Path $testRoot 'uninstall.log') + '"')) -WindowStyle Hidden -Wait -PassThru
            if ($process.ExitCode -ne 0) { throw 'Uninstall failed' }
        }
    }
    $env:LOCALAPPDATA = $savedLocalAppData
    $env:AI4PDF_HOME = $savedAppHome
    $env:AI4PDF_DATA = $savedData
    $env:PAPERDESK_DATA = $savedLegacyData
}
if (Test-Path -LiteralPath (Join-Path $installRoot 'Ai4PDF.exe')) { throw 'Uninstall left the executable behind' }
if ((Get-FileHash -LiteralPath $sentinel).Hash -ne $sentinelHash) { throw 'Uninstall changed personal data' }
if ((Get-FileHash -LiteralPath $pointer).Hash -ne $pointerHash) { throw 'Uninstall removed library settings' }
Write-Host 'PASS: custom Unicode library, installed EXE, invalid-path rejection, upgrade and uninstall preserve documents and settings'
Write-Host "Test logs: $testRoot"
