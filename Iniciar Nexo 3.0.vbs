' J.A.R.V.I.S Beta — Lanzador
Option Explicit
Dim ws, fso, d, py, main_py, cmd
Set ws  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
d = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
py = d & ".venv\Scripts\pythonw.exe"
If Not fso.FileExists(py) Then
    py = d & ".venv\Scripts\python.exe"
End If
If Not fso.FileExists(py) Then
    MsgBox "NEXO Beta: no se encontro el entorno virtual." & vbCrLf & _
           "Ejecuta NEXO_Beta_Installer.exe primero.", 16, "J.A.R.V.I.S Beta"
    WScript.Quit 1
End If
main_py = d & "main.py"
If Not fso.FileExists(main_py) Then
    MsgBox "NEXO Beta: no se encontro main.py en:" & vbCrLf & d & vbCrLf & _
           "Vuelve a ejecutar NEXO_Beta_Installer.exe.", 16, "J.A.R.V.I.S Beta"
    WScript.Quit 1
End If
cmd = Chr(34) & py & Chr(34) & " " & Chr(34) & main_py & Chr(34)
ws.Run cmd, 0, False
Set ws  = Nothing
Set fso = Nothing
