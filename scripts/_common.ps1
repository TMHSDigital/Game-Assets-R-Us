# SPDX-License-Identifier: GPL-3.0-or-later
# Shared helpers for the scripts in this folder. Dot-source it:  . "$PSScriptRoot/_common.ps1"

$script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$script:WorkingProfiles = @("unity", "unreal", "godot", "gltf_web", "stl_print")

function Resolve-Blender {
    param([string]$Blender)
    # Order: -Blender parameter, GARU_BLENDER environment variable, blender on PATH.
    foreach ($candidate in @($Blender, $env:GARU_BLENDER)) {
        if ($candidate) {
            if (-not (Test-Path $candidate)) { throw "Blender not found at '$candidate'" }
            return (Resolve-Path $candidate).Path
        }
    }
    $cmd = Get-Command blender -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "Blender not found. Pass -Blender <path> or set GARU_BLENDER."
}

function Split-List {
    # Accepts both real arrays and "a,b,c" strings (pwsh -File passes arrays as one string).
    param([string[]]$Items)
    $out = @()
    foreach ($item in $Items) { $out += ($item -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ }) }
    return , $out
}

function Expand-Profiles {
    param([string[]]$Profiles)
    $list = Split-List $Profiles
    if ($list.Count -eq 1 -and $list[0] -eq "working") { return , $script:WorkingProfiles }
    return , $list
}

function Invoke-Blender {
    # Runs Blender headless and streams its output. Returns the exit code.
    param([string]$Exe, [string[]]$Arguments)
    & $Exe --background --factory-startup @Arguments 2>&1 | ForEach-Object { "$_" } | Write-Host
    return $LASTEXITCODE
}
