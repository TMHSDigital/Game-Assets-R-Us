# SPDX-License-Identifier: GPL-3.0-or-later
<#
.SYNOPSIS
Delete build/ and dist/ inside this repository (both are gitignored).
#>
$ErrorActionPreference = "Stop"
. "$PSScriptRoot/_common.ps1"
foreach ($name in @("build", "dist")) {
    $path = Join-Path $RepoRoot $name
    if (Test-Path $path) {
        Remove-Item -Recurse -Force -LiteralPath $path
        Write-Host "removed $path"
    }
}
