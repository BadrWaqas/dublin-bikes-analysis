# Invoked by the "DublinBikesCollector" Windows Task Scheduler task every
# few minutes. Kept as its own tiny script (rather than pointing the task
# straight at python.exe) for two reasons:
# 1. Task Scheduler has no console attached, so collect_data.py's print()
#    output would otherwise vanish into nothing. This wrapper redirects it
#    to a log file, which is the only way to notice the collector broke
#    (e.g. network blip, API schema change) without checking in every day.
# 2. One file to point Task Scheduler at means the python path and log
#    path only need to be correct in one place.

$ErrorActionPreference = "Stop"

$scriptsDir = $PSScriptRoot
$projectRoot = Split-Path -Parent $scriptsDir
$python = "C:\Users\Badrw\AppData\Local\Python\pythoncore-3.14-64\python.exe"
$logFile = Join-Path $projectRoot "data\raw\collector.log"

New-Item -ItemType Directory -Force -Path (Split-Path $logFile) | Out-Null

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$timestamp] --- run start ---" | Out-File -FilePath $logFile -Append -Encoding utf8

# Piping python.exe's output through PowerShell's own *>> redirection re-encodes
# it as UTF-16 and garbles it (every character gets padded with a null byte).
# Shelling out to cmd.exe for the redirection instead keeps it as raw bytes,
# so the UTF-8 text collect_data.py prints comes through unmangled.
$collectScript = Join-Path $scriptsDir "collect_data.py"
cmd.exe /c "`"$python`" `"$collectScript`" >> `"$logFile`" 2>&1"
