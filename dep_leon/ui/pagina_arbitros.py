"""Página de árbitros: registro con foto, su promedio de estrellas y los partidos que han dirigido."""

import sqlite3
from datetime import date
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from .. import arbitros, rol
from ..jugadores import borrar_foto, guardar_foto
from ..paths import fotos_dir
from . import campos, diseno
from .comun import (
    al_activar,
    boton,
    botones_dialogo,
    campo_busqueda,
    confirmar,
    error,
    fila_con_error,
    id_seleccionado,
    listo,
    llenar,
    poner_vacio,
    tabla,
)
from .avatar import avatar
from .estrellas import pixmap_estrellas

TAMANO_FOTO = QSize(120, 150)


def _ruta_foto(fila) -> Path | None:
    return fotos_dir() / fila["foto"] if fila and fila["foto"] else None


def _promedio(fila) -> str:
    return f"{fila['promedio']:.1f} de 5" if fila["calificados"] else "Sin calificar"


class DialogoArbitro(QDialog):
    def __init__(self, padre, arbitro=None):
        super().__init__(padre)
        self.setWindowTitle("Árbitro")
        self.ruta_foto: Path | None = None
        self.nombre = QLineEdit(arbitro["nombre"] if arbitro else "")
        self.telefono = QLineEdit(arbitro["telefono"] if arbitro else "")
        campos.solo_nombre(self.nombre, "Nombre y apellidos")
        campos.solo_telefono(self.telefono)
        self.activo = QCheckBox("Disponible para asignarle partidos")
        self.activo.setChecked(bool(arbitro["activo"]) if arbitro else True)
        self.vista_foto = QLabel("Sin foto", objectName="marcoFoto", alignment=Qt.AlignmentFlag.AlignCenter)
        self.vista_foto.setFixedSize(TAMANO_FOTO)
        if arbitro and arbitro["foto"]:
            self._mostrar_foto(fotos_dir() / arbitro["foto"])

        forma = QFormLayout(self)
        self.error_nombre = fila_con_error(forma, "Nombre completo:", self.nombre)
        self.error_telefono = fila_con_error(forma, "Teléfono:", self.telefono)
        forma.addRow("", self.activo)
        forma.addRow("Foto:", self.vista_foto)
        forma.addRow("", boton("Elegir foto...", self._elegir_foto, "secundario", icono="imagen"))
        forma.addRow(botones_dialogo(self, self._aceptar))

    def _mostrar_foto(self, ruta: Path) -> bool:
        imagen = QPixmap(str(ruta))
        if imagen.isNull():
            return False
        self.vista_foto.setPixmap(
            imagen.scaled(
                self.vista_foto.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        return True

    def _elegir_foto(self):
        ruta, _ = QFileDialog.getOpenFileName(self, "Elegir foto", "", "Imágenes (*.jpg *.jpeg *.png)")
        if not ruta:
            return
        if self._mostrar_foto(Path(ruta)):
            self.ruta_foto = Path(ruta)
        else:
            error(self, "No se pudo leer esa imagen.")

    def _aceptar(self):
        if not self.nombre.text().strip():
            self.error_nombre.mostrar("Escribe el nombre del árbitro.")
            return
        motivo = campos.error_telefono(self.telefono.text())
        if motivo:
            self.error_telefono.mostrar(motivo)
            return
        self.accept()


def combo_arbitros(conn: sqlite3.Connection, actual: int | None) -> QComboBox:
    """Los árbitros disponibles (y el ya asignado aunque esté de baja), con su foto."""
    combo = QComboBox()
    combo.setAccessibleName("Árbitro del partido")
    combo.addItem("Sin árbitro", None)
    for a in arbitros.para_elegir(conn, actual):
        combo.addItem(QIcon(avatar(_ruta_foto(a), a["nombre"], 20)), a["nombre"], a["id"])
    combo.setIconSize(QSize(20, 20))
    combo.setCurrentIndex(max(0, combo.findData(actual)))
    return combo


class DialogoAsignar(QDialog):
    """Elegir el árbitro de un partido desde el rol, antes de jugarse."""

    def __init__(self, padre, conn: sqlite3.Connection, partido_id: int, titulo: str):
        super().__init__(padre)
        self.setWindowTitle("Asignar árbitro")
        previo = arbitros.de_partido(conn, partido_id)
        self.arbitro = combo_arbitros(conn, previo["id"] if previo else None)
        forma = QFormLayout(self)
        forma.addRow(QLabel(titulo, objectName="seccion"))
        forma.addRow("Árbitro:", self.arbitro)
        if self.arbitro.count() == 1:
            forma.addRow(QLabel("Todavía no hay árbitros. Regístralos en la página «Árbitros».",
                                objectName="ayuda", wordWrap=True))
        forma.addRow(botones_dialogo(self, self.accept))


def asignar_arbitro(padre: QWidget, conn: sqlite3.Connection, partido_id: int) -> bool:
    partido = conn.execute(
        """SELECT l.nombre AS local, v.nombre AS visitante FROM partidos p
           JOIN equipos l ON l.id = p.local_id JOIN equipos v ON v.id = p.visitante_id WHERE p.id = ?""",
        (partido_id,),
    ).fetchone()
    dialogo = DialogoAsignar(padre, conn, partido_id, f"{partido['local']} vs {partido['visitante']}")
    if not dialogo.exec():
        return False
    try:
        arbitros.asignar(conn, partido_id, dialogo.arbitro.currentData())
    except ValueError as exc:
        error(padre, str(exc))
        return False
    return True


class FichaArbitro(QFrame):
    """Foto, datos y promedio del árbitro elegido."""

    def __init__(self):
        super().__init__(objectName="tarjeta")
        diseno.sombra(self)
        self.foto = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.foto.setFixedSize(TAMANO_FOTO)
        self.nombre = QLabel("Elige un árbitro", objectName="seccion", wordWrap=True)
        self.estrellas = QLabel()
        self.estrellas.setAccessibleName("Calificación promedio")
        self.calificacion = QLabel(objectName="ayuda")
        self.valores: dict[str, QLabel] = {}
        datos = QGridLayout()
        datos.setHorizontalSpacing(18)
        datos.setVerticalSpacing(8)
        for i, (clave, titulo) in enumerate(
            (("telefono", "Teléfono"), ("partidos", "Partidos asignados"), ("estado", "Estado"))
        ):
            caja = QVBoxLayout()
            caja.setSpacing(0)
            caja.addWidget(QLabel(titulo, objectName="datoTitulo"))
            valor = QLabel("-", objectName="datoValor")
            valor.setAccessibleName(titulo)
            valor.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            caja.addWidget(valor)
            self.valores[clave] = valor
            datos.addLayout(caja, 0, i)
        promedio = QHBoxLayout()
        promedio.setSpacing(8)
        promedio.addWidget(self.estrellas)
        promedio.addWidget(self.calificacion, 1)

        textos = QVBoxLayout()
        textos.setSpacing(6)
        textos.addWidget(self.nombre)
        textos.addLayout(promedio)
        textos.addSpacing(4)
        textos.addLayout(datos)
        textos.addStretch(1)
        fila = QHBoxLayout(self)
        fila.setContentsMargins(16, 14, 16, 14)
        fila.setSpacing(16)
        fila.addWidget(self.foto, 0, Qt.AlignmentFlag.AlignTop)
        fila.addLayout(textos, 1)
        self.mostrar(None)

    def mostrar(self, fila):
        if fila is None:
            self.foto.setPixmap(avatar(None, "?", TAMANO_FOTO.width()))
            self.nombre.setText("Elige un árbitro de la lista")
            self.estrellas.setPixmap(pixmap_estrellas(0, 18))
            self.calificacion.setText("")
            for valor in self.valores.values():
                valor.setText("-")
            return
        ruta = _ruta_foto(fila)
        imagen = QPixmap(str(ruta)) if ruta else QPixmap()
        if imagen.isNull():
            self.foto.setPixmap(avatar(None, fila["nombre"], TAMANO_FOTO.width()))
        else:
            self.foto.setPixmap(imagen.scaled(
                TAMANO_FOTO, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            ))
        self.nombre.setText(fila["nombre"])
        self.estrellas.setPixmap(pixmap_estrellas(fila["promedio"], 18))
        if fila["calificados"]:
            veces = "calificación" if fila["calificados"] == 1 else "calificaciones"
            self.calificacion.setText(f"{fila['promedio']:.1f} de 5 · {fila['calificados']} {veces}")
        else:
            self.calificacion.setText("Sin calificar todavía")
        self.valores["telefono"].setText(fila["telefono"] or "-")
        self.valores["partidos"].setText(str(fila["partidos"]))
        self.valores["estado"].setText("Disponible" if fila["activo"] else "De baja")


class PaginaArbitros(QWidget):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.setObjectName("pagina")
        self.conn = conn

        self.tabla = tabla(["Nombre", "Partidos", "Calificación", "Estado"], estirar=0)
        self.tabla.setIconSize(QSize(26, 26))
        self.tabla.itemSelectionChanged.connect(self.refrescar_ficha)
        al_activar(self.tabla, self.editar)
        poner_vacio(self.tabla, "Todavía no hay árbitros. Pulsa «Agregar árbitro» para registrar el primero.")
        self.busqueda = campo_busqueda(self.tabla, "Buscar árbitro")

        self.ficha = FichaArbitro()
        self.partidos = tabla(["Fecha", "Partido", "Calificó", "Calificación", "Comentario"], estirar=4)
        self.partidos.setIconSize(QSize(68, 12))
        poner_vacio(self.partidos, "Este árbitro todavía no tiene partidos. Se le asignan en «Rol de juegos» "
                                   "o al capturar el resultado.")

        izquierda = QVBoxLayout()
        cabeza = QHBoxLayout()
        cabeza.addWidget(QLabel("Árbitros registrados", objectName="seccion"))
        cabeza.addStretch(1)
        cabeza.addWidget(self.busqueda)
        izquierda.addLayout(cabeza)
        izquierda.addWidget(self.tabla, 1)
        fila = diseno.FilaBotones()
        fila.addWidget(boton("Editar árbitro", self.editar, "secundario"))
        fila.addWidget(boton("Eliminar", self.borrar, "peligro"))
        izquierda.addLayout(fila)

        derecha = QVBoxLayout()
        derecha.addWidget(self.ficha)
        derecha.addSpacing(6)
        derecha.addWidget(QLabel("Partidos que ha dirigido", objectName="seccion"))
        derecha.addWidget(self.partidos, 1)

        columnas = QHBoxLayout()
        columnas.setSpacing(14)
        columnas.addLayout(izquierda, 2)
        columnas.addLayout(derecha, 3)

        raiz = QVBoxLayout(self)
        raiz.addWidget(diseno.encabezado(
            "Árbitros",
            "Registra a los árbitros con su foto. Asígnalos a cada partido en «Rol de juegos» o al capturar "
            "el resultado, y ahí mismo califícalos de 1 a 5 estrellas.",
            [boton("Agregar árbitro", self.nuevo)],
        ))
        raiz.addLayout(columnas, 1)
        self.refrescar()

    def showEvent(self, evento):
        super().showEvent(evento)
        self.refrescar()  # las calificaciones cambian al capturar resultados

    def refrescar(self):
        self._filas = {f["id"]: f for f in arbitros.resumen(self.conn)}
        llenar(
            self.tabla,
            [
                (f["id"], [f["nombre"], f["partidos"], _promedio(f),
                           "Disponible" if f["activo"] else "De baja"])
                for f in self._filas.values()
            ],
        )
        for r in range(self.tabla.rowCount()):
            fila = self._filas[self.tabla.item(r, 0).data(Qt.ItemDataRole.UserRole)]
            self.tabla.item(r, 0).setIcon(QIcon(avatar(_ruta_foto(fila), fila["nombre"], 26)))
        self.tabla.setIconSize(QSize(26, 26))
        if id_seleccionado(self.tabla) is None and self.tabla.rowCount():
            self.tabla.selectRow(0)
        self.refrescar_ficha()

    def refrescar_ficha(self):
        arbitro_id = id_seleccionado(self.tabla)
        self.ficha.mostrar(self._filas.get(arbitro_id))
        filas = arbitros.historial(self.conn, arbitro_id) if arbitro_id is not None else []

        def calificacion(p) -> str:
            if p["estrellas"]:
                return f"{p['estrellas']} de 5"
            if p["equipo"]:
                return "Sin estrellas"
            return "Sin calificar" if p["estado"] in (rol.JUGADO, rol.DEFAULT) else "Por jugar"

        # Un renglón por cada equipo que calificó; la clave une partido y equipo.
        renglones = {f"{p['partido_id']}-{p['equipo_id']}": p for p in filas}
        llenar(
            self.partidos,
            [
                (
                    clave,
                    [
                        date.fromisoformat(p["fecha"]).strftime("%d/%m/%Y") if p["fecha"] else "Sin fecha",
                        f"{p['local']} {p['goles_local']}-{p['goles_visitante']} {p['visitante']}"
                        if p["goles_local"] is not None else f"{p['local']} vs {p['visitante']}",
                        p["equipo"] or "-",
                        calificacion(p),
                        p["comentario"] or "",
                    ],
                )
                for clave, p in renglones.items()
            ],
        )
        for r in range(self.partidos.rowCount()):
            p = renglones[self.partidos.item(r, 0).data(Qt.ItemDataRole.UserRole)]
            if p["estrellas"]:
                celda = self.partidos.item(r, 3)
                celda.setIcon(QIcon(pixmap_estrellas(p["estrellas"], 12)))
                celda.setToolTip(arbitros.texto_calificacion(p["estrellas"]))

    def _arbitro(self):
        arbitro_id = id_seleccionado(self.tabla)
        if arbitro_id is None:
            error(self, "Primero selecciona un árbitro.")
            return None
        return self.conn.execute("SELECT * FROM arbitros WHERE id = ?", (arbitro_id,)).fetchone()

    def nuevo(self):
        dialogo = DialogoArbitro(self)
        if dialogo.exec():
            self._guardar(dialogo, None)

    def editar(self):
        arbitro = self._arbitro()
        if arbitro is None:
            return
        dialogo = DialogoArbitro(self, arbitro)
        if dialogo.exec():
            self._guardar(dialogo, arbitro)

    def _guardar(self, dialogo: DialogoArbitro, arbitro):
        foto = arbitro["foto"] if arbitro else ""
        foto_nueva = None
        if dialogo.ruta_foto:
            try:
                foto_nueva = guardar_foto(dialogo.ruta_foto, fotos_dir())
            except ValueError as exc:
                error(self, str(exc))
                return
        try:
            arbitro_id = arbitros.guardar(
                self.conn, dialogo.nombre.text(), dialogo.telefono.text(), foto_nueva or foto,
                dialogo.activo.isChecked(), arbitro["id"] if arbitro else None,
            )
        except ValueError as exc:
            if foto_nueva:
                borrar_foto(foto_nueva, fotos_dir())
            error(self, str(exc))
            return
        if foto_nueva and foto:
            borrar_foto(foto, fotos_dir())
        self.refrescar()
        self._elegir(arbitro_id)
        listo(self, "árbitro guardado.")

    def _elegir(self, arbitro_id: int):
        for r in range(self.tabla.rowCount()):
            if self.tabla.item(r, 0).data(Qt.ItemDataRole.UserRole) == arbitro_id:
                self.tabla.selectRow(r)
                return

    def borrar(self):
        arbitro = self._arbitro()
        if arbitro is None:
            return
        if arbitros.partidos_dirigidos(self.conn, arbitro["id"]):
            if not arbitro["activo"]:
                error(self, "Este árbitro ya está de baja. Se conserva porque tiene partidos y calificaciones.")
                return
            if confirmar(
                self,
                f"{arbitro['nombre']} ya tiene partidos y calificaciones, así que no se puede eliminar. "
                "¿Darlo de baja? Ya no aparecerá al asignar partidos, pero se conserva su historial.",
            ):
                arbitros.dar_de_baja(self.conn, arbitro["id"])
                self.refrescar()
                listo(self, "árbitro dado de baja.")
            return
        if not confirmar(self, f"¿Eliminar a {arbitro['nombre']}?"):
            return
        borrar_foto(arbitros.borrar(self.conn, arbitro["id"]), fotos_dir())
        self.refrescar()
        listo(self, "árbitro eliminado.")
