$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$RequirementsPath = Join-Path $ProjectRoot "requirements.txt"

$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
chcp 65001 | Out-Null

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PIP_PROGRESS_BAR = "off"

Write-Host "Using current python from PATH:"
python --version

Write-Host "Installing project dependencies into the current Python environment..."
python -m pip install --disable-pip-version-check --no-color --progress-bar off -r $RequirementsPath

Write-Host ""
Write-Host "Done. You can now run:"
Write-Host "  python scripts\embed_chunks.py"
Write-Host "  python scripts\test_embedding_search.py"
Write-Host "  python scripts\upload_vectors_to_supabase.py"
Write-Host "  python scripts\test_supabase_vector_search.py"
