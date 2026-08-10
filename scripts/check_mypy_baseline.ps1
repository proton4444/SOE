param(
    [int]$Baseline = 589
)

$output = @(mypy spoils_engine webapp cli.py --no-incremental 2>&1)
$summary = $output | Select-String -Pattern 'Found ([0-9]+) errors?'
if (-not $summary) {
    $summary = $output | Select-String -Pattern 'Success: no issues found'
}

if ($summary -and $summary.Line -match 'Found ([0-9]+) errors?') {
    $actual = [int]$Matches[1]
} elseif ($summary) {
    $actual = 0
} else {
    $output | Select-Object -Last 30
    throw 'Could not determine the mypy error count.'
}

Write-Host "mypy errors: $actual (baseline: $Baseline)"
if ($actual -gt $Baseline) {
    throw "mypy debt increased by $($actual - $Baseline) error(s)."
}
if ($actual -lt $Baseline) {
    Write-Host 'mypy debt decreased; review the changed baseline before updating it.'
}
