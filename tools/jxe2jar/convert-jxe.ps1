# SPDX-License-Identifier: GPL-3.0-only
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InputJxe,

    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory,

    [string]$Python = 'python',

    [string]$ToolCacheRoot = (Join-Path $env:LOCALAPPDATA 'MHI2FirmwareToolkit\tool-cache\jxe2jar-9eeb45bbf14b')
)

$ErrorActionPreference = 'Stop'
$toolRepo = 'https://github.com/luka-dev/jxe2jar.git'
$toolCommit = '9eeb45bbf14bf8afe3452c7be96a4d1f0206a286'

function Assert-ExitCode([string]$Action) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Action failed with exit code $LASTEXITCODE."
    }
}

function Get-Sha256([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$inputFull = (Resolve-Path -LiteralPath $InputJxe).Path
$outputFull = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $outputFull) {
    throw "Output directory already exists; choose a new path: $outputFull"
}
$outputParent = Split-Path -Parent $outputFull
if (-not (Test-Path -LiteralPath $outputParent -PathType Container)) {
    throw "Output parent must already exist: $outputParent"
}

$git = (Get-Command git -ErrorAction Stop).Source
$pythonCommand = Get-Command -Name $Python -ErrorAction Stop
$pythonExe = $pythonCommand.Source
if (-not $pythonExe) { $pythonExe = $pythonCommand.Name }

if (-not (Test-Path -LiteralPath $ToolCacheRoot)) {
    $cacheParent = Split-Path -Parent $ToolCacheRoot
    if (-not (Test-Path -LiteralPath $cacheParent -PathType Container)) {
        New-Item -ItemType Directory -Path $cacheParent -Force | Out-Null
    }
    & $git clone --filter=blob:none --no-checkout $toolRepo $ToolCacheRoot
    Assert-ExitCode 'jxe2jar clone'
}

if (-not (Test-Path -LiteralPath (Join-Path $ToolCacheRoot '.git') -PathType Container)) {
    throw "Tool cache exists but is not a Git checkout: $ToolCacheRoot"
}

$origin = (& $git -C $ToolCacheRoot remote get-url origin | Out-String).Trim()
Assert-ExitCode 'jxe2jar origin lookup'
if ($origin -ne $toolRepo -and $origin -ne 'https://github.com/luka-dev/jxe2jar') {
    throw "Unexpected jxe2jar origin '$origin'; use a fresh -ToolCacheRoot."
}

& $git -C $ToolCacheRoot fetch --depth=1 origin $toolCommit
Assert-ExitCode 'jxe2jar pinned fetch'
& $git -C $ToolCacheRoot checkout --detach --force $toolCommit
Assert-ExitCode 'jxe2jar pinned checkout'

$head = (& $git -C $ToolCacheRoot rev-parse HEAD | Out-String).Trim()
Assert-ExitCode 'jxe2jar HEAD verification'
if ($head -ne $toolCommit) {
    throw "Pinned checkout mismatch: expected $toolCommit, got $head"
}
$dirty = (& $git -C $ToolCacheRoot status --porcelain=v1 | Out-String).Trim()
Assert-ExitCode 'jxe2jar worktree verification'
if ($dirty) {
    throw "Pinned jxe2jar checkout is modified. Preserve it and use a fresh -ToolCacheRoot."
}

New-Item -ItemType Directory -Path $outputFull | Out-Null
$jarPath = Join-Path $outputFull (([System.IO.Path]::GetFileNameWithoutExtension($inputFull)) + '.jar')
$converter = Join-Path $ToolCacheRoot 'src\jxe2jar.py'

& $pythonExe $converter $inputFull $jarPath
Assert-ExitCode 'JXE-to-JAR conversion'

$classCount = (& $pythonExe -c "import sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); bad=z.testzip(); assert bad is None, bad; print(sum(1 for n in z.namelist() if n.endswith('.class')))" $jarPath | Out-String).Trim()
Assert-ExitCode 'JAR integrity validation'
if ([int]$classCount -le 0) {
    throw 'Converted JAR contains no class entries.'
}

$manifest = [ordered]@{
    created_utc = [DateTime]::UtcNow.ToString('o')
    source_file = [System.IO.Path]::GetFileName($inputFull)
    source_bytes = (Get-Item -LiteralPath $inputFull).Length
    source_sha256 = Get-Sha256 $inputFull
    converter_repository = $toolRepo
    converter_commit = $toolCommit
    converter_checkout_clean = $true
    output_jar = [System.IO.Path]::GetFileName($jarPath)
    output_jar_bytes = (Get-Item -LiteralPath $jarPath).Length
    output_jar_sha256 = Get-Sha256 $jarPath
    class_entry_count = [int]$classCount
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $outputFull 'conversion-manifest.json') -Encoding utf8NoBOM
Write-Output "PASS: $outputFull"
