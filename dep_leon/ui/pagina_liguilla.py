"""Página de liguilla: elegir el rango de clasificados, ver la llave y capturar sus partidos."""

import sqlite3
from datetime import date

from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import liguilla, rol
from .comun import boton, confirmar, error, info, llenar, tabla
from .filtros import FiltrosLiga
from .pagina_resultados import borrar_resultado, capturar_partido, marcar_no_presentado
from .pagina_rol import editar_partido

OPCIONES_DESEMPATE = [
    ("Penales", liguilla.PENALES),
    ("Mejor lugar en la tabla", liguilla.TABLA),
]


def _combo_desempate() -> QComboBox:
    combo = QComboBox()
    for texto, valor in OPCIONES_DESEMPATE:
        combo.addItem(texto, valor)
    return combo


def _linea_equipo(nombre: str, semilla, goles, penales, gano: bool) -> str:
    if not nombre:
        return "Por definir"
    marca = "» " if gano else ""
    lugar = f"({semilla}) " if semilla else ""
    marcador = "" if goles is None else f"   {goles}"
    extra = "" if penales is None else f" ({penales} pen.)"
    return f"{marca}{lugar}{nombre}{marcador}{extra}"


def texto_llave(v: liguilla.VistaLlave) -> str:
    if v.pasa_directo:
        return f"{v.ganador}\nPasa directo a la siguiente ronda"
    if v.fecha:
        dia = rol.DIAS[date.fromisoformat(v.fecha).weekday()][:3]
        cuando = f"{dia} {date.fromisoformat(v.fecha):%d/%m} · {v.hora} · Cancha {rol.nombre_cancha(v.cancha)}"
    elif v.partido_id:
        cuando = "Sin fecha"
    else:
        cuando = "Esperando rivales"
    return "\n".join(
        [
            cuando,
            _linea_equipo(v.equipo_a, v.semilla_a, v.goles_a, v.penales_a, bool(v.ganador) and v.ganador == v.equipo_a),
            _linea_equipo(v.equipo_b, v.semilla_b, v.goles_b, v.penales_b, bool(v.ganador) and v.ganador == v.equipo_b),
        ]
    )


class PaginaLiguilla(QWidget):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.setObjectName("pagina")
        self.conn = conn
        self.liguilla_id: int | None = None
        self._seleccion: int | None = None  # id de la llave elegida
        self._partidos: dict[int, int | None] = {}
        self._grupo = QButtonGroup(self, exclusive=True)

        self.filtros = FiltrosLiga(conn, con_todas=False)
        self.filtros.cambiado.connect(self.refrescar)

        self.aviso = QLabel(objectName="ayuda", wordWrap=True)
        self.crear_panel = self._crear_panel_nueva()
        self.llave_panel = self._crear_panel_llave()

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.addWidget(QLabel("Liguilla", objectName="titulo"))
        raiz.addWidget(self.filtros)
        raiz.addWidget(self.aviso)
        raiz.addWidget(self.crear_panel, 1)
        raiz.addWidget(self.llave_panel, 1)
        self.refrescar()

    def _crear_panel_nueva(self) -> QWidget:
        panel = QWidget()
        self.desde = QSpinBox(minimum=1, maximum=1)
        self.hasta = QSpinBox(minimum=1, maximum=1)
        self.desde.valueChanged.connect(self.refrescar_clasificados)
        self.hasta.valueChanged.connect(self.refrescar_clasificados)
        self.desempate_nuevo = _combo_desempate()

        fila = QHBoxLayout()
        fila.addWidget(QLabel("Clasifican del lugar"))
        fila.addWidget(self.desde)
        fila.addWidget(QLabel("al lugar"))
        fila.addWidget(self.hasta)
        fila.addSpacing(16)
        fila.addWidget(QLabel("Si empatan:"))
        fila.addWidget(self.desempate_nuevo)
        fila.addSpacing(16)
        fila.addWidget(boton("Crear liguilla", self.crear))
        fila.addStretch(1)

        self.tabla_clasificados = tabla(["Lugar", "Equipo", "PJ", "Pts", "DG"], estirar=1)
        self.nota_llave = QLabel(objectName="ayuda", wordWrap=True)

        columna = QVBoxLayout(panel)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.addLayout(fila)
        columna.addWidget(self.nota_llave)
        columna.addWidget(QLabel("Equipos que clasifican", objectName="seccion"))
        columna.addWidget(self.tabla_clasificados, 1)
        return panel

    def _crear_panel_llave(self) -> QWidget:
        panel = QWidget()
        self.desempate = _combo_desempate()
        self.desempate.activated.connect(self.cambiar_desempate)

        acciones = QHBoxLayout()
        acciones.addWidget(boton("Programar partido", self.programar, "secundario"))
        acciones.addWidget(boton("Capturar resultado", self.capturar))
        acciones.addWidget(boton("No se presentó", self.no_se_presento, "secundario"))
        acciones.addWidget(boton("Borrar resultado", self.borrar, "peligro"))
        acciones.addStretch(1)
        acciones.addWidget(QLabel("Si empatan:"))
        acciones.addWidget(self.desempate)
        acciones.addWidget(boton("Eliminar liguilla", self.eliminar, "peligro"))

        self.campeon = QLabel(objectName="campeon")
        self.campeon.setVisible(False)
        self.lienzo = QWidget(objectName="lienzoLlave")
        self.lienzo_fila = QHBoxLayout(self.lienzo)
        area = QScrollArea(frameShape=QFrame.Shape.NoFrame)
        area.setWidgetResizable(True)
        area.setWidget(self.lienzo)

        columna = QVBoxLayout(panel)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.addLayout(acciones)
        columna.addWidget(self.campeon)
        columna.addWidget(area, 1)
        return panel

    def showEvent(self, evento):
        super().showEvent(evento)
        self.filtros.refrescar()

    def refrescar(self):
        torneo, categoria = self.filtros.torneo_id, self.filtros.categoria_id
        actual = liguilla.obtener(self.conn, torneo, categoria) if torneo and categoria else None
        self.liguilla_id = actual["id"] if actual else None
        self.crear_panel.setVisible(actual is None)
        self.llave_panel.setVisible(actual is not None)
        if actual:
            self.aviso.setText(
                f"Clasificaron del lugar {actual['desde']} al {actual['hasta']}. "
                "Selecciona un partido de la llave. Cambiar «Si empatan» aplica a lo que se capture después."
            )
            self.desempate.setCurrentIndex(self.desempate.findData(actual["desempate"]))
            self._dibujar_llave()
        else:
            self._preparar_nueva()

    def _preparar_nueva(self):
        torneo, categoria = self.filtros.torneo_id, self.filtros.categoria_id
        total = 0
        if torneo and categoria:
            total = self.conn.execute(
                "SELECT COUNT(*) FROM equipos WHERE torneo_id = ? AND categoria_id = ?", (torneo, categoria)
            ).fetchone()[0]
        for control in (self.desde, self.hasta):
            control.blockSignals(True)
            control.setMaximum(max(total, 1))
        self.desde.setValue(1)
        self.hasta.setValue(min(total, 8) or 1)
        for control in (self.desde, self.hasta):
            control.blockSignals(False)
        if total < 2:
            self.aviso.setText("Registra al menos 2 equipos en esta categoría para crear su liguilla.")
        else:
            pendientes = liguilla.partidos_regulares_pendientes(self.conn, torneo, categoria)
            self.aviso.setText(
                f"Faltan {pendientes} partidos de la fase regular por capturar; la tabla aún puede cambiar."
                if pendientes
                else "La fase regular está completa. Elige el rango de lugares que clasifican."
            )
        self.refrescar_clasificados()

    def refrescar_clasificados(self):
        torneo, categoria = self.filtros.torneo_id, self.filtros.categoria_id
        try:
            lista = liguilla.clasificados(self.conn, torneo, categoria, self.desde.value(), self.hasta.value())
        except (ValueError, TypeError):
            llenar(self.tabla_clasificados, [])
            self.nota_llave.setText("Deben clasificar al menos 2 equipos.")
            return
        inicio = self.desde.value()
        llenar(
            self.tabla_clasificados,
            [
                (f.equipo_id, [inicio + i, f.nombre, f.pj, f.pts, f"{f.dg:+d}"])
                for i, f in enumerate(lista)
            ],
        )
        tamano = 2
        while tamano < len(lista):
            tamano *= 2
        directos = tamano - len(lista)
        self.nota_llave.setText(
            f"{len(lista)} equipos. Los {directos} mejores pasan directo a la siguiente ronda."
            if directos > 1
            else f"{len(lista)} equipos. El mejor lugar pasa directo a la siguiente ronda."
            if directos == 1
            else f"{len(lista)} equipos. Todos juegan desde la primera ronda."
        )

    def _dibujar_llave(self):
        while self.lienzo_fila.count():
            elemento = self.lienzo_fila.takeAt(0)
            widget = elemento.widget()
            if widget:
                # Se retira de inmediato para que no quede encimada mientras se destruye.
                widget.setParent(None)
                widget.deleteLater()
        vistas = liguilla.vista(self.conn, self.liguilla_id)
        self._partidos = {v.id: v.partido_id for v in vistas}
        if self._seleccion not in self._partidos:
            self._seleccion = None

        rondas: dict[int, list[liguilla.VistaLlave]] = {}
        for v in vistas:
            rondas.setdefault(v.numero_ronda, []).append(v)
        for numero in sorted(rondas):
            columna = QVBoxLayout()
            contenedor = QWidget()
            contenedor.setLayout(columna)
            columna.addWidget(QLabel(rondas[numero][0].ronda, objectName="seccion"))
            for v in rondas[numero]:
                columna.addStretch(1)
                tarjeta = QPushButton(texto_llave(v), objectName="llave", checkable=True)
                tarjeta.setEnabled(v.partido_id is not None)
                tarjeta.setChecked(v.id == self._seleccion)
                tarjeta.clicked.connect(lambda _=False, i=v.id: self._elegir(i))
                self._grupo.addButton(tarjeta)
                columna.addWidget(tarjeta)
            columna.addStretch(1)
            self.lienzo_fila.addWidget(contenedor)

        ganador = liguilla.campeon(self.conn, self.liguilla_id)
        self.campeon.setText(f"Campeón: {ganador}")
        self.campeon.setVisible(bool(ganador))

    def _elegir(self, llave_id: int):
        self._seleccion = llave_id

    def _partido_elegido(self) -> int | None:
        partido = self._partidos.get(self._seleccion)
        if partido is None:
            error(self, "Primero selecciona un partido de la llave.")
        return partido

    def crear(self):
        torneo, categoria = self.filtros.torneo_id, self.filtros.categoria_id
        if torneo is None:
            error(self, "Primero crea un torneo para esta liga en «Ligas y categorías».")
            return
        if categoria is None:
            error(self, "Primero crea una categoría para esta liga.")
            return
        pendientes = liguilla.partidos_regulares_pendientes(self.conn, torneo, categoria)
        if pendientes and not confirmar(
            self,
            f"Faltan {pendientes} partidos de la fase regular. La llave se arma con la tabla actual "
            "y no cambiará después. ¿Crear la liguilla de todos modos?",
        ):
            return
        try:
            liguilla.crear(
                self.conn, torneo, categoria, self.desde.value(), self.hasta.value(),
                self.desempate_nuevo.currentData(),
            )
        except ValueError as exc:
            error(self, str(exc))
            return
        self.refrescar()

    def programar(self):
        partido = self._partido_elegido()
        if partido is not None and editar_partido(self, self.conn, partido):
            self.refrescar()

    def capturar(self):
        partido = self._partido_elegido()
        if partido is not None and capturar_partido(self, self.conn, partido):
            self.refrescar()

    def no_se_presento(self):
        partido = self._partido_elegido()
        if partido is not None and marcar_no_presentado(self, self.conn, partido):
            self.refrescar()

    def borrar(self):
        partido = self._partido_elegido()
        if partido is not None and borrar_resultado(self, self.conn, partido):
            self.refrescar()

    def cambiar_desempate(self):
        if self.liguilla_id:
            liguilla.cambiar_desempate(self.conn, self.liguilla_id, self.desempate.currentData())
            info(self, "Listo. Se aplicará a los partidos que captures de ahora en adelante.")

    def eliminar(self):
        if not self.liguilla_id or not confirmar(
            self, "¿Eliminar esta liguilla y sus partidos? Podrás crearla de nuevo."
        ):
            return
        try:
            liguilla.eliminar(self.conn, self.liguilla_id)
        except ValueError as exc:
            error(self, str(exc))
            return
        self.refrescar()
