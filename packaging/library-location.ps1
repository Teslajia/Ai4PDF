param(
    [Parameter(Mandatory=$true)][ValidateSet('Inspect','Validate','Commit')][string]$Mode,
    [Parameter(Mandatory=$true)][string]$ConfigRoot,
    [Parameter(Mandatory=$true)][string]$ResultFile,
    [string]$LibraryPath = '',
    [string]$InstallDir = '',
    [string]$ExpectedPath = '',
    [string]$ExpectedMode = ''
)
# Windows PowerShell 5.1 is supplied with Windows 10/11. No Python is needed here.
$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Full-Directory([string]$Value) {
    if ($Value -notmatch '^(?:[A-Za-z]:[\\/]|\\\\[^\\]+\\[^\\]+)') { throw 'Please choose an absolute folder path.' }
    $full = [IO.Path]::GetFullPath($Value)
    $root = [IO.Path]::GetPathRoot($full)
    foreach ($part in $full.Substring($root.Length).Split([char]'\')) {
        if ($part -and ($part -match '[<>:"|?*\x00-\x1f]' -or $part.TrimEnd(' ','.') -ne $part -or $part -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)')) {
            throw 'The folder name contains characters that Windows does not support.'
        }
    }
    if ($full -ne $root) { $full = $full.TrimEnd('\') }
    return $full
}

function Same-Path([string]$Left, [string]$Right) { return [string]::Equals($Left, $Right, [StringComparison]::OrdinalIgnoreCase) }

function Get-LibraryState {
    $override = $env:AI4PDF_DATA
    if (!$override) { $override = $env:PAPERDESK_DATA }
    if ($override) {
        # Existing environment-managed configurations are only displayed, never rewritten.
        return @{ Mode='environment'; Path=[IO.Path]::GetFullPath($override) }
    }
    $pointer = Join-Path $ConfigRoot 'library-location.json'
    $location = Join-Path $ConfigRoot 'data'
    $hasPointer = Test-Path -LiteralPath $pointer
    if ($hasPointer) {
        $saved = [IO.File]::ReadAllText($pointer, $utf8) | ConvertFrom-Json
        if (!$saved.path -or $saved.path -isnot [string]) { throw 'The existing library-location.json is invalid. Please repair it before installing.' }
        $location = Full-Directory $saved.path
    }
    if (Test-Path -LiteralPath $location -PathType Leaf) { throw 'The configured library path is a file, not a folder.' }
    if (($hasPointer -and !(Test-Path -LiteralPath $location -PathType Container)) -or
        ((Test-Path -LiteralPath $location -PathType Container) -and @(Get-ChildItem -LiteralPath $location -Force | Select-Object -First 1).Count)) {
        return @{ Mode='existing'; Path=$location }
    }
    return @{ Mode='new'; Path=$location }
}

function Write-Result([string]$State, [string]$Path, [string]$Message) {
    $messageLine = $Message.Replace("`r",' ').Replace("`n",' ')
    # UTF-16 INI supports non-ASCII paths through Inno Setup's GetIniString.
    [IO.File]::WriteAllText($ResultFile, "[Library]`r`nMode=$State`r`nPath=$Path`r`nMessage=$messageLine`r`n", [Text.Encoding]::Unicode)
}

function Validate-Library([string]$Destination, [string]$ProgramFolder) {
    if ((Same-Path $Destination $ProgramFolder) -or $Destination.StartsWith($ProgramFolder.TrimEnd('\')+'\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'The library must be outside the program installation folder.'
    }
    if (Same-Path $Destination ([IO.Path]::GetPathRoot($Destination))) { throw 'Choose a dedicated library folder, not the root of a drive.' }
    if (Test-Path -LiteralPath $Destination -PathType Leaf) { throw 'The selected path is a file, not a folder.' }
    $ancestor = $Destination
    while ($ancestor) {
        if (Test-Path -LiteralPath $ancestor) {
            $item = Get-Item -LiteralPath $ancestor -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Choose a real folder, not a symbolic link or junction.' }
        }
        $ancestor = [IO.Path]::GetDirectoryName($ancestor.TrimEnd('\'))
    }
    if (Test-Path -LiteralPath $Destination -PathType Container) {
        $items = @(Get-ChildItem -LiteralPath $Destination -Force)
        if ($items.Count) {
            $recognized = $false
            $catalog = Join-Path $Destination 'library.json'
            if (Test-Path -LiteralPath $catalog -PathType Leaf) {
                $saved = [IO.File]::ReadAllText($catalog, $utf8) | ConvertFrom-Json
                $recognized = $null -ne $saved.folders -and $null -ne $saved.documents
            }
            foreach ($item in $items) {
                if ($item.PSIsContainer -and $item.Name -match '^[a-f0-9]{24}$' -and
                    (Test-Path -LiteralPath (Join-Path $item.FullName 'document.json')) -and
                    (Test-Path -LiteralPath (Join-Path $item.FullName 'original.pdf'))) { $recognized = $true; break }
            }
            if (!$recognized) { throw 'Choose an empty folder or an existing Ai4PDF library. Ordinary PDF folders are not imported automatically.' }
        }
    }
    # Probe the nearest existing parent, then remove only our newly created probe.
    # Validation does not create the chosen folder, so Cancel leaves no library behind.
    $parent = $Destination
    while (!(Test-Path -LiteralPath $parent -PathType Container)) {
        $parent = [IO.Path]::GetDirectoryName($parent)
        if (!$parent) { throw 'The selected drive or network location is not available.' }
    }
    $probe = Join-Path $parent ('.ai4pdf-write-' + [guid]::NewGuid().ToString('N'))
    $stream = [IO.File]::Open($probe, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    $stream.Dispose()
    [IO.File]::Delete($probe)
}

try {
    $ConfigRoot = Full-Directory $ConfigRoot
    $state = Get-LibraryState
    if ($Mode -eq 'Inspect') { Write-Result $state.Mode $state.Path ''; exit 0 }
    $ExpectedPath = Full-Directory $ExpectedPath
    if (!(Same-Path $ExpectedPath $state.Path) -or $ExpectedMode -ne $state.Mode) { throw 'Library settings changed during installation. Restart the installer to use the current settings.' }
    $selected = Full-Directory $LibraryPath
    $program = Full-Directory $InstallDir
    if ($state.Mode -ne 'new') {
        if (!(Same-Path $selected $state.Path)) { throw 'An existing library must be preserved during upgrade. Move it later using Settings > Library migration.' }
        Write-Result $state.Mode $state.Path ''
        exit 0
    }
    Validate-Library $selected $program
    if ($Mode -eq 'Commit') {
        [IO.Directory]::CreateDirectory($ConfigRoot) | Out-Null
        $guard = [IO.File]::Open((Join-Path $ConfigRoot 'desktop.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::ReadWrite)
        $locked = $false
        $temporary = $null
        try {
            if ($guard.Length -eq 0) { $guard.WriteByte(48); $guard.Flush() }
            $guard.Lock(0, 1)
            $locked = $true
            $latest = Get-LibraryState
            if (!(Same-Path $ExpectedPath $latest.Path) -or $ExpectedMode -ne $latest.Mode) { throw 'Library settings changed. Restart the installer.' }
            [IO.Directory]::CreateDirectory($selected) | Out-Null
            $pointer = Join-Path $ConfigRoot 'library-location.json'
            $temporary = Join-Path $ConfigRoot ('library-location-' + [guid]::NewGuid().ToString('N') + '.tmp')
            [IO.File]::WriteAllText($temporary, (@{path=$selected} | ConvertTo-Json -Compress), $utf8)
            # PowerShell 5.1 converts $null to an empty string for this .NET overload.
            if (Test-Path -LiteralPath $pointer) { [IO.File]::Replace($temporary, $pointer, [NullString]::Value) }
            else { [IO.File]::Move($temporary, $pointer) }
        } finally {
            if ($temporary -and (Test-Path -LiteralPath $temporary)) { [IO.File]::Delete($temporary) }
            if ($locked) { $guard.Unlock(0, 1) }
            $guard.Dispose()
        }
    }
    Write-Result $state.Mode $selected ''
    exit 0
} catch {
    Write-Result 'error' '' $_.Exception.Message
    exit 1
}
