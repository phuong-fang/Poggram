' Launches Poggram with no console window at all.
'
' Double-click this (or make a shortcut to it) instead of running app.py with
' python.exe. pythonw.exe is the console-less build of the interpreter, so no
' terminal is ever created - which is the only reliable way to not have one.
' The app can't hide a console it already has when Windows Terminal is the
' console host: GetConsoleWindow returns a hidden proxy window there, and the
' visible Terminal window belongs to a shared process that may hold your other
' tabs, so it isn't the app's to touch.
'
' Logs still go to data\poggram.log - Settings > Interface > Open log file.
Dim shell, fso, here
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
' 0 = hidden window, False = don't wait for it to exit.
shell.Run """" & here & "\.venv\Scripts\pythonw.exe"" """ & here & "\app.py""", 0, False
