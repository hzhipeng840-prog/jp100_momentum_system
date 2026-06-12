param(
    [string]$Summary = "Describe this version before publishing."
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$versionPath = Join-Path $root "VERSION"
$changeLogPath = Join-Path $root "CHANGELOG.md"
$versionDir = Join-Path $root "docs\versions"

if (-not (Test-Path -LiteralPath $versionPath)) {
    throw "VERSION file was not found."
}

$current = (Get-Content -Raw -LiteralPath $versionPath).Trim()
if ($current -notmatch '^v([0-9]+)$') {
    throw "VERSION must use the vN format."
}

$nextNumber = [int]$Matches[1] + 1
$next = "v$nextNumber"
$detailPath = Join-Path $versionDir "$next.md"

if (Test-Path -LiteralPath $detailPath) {
    throw "$detailPath already exists."
}

New-Item -ItemType Directory -Force -Path $versionDir | Out-Null
Set-Content -LiteralPath $versionPath -Value $next -Encoding UTF8

$today = Get-Date -Format "yyyy-MM-dd"
$detail = @"
# $next

Created: $today

## Purpose

$Summary

## Changes

- TODO

## Compatibility

- TODO

## Validation

- TODO

## Known limitations

- TODO
"@
Set-Content -LiteralPath $detailPath -Value $detail -Encoding UTF8

$changeLog = Get-Content -Raw -LiteralPath $changeLogPath
$heading = "# 変更履歴"
$entry = @"

## [$next] - $today

### 変更予定

- $Summary

"@
if ($changeLog.StartsWith($heading)) {
    $changeLog = $heading + $entry + $changeLog.Substring($heading.Length)
} else {
    $changeLog = $heading + $entry + "`r`n" + $changeLog
}
Set-Content -LiteralPath $changeLogPath -Value $changeLog -Encoding UTF8

Write-Host "Created $next"
Write-Host "Update CHANGELOG.md and docs/versions/$next.md before publishing."
