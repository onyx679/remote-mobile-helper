param(
    [string]$Serial = "adb-2252475e-baGT88._adb-tls-connect._tcp",
    [string]$Crop = "0.0,0.0,1.0,1.0",
    [string]$ScreenRegion = "desktop",
    [double]$PollSeconds = 0.15,
    [switch]$CopyAnswer
)

$ErrorActionPreference = "Stop"

$argsList = @(
    ".\watch_phone_answer_fast.py",
    "--mode", "preview",
    "--serial", $Serial,
    "--crop", $Crop,
    "--poll", "$PollSeconds",
    "--simple-output"
)

if (-not [string]::IsNullOrWhiteSpace($ScreenRegion)) {
    $argsList += @("--screen-region", $ScreenRegion)
}

if ($CopyAnswer) {
    $argsList += "--copy-answer"
}

python @argsList
