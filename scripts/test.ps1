# SPDX-License-Identifier: GPL-3.0-or-later
#Requires -Version 7
<#
.SYNOPSIS
Run the test suite inside headless Blender, then the repository brand scan.

.PARAMETER Quick
Skip the slow tests (determinism and Godot import launch extra processes).

.PARAMETER Godot
Path to a Godot 4 executable; enables the Godot import test (or set GARU_GODOT).
#>
param(
    [string]$Blender,
    [string]$Godot,
    [switch]$Quick,
    [string]$Pattern = "test_*.py"
)
$ErrorActionPreference = "Stop"
. "$PSScriptRoot/_common.ps1"

$exe = Resolve-Blender $Blender
if ($Godot) { $env:GARU_GODOT = (Resolve-Path $Godot).Path }
$blArgs = @("--python", (Join-Path $RepoRoot "tests/run_tests.py"), "--", "--pattern", $Pattern)
if ($Quick) { $blArgs += "--skip-slow" }
$testCode = Invoke-Blender $exe $blArgs

$scanCode = Invoke-Blender $exe @("--python", (Join-Path $RepoRoot "core/cli.py"), "--", "brandscan",
    (Join-Path $RepoRoot "kits"), (Join-Path $RepoRoot "profiles"), (Join-Path $RepoRoot "docs"),
    (Join-Path $RepoRoot "README.md"))

Write-Host "tests exit=$testCode brandscan exit=$scanCode"
if ($testCode -ne 0 -or $scanCode -ne 0) { exit 1 }
exit 0
