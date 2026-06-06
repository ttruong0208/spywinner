# WinnerSpy Web — chạy trong PowerShell: .\start_web.ps1
Set-Location $PSScriptRoot

$py = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "Chua co venv. Chay lan dau: .\start_web.bat"
    exit 1
}

Write-Host "WinnerSpy Web — http://127.0.0.1:5050"
Write-Host "Dev: .\start_chrome_debug.bat truoc khi quet"
Write-Host "SaaS (VPS): `$env:WINNERSPY_SAAS_MODE='1' truoc khi chay web"
Write-Host "Link nang cap: `$env:WINNERSPY_UPGRADE_URL='https://zalo.me/...'`n"

& $py -m pip install -r requirements-web.txt -q
& $py web_app.py
