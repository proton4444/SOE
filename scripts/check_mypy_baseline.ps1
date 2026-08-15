param(
    # Read from the record rather than repeated here. A default that drifts
    # above the real count is not a loose gate, it is no gate: it was 589
    # while docs/mypy-baseline.txt said 102, which left room for 487 new
    # errors to land without a word.
    [int]$Baseline = -1
)

$root = Split-Path -Parent $PSScriptRoot
$baselineFile = Join-Path $root 'docs/mypy-baseline.txt'

if ($Baseline -lt 0) {
    if (-not (Test-Path -LiteralPath $baselineFile)) {
        throw "Baseline record is missing: $baselineFile"
    }
    $recorded = Select-String -Path $baselineFile -Pattern '^Baseline error count:\s*([0-9]+)' |
        Select-Object -First 1
    if (-not $recorded) {
        throw "Could not read 'Baseline error count:' from $baselineFile"
    }
    $Baseline = [int]$recorded.Matches[0].Groups[1].Value
}

$output = @(mypy soe webapp cli.py --no-incremental 2>&1)
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

# Explicit: mypy exits non-zero whenever it reports an error, and without this
# a passing gate inherits that code and reads as a failure to anything that
# runs the script rather than reading its output.
exit 0
