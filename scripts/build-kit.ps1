# SPDX-License-Identifier: GPL-3.0-or-later
#Requires -Version 7
<#
.SYNOPSIS
Generate, validate, export, render previews and package a kit.

CLI exit codes per profile: 0 ok, 1 failed, 2 usage/contract error,
3 stub profile (nothing exported), 4 profile unavailable (for example the
Sollumz add-on is missing). 3 is reported but not counted as a failure;
4 and every other non-zero code fail the script.

.PARAMETER Strict
Also fail on exit 3 for profiles whose profile.toml says status = "working",
so a working profile that silently regresses to a stub cannot pass. CI uses it.

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
    [switch]$Fix,
    [switch]$Strict
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
    # Remove the previous run's summary first, so a run that stops before
    # validation never reports stale pass/fail counts.
    $summaryPath = Join-Path $BuildDir "$Kit/$prof/reports/summary.json"
    if (Test-Path -LiteralPath $summaryPath) { Remove-Item -LiteralPath $summaryPath -Force }
    $code = Invoke-Blender $exe $blArgs
    $profStatus = Get-ProfileStatus $prof
    $status = switch ($code) {
        0 { "ok" }
        1 { "FAILED" }
        3 { "stub (nothing exported)" }
        4 { "unavailable (nothing exported)" }
        default { "ERROR ($code)" }
    }
    # Exit 3 (stub) is informational unless -Strict is set and the profile
    # claims status "working"; every other non-zero code is a failure.
    $failed = $code -ne 0 -and ($code -ne 3 -or ($Strict -and $profStatus -eq "working"))
    $pass = $fail = ""
    if (($code -in @(0, 1)) -and (Test-Path -LiteralPath $summaryPath)) {
        $summary = Get-Content $summaryPath -Raw | ConvertFrom-Json
        $pass = [int]($summary.checks.PSObject.Properties.Value | Measure-Object -Property pass -Sum).Sum
        $fail = [int]($summary.checks.PSObject.Properties.Value | Measure-Object -Property fail -Sum).Sum
    }
    $results += [pscustomobject]@{ Profile = $prof; ProfileStatus = $profStatus; Status = $status
        ChecksPassed = $pass; ChecksFailed = $fail; ExitCode = $code; Failed = $failed }
}
Write-Host ""
$results | Format-Table -AutoSize | Out-String | Write-Host
if ($results | Where-Object Failed) { exit 1 }
exit 0
