# Reglas de Negocio — Métricas de Logística

Este documento es la **fuente de verdad** de cómo se calcula cada métrica.
Cuando una definición cambie o aparezca un caso nuevo no contemplado, se
actualiza acá primero y después se refleja en los tres lugares que
implementan estas reglas por separado (no comparten código entre sí):
- `scripts/generar_reporte.py`, sección `CONFIG` al inicio del archivo.
- `dashboard/dashboard_logistica.html`, sección "Reglas de negocio" al
  inicio del `<script>`.
- `scripts/publicar_firestore.py` (automatización diaria), que reutiliza
  `ESTADOS_ENTREGA_EFECTIVA`/`ESTADOS_CANCELADO` de `generar_reporte.py` pero
  calcula las franjas horarias y los agregados por su cuenta, replicando la
  misma lógica que el dashboard.

Última actualización: 2026-10-24.

---

## 1. Entrega efectiva

**Definición:** un envío se considera "entregado con éxito" si su `Estado` es
uno de los siguientes:

- `Entregado`
- `Entregado 2DA visita`

**Excluye** (por ahora, hasta que se definan): `Retirado`, `Nadie`,
`Nadie 2DA visita`. Estos quedan clasificados como "otros / en curso" en los
reportes — no suman ni restan en el % de efectividad hasta que se decida
dónde van.

**`A retirar` se excluye también, pero del *denominador*, no solo del
numerador** (agregado 2026-09-04): son envíos que todavía no llegaron al
depósito, así que no corresponde contarlos en el universo de envíos
gestionados para medir efectividad — inflarían artificialmente el total sin
haber tenido chance de ser entregados todavía.

**Fórmula:**
```
% Entregas efectivas = (envíos con Estado en {Entregado, Entregado 2DA visita}) / (total de envíos − envíos en A retirar) × 100
```

---

## 2. Entregas antes de las 21:00 hs

**Definición:** de las entregas efectivas (regla #1), se considera "entregada
antes de las 21hs" cuando el timestamp de `Fecha estado` tiene hora **menor a
21:00**.

**Timestamp usado:** `Fecha estado` (la fecha/hora en que el sistema registró
el último cambio de estado). Se eligió esta columna porque, para los envíos en
estado `Entregado`, corresponde al momento real en que se marcó la entrega —
se verificó contra la distribución horaria de entregas del archivo de muestra
y el patrón es consistente con horarios de reparto reales (pico entre 18 y
21hs).

**No se usa** `Fecha de asignación` (es cuándo se le dio el envío al chofer,
no cuándo lo entregó) ni `Fecha MercadoPacks` (es de ingreso al sistema, no
de entrega).

**Fórmula:**
```
% Entregas antes de 21hs = (entregas efectivas con hora(Fecha estado) < 21) / (total de entregas efectivas) × 100
```

> Se reporta también como % sobre el total de envíos, para tener ambas
> lecturas (de las entregadas cuántas llegaron a horario, y del total
> gestionado cuántas llegaron a horario).

---

## 3. Cancelados

**Definición:** un envío se considera "cancelado" si su `Estado` es uno de
los siguientes:

- `Cancelado`
- `Rechazado por el comprador`

**Fórmula:**
```
% Cancelados = (envíos con Estado en {Cancelado, Rechazado por el comprador}) / (total de envíos) × 100
```

---

## 4. Efectividad por chofer (`Cadete`)

**Definición:** para cada chofer, se calcula el % de entregas efectivas
(regla #1) sobre el total de envíos que tuvo asignados.

**Fórmula:**
```
% Efectividad chofer = (entregas efectivas del chofer) / (total de envíos asignados al chofer) × 100
```

**Reglas adicionales:**

- **Envíos sin chofer asignado** (`Cadete` vacío) se excluyen del ranking por
  chofer — no se le puede atribuir efectividad a nadie. Esto pasa
  principalmente en envíos `A retirar` (el cliente retira en sucursal, no
  hay reparto) y en algunos `Entregado` que no registraron cadete. Estos
  casos se muestran aparte en el reporte como "sin chofer asignado", no se
  ocultan.
- **Muestra chica:** el reporte marca con una nota los choferes con menos de
  **5 envíos** en el período, porque un % de efectividad sobre pocos casos
  no es representativo (ej. 1 de 2 = 50% no es comparable con 40 de 50 =
  80%). No se excluyen del reporte, solo se señalan.
- Cancelaciones (regla #3) restan efectividad igual que cualquier estado que
  no sea entrega efectiva — no hay excepción especial todavía para
  cancelaciones no atribuibles al chofer (ej. el cliente se arrepintió antes
  de que el chofer saliera a repartir). **Pendiente de definir** si estas
  deben excluirse del denominador del chofer.

---

## 5. A qué día pertenece cada envío (para navegar por fechas en el dashboard)

Un mismo archivo exportado puede traer envíos que técnicamente "avanzan" en
días distintos (por ejemplo, uno que entró al sistema el 31/08 pero se marcó
`Entregado` recién el 01/09 a la madrugada). Para que el dashboard pueda
mostrar "las métricas del día X" de forma consistente, cada envío se asigna
al día que indica su columna **`Fecha MercadoPacks`** (el día en que el
envío entró al sistema de logística) — no el día en que cambió de estado.

Esto significa que un envío que entró el 31/08 pero se entregó el 01/09 de
madrugada **cuenta para las métricas del 31/08** (es el lote de ese día),
aunque el chequeo de "antes de las 21hs" siga mirando la hora real de
`Fecha estado` de ese envío en particular.

**Ventana de repaso (agregada 2026-09-17):** el caso de arriba (entrega la
madrugada siguiente) se resuelve solo, pero hay un caso más largo que no:
un envío puede entrar el día X y no entregarse hasta 2 o 3 días después
(ej. entra el 07/09, se entrega el 10/09). Como la descarga automática
filtra por `Fecha MercadoPacks`, ese envío ya se contó en el **total** del
07/09 desde el primer momento — pero si la automatización solo descargara
y "cerrara" cada día una única vez, su entrega del 10/09 nunca se reflejaría
en la efectividad del 07/09 (quedaría como no entregado para siempre, aunque
LightData sí muestre la entrega al consultarlo más tarde).

Por eso la corrida de cierre de las 00hs (ver README, sección de
automatización) no solo descarga "ayer": vuelve a descargar y a recalcular
los **últimos 3 días** cada vez, no solo el que acaba de cerrar. Así, una
entrega que llega 1 o 2 días tarde se termina reflejando en el día de origen
que le corresponde según esta regla, sin esperar un backfill manual. Una
entrega que tarda más de 3 días en resolverse sigue quedando fuera de este
repaso automático — para esos casos hay que backfillear el día a mano (ver
input `fecha` del workflow).

El export de LightData trae, al final del archivo, una fila de totales
(una suma de la columna `Precio`) que **no es un envío real** y no tiene
`ID (Interno)`. Cualquier procesamiento debe descartar toda fila sin
`ID (Interno)` antes de contar — no alcanza con descartar solo las filas
completamente vacías, porque esta fila de totales sí tiene un valor cargado.
(Se detectó este caso el 2026-09-01 al construir el dashboard; el script
`generar_reporte.py` fue corregido para excluirla también.)

## 7. Pendiente de definir (backlog de reglas)

Estos puntos quedaron abiertos en esta primera versión. Se van resolviendo a
medida que se necesiten para un reporte concreto:

- [ ] ¿Dónde clasificar `Retirado`, `Nadie` y `Nadie 2DA visita`? (¿cuentan
      como entrega efectiva, como cancelado, o como una tercera categoría
      propia con su propio %?)
- [ ] ¿Las cancelaciones donde el chofer nunca llegó a salir a reparto
      (cancelado por el cliente antes de asignación) deben excluirse del
      cálculo de efectividad del chofer?
- [ ] ¿Se necesita una métrica de tiempos (ej. tiempo entre `Fecha de
      asignación` y `Fecha estado`) además del corte de las 21hs?
- [ ] ¿Cómo tratar los envíos con `Método de envío` vacío (~4% de los casos)?
- [ ] Estandarizar `Logistica Inversa` si en algún momento se necesita medir
      volumen de cambios/devoluciones.

---

## 8. Franjas horarias de entrega (semáforo de puntualidad)

A partir de esta versión, además del corte binario "antes/después de las
21hs", el dashboard mide 4 franjas sobre las **entregas efectivas**, según
la hora de `Fecha estado`:

| Franja | Rango | Color |
|---|---|---|
| Antes de las 21:00 | hora < 21 | 🟢 Verde |
| Entre las 21 y 22hs | hora = 21 | 🟡 Amarillo |
| Entre las 22 y 23hs | hora = 22 | 🔴 Rojo |
| Después de las 23hs | hora ≥ 23 | 🔴 Rojo oscuro |

Estas franjas se calculan y se guardan a 3 niveles en cada snapshot diario:
global, por zona y por chofer — lo que permite que el dashboard filtre de
forma interactiva (ver punto 9). Estos 3 niveles siguen siendo **solo sobre
entregas efectivas** (regla #1): es el criterio que se usa para las tarjetas
de KPI, el gráfico por zona y el ranking de choferes.

**Excepción — cruce por estado:** la tabla "Cruce por hora de entrega" del
dashboard sí desglosa **todos los valores de `Estado`** que aparezcan en el
archivo (no solo `Entregado` / `Entregado 2DA visita`), agrupando por la hora
de `Fecha estado` de cada uno — así se puede ver, por ejemplo, a qué hora se
concentran los `reprogramado por meli` o los `Cancelado` del día. Esta tabla
es la única vista que no se limita a entregas efectivas; el resto de las
métricas de franja horaria (KPI, por zona, por chofer) siguen sin incluir
estados que no sean entrega efectiva.

**Nota de calidad de dato conocida:** la franja se asigna solo mirando la
hora del timestamp, sin importar si la entrega ocurrió al día siguiente del
que se le asignó el envío (por ejemplo, un envío que entró al sistema el
31/08 pero se entregó el 01/09 a las 08:00 cuenta como "antes de las 21hs",
porque hora=8 < 21). Es una simplificación heredada de cómo ya funcionaba el
corte de las 21hs desde la primera versión; no se resolvió porque son pocos
casos y cambiar el criterio ahora rompería la comparación con reportes
anteriores. Si en algún momento se vuelve relevante (por ejemplo, si crece
el volumen de entregas que cruzan la medianoche), hay que decidir y
documentar acá cómo tratarlas antes de tocar el código.

## 9. Filtros interactivos del dashboard

El dashboard permite hacer click en una zona, en una franja horaria o en un
chofer del ranking para filtrar el resto del panel. Reglas:

- **Zona** y **chofer** son mutuamente excluyentes: elegir uno limpia el
  otro. No se guarda el cruce exacto zona+chofer (cuánto entregó tal chofer
  en tal zona con tal desglose horario), así que no tendría sentido
  combinarlos con precisión.
- **Franja horaria** sí se puede combinar con zona o con chofer, porque las
  tres vistas (global, por zona, por chofer) guardan su propio desglose de
  las 4 franjas.
- La tabla "por estado" (todos los valores de `Estado` del archivo, no solo
  entrega efectiva — ver punto 8) que cruza con las franjas horarias es
  **siempre global**: no se filtra por zona ni por chofer, porque ese cruce
  de 3 dimensiones no se guarda (sería demasiado dato para lo que aporta).
  Se avisa esto mismo en el pie de esa tabla.
- Cuando el filtro de zona está activo, el ranking de choferes se filtra a
  los que tuvieron algún envío en esa zona, pero sus métricas (efectividad,
  % antes de 21hs, etc.) siguen siendo sobre el **total** de ese chofer, no
  solo sobre esa zona — se aclara con una nota arriba de la tabla.

## 10. Colores: marca vs. semáforo de puntualidad

A pedido explícito, se separaron dos paletas que no deben mezclarse:

- **Marca (MP):** dorado `#f6be05` + negro, tomado directamente del logo.
  Se usa solo para elementos de interfaz (botones, navegación, acentos) —
  nunca para indicar si algo está bien o mal.
- **Semáforo de puntualidad:** verde/amarillo/rojo/rojo oscuro, según la
  franja horaria de la entrega (ver punto 8). Se usa en el gráfico de
  entregas por hora, el cruce por franja horaria, y el gráfico por zona.

Esto es intencional: si el dorado de marca también significara "alerta", se
prestaría a confusión entre "esto es un botón" y "esto está tardando".

## 11. Detalle de envíos por chofer

Al seleccionar un chofer en el ranking, el dashboard muestra además el
detalle fila por fila de sus envíos del período (tracking, cliente,
localidad, zona, estado, hora de entrega).

**Decisión de privacidad (2026-09-17):** este detalle **no incluye
`Dirección` ni `CP`** (el domicilio exacto del destinatario) — solo
`Localidad` (nivel ciudad/partido). La razón es que las reglas de Firestore
del proyecto están abiertas a propósito (lectura/escritura sin login, ver
README) porque hasta ahora solo se guardaban métricas agregadas, nunca
datos personales. Guardar el domicilio exacto ahí lo expondría
públicamente a cualquiera que abra el dashboard (la config de Firebase
está embebida en el HTML público). Si en algún momento se necesita el
domicilio exacto en el dashboard, hay que agregar autenticación primero —
no guardarlo en la base abierta como está hoy.

`Nombre Fantasia` (el cliente/cuenta comercial, no el destinatario) y
`Fecha estado` (de donde sale la hora de entrega) no tienen este problema:
no son datos personales de una persona física.

## 12. Indicadores estilo Mercado Libre ("Mis métricas")

Fila de 6 tarjetas chicas arriba de los KPIs principales, pedida para
replicar el panel "Mis métricas" que Mercado Libre comparte con los
transportistas. Se calculan enteramente a partir de `porEstadoHora`
(desglose por estado × franja horaria, ya guardado en cada snapshot diario
desde antes — ver sección 8), así que no hace falta ningún cambio en la
descarga ni en la publicación.

**Importante — son siempre GLOBALES:** igual que la tabla "Cruce por hora
de entrega" (sección 8), estos indicadores NO respetan el filtro de
zona/chofer activo, porque `porEstadoHora` no se guarda con ese cruce. Usan
el agregado completo del período (`agg`), no el `scope` filtrado.

Cada tarjeta muestra un valor principal (grande) y, debajo, el desglose
numérico que lo compone — cada número junto a su "de TOTAL" para no tener
que adivinar la base de comparación (ajuste pedido el 2026-10-16). Un ícono
"i" en cada título muestra la fórmula completa al pasar el mouse, y el
bloque de definiciones fijo que antes estaba siempre visible al pie de
página pasó a un link colapsable ("ⓘ Cómo se calculan estas métricas").

Definiciones (TOTAL = total de envíos del período, sin excluir "A retirar"
salvo que se diga lo contrario):

1. **Entregas Efectivas** (2026-10-23, antes "Envíos correctos") — % =
   (`Entregado` + `Entregado 2DA visita`, sin restringir por hora) /
   (TOTAL − "A retirar"). Mismo criterio que el viejo KPI "Entregas
   efectivas" que este panel reemplazó. Debajo, el número de `Entregado` y
   de `Entregado 2DA visita` por separado.
2. **Entregas Pre 21** (2026-10-23: pasó a tener un % como protagonista,
   igual que "Entregas Post 21") — % = `Entregado` antes de 21hs / TOTAL.
   Debajo, el número de `Entregado` y de `Entregado 2DA visita` antes de
   21hs, por separado.
3. **Entregas post 21** — % = `Entregado` después de 21hs / TOTAL (el % no
   incluye "2DA visita", solo el desglose numérico la muestra aparte).
   Números: `Entregado` después de 21hs, y `Entregado 2DA visita` después
   de 21hs.
4. **Envíos incorrectos** — % = (TOTAL − Entregado antes de 21hs) / TOTAL.
   Es decir, todo lo que no sea "Entregado antes de 21hs" cuenta como
   incorrecto, incluida una entrega real pero tardía (mismo criterio desde
   que se creó esta tarjeta, no cambió con el punto 1).
5. **Reprogramado post 21** — % = (`reprogramado por meli` +
   `reprogramado por comprador`, después de 21hs) / TOTAL. Los nombres de
   estado van en minúsculas tal cual los exporta LightData (inconsistencia
   real del export, no un error de tipeo). `reprogramado por comprador`
   nunca apareció todavía en los datos reales (43 días de historial
   revisados el 2026-10-15) pero se incluye igual porque es un estado
   válido de LightData.
6. **Demora** — % = (todo estado que NO sea `Entregado` ni `Entregado 2DA
   visita`, sumado después de 21hs) / TOTAL. Por diseño puede solaparse
   con el punto 5 (un `reprogramado por meli` post-21 cuenta en las dos
   tarjetas) — son tarjetas independientes, no una partición exhaustiva.

### Pestañas de reportes (2026-10-16)

"Entregas por hora", "Cruce por hora de entrega", "Por zona" y "Ranking de
choferes" dejaron de mostrarse todos apilados — ahora son 4 pestañas y se
ve una a la vez. Internamente se sigue calculando todo igual; lo único que
cambia es que el gráfico SVG activo se vuelve a dibujar al cambiar de
pestaña (si se dibuja con el contenedor oculto, mide ancho/alto 0 y queda
mal escalado para siempre — ver comentario de `aplicarReportTab()` en el
dashboard).

### Tema visual claro (2026-10-23)

El dashboard pasó de fondo oscuro a fondo claro (gris muy clarito de
página, tarjetas blancas) con la marca (dorado `#F6BE05` + casi negro) para
título, bordes, botones y estados activos. El semáforo de puntualidad
(verde/amarillo/rojo/rojo oscuro, sección 8) se mantuvo exactamente igual a
propósito — la marca es para el "chrome" de la interfaz, el semáforo sigue
siendo el lenguaje de color para leer las métricas de un vistazo. De paso
se corrigió un bug real preexistente (no introducido por este cambio): el
cuadro de "filtros activos" se veía vacío con borde dorado aun sin ningún
filtro puesto, porque la regla CSS de la clase tenía más especificidad que
el atributo `hidden` del navegador.

## 13. Seguimiento de Repartidores (2026-10-24)

Segundo reporte del dashboard (botones "Seguimiento de Envíos" /
"Seguimiento de Repartidores" arriba de todo). Mide asistencia, puntualidad
y flota de los choferes — dato totalmente distinto al de envíos, viene de
dos planillas de Google Sheets, no de LightData/Firestore.

### 13.1 Fuente de datos

El navegador lee dos planillas publicadas como CSV (Archivo → Compartir →
Publicar en la Web), **directo, sin pasar por Firestore ni ninguna
automatización** — a pedido explícito, para no duplicar el trabajo de
armar otro pipeline como el de LightData:

- **Hoja viva** (`Seguimiento choferes`): tiene **solo el día de hoy**, se
  carga a mano durante la jornada. Importante: la hoja cambia de "día" a
  la **medianoche UTC, no a la medianoche de Argentina** — a las 21hs ART
  ya puede tener filas con la fecha del día siguiente. Por eso el
  dashboard NO usa el reloj del navegador para decidir qué es "hoy": usa
  la fecha que la propia fila trae (`fechaReferenciaHoyRepa()`).
- **Hoja histórica** (`Seguimiento Choferes histórica`): todos los días
  anteriores, no incluye hoy. Mismo patrón hoy/ayer que ya existe para
  LightData, pero sin índice ni snapshots — cada hoja es una lista plana
  de filas (una por asignación chofer+turno+zona) que se filtra por fecha
  en el momento de renderizar.
- Cada fila = una **asignación** (chofer + turno + zona ese día), no un
  chofer único — un repartidor puede tener más de una asignación el mismo
  día (confirmado con datos reales).
- Columnas de ambas hojas con nombres levemente inconsistentes entre sí
  (ej. `reprogramado por meli` en minúsculas, `ZONA`/`TIPO DE VEHICULO`
  con mayúsculas/minúsculas mezcladas en la histórica) — se normalizan en
  el dashboard, no en el origen.
- **Hoja de roster** (`Listado de Choferes`): tercera pestaña del **mismo
  documento** que la hoja viva — se publicó "todo el documento" de una
  sola vez en "Publicar en la Web", así que comparte el mismo ID de
  publicación y solo cambia el `gid` en la URL (confirmado el 2026-10-24
  leyendo `/pubhtml` y probando los `gid` que aparecían ahí, sin necesitar
  un link nuevo del usuario). Trae, por repartidor, la columna `ASISTE
  SABADO` (TRUE/FALSE) usada para filtrar qué asignaciones de sábado
  entran en los indicadores de arriba — ver 13.3.

### 13.2 Flujo de una asignación

`ASISTE A DEPOSITO (SOPORTE)` (confirma asistencia) → `PALLET LISTO
(DEPÓSITO)` → `CONFIRMA RETIRO (SOPORTE)` → `HORA LLEGADA` (llegada física
al depósito) → `PALLET RETIRADO (DEPÓSITO)`. La columna `ALERTADO` trae
alertas operativas en vivo (ej. "Pallet sin retirar", "chofer no asiste con
pallet armado").

**OJO:** `HORA LLEGADA` (y por lo tanto todo lo que depende de ella —
"Llegada a tiempo", el heatmap histórico de puntualidad) recién se empezó
a cargar — revisando los 22 días completos de histórico al 2026-10-23, no
hay NINGÚN registro con ese campo poblado antes de esa fecha. No es un bug:
para períodos que no sean "hoy", esas métricas van a mostrar "—" hasta que
se acumule histórico real.

### 13.3 Definiciones

- **Llegada a tiempo:** `HORA LLEGADA` ≤ `TURNO` asignado + **15 minutos**
  de tolerancia (confirmado con el usuario).
- **Objetivo de Asistencia confirmada / Pallet retirado — 95% todos los
  días hábiles, incluido sábado.** No todos los repartidores están
  asignados a trabajar sábado, así que en vez de bajar el objetivo ese
  día (como se hacía al principio, con un 70% de arranque), el dashboard
  **filtra el denominador**: los sábados, `filasEsperadasHoyRepa()` saca
  de la cuenta a las asignaciones de gente marcada `ASISTE SABADO=FALSE`
  en la hoja de roster, antes de calcular los indicadores. Si un
  repartidor no aparece en el roster, NO se excluye (por seguridad, para
  no esconder una inasistencia real por un roster desactualizado). La
  cantidad excluida se muestra como nota debajo de los indicadores
  (`#repaNotaRoster`). Domingo no se evalúa (no opera, igual que Envíos).
- **Objetivo de Llegada a tiempo:** 80% fijo (no varía por día).
- **Centro de alertas:** se excluyen las alertas que digan "a tiempo" —
  dado que la puntualidad todavía no se mide de forma confiable (ver
  13.2), esas alertas son ruido, no algo accionable.
- **Score del ranking histórico** (Rendimiento histórico → Ranking de
  repartidores): `40% asistencia + 40% puntualidad (solo sobre los que
  llegaron) + 20% por no tener alertas`. Pensado para ordenar el ranking,
  no es una métrica oficial de la empresa. **Limitación conocida:**
  no tiene piso de muestra — un repartidor con 1 sola asignación y 100% de
  asistencia puede quedar primero, empatado con alguien de muchas más
  asignaciones (mismo tipo de sesgo que ya se resolvió en Envíos con la
  etiqueta "muestra chica", todavía no replicado acá).

### 13.4 Estructura de la pantalla

Dos modos, para no mezclar "qué pasa ahora" con "cómo venimos
performando" (separación pedida explícitamente):

- **🟢 Operación en vivo** (siempre "hoy"): 3 indicadores con semáforo
  según objetivo del día (Asistencia confirmada, Llegada a tiempo, Pallet
  retirado) → Centro de alertas (lugar fijo, no es una pestaña) → dos
  sub-pestañas: "Repartidores y flota por zona" (tarjeta por zona, solo
  cuenta a los **confirmados**, no a todos los asignados; flota como
  barras ordenadas siempre Furgoneta → Camioneta → Auto → Moto — click en
  una tarjeta muestra el detalle de esos repartidores con turno y
  vehículo) y "Zona × turno" (heatmap, color = % asistencia).
- **📊 Rendimiento histórico** (con su propio selector de período): Ranking
  de repartidores (Top 5 / A mejorar) → heatmap de cuellos de botella
  (zona × turno, color = % puntualidad) → tabla completa, ordenable
  haciendo click en cualquier columna (alterna asc/desc, con flecha
  dorada indicando cuál y en qué sentido — mismo componente que el
  ranking de choferes de Envíos, ver 13.5), por defecto por score
  descendente.
- Se actualiza solo cada 45 segundos mientras la pestaña de Repartidores
  esté abierta (mismo intervalo que Envíos), para reflejar repartidores
  que se van agregando a la hoja viva durante el día.

### 13.5 Tablas ordenables (`wireSortableTable` / `ordenarPorClave`)

Componente genérico (no exclusivo de Repartidores) agregado el
2026-10-24: cualquier `<th data-key="...">` dentro de un `<thead>` pasado
a `wireSortableTable(thead, sortState, onSort)` queda clickeable
(y navegable por teclado, Enter/Espacio) para ordenar asc/desc por esa
columna, con una flecha (`▲`/`▼`, dorada) que indica cuál columna y en
qué sentido — antes el ranking de choferes de Envíos ya tenía el
`data-key` y la lógica de orden, pero sin ningún indicador visual, así
que no se notaba que ya era clickeable. La tabla "Todos los
repartidores" (histórico) directamente no tenía `data-key` ni handler —
el click en los headers no hacía nada. Se usa en dos tablas hoy:
"Ranking de choferes" (Envíos) y "Todos los repartidores"
(Repartidores → histórico), ambas con su propio `state.sort` /
`stateRepa.sort` persistente entre renders. `ordenarPorClave(filas,
sortState)` es el comparador genérico (strings con `localeCompare`,
números restando, `null`/`undefined` al final).

| Fecha | Cambio |
|---|---|
| 2026-09-01 | Versión inicial: definiciones de entrega efectiva, corte de 21hs, cancelados y efectividad por chofer. |
| 2026-09-01 | Se agregó la definición de "día" del envío (`Fecha MercadoPacks`) para el dashboard, y se documentó/corrigió el bug de la fila de totales al final del export. |
| 2026-09-01 | Se sacó la dependencia de Chart.js (CDN externo) del dashboard: no cargaba de forma confiable dentro del artifact y rompía en cadena zona/choferes. Los tres gráficos ahora se dibujan con SVG nativo, sin librerías externas. |
| 2026-09-02 | Corrección de bug crítico: una lectura fallida del almacenamiento compartido podía borrar de la pantalla (y en el peor caso, del storage) datos ya cargados. Se blindó `refreshIndex` y el merge de índice en la carga de archivos para que un fallo transitorio nunca pise datos buenos. |
| 2026-09-02 | Se agregó la columna "Después de 21hs" (cantidad) al ranking de choferes. |
| 2026-09-02 | Se sacó el recorte de 06:00–23:00 del gráfico de entregas por hora (vuelve a mostrar 00–23). |
| 2026-09-02 | Se agregaron las 4 franjas horarias (antes de 21 / 21-22 / 22-23 / después de 23), el cruce por estado, y la columna "Pendientes" (Envíos − Efectivas) en el ranking de choferes. Se agregaron filtros interactivos por zona, franja horaria y chofer. Se re-tematizó el dashboard con la paleta de marca (dorado/negro del logo) separada del semáforo de puntualidad (verde/amarillo/rojo). |
| 2026-09-02 | El cruce por hora de entrega ahora desglosa **todos** los valores de `Estado` (antes solo mostraba `Entregado` y `Entregado 2DA visita`) — ver excepción agregada al punto 8. El ranking de choferes reemplazó la columna "Después de 21hs" por las 4 franjas horarias individuales (cantidad de entregas antes de 21 / 21-22 / 22-23 / después de 23 por chofer). Al cargar un archivo, el panel se posiciona automáticamente en el rango de fechas que trae ese archivo (antes solo pasaba si el archivo incluía el día de hoy). |
| 2026-09-04 | Regla #1: el % de entregas efectivas ahora excluye los envíos en estado `A retirar` del **denominador** (antes solo se excluían del numerador, junto con `Retirado`/`Nadie`/`Nadie 2DA visita`), porque son envíos que todavía no llegaron al depósito. Se agregó el contador `aRetirar` a nivel global/zona/chofer en el snapshot que arma `publicar_firestore.py`, y se replicó en `generar_reporte.py`. |
| 2026-09-04 | Se sacó la carga manual de archivo del dashboard (botón, drag&drop, parseo de .xls en el navegador) porque quedó redundante con la automatización diaria — el dashboard ahora es un lector puro de Firestore, ya no procesa archivos por su cuenta. |
| 2026-09-17 | Regla #5: se agregó la "ventana de repaso" de 3 días — la corrida de cierre re-descarga y recalcula los últimos 3 días (no solo "ayer") para que las entregas que tardan 1-2 días en confirmarse se reflejen en la efectividad de su día de origen. Se agregó la sección 11: detalle de envíos por chofer (tracking, cliente, localidad, zona, estado, hora de entrega) — sin dirección exacta del destinatario, por privacidad (las reglas de Firestore son abiertas). |
| 2026-10-15 | Sección 12: se agregaron 6 indicadores estilo "Mis métricas" de Mercado Libre (envíos correctos, entregas pre/post 21, envíos incorrectos, reprogramado post 21, demora) arriba de los KPIs principales. Se calculan enteramente a partir de `porEstadoHora`, que ya se guardaba — no hubo que tocar descarga ni publicación. Son siempre globales (no respetan filtro de zona/chofer), igual que la tabla "Cruce por hora". |
| 2026-10-16 | Tres ajustes a los indicadores del 2026-10-15: cada valor ahora muestra "de TOTAL" para no perder de vista la base de comparación; el bloque fijo de definiciones/días cargados pasó a un link colapsable ("ⓘ Cómo se calculan estas métricas"); y "Entregas por hora" / "Cruce por hora de entrega" / "Por zona" / "Ranking de choferes" pasaron de estar todos apilados a ser 4 pestañas (una visible a la vez). |
| 2026-10-23 | Los 4 KPIs viejos del dashboard (Total de envíos, Entregas efectivas, Antes de las 21:00, Cancelados/rechazados) se sacaron del todo — quedaron redundantes con los indicadores nuevos. El indicador "Envíos correctos" pasó a llamarse "Entregas Efectivas" y retomó la definición del viejo KPI del mismo nombre (Entregado + Entregado 2DA visita, sin restringir por hora, sobre total − "A retirar"); "Entregas Pre 21" pasó a tener un % como valor principal, igual que "Entregas Post 21" (antes mostraba solo el total sin porcentaje). Además, el dashboard pasó de tema oscuro a tema claro (fondo gris clarito, tarjetas blancas, marca dorado/negro en el "chrome" de la interfaz) manteniendo el semáforo verde/amarillo/rojo de puntualidad sin cambios — ver sección 12. |
| 2026-10-24 | Segundo reporte: **Seguimiento de Repartidores** (sección 13), con botones arriba para navegar entre los dos. Lee dos planillas de Google Sheets publicadas como CSV directo desde el navegador (sin Firestore ni automatización nueva). Dos modos — "Operación en vivo" (hoy: KPIs con objetivo según día de semana, Centro de alertas, flota confirmada por zona con barras, heatmap zona × turno) y "Rendimiento histórico" (ranking con score compuesto, heatmap de cuellos de botella, tabla completa) — para no mezclar monitoreo en vivo con análisis histórico. Se usó la skill de dataviz para la paleta de colores de los vehículos (validada contra daltonismo). De paso se corrigió un bug real preexistente que afectaba a todo el dashboard: `setChip()` no estaba acotado a `#chips`, así que en cada carga de página le borraba la clase "active" a todos los `.chip`, incluidos los botones de navegación nuevos (recién se veían marcados después de un click). **Pendiente:** agregar un piso de muestra al score del ranking. |
| 2026-10-24 | Se conectó la tercera hoja ("Listado de Choferes") para la disponibilidad de sábados — era otra pestaña del mismo documento ya compartido, sin necesitar un link nuevo. Los sábados, el dashboard ahora filtra el denominador de Asistencia confirmada / Pallet retirado a solo quienes están habilitados en el roster (`ASISTE SABADO=TRUE` o sin dato), y el objetivo volvió a 95% (reemplaza el 70% de arranque). Se muestra una nota con la cantidad excluida. De paso se corrigió un bug real: `filasAObjetosRepa()` asumía NOMBRE en la columna 2 (cierto en viva/histórica), pero en el roster NOMBRE es la columna 1 — ahora busca el índice por nombre de columna en vez de asumir una posición fija. |
| 2026-10-24 | Se agregó un componente genérico de tablas ordenables (`wireSortableTable`/`ordenarPorClave`, sección 13.5) y se aplicó a "Todos los repartidores" (histórico de Repartidores), que antes no tenía ningún `data-key` ni handler de click — los headers no hacían nada. De paso se notó que "Ranking de choferes" (Envíos) ya tenía la lógica de orden pero sin indicador visual, así que no se notaba que era clickeable; ahora ambas tablas muestran una flecha dorada (▲/▼) en la columna activa. |
