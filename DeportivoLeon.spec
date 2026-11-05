# Genera dist/DeportivoLeon.exe con: pyinstaller DeportivoLeon.spec
import os

import PySide6

a = Analysis(
    ["main.py"],
    datas=[
        ("dep_leon/assets", "dep_leon/assets"),
        (os.path.join(os.path.dirname(PySide6.__file__), "translations", "qtbase_es.qm"), "PySide6/translations"),
    ],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="DeportivoLeon",
    icon="dep_leon/assets/icono.ico",
    console=False,
    upx=False,
)
