Set-Location $PSScriptRoot
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --clean ollama_code.spec
Write-Host "Built dist\ollama_code.exe"
