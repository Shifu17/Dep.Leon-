# Deportivo León

Programa de escritorio para Windows para administrar la liga. Los requisitos y las etapas están
en [docs/REQUISITOS.md](docs/REQUISITOS.md).

## Desarrollo

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python main.py      # abrir el programa
.venv\Scripts\python -m pytest    # correr las pruebas
```

Los datos se guardan en `%LOCALAPPDATA%\DeportivoLeon`, fuera del programa y del repositorio.
Para probar sin tocarlos, define la variable `DEP_LEON_DATA` con otra carpeta.

## Generar el ejecutable

```powershell
.venv\Scripts\pyinstaller --noconfirm DeportivoLeon.spec
```

El resultado queda en `dist\DeportivoLeon.exe`.

## Publicar una actualización

El programa instalado consulta la última versión publicada en GitHub cuando hay internet.

1. Sube `__version__` en `dep_leon/__init__.py` y genera el ejecutable.
2. Calcula la huella del archivo:
   ```powershell
   (Get-FileHash dist\DeportivoLeon.exe -Algorithm SHA256).Hash | Set-Content -NoNewline dist\DeportivoLeon.exe.sha256
   ```
3. Publica la versión con ambos archivos. Los nombres deben ser exactamente estos:
   ```powershell
   gh release create v0.2.0 dist\DeportivoLeon.exe dist\DeportivoLeon.exe.sha256 --notes "Qué cambió"
   ```

El repositorio es público: nunca subas la base de datos, las fotos ni archivos con datos de
jugadores.
