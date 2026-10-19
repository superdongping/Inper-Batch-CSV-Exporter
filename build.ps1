$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
$taskIcon = Join-Path $PSScriptRoot 'assets/inper-exporter.ico'
$taskVersion = Join-Path $PSScriptRoot 'windows_version_info.txt'
$taskEntry = Join-Path $PSScriptRoot 'inper_exporter_gui.py'
python -m PyInstaller --noconfirm --clean --onefile --windowed --name 'Inper Batch CSV Exporter' --icon $taskIcon --version-file $taskVersion --add-data ($taskIcon + ';assets') --distpath $PSScriptRoot --workpath '_build/work' --specpath '_build' $taskEntry
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
