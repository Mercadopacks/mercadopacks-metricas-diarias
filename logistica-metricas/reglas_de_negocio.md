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
| 2026-11-11 | Sección 16: bug real corregido antes de extender el horario de corridas intradía — todo el cálculo de "hoy"/"ayer" usaba la fecha UTC cruda asumiendo que coincidía con la de Argentina, cierto solo entre las 14:00 y 21:00 UTC. Se corrigió restando 3 horas (ART=UTC-3) antes de calcular fecha/día de semana, tanto en `descarga_diaria.yml` como en `fecha_descarga.calcular_fecha_objetivo()`. Con el fix, se extendieron las corridas intradía hasta las 23:40 ART (antes 18:00) para seguimiento en vivo de repartidores, con 2 jobs de cron-job.org en vez de 1 (ver sección 16 para por qué). |
