param(
    [string]$Python = 'python',
    [string]$InnoCompiler = '',
    [switch]$SkipDependencies
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Push-Location $projectRoot
try {
    $buildPython = Join-Path $projectRoot '.build-venv/Scripts/python.exe'
    if (!$SkipDependencies) {
        & $Python -c "import sys,struct; assert sys.version_info[:2] == (3,13) and struct.calcsize('P') == 8, 'Build requires 64-bit Python 3.13'"
        if ($LASTEXITCODE -ne 0) { throw 'Python version check failed' }
        if (!(Test-Path -LiteralPath $buildPython)) {
            & $Python -m venv .build-venv
            if ($LASTEXITCODE -ne 0) { throw 'Cannot create build environment' }
        }
        & $buildPython -m pip install -r requirements-build.lock
        if ($LASTEXITCODE -ne 0) { throw 'Python dependencies failed' }
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'JavaScript dependencies failed' }
    }
    $version = (Get-Content package.json -Raw | ConvertFrom-Json).version
    if ($version -notmatch '^\d+\.\d+\.\d+$') { throw 'Version must use x.y.z format' }
    New-Item -ItemType Directory -Force build,release | Out-Null
    & $buildPython packaging/make_icon.py
    if ($LASTEXITCODE -ne 0) { throw 'Icon conversion failed' }
    & $buildPython packaging/prepare_release.py
    if ($LASTEXITCODE -ne 0) { throw 'Release source preparation failed' }
    & $buildPython packaging/version_resource.py
    if ($LASTEXITCODE -ne 0) { throw 'Version resource failed' }
    & $buildPython -m PyInstaller --noconfirm --clean --log-level WARN packaging/Ai4PDF.spec
    if ($LASTEXITCODE -ne 0) { throw 'Executable build failed' }
    & $buildPython packaging/smoke_release.py dist/Ai4PDF/Ai4PDF.exe
    if ($LASTEXITCODE -ne 0) { throw 'Packaged application smoke test failed' }
    if (!$InnoCompiler) { $InnoCompiler = & "$PSScriptRoot/bootstrap_inno.ps1" }
    & $InnoCompiler /Q "/DAppVersion=$version" packaging/installer.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
    & $buildPython packaging/finish_release.py
    if ($LASTEXITCODE -ne 0) { throw 'Release archives failed' }
    Write-Host "Release ready: $projectRoot\release" -ForegroundColor Green
} finally { Pop-Location }
