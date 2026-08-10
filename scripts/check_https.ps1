<#
.SYNOPSIS
    Verifies external HTTPS termination for the controlled beta.

.DESCRIPTION
    Run this on or from the operator workstation against the real beta hostname
    after the reverse proxy is configured. Certificate validation is strict on
    purpose: no check may be relaxed to make this script pass. A failure here is
    a genuine readiness blocker, not a test artifact.

    The application itself never terminates TLS; it listens on 127.0.0.1 only.

.EXAMPLE
    .\scripts\check_https.ps1 -BetaHostname beta.example.org

.EXAMPLE
    .\scripts\check_https.ps1 -BetaHostname beta.example.org -RoomCode ABCDE -AgentKey $key
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$BetaHostname,
    [int]$HttpsPort = 443,
    [int]$AppPort = 8000,
    [string]$RoomCode = '',
    [string]$AgentKey = ''
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$script:Failures = @()

function Write-Check {
    param([string]$Name, [bool]$Ok, [string]$Detail)
    if ($Ok) {
        Write-Host ("PASS  {0}: {1}" -f $Name, $Detail)
    }
    else {
        Write-Host ("FAIL  {0}: {1}" -f $Name, $Detail)
        $script:Failures += $Name
    }
}

Write-Host "HTTPS verification for $BetaHostname (port $HttpsPort)"
Write-Host ("Run at {0}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'))
Write-Host ''

# 1. DNS resolution.
try {
    $addresses = [Net.Dns]::GetHostAddresses($BetaHostname) | ForEach-Object { $_.IPAddressToString }
    Write-Check 'dns' $true ($addresses -join ', ')
}
catch {
    Write-Check 'dns' $false $_.Exception.Message
    Write-Host ''
    Write-Host 'Cannot continue without DNS resolution.'
    exit 1
}

# 2. TCP reachability on the HTTPS port.
$tcp = New-Object Net.Sockets.TcpClient
try {
    $tcp.Connect($BetaHostname, $HttpsPort)
    Write-Check 'tcp-443' $true "connected to ${BetaHostname}:${HttpsPort}"
}
catch {
    Write-Check 'tcp-443' $false $_.Exception.Message
    $tcp.Dispose()
    Write-Host ''
    Write-Host 'Cannot continue without a TCP connection.'
    exit 1
}

# 3-5. Strict TLS handshake: chain trust, hostname match, and expiry.
#      The callback records detail but still enforces the platform verdict.
$script:PolicyErrors = 'not-evaluated'
$script:PeerCert = $null
$validation = [Net.Security.RemoteCertificateValidationCallback] {
    param($senderObj, $certificate, $chain, $sslPolicyErrors)
    $script:PolicyErrors = $sslPolicyErrors.ToString()
    if ($certificate) {
        $script:PeerCert = New-Object Security.Cryptography.X509Certificates.X509Certificate2 $certificate
    }
    return ($sslPolicyErrors -eq [Net.Security.SslPolicyErrors]::None)
}

$protocols = [Security.Authentication.SslProtocols]::Tls12
if ([enum]::GetNames([Security.Authentication.SslProtocols]) -contains 'Tls13') {
    $protocols = [Security.Authentication.SslProtocols]([int]$protocols -bor [int][Security.Authentication.SslProtocols]::Tls13)
}

$ssl = New-Object Net.Security.SslStream($tcp.GetStream(), $false, $validation)
try {
    $ssl.AuthenticateAsClient($BetaHostname, $null, $protocols, $true)
    Write-Check 'tls-handshake' $true ("{0}, cipher {1}" -f $ssl.SslProtocol, $ssl.CipherAlgorithm)
    Write-Check 'tls-chain-and-hostname' $true "policy errors: $script:PolicyErrors"
}
catch {
    Write-Check 'tls-handshake' $false ("{0} (policy errors: {1})" -f $_.Exception.Message, $script:PolicyErrors)
}

if ($script:PeerCert) {
    $cert = $script:PeerCert
    $daysLeft = [int]([datetime]$cert.NotAfter - (Get-Date)).TotalDays
    Write-Host ("      subject: {0}" -f $cert.Subject)
    Write-Host ("      issuer:  {0}" -f $cert.Issuer)
    $san = $cert.Extensions | Where-Object { $_.Oid.Value -eq '2.5.29.17' }
    if ($san) {
        Write-Host ("      san:     {0}" -f ($san.Format($false)))
    }
    Write-Check 'cert-not-expired' ($daysLeft -gt 0) ("valid {0} to {1}, {2} day(s) remaining" -f $cert.NotBefore, $cert.NotAfter, $daysLeft)
    if ($daysLeft -le 21 -and $daysLeft -gt 0) {
        Write-Host '      NOTE: renewal window is close; confirm certificate automation is running.'
    }
}
else {
    Write-Check 'cert-not-expired' $false 'no peer certificate was captured'
}
$ssl.Dispose()
$tcp.Dispose()

$base = "https://${BetaHostname}"
if ($HttpsPort -ne 443) { $base = "https://${BetaHostname}:${HttpsPort}" }

# 6. Health endpoint over public HTTPS, with normal certificate validation.
try {
    $health = Invoke-RestMethod -Uri "$base/healthz" -TimeoutSec 15
    $healthy = ($health.status -eq 'ok')
    Write-Check 'healthz-https' $healthy ($health | ConvertTo-Json -Compress -Depth 5)
}
catch {
    Write-Check 'healthz-https' $false $_.Exception.Message
}

# 7. Application HTML and static assets through the proxy.
try {
    $rootPage = Invoke-WebRequest -Uri "$base/" -TimeoutSec 15 -UseBasicParsing
    Write-Check 'app-root' ($rootPage.StatusCode -eq 200) ("HTTP {0}, {1} byte(s)" -f $rootPage.StatusCode, $rootPage.RawContentLength)
}
catch {
    Write-Check 'app-root' $false $_.Exception.Message
}

try {
    $asset = Invoke-WebRequest -Uri "$base/static/style.css" -TimeoutSec 15 -UseBasicParsing
    Write-Check 'static-assets' ($asset.StatusCode -eq 200) ("HTTP {0}" -f $asset.StatusCode)
}
catch {
    Write-Check 'static-assets' $false $_.Exception.Message
}

# 8. Room/game API routes through the proxy. Requires an existing room.
if ($RoomCode -and $AgentKey) {
    try {
        $status = Invoke-RestMethod -Uri "$base/api/rooms/$RoomCode/status" -TimeoutSec 15 `
            -Headers @{ 'X-Agent-Key' = $AgentKey }
        Write-Check 'api-room-status' $true ("turn {0}" -f $status.turn)
    }
    catch {
        Write-Check 'api-room-status' $false $_.Exception.Message
    }
}
else {
    Write-Host 'SKIP  api-room-status: pass -RoomCode and -AgentKey to exercise a real room route.'
}

# 9. HTTP port 80 must redirect to HTTPS rather than serve the application.
try {
    $plain = [Net.HttpWebRequest]::Create("http://${BetaHostname}/healthz")
    $plain.AllowAutoRedirect = $false
    $plain.Timeout = 15000
    $plain.Method = 'GET'
    try {
        $resp = $plain.GetResponse()
    }
    catch [Net.WebException] {
        $resp = $_.Exception.Response
        if (-not $resp) { throw }
    }
    $code = [int]$resp.StatusCode
    $location = $resp.Headers['Location']
    $redirects = ($code -ge 300 -and $code -lt 400 -and $location -like 'https://*')
    Write-Check 'http-to-https-redirect' $redirects ("HTTP {0} -> {1}" -f $code, $location)
    if (-not $redirects -and $code -eq 200) {
        Write-Host '      Port 80 served content directly. Plaintext beta traffic is a blocker.'
    }
    $resp.Close()
}
catch {
    Write-Check 'http-to-https-redirect' $true ("port 80 not reachable ({0}); acceptable if only 443 is published" -f $_.Exception.Message)
}

# 10. The application port must not be reachable on the public hostname.
$exposed = New-Object Net.Sockets.TcpClient
try {
    $async = $exposed.BeginConnect($BetaHostname, $AppPort, $null, $null)
    $opened = $async.AsyncWaitHandle.WaitOne(5000, $false) -and $exposed.Connected
    if ($opened) { $exposed.EndConnect($async) }
    Write-Check 'app-port-not-public' (-not $opened) ("{0}:{1} {2}" -f $BetaHostname, $AppPort, $(if ($opened) { 'ACCEPTED a connection' } else { 'refused or filtered' }))
}
catch {
    Write-Check 'app-port-not-public' $true ("{0}:{1} refused or filtered" -f $BetaHostname, $AppPort)
}
finally {
    $exposed.Dispose()
}

# The web client uses HTMX polling over ordinary HTTP requests. There is no
# WebSocket, SSE, or streaming endpoint, so no upgrade path needs verification.
Write-Host 'INFO  websocket/sse: not applicable; the client uses HTMX polling only.'
Write-Host 'INFO  cookies are issued with Secure=1, so the public origin must be HTTPS end to end.'

Write-Host ''
if ($script:Failures.Count -eq 0) {
    Write-Host 'RESULT: all HTTPS termination checks passed.'
    exit 0
}
Write-Host ("RESULT: {0} check(s) failed: {1}" -f $script:Failures.Count, ($script:Failures -join ', '))
exit 1
