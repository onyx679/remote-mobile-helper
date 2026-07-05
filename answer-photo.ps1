param(
    [Parameter(Mandatory = $true)]
    [string]$PhotoPath,

    [string]$Crop = "0.30,0.42,0.75,0.60",

    [switch]$CopyAnswer
)

$ErrorActionPreference = "Stop"

$result = & python .\ocr_answer_photo.py $PhotoPath --crop $Crop --json-out .\latest-result.json --txt-out .\latest-answer.txt --save-crop .\latest-crop.png

if ($CopyAnswer) {
    $answer = Get-Content -Raw -LiteralPath .\latest-answer.txt
    Set-Clipboard -Value $answer.Trim()
}

Write-Output $result
