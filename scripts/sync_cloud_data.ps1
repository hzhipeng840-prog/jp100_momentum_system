param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$tempRoot = Join-Path $root ".test-tmp"
$temp = Join-Path $tempRoot ("cloud-sync-" + [guid]::NewGuid().ToString("N"))
$archive = Join-Path $temp "data.tar"
$extract = Join-Path $temp "extract"

try {
    New-Item -ItemType Directory -Force -Path $extract | Out-Null

    & git -C $root fetch origin data:refs/remotes/origin/data
    if ($LASTEXITCODE -ne 0) {
        throw "Could not fetch the origin/data branch."
    }

    & git -C $root archive --format=tar --output=$archive origin/data -- data
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create an archive from origin/data."
    }

    & tar -xf $archive -C $extract
    if ($LASTEXITCODE -ne 0) {
        throw "Could not extract the cloud data archive."
    }

    $cloudMetadataPath = Join-Path $extract "data\processed\metadata.json"
    if (-not (Test-Path -LiteralPath $cloudMetadataPath)) {
        throw "The cloud data branch does not contain metadata.json."
    }
    $cloudMetadata = Get-Content -Raw -Encoding UTF8 $cloudMetadataPath |
        ConvertFrom-Json

    $localMetadataPath = Join-Path $root "data\processed\metadata.json"
    if ((Test-Path -LiteralPath $localMetadataPath) -and (-not $Force)) {
        $localMetadata = Get-Content -Raw -Encoding UTF8 $localMetadataPath |
            ConvertFrom-Json
        if ([string]$localMetadata.trade_date -gt [string]$cloudMetadata.trade_date) {
            throw "Local data is newer. Use -Force only after checking the dates."
        }
    }

    foreach ($name in @("history", "processed", "snapshots")) {
        $source = Join-Path $extract ("data\" + $name)
        if (-not (Test-Path -LiteralPath $source)) {
            continue
        }
        $target = Join-Path $root ("data\" + $name)
        New-Item -ItemType Directory -Force -Path $target | Out-Null
        Get-ChildItem -LiteralPath $source -Force |
            Copy-Item -Destination $target -Recurse -Force
    }

    Write-Output (
        "Cloud data synced. Trade date: " + [string]$cloudMetadata.trade_date +
        " / Version: " + [string]$cloudMetadata.app_version
    )
}
finally {
    $resolvedRoot = [IO.Path]::GetFullPath($root)
    $resolvedTemp = [IO.Path]::GetFullPath($temp)
    $prefix = $resolvedRoot.TrimEnd("\") + "\"
    if ($resolvedTemp.StartsWith(
        $prefix,
        [StringComparison]::OrdinalIgnoreCase
    ) -and (Test-Path -LiteralPath $resolvedTemp)) {
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
    }
}
