# uv 0.12.21'i tools\uv\ klasorune indirir (SHA-256 dogrulamali). Yalnizca ASCII.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
# Konsol dili baslat.cmd'den gelir (tr ya da en); yoksa Ingilizce.
$Tr = ($env:AUTOCRIPT_KONSOL_DIL -eq 'tr')
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$Url = 'https://github.com/astral-sh/uv/releases/download/0.12.21/uv-x86_64-pc-windows-msvc.zip'
$Sha256 = '5d223efa0bf00208c3853246af09420419dfbd352536aa6bb8163d6170e23890'

$Root = Split-Path -Parent $PSScriptRoot
$Tools = Join-Path $Root 'tools'
$Dest = Join-Path $Tools 'uv'
$Zip = Join-Path $Tools 'uv-indirme.zip'
$Tmp = Join-Path $Tools 'uv-tmp'

try {
    New-Item -ItemType Directory -Force -Path $Tools | Out-Null
    Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Zip
    $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Zip).Hash.ToLowerInvariant()
    if ($Hash -ne $Sha256) {
        if ($Tr) { throw 'uv dosyasinin SHA-256 degeri eslesmiyor.' } else { throw 'The SHA-256 of the uv file does not match.' }
    }
    if (Test-Path -LiteralPath $Tmp) { Remove-Item -LiteralPath $Tmp -Recurse -Force }
    Expand-Archive -LiteralPath $Zip -DestinationPath $Tmp -Force
    if (-not (Test-Path -LiteralPath (Join-Path $Tmp 'uv.exe'))) {
        if ($Tr) { throw 'uv.exe arsivde bulunamadi.' } else { throw 'uv.exe was not found in the archive.' }
    }
    if (Test-Path -LiteralPath $Dest) { Remove-Item -LiteralPath $Dest -Recurse -Force }
    Move-Item -LiteralPath $Tmp -Destination $Dest
}
catch {
    if ($Tr) { $Onek = 'uv indirilemedi: ' } else { $Onek = 'Could not download uv: ' }
    Write-Host ($Onek + $_.Exception.Message)
    exit 1
}
finally {
    if (Test-Path -LiteralPath $Zip) { Remove-Item -LiteralPath $Zip -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $Tmp) { Remove-Item -LiteralPath $Tmp -Recurse -Force -ErrorAction SilentlyContinue }
}
exit 0
