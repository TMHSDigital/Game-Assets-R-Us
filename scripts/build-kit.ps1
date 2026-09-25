# SPDX-License-Identifier: GPL-3.0-or-later
<#
.SYNOPSIS
Generate, validate, export, render previews and package a kit.

.EXAMPLE
pwsh scripts/build-kit.ps1 -Kit stone-dungeon-wall-sampler -Profiles unity,unreal,godot,gltf_web,stl_print -Seed 1337

.EXAMPLE
pwsh scripts/build-kit.ps1 -Kit stone-dungeon-wall-sampler -Profiles working -Seed 1337 -Blender C:\blender\blender.exe
#>
param(
    [Parameter(Mandatory = $true)][string]$Kit,
    [Parameter(Mandatory = $true)][string[]]$Profiles,
    [int]$Seed = -1,
    [string]$Blender,
    [string[]]$GeneratorPath = @(),
    [string]$Stages = "generate,validate,export,render,package",
    [string]$BuildDir,
    [string]$DistDir,
    [switch]$Fix
)
$ErrorActionPreference = "Stop"
. "$PSScriptRoot/_common.ps1"

$exe = Resolve-Blender $Blender
$cli = Join-Path $RepoRoot "core/cli.py"
if (-not $BuildDir) { $BuildDir = Join-Path $RepoRoot "build" }
if (-not $DistDir) { $DistDir = Join-Path $RepoRoot "dist" }
$results = @()
foreach ($prof in (Expand-Profiles $Profiles)) {
    Write-Host "=== $Kit / $prof" -ForegroundColor Cyan
    $blArgs = @("--python", $cli, "--", "run", "--kit", $Kit, "--profile", $prof, "--stages", $Stages,
        "--build-dir", $BuildDir, "--dist-dir", $DistDir)
    if ($Seed -ge 0) { $blArgs += @("--seed", "$Seed") }
    if ($Fix) { $blArgs += "--fix" }
    foreach ($path in (Split-List $GeneratorPath)) { $blArgs += @("--generator-path", $path) }
    $code = Invoke-Blender $exe $blArgs
    $status = switch ($code) { 0 { "ok" } 1 { "FAILED" } 3 { "stub (nothing exported)" } default { "ERROR ($code)" } }
    $summaryPath = Join-Path $BuildDir "$Kit/$prof/reports/summary.json"
    $pass = $fail = ""
    if (Test-Path $summaryPath) {
        $summary = Get-Content $summaryPath -Raw | ConvertFrom-Json
        $pass = [int]($summary.checks.PSObject.Properties.Value | Measure-Object -Property pass -Sum).Sum
        $fail = [int]($summary.checks.PSObject.Properties.Value | Measure-Object -Property fail -Sum).Sum
    }
    $results += [pscustomobject]@{ Profile = $prof; Status = $status; ChecksPassed = $pass; ChecksFailed = $fail; ExitCode = $code }
}
Write-Host ""
$results | Format-Table -AutoSize | Out-String | Write-Host
$bad = $results | Where-Object { $_.ExitCode -ne 0 -and $_.ExitCode -ne 3 }
if ($bad) { exit 1 }
exit 0
