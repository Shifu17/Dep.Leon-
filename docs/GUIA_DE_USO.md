# Guía de uso

Este es el recorrido normal de un torneo, de principio a fin. Cada paso depende del anterior, así que
conviene seguirlos en orden la primera vez.

**Contenido**

1. [Entrar al programa](#1-entrar-al-programa)
2. [Preparar la liga y el torneo](#2-preparar-la-liga-y-el-torneo)
3. [Registrar equipos y jugadores](#3-registrar-equipos-y-jugadores)
4. [Generar el rol de juegos](#4-generar-el-rol-de-juegos)
5. [Capturar resultados](#5-capturar-resultados)
6. [Consultar estadísticas](#6-consultar-estadísticas)
7. [Jugar la liguilla](#7-jugar-la-liguilla)
8. [Llevar los cobros](#8-llevar-los-cobros)
9. [Sacar reportes](#9-sacar-reportes)
10. [Respaldos y actualizaciones](#10-respaldos-y-actualizaciones)
11. [Si algo no sale](#11-si-algo-no-sale)

## 1. Entrar al programa

![Pantalla de inicio de sesión](img/inicio_de_sesion.png)

La primera vez, crea tu usuario y contraseña. El programa te mostrará un **código de recuperación**:
anótalo y guárdalo fuera de la computadora. Si olvidas la contraseña, es la única forma de volver a
entrar, y no se puede consultar después.

Después de 5 intentos fallidos, el programa pide esperar 30 segundos. Puedes cambiar la contraseña o
cerrar sesión en **Configuración**.

## 2. Preparar la liga y el torneo

Entra a **Ligas y categorías** y selecciona una liga:

- **Ligas:** ya vienen creadas Femenil, Libre Martes, Libre Miércoles, Libre Jueves, Infantil y Fut 11.
  Puedes editarlas o agregar otras.
- **Categorías:** las infantiles ya vienen cargadas, de 2009-2010 a 2019-2020. Para las demás ligas,
  agrega las que uses. Marca **Sin límite de edad** en la categoría libre.
- **Torneos:** agrega uno, por ejemplo «Copa de Verano». **Este paso es necesario** antes de registrar
  equipos.

## 3. Registrar equipos y jugadores

Entra a **Equipos y jugadores** y elige liga y torneo. Hay dos formas de registrar jugadores.

### Desde Excel (recomendado para muchos jugadores)

1. Pulsa **Descargar plantilla de Excel**. La hoja **Instrucciones** explica cómo llenarla.
2. Captura un jugador por renglón en la hoja **Jugadores**.
3. Si hay fotos, ponlas en la misma carpeta que el Excel o en una subcarpeta `fotos`, y escribe el nombre
   del archivo en la columna **Foto**.
4. Guarda, cierra el archivo y pulsa **Importar Excel**.
5. Revisa la vista previa: los renglones con error salen en rojo y no se registran. Corrígelos en Excel y
   vuelve a importar; los jugadores ya registrados se actualizan, no se duplican.

Los equipos que no existan se crean solos. El programa revisa que la fecha de nacimiento corresponda a
la categoría y que no se repita el número de playera en un equipo.

### A mano

Agrega el equipo y, con el equipo seleccionado, agrega cada jugador.

### Otras acciones del equipo

- **Credenciales PDF:** genera las credenciales del equipo seleccionado, 8 por hoja.
- **Disponibilidad:** indica qué días y horas puede jugar. Si no marcas nada, puede jugar siempre.

## 4. Generar el rol de juegos

Entra a **Rol de juegos**, elige el torneo y pulsa **Generar rol**. Después:

1. Marca las categorías. Cada una necesita al menos 2 equipos.
2. Marca los días de juego y el horario de cada día.
3. Indica desde qué fecha empezar, cada cuánto hay un partido (50 minutos por defecto) y qué canchas usar.
4. Si juegan ida y vuelta, marca esa opción.

El programa arma las jornadas y:

- Pone cada jornada en una semana y reparte los partidos entre los días de juego.
- Respeta la disponibilidad de cada equipo.
- Evita empalmes, también con otras ligas. Un partido de Fut 11 ocupa todo el terreno.
- Muestra quién descansa cuando el número de equipos es impar.

Si dos equipos no coinciden en ningún horario, te avisa y deja su partido **sin fecha** para que lo
programes a mano.

Después puedes **Agregar partido**, **Editar o reprogramar**, **Posponer** o **Eliminar**. Un partido
pospuesto o sin coincidencia de horarios aparece como **Sin fecha** hasta que le asignes una.

> **Antes de generar de nuevo:** se borra el rol anterior de esas categorías, incluidos los cambios a mano
> y los partidos pospuestos. El programa pide confirmar. Si una categoría ya tiene resultados o liguilla,
> no se puede generar de nuevo.

## 5. Capturar resultados

En **Resultados**, selecciona un partido y pulsa **Capturar resultado**, o haz doble clic en él.

- **Marcador y goleadores:** los goleadores son opcionales. Puede haber goles sin jugador, como un
  autogol, pero no más goles asignados que los del marcador.
- **Corregir:** vuelve a capturar el partido. **Borrar resultado** lo regresa a por jugar.

Si un equipo no llegó, pulsa **No se presentó** y elige:

- **Dar por default:** el equipo presente gana 3-0 (configurable). Indicas quién paga el arbitraje: el
  ausente, el presente, ambos o ninguno.
- **Posponer:** el partido queda pendiente de nueva fecha y no genera cobro.

## 6. Consultar estadísticas

En **Estadísticas**, elige torneo y categoría para ver:

- **Clasificación:** PJ, PG, PE, PP, GF, GC, DG y Pts.
- **Goleadores**.
- **Portería menos goleada**, por equipo.

Con **Reglas de puntos** puedes cambiar los puntos por victoria, empate y derrota, y los goles de un
default. El desempate va por diferencia de goles, goles a favor y resultado entre los empatados.

## 7. Jugar la liguilla

![Llave de liguilla](img/liguilla.png)

En **Liguilla**, elige torneo y categoría:

1. Indica el rango: **Clasifican del lugar X al lugar Y**.
2. Elige **Si empatan**: penales o mejor lugar en la tabla.
3. Pulsa **Crear liguilla**.
4. Selecciona cada partido de la llave para programarlo y capturar su resultado.

Si los clasificados no completan 2, 4, 8 o 16 equipos, los mejores lugares pasan directo a la siguiente
ronda. El ganador avanza solo hasta llegar al campeón.

Ten en cuenta que:

- La llave usa la tabla del momento y ya no cambia sola. Si faltan partidos regulares, el programa avisa.
- La liguilla **no suma a la tabla regular**, pero sí al goleo y a los cobros de arbitraje.
- No se puede cambiar quién avanza si la siguiente ronda ya tiene resultado. Primero hay que borrarlo.

## 8. Llevar los cobros

En **Cobros**, elige el torneo:

1. Pulsa **Montos del torneo** y escribe el arbitraje y la inscripción de cada categoría. Con un monto en
   cero no se cobra ese concepto.
2. Selecciona un equipo para ver sus cargos.
3. Pulsa **Registrar pago**. Puede ser un abono: se aplica primero al cargo seleccionado y lo que sobre, al
   más antiguo.
4. Selecciona el pago y pulsa **Recibo PDF** para generar su recibo.

**Cuándo se cobra cada cosa:**

- **Inscripción:** una vez por equipo y torneo.
- **Arbitraje:** a cada equipo **al capturar el resultado**, nunca antes. Los partidos pospuestos no se
  cobran.

**Correcciones:**

- **Ajustar monto** cambia un solo cargo. En cero, lo perdona.
- **Anular pago** deja el folio marcado como anulado, y lo que cubría vuelve a quedar pendiente.
- Si pones un monto después de jugar partidos, esos partidos se cobran al ponerlo.
- Un arbitraje con pagos protege su partido: para borrar el resultado, primero hay que anular el pago.

## 9. Sacar reportes

![Rol de juegos como imagen](img/reporte_rol.png)

En **Reportes**, elige el reporte y revisa la vista previa:

| Reporte | PDF | Imagen para WhatsApp |
|---|---|---|
| Rol de juegos (una fecha o todas) | Sí | Sí |
| Tabla de posiciones | Sí | Sí |
| Llave de liguilla | Sí | Sí |
| Goleadores y portería menos goleada | Sí | No |
| Adeudos | Sí | No |

**Copiar imagen** te deja pegarla directo en WhatsApp sin guardar un archivo.

## 10. Respaldos y actualizaciones

Ambas opciones están en **Configuración**.

**Respaldos**

- **Crear respaldo** guarda un archivo `.zip` con todos los datos y las fotos. Hazlo seguido y guarda una
  copia fuera de la computadora, por ejemplo en una USB.
- Cuida ese archivo: **no lleva contraseña** y contiene datos de jugadores.
- **Restaurar respaldo** reemplaza toda la información actual, pero conserva tu cuenta.

**Actualizaciones**

Con internet, el programa revisa si hay una versión nueva y te avisa. Solo se instala si aceptas, y antes
crea un respaldo automático. Sin internet no ocurre nada y todo sigue funcionando.

## 11. Si algo no sale

| Situación | Qué hacer |
|---|---|
| «Windows protegió su PC» al abrir | Pulsa **Más información** y luego **Ejecutar de todas formas**. El programa no tiene firma digital. |
| Olvidé mi contraseña | Pulsa **Olvidé mi contraseña** y escribe tu código de recuperación. |
| Perdí también el código | El programa no ofrece otra forma de entrar. Pide ayuda técnica y conserva tu carpeta de datos y tus respaldos. |
| No me deja guardar la plantilla o importarla | Cierra el archivo en Excel e inténtalo de nuevo. |
| Un renglón del Excel sale con error | Lee el motivo en la vista previa, corrígelo en Excel y vuelve a importar. |
| No me deja generar el rol | Revisa que la categoría tenga 2 equipos o más y que no tenga resultados ni liguilla. |
| Un partido no aparece para capturar | Revisa que tenga fecha. Los partidos sin fecha se programan en **Rol de juegos**. |
| No me deja eliminar un equipo | Tiene partidos, un lugar en la liguilla o pagos registrados. |
