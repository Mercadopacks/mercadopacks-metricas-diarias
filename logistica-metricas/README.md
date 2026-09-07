# Métricas de Logística

Proyecto para transformar el export crudo de envíos (descargado del sistema
de gestión) en reportes de métricas: cantidad de envíos, entregas efectivas,
entregas antes de las 21hs, cancelados, y efectividad por chofer y por zona.

## Estructura

```
Mercadopacks - Metricas/       → raíz del repositorio git
├── index.html                 → redirige a dashboard/dashboard_logistica.html (URL limpia de GitHub Pages)
├── .gitignore                 → excluye los .xls crudos (tienen datos personales) del repo público
├── .github/workflows/
│   └── descarga_diaria.yml     → corre todos los días a las 00hs ART (ver sección de automatización)
└── logistica-metricas/
    ├── README.md               → este archivo
    ├── reglas_de_negocio.md    → definiciones oficiales de cada métrica (fuente de verdad)
    ├── diccionario_de_datos.md → qué significa cada columna del archivo crudo
    ├── datos_crudos/           → los .xls que vas descargando del sistema (NO se suben a git)
    ├── reportes/                → los .xlsx generados por el script (detalle/auditoría)
    ├── dashboard/
    │   ├── dashboard_logistica.html   → dashboard interactivo (ver sección abajo)
    │   └── assets/logo-mp.png          → logo de la empresa, embebido en base64 en el HTML
    └── scripts/
        ├── generar_reporte.py       → script que arma el reporte en Excel
        ├── descargar_lightdata.py   → automatización: login + descarga diaria del export
        ├── publicar_firestore.py    → calcula el snapshot del día y lo publica en Firestore
        └── requirements.txt         → dependencias de Python para los tres scripts
```

## Cómo usarlo

1. Descargá el export del sistema de logística y guardalo en `datos_crudos/`
   (el nombre que trae por defecto ya incluye fecha y hora, así que no hace
   falta renombrarlo).
2. Corré el script:

   ```bash
   cd scripts
   python3 generar_reporte.py ../datos_crudos/NOMBRE_DEL_ARCHIVO.xls
   ```

3. El reporte queda guardado en `reportes/reporte_<fecha_de_hoy>.xlsx`, con
   4 hojas:
   - **Resumen** — KPIs generales (total de envíos, % entregas efectivas, %
     antes de las 21hs, % cancelados).
   - **Por Chofer** — ranking de choferes por % de efectividad, con las
       entregas antes de corte y cancelaciones de cada uno. Los choferes con
       menos de 5 envíos en el período quedan marcados (`muestra_chica`) para
       no sacar conclusiones apuradas sobre poca data.
   - **Por Zona** — mismo desglose pero por zona geográfica.
   - **Detalle** — todas las filas originales con las columnas calculadas
     (`es_entrega_efectiva`, `es_antes_de_corte`, `es_cancelado`) para poder
     auditar o cruzar cualquier número contra el dato crudo.

   Si querés elegir vos el nombre/ubicación del archivo de salida:

   ```bash
   python3 generar_reporte.py ../datos_crudos/archivo.xls --salida ../reportes/reporte_semana_36.xlsx
   ```

### Requisitos

- Python 3 con `pandas`, `openpyxl` y (para leer `.xls` viejos) `xlrd`.
- LibreOffice instalado (el script lo usa automáticamente como respaldo si
  el `.xls` viene con el archivo interno corrupto — un problema que ya
  apareció con este sistema de origen y que el script maneja solo).

## Dashboard interactivo (`dashboard/dashboard_logistica.html`)

Esto es lo que gerencia y el equipo van a mirar día a día — no hace falta
correr nada ni saber Python. Es un único archivo HTML que se abre en
cualquier navegador.

**Qué hace:**
- Es un lector puro de Firestore — no procesa archivos en el navegador. Los
  datos los carga la automatización diaria (ver más abajo); el dashboard
  solo se encarga de mostrarlos.
- Muestra tarjetas de KPIs (total de envíos, % entregas efectivas, franja
  horaria de entrega, % cancelados), un gráfico de evolución o de entregas
  por hora según el período elegido, el cruce de entregas por franja
  horaria (antes de 21 / 21-22 / 22-23 / después de 23, con semáforo
  verde-amarillo-rojo, desglosado por **todos** los valores de `Estado` del
  archivo — no solo entregados), el desglose por zona (con la cantidad de
  cada segmento de la barra, no solo el total), y el ranking de choferes
  (con Pendientes, la cantidad de entregas en cada una de las 4 franjas
  horarias, buscador y orden por columna).
- Tiene selector de período: Hoy, Ayer, Últimos 7 días, Últimos 30 días, o
  un rango de fechas a elección. Al abrir el panel, elige automáticamente
  "Hoy" si ya hay datos del día, si no "Ayer", y si no el último día
  disponible.
- **Es interactivo:** hacer click en una zona, en una franja horaria del
  cruce, o en un chofer del ranking filtra el resto del panel a esa
  selección (con un aviso claro de qué filtro está activo y un botón para
  limpiarlo). Los detalles exactos de qué se puede cruzar con qué están en
  `reglas_de_negocio.md`, sección 9.

**Cómo se comparte con el equipo:** los datos quedan guardados en una base de
datos compartida (Firebase Firestore), cargados automáticamente todos los
días por la automatización (ver sección más abajo) — **cualquier persona que
entre a la URL pública ve los mismos datos**, sin que nadie tenga que subir
nada a mano.

**Dónde vive publicado:** el dashboard está alojado gratis en GitHub Pages,
en **https://mercadopacks.github.io/mercadopacks-metricas-diarias/** (repo:
`github.com/mercadopacks/mercadopacks-metricas-diarias`, público, dentro de
la organización `mercadopacks`). El HTML no necesita ningún proceso de
build — cualquier cambio que se pushea a la rama `main` se refleja solo en
esa URL en 1-2 minutos.

**Cómo funciona el guardado compartido:** el archivo `dashboard_logistica.html`
inicializa el SDK de Firebase (config del proyecto `mercadopacks-metricas`,
ver bloque `firebaseConfig` al inicio del `<script>`) y usa dos colecciones de
Firestore:
- `envios_index` (un solo documento, `index`) — la lista de fechas que tienen
  datos cargados.
- `envios_daily` — un documento por fecha (ID = fecha ISO, ej. `2026-08-31`)
  con el snapshot agregado de ese día (totales, buckets horarios, por chofer,
  por zona).

Las reglas de Firestore están abiertas (lectura/escritura sin autenticación)
para esas dos colecciones — es una decisión consciente porque es una
herramienta interna sin sistema de login y lo que se guarda ahí son métricas
agregadas, no datos personales de destinatarios. Si el link llegase a
filtrarse fuera del equipo habría que revisar esto (agregar autenticación o
cerrar las reglas).

**Qué NO hace (para que no haya sorpresas):**
- No tiene forma de cargar un archivo a mano — se sacó el botón de carga
  manual porque quedó redundante con la automatización diaria (ver más
  abajo). Si algún día la automatización falla y hace falta cargar un día
  puntual "a mano", hoy no hay una vía en el dashboard para eso (habría que
  reactivar ese código o correr `publicar_firestore.py` manualmente con el
  archivo correspondiente).
- No es "tiempo real" en el sentido de que empuje cambios al instante: el
  panel se refresca solo cada ~45 segundos para quienes lo tengan abierto (o
  pueden tocar "Actualizar" para forzarlo ya mismo). Para una métrica diaria
  esto es más que suficiente.
- Las definiciones de negocio están duplicadas a propósito en este archivo
  y en `scripts/generar_reporte.py` (JavaScript y Python no comparten
  código). Si cambiás una regla, hay que actualizarla en `reglas_de_negocio.md`
  y después replicarla en los dos lugares — está comentado en el código de
  ambos para que sea fácil de encontrar.
- Los `.xls` crudos (que traen nombre/teléfono/email del destinatario) **no
  se suben al repositorio de git** — está en `.gitignore` a propósito porque
  el repo es público. Quedan solo en la carpeta local `datos_crudos/` de quien
  los descarga.

## Automatización de la descarga diaria (GitHub Actions)

**Estado: en funcionamiento** — probado de punta a punta el 2026-09-02 (login,
filtro de fecha, descarga, cálculo del snapshot y publicación en Firestore,
visible en el dashboard sin que nadie suba nada a mano).

LightData no tiene API ni URL fija de exportación — solo se puede descargar
el archivo iniciando sesión manualmente en el navegador. Por eso la
automatización usa **Playwright** para manejar un navegador real de forma
desatendida, orquestado por **GitHub Actions** (gratis, no depende de que
una computadora quede prendida).

**Qué hace, 5 veces por día (hora Argentina): 11:00, 13:00, 15:00, 18:00 y
00:00** (en la práctica corre unos minutos después de esa hora — ver nota de
"por qué :17" en el propio workflow):
1. `scripts/descargar_lightdata.py` inicia sesión en LightData, filtra el
   listado de envíos SIN filtro de Estado (se necesitan todos los estados) y
   descarga el `.xls`. Las 4 corridas de 11 a 18hs piden el día **en curso**
   (una "foto" actualizada de lo que va del día); la corrida de las 00hs
   pide el día que **acaba de cerrar**.
2. `scripts/publicar_firestore.py` toma ese archivo, calcula exactamente el
   mismo snapshot que arma el dashboard en el navegador (mismas reglas de
   negocio, ver comentarios en el script) y lo publica en Firestore.
3. El dashboard no necesita ningún cambio para esto — lee de Firestore igual
   que cuando alguien carga un archivo a mano.

**Sobre las corridas intradía (11 a 18hs):** cada una vuelve a descargar el
día completo desde LightData y **reemplaza** el snapshot de ese día en
Firestore (no lo suma al anterior) — así el dashboard siempre muestra la
versión más actualizada de "hoy" sin datos duplicados ni acumulados de más.
Los días anteriores no se tocan: cada corrida solo escribe el documento de
la fecha que le corresponde. Un `concurrency` a nivel de workflow evita que
dos corridas se pisen si una se atrasa y se solapa con la siguiente.

El `.xls` descargado **no se guarda en el repositorio de git** (contiene
datos personales de destinatarios y el repo es público) — vive solo en el
runner de GitHub Actions durante esa corrida y se descarta al terminar; lo
que queda de forma permanente es el snapshot agregado en Firestore.

**Configuración necesaria (una sola vez), en
`github.com/mercadopacks/mercadopacks-metricas-diarias` → Settings → Secrets
and variables → Actions → New repository secret:**

| Secret | Valor |
|---|---|
| `LIGHTDATA_USER` | Usuario de LightData |
| `LIGHTDATA_PASS` | Contraseña de LightData |
| `FIREBASE_SERVICE_ACCOUNT` | El JSON completo de una service account de Firebase (Consola de Firebase → ⚙️ Configuración del proyecto → pestaña "Cuentas de servicio" → "Generar nueva clave privada") |

Estos tres valores quedan encriptados por GitHub y nunca aparecen en los
logs de las corridas, ni fueron compartidos en ningún chat al armar esto.
Ya están cargados y el workflow corre solo — no hace falta ninguna acción
manual salvo que alguno de los tres cambie (ej. se rota la contraseña de
LightData) o LightData cambie el diseño de su página.

**Cómo probarlo sin esperar al horario programado, o rehacer un día puntual
(backfill):** pestaña **Actions** del repo → workflow "Descarga diaria de
LightData" → botón **"Run workflow"** → en el campo **"fecha"** poner la
fecha a rehacer en formato `YYYY-MM-DD` (ej. `2026-09-01`) o dejarlo vacío
para que traiga "ayer" como en la corrida normal. Esto es lo que hay que
usar si un día quedó con datos calculados con una regla de negocio vieja
(ej. antes de que se excluyera "A retirar" del % de efectividad): como el
`.xls` crudo no se guarda en ningún lado, la única forma de corregir un día
ya cargado es volver a descargarlo y recalcularlo así. Si la corrida falla,
el job sube como *artifact* descargable una captura de pantalla del momento
del error (`error-descarga-lightdata`), para diagnosticar sin tener que
repetirlo a mano.

**Limitación conocida:** el selector de fecha del calendario de LightData se
probó seleccionando el día del mes directamente; si "ayer" cae en el mes
anterior (es decir, hoy es el día 1), el calendario podría necesitar navegar
un mes atrás antes de poder elegir ese día — este caso no se probó todavía.
Si el workflow falla puntualmente el día 1 de un mes, revisar
`seleccionar_dia()` en `descargar_lightdata.py` primero.

## Dónde están las definiciones

Cualquier duda de "¿esto cuenta como entregado?" o "¿por qué el corte es a
las 21 y no a las 20?" se responde en **`reglas_de_negocio.md`**, no en el
código. El script lee esas mismas reglas desde su sección `CONFIG` al
principio del archivo — si una definición cambia, se edita ahí y en el
`.md` al mismo tiempo.

## Cómo seguir escalando esto

Ideas para las próximas iteraciones, en orden sugerido:

1. **Cerrar las reglas pendientes** que quedaron abiertas en
   `reglas_de_negocio.md` (sección 5) a medida que haga falta decidir sobre
   ellas para un reporte real.
2. **Histórico comparable:** guardar cada reporte generado y armar una hoja
   o script aparte que compare período contra período (esta semana vs. la
   anterior, este mes vs. el pasado).
3. ~~**Automatizar la descarga**~~ — hecho: ver sección "Automatización de la
   descarga diaria" más arriba. Pendiente solo cargar los 3 secrets en GitHub
   para que empiece a correr.
4. **Alertas:** un chequeo simple que avise si algún chofer cae por debajo
   de cierto % de efectividad, o si el % de cancelados de la semana se
   dispara respecto del promedio.

## Historial de cambios del proyecto

| Fecha | Cambio |
|---|---|
| 2026-09-01 | Versión inicial: estructura de carpetas, diccionario de datos, reglas de negocio (entrega efectiva, corte 21hs, cancelados, efectividad por chofer) y script `generar_reporte.py`. |
| 2026-09-01 | Dashboard interactivo (`dashboard/dashboard_logistica.html`) con carga de archivo en el navegador, período, gráficos y ranking. |
| 2026-09-02 | Corrección de bug crítico de datos que desaparecían por fallos transitorios de lectura; gráficos reescritos en SVG nativo (sin dependencia de Chart.js). |
| 2026-09-02 | Franjas horarias de entrega (4 tramos), filtros interactivos por zona/franja/chofer, columna Pendientes, y rediseño con la paleta de marca. |
| 2026-09-02 | Ajustes de UX: al cargar un archivo el panel se posiciona solo en el rango de fechas de ese archivo; se sacó el mensaje de carga con el detalle de cantidad/fechas de la pantalla; se corrigieron los labels de la leyenda en "Evolución diaria" que se salían del margen; el cruce por hora de entrega ahora incluye todos los estados (no solo entregado); el gráfico por zona muestra la cantidad de cada segmento de la barra; el ranking de choferes muestra la cantidad de entregas en cada una de las 4 franjas horarias. |
| 2026-09-02 | Rebranding: el dashboard pasó a llamarse "Seguimiento de envíos - Mercadopacks" (antes "Torre de Control · Envíos") y el logo autogenerado (SVG con las letras "MP") se reemplazó por el isotipo real de la empresa (`dashboard/assets/logo-mp.png`, embebido en el HTML como base64 para mantener el archivo autocontenido). |
| 2026-09-02 | Se creó el repositorio git (`github.com/Agra95/mercadopacks-metricas`) y se publicó el dashboard en GitHub Pages (`agra95.github.io/mercadopacks-metricas`). El almacenamiento compartido se migró de `window.storage` (exclusivo de Claude.ai) a Firebase Firestore, para que el dashboard funcione como sitio independiente. Los `.xls` crudos (con datos personales de destinatarios) se excluyeron del repo vía `.gitignore` por ser un repo público. |
| 2026-09-02 | Automatización de la descarga diaria: `scripts/descargar_lightdata.py` (Playwright) inicia sesión en LightData y descarga el export de "ayer", `scripts/publicar_firestore.py` calcula el mismo snapshot que el dashboard y lo publica en Firestore, orquestados por `.github/workflows/descarga_diaria.yml` (cron 00hs ART). Se cargaron los secrets y se probó de punta a punta con éxito: la automatización queda operativa. |
| 2026-09-03 | Se cambió el cron de la automatización de `0 3 * * *` a `17 3 * * *` (correr unos minutos después de la hora en punto, no justo a las :00) para reducir la demora observada (~2hs) causada por la congestión típica de GitHub Actions en los horarios "en punto". |
| 2026-09-04 | Se trasladó el repositorio de la cuenta personal (`Agra95/mercadopacks-metricas`) a la organización `mercadopacks`, renombrado a `mercadopacks-metricas-diarias`. Nueva URL pública: **https://mercadopacks.github.io/mercadopacks-metricas-diarias/**. Los secrets de Actions y la configuración de GitHub Pages se mantuvieron intactos durante la transferencia. |
| 2026-09-04 | Se sacó la carga manual de archivo del dashboard (botón, drag&drop, parseo de `.xls` en el navegador con la librería XLSX) — quedó redundante con la automatización diaria. El dashboard pasó a ser un lector puro de Firestore. |
| 2026-09-04 | El % de entregas efectivas ahora excluye los envíos en estado "A retirar" del denominador (son envíos que todavía no llegaron al depósito), tanto en el KPI principal como en el ranking de choferes. Replicado en `publicar_firestore.py` y `generar_reporte.py` para mantener la paridad entre los tres lugares que calculan esta métrica. |
| 2026-09-04 | Se agregó soporte para "backfill" manual: el workflow de descarga diaria ahora acepta una fecha puntual (input `fecha` en "Run workflow") para rehacer un día ya cargado con reglas de negocio viejas, dado que el `.xls` crudo no se guarda en ningún lado y no hay otra forma de recalcularlo. Necesario porque los días cargados antes del cambio de "A retirar" quedaron con el % de efectividad viejo. |
| 2026-09-07 | La descarga pasó de correr 1 vez por día (00hs) a 5 veces (11, 13, 15, 18 y 00hs ART). Las 4 corridas intradía traen el día "en curso" y reemplazan (no acumulan) el snapshot de ese día en Firestore; la de las 00hs sigue cerrando el día anterior, sin cambios en esa lógica. Se agregó `MODO_FECHA=hoy\|ayer` a `descargar_lightdata.py` (el workflow decide el modo según qué cron disparó la corrida, no según la hora del reloj, para ser inmune a demoras de GitHub Actions) y un `concurrency` a nivel de workflow para que dos corridas nunca se pisen entre sí. |
