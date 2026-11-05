$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PIP_NO_INDEX = '0'
$env:NPM_CONFIG_OFFLINE = 'false'
if (!(Get-Command python -ErrorAction SilentlyContinue)) { throw 'Please install Python 3.11+ first.' }
if (!(Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Please install Node.js 22+ first.' }
if (!(Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment.' }
}
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
npm.cmd ci --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
Write-Host 'Ready. Double-click start.cmd to open Ai4PDF.' -ForegroundColor Green
