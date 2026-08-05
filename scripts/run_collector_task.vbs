' Task Scheduler is pointed at this file instead of directly at
' run_collector_task.ps1. PowerShell's own -WindowStyle Hidden still flashes
' a console window briefly on some Windows builds; launching it through
' WScript.Shell.Run with windowStyle 0 is the reliable way to get a
' genuinely invisible run every time.
Dim fso, scriptDir, psScript, shell

Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
psScript = scriptDir & "\run_collector_task.ps1"

Set shell = CreateObject("WScript.Shell")
shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & psScript & """", 0, False
