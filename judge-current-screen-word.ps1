param(
    [string]$Serial = "adb-2252475e-baGT88._adb-tls-connect._tcp",
    [double]$Threshold = 1.35,
    [switch]$CopyAnswer,
    [switch]$ShowDebug
)

$ErrorActionPreference = "Stop"

function Find-Adb {
    $cmd = Get-Command adb -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $wingetRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    $adb = Get-ChildItem -Path $wingetRoot -Recurse -Filter adb.exe -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -like "*Genymobile.scrcpy*" } |
        Select-Object -First 1 -ExpandProperty FullName

    if (-not $adb) {
        throw "adb.exe not found. Install scrcpy first: winget install --id Genymobile.scrcpy --exact"
    }

    return $adb
}

function Get-CandidateWord {
    param(
        [string]$XmlText
    )

    $matches = [regex]::Matches($XmlText, 'text="([^"]+)"')
    $candidates = foreach ($match in $matches) {
        $decoded = [System.Net.WebUtility]::HtmlDecode($match.Groups[1].Value)
        foreach ($token in [regex]::Matches($decoded, "[A-Za-z][A-Za-z'-]*")) {
            $word = $token.Value.Trim("'")
            if ($word.Length -ge 2 -and $word.Length -le 24) {
                $word
            }
        }
    }

    $stop = @(
        "the", "and", "or", "of", "to", "in", "is", "are", "this", "that",
        "select", "word", "english", "continue", "next", "yes", "no"
    )

    $candidates |
        Where-Object { $stop -notcontains $_.ToLowerInvariant() } |
        Sort-Object { $_.Length } -Descending |
        Select-Object -First 1
}

$started = Get-Date
$adb = Find-Adb
$remoteXml = "/sdcard/window_dump.xml"
$localXml = Join-Path $env:TEMP "window_dump_$PID.xml"

& $adb -s $Serial shell uiautomator dump $remoteXml | Out-Null
& $adb -s $Serial pull $remoteXml $localXml | Out-Null

$xmlText = Get-Content -Raw -LiteralPath $localXml
$word = Get-CandidateWord -XmlText $xmlText

if (-not $word) {
    throw "No candidate English word found in current screen accessibility text."
}

$judgeArgs = @(".\judge_english_word.py", $word, "--threshold", "$Threshold")
if ($ShowDebug) {
    $judgeArgs += "--debug"
}

$answer = (& python @judgeArgs).Trim()
if ($CopyAnswer) {
    Set-Clipboard -Value $answer
}

if ($ShowDebug) {
    $elapsed = [int]((Get-Date) - $started).TotalMilliseconds
    Write-Output "$answer`tcandidate=$word`ttotal_ms=$elapsed"
} else {
    Write-Output $answer
}
