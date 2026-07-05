param(
    [string]$Serial = "adb-2252475e-baGT88._adb-tls-connect._tcp",
    [ValidateSet(0, 90, 180, 270)]
    [int]$RotateDegrees = 0,
    [double]$PollSeconds = 0.3
)

$ErrorActionPreference = "Stop"

& .\sync-camera-photos.ps1 `
    -Serial $Serial `
    -CopyToClipboard `
    -RotateDegrees $RotateDegrees `
    -PollSeconds $PollSeconds
