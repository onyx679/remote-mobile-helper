param(
    [Parameter(Mandatory = $true)]
    [string]$PhotoPath
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $PhotoPath)) {
    throw "Photo not found: $PhotoPath"
}

$outbox = Join-Path (Get-Location) "ai-outbox"
New-Item -ItemType Directory -Force -Path $outbox | Out-Null

$resolvedPhoto = (Resolve-Path -LiteralPath $PhotoPath).Path
$destination = Join-Path $outbox (Split-Path -Leaf $resolvedPhoto)
Copy-Item -LiteralPath $resolvedPhoto -Destination $destination -Force

$record = [ordered]@{
    queuedAt = (Get-Date).ToString("o")
    source = $resolvedPhoto
    outbox = (Resolve-Path -LiteralPath $destination).Path
    status = "queued-not-sent"
}

$record | ConvertTo-Json -Compress | Add-Content -Path (Join-Path $outbox "queue.jsonl")
Write-Host "Queued for AI review: $destination"
