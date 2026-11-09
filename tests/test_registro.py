"""Hoja de registro de los clubes, pase de lista y la migración que los hizo posibles."""

import sqlite3
from datetime import datetime

import pytest
from openpyxl import Workbook, load_workbook

from dep_leon import asistencia, db, registro, rol


def hoja_de_registro(ruta, club="Halcones FC", categoria="LIBRE", rama="VARONIL", jugadores=None, numeros=None):
    """Arma un archivo con el mismo acomodo que entregan los clubes."""
    jugadores = jugadores or [
        ("JUAN PÉREZ GÓMEZ ", datetime(1984, 7, 16), "PEGJ840716HCLRMN01"),
        ("LUIS SOTO RÍOS", "21/08/2008", "SORL080821HCLTSS02"),
        ("PEDRO NAVA", datetime(2007, 2, 25), None),
    ]
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Hoja de Registro"
    hoja["B3"], hoja["C3"] = "NOMBRE DEL CLUB", club
    hoja["B4"], hoja["C4"] = "CATEGORÍA:", categoria
    hoja["B5"], hoja["C5"] = "RAMA:", rama
    for i, titulo in enumerate(["NO. PLAYERA", "NOMBRE COMPLETO", "FECHA DE NACIMIENTO", "CURP"], start=2):
        hoja.cell(row=7, column=i, value=titulo)
    for n in range(10):
        hoja.cell(row=7, column=7 + n, value=f"J{n + 1}")
    for r, (nombre, nacimiento, curp) in enumerate(jugadores, start=8):
        hoja.cell(row=r, column=2, value=(numeros or {}).get(r))
        hoja.cell(row=r, column=3, value=nombre)
        hoja.cell(row=r, column=4, value=nacimiento)
        hoja.cell(row=r, column=5, value=curp)
    fin = 8 + len(jugadores)
    hoja.cell(row=fin, column=2, value="Entrenador")
    hoja.cell(row=fin, column=3, value="JUAN PÉREZ")
    hoja.cell(row=fin + 1, column=2, value="Asistente")
    hoja.cell(row=fin + 2, column=2, value="Dr. Gral")
    hoja.cell(row=fin + 2, column=3, value="ANA LÓPEZ")
    libro.create_sheet("Cédula")["A1"] = "Deportivo León Saltillo A.C."
    libro.save(ruta)
    return ruta


@pytest.fixture
def libre(conn):
    """Torneo de una liga libre, que al empezar no tiene categorías."""
    liga = conn.execute("SELECT id FROM ligas WHERE nombre = 'Libre Martes'").fetchone()["id"]
    with conn:
        return conn.execute("INSERT INTO torneos (liga_id, nombre) VALUES (?, 'Apertura')", (liga,)).lastrowid


def test_lee_club_categoria_jugadores_y_personal(tmp_path):
    ruta = hoja_de_registro(tmp_path / "halcones.xlsx")
    assert registro.es_hoja_de_registro(ruta)
    (r,) = registro.leer([ruta])
    assert (r.equipo, r.categoria, r.rama) == ("Halcones FC", "LIBRE", "VARONIL")
    assert (r.entrenador, r.asistente, r.director) == ("JUAN PÉREZ", "", "ANA LÓPEZ")
    assert [v["nombre"] for _, v in r.crudos][0].strip() == "JUAN PÉREZ GÓMEZ"
    assert len(r.crudos) == 3  # el renglón del entrenador no es un jugador


def test_plantilla_del_programa_no_se_confunde_con_registro(conn, tmp_path, infantil_id):
    from dep_leon import excel

    ruta = tmp_path / "plantilla.xlsx"
    excel.crear_plantilla(conn, infantil_id, ruta)
    assert not registro.es_hoja_de_registro(ruta)


def test_importa_sin_numero_crea_categoria_y_no_duplica(conn, libre, tmp_path):
    ruta = hoja_de_registro(tmp_path / "halcones.xlsx")
    registros = registro.leer([ruta])
    registro.preparar(conn, registros, libre)
    assert registros[0].categoria_id == registro.CATEGORIA_NUEVA
    assert registros[0].validas == 3

    assert registro.importar(conn, registros, libre, tmp_path) == (3, 0, 1, 1)
    categoria = conn.execute("SELECT * FROM categorias WHERE nombre = 'Libre'").fetchone()
    assert (categoria["anio_min"], categoria["anio_max"]) == (None, None)
    equipo = conn.execute("SELECT * FROM equipos").fetchone()
    assert (equipo["nombre"], equipo["responsable"]) == ("Halcones FC", "JUAN PÉREZ")
    jugador = conn.execute("SELECT * FROM jugadores WHERE nombre LIKE 'LUIS%'").fetchone()
    assert (jugador["numero"], jugador["fecha_nacimiento"], jugador["curp"]) == (
        None, "2008-08-21", "SORL080821HCLTSS02"
    )

    registros = registro.leer([ruta])
    registro.preparar(conn, registros, libre)
    assert registros[0].categoria_id == categoria["id"]  # la segunda vez ya la encuentra
    assert registro.importar(conn, registros, libre, tmp_path) == (0, 3, 0, 0)


def test_varios_archivos_de_distintas_categorias(conn, torneo_id, tmp_path):
    rutas = [
        hoja_de_registro(tmp_path / "a.xlsx", club="Pumas", categoria="2015-2016",
                         jugadores=[("Ana Ruiz", datetime(2015, 3, 1), None)]),
        hoja_de_registro(tmp_path / "b.xlsx", club="Toros", categoria="2014",
                         jugadores=[("Beto Paz", datetime(2014, 5, 2), None)]),
    ]
    registros = registro.leer(rutas)
    registro.preparar(conn, registros, torneo_id)
    nombres = {
        r.equipo: conn.execute("SELECT nombre FROM categorias WHERE id = ?", (r.categoria_id,)).fetchone()["nombre"]
        for r in registros
    }
    assert nombres == {"Pumas": "2015-2016", "Toros": "2013-2014"}  # el año cae en su rango
    assert registro.importar(conn, registros, torneo_id, tmp_path)[:3] == (2, 0, 2)


def test_edad_fuera_de_categoria_y_numero_repetido_se_reportan(conn, torneo_id, tmp_path):
    ruta = hoja_de_registro(
        tmp_path / "x.xlsx", club="Linces", categoria="2015-2016",
        jugadores=[("Uno", datetime(2015, 1, 1), None), ("Dos", datetime(2010, 1, 1), None),
                   ("Tres", datetime(2016, 1, 1), "CORTA")],
        numeros={8: 5, 10: 5},
    )
    registros = registro.leer([ruta])
    registro.preparar(conn, registros, torneo_id)
    filas = {f.nombre: f for f in registros[0].filas}
    assert filas["Uno"].valida
    assert any("2010" in e for e in filas["Dos"].errores)
    assert any("número 5" in e for e in filas["Tres"].errores)
    assert any("CURP" in a for a in filas["Tres"].avisos)


def test_archivo_sin_hoja_de_registro_da_mensaje_claro(tmp_path):
    ruta = tmp_path / "otro.xlsx"
    Workbook().save(ruta)
    with pytest.raises(ValueError, match="NOMBRE DEL CLUB"):
        registro.leer([ruta])


@pytest.fixture
def partido(conn, torneo_id, tmp_path):
    rutas = [
        hoja_de_registro(tmp_path / f"{n}.xlsx", club=n, categoria="2015-2016",
                         jugadores=[(f"{n} uno", datetime(2015, 1, 1), None), (f"{n} dos", datetime(2015, 2, 2), None)])
        for n in ("Pumas", "Toros")
    ]
    registros = registro.leer(rutas)
    registro.preparar(conn, registros, torneo_id)
    registro.importar(conn, registros, torneo_id, tmp_path)
    pumas, toros = (conn.execute("SELECT id FROM equipos WHERE nombre = ?", (n,)).fetchone()["id"] for n in ("Pumas", "Toros"))
    categoria = conn.execute("SELECT categoria_id FROM equipos WHERE id = ?", (pumas,)).fetchone()[0]
    with conn:
        partido_id = conn.execute(
            """INSERT INTO partidos (torneo_id, categoria_id, jornada, local_id, visitante_id, fecha, hora,
               minutos, cancha, estado) VALUES (?, ?, 1, ?, ?, '2026-11-14', '09:00', 50, '1', ?)""",
            (torneo_id, categoria, pumas, toros, rol.PROGRAMADO),
        ).lastrowid
    return partido_id, pumas, toros


def _jugadores(conn, equipo_id):
    return [f["id"] for f in conn.execute("SELECT id FROM jugadores WHERE equipo_id = ? ORDER BY id", (equipo_id,))]


def test_pase_de_lista_por_partido_y_resumen(conn, partido):
    partido_id, pumas, toros = partido
    p1, p2 = _jugadores(conn, pumas)
    t1, _ = _jugadores(conn, toros)
    asistencia.guardar(conn, partido_id, {p1, t1})
    assert asistencia.presentes(conn, partido_id) == {p1, t1}
    assert asistencia.resumen_de_equipo(conn, pumas) == ({p1: 1}, 1)

    asistencia.guardar(conn, partido_id, {p1, p2})  # se corrige: reemplaza la lista anterior
    assert asistencia.presentes(conn, partido_id) == {p1, p2}

    (columna,) = asistencia.partidos_de_equipo(conn, pumas)
    assert columna.etiqueta == "J1" and "Toros" in columna.descripcion


def test_pase_de_lista_rechaza_jugadores_ajenos(conn, partido, torneo_id):
    partido_id, pumas, _ = partido
    otro = conn.execute(
        "INSERT INTO equipos (torneo_id, categoria_id, nombre) SELECT torneo_id, categoria_id, 'Otro' FROM equipos WHERE id = ?",
        (pumas,),
    ).lastrowid
    ajeno = conn.execute(
        "INSERT INTO jugadores (equipo_id, nombre, fecha_nacimiento) VALUES (?, 'Ajeno', '2015-01-01')", (otro,)
    ).lastrowid
    conn.commit()
    with pytest.raises(ValueError):
        asistencia.guardar(conn, partido_id, {ajeno})


def test_cuadricula_de_equipo_no_toca_al_rival(conn, partido):
    partido_id, pumas, toros = partido
    p1, p2 = _jugadores(conn, pumas)
    t1, _ = _jugadores(conn, toros)
    asistencia.guardar(conn, partido_id, {p1, t1})
    asistencia.guardar_de_equipo(conn, pumas, {partido_id: {p2}})
    assert asistencia.presentes(conn, partido_id) == {p2, t1}


def test_exportar_registro_marca_el_pase_de_lista(conn, partido, tmp_path):
    partido_id, pumas, _ = partido
    p1, _ = _jugadores(conn, pumas)
    asistencia.guardar(conn, partido_id, {p1})
    destino = tmp_path / "salida.xlsx"
    registro.exportar(conn, pumas, destino)

    hoja = load_workbook(destino).active
    assert hoja["C3"].value == "Pumas" and hoja["G7"].value == "J1"
    marcas = {hoja.cell(row=r, column=3).value: hoja.cell(row=r, column=7).value for r in (8, 9)}
    assert marcas == {"Pumas uno": registro.MARCA_ASISTENCIA, "Pumas dos": None}
    (vuelta,) = registro.leer([destino])  # el archivo exportado se puede volver a importar
    assert vuelta.equipo == "Pumas" and len(vuelta.crudos) == 2


def test_borrar_partido_borra_su_lista(conn, partido):
    partido_id, pumas, _ = partido
    asistencia.guardar(conn, partido_id, set(_jugadores(conn, pumas)))
    with conn:
        conn.execute("DELETE FROM partidos WHERE id = ?", (partido_id,))
    assert conn.execute("SELECT COUNT(*) FROM asistencias").fetchone()[0] == 0


def test_migra_una_base_anterior_sin_perder_goles(tmp_path):
    """Hasta la 0.9.5 el número era obligatorio y no existía la CURP."""
    ruta = tmp_path / "vieja.db"
    vieja = sqlite3.connect(ruta)
    esquema_viejo = db.ESQUEMA.replace("    numero INTEGER,\n", "    numero INTEGER NOT NULL,\n").replace(
        "    curp TEXT NOT NULL DEFAULT '',\n", ""
    )
    vieja.executescript(esquema_viejo)
    with vieja:
        vieja.execute("INSERT INTO ligas (id, nombre, modalidad) VALUES (1, 'L', 'Fut 7')")
        vieja.execute("INSERT INTO categorias (id, liga_id, nombre) VALUES (1, 1, 'C')")
        vieja.execute("INSERT INTO torneos (id, liga_id, nombre) VALUES (1, 1, 'T')")
        vieja.execute("INSERT INTO equipos (id, torneo_id, categoria_id, nombre) VALUES (1, 1, 1, 'A'), (2, 1, 1, 'B')")
        vieja.execute("INSERT INTO jugadores (id, equipo_id, nombre, fecha_nacimiento, numero) VALUES (1, 1, 'Ana', '2015-01-01', 7)")
        vieja.execute(
            "INSERT INTO partidos (id, torneo_id, categoria_id, jornada, local_id, visitante_id, minutos, estado) "
            "VALUES (1, 1, 1, 1, 1, 2, 50, 'Jugado')"
        )
        vieja.execute("INSERT INTO goles VALUES (1, 1, 2)")
    vieja.close()

    conn = db.conectar(ruta)
    columnas = {c["name"]: c["notnull"] for c in conn.execute("PRAGMA table_info(jugadores)")}
    assert columnas["numero"] == 0 and "curp" in columnas
    assert tuple(conn.execute("SELECT nombre, numero, curp FROM jugadores").fetchone()) == ("Ana", 7, "")
    assert conn.execute("SELECT cantidad FROM goles").fetchone()[0] == 2
    with pytest.raises(sqlite3.IntegrityError):  # los goles siguen protegiendo al jugador
        conn.execute("DELETE FROM jugadores WHERE id = 1")
    conn.close()


# --- Pantallas ------------------------------------------------------------------------------------


def test_vista_previa_permite_cambiar_la_categoria(app, conn, torneo_id, tmp_path):
    from PySide6.QtWidgets import QComboBox

    from dep_leon.ui.pagina_equipos import DialogoRegistros

    ruta = hoja_de_registro(tmp_path / "x.xlsx", club="Linces", categoria="LIBRE",
                            jugadores=[("Uno", datetime(2015, 1, 1), None)])
    registros = registro.leer([ruta])
    registro.preparar(conn, registros, torneo_id)
    categorias = conn.execute(
        "SELECT * FROM categorias WHERE liga_id = (SELECT liga_id FROM torneos WHERE id = ?) ORDER BY nombre",
        (torneo_id,),
    ).fetchall()
    dialogo = DialogoRegistros(None, conn, registros, torneo_id, categorias)
    assert "Crear nueva" in dialogo.equipos.cellWidget(0, 3).currentText()
    assert dialogo.importar.text() == "Importar 1 jugador de 1 equipo"

    combo: QComboBox = dialogo.equipos.cellWidget(0, 3)
    combo.setCurrentIndex(combo.findText("2009-2010"))  # nació en 2015: no corresponde
    assert registros[0].validas == 0 and not dialogo.importar.isEnabled()
    assert "Error" in dialogo.jugadores.item(0, 5).text()


def test_cuadricula_del_equipo_guarda_lo_marcado(app, conn, partido):
    from dep_leon.ui.pagina_equipos import DialogoListaEquipo

    partido_id, pumas, _ = partido
    p1, p2 = _jugadores(conn, pumas)
    dialogo = DialogoListaEquipo(None, conn, pumas, "Pumas")
    assert dialogo.rejilla.horizontalHeaderItem(1).text() == "J1"
    fila = next(r for r in range(dialogo.rejilla.rowCount()) if dialogo.rejilla.item(r, 0).text() == "Pumas dos")
    dialogo.alternar(fila, 1)  # un clic en la celda la marca
    assert dialogo.marcado(fila, 1) and dialogo.rejilla.item(fila, 2).text() == "1"
    dialogo.alternar(fila, 0)  # el nombre no es una casilla
    assert dialogo.rejilla.item(fila, 2).text() == "1"
    dialogo._aceptar()
    assert asistencia.presentes(conn, partido_id) == {p2}


def test_capturar_resultado_guarda_quien_vino_y_suma_goleadores(app, conn, partido):
    from dep_leon.ui import pagina_resultados as ui_resultados

    partido_id, pumas, toros = partido
    p1, p2 = _jugadores(conn, pumas)
    t1, _ = _jugadores(conn, toros)
    with conn:
        conn.execute("UPDATE partidos SET fecha = '2026-11-01' WHERE id = ?", (partido_id,))
    fila = conn.execute("SELECT * FROM partidos WHERE id = ?", (partido_id,)).fetchone()
    dialogo = ui_resultados.DialogoResultado(None, conn, fila, "Pumas", "Toros")
    dialogo.local.casillas[p1].setChecked(True)
    dialogo.marcador_local.setValue(1)
    dialogo.goles[p2].setValue(1)  # anotó sin que lo marcaran: cuenta como presente
    assert dialogo.local.casillas[p2].isChecked()
    dialogo.visitante.casillas[t1].setChecked(True)
    dialogo._aceptar()
    assert asistencia.presentes(conn, partido_id) == {p1, p2, t1}


def test_pase_de_lista_desde_resultados(app, conn, partido):
    from dep_leon.ui.lista import DialogoPaseLista

    partido_id, pumas, _ = partido
    p1, _ = _jugadores(conn, pumas)
    fila = conn.execute(
        """SELECT p.*, l.nombre AS local, v.nombre AS visitante FROM partidos p
           JOIN equipos l ON l.id = p.local_id JOIN equipos v ON v.id = p.visitante_id WHERE p.id = ?""",
        (partido_id,),
    ).fetchone()
    dialogo = DialogoPaseLista(None, conn, fila)
    dialogo.local._marcar_todos(True)
    assert dialogo.local.contador.text() == "Vinieron 2 de 2 jugadores."
    dialogo._aceptar()
    assert asistencia.presentes(conn, partido_id) == set(_jugadores(conn, pumas))
