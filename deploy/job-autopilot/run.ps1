# run.ps1 — Daily JobAutopilot wrapper (Task Scheduler -> headless claude --chrome -p).
# Same pattern as me\morning-brief\brief.ps1; one attempt, honest exit code, logs kept.
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

if ($PSScriptRoot) { $root = $PSScriptRoot }
else { $root = Split-Path -Parent $MyInvocation.MyCommand.Path }

Set-Location $root
$logDir = Join-Path $root 'logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

$outFile = Join-Path $logDir 'last-output.txt'
$errFile = Join-Path $logDir 'last-stderr.txt'

$claude = (Get-Command claude -ErrorAction Stop).Source
$promptText = Get-Content (Join-Path $root 'prompt.md') -Raw

$null | & $claude --chrome --model opus -p $promptText 1> $outFile 2> $errFile
$code = $LASTEXITCODE

Add-Content -Path (Join-Path $logDir 'history.log') -Value ("{0} exit={1}" -f (Get-Date -Format 's'), $code)
exit $code
