Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $repoRoot "backend"
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$appPath = Join-Path $backendRoot "src\rag_mcp\observability\dashboard\app.py"

if (-not (Test-Path $pythonExe)) {
    throw "Python virtual environment not found at $pythonExe"
}

Push-Location $backendRoot
try {
    $env:PYTHONPATH = "src"
    & $pythonExe -m streamlit run $appPath
}
finally {
    Pop-Location
}
