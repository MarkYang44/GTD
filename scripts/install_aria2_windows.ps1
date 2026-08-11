param(
    [string]$Version = "1.37.0"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$destination = Join-Path $projectRoot "tools\aria2"
$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) (
    "mvd-aria2-" + [Guid]::NewGuid().ToString("N")
)
$archive = Join-Path $temporaryRoot "aria2.zip"
$expanded = Join-Path $temporaryRoot "expanded"
$assetName = "aria2-$Version-win-64bit-build1.zip"
$downloadUrl = (
    "https://github.com/aria2/aria2/releases/download/" +
    "release-$Version/$assetName"
)

try {
    New-Item -ItemType Directory -Path $temporaryRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $expanded -Force | Out-Null
    $aria2 = $null
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "Installing official aria2 $Version through winget..."
        & $winget.Source install --id aria2.aria2 --exact --source winget `
            --scope user --silent --accept-package-agreements `
            --accept-source-agreements --disable-interactivity | Out-Host
        $packages = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
        $aria2 = Get-ChildItem -LiteralPath $packages -Depth 6 -File `
            -Filter "aria2c.exe" -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -like "*aria2.aria2_*" } |
            Sort-Object FullName -Descending |
            Select-Object -First 1
    }

    if (-not $aria2) {
        Write-Host "Downloading official aria2 $Version release archive..."
        $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
        if ($curl) {
            & $curl.Source -L --fail --retry 3 --retry-all-errors `
                --silent --show-error -o $archive $downloadUrl
            if ($LASTEXITCODE -ne 0) {
                throw "curl.exe failed with exit code $LASTEXITCODE"
            }
        } else {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -UseBasicParsing -Uri $downloadUrl -OutFile $archive
        }
        Expand-Archive -LiteralPath $archive -DestinationPath $expanded -Force
        $aria2 = Get-ChildItem -LiteralPath $expanded -Recurse -File `
            -Filter "aria2c.exe" | Select-Object -First 1
        if (-not $aria2) {
            throw "The downloaded archive does not contain aria2c.exe"
        }
    }

    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    Copy-Item -Path (Join-Path $aria2.Directory.FullName "*") `
        -Destination $destination -Recurse -Force
    $installed = Join-Path $destination "aria2c.exe"
    $versionOutput = & $installed --version | Select-Object -First 1
    if ($LASTEXITCODE -ne 0 -or $versionOutput -notmatch [regex]::Escape($Version)) {
        throw "aria2c verification failed: $versionOutput"
    }
    Write-Host "Installed and verified: $installed"
    Write-Host $versionOutput
} finally {
    $resolvedTemp = [IO.Path]::GetFullPath($temporaryRoot)
    $systemTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if ($resolvedTemp.StartsWith($systemTemp, [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force -ErrorAction SilentlyContinue
    }
}
