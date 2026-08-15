<#
.SYNOPSIS
    Point this clone's git hooks at the repository's own githooks/ directory.

.DESCRIPTION
    The pre-commit guard in githooks/ refuses to stage waitlist rows, live
    server data, private keys, or third-party source material. It ships with
    the repository so every clone gets it, but git will not enable a tracked
    hooks directory on its own -- that is what this script is for.

    If core.hooksPath already points somewhere else, this refuses rather than
    silently replacing whatever is installed. Pass -Force to take it over.

.EXAMPLE
    .\scripts\install_hooks.ps1
    .\scripts\install_hooks.ps1 -Force
#>
param(
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$desired = 'githooks'
$current = (git config --get core.hooksPath)

if ($current -and $current -ne $desired -and -not $Force) {
    Write-Host "core.hooksPath is already set to: $current"
    Write-Host "Leaving it alone. Re-run with -Force to point it at $desired,"
    Write-Host "or chain the guard yourself from that directory's pre-commit."
    exit 1
}

git config core.hooksPath $desired
Write-Host "core.hooksPath = $desired"

if ($IsLinux -or $IsMacOS) {
    chmod +x (Join-Path $root 'githooks/pre-commit')
}

Write-Host 'Installed. The guard runs on the next commit.'
