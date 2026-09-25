# SPDX-License-Identifier: GPL-3.0-or-later
<#
.SYNOPSIS
Run the test suite inside headless Blender, then the repository brand scan.

.PARAMETER Quick
Skip the determinism test (it launches extra Blender processes).
#>
param(
    [string]$Blender,
    [switch]$Quick,
    [string]$Pattern = "test_*.py"
)
$ErrorActionPreference = "Stop"
. "$PSScriptRoot/_common.ps1"

$exe = Resolve-Blender $Blender
$blArgs = @("--python", (Join-Path $RepoRoot "tests/run_tests.py"), "--", "--pattern", $Pattern)
if ($Quick) { $blArgs += "--skip-slow" }
$testCode = Invoke-Blender $exe $blArgs

$scanCode = Invoke-Blender $exe @("--python", (Join-Path $RepoRoot "core/cli.py"), "--", "brandscan",
    (Join-Path $RepoRoot "kits"), (Join-Path $RepoRoot "profiles"), (Join-Path $RepoRoot "docs"),
    (Join-Path $RepoRoot "README.md"))

Write-Host "tests exit=$testCode brandscan exit=$scanCode"
if ($testCode -ne 0 -or $scanCode -ne 0) { exit 1 }
exit 0
