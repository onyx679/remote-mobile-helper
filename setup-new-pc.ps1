Write-Host "=== Remote phone helper environment check ==="

function Test-CommandInstalled {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

$issues = @()

if (Test-CommandInstalled -Name python) {
    Write-Host "[OK] python found: $(python --version)"
} else {
    $issues += "Python not found. Install Python 3.10+."
}

if (Test-CommandInstalled -Name adb) {
    Write-Host "[OK] adb found: $((& adb version).Split(\"`n\")[0])"
} else {
    $issues += "adb not found. Install scrcpy or Android platform-tools."
}

if (Test-CommandInstalled -Name scrcpy) {
    Write-Host "[OK] scrcpy found: $((& scrcpy --version).Split(\"`n\")[0])"
} else {
    $issues += "scrcpy not found."
}

$tesseractPaths = @(
    "C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
    "C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe"
)
$tesseractPath = $tesseractPaths | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($tesseractPath) {
    Write-Host "[OK] tesseract found: $tesseractPath"
    Write-Host "      $(& $tesseractPath --version | Select-Object -First 1)"
} else {
    $issues += "Tesseract OCR not found at default paths."
}

if (Test-Path "requirements.txt") {
    Write-Host "[OK] requirements.txt present."
} else {
    $issues += "requirements.txt missing."
}

if ($issues.Count -eq 0) {
    Write-Host "Environment looks ready."
    Write-Host "Run: python -m pip install -r requirements.txt"
} else {
    Write-Host "Missing components:"
    $issues | ForEach-Object { Write-Host " - $_" }
}
