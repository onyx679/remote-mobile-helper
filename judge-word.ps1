param(
    [Parameter(Mandatory = $true)]
    [string]$Word,

    [double]$Threshold = 1.35,

    [switch]$CopyAnswer,

    [switch]$ShowDebug
)

$ErrorActionPreference = "Stop"

$argsList = @(".\judge_english_word.py", $Word, "--threshold", "$Threshold")
if ($ShowDebug) {
    $argsList += "--debug"
}

$answer = (& python @argsList).Trim()
if ($CopyAnswer) {
    Set-Clipboard -Value $answer
}

Write-Output $answer
