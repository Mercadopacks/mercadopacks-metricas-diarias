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

Última actualización: 2026-09-17.

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

## Historial de cambios

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
