"""Genera las capturas de la documentación con datos inventados, sin tocar los datos reales.

Uso: python scripts/capturas.py
"""

import os
import random
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "docs" / "img"

os.environ["DEP_LEON_DATA"] = tempfile.mkdtemp(prefix="DeportivoLeon-capturas-")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(RAIZ))

from PySide6.QtGui import QFont, QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from dep_leon import acceso, arbitros, asistencia, cobros, db, liguilla, lienzo, reportes, resultados, rol, updater  # noqa: E402
from dep_leon.paths import db_path  # noqa: E402
from dep_leon.ui.acceso import DialogoAcceso  # noqa: E402
from dep_leon.ui.tema import ESTILO  # noqa: E402
from dep_leon.ui.ventana import Ventana  # noqa: E402

EQUIPOS = {
    "2015-2016": ["Águilas", "Toros", "Linces", "Pumas", "Jaguares", "Coyotes"],
    "2017-2018": ["Águilas", "Toros", "Linces", "Pumas"],
}


def preparar(conn):
    infantil = conn.execute("SELECT id FROM ligas WHERE nombre = 'Infantil'").fetchone()["id"]
    categorias = {
        c["nombre"]: c["id"]
        for c in conn.execute("SELECT * FROM categorias WHERE liga_id = ?", (infantil,))
    }
    with conn:
        torneo = conn.execute(
            "INSERT INTO torneos (liga_id, nombre) VALUES (?, 'Copa de Ejemplo')", (infantil,)
        ).lastrowid
        for categoria, nombres in EQUIPOS.items():
            for equipo in nombres:
                equipo_id = conn.execute(
                    "INSERT INTO equipos (torneo_id, categoria_id, nombre) VALUES (?, ?, ?)",
                    (torneo, categorias[categoria], equipo),
                ).lastrowid
                # Datos inventados con la forma de la hoja de registro (la CURP no es de nadie).
                conn.execute(
                    "UPDATE equipos SET responsable = ?, asistente = ?, director = ?, rama = 'VARONIL', "
                    "telefono = '8440000000' WHERE id = ?",
                    (f"Entrenador {equipo}", f"Asistente {equipo}", "Dirección del club", equipo_id),
                )
                for numero in range(1, 6):
                    conn.execute(
                        "INSERT INTO jugadores (equipo_id, nombre, fecha_nacimiento, numero, curp) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (equipo_id, f"Jugador {numero} {equipo}", f"{categoria[:4]}-03-01", numero,
                         f"XXXX{categoria[2:4]}0301HCLXXX{numero:02d}"),
                    )
    ids = [categorias[c] for c in EQUIPOS]
    cobros.guardar_tarifas(conn, torneo, {ids[0]: (15000, 120000), ids[1]: (12000, 100000)})

    hoy = rol.hoy()
    inicio = hoy - timedelta(days=(hoy.weekday() - 5) % 7 + 21)
    rol.generar(conn, torneo, ids, rol.Horario(inicio, {5: (540, 840)}), azar=random.Random(7))

    azar = random.Random(11)
    # Árbitros inventados, sin foto: se ven con sus iniciales.
    silbantes = [arbitros.guardar(conn, n, "8440000000") for n in ("Árbitro Uno", "Árbitro Dos", "Árbitro Tres")]
    for p in conn.execute(
        "SELECT * FROM partidos WHERE fecha < ? ORDER BY fecha", (hoy.isoformat(),)
    ).fetchall():
        goles_local, goles_visitante = azar.randint(0, 4), azar.randint(0, 3)
        goles: dict[int, int] = {}
        for equipo, total in ((p["local_id"], goles_local), (p["visitante_id"], goles_visitante)):
            plantel = [j["id"] for j in conn.execute("SELECT id FROM jugadores WHERE equipo_id = ?", (equipo,))]
            for _ in range(total):
                elegido = azar.choice(plantel[:3])
                goles[elegido] = goles.get(elegido, 0) + 1
        resultados.guardar_resultado(conn, p["id"], goles_local, goles_visitante, goles)
        vinieron = set(goles)
        for equipo in (p["local_id"], p["visitante_id"]):
            plantel = [j["id"] for j in conn.execute("SELECT id FROM jugadores WHERE equipo_id = ?", (equipo,))]
            vinieron |= set(azar.sample(plantel, azar.randint(3, len(plantel))))
        asistencia.guardar(conn, p["id"], vinieron)
        arbitros.asignar(conn, p["id"], azar.choice(silbantes), azar.choice([3, 4, 4, 5, 5]))

    aguilas = conn.execute(
        "SELECT id FROM equipos WHERE nombre = 'Águilas' AND categoria_id = ?", (ids[0],)
    ).fetchone()["id"]
    cobros.registrar_pago(conn, aguilas, 125000, hoy, "transferencia")

    llave = liguilla.crear(conn, torneo, ids[1], 1, 4, liguilla.PENALES)
    semifinales = [v for v in liguilla.vista(conn, llave) if v.numero_ronda == 1]
    for v, hora in zip(semifinales, ("09:00", "09:50")):
        with conn:
            conn.execute(
                "UPDATE partidos SET fecha = ?, hora = ?, cancha = '1', estado = ? WHERE id = ?",
                ((hoy + timedelta(days=7)).isoformat(), hora, rol.PROGRAMADO, v.partido_id),
            )
    resultados.guardar_resultado(conn, semifinales[0].partido_id, 2, 2, penales=(4, 3))
    return torneo, ids


def main():
    DESTINO.mkdir(parents=True, exist_ok=True)
    updater.buscar = lambda actual: None
    app = QApplication([])
    for fuente in ("segoeui", "segoeuib", "seguisb", "segmdl2"):
        QFontDatabase.addApplicationFont(f"C:/Windows/Fonts/{fuente}.ttf")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyle("Fusion")
    app.setStyleSheet(ESTILO)

    conn = db.conectar(db_path())
    torneo, categorias = preparar(conn)
    acceso.crear_cuenta(conn, "Administrador", "contrasena-de-ejemplo")

    dialogo = DialogoAcceso(conn)
    dialogo.show()
    app.processEvents()
    dialogo.grab().save(str(DESTINO / "inicio_de_sesion.png"))
    dialogo.close()

    ventana = Ventana(conn)
    ventana.resize(1200, 760)
    ventana.show()
    ventana.temporizador.stop()
    navegacion = {b.text(): b for b in ventana.findChildren(QPushButton) if b.objectName() == "nav"}

    def capturar(pagina: str, archivo: str, preparar_pagina=None):
        navegacion[pagina].click()
        app.processEvents()
        if preparar_pagina:
            preparar_pagina()
            app.processEvents()
        ventana.grab().save(str(DESTINO / archivo))

    def elegir_categoria(filtros, nombre):
        filtros.categoria.setCurrentText(nombre)

    capturar("Inicio", "inicio.png")
    capturar(
        "Rol de juegos", "rol.png",
        lambda: ventana.rol.categoria.setCurrentIndex(0) or ventana.rol.fecha.setCurrentIndex(0),
    )
    capturar("Estadísticas", "estadisticas.png", lambda: elegir_categoria(ventana.estadisticas.filtros, "2015-2016"))
    capturar("Liguilla", "liguilla.png", lambda: elegir_categoria(ventana.liguilla.filtros, "2017-2018"))

    def elegir_equipo():
        tabla = ventana.cobros.equipos
        tabla.selectRow(next(f for f in range(tabla.rowCount()) if tabla.item(f, 0).text() == "Águilas"))

    capturar("Cobros", "cobros.png", elegir_equipo)

    def equipo_con_lista():
        ventana.equipos.categoria.setCurrentText("2015-2016")
        app.processEvents()
        tabla = ventana.equipos.tabla_equipos
        tabla.selectRow(next(f for f in range(tabla.rowCount()) if tabla.item(f, 0).text() == "Águilas"))

    capturar("Equipos y jugadores", "equipos.png", equipo_con_lista)
    capturar("Árbitros", "arbitros.png")

    from dep_leon.ui import pagina_resultados as ui_resultados  # noqa: E402

    jugado = conn.execute("SELECT p.id FROM partidos p JOIN arbitrajes x ON x.partido_id = p.id LIMIT 1").fetchone()
    fila = ui_resultados._partido_completo(conn, jugado["id"])
    captura = ui_resultados.DialogoResultado(ventana, conn, fila, fila["local"], fila["visitante"])
    captura.show()
    app.processEvents()
    captura.grab().save(str(DESTINO / "calificar_arbitro.png"))
    captura.close()
    from dep_leon.ui.pagina_equipos import DialogoListaEquipo  # noqa: E402

    aguilas_infantil = conn.execute(
        "SELECT id FROM equipos WHERE nombre = 'Águilas' AND categoria_id = ?", (categorias[0],)
    ).fetchone()["id"]
    lista = DialogoListaEquipo(ventana, conn, aguilas_infantil, "Águilas")
    lista.resize(900, 420)
    lista.show()
    app.processEvents()
    lista.grab().save(str(DESTINO / "pase_de_lista.png"))
    lista.close()
    primera_fecha = reportes.fechas_de_rol(conn, torneo)[-2]
    lienzo.guardar_imagen(reportes.hoja_rol(conn, torneo, None, primera_fecha), DESTINO / "reporte_rol.png")
    conn.close()
    print(f"Capturas guardadas en {DESTINO}")


if __name__ == "__main__":
    main()
