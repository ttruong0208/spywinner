# WinnerSpy — cai Flask + chay web (PowerShell)
Set-Location $PSScriptRoot

$venvPy = Join-Path $PSScriptRoot "venv\Scripts\python.exe"

if (-not (Test-Path $venvPy)) {
    if (Test-Path "venv") {
        Write-Host "Xoa venv cu..."
        Remove-Item -Recurse -Force "venv"
    }
    Write-Host "Tao venv..."
    if (Get-Command py -ErrorAction SilentlyContinue) {
        py -3 -m venv venv
    } else {
        python -m venv venv
    }
}

& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -r requirements-web.txt

Write-Host ""
Write-Host "Xong. Chay web:"
Write-Host "  .\venv\Scripts\python.exe web_app.py"
Write-Host "Hoac: .\start_web.bat"
