<#
.SYNOPSIS
    Start a local TLS terminator in front of the loopback application worker.

.DESCRIPTION
    Generates a local CA and a leaf certificate for 127.0.0.2 (and soe.local),
    trusts the CA in the current-user Root store, and starts scripts/https_proxy.py
    on 127.0.0.2:8443 forwarding to 127.0.0.1:8000.

    The application stays on 127.0.0.1. Connecting to 127.0.0.2:8000 must fail
    so check_https.ps1 can prove the app port is not on the public hostname.

.EXAMPLE
    .\scripts\start_https.ps1
    .\scripts\check_https.ps1 -BetaHostname 127.0.0.2 -HttpsPort 8443
#>
param(
    [string]$ListenAddress = '127.0.0.2',
    [int]$HttpsPort = 8443,
    [int]$AppPort = 8000,
    [string]$CertDir = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$dataDir = if ($env:SOE_DATA_DIR) { $env:SOE_DATA_DIR } else { Join-Path $root 'server_data' }
if (-not $CertDir) { $CertDir = Join-Path $dataDir 'tls' }
New-Item -ItemType Directory -Force -Path $CertDir | Out-Null

$caKey = Join-Path $CertDir 'ca.key'
$caCrt = Join-Path $CertDir 'ca.crt'
$leafKey = Join-Path $CertDir 'soe.local.key'
$leafCsr = Join-Path $CertDir 'soe.local.csr'
$leafCrt = Join-Path $CertDir 'soe.local.crt'
$extFile = Join-Path $CertDir 'soe.local.ext'

if (-not (Test-Path -LiteralPath $caCrt)) {
    openssl genrsa -out $caKey 2048
    openssl req -x509 -new -nodes -key $caKey -sha256 -days 825 -out $caCrt `
        -subj '/CN=SOE local CA'
}

if (-not (Test-Path -LiteralPath $leafCrt)) {
    @"
basicConstraints=CA:FALSE
subjectAltName=IP:$ListenAddress,DNS:soe.local
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
"@ | Set-Content -LiteralPath $extFile -Encoding ascii
    openssl genrsa -out $leafKey 2048
    openssl req -new -key $leafKey -out $leafCsr -subj "/CN=$ListenAddress"
    openssl x509 -req -in $leafCsr -CA $caCrt -CAkey $caKey -CAcreateserial `
        -out $leafCrt -days 825 -sha256 -extfile $extFile
}

$caCnf = Join-Path $CertDir 'ca.cnf'
$crlFile = Join-Path $CertDir 'ca.crl'
@"
[ ca ]
default_ca = CA_default
[ CA_default ]
dir = .
database = index.txt
crlnumber = crlnumber
default_md = sha256
default_crl_days = 3650
"@ | Set-Content -LiteralPath $caCnf -Encoding ascii
if (-not (Test-Path -LiteralPath (Join-Path $CertDir 'index.txt'))) {
    New-Item -ItemType File -Path (Join-Path $CertDir 'index.txt') | Out-Null
}
if (-not (Test-Path -LiteralPath (Join-Path $CertDir 'crlnumber'))) {
    Set-Content -LiteralPath (Join-Path $CertDir 'crlnumber') -Value "1000`n" -Encoding ascii
}
Push-Location $CertDir
try {
    openssl ca -gencrl -config $caCnf -keyfile $caKey -cert $caCrt -out $crlFile
}
finally {
    Pop-Location
}
certutil -user -addstore CA $crlFile | Out-Null

$trusted = $false
try {
    $store = New-Object System.Security.Cryptography.X509Certificates.X509Store 'Root', 'CurrentUser'
    $store.Open('ReadWrite')
    $ca = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 $caCrt
    $already = $store.Certificates | Where-Object { $_.Thumbprint -eq $ca.Thumbprint }
    if (-not $already) {
        $store.Add($ca)
    }
    $store.Close()
    $trusted = $true
}
catch {
    Write-Host "Could not trust the local CA in the current-user Root store: $($_.Exception.Message)"
    Write-Host 'check_https.ps1 will fail tls-chain-and-hostname until the CA is trusted.'
}

$pidFile = Join-Path $dataDir 'https.pid'
if (Test-Path $pidFile) {
    $oldPid = [int](Get-Content $pidFile -Raw)
    if (Get-Process -Id $oldPid -ErrorAction SilentlyContinue) {
        throw "An HTTPS terminator is already recorded as PID $oldPid."
    }
    Remove-Item -LiteralPath $pidFile -Force
}

$python = (Get-Command python).Source
$stdout = Join-Path $dataDir 'https.stdout.log'
$stderr = Join-Path $dataDir 'https.stderr.log'
$arguments = @(
    (Join-Path $root 'scripts\https_proxy.py'),
    '--cert', $leafCrt,
    '--key', $leafKey,
    '--listen-host', $ListenAddress,
    '--listen-port', "$HttpsPort",
    '--upstream-host', '127.0.0.1',
    '--upstream-port', "$AppPort"
)
$process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $root `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
$process.Id | Set-Content -LiteralPath $pidFile -NoNewline

Write-Host "Started HTTPS terminator PID $($process.Id) on ${ListenAddress}:$HttpsPort -> 127.0.0.1:$AppPort."
if ($trusted) {
    Write-Host "CA trusted in CurrentUser Root. Verify with:"
} else {
    Write-Host "CA was not trusted. Verify will fail until it is. After trusting, run:"
}
Write-Host "  .\scripts\check_https.ps1 -BetaHostname $ListenAddress -HttpsPort $HttpsPort -AppPort $AppPort"
