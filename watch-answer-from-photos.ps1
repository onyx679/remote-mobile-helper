param(
    [string]$PhotoDir = ".\camera-inbox",
    [string]$Crop = "0.30,0.42,0.75,0.60",
    [double]$PollSeconds = 0.2,
    [switch]$CopyAnswer,
    [string]$LogFile = ".\watch-answer.log"
)

$ErrorActionPreference = "Stop"

$resolvedPhotoDir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($PhotoDir)
New-Item -ItemType Directory -Force -Path $resolvedPhotoDir | Out-Null

function Get-PhotoFiles {
    param(
        [string]$Directory
    )

    Get-ChildItem -LiteralPath $Directory -File |
        Where-Object { $_.Extension.ToLowerInvariant() -in @(".jpg", ".jpeg", ".png") }
}

$seen = @{}
Get-PhotoFiles -Directory $resolvedPhotoDir |
    ForEach-Object { $seen[$_.FullName] = $true }

Write-Host "Watching photos in $resolvedPhotoDir"
Write-Host "Crop: $Crop"
Write-Host "Results: latest-result.json and latest-answer.txt"
Write-Host "Press Ctrl+C to stop."
Add-Content -LiteralPath $LogFile -Value "[$(Get-Date -Format o)] watcher started: $resolvedPhotoDir"

while ($true) {
    $files = Get-PhotoFiles -Directory $resolvedPhotoDir |
        Sort-Object LastWriteTime

    foreach ($file in $files) {
        if ($seen.ContainsKey($file.FullName)) {
            continue
        }

        Start-Sleep -Milliseconds 100
        $before = $file.Length
        $after = (Get-Item -LiteralPath $file.FullName).Length
        if ($before -ne $after) {
            continue
        }

        $seen[$file.FullName] = $true
        Write-Host "Answering $($file.Name)"
        Add-Content -LiteralPath $LogFile -Value "[$(Get-Date -Format o)] answering $($file.FullName)"

        $argsList = @(".\answer-photo.ps1", "-PhotoPath", $file.FullName, "-Crop", $Crop)
        if ($CopyAnswer) {
            $argsList += "-CopyAnswer"
        }

        & powershell -NoProfile -ExecutionPolicy Bypass -File @argsList 2>&1 |
            Tee-Object -FilePath $LogFile -Append |
            Out-Host
    }

    Start-Sleep -Milliseconds ([int]($PollSeconds * 1000))
}
