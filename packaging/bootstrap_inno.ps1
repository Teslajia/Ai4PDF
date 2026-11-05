param([string]$ToolDirectory = (Join-Path $PSScriptRoot '../tmp/build-tools'))
$ErrorActionPreference = 'Stop'
$ToolDirectory = [IO.Path]::GetFullPath($ToolDirectory)
$compiler = Join-Path $ToolDirectory 'InnoSetup/ISCC.exe'
if (Test-Path -LiteralPath $compiler) { Write-Output $compiler; exit 0 }
New-Item -ItemType Directory -Force -Path $ToolDirectory | Out-Null
$download = Join-Path $ToolDirectory 'innosetup.exe'
Invoke-WebRequest -Uri 'https://github.com/jrsoftware/issrc/releases/download/is-7_1_1/innosetup-7.1.1-x64.exe' -OutFile $download -TimeoutSec 180
$expected = '8A5A6711C3766A6E5FB74F280BA0E3551E719CE94538D901FDBD1F8F9920B3F0'
if ((Get-FileHash -LiteralPath $download -Algorithm SHA256).Hash -ne $expected) { throw 'Inno Setup checksum mismatch' }
if ((Get-AuthenticodeSignature -LiteralPath $download).Status -ne 'Valid') { throw 'Inno Setup signature verification failed' }
$destination = Join-Path $ToolDirectory 'InnoSetup'
$process = Start-Process -FilePath $download -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER','/NOICONS',('/DIR="' + $destination + '"')) -WindowStyle Hidden -Wait -PassThru
if ($process.ExitCode -ne 0 -or !(Test-Path -LiteralPath $compiler)) { throw 'Inno Setup installation failed' }
Write-Output $compiler
