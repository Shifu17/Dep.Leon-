# Genera dist/DeportivoLeon.exe con: pyinstaller DeportivoLeon.spec
a = Analysis(
    ["main.py"],
    datas=[("dep_leon/assets", "dep_leon/assets")],
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
