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

### Entregas Efectivas — desglose Flex de Mercado Libre (2026-11-06)

La tarjeta "Entregas Efectivas" (punto 1 arriba) muestra ahora, debajo del
desglose normal, una sub-sección "Solo Flex de Mercado Libre" con el mismo
% y los mismos números pero calculados únicamente sobre los envíos Flex.

**Qué cuenta como "Flex de Mercado Libre":** el export de LightData no trae
ninguna columna llamada "Flex" — se usa la columna `Origen` (ver
`diccionario_de_datos.md`), y un envío cuenta como Flex si `Origen` es
`"ML"` o `"ML TURBO"`. Criterio confirmado con el equipo el 2026-11-06
(se descartó limitar a solo `"ML"` porque "ML TURBO" también es Flex).

**Cómo se calcula:** `publicar_firestore.py` ahora calcula, fila por fila,
si el envío es Flex (`Origen` ∈ {`ML`, `ML TURBO`}) y, si lo es, además de
sumarlo en los contadores globales de siempre lo suma en un sub-objeto
`flex` del snapshot diario (`{total, aRetirar, porEstadoHora}` — mismo
shape que los campos globales, pero restringido a Flex). El dashboard
agrega ese sub-objeto igual que el resto (`aggregate()`) y
`renderIndicadoresMeli()` aplica la misma fórmula del punto 1
(`Entregado + Entregado 2DA visita`, sin restringir por hora, sobre
`total flex − "A retirar" flex`) pero leyendo `agg.flex` en vez de `agg`.

**Limitación conocida:** los snapshots ya publicados en Firestore antes de
este cambio no tienen el campo `flex` (quedan en `{total:0, aRetirar:0,
porEstadoHora:{}}` por el fallback del dashboard), así que para esos días
la sub-sección muestra "—". Se completa solo, día a día, a medida que
`publicar_firestore.py` corre con el código nuevo — no hace falta
reprocesar el historial salvo que se quiera tener el dato retroactivo
(en ese caso, habría que volver a correr `publicar_firestore.py` sobre los
archivos crudos ya descargados de esos días).

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

`ASISTENCIA` (confirma asistencia — hasta el 2026-10-31 se llamaba `ASISTE
A DEPOSITO (SOPORTE)`, ver 13.6) → `PALLET LISTO (DEPÓSITO)` →
`CONFIRMA RETIRO (SOPORTE)` → `HORA LLEGADA` (llegada física al depósito)
→ `PALLET RETIRADO (DEPÓSITO)`. La columna de alertas operativas en vivo
(ej. "Pallet sin retirar", "chofer no asiste con pallet armado") está, al
2026-10-31, **sin nombre de columna** en el CSV publicado — el dashboard
la ubica por posición, justo después de `ESTADO DEL CHOFER` — y se sigue
exponiendo internamente como `ALERTADO`, ver 13.6.

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

### 13.6 La planilla de origen puede cambiar de esquema sin avisar

Bug real encontrado el 2026-10-31: entre el 2026-10-24 (conexión inicial)
y esa fecha, alguien restructuró las columnas de las hojas "viva" e
"histórica" en Google Sheets — mismo documento, mismo `gid`, pero:

- `ASISTE A DEPOSITO (SOPORTE)` se renombró a `ASISTENCIA` (mismo
  significado, TRUE/FALSE).
- La columna `ALERTADO` perdió su nombre de columna al republicar —
  quedó como un header vacío (`""`) pegado justo después de `ESTADO DEL
  CHOFER` (una columna narrativa nueva que no es lo mismo: trae estados
  como "👍 Asistencia confirmada" o "🚚 En camino al depósito", no
  alertas).

Como `filasAObjetosRepa()` arma el objeto de cada fila a partir del
nombre de columna (`header.forEach((h,i) => { if(h && h.trim())
obj[h.trim()] = ... })`), el resultado fue silencioso y específico:
- `f['ASISTE A DEPOSITO (SOPORTE)']` pasó a ser siempre `undefined` →
  nunca `=== 'TRUE'` → Asistencia confirmada y Pallet retirado
  mostraban 0% todo el tiempo, con la "fecha de hoy" y la cantidad de
  asignaciones calculadas bien (la hoja SÍ tenía filas de hoy) — lo que
  hacía parecer que "no mostraba datos de hoy" cuando en realidad sí los
  encontraba, pero los contaba todos como "no asistió".
- La columna de header vacío (que traía el texto de la alerta) se
  descartaba del todo en el loop de arriba → Centro de alertas siempre
  "Sin alertas", aunque hubiera alertas reales ese día.
- No hubo ningún error de JS ni pantalla vacía — por eso pasó
  desapercibido hasta que el usuario lo reportó a simple vista.

**Fix:** `asisteRepa(f)` prueba los dos nombres de columna (`ASISTENCIA`
primero, `ASISTE A DEPOSITO (SOPORTE)` como fallback) en vez de asumir
uno solo. `filasAObjetosRepa()` ubica la columna de alertas **por
posición** (el índice siguiente a `ESTADO DEL CHOFER`, solo si ese header
está vacío) y la expone bajo la clave `ALERTADO` de siempre, para no
tener que tocar el resto del código que ya la usa.

**Lección para el futuro:** esta integración lee una planilla operativa
que el equipo de depósito edita directamente (no un export generado por
el propio dashboard), así que el esquema de columnas puede cambiar en
cualquier momento sin que nadie avise al código. Si un indicador de
Repartidores empieza a dar 0% o "sin datos" de forma sospechosa (sobre
todo si la cantidad de asignaciones del período sigue siendo la
correcta), lo primero a revisar es si los nombres de columna en
`dashboard_logistica.html` siguen matcheando el CSV real —
`curl -sL "<URL_REPA_VIVA>" | head -1` para ver el header actual.

## 14. Migración de la descarga a la API externa de LightData (en curso, 2026-11-11)

**Motivación:** la descarga actual (`descargar_lightdata.py`) loguea con
Playwright contra la UI de LightData, lo que implica: una VM de GitHub
Actions efímera que reinstala Chromium + LibreOffice (fallback para .xls
con BIFF corrupto) en cada corrida (~2 min de las cuales la mayor parte es
instalación, no descarga), y selectores de UI que se rompen cada vez que
LightData cambia el diseño de la página (ya pasó más de una vez, ver
comentarios de `descargar_lightdata.py`). LightData tiene una API externa
documentada en https://lightdata.app/documentacion_api_externa.html con un
endpoint pensado justo para esto: `POST /externa/consultar-fecha`, que
devuelve JSON por rango de fecha sin navegador ni login de UI.

**Estado actual: escrito pero NO conectado al workflow.**

- `descargar_lightdata_api.py` llama a `consultar-fecha`, pagina los
  resultados (hasta 1000 por página, límite de 50 req/min) y escribe un
  `.csv` en `datos_crudos/` con los mismos nombres de columna que
  `generar_reporte.cargar_export()` espera del .xls real — así
  `procesar()`, `calcular_snapshots()` y el resto del pipeline no
  necesitan ningún cambio, solo la fuente de datos cambia.
- `cargar_export()` ahora detecta la extensión `.csv` y la lee directo
  (sin la detección de header/fila de totales que sí hace falta para el
  .xls real).
- La lógica de "qué día descargar" (`calcular_fecha_objetivo`) se movió a
  `fecha_descarga.py`, compartida por los dos scripts de descarga, para
  que el script de API no tenga que importar `playwright` solo por esa
  función (uno de los puntos de esta migración es justamente dejar de
  depender de un navegador).

**Por qué todavía no reemplaza a Playwright en el workflow — dos bloqueos:**

1. **El endpoint no está habilitado.** `consultar-fecha` devuelve
   `{"success":false,"message":"Empresa no habilitada"}` para la empresa
   253 (confirmado llamándolo directamente el 2026-11-11, con el
   `TokenEmpresa` real) — la documentación ya advertía que este endpoint
   "no está habilitado para todas las empresas". Hay que pedirle a
   LightData que lo habilite. Se probaron también los demás endpoints de
   lectura (`estado-envio`, `estado-envios`, `estado-historial`,
   `obtener-info-entrega`) y piden además un segundo token ("de
   integrador cliente") que no tenemos — pero no hace falta, porque esos
   endpoints son para consultar un envío puntual, no para el export
   diario completo.
2. **Mapeos de campo sin confirmar contra datos reales**, en particular
   dentro de `_mapear_fila()` de `descargar_lightdata_api.py`:
   - **`Fecha MercadoPacks`** (qué campo de la API corresponde al "día de
     ingreso al sistema", regla de negocio sensible — sección 5) se deja
     vacío a propósito en vez de adivinar, lo que fuerza el fallback a
     `Fecha estado` en `fecha_operativa()` (ese sí confirmado:
     `fecha_ultimo_estado` de la API). Si se quiere recuperar la
     semántica exacta de "Fecha MercadoPacks", hay que comparar un día
     real campo por campo contra el .xls equivalente antes de mapear algo.
   - **Nombres exactos de `Estado`**: no confirmado si la API devuelve
     "Entregado 2DA visita" y "reprogramado por meli" (en minúsculas,
     inconsistencia real del .xls — sección 12, punto 5) tal cual, o con
     otro formato.
   - **`Origen`**: la API devuelve un código numérico (0-8) + un flag
     `turbo`; se mapea a los mismos strings que ya usa el pipeline
     (`ML`, `ML TURBO`, `Directo`, `TNube`) asumiendo que código 1 = "ML"
     y que `turbo=1` es lo mismo que el "ML TURBO" del export viejo — sin
     confirmar todavía contra una fila real.

**Antes de conectar esto al workflow de GitHub Actions**, hay que: pedir
la habilitación del endpoint, correr `descargar_lightdata_api.py` a mano
para un día ya conocido, y comparar el resultado fila por fila contra el
.xls real del mismo día (en especial los tres puntos de arriba). Recién
después de esa validación se cambia `descarga_diaria.yml` para usar este
script en vez de `descargar_lightdata.py`.

## 15. Imagen Docker de CI para la corrida diaria (2026-11-11)

**Problema que resuelve:** cada corrida de `descarga_diaria.yml` arrancaba
en una VM de GitHub Actions totalmente vacía y reinstalaba, de cero,
Chromium + sus dependencias de sistema (`playwright install --with-deps
chromium`), LibreOffice (`apt-get install libreoffice-calc`) y las
dependencias de Python (`pip install -r requirements.txt`) — de los ~2
minutos que tardaba la corrida completa, la mayor parte era instalación,
no descarga ni procesamiento. Esto no era un problema de costo (repo
público = Actions gratis e ilimitado), pero sí de tiempo: con el
concurrency group del workflow (una sola corrida en cola a la vez), ese
tiempo de instalación limitaba cuán seguido se podía disparar el workflow
sin perder corridas encoladas (ver changelog 2026-11-07).

**Solución:** una imagen Docker propia, con todo lo de arriba ya
instalado, publicada en GitHub Container Registry (gratis para repos
públicos) y reconstruida sola cuando hace falta:

- `scripts/Dockerfile` — parte de la imagen oficial de Microsoft
  `mcr.microsoft.com/playwright/python:v1.62.0-jammy` (Python + Playwright
  + Chromium + todas sus dependencias de sistema ya instalados), le suma
  `libreoffice-calc` (no viene en la imagen base) y corre `pip install -r
  requirements.txt`. El tag de versión de la imagen base tiene que
  coincidir con la versión de `playwright` fijada en `requirements.txt`
  (ambas en `1.62.0`) — si se actualiza una, hay que actualizar la otra.
- `.github/workflows/build_imagen_ci.yml` — arma y publica la imagen en
  `ghcr.io/mercadopacks/mercadopacks-metricas-diarias/ci:latest` cuando
  cambia el Dockerfile o `requirements.txt` (o a mano, por
  `workflow_dispatch`).
- `descarga_diaria.yml` ahora corre el job entero dentro de esa imagen
  (`container: image: ...`) en vez de instalar nada — se sacaron los 3
  pasos de instalación ("Configurar Python" / "Instalar LibreOffice" /
  "Instalar dependencias"). El job necesita `permissions: packages: read`
  y credenciales (`${{ secrets.GITHUB_TOKEN }}`, automático, no es un
  secret que haya que cargar a mano) para poder bajar la imagen desde
  GHCR, aunque sea del mismo repo.

**Resultado esperado:** la corrida pasa de ~2 minutos a (en teoría, a
confirmar con la primera corrida real post-deploy) unos segundos — solo
el tiempo de bajar la imagen (cacheada entre corridas por el runner),
loguear en LightData, descargar y procesar. Esto despeja el límite real
que había para aumentar la frecuencia de refresco del dashboard.

**Confirmado en producción (2026-11-11, corrida real post-deploy):** la
corrida completa tardó 56 segundos de punta a punta (30s bajando la
imagen + 18s de login a LightData/descarga/publicación), contra los ~2
minutos de antes — sin errores de permisos bajando la imagen desde GHCR.

## 16. Corridas intradía hasta la noche + bug de fecha UTC/ART corregido (2026-11-11)

**Motivación:** el usuario quiere usar las corridas intradía para hacer
seguimiento en vivo de repartidores demorados, no solo un refresco del
dashboard — necesita datos actualizados cada 20 minutos desde las 11:00
hasta las 23:40 ART (justo antes de la corrida de cierre de las 00hs),
no solo hasta las 18:00 como antes. Esto dejó de ser un problema de
"tiempo de Actions" (sección 15 ya lo bajó a segundos) y pasó a ser
puramente de cuántas veces por día se dispara desde cron-job.org.

**Bug real encontrado al planear esto, corregido antes de habilitar el
horario extendido:** toda la resolución de "qué día es hoy" (tanto en
`descarga_diaria.yml` como en `fecha_descarga.calcular_fecha_objetivo()`)
usaba la fecha UTC cruda (`date -u` / `datetime.now(timezone.utc).date()`)
asumiendo que coincidía con la fecha de Argentina. Eso es cierto
**solo** mientras las corridas de `modo=hoy` ocurren entre las 14:00 y
las 21:00 UTC (11:00-18:00 ART) — un rango que nunca cruza la medianoche
UTC. Al extender las corridas hasta las 23:40 ART, las de 21:00 a 23:40
ART caen en **00:00 a 02:40 UTC del día calendario siguiente**:
- Con la fecha UTC cruda, una corrida de las 22hs ART del sábado se leía
  como domingo en UTC → el chequeo de "día operativo" la saltaba sola,
  en silencio (sin error, sin log de alerta — el mismo patrón de fallo
  silencioso que ya pasó antes en este proyecto, ver incidente del
  2026-10-01 en `descargar_lightdata.py`).
- Si no se saltaba, `FECHA_DESCARGA` quedaba con la fecha de **mañana**
  en vez de la de hoy, y el snapshot se hubiera publicado bajo la fecha
  equivocada en Firestore.

**Fix:** tanto el chequeo de día operativo como el cálculo de `FECHAS` en
`descarga_diaria.yml`, y `calcular_fecha_objetivo()` en
`fecha_descarga.py`, ahora restan 3 horas (ART = UTC-3 fijo, sin horario
de verano) al instante UTC actual **antes** de tomar la fecha/día de la
semana — así "hoy" siempre es el día de Argentina, sin importar a qué
hora UTC se ejecute. Verificado con casos simulados por epoch (sábado
23:30 UTC, domingo 00:30-01:30 UTC que en ART siguen siendo sábado a la
noche, lunes 00:30/03:00 UTC que en ART son domingo/lunes) — todos
resuelven el día ART correcto.

**Nuevo esquema de cron-job.org (reemplaza los 4 jobs de `modo=hoy` por
2, por la razón de abajo):**

| Job | Minutos | Horas (UTC) | Días (UTC) | Representa en ART |
|---|---|---|---|---|
| "Hoy — día" | 0,20,40 | 14-23 | Lunes-Sábado (1-6) | 11:00-20:40 ART, Lunes-Sábado |
| "Hoy — noche" | 0,20,40 | 0-2 | Martes-Domingo (2-7) | 21:00-23:40 ART, Lunes-Sábado |
| "Ayer" (sin cambios) | 0 | 3 | Todos menos Lunes | Cierre 00:00 ART |

**Por qué son 2 jobs y no 1 con más horas seleccionadas:** cron-job.org sí
permite seleccionar horas no contiguas (14-23 y 0-2) dentro de un mismo
job, pero el campo de **día de la semana es uno solo por job** — y el
día de la semana en UTC que corresponde a "Lunes ART" es distinto según
el tramo horario (el tramo 14-23 UTC coincide con el día ART; el tramo
0-2 UTC es el día ART **siguiente** en el calendario UTC, por el cruce de
medianoche). Un solo job no puede aplicar dos reglas de día de la semana
distintas según la hora, así que hace falta separarlos en dos jobs con
su propio rango de día de la semana cada uno.

## 17. Seguimiento en ruta (mockeado, 2026-11-11)

Tercer modo dentro de "Seguimiento de Repartidores" (junto a "Operación en
vivo" y "Rendimiento histórico"), chip `🚚 Seguimiento en ruta`.

**Por qué es un modo distinto de "Operación en vivo":** ese modo existente
es **asistencia** — quién se presentó hoy, con qué vehículo, por zona
(lee el roster de Google Sheets). Este modo nuevo es **rendimiento
durante la ruta** — de los choferes que ya salieron a repartir, quién va
a tiempo y quién demorado, para que soporte (dividido por zona) accione
en caliente. Son preguntas distintas aunque las haga la misma persona.

**Mapa de zonas (ML Flex)** usado para los chips de filtro: CABA; Zona
Norte (Vicente López, San Isidro, San Fernando, Tigre, San Martín,
Malvinas Argentinas, San Miguel, Escobar, Pilar, José C. Paz); Zona Sur
(Avellaneda, Lanús, Lomas de Zamora, Quilmes, Almirante Brown,
Berazategui, Esteban Echeverría, Ezeiza, Florencio Varela, Berisso,
Ensenada, La Plata, Presidente Perón, San Vicente); Zona Oeste (Tres de
Febrero, La Matanza, Morón, Hurlingham, Ituzaingó, Merlo, Moreno,
General Rodríguez, Marcos Paz). Hoy el dato real de "zona" de cada
chofer sigue viniendo de la planilla de Repartidores (no hay una
localidad por chofer para mapear contra esta lista); este mapa queda
documentado para cuando se conecte una fuente real con localidad.

**Estado actual — datos mockeados:** no existe todavía una fuente real
para "entregado / pendiente de la hoja de ruta en este momento" ni para
el tiempo real entre entregas de cada chofer. La UI corre sobre
`generarMockChoferesRuta()` (dashboard_logistica.html), con una semilla
fija para que la demo sea reproducible al revisarla con el equipo. Antes
de pasar a producción falta: definir la fuente real de estos datos
(¿otra columna en la planilla de Repartidores? ¿un sistema de tracking
GPS/checkpoints?), y reemplazar esa función por la carga real — el resto
(KPIs, alertas, tabla ordenable, filtro por zona) ya queda armado sobre
la misma forma de fila.

**Qué datos muestra, definición confirmada con soporte (2026-11-11):**
- **Progreso**: paquetes asignados vs. entregados, como barra (reutiliza
  `.repa-meter`).
- **Hora de la 1ª entrega** y **paquetes por hora** (velocidad real:
  entregados ÷ horas transcurridas desde esa primera entrega).
- **Entregados antes de las 21hs** y **pendientes** — para que soporte
  evalúe a ojo si el chofer va a llegar a terminar su hoja de ruta o no
  (mismo corte de las 21hs que ya usa el resto del dashboard para la
  puntualidad de entrega, sección 2).
- **Demora**, calculada contra el **tiempo entre una entrega y la
  siguiente** — no contra un horario planificado (no existe esa hoja).
  Si el chofer se achica de ritmo, se lo marca sin importar cuántos
  paquetes tenga asignados:
  - **Óptimo** (verde): hasta 5 min entre entregas.
  - **A tiempo** (amarillo): entre 6 y 20 min.
  - **Demorado** (rojo): más de 20 min.

**Componentes:** reutiliza los ya existentes de "Repartidores" para
mantener consistencia visual — `.repa-rag` (badge de estado),
`.repa-meter` (barra de progreso, ahora dentro de la tabla en vez de
solo en mini-kpis), `.repa-alerta-fila` (lista de "Demorados ahora"),
`mini-kpi` (resumen), y el mismo mecanismo genérico de tabla ordenable
(`wireSortableTable`/`ordenarPorClave`, sección 13.5) para poder
ordenar por mayor demora, menor velocidad o más pendientes.

Los 5 mini-kpis de arriba (Choferes en ruta, % dentro de ritmo,
Demorados ahora, Velocidad promedio, Paquetes pendientes) van en una
sola fila compacta (`.mini-kpis-linea`, sección 18) en vez del grid de 3
columnas que usa el resto del dashboard — con un ícono ⓘ por tarjeta que
explica qué mide cada número, porque sin el texto de detalle ("sub") que
sí tienen las demás tarjetas, el nombre corto de la etiqueta no siempre
alcanza para entender la cuenta (ej. "% dentro de ritmo" por sí solo no
dice que es sobre el filtro de zona activo, no sobre el total general).

## 18. Filtros por columna en tablas (agregado 2026-11-11)

Se agregó un componente genérico reusado en varias tablas del
dashboard: una segunda fila debajo del header ordenable, con un
input/select por columna, para poder **acotar** la tabla además de
**ordenarla** (que ya existía vía `wireSortableTable`/`ordenarPorClave`,
sección 13.5). Funciones genéricas en el HTML: `crearFilaFiltros()`
(arma la fila de inputs/selects), `aplicarFiltrosColumna()` (aplica el
filtro sobre las filas antes de ordenar) y `refrescarOpcionesFiltro()`
(actualiza las opciones de un `<select>` cuando dependen de datos que
llegan después por fetch, ej. las zonas reales de una planilla).

Cada columna es, según el tipo de dato: `<select>` de coincidencia
exacta (Zona/Turno/Estado — un set chico y fijo de valores) o `<input>`
de texto de coincidencia parcial (métricas numéricas). La columna del
nombre (Chofer/Repartidor) queda sin filtro de columna a propósito — ya
tiene su propio buscador de texto libre arriba de la tabla, que además
se unificó visualmente en este mismo cambio (ver más abajo).

**Tablas donde se aplicó** (las que ya tenían columnas ordenables):
- **Choferes en ruta** (Repartidores → Seguimiento en ruta): Zona/Turno/
  Estado como `<select>`; Min. entre entregas/Hora 1ª entrega/Paq. por
  hora/Progreso/Pendientes como texto.
- **Todos los repartidores** (Repartidores → Histórico): Zona como
  `<select>` (con opciones dinámicas según el período cargado — la
  planilla real puede no usar los mismos nombres de zona que el mapa ML
  Flex de "Seguimiento en ruta"); Asignaciones/% Asistencia/% A tiempo/
  Alertas/Score como texto.
- **Ranking de choferes** (Envíos): las 10 columnas de métricas, todas
  como texto (Chofer ya tenía su buscador y el filtro por zona/chofer
  por click en los gráficos — regla #9 — así que no se tocó esa parte).

**Dónde NO se aplicó, a propósito:** "Detalle de envíos por chofer"
(sección 11) no tenía columnas ordenables antes de este cambio, así que
quedó fuera de esta pasada para no mezclar dos features en el mismo
cambio — sigue con su buscador de texto libre (ahora con el estilo
unificado) pero sin fila de filtros por columna. Si hace falta, es la
misma función genérica la que habría que conectar ahí.

**Buscador de tabla unificado:** los 4 inputs de búsqueda del dashboard
(`#buscarChofer`, `#buscarDetalle`, `#buscarChoferRuta`,
`#buscarRepartidor`) tenían cada uno su propio estilo chico y sin
padding real (herencia de cuando se agregaron de a uno). Ahora comparten
la clase `.buscador`, más grande y con la paleta del resto de la
interfaz (fondo, borde, foco dorado).

### 18.1 Pasada de QA sobre esta misma feature (2026-11-11)

Tras el primer pase (18) se hizo una revisión de UX/QA enfocada en lo
agregado — se usó la skill `ui-ux-pro-max` para confirmar el criterio de
"sacar el look nativo de un `<select>`" (no hay match exacto en la base
de estilos para esa técnica puntual, así que se aplicó la práctica
estándar documentada abajo, no una recomendación sacada de la skill).
Se encontraron y corrigieron estos problemas reales:

- **`<select>` con el look nativo del sistema operativo** (reportado por
  el usuario con captura, dos veces: primero se le sacó el `appearance`
  nativo y se le dibujó una flecha propia por CSS, pero eso solo cambia
  el recuadro CERRADO — la lista DESPLEGADA la sigue pintando el
  navegador/SO sobre un `<select>` real, cuadrada y con el resaltado
  azul de Windows, sin forma de tocarla con CSS). Solución definitiva:
  se reemplazó el `<select>` por un combo propio (`crearComboFiltro()`)
  — un `<button>` + una `<ul role="listbox">` con los mismos colores,
  bordes y radios que el resto de la interfaz, tanto cerrado como
  abierto. Mantiene semántica y teclado de un combobox (flechas, Enter,
  Escape, cierre al click afuera).
- **Desalineación de columnas en mobile**: la fila de filtros no copiaba
  la clase `hide-mobile` de las columnas que el dashboard ya oculta en
  pantallas chicas (ej. "Turno" en Choferes en ruta, la mayoría de las
  columnas de "Ranking de choferes"). Resultado: en mobile el filtro de
  una columna oculta seguía ocupando una celda, corriendo todo lo demás
  un lugar. `crearFilaFiltros()` ahora copia esa clase leyendo el `<th>`
  del header real, columna por columna.
- **`aria-label` ilegible para lectores de pantalla**: decían "Filtrar
  por estadoLabel" / "Filtrar por zonaPrincipal" (el nombre interno de
  la variable). Ahora se arma leyendo el texto visible del header de esa
  columna ("Filtrar por Estado", "Filtrar por Zona").
- **Bug real preexistente, destapado por los filtros nuevos** (no
  introducido por este cambio): en "Ranking de choferes", la fila
  resumen "(sin chofer asignado)" se agregaba siempre al final de la
  tabla sin pasar por el buscador ni ningún filtro — con cualquier
  filtro activo igual aparecía, aunque sus columnas fueran todas "—" y
  no tuviera sentido contra ese filtro. Ahora se oculta en cuanto hay un
  buscador o un filtro de columna activo, igual que cualquier otra fila.
- **Número de los mini-kpis en línea muy chico** en relación a la
  etiqueta (quedaba igual de peso visual que el texto de arriba, en vez
  de destacarse). Se subió de 16px a 19px — sigue siendo más chico que
  el de las tarjetas en grid (21px) porque la fila es más angosta, pero
  ya se distingue como el dato principal.

## 19. Dos bugs reales en "Operación en vivo" + "Seguimiento en ruta" pasa a datos reales (2026-11-11)

Al preparar el pase a producción se encontraron y corrigieron dos bugs
reales — ninguno introducido por los cambios recientes, estaban desde
antes — y se conectó "Seguimiento en ruta" a datos reales de LightData
(hasta acá corría sobre `generarMockChoferesRuta()`, ver sección 17).

### 19.1 "Operación en vivo" no traía datos — dos causas combinadas

**Causa 1 — `URL_REPA_VIVA` apuntaba a la hoja equivocada.** Esa URL no
tenía `gid` en el query string, así que dependía de cuál fuera la
pestaña "por defecto" del documento publicado — hasta que esa
configuración cambió (alguien dejó otra pestaña abierta al
guardar/republicar, lo más probable) y empezó a servir en silencio la
pestaña **"Localidades"** (gid `620286872`, un cuadro de zonas/horarios
de ~20 filas) en vez de **"Seguimiento Diario"** (gid `407099768`, la
hoja operativa real). Confirmado leyendo `/pubhtml` del documento
publicado — mismo método ya usado en 2026-10-24 para encontrar el gid
del roster. Fix: `URL_REPA_VIVA` ahora fija `&gid=407099768`
explícitamente, igual que ya se hacía con `URL_REPA_ROSTER`.

**Causa 2 — fila en blanco antes del header real.** Con el gid
corregido, la hoja "Seguimiento Diario" resultó tener una fila vacía
(`,,,,,,,,,,,,,,,,,,,,,,`) ANTES del header real (`FECHA,NOMBRE,...`) —
algo que la copia histórica no tiene. `filasAObjetosRepa()` tomaba
`filas[0]` como header a ciegas, así que esa fila en blanco se usaba
como header: todas las columnas quedaban sin nombre (el loop ya
descartaba columnas con header vacío), y la planilla entera se leía
como 0 filas útiles — sin ningún error, "Operación en vivo" mostraba
"Todavía no hay datos de hoy" con la planilla llena de filas reales.
Fix: ahora se busca la primera fila que tenga `FECHA` o `NOMBRE` entre
sus celdas y se usa esa como header, descartando lo que venga antes
(no cambia nada para histórica/roster, que no tienen esa fila extra).

Ambos bugs se superponían — corregir solo el primero no alcanzaba,
porque la fila en blanco también está en "Seguimiento Diario"
(descubierto recién al corregir el gid y volver a probar).

### 19.2 "Seguimiento en ruta" pasa a datos reales

Reemplaza `generarMockChoferesRuta()` por `cargarChoferesEnRutaHoy()`,
que lee `envios_detalle/<hoy>/choferes` en Firestore — el mismo detalle
por chofer que ya arma `publicar_firestore.py` a partir del export de
LightData (sección 11), actualizado cada 20 minutos por la corrida
intradía (sección 16). Una sola lectura de colección trae TODOS los
choferes del día (sin necesitar sus ids de antemano), mucho más barato
que pedir chofer por chofer.

**Cómo se calcula cada fila, a partir de los items de ese chofer:**
- **Asignados** = items con `estado` distinto de `"A retirar"` (todavía
  no llegó al depósito — mismo criterio que la regla de negocio #1).
- **Entregados** = items con `estado` en `{"Entregado", "Entregado 2DA
  visita"}`.
- **Pendientes** = asignados − entregados.
- **Minutos entre entregas** = promedio de los gaps entre los
  `horaEntrega` (ya vienen como `"HH:MM"`) de los items entregados,
  ordenados. Con menos de 2 entregas no hay ritmo que medir → estado
  **"Sin entregas aún"** (gris, cuarto estado agregado al semáforo de la
  sección 17 — antes solo eran 3), no un falso "Óptimo".
- **Hora de la 1ª entrega** = el `horaEntrega` más chico entre los
  entregados.
- **Pre 21** = entregados con `horaEntrega` antes de las 21:00.
- **Zona** = la más frecuente entre los items asignados de ese chofer
  (un chofer puede tener paquetes de más de una zona en el día).

**Se sacó la columna "Turno"**: no es un dato que LightData registre
por envío (es un concepto de la planilla de Repartidores/asistencia,
sección 13), así que no había forma de calcularlo sin inventarlo.

**Estado vacío**: si `envios_detalle/<hoy>` todavía no tiene ningún
chofer (antes de la primera corrida intradía del día, o un domingo no
operativo), se muestra un estado vacío en vez de una tabla en blanco.

### 19.3 Corrección del criterio de zona (2026-11-11, mismo día)

La primera versión de 19.2 clasificaba por el campo `Zona` que trae el
export de LightData — resultó ser **el criterio equivocado**: el equipo
confirmó que el criterio es el mapa de localidades ML Flex (CABA/Zona
Norte/Zona Sur/Zona Oeste) dado al principio del proyecto (sección 17),
no la zona interna de LightData. Dos problemas con la zona de LightData,
además de no ser el criterio pedido:
- Trae **sus propios valores** (`"CABA"`, `"ZONA 1"`, `"ZONA 2"`,
  `"ZONA 3"`, `"Sin zona"`), sin relación directa con los 4 grupos ML Flex.
- Es **inconsistente**: la misma localidad aparecía con distinto valor
  de `Zona` en envíos distintos del mismo día (ej. "La Plata" repartido
  entre `ZONA 3` y `Sin zona`, "Esteban Echeverría" entre `ZONA 1`,
  `ZONA 2` y `Sin zona`) — no es confiable como fuente de zona.

**Fix:** la zona ahora se calcula a partir de la **`Localidad`** de cada
envío (no de `Zona`), con `zonaPorLocalidad()` + el mapa
`ZONA_POR_LOCALIDAD` (dashboard_logistica.html). Los envíos reales traen
la localidad FINA (barrio/pueblo — ej. "Olivos", "Don Torcuato", "Haedo"),
no el nombre del partido que dio el equipo (San Isidro, Tigre, Morón) —
`ZONA_POR_LOCALIDAD` ubica cada localidad conocida dentro de su partido
y de ahí a su zona, construido y chequeado contra las ~290 localidades
reales del 2026-11-11. Normaliza acentos/mayúsculas/comas
(`normalizarLocalidad()`) para tolerar variantes como "José C. Paz" /
"jose clemente paz" / "JOSE C PAZ". Lo que no se reconoce queda **"Sin
zona"** a propósito (mejor visible y corregible — agregar una entrada
nueva al mapa — que mal clasificado en una zona que no le corresponde).
Cobertura real verificada: de 116 choferes del 2026-11-11, solo 4
(3.4%) cayeron en "Sin zona".

Los chips de arriba y el filtro de columna "Zona" volvieron a ser
**fijos** (Global/CABA/Zona Norte/Zona Sur/Zona Oeste/Sin zona, en ese
orden) en vez de dinámicos — es un criterio cerrado dado por el equipo,
no algo que deba variar según lo que traiga LightData ese día.

### 19.4 Mapa de localidades ampliado al listado completo por partido (2026-11-11, mismo día)

El equipo envió el listado completo y oficial, por partido y por
"cordón" (1/2/3, zonas de cobertura habilitadas), con el detalle de
localidades de cada uno. Se reemplazó el mapa armado en 19.3 (que solo
cubría las localidades vistas ese día en los datos reales) por este
listado completo:

- **CABA**: cobertura 100% de barrios — listado oficial de 46 barrios.
- **Zona Norte**: Vicente López, San Isidro, San Fernando, Tigre, San
  Martín, Malvinas Argentinas, San Miguel (cordón 1-2) + Escobar, Pilar,
  José C. Paz (cordón 3), con sus localidades principales de cada uno
  (ej. Tigre: Don Torcuato, General Pacheco, El Talar, Benavídez,
  Nordelta...).
- **Zona Sur**: Avellaneda, Lanús, Lomas de Zamora, Quilmes, Almirante
  Brown, Berazategui, Esteban Echeverría, Ezeiza (cordón 1-2) +
  Florencio Varela, Berisso, Ensenada, La Plata, Presidente Perón, San
  Vicente (cordón 3).
- **Zona Oeste**: Tres de Febrero, La Matanza (Norte/Centro), Morón,
  Hurlingham, Ituzaingó, Merlo, Moreno (cordón 1-2) + La Matanza (Sur),
  General Rodríguez, Marcos Paz (cordón 3).

Cobertura verificada de nuevo tras ampliar el mapa: 4 de 122 choferes
(3.3%) en "Sin zona" — en línea con la medición anterior, ahora con un
mapa más completo y trazable directamente al listado oficial en vez de
sólo a lo que apareció un día puntual.

**Única ambigüedad encontrada en el listado**: "Villa Bosch" aparece
listada tanto bajo San Martín (Zona Norte) como bajo Tres de Febrero
(Zona Oeste) — administrativamente es una localidad de San Martín, así
que se resolvió a Norte. Si el criterio real para esa localidad puntual
es otro, avisar para corregir la entrada en `ZONA_POR_LOCALIDAD`.

## 20. Bug real: header de la hoja "viva" pisado por datos + historial en "Seguimiento en ruta" (2026-11-12)

### 20.1 "Operación en vivo" y "Rendimiento histórico" sin datos — otra vez, otra causa

Reportado por el usuario el día después de 19.1 (que ya había corregido
un problema de header distinto). Encontrado: alguien tipeó los datos de
un chofer (Miguel Gomez, 12/11) directamente en lo que debía ser la fila
de header de "Seguimiento Diario" — pisó `FECHA`/`NOMBRE`/`TIPO DE
VEHICULO`/`TURNO` con valores reales, pero sin tocar el resto de los
títulos de columna (`ESTADO DEL CHOFER`, `ALERTADO`, etc., que
quedaron intactos más a la derecha de esa misma fila). Resultado: ni
`"FECHA"` ni `"NOMBRE"` aparecían ya en ninguna fila completa, la
detección por nombre de 19.1 fallaba de nuevo (mismo síntoma, causa
distinta), y la hoja entera se volvía a leer como "sin datos".

**Fix:** se agregó un segundo nivel de detección en `filasAObjetosRepa()`.
Si ninguna fila tiene `"FECHA"`/`"NOMBRE"` literal pero alguna fila tiene
alguno de 4 fragmentos de columna lo bastante largos/específicos como
para no aparecer nunca por casualidad como dato real (`"ESTADO DEL
CHOFER"`, `"TIENE FALLIDOS (SOPORTE)"`, `"CONFIRMA RETIRO (SOPORTE)"`,
`"PALLET RETIRADO (DEPÓSITO)"`), se usa un **header fijo hardcodeado**
(`HEADER_REPA_VIVA_HIST`, las 23 columnas en el orden confirmado tanto
en viva como en histórica) en vez de intentar extraerlo de la hoja, y se
toman TODAS las filas como datos (se filtran por `NOMBRE` no vacío, como
siempre). La fila con el header pisado entra como una fila más — su
`FECHA`/`NOMBRE`/`TIPO DE VEHICULO`/`TURNO` son reales (son los datos
que alguien tipeó ahí), pero sus columnas de `ESTADO DEL CHOFER` en
adelante van a mostrar el texto del título en vez de un valor real,
hasta que alguien del equipo corrija la hoja a mano (retipear la fila de
header en las columnas 1 a 7 de "Seguimiento Diario", sin tocar las
demás). Verificado: con el fix, "Operación en vivo" volvió a traer las
~160 filas reales del día, con Miguel Gomez visible en el Centro de
Alertas mostrando el dato corrupto de forma aislada (no afecta al resto).

### 20.2 "Seguimiento en ruta" — historial día por día

Hasta ahora "Seguimiento en ruta" (sección 19) solo mostraba "hoy"
(`todayISO()` fijo). Pedido explícito: poder ver también días
anteriores, igual que el resto del dashboard.

Se agregaron chips **Hoy / Ayer / Elegir fecha…** arriba de los chips de
zona (nuevo `#rutaFechaFiltro`, con un `<input type="date">` que aparece
solo con "Elegir fecha…", acotado entre `2026-09-17` —desde cuando se
guarda `envios_detalle`— y hoy). `fechaRutaActual()` resuelve qué fecha
ISO mostrar según el chip activo; `cargarChoferesEnRutaHoy()` ahora lee
`envios_detalle/<fecha>/choferes` de la fecha resuelta (no siempre
"hoy"), cacheando por fecha en `stateRuta.cachePorFecha` para no releer
Firestore al ir y volver entre fechas ya vistas — "Actualizar" fuerza
una relectura de la fecha actual. El título de la tabla ahora muestra la
fecha que se está viendo (`"Choferes en ruta — DD/MM"`), y el estado
vacío distingue entre "hoy, antes de la primera corrida intradía
(11hs ART)" y "un día pasado sin detalle guardado" (domingo no
operativo, o anterior al 2026-09-17).

**Bug real encontrado probando esto antes de enviarlo** (no llegó a
producción): al mover la carga de datos al cache por fecha, se dejó de
asignar `stateRuta.todasFilas` — la función de filtro por zona seguía
leyendo esa variable, que ya no se actualizaba nunca, así que cualquier
fecha distinta de la primera mostraba "Sin choferes en ruta" con 0 filas
aunque la lectura de Firestore sí hubiera traído datos reales. Corregido
asignando `stateRuta.todasFilas = todasFilas` antes de aplicar el filtro
de zona. Verificado con Playwright contra "Ayer" (131 choferes reales)
y una fecha elegida a mano, dos días atrás (137 choferes reales).

### 20.3 Bug real: "Sin zona" ganaba por paquetes sin localidad (2026-11-12, mismo día)

Reportado por el usuario: choferes que claramente reparten en una zona
reconocida aparecían como "Sin zona". Causa: LightData a veces no trae
la `Localidad` de algún paquete puntual (viene vacía) — y
`zonaPorLocalidad('')` devuelve `'Sin zona'` igual que una localidad
realmente no reconocida. En `construirFilaRutaDesdeItems()`, la zona del
chofer se elige por mayoría entre TODOS sus paquetes asignados — si
tenía varios paquetes sin ese dato, `"Sin zona"` podía juntar más votos
que la zona real, aunque el resto de sus paquetes sí tuvieran localidad
reconocida.

**Fix:** al elegir la zona más frecuente del chofer, `"Sin zona"` ahora
se ignora como candidata — gana la zona real con más paquetes, sea cual
sea su cantidad frente a los paquetes sin dato. Solo se devuelve `"Sin
zona"` cuando NINGÚN paquete del chofer tiene una zona reconocible (ni
por localidad vacía, ni por localidad no mapeada). Verificado con datos
reales del 2026-11-11: "Sin zona" bajó de varios choferes a solo 2 de
131 (los que de verdad no tienen ningún paquete clasificable).

Los 2 choferes que seguían quedando en "Sin zona" eran de **Zárate** y
**Campana** — localidades que no estaban en el listado original por
partido (sección 19.4). Confirmado por el usuario: van a **Zona
Norte**. Agregadas a `ZONA_POR_LOCALIDAD`; con esto, "Sin zona" bajó a
0 de 131 choferes reales del 2026-11-11.

### 20.4 Bug real en `publicar_firestore.py`: choferes con asignaciones "fantasma" (2026-11-12)

Reportado por el usuario: "Leyderman Martinez" y "Adriano Tovani"
aparecían en "Seguimiento en ruta" con paquetes asignados (14 y otro
número) y 0 entregados, pero al consultar LightData directamente no
tenían nada asignado ese día. Hipótesis del usuario, correcta: sus
envíos se habían reasignado a otro chofer durante el día.

**Causa real**, en `publicar_firestore.py` (no en el dashboard):
`publicar()` escribe un documento `envios_detalle/<fecha>/choferes/<id>`
por cada chofer que aparece en la corrida ACTUAL, pero nunca tocaba (ni
borraba) el documento de un chofer que en una corrida anterior tenía
envíos y después los perdió — como la corrida de las 20:00 ART no
vuelve a ver a ese chofer entre las claves de `detalle[fecha]` (tiene 0
filas), simplemente lo salteaba, y su documento quedaba para siempre
con la foto de la corrida vieja (ej. la de las 11:00, cuando sí tenía
14 envíos asignados). Como "Seguimiento en ruta" lee esa colección
completa sin filtrar por si el documento es reciente, mostraba esas
asignaciones fantasma como si fueran reales.

**Fix:** `publicar()` ahora arma `choferes_actuales` (el set de todos
los choferes con al menos un ítem en la corrida actual para esa fecha)
y, después de escribir sus documentos, recorre TODOS los documentos
existentes en `envios_detalle/<fecha>/choferes` y borra cualquiera que
no esté en `choferes_actuales` — `detalle[fecha]` es la verdad completa
y actual de esa fecha en el momento en que se reprocesa (el export se
vuelve a bajar entero, no es incremental), así que un chofer ausente
ahí genuinamente ya no tiene nada asignado ese día.

**Alcance de la corrección**: se autocorrige solo en los próximos días
hacia adelante, y en los últimos 3 días hacia atrás cada vez que corre
el cierre de las 00hs (la "ventana de repaso" de la regla #5 ya
reprocesa esos días igual). Para fechas más viejas que ya tienen
documentos fantasma y que no van a volver a reprocesarse solas, hace
falta un backfill manual (volver a correr `descarga_diaria.yml` con
`fecha` puntual para ese día) para que se limpien.

Backfill hecho a mano el mismo día para la semana en curso (lunes
2026-11-09 a jueves 2026-11-12, las 4 fechas con dato hasta ese momento)
— los 4 `workflow_dispatch` con `fecha` puntual corrieron con éxito.
Verificado contra Firestore: los documentos fantasma se borraron en los
4 días; donde el chofer sí tenía envíos reales esos días (ej. Leyderman
Martinez el 09/11 y 10/11), el documento se mantuvo intacto — el fix
distingue correctamente entre dato real y dato fantasma.

### 20.5 Tres ajustes de UX en "Seguimiento en ruta" (2026-11-12, mismo día)

Pedidos explícitos del usuario tras usar la pantalla con datos reales:

1. **Título + buscador de cada tabla, fijos al hacer scroll.**
   `.table-head` (el `<h3>` + el buscador, y el botón "Cerrar" en los
   paneles de detalle) pasó a `position:sticky; top:0` — se aplica a
   TODAS las tablas del dashboard (Ranking de choferes, Todos los
   repartidores, Choferes en ruta, los paneles de detalle), no solo a
   Ruta, por consistencia. Efecto secundario que hubo que corregir: el
   header de columnas de cada tabla (`thead`, ya `sticky` desde antes
   pero relativo a `.table-wrap`, un contexto de scroll distinto) quedaba
   tapado detrás del `.table-head` ahora también sticky — dos stickies
   compitiendo por el mismo `top:0` en marcos de referencia distintos.
   Se agregó `ajustarOffsetTheadSticky()`, que mide el alto real de cada
   `.table-head` y lo guarda en la variable CSS `--table-head-h` de su
   `.table-card`; el `thead` usa esa variable como su propio `top` en vez
   de `0`, así se pega justo debajo en vez de superponerse. Se vuelve a
   medir en `resize` y cada vez que algo con el atributo `hidden` cambia
   en la página (vía `MutationObserver`) — una tarjeta oculta mide alto 0,
   así que hace falta remedirla recién cuando se muestra.
2. **"Demorados ahora" limitado a ~10 filas visibles**, con scroll propio
   para el resto (`#rutaAlertasLista{ max-height:420px; overflow-y:auto }`)
   — antes la lista completa (hasta 13+ demorados en un día real) estiraba
   la página entera.
3. **Detalle de los envíos pendientes de un chofer**, mismo patrón que
   "Detalle de envíos" de Seguimiento de Envíos (sección 11): la celda
   "Faltan: N" de la tabla ahora es un botón clickeable (solo cuando
   `pendientes > 0`) que abre una tarjeta nueva (`#rutaDetalleCard`) con
   la lista de esos envíos puntuales (Tracking/Cliente/Localidad/Zona/
   Estado/Hora), buscador propio y botón "Cerrar". No pide nada a
   Firestore: `construirFilaRutaDesdeItems()` ahora también guarda
   `itemsPendientes` (los items de ese chofer que no están en
   `ESTADOS_ENTREGA_RUTA`) junto con el resto de la fila, así que el
   detalle sale de datos que ya estaban en memoria. Se cierra solo al
   cambiar de fecha (el detalle de una fecha vieja ya no tiene sentido
   tras cargar otra).

### 20.6 Bug real: el header de columnas de TODAS las tablas ordenables nunca llegó a quedar sticky (2026-11-12, mismo día)

El usuario reportó, con capturas de la pantalla real (no de una prueba), que
después del punto 20.5 el header de "Choferes en ruta" se veía roto al
scrollear: texto de una fila de datos superpuesto, mezclado, con la fila de
filtros por columna.

**Causa real:** la regla `thead th[data-key]{ position:relative; }`
(agregada mucho antes, sección 13.5, solo para que la flechita de orden
`::after` tuviera un contenedor posicionado) tiene más especificidad que
`thead th{ position:sticky; ... }`, así que GANA y pisa el `sticky` en
CUALQUIER columna ordenable — es decir, en la práctica, en casi todas las
columnas de casi todas las tablas del dashboard. Resultado real: la fila de
**filtros** (`tr.fila-filtros`, sin `[data-key]`) sí quedaba sticky, pero la
fila de **nombres de columna** (con `[data-key]` en casi todas sus celdas)
quedaba `position:relative`, es decir NO sticky — scrolleaba junto con los
datos, cruzándose con la fila de filtros (que sí estaba fija) y con las
filas de la tabla. Esto afectaba a TODO el dashboard desde que existen
columnas ordenables (sección 13.5, 2026-10-24), no solo a "Seguimiento en
ruta" — simplemente no se había notado antes porque recién el 20.5 agregó
el sticky de página que hizo que el usuario se quedara mirando el header
mientras scrolleaba.

**Fix:** se sacó el `position:relative` de esa regla — `position:sticky` ya
alcanza para que el `::after` tenga dónde posicionarse (cualquier valor de
`position` que no sea `static` sirve), así que no hacía falta forzarlo a
`relative` y pisar el sticky de la regla general.

Para que la fila de filtros (que sí es sticky, `tr.fila-filtros th`) quede
**debajo** de la fila de nombres de columna (también sticky) en vez de en
el mismo `top`, se agregó una segunda variable CSS, `--thead-row1-h`
(alto real de la primera fila del `thead`, medida por la misma función
`ajustarOffsetTheadSticky()` del punto 20.5, extendida para esto), y el
`top` de la fila de filtros pasó a ser `calc(var(--table-head-h) +
var(--thead-row1-h))`.

**Mejora de paso:** se encontró, probando con scroll real de mouse wheel
(no solo mediciones de geometría), que una fila cuyo nombre + el tag
"muestra chica" wrappeaba a 2 líneas quedaba casi el doble de alta que el
resto — al estar en la frontera exacta del scroll, un fragmento recortado
de esa fila quedaba asomando debajo del header fijo, con pinta de texto
roto (aunque la causa estructural ya estuviera arreglada). Se agregó
`tbody td:first-child{ white-space:nowrap; }` para que la primera columna
(nombre/tracking) nunca wrappee, manteniendo las filas a una altura
uniforme.

**Verificado:** con Playwright, simulando scroll real con la rueda del
mouse (`page.mouse.wheel`, no solo `scrollTop` por JS) sobre "Ranking de
choferes" (la tabla con más filas de prueba disponibles), comparando
capturas de pantalla antes/después del fix — la superposición de texto
visible en las capturas del usuario no se reproduce más; a lo sumo, en una
posición de scroll exacta "a mitad de fila", se ve un hairline de 1-2px
(normal en cualquier tabla con header sticky, invisible en scroll continuo
real). Smoke test completo de todas las pestañas sin errores de consola.

**Regla de proceso agregada explícitamente por el usuario:** antes de subir
cualquier cambio visual, hay que probarlo con una mirada de QA de
UX/UI — no alcanza con verificar que la geometría calculada da el
resultado esperado en abstracto (eso fue lo que falló en 20.5: medir con
`getBoundingClientRect()` y dar por buena una conclusión sin haber
reproducido el gesto real de un usuario scrolleando con la rueda del
mouse). Antes de cada publish: (1) reproducir el caso con el mismo gesto
que usaría una persona real (scroll con rueda, no solo `scrollTop` por
JS), (2) sacar una captura de pantalla real del resultado y mirarla, no
solo confiar en números, (3) si algo se ve raro en la captura, no
descartarlo como "artefacto de la herramienta" sin antes probar con un
gesto de usuario real — la vez anterior (sección "Current Work" de la
sesión previa) se concluyó erróneamente que una superposición vista en una
captura era un artefacto de Playwright, cuando en realidad era este bug
real.

### 20.7 Bug real (segunda vuelta, mismo día): el offset del header quedaba mal cuando se scrollea la TABLA en vez de la página

El usuario reportó, de nuevo con captura real (en "Choferes en ruta"), que
el header de columnas seguía viéndose separado de los envíos — "no es una
cabecera de tabla", con una fila de datos completa asomando por ENCIMA del
bloque título+header, como si el header flotara en el medio de la tabla en
vez de pegado arriba.

**Causa real (distinta de 20.6, aunque en la misma zona de código):** el
offset `--table-head-h` (que el `thead` usa para no quedar tapado por el
`.table-head` sticky-a-la-página) se calculaba UNA sola vez al cargar la
página y se daba por hecho que, siempre que el usuario scrollee lo
suficiente como para que el `thead` necesite ese offset, el
`.table-head` YA está pegado arriba del todo (ocupando esos mismos
píxeles). Eso es cierto si el usuario scrollea la PÁGINA — pero no es
cierto si el usuario scrollea la TABLA directamente (posando el mouse
sobre la tabla y usando la rueda, el gesto más natural cuando una tabla
tiene su propio scroll interno por `max-height`): ahí el scroll INTERNO de
`.table-wrap` arranca antes de que la página haya scrolleado lo suficiente
como para pegar el título. El `thead` igual reservaba el espacio del título
(como si ya estuviera pegado), dejando un hueco real donde se veía una fila
de datos completa de la tabla.

**Fix:** se reemplazó la medición fija por un `IntersectionObserver` con un
centinela de alto 0 (`.sticky-sentinel`) puesto justo antes de cada
`.table-head`. Mientras el centinela sigue siendo visible en el viewport,
`.table-head` todavía NO está pegado (está en su posición normal, más
abajo) y `--table-head-h` se fuerza a `0px` — así el `thead` se pega
directo arriba de `.table-wrap`, sin hueco. Recién cuando el centinela sale
del viewport **por arriba** (`!isIntersecting && boundingClientRect.top <
0`, para no confundirlo con que la tarjeta entera se scrolleó por abajo),
`.table-head` pasa a estar realmente pegado y ahí sí se activa el offset
real (su alto medido). Se autoactualiza con cualquier scroll — de la
página, de la tabla, o de ambos combinados — sin necesitar un listener de
scroll aparte ni volver a medir en cada resize.

**Verificado:** con el mismo gesto que reportó el usuario (mouse posado
sobre la tabla, `page.mouse.wheel` real, no `scrollTop` por JS) sobre
"Choferes en ruta" con datos reales de Firestore (127 choferes, no
mockeados) — el header ahora queda pegado directo contra el título sin
hueco visible en ningún punto del scroll. Smoke test completo sin errores.

### 20.8 Bug real (tercera vuelta, 2026-11-13): fila "fantasma" encima del header por `border-collapse` + sticky

El usuario volvió a reportar con captura real (de nuevo "Choferes en ruta",
scrolleando la tabla) una fila de datos completa pintada por ENCIMA del
header de columnas, con texto de otra fila fantaseándose detrás de la fila
de filtros — distinto de 20.6 y 20.7: la geometría (`getBoundingClientRect`)
de esos elementos ya daba bien (sin huecos, sin offsets mal calculados); el
problema era puramente de **pintado**, no de posición.

**Causa real:** `table{ border-collapse:collapse; }` combinado con celdas
`position:sticky` es un bug de renderizado conocido de Chrome — el modelo
de bordes colapsados pinta los bordes compartidos entre celdas por un
camino de compositing distinto al de una celda sticky normal, y durante un
scroll rápido (rueda del mouse o arrastre de la scrollbar interna de
`.table-wrap`) puede quedar una fila ya scrolleada pintada en una capa
vieja por encima del header, en vez de detrás — exactamente el síntoma
reportado. No se veía con scroll lento ni con `scrollTop` seteado por JS
(por eso las dos rondas anteriores no lo habían atrapado), solo con scroll
real a velocidad variable.

**Fix:** se cambió `border-collapse:collapse` por `border-collapse:separate;
border-spacing:0` en la tabla — visualmente idéntico acá porque ninguna
columna depende de bordes verticales compartidos (todos los bordes son
`border-bottom` por celda), pero saca a la tabla del camino de pintado roto.
De paso se subieron los `z-index` de las tres capas sticky (título 15→30,
header de columnas 10→20, fila de filtros 9→15) para darles más margen
contra cualquier otro elemento superpuesto, y se agregó `will-change:
transform` a las tres para que el navegador las mantenga en su propia capa
de composición (evita además el salto de un frame en scrolls muy rápidos).

**Verificado:** 25 rondas de scroll real (`page.mouse.wheel`) a velocidades
variables sobre "Choferes en ruta" con datos reales de Firestore (135
choferes), comprobando en cada ronda que ninguna fila visible quedara por
encima del header (`row.top < header.top`) — ninguna lo hizo. Smoke test
completo sin errores.

### 20.9 Rediseño: un solo contexto de scroll para el encabezado de tabla (2026-11-13)

Cuarto reporte del mismo síntoma, y el que dio con la causa de fondo. El
usuario aportó el dato que faltaba: **el error pasa scrolleando con la barra
de AFUERA (la de la página), no con la interna de la tabla**, y propuso la
solución correcta — poner la barra de columnas en el mismo bloque que el
buscador.

**Por qué 20.6, 20.7 y 20.8 no alcanzaron.** El diseño tenía las capas
fijas repartidas en **dos contenedores de scroll distintos**:

- `.table-head` (título + buscador): `sticky` respecto de la **página**.
- `thead th` + `tr.fila-filtros th`: `sticky` respecto del **scroll interno
  de `.table-wrap`** (su ancestro con `overflow`).

Son dos sistemas de coordenadas independientes. Para que el `thead` no
quedara tapado por el título, se le daba un offset (`--table-head-h`) igual
al alto del título. Pero ese offset solo es correcto cuando el borde
superior de `.table-wrap` coincide con el del viewport. Scrolleando la
página, ese borde se mueve: si `.table-wrap` arranca en y=100 y el título
está pegado ocupando y=0..62, el `thead` se posiciona en 100+62=162 y queda
una **franja de 62px entre y=100 e y=162 por donde se ven pasar las filas**
— la "fila fantasma" de todas las capturas. El offset correcto sería
`max(0, bordeInferiorDelTítulo − bordeSuperiorDelWrap)`, que cambia en cada
frame del scroll: imposible de sostener con una variable CSS estática, y con
un listener de scroll quedaría siempre un frame atrasado. Los tres intentos
anteriores corrigieron casos particulares de ese cálculo sin tocar el
problema estructural: **mientras haya dos contextos de scroll, siempre va a
existir una posición donde se separan.**

**Fix (estructural):** se eliminó el segundo contexto. El bloque título +
buscador (`.table-head`) pasó a vivir **dentro de `.table-wrap`**, el mismo
contenedor de scroll que la tabla, en las 6 tarjetas del dashboard. Ahora
las tres capas fijas se pegan al mismo borde y se apilan:

```
.table-wrap  (único contenedor de scroll: overflow x/y, max-height 600px)
  └─ .table-head      sticky top:0                                   z-30
  └─ thead tr         sticky top:var(--table-head-h)                 z-20
  └─ tr.fila-filtros  sticky top:calc(--table-head-h + --thead-row1-h) z-15
  └─ tbody            filas normales, pasan por detrás
```

Los offsets son simples sumas de altos medidos una vez, y son correctos
pase lo que pase con el scroll de la página, porque la página ya no
participa: scrollearla mueve la tarjeta entera, encabezado incluido, como
un bloque. `margin-bottom:0` en `.table-head` a propósito — cualquier
separación entre capas es una rendija por donde se ve pasar una fila.

Efecto secundario aceptado: el título ya no queda pegado al viewport al
scrollear la página (lo que se había pedido en 20.5). No se pierde nada
práctico, porque la tabla tiene scroll interno propio (`max-height`), así
que nunca hace falta scrollear la página para ver más filas — el buscador
queda fijo justo donde importa, mientras se recorre la tabla.

Se borraron el centinela, el `IntersectionObserver` y toda la lógica de
`configurarStickySentinels()` de 20.7: con un solo contexto quedaron de
más. `ajustarOffsetTheadSticky()` ahora solo mide los dos altos, y se le
agregó un `ResizeObserver` sobre el encabezado (en pantallas angostas el
buscador se reacomoda a dos líneas y cambia el alto).

**Verificado:** 111 mediciones automáticas sobre 3 tablas distintas
("Choferes en ruta" con 135 choferes reales, "Todos los repartidores",
"Ranking de choferes"), con scroll real de rueda — interno, de página, y
alternando entre los dos — en ventana de 900px y de 700px de alto.
Desalineación máxima entre las tres capas: **0px** en todos los casos
(antes el hueco llegaba al alto completo del título). También verificado a
390px de ancho (mobile), incluyendo scroll horizontal: el encabezado queda
pegado a la izquierda y cubre todo el ancho visible. Smoke test completo
sin errores de consola.

### 20.10 El contenedor principal pasó de 1180px a 1600px, para sacar el scroll horizontal de los listados (2026-11-13)

Pedido explícito del usuario, inmediatamente después de 20.9: con el
encabezado de tabla ya arreglado, señaló que los indicadores (todo el
contenido del dashboard) deberían usar el ancho real de la pantalla — con
un margen prudente a los costados — y que eso además sacaría el scroll
horizontal que varios listados seguían necesitando.

**Diagnóstico:** `.app{ max-width:1180px; }` topeaba el contenido mucho
antes de llegar al ancho real de cualquier monitor moderno (1920px,
1440px, etc.), dejando franjas de fondo vacías cada vez más grandes cuanto
más ancha la pantalla — y, adentro de esos 1180px, varias tablas con
muchas columnas (8 en "Choferes en ruta", 11 en "Ranking de choferes") ya
no entraban y quedaban con su propio scroll horizontal interno. Medido a
1920px de viewport antes del cambio: `.table-wrap` tenía 1106px
disponibles, pero "Choferes en ruta" necesitaba 1144px (38px de scroll) y
"Ranking de choferes" 1329px (223px de scroll).

**Fix:** `.app` pasó de `max-width:1180px` a `max-width:1600px`, con el
padding lateral de 20px a 32px (el margen "prudente" pedido). Por debajo de
880px (mobile) el padding vuelve a 20px — un margen fijo de 32px le come
una porción grande del ancho a una pantalla de teléfono, cosa que no pasa
en desktop.

**Verificado:** con el ancho real que la tabla necesita (medido con
`table.scrollWidth`, constante sin importar la ventana) contra el ancho
disponible en 1920 / 1536 / 1440 / 1366 / 1280px de viewport: "Choferes en
ruta" y "Todos los repartidores" ya no necesitan scroll horizontal en
ninguno de esos anchos. "Ranking de choferes" (11 columnas, la tabla más
ancha de todo el dashboard) dejó de necesitarlo desde 1440px hacia arriba
— por debajo de eso sigue con su scroll horizontal interno como respaldo,
esperable dada la cantidad de columnas que muestra a la vez. Se re-verificó
que el fix de 20.9 (header sticky sin desalineación) sigue intacto después
de este cambio, y smoke test completo sin errores.

### 20.11 "Pendientes" en Seguimiento en ruta: distinguir gestionado de sin resolver (2026-11-13)

Pedido explícito del usuario sobre el significado de negocio de
"Pendientes" (asignados − entregados) en "Choferes en ruta": no todos los
paquetes sin entregar son iguales. Si un chofer tiene 20 asignados, entregó
18, y los otros 2 quedaron en un estado como `Reprogramado por comprador`
o `Cancelado`, ese chofer **sí hizo su trabajo** — fue, gestionó el
paquete, y cerró el estado, simplemente no terminó en una entrega. El caso
que necesita seguimiento es el chofer que tiene paquetes pendientes en
**cualquier otro estado** (en camino, en planta, o cualquier cosa que no
sea un cierre real) — a ese hay que preguntarle qué pasó.

**Estados que cuentan como "gestionado"** (confirmados por el usuario):
`Nadie`, `Nadie 2DA visita`, `Reprogramado por comprador`, `Rechazado por
el comprador`, `Reprogramado por MELI`, `Cancelado`. Cualquier otro estado
que no sea `Entregado`/`Entregado 2DA visita` (ya contado como entrega
efectiva) ni uno de estos seis cuenta como **sin resolver**.

**Detalle importante encontrado al implementarlo:** los nombres de estado
de LightData no son 100% consistentes en mayúsculas — `renderIndicadoresMeli`
ya tenía la nota de que `reprogramado por meli` y `reprogramado por
comprador` vienen en minúsculas en los datos reales, a diferencia de
`Entregado`/`Cancelado`. Comparar tal cual (como primer intento) hubiera
clasificado esos dos estados reales como "sin resolver" por error — el
mismo tipo de bug silencioso de mayúsculas que ya pasó antes con otros
campos de LightData (secciones 19.x). Se agregó `normalizarEstado()`
(minúsculas + espacios colapsados) antes de comparar, igual que ya existe
`normalizarLocalidad()` para el mapa de zonas.

**Fix:**
- `construirFilaRutaDesdeItems()` separa `itemsPendientes` en
  `itemsSinResolver` (estado no gestionado) y guarda el conteo en
  `pendientesSinResolver`.
- El botón "Faltan: N" de cada chofer pasa a ser "Sin resolver: K" (rojo,
  con tooltip) cuando `K > 0`, o "Gestionados: N" (gris, sin alarma) cuando
  todos los pendientes de ese chofer ya están cerrados — "Faltan: 0" se
  mantiene igual cuando no hay ningún pendiente.
- El detalle que abre ese botón (misma tabla de siempre) marca cada fila
  con un punto rojo/verde según esté sin resolver o gestionado, y ordena
  los sin resolver primero.
- Nuevo KPI "Sin resolver" en la fila de indicadores de "Seguimiento en
  ruta", al lado de "Paquetes pendientes" (que se mantiene con el total
  sin entregar, sin cambios).

**Verificado contra datos reales** (135 choferes, 2026-11-12): de 398
pendientes totales, 186 clasificaron como sin resolver. Revisando el
detalle de un chofer con estados mixtos se confirmó que `reprogramado por
comprador` y `reprogramado por meli` (minúsculas, reales) clasifican
correctamente como gestionado, y un estado real no previsto (`En planta de
procesamiento`) clasifica correctamente como sin resolver — exactamente el
caso que la normalización de mayúsculas estaba previniendo. Smoke test
completo sin errores.

### 20.12 Bug real: la pantalla abierta no mostraba las corridas intradía sin recargar (2026-11-14)

Reporte del usuario: el Action "Descarga de LightData" corre bien cada ~20
minutos, pero si el dashboard ya estaba abierto en el navegador, los
cambios no se veían hasta hacer un refresh completo de la página — ni solo
ni con el botón "Actualizar" (parte superior derecha del título) lograban
mostrarlos. Dos bugs independientes, ambos de cacheo en el cliente — nada
del lado de Firestore/descarga estaba mal.

**Causa 1 — vista "Envíos":** `state.cache` guarda, por fecha, el
snapshot ya leído de `envios_daily/<fecha>` para no releer Firestore en
cada render. `refreshIndex()` solo vaciaba ese cache cuando la **lista de
fechas** del índice (`envios_index/index`) cambiaba — es decir, una vez
por día, cuando aparece una fecha nueva. Pero el documento de "hoy" se
**sobreescribe** en cada corrida intradía sin que la lista de fechas
cambie, así que el cache nunca se invalidaba durante el día: la pantalla
se quedaba mostrando para siempre el snapshot de la primera lectura de la
mañana. El botón "Actualizar" llamaba a `refreshIndex()` y después a
`render()`, pero como `refreshIndex()` nunca marcaba `cambio`, el cache
seguía intacto y `render()` repintaba los mismos datos viejos.

**Causa 2 — pestaña "Seguimiento en ruta":** el `setInterval` que
refresca solo la vista de "Seguimiento de Repartidores" cada `POLL_MS`
(45s) solo tenía ramas para los modos `'vivo'` e implícitamente
"cualquier otro" (que llamaba a `renderRepartidoresHistorico()`). El modo
`'ruta'` no tenía rama propia y caía en el `else`, refrescando la pestaña
de histórico en vez de releer Firestore para "Seguimiento en ruta" — esa
pestaña no se refrescaba nunca sola, ni siquiera cuando sí cambiaban los
datos.

**Fix:**
- `refreshIndex()` ahora borra de `state.cache` las entradas de "hoy" y
  de los 2 días anteriores (la misma ventana de 3 días que reprocesa el
  cierre de las ~00:01, sección 16) en **cada** llamada, no solo cuando
  cambia la lista de fechas. Los días fuera de esa ventana son definitivos
  y no necesitan invalidarse.
- El poll automático de la vista "Envíos" (`setInterval` de `init()`) pasó
  de renderizar solo si `cambio` era `true` a renderizar siempre — la
  invalidación de cache de arriba ya no depende de que aparezca una fecha
  nueva, así que hay que repintar en cada poll para que se note. El toast
  "Se detectaron datos nuevos" se sigue mostrando únicamente cuando sí
  apareció una fecha nueva.
- El poll de "Seguimiento de Repartidores" ahora tiene una rama explícita
  para `stateRepa.modo === 'ruta'` que llama a
  `renderRepartidoresRuta(true)` (forzado, igual que hace el botón
  "Actualizar" para este modo), en vez de caer en el `else` de histórico.

**Verificado con Playwright** contra el dashboard real (datos de
producción, servido localmente): se inyectó un valor cacheado "falso" en
`state.cache[hoy]` y se confirmó que `refreshIndex()` lo borra aunque el
índice no cambió; se confirmó que un click real en "Actualizar" ya no deja
ver ese valor falso; y se marcó con un centinela la entrada cacheada de
"hoy" en `stateRuta.cachePorFecha` estando en la pestaña "Seguimiento en
ruta", esperando los 45s reales del poll automático — el centinela
desapareció, confirmando que el poll ahora fuerza una relectura real de
Firestore para esa pestaña.

### 20.13 "Sin entregas aún" → "Sin Iniciar", y nuevo estado "Terminó" (2026-11-14)

Pedido explícito del usuario sobre los estados de ritmo de cada chofer en
"Seguimiento en ruta" (`calcularEstadoRuta()`, ver sección 18 y el
comentario junto a la función):

1. Renombrar la etiqueta "Sin entregas aún" a **"Sin Iniciar"** — mismo
   criterio de siempre (menos de 2 entregas registradas, todavía no hay
   ritmo que medir), solo cambia el texto.
2. Agregar un estado **"Terminó"** que evalúe si el recorrido ya se
   cerró, comparando la cantidad asignada contra la entregada — pero sin
   exigir el 100%: si al chofer le quedan pendientes pero ya los
   **gestionó** (ver `ESTADOS_PENDIENTE_GESTIONADO` / sección 20.11 —
   Nadie, Nadie 2DA visita, Reprogramado por comprador, Rechazado por el
   comprador, Reprogramado por MELI, Cancelado), el recorrido se considera
   terminado igual.

**Fix:** `calcularEstadoRuta(minEntreEntregas, asignados, pendientesSinResolver)`
ahora chequea primero si `asignados > 0 && pendientesSinResolver === 0` y,
si es así, devuelve `{ color: 'azul', label: 'Terminó' }` — esta condición
se evalúa **antes** que el ritmo y lo pisa, porque una vez cerrado el
recorrido, la velocidad con la que venía entregando ya no es relevante
(no tiene sentido mostrar "Demorado" a un chofer que ya terminó). El nuevo
color `azul` (`--azul: #2f80ed`) es intencionalmente distinto del semáforo
verde/amarillo/rojo de ritmo — "Terminó" no es parte de ese semáforo, es
un estado de cierre aparte, igual que "Sin Iniciar" (gris) ya lo era.

Efectos en cascada, para que "Terminó" no se mezcle con las métricas de
ritmo en curso:
- El KPI "% dentro de ritmo" (`renderRutaMiniKpis`) ahora excluye tanto
  "Sin Iniciar" como "Terminó" del denominador — antes solo excluía
  "Sin Iniciar" (gris).
- El filtro de columna "Estado" de la tabla pasó a listar
  `['Terminó','Óptimo','A tiempo','Demorado','Sin Iniciar']`.
- "Demorados ahora" y la lista de alertas siguen basados en
  `estadoColor === 'rojo'`, que un chofer "Terminó" nunca puede tener (la
  condición de "Terminó" se evalúa primero), así que no hizo falta
  tocarlos.

**Verificado con Playwright** contra los 133 choferes reales del
2026-11-13 ("Seguimiento en ruta" → Ayer): aparecen los 4 estados
`Demorado`, `Terminó`, `A tiempo`, `Sin Iniciar` (ningún chofer real cayó
en "Óptimo" ese día). De 133 choferes, 92 clasificaron "Terminó" — se
inspeccionó el detalle de 5 de ellos y los 5 muestran "Faltan: 0" o
"Gestionados: N" en la columna de pendientes, nunca "Sin resolver". Los
que sí tenían pendientes sin resolver (ej. las filas de depósito/REPRO*
que no son choferes reales, con 0 entregas y pendientes abiertos)
clasificaron correctamente como "Sin Iniciar" y no como "Terminó".

### 20.14 20.13 se separa en dos columnas: "Rendimiento" y "Estado" — y se corrige un recorte visual (2026-11-14)

El usuario, al ver 20.13 funcionando, pidió un rediseño: mezclar ritmo
(qué tan rápido entrega) y avance del recorrido (cuánto le falta) en una
sola columna "Estado" quedaba confuso. Pedido explícito:

1. La columna "Estado" vuelve a ser solo ritmo, con el nombre
   **"Rendimiento"** y 3 estados: `Demorado` (rojo), `A tiempo` (azul —
   antes amarillo), `Óptimo` (verde).
2. Columna nueva **"Estado"**, separada, con 4 valores sobre avance del
   recorrido: `Sin iniciar`, `En ruta`, `Termino sin pendientes`,
   `Termino con pendientes`.
3. Para hacer lugar a la columna nueva sin agrandar más la tabla (ver
   20.10), las columnas "Min. entre entregas", "Hora 1ª entrega" y
   "Paq./hora" se sacan de la grilla y pasan a un tooltip al pasar el
   mouse (o el foco de teclado) sobre el badge de "Rendimiento".
4. Ayudas tipo "ⓘ" en los encabezados de "Rendimiento" y "Estado"
   explicando qué significa cada valor.
5. Centrar las columnas de badge (Zona/Rendimiento/Estado) y corregir un
   recorte visual real, reportado con captura: el anillo dorado de foco
   del buscador "Buscar chofer…" se veía cortado en las tres esquinas de
   arriba.

**`calcularEstadoRuta()` vuelve a ser SOLO ritmo** (revierte el pisado de
20.13 — "Terminó" ya no vive acá):
```
Óptimo:   ≤ 5 min entre entregas   → verde
A tiempo: 6 a 20 min               → azul  (antes amarillo)
Demorado: > 20 min                 → rojo
sin datos (< 2 entregas)           → gris, label "Sin datos"
```

**`calcularEstadoRutaChofer(asignados, entregados, pendientes, pendientesSinResolver)`**
(nueva), evalúa avance contra lo asignado, sin mirar ritmo:
```
pendientesSinResolver === 0 →  pendientes === 0 ? "Terminó sin pendientes" (verde)
                                                  : "Terminó con pendientes" (azul)
si no: entregados === 0 && pendientesSinResolver === asignados → "Sin iniciar" (gris)
si no:                                                           "En ruta" (amarillo)
```
"Terminó con pendientes" es el mismo caso de negocio de 20.11/20.13 (el
chofer gestionó todo lo que le quedó, aunque no haya entregado el 100%) —
solo que ahora vive en su propia columna en vez de pisar el ritmo.

**Causa del recorte del buscador:** `.table-wrap` recorta con
`overflow:auto` (necesario para el scroll de la tabla, sección 20.9/20.10)
y `.table-head` tenía `padding:2px 0 10px` — 0px a los costados y solo 2px
arriba. El anillo de foco (`outline:2px` + `outline-offset:2px` ≈ 4px por
fuera del input) no entraba en ese margen y quedaba tapado por el recorte
de `.table-wrap`. Fix: `.table-head` pasó a `padding:8px 8px 10px` — el
alto real se sigue midiendo dinámicamente
(`ajustarOffsetTheadSticky`/`ResizeObserver`, sección 20.9), así que el
padding de más no desalinea las otras capas sticky (header de columnas,
fila de filtros).

**Tooltips sin recorte, a propósito con `position:fixed` + JS en vez de
`position:absolute` + CSS `:hover`:** `.table-wrap` recorta, y
`.table-head`/`thead th`/`tr.fila-filtros th` tienen `will-change:transform`
— eso también vuelve "contenedor de posicionamiento" a los descendientes
`position:fixed` (mismo efecto que un `transform`), así que un tooltip
metido ADENTRO de la tabla se recortaría en los bordes igual que pasó con
el buscador. Se agregó un único elemento `#tooltipFlotante`, hijo directo
de `<body>` (sin ningún ancestro con overflow ni transform de por medio,
igual que `#toast`), posicionado por JS (`mostrarTooltipFlotante()`) con
`getBoundingClientRect()` del disparador + corrección si se sale del
viewport. Cualquier elemento con `[data-tip="..."]` lo dispara al pasar el
mouse o llegar el foco (delegado sobre `document`, `mouseover`/`mouseout`/
`focusin`/`focusout`) — usado tanto por el badge de Rendimiento como por
los íconos "ⓘ" de los encabezados.

**El ícono "ⓘ" no dispara el ordenamiento del header:** `wireSortableTable`
delega el click/Enter/Espacio sobre `th[data-key]`; se agregó un guard
(`e.target.closest('.th-info')`) al principio de ambos handlers para que
tocar el ícono de ayuda (o llegar a él con Tab + Enter) no ordene la
columna por accidente.

**Otros ajustes en cascada:**
- El KPI "% dentro de ritmo" ahora excluye solo "Sin datos" (gris) del
  denominador — "Terminó" ya no es un valor de `estadoColor` (Rendimiento),
  así que no hace falta excluirlo ahí.
- La barra de "Progreso" (`repa-meter`) pasó a colorearse por
  `estadoRutaColor` (avance) en vez de `estadoColor` (ritmo) — tiene más
  sentido que el color de "cuánto llevo entregado" dependa de cuánto falta,
  no de qué tan rápido entrega.
- `COLUMNAS_FILTRO_RUTA` bajó de 8 a 6 entradas (se sacaron los 3 filtros
  de texto de las columnas que ya no están, se agregó un `select` nuevo
  para "Estado").
- Se sacó `tr.fila-demorado` (CSS muerto: dependía de `estadoColor ===
  'amarillo'`, que ya no existe en Rendimiento).

**Verificado con Playwright** contra los 133 choferes reales del
2026-11-13: aparecen los 4 valores de Rendimiento (`Demorado`, `A tiempo`,
`Óptimo`, `Sin datos`) y los 4 de Estado (`Sin iniciar`, `En ruta`,
`Terminó sin pendientes`, `Terminó con pendientes`); se confirmó
programáticamente que ningún chofer "Terminó sin pendientes" tiene otra
cosa que "Faltan: 0" y que todo "Terminó con pendientes" tiene
"Gestionados: N" (nunca "Sin resolver"); el tooltip del badge de
Rendimiento (hover real, no `title` nativo) quedó 100% dentro del viewport
al medir su `getBoundingClientRect()`; el click en el ícono "ⓘ" del header
"Estado" no cambió `aria-sort`, y un click real en el resto del header sí
lo cambió; y una captura de la zona del buscador confirma el anillo de
foco completo, sin cortes en ninguna esquina.

**Nota aparte, fuera del alcance de este cambio:** durante esta verificación
apareció un error real no relacionado (`TypeError` en
`renderAlertasListaRepa`, al abrir "Operación en vivo") — no tiene que ver
con "Seguimiento en ruta" ni con nada tocado hoy; reportado al usuario para
decidir por separado si se investiga.

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
| 2026-10-31 | Bug real (sección 13.6): la hoja "viva" de Repartidores cambió de esquema sin avisar — `ASISTE A DEPOSITO (SOPORTE)` pasó a llamarse `ASISTENCIA` y la columna `ALERTADO` quedó sin nombre de columna en el CSV publicado. Asistencia confirmada y Pallet retirado mostraban 0% todo el tiempo (con la cantidad de asignaciones de hoy bien calculada, lo que lo hacía parecer "no muestra datos de hoy") y el Centro de alertas siempre decía "Sin alertas". Sin ningún error de JS — reportado por el usuario a simple vista. Fix: `asisteRepa()` prueba los dos nombres de columna, y la columna de alertas se ubica por posición (siguiente a `ESTADO DEL CHOFER`) en vez de por nombre. |
| 2026-11-06 | La tarjeta "Entregas Efectivas" (sección 12) suma una sub-sección "Solo Flex de Mercado Libre" con el mismo % y números pero restringidos a envíos Flex (`Origen` = `"ML"` o `"ML TURBO"`, criterio confirmado con el equipo — no hay columna "Flex" explícita en el export). `publicar_firestore.py` agrega un sub-objeto `flex` (`{total, aRetirar, porEstadoHora}`) a cada snapshot diario; el dashboard lo agrega igual que el resto y aplica la misma fórmula de efectividad. Los snapshots publicados antes de este cambio no tienen ese campo, así que muestran "—" hasta que se reprocesen o se acumulen días nuevos. |
| 2026-11-11 | Sección 14: se escribió `descargar_lightdata_api.py`, una alternativa a la descarga por Playwright usando la API externa de LightData (`POST /externa/consultar-fecha`). Todavía NO está conectada al workflow — el endpoint devuelve "Empresa no habilitada" para la empresa 253 hasta que LightData lo habilite, y faltan validar varios mapeos de campo contra datos reales (ver sección 14). |
| 2026-11-11 | Sección 15: el workflow de descarga diaria pasó a correr dentro de una imagen Docker propia (`scripts/Dockerfile`, publicada por `build_imagen_ci.yml` en GitHub Container Registry) con Chromium/Playwright, LibreOffice y las dependencias de Python ya instalados, en vez de reinstalar todo eso en cada corrida. Pensado para bajar el tiempo de cada corrida de ~2 min a unos segundos y despejar el límite real que había para aumentar la frecuencia de refresco (el concurrency group del workflow deja solo una corrida en cola a la vez). No depende de que LightData habilite nada — es independiente del punto anterior. Confirmado en producción: 56 segundos de punta a punta. |
| 2026-11-11 | Sección 17: nuevo modo "🚚 Seguimiento en ruta" dentro de Repartidores — progreso (asignados vs. entregados), hora de la 1ª entrega, paquetes por hora, entregados antes de las 21hs vs. pendientes, y demora de cada chofer durante el reparto (no asistencia), con filtro por zona ML Flex, lista "Demorados ahora" y tabla ordenable con highlight visual para los demorados. La demora se mide contra el tiempo entre una entrega y la siguiente (criterio confirmado con soporte): ≤5 min óptimo, 6-20 a tiempo, >20 demorado. Corre sobre datos mockeados (`generarMockChoferesRuta()`) hasta definir una fuente real de progreso de ruta en vivo. |
| 2026-11-11 | Sección 18: se agregó una fila de filtros por columna (además de poder ordenar) en "Choferes en ruta", "Todos los repartidores" y "Ranking de choferes" — `<select>` para Zona/Turno/Estado, texto libre para el resto. Se unificó el estilo de los 4 buscadores de tabla del dashboard (antes cada uno tenía su propio input chico y sin estilo). Los mini-kpis de "Seguimiento en ruta" pasaron de grid a una sola fila compacta, con un ícono ⓘ por tarjeta explicando qué mide cada número. |
| 2026-11-11 | Sección 18.1: pasada de QA sobre lo anterior — se reemplazó el `<select>` nativo de los filtros de Zona/Turno/Estado por un combo propio (botón + listbox con el estilo del dashboard, ver sección 18.1), porque la lista desplegada de un `<select>` real no se puede estilar con CSS. Se corrigió que la fila de filtros desalineaba columnas en mobile (no copiaba `hide-mobile`), se arreglaron los `aria-label` (decían el nombre interno de la variable en vez del nombre visible de la columna), se agrandó un poco más el número de los mini-kpis en línea, y se corrigió un bug real preexistente: la fila "(sin chofer asignado)" del Ranking de choferes ignoraba el buscador y los filtros de columna. |
| 2026-11-11 | Sección 19: dos bugs reales corregidos antes de pasar a producción. (1) "Operación en vivo" no traía datos: `URL_REPA_VIVA` apuntaba sin `gid` explícito y, al cambiar la pestaña "por defecto" del documento publicado, empezó a servir en silencio una hoja de referencia ("Localidades") en vez de la operativa ("Seguimiento Diario") — más una fila en blanco antes del header real en esa hoja, que `filasAObjetosRepa()` tomaba como header y vaciaba toda la lectura. (2) "Seguimiento en ruta" pasó de datos mockeados a datos reales, leyendo `envios_detalle/<hoy>/choferes` (el mismo detalle por chofer de LightData que ya alimenta el resto del dashboard); se sacó la columna "Turno" porque LightData no la registra. |
| 2026-11-11 | Sección 19.3: corrección del criterio de zona del punto anterior — el campo `Zona` de LightData no era el criterio correcto (además de traer valores propios tipo "ZONA 1/2/3", resultó inconsistente: la misma localidad aparecía con distinta `Zona` en envíos distintos). El criterio real es el mapa de localidades ML Flex (CABA/Norte/Sur/Oeste) dado por el equipo. Se agregó `zonaPorLocalidad()` + un mapa de ~160 localidades reales a su partido y zona, aplicado sobre el campo `Localidad` de cada envío (no `Zona`). Cobertura verificada: de 116 choferes reales, solo 4 (3.4%) quedaron en "Sin zona". Los chips y el filtro de columna volvieron a ser fijos (el criterio es cerrado, no depende de lo que traiga LightData cada día). |
| 2026-11-11 | Sección 19.4: se reemplazó el mapa de localidades de 19.3 (armado contra lo visto un día puntual) por el listado completo y oficial que mandó el equipo, por partido y por cordón (1/2/3) — CABA 100% de barrios, Norte/Sur/Oeste con todas sus localidades principales. Cobertura verificada de nuevo: 4 de 122 choferes (3.3%) en "Sin zona". Única ambigüedad: "Villa Bosch" figuraba en el listado bajo dos partidos (San Martín y Tres de Febrero); se resolvió a Zona Norte (San Martín) por ser su partido administrativo real. |
| 2026-11-12 | Sección 20.1: otro bug real en "Operación en vivo"/"Histórico" (causa distinta de 19.1) — alguien tipeó los datos de un chofer directo en la fila de header de "Seguimiento Diario", pisando FECHA/NOMBRE/TIPO DE VEHICULO/TURNO. `filasAObjetosRepa()` ahora reconoce ese caso por otros fragmentos de columna que quedaron intactos (ESTADO DEL CHOFER, etc.) y usa un header fijo hardcodeado en vez de intentar leerlo de la hoja. |
| 2026-11-12 | Sección 20.2: "Seguimiento en ruta" ahora deja ver el historial día por día (antes solo mostraba "hoy") — chips Hoy/Ayer/Elegir fecha…, leyendo `envios_detalle/<fecha>/choferes` de la fecha elegida, con cache por fecha para no releer Firestore al ir y volver. De paso se encontró y corrigió, antes de subir, un bug real propio de este cambio: el filtro de zona quedó leyendo una variable que ya no se actualizaba, mostrando "0 choferes" en cualquier fecha que no fuera la primera cargada. |
| 2026-11-12 | Sección 20.3: bug real reportado por el usuario — choferes con paquetes en una zona reconocida igual aparecían como "Sin zona", porque LightData a veces no trae la `Localidad` de algún paquete puntual, y esos paquetes sin dato competían por mayoría contra la zona real. Ahora "Sin zona" se ignora al elegir la zona más votada del chofer; solo gana si NINGÚN paquete tiene zona reconocible. Verificado: "Sin zona" bajó a 2 de 131 choferes reales. |
| 2026-11-12 | Se agregaron Zárate y Campana a `ZONA_POR_LOCALIDAD` (Zona Norte, confirmado por el usuario) — eran los 2 choferes que seguían quedando en "Sin zona" tras el fix anterior. Con esto, 0 de 131 choferes reales del 2026-11-11 quedan sin zona. |
| 2026-11-12 | Sección 20.4: bug real en `publicar_firestore.py` (no en el dashboard) — un chofer que perdía todos sus envíos durante el día (reasignados a otro chofer) seguía mostrando en "Seguimiento en ruta" las asignaciones de una corrida anterior, porque `publicar()` nunca borraba el documento de un chofer ausente en la corrida actual. Ahora se borran los documentos de choferes que ya no tienen ningún ítem en la corrida actual de esa fecha. Se autocorrige hacia adelante y en los últimos 3 días (ventana de repaso); fechas más viejas con el dato fantasma necesitan un backfill manual. Se hizo el backfill manual de lunes a jueves de esa semana — verificado que se borró lo fantasma y se mantuvo lo real. |
| 2026-11-12 | Sección 20.5: tres ajustes de UX pedidos sobre "Seguimiento en ruta" (aplicados a todas las tablas del dashboard por consistencia) — título + buscador de cada tabla quedan fijos al hacer scroll (con un ajuste de offset para que no tapen el header de columnas, que es un sticky aparte); "Demorados ahora" se limita a ~10 filas visibles con scroll propio; y la celda "Faltan: N" de cada chofer ahora es clickeable y abre el detalle de esos envíos puntuales pendientes, mismo patrón que "Detalle de envíos" de la sección 11. |
| 2026-11-12 | Sección 20.6: bug real reportado por el usuario con capturas — el header de columnas de toda tabla ordenable nunca quedaba sticky de verdad (`thead th[data-key]{position:relative}` pisaba el `sticky`, sección 13.5), mientras la fila de filtros sí lo estaba; al scrollear se cruzaban y el texto se veía superpuesto. Se sacó ese `relative` innecesario y se agregó `--thead-row1-h` para que la fila de filtros se pegue debajo de la de nombres de columna (no en el mismo `top`). De paso, `tbody td:first-child{white-space:nowrap}` para evitar filas más altas de lo normal (nombre + tag "muestra chica" a 2 líneas) que hacían más visible el recorte normal de una fila a mitad de scroll. Verificado con scroll real de mouse wheel (no solo geometría) — la sesión anterior había descartado por error esta misma superposición como "artefacto de Playwright"; no lo era. |
| 2026-11-12 | Sección 20.7: segundo bug real reportado por el usuario el mismo día, también con captura — el header de columnas seguía viéndose "separado" del header de título en "Choferes en ruta" (una fila de datos asomaba por encima). Causa: `--table-head-h` se calculaba una sola vez asumiendo que el título siempre está pegado arriba cuando el `thead` lo necesita, cierto solo si se scrollea la página, no si se scrollea la tabla directamente (el gesto real del usuario). Se reemplazó por un `IntersectionObserver` con un centinela que detecta el momento real en que el título queda pegado, y solo ahí activa el offset. Verificado con scroll real de mouse wheel sobre datos reales (127 choferes). |
| 2026-11-11 | Sección 16: bug real corregido antes de extender el horario de corridas intradía — todo el cálculo de "hoy"/"ayer" usaba la fecha UTC cruda asumiendo que coincidía con la de Argentina, cierto solo entre las 14:00 y 21:00 UTC. Se corrigió restando 3 horas (ART=UTC-3) antes de calcular fecha/día de semana, tanto en `descarga_diaria.yml` como en `fecha_descarga.calcular_fecha_objetivo()`. Con el fix, se extendieron las corridas intradía hasta las 23:40 ART (antes 18:00) para seguimiento en vivo de repartidores, con 2 jobs de cron-job.org en vez de 1 (ver sección 16 para por qué). |
| 2026-11-13 | Sección 20.11: "Pendientes" de un chofer en "Seguimiento en ruta" ahora distingue gestionado (el chofer fue y cerró el paquete en un estado terminal — Nadie, Nadie 2DA visita, Reprogramado por comprador, Rechazado por el comprador, Reprogramado por MELI, Cancelado — aunque no haya sido una entrega) de sin resolver (cualquier otro estado, que sí necesita preguntarle al chofer qué pasó). Botón "Faltan: N" pasó a "Sin resolver: K" (rojo) o "Gestionados: N" (gris) según corresponda, nuevo KPI "Sin resolver" en los indicadores, y el detalle marca cada fila con un punto de color. Los estados de LightData no son consistentes en mayúsculas (`reprogramado por meli`/`reprogramado por comprador` vienen en minúsculas en los datos reales) — se normaliza antes de comparar para no clasificarlos mal. |
| 2026-11-13 | Sección 20.10: el contenedor principal del dashboard pasó de 1180px a 1600px de ancho máximo (con 32px de margen lateral en vez de 20px, 20px de nuevo en mobile) — pedido explícito del usuario para aprovechar el ancho real de pantallas anchas y, de paso, sacar el scroll horizontal que varios listados todavía necesitaban adentro del espacio angosto de antes. "Choferes en ruta" y "Todos los repartidores" dejan de necesitar scroll horizontal en cualquier ancho de escritorio común; "Ranking de choferes" (11 columnas, la tabla más ancha) lo dejó de necesitar desde 1440px hacia arriba, y por debajo mantiene su scroll horizontal interno como respaldo. |
| 2026-11-13 | Sección 20.9: rediseño del encabezado fijo de tabla, que resuelve de raíz los cuatro reportes seguidos (20.6 a 20.8 fueron parches a casos particulares). El dato clave lo aportó el usuario: el error aparecía scrolleando con la barra de la PÁGINA. Causa de fondo: el título+buscador estaba fijado respecto de la página y la cabecera de columnas respecto del scroll interno de la tabla — dos sistemas de coordenadas independientes, imposibles de mantener pegados con un offset fijo. Fix: el título+buscador pasó a vivir dentro del mismo contenedor de scroll que la tabla, así las tres capas fijas se apilan contra el mismo borde. Se borró el centinela/IntersectionObserver de 20.7, que quedó de más. Verificado con 111 mediciones automáticas sobre 3 tablas, dos alturas de ventana y mobile: 0px de desalineación. |
| 2026-11-13 | Sección 20.8: tercer bug real reportado por el usuario sobre el mismo header sticky, también con captura — una fila de datos se pintaba por encima del header de columnas al scrollear rápido la tabla. Causa, distinta de 20.6/20.7: `border-collapse:collapse` + celdas `position:sticky` es un bug de pintado conocido de Chrome. Se cambió a `border-collapse:separate; border-spacing:0` (visualmente idéntico, sin bordes verticales que dependieran del colapsado), se subieron los z-index de las tres capas sticky y se les agregó `will-change:transform`. Verificado con 25 rondas de scroll real a velocidad variable sobre datos reales (135 choferes), comprobando programáticamente que ninguna fila quedara por encima del header. |
| 2026-11-14 | Sección 20.12: bug real reportado por el usuario — con el dashboard ya abierto, las corridas intradía (cada ~20 min) no se veían en pantalla hasta hacer un refresh completo; ni solas ni con el botón "Actualizar". Dos causas de cacheo en el cliente: (1) `refreshIndex()` solo vaciaba `state.cache` cuando cambiaba la lista de fechas del índice, no cuando se sobreescribía el documento de "hoy" — ahora borra siempre las entradas de "hoy" y los 2 días anteriores (ventana de repaso). (2) el poll automático de "Seguimiento en ruta" no tenía rama propia y caía en la de "histórico" — ahora llama a `renderRepartidoresRuta(true)`. El poll de "Envíos" pasó a renderizar siempre, no solo cuando aparece una fecha nueva. Verificado con Playwright contra datos reales, incluyendo los 45s reales de espera del poll automático. |
| 2026-11-14 | Sección 20.13: pedido del usuario sobre el estado de cada chofer en "Seguimiento en ruta" — "Sin entregas aún" pasó a llamarse "Sin Iniciar" (mismo criterio: menos de 2 entregas), y se agregó el estado "Terminó" (azul), que pisa al semáforo de ritmo cuando al chofer no le quedan pendientes sin resolver — no exige haber entregado el 100%, un recorrido con pendientes pero todos gestionados (Nadie, Reprogramado, Cancelado, etc.) también cuenta como terminado. Se excluyó a "Terminó" (junto con "Sin Iniciar") del cálculo de "% dentro de ritmo", porque una vez cerrado el recorrido el ritmo con el que venía entregando deja de ser relevante. Verificado contra 133 choferes reales del 2026-11-13: 92 clasificaron como "Terminó" (todos con "Faltan: 0" o "Gestionados: N", nunca con pendientes sin resolver) y los que sí tenían pendientes sin resolver quedaron correctamente fuera de "Terminó". |
| 2026-11-14 | Sección 20.14: a pedido del usuario, 20.13 se separó en dos columnas — "Rendimiento" (solo ritmo: Demorado/A tiempo/Óptimo, "A tiempo" pasó de amarillo a azul) y "Estado" (solo avance: Sin iniciar/En ruta/Terminó sin pendientes/Terminó con pendientes). Para hacer lugar a la columna nueva, "Min. entre entregas"/"Hora 1ª entrega"/"Paq./hora" se sacaron de la grilla y pasaron a un tooltip al pasar el mouse sobre el badge de Rendimiento; se agregaron íconos de ayuda "ⓘ" en los encabezados; y se centraron las columnas de badge. De paso se corrigió un bug visual real con captura: el anillo dorado de foco del buscador se veía cortado en las esquinas de arriba (`.table-wrap` lo recortaba por falta de padding en `.table-head`). Los tooltips nuevos usan `position:fixed` posicionado por JS (no CSS `:hover`) para no toparse con el mismo recorte. |
