# SPDX-License-Identifier: GPL-3.0-or-later
<#
.SYNOPSIS
Generate and validate a kit without exporting. Reports go to build/<kit>/<profile>/reports.

.EXAMPLE
pwsh scripts/validate.ps1 -Kit stone-dungeon-wall-sampler -Profiles working
#>
param(
    [Parameter(Mandatory = $true)][string]$Kit,
    [string[]]$Profiles = @("working"),
    [int]$Seed = -1,
    [string]$Blender,
    [string[]]$GeneratorPath = @(),
    [switch]$Fix
)
$ErrorActionPreference = "Stop"
& "$PSScriptRoot/build-kit.ps1" -Kit $Kit -Profiles $Profiles -Seed $Seed -Blender $Blender `
    -GeneratorPath $GeneratorPath -Stages "generate,validate" -Fix:$Fix
exit $LASTEXITCODE
