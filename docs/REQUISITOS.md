# Deportivo León: requisitos

Programa de escritorio para Windows, en Python y en español, para administrarlo en una sola
computadora, con una cuenta de acceso y código de recuperación.

## Estructura de la liga

| Liga | Día (editable) | Modalidad |
|---|---|---|
| Femenil | Lunes | Fut 7 |
| Libre Martes | Martes | Fut 7 |
| Libre Miércoles | Miércoles | Fut 7 |
| Libre Jueves | Jueves | Fut 7 |
| Infantil | Viernes y sábado | Fut 7 |
| Fut 11 | Domingo | Fut 11 |

- Canchas: Fut 7 usa Cancha 1 y Cancha 2. Fut 11 se juega en **el mismo terreno**, así que un
  partido de Fut 11 ocupa ambas canchas y el rol debe evitar empalmes entre modalidades.
- Categorías infantiles: 2009-2010, 2011-2012, 2013-2014, 2015-2016, 2017-2018, 2019-2020.
- Las demás categorías (como la libre) se crean desde el programa.

## Reglas de competencia

- Fase regular todos contra todos, seguida de liguilla de eliminación directa.
- Puntos: 3 por victoria, 1 por empate, 0 por derrota (configurable).
- Desempate: diferencia de goles, goles a favor y resultado entre ambos equipos.
- La liguilla no suma a la tabla regular, pero sí al goleo.
- Una categoría con resultados no se puede generar de nuevo, para no perderlos.
- Portero menos goleado: se lleva **por equipo** (goles recibidos); no se elige portero por partido.
- Horario de referencia del rol infantil: partidos cada 50 minutos desde las 9:00.

## Partido no presentado

Al marcar que un equipo no se presentó, quien captura elige una de estas opciones:

1. **Posponer** el partido, que queda pendiente de reprogramar.
2. **Dar el partido por default**, indicando **qué equipo paga** el arbitraje.

## Cobros

- Inscripción por equipo y por torneo.
- Arbitraje por equipo y por partido, con monto por categoría.
- Abonos parciales, adeudos por equipo y recibo en PDF.

## Reportes

PDF para imprimir, imagen para WhatsApp y recibos de pago. El rol de juegos usa las columnas de la
hoja actual de la liga: Hora, Equipo, Equipo, Categoría y Cancha.

## Fuera de alcance

Tarjetas, sanciones, asistencia, exportación a Excel de tablas, varias computadoras y varios
usuarios.

## Etapas

1. Ligas, categorías, torneos, equipos y jugadores, con importación desde Excel, credenciales,
   respaldo y actualizaciones. **Hecha.**
2. Rol de juegos: generación automática por categoría, descansos, control de empalmes, edición,
   reprogramación y partidos pospuestos. **Hecha.** La hoja del rol en PDF e imagen llega en la
   etapa 6.
3. Resultados y estadísticas: marcadores, goleadores, default con equipo que paga, clasificación
   y portería menos goleada por equipo. **Hecha.** El cobro de lo que indica el default llega en
   la etapa 4.
4. Cobros.
5. Liguilla.
6. Reportes.
