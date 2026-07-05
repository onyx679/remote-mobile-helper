param(
    [string]$AnswerFile = ".\latest-answer.txt",
    [int]$PollMilliseconds = 100
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = "Latest Answer"
$form.Width = 420
$form.Height = 260
$form.TopMost = $true
$form.StartPosition = "CenterScreen"

$label = New-Object System.Windows.Forms.Label
$label.Dock = "Fill"
$label.TextAlign = "MiddleCenter"
$label.Font = New-Object System.Drawing.Font("Arial", 72, [System.Drawing.FontStyle]::Bold)
$label.Text = "WAIT"
$label.BackColor = [System.Drawing.Color]::FromArgb(17, 24, 39)
$label.ForeColor = [System.Drawing.Color]::White
$form.Controls.Add($label)

$last = ""
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = $PollMilliseconds
$timer.Add_Tick({
    if (-not (Test-Path -LiteralPath $AnswerFile)) {
        return
    }

    $current = (Get-Content -Raw -LiteralPath $AnswerFile).Trim().ToUpperInvariant()
    if ($current -eq "" -or $current -eq $last) {
        return
    }

    $script:last = $current
    $label.Text = $current
    if ($current -eq "YES") {
        $label.BackColor = [System.Drawing.Color]::FromArgb(6, 95, 70)
    } elseif ($current -eq "NO") {
        $label.BackColor = [System.Drawing.Color]::FromArgb(153, 27, 27)
    } else {
        $label.BackColor = [System.Drawing.Color]::FromArgb(17, 24, 39)
    }
})

$timer.Start()
[void]$form.ShowDialog()
