# SPDX-License-Identifier: GPL-3.0-or-later
#Requires -Version 7
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
    # "working" expands in place, so "working,roblox" also works.
    $out = @()
    foreach ($p in (Split-List $Profiles)) {
        if ($p -eq "working") { $out += $script:WorkingProfiles } else { $out += $p }
    }
    return , @($out | Select-Object -Unique)
}

function Get-ProfileStatus {
    # The status = "..." line of profiles/<name>/profile.toml, or "" if absent.
    param([string]$Name)
    $toml = Join-Path $script:RepoRoot "profiles/$Name/profile.toml"
    if (-not (Test-Path -LiteralPath $toml)) { return "" }
    $m = Select-String -LiteralPath $toml -Pattern '^\s*status\s*=\s*"([^"]*)"' | Select-Object -First 1
    if ($m) { return $m.Matches[0].Groups[1].Value }
    return ""
}

function Invoke-Blender {
    # Runs Blender headless and streams its output. Returns the exit code.
    param([string]$Exe, [string[]]$Arguments)
    & $Exe --background --factory-startup --python-exit-code 1 @Arguments 2>&1 | ForEach-Object { "$_" } | Write-Host
    return $LASTEXITCODE
}
