$ErrorActionPreference = "Stop"

$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

chcp 65001 | Out-Null

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$env:PIP_PROGRESS_BAR = "off"

$PSDefaultParameterValues["Get-Content:Encoding"] = "UTF8"
$PSDefaultParameterValues["Select-String:Encoding"] = "UTF8"

Write-Host "UTF-8 dev shell is ready."
Write-Host "Tip: dot-source this file before working: . .\scripts\dev_utf8.ps1"

