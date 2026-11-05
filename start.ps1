$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$readerPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $readerPython) -or !(Test-Path -LiteralPath (Join-Path $PSScriptRoot 'node_modules\pdfjs-dist\build\pdf.mjs')) -or !(Test-Path -LiteralPath (Join-Path $PSScriptRoot 'node_modules\katex\dist\katex.mjs'))) {
    & (Join-Path $PSScriptRoot 'setup.ps1')
}
try {
    $running = Invoke-WebRequest -Uri 'http://127.0.0.1:8765/' -UseBasicParsing -TimeoutSec 2
    if ($running.Content -match '(Ai4PDF|Paperdesk)') {
        Start-Process 'http://127.0.0.1:8765/'
        exit 0
    }
} catch { }
Write-Host 'Ai4PDF: http://127.0.0.1:8765/' -ForegroundColor Green
Write-Host 'Keep this window open. Press Ctrl+C to stop.'
& $readerPython app.py --open
exit $LASTEXITCODE
