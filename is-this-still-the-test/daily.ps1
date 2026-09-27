# Daily Kaggle runs for "Is This Still the Test?".  Run from this folder in PowerShell:
#
#   .\daily.ps1 pilot         round-2 pilot on the main 10 models            (~$3)
#   .\daily.ps1 grid          one more repeat of the 96-question grid          (~$3)
#   .\daily.ps1 generations   older model versions for the "newer isn't better" chart
#   .\daily.ps1 status        what has run so far (no cost)
#
# Check your remaining Kaggle model quota first: if it's empty every call fails with
# "max estimated cost ... exceeds your available quota". After a run finishes, tell Claude
# "done": it downloads the results and runs tools/refresh_all.py, which rebuilds every chart,
# the post and the paper from all complete runs.

param([string]$what = "status")
$env:PYTHONUTF8 = "1"

$main = @("gpt-5.5-2026-04-23", "claude-sonnet-5-default", "gemini-3.8-flash", "gemini-3.7-flash",
          "gpt-6-astra", "gpt-5.6-terra", "claude-haiku-4-5-20251001", "gemma-4-31b-it",
          "gpt-5.4-mini-2026-03-17", "glm-5")
$older = @("claude-sonnet-4-20250514", "claude-sonnet-4-5-20250929", "claude-sonnet-4-6-default",
           "gpt-5.4-2026-03-05", "gpt-5.4-nano-2026-03-17", "gemini-2.5-flash", "gemini-2.5-pro")

function Run-Models([string]$task, [string[]]$models) {
    $cmd = @("b", "t", "run", $task)
    foreach ($m in $models) { $cmd += @("-m", $m) }
    $cmd += "--wait"
    Write-Host "kaggle $($cmd -join ' ')"
    & kaggle @cmd
}

switch ($what) {
    "pilot"       { Run-Models "itst-round2-pilot" $main }
    "grid"        { Run-Models "reality-threshold-scorecard" $main }
    "generations" { Run-Models "reality-threshold-scorecard" $older }
    "status" {
        foreach ($t in @("itst-round2-pilot", "reality-threshold-scorecard")) {
            Write-Host "`n=== $t ==="
            & kaggle b t status $t
        }
    }
    default { Write-Host "usage: .\daily.ps1 pilot | grid | generations | status" }
}
