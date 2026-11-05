"""Página de cobros: montos del torneo, adeudos por equipo, pagos y recibos."""

import os
import sqlite3
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from .. import cobros, recibos
from .comun import boton, botones_dialogo, confirmar, error, id_seleccionado, llenar, tabla
from .filtros import FiltrosLiga
from .pagina_inicio import Tarjeta

MONTO_MAXIMO = 1_000_000


def _campo_monto(centavos: int = 0) -> QDoubleSpinBox:
    campo = QDoubleSpinBox(minimum=0, maximum=MONTO_MAXIMO, decimals=2, prefix="$ ")
    campo.setGroupSeparatorShown(True)
    campo.setValue(centavos / 100)
    return campo


def _fecha_corta(texto: str) -> str:
    return date.fromisoformat(texto).strftime("%d/%m/%Y")


class DialogoTarifas(QDialog):
    def __init__(self, padre, tarifas: list[cobros.Tarifa], torneo: str):
        super().__init__(padre)
        self.setWindowTitle("Montos del torneo")
        self.campos: dict[int, tuple[QDoubleSpinBox, QDoubleSpinBox]] = {}

        raiz = QVBoxLayout(self)
        raiz.addWidget(QLabel(torneo, objectName="seccion"))
        rejilla = QGridLayout()
        rejilla.addWidget(QLabel("Categoría"), 0, 0)
        rejilla.addWidget(QLabel("Arbitraje por partido, por equipo"), 0, 1)
        rejilla.addWidget(QLabel("Inscripción por equipo"), 0, 2)
        for i, t in enumerate(tarifas, start=1):
            arbitraje, inscripcion = _campo_monto(t.arbitraje), _campo_monto(t.inscripcion)
            arbitraje.setAccessibleName(f"Arbitraje de {t.categoria}")
            inscripcion.setAccessibleName(f"Inscripción de {t.categoria}")
            self.campos[t.categoria_id] = (arbitraje, inscripcion)
            rejilla.addWidget(QLabel(t.categoria), i, 0)
            rejilla.addWidget(arbitraje, i, 1)
            rejilla.addWidget(inscripcion, i, 2)
        raiz.addLayout(rejilla)

        self.aplicar = QCheckBox("Aplicar también a los cargos que todavía no tienen pagos", checked=True)
        raiz.addWidget(self.aplicar)
        raiz.addWidget(
            QLabel(
                "Con monto en cero no se generan cobros de ese tipo. Al poner un monto, se crean "
                "los cargos que faltaban. Los cargos con pagos nunca cambian.",
                objectName="ayuda", wordWrap=True,
            )
        )
        raiz.addWidget(botones_dialogo(self, self.accept))

    def valores(self) -> dict[int, tuple[int, int]]:
        return {
            c: (cobros.a_centavos(a.value()), cobros.a_centavos(i.value()))
            for c, (a, i) in self.campos.items()
        }


class DialogoPago(QDialog):
    def __init__(self, padre, equipo: str, deuda: int, sugerido: int):
        super().__init__(padre)
        self.setWindowTitle("Registrar pago")
        self.monto = _campo_monto(sugerido)
        self.monto.setMaximum(deuda / 100)
        self.fecha = QDateEdit(QDate.currentDate(), calendarPopup=True, displayFormat="dd/MM/yyyy")
        self.fecha.setMaximumDate(QDate.currentDate())
        self.nota = QLineEdit()
        self.nota.setPlaceholderText("Opcional, por ejemplo: transferencia")
        forma = QFormLayout(self)
        forma.addRow(QLabel(equipo, objectName="seccion"))
        forma.addRow(QLabel(f"Debe en total: {cobros.dinero(deuda)}"))
        forma.addRow("Monto:", self.monto)
        forma.addRow("Fecha:", self.fecha)
        forma.addRow("Nota:", self.nota)
        forma.addRow(
            QLabel(
                "Puede ser un abono. Se aplica primero al cargo seleccionado y lo que sobre, "
                "a los cargos más antiguos.",
                objectName="ayuda", wordWrap=True,
            )
        )
        forma.addRow(botones_dialogo(self, self._aceptar, "Registrar"))

    def _aceptar(self):
        if self.monto.value() <= 0:
            error(self, "Escribe un monto mayor a cero.")
            return
        self.accept()


class DialogoAjuste(QDialog):
    def __init__(self, padre, cargo: cobros.Cargo):
        super().__init__(padre)
        self.setWindowTitle("Ajustar monto")
        self.monto = _campo_monto(cargo.monto)
        forma = QFormLayout(self)
        forma.addRow(QLabel(f"{cargo.concepto} {cargo.detalle}".strip(), objectName="seccion"))
        forma.addRow("Monto:", self.monto)
        forma.addRow(
            QLabel(
                "Solo cambia este cargo. Déjalo en cero para perdonarlo.",
                objectName="ayuda", wordWrap=True,
            )
        )
        forma.addRow(botones_dialogo(self, self.accept))


class PaginaCobros(QWidget):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.setObjectName("pagina")
        self.conn = conn

        self.filtros = FiltrosLiga(conn, con_todas=True)
        self.filtros.cambiado.connect(self.refrescar)
        fila_filtros = QHBoxLayout()
        fila_filtros.addWidget(self.filtros, 1)
        fila_filtros.addWidget(boton("Montos del torneo", self.editar_tarifas, "secundario"))

        self.cargado = Tarjeta("Total de cargos")
        self.cobrado = Tarjeta("Cobrado")
        self.pendiente = Tarjeta("Pendiente")
        tarjetas = QHBoxLayout()
        for tarjeta in (self.cargado, self.cobrado, self.pendiente):
            tarjetas.addWidget(tarjeta)

        self.solo_adeudo = QCheckBox("Solo equipos con adeudo")
        self.solo_adeudo.toggled.connect(self.refrescar)
        self.equipos = tabla(["Equipo", "Categoría", "Cargos", "Pagado", "Saldo"], estirar=0)
        self.equipos.itemSelectionChanged.connect(self.refrescar_detalle)
        encabezado_equipos = QHBoxLayout()
        encabezado_equipos.addWidget(QLabel("Adeudos por equipo", objectName="seccion"))
        encabezado_equipos.addStretch(1)
        encabezado_equipos.addWidget(self.solo_adeudo)
        izquierda = QVBoxLayout()
        izquierda.addLayout(encabezado_equipos)
        izquierda.addWidget(self.equipos, 1)

        self.cargos = tabla(["Concepto", "Detalle", "Fecha", "Monto", "Pagado", "Saldo"], estirar=1)
        fila_cargos = QHBoxLayout()
        fila_cargos.addWidget(boton("Registrar pago", self.registrar_pago))
        fila_cargos.addWidget(boton("Ajustar monto", self.ajustar, "secundario"))
        fila_cargos.addStretch(1)

        self.pagos = tabla(["Folio", "Fecha", "Monto", "Nota", "Estado"], estirar=3)
        fila_pagos = QHBoxLayout()
        fila_pagos.addWidget(boton("Recibo PDF", self.recibo))
        fila_pagos.addWidget(boton("Anular pago", self.anular, "peligro"))
        fila_pagos.addStretch(1)

        derecha = QVBoxLayout()
        derecha.addWidget(QLabel("Cargos del equipo", objectName="seccion"))
        derecha.addWidget(self.cargos, 3)
        derecha.addLayout(fila_cargos)
        derecha.addWidget(QLabel("Pagos del equipo", objectName="seccion"))
        derecha.addWidget(self.pagos, 2)
        derecha.addLayout(fila_pagos)

        columnas = QHBoxLayout()
        columnas.addLayout(izquierda, 2)
        columnas.addLayout(derecha, 3)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.addWidget(QLabel("Cobros", objectName="titulo"))
        raiz.addLayout(fila_filtros)
        raiz.addLayout(tarjetas)
        raiz.addLayout(columnas, 1)
        self.refrescar()

    def showEvent(self, evento):
        super().showEvent(evento)
        self.filtros.refrescar()

    def refrescar(self):
        torneo, categoria = self.filtros.torneo_id, self.filtros.categoria_id
        if torneo is None:
            for t in (self.cargado, self.cobrado, self.pendiente):
                t.numero.setText(cobros.dinero(0))
            self.equipos.setRowCount(0)
            self.refrescar_detalle()
            return
        cobros.sincronizar_torneo(self.conn, torneo)
        total = cobros.resumen(self.conn, torneo, categoria)
        self.cargado.numero.setText(cobros.dinero(total.cargado))
        self.cobrado.numero.setText(cobros.dinero(total.cobrado))
        self.pendiente.numero.setText(cobros.dinero(total.pendiente))
        lista = cobros.adeudos(self.conn, torneo, categoria)
        if self.solo_adeudo.isChecked():
            lista = [a for a in lista if a.saldo > 0]
        llenar(
            self.equipos,
            [
                (
                    a.equipo_id,
                    [a.equipo, a.categoria, cobros.dinero(a.cargos), cobros.dinero(a.pagado), cobros.dinero(a.saldo)],
                )
                for a in lista
            ],
        )
        self.refrescar_detalle()

    def refrescar_detalle(self):
        equipo = id_seleccionado(self.equipos)
        cargos = cobros.cargos_de_equipo(self.conn, equipo) if equipo else []
        llenar(
            self.cargos,
            [
                (
                    c.id,
                    [
                        c.concepto, c.detalle, _fecha_corta(c.fecha), cobros.dinero(c.monto),
                        cobros.dinero(c.pagado), cobros.dinero(c.saldo),
                    ],
                )
                for c in cargos
            ],
        )
        pagos = cobros.pagos_de_equipo(self.conn, equipo) if equipo else []
        llenar(
            self.pagos,
            [
                (
                    p["id"],
                    [
                        f"{p['id']:05d}", _fecha_corta(p["fecha"]), cobros.dinero(p["monto"]), p["nota"],
                        "Anulado" if p["anulado"] else "Vigente",
                    ],
                )
                for p in pagos
            ],
        )

    def editar_tarifas(self):
        torneo = self.filtros.torneo_id
        if torneo is None:
            error(self, "Primero crea un torneo para esta liga en «Ligas y categorías».")
            return
        lista = cobros.tarifas(self.conn, torneo)
        if not lista:
            error(self, "Esta liga todavía no tiene categorías.")
            return
        dialogo = DialogoTarifas(self, lista, self.filtros.torneo.currentText())
        if dialogo.exec():
            cobros.guardar_tarifas(self.conn, torneo, dialogo.valores(), dialogo.aplicar.isChecked())
            self.refrescar()

    def _equipo(self) -> int | None:
        equipo = id_seleccionado(self.equipos)
        if equipo is None:
            error(self, "Primero selecciona un equipo.")
        return equipo

    def registrar_pago(self):
        equipo = self._equipo()
        if equipo is None:
            return
        cargos = cobros.cargos_de_equipo(self.conn, equipo)
        deuda = sum(c.saldo for c in cargos if c.saldo > 0)
        if deuda == 0:
            error(self, "Este equipo no tiene adeudos.")
            return
        primero = id_seleccionado(self.cargos)
        elegido = next((c for c in cargos if c.id == primero and c.saldo > 0), None)
        dialogo = DialogoPago(
            self, self.equipos.item(self.equipos.currentRow(), 0).text(), deuda,
            elegido.saldo if elegido else deuda,
        )
        if not dialogo.exec():
            return
        try:
            cobros.registrar_pago(
                self.conn, equipo, cobros.a_centavos(dialogo.monto.value()),
                dialogo.fecha.date().toPython(), dialogo.nota.text(), primero,
            )
        except ValueError as exc:
            error(self, str(exc))
            return
        self.refrescar()

    def ajustar(self):
        equipo = self._equipo()
        if equipo is None:
            return
        cargo_id = id_seleccionado(self.cargos)
        cargo = next((c for c in cobros.cargos_de_equipo(self.conn, equipo) if c.id == cargo_id), None)
        if cargo is None:
            error(self, "Primero selecciona un cargo.")
            return
        dialogo = DialogoAjuste(self, cargo)
        if not dialogo.exec():
            return
        try:
            cobros.ajustar_cargo(self.conn, cargo.id, cobros.a_centavos(dialogo.monto.value()))
        except ValueError as exc:
            error(self, str(exc))
            return
        self.refrescar()

    def _pago(self):
        folio = id_seleccionado(self.pagos)
        if folio is None:
            error(self, "Primero selecciona un pago.")
            return None
        return self.conn.execute("SELECT * FROM pagos WHERE id = ?", (folio,)).fetchone()

    def recibo(self):
        pago = self._pago()
        if pago is None:
            return
        if pago["anulado"]:
            error(self, "Este pago está anulado; no se puede generar su recibo.")
            return
        sugerido = str(Path.home() / f"Recibo {pago['id']:05d}.pdf")
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar recibo", sugerido, "PDF (*.pdf)")
        if not ruta:
            return
        try:
            recibos.generar(self.conn, pago["id"], ruta)
        except PermissionError:
            error(self, "No se pudo guardar: el archivo está abierto en otro programa.")
            return
        os.startfile(ruta)

    def anular(self):
        pago = self._pago()
        if pago is None:
            return
        if pago["anulado"]:
            error(self, "Este pago ya está anulado.")
            return
        if confirmar(
            self,
            f"¿Anular el pago con folio {pago['id']:05d} por {cobros.dinero(pago['monto'])}? "
            "Lo que cubría volverá a quedar pendiente.",
        ):
            cobros.anular_pago(self.conn, pago["id"])
            self.refrescar()
