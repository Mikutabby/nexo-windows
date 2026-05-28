import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
def _err(msg):
    import tkinter as tk; from tkinter import messagebox
    r = tk.Tk(); r.withdraw()
    messagebox.showerror("J.A.R.V.I.S Beta - Error", msg); r.destroy()
def main():
    py = ROOT/".venv"/"Scripts"/"python.exe"
    if not py.exists():
        _err("No se encontro el entorno virtual .venv\n\nEjecuta NEXO_Beta_Installer.exe nuevamente.")
        return
    log = ROOT/"config"/"nexo_launch.log"
    (ROOT/"config").mkdir(parents=True, exist_ok=True)
    with open(log,"w",encoding="utf-8") as lf:
        p = subprocess.Popen([str(py),str(ROOT/"main.py")],cwd=str(ROOT),
                             stdout=lf,stderr=lf,creationflags=0x08000000)
    p.wait()
    if p.returncode != 0:
        c = ""
        try: c = log.read_text(encoding="utf-8",errors="replace")
        except: pass
        _err(f"NEXO cerro con error ({p.returncode}):\n\n"+
             "\n".join(c.splitlines()[-25:])+f"\n\nLog: {log}")
main()
