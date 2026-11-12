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
        ├── requirements.txt         → dependencias de Python para los tres scripts
        └── tests/
            ├── test_estado_lightdata.py      → test de regresión del filtro de Estado (sin credenciales)
            ├── fixture_estado_select2.html   → página local que simula el campo real de LightData
            └── vendor/                        → jQuery + Select2 vendorizados para el test
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
  horarias, buscador y orden por columna). Al seleccionar un chofer, además
  se muestra el detalle fila por fila de sus envíos del período (tracking,
  cliente, localidad, zona, estado, hora de entrega — sin dirección exacta,
  ver reglas_de_negocio.md sección 11).
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
ver bloque `firebaseConfig` al inicio del `<script>`) y usa estas colecciones
de Firestore:
- `envios_index` (un solo documento, `index`) — la lista de fechas que tienen
  datos cargados.
- `envios_daily` — un documento por fecha (ID = fecha ISO, ej. `2026-08-31`)
  con el snapshot agregado de ese día (totales, buckets horarios, por chofer,
  por zona).
- `envios_detalle/<fecha>/choferes/<chofer>` — el detalle fila por fila de
  los envíos de ese chofer ese día (tracking, cliente, localidad, zona,
  estado, hora de entrega), para la vista de detalle del dashboard al
  seleccionar un chofer. **No incluye dirección exacta ni CP** — ver
  reglas_de_negocio.md, sección 11, sobre por qué.

Las reglas de Firestore están abiertas (lectura/escritura sin autenticación)
para estas colecciones — es una decisión consciente porque es una
herramienta interna sin sistema de login y lo que se guarda ahí son métricas
agregadas y datos operativos (no domicilios ni datos personales del
destinatario). Si el link llegase a filtrarse fuera del equipo habría que
revisar esto (agregar autenticación o cerrar las reglas) — y sobre todo
**nunca** agregar dirección/CP/teléfono/email del destinatario a ninguna
colección mientras las reglas sigan abiertas.

Reglas de Firestore vigentes (Firebase Console → Firestore Database →
Reglas):
```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /envios_index/{document} {
      allow read, write: if true;
    }
    match /envios_daily/{document} {
      allow read, write: if true;
    }
    match /envios_detalle/{fecha}/choferes/{chofer} {
      allow read, write: if true;
    }
  }
}
```

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

## Automatización de la descarga diaria

**Estado: en funcionamiento**, disparada desde un cron externo (ver más
abajo por qué no usa el `schedule` nativo de GitHub Actions).

LightData no tiene API ni URL fija de exportación — solo se puede descargar
el archivo iniciando sesión manualmente en el navegador. Por eso la
automatización usa **Playwright** para manejar un navegador real de forma
desatendida.

**Qué hace, cada 20 minutos de 11:00 a 23:40 ART + el cierre de las 00:00,
de lunes a sábado** (domingo no es día operativo — ver más abajo; horario
ampliado el 2026-11-11 para seguimiento en vivo de repartidores, antes
llegaba solo hasta las 18:00):
1. `scripts/descargar_lightdata.py` inicia sesión en LightData, filtra el
   listado de envíos SIN filtro de Estado (se necesitan todos los estados) y
   descarga el `.xls`. Las corridas intradía (11:00 a 23:40) piden el día
   **en curso** (una "foto" actualizada de lo que va del día); la corrida de
   las 00hs pide el día que **acaba de cerrar, y además los 2 días anteriores a ese**
   — una "ventana de repaso" de 3 días para que las entregas que tardan 1-2
   días en confirmarse (recibido el lunes, entregado el miércoles) se
   reflejen en la efectividad de su día de origen en vez de quedar
   congeladas para siempre en el número que tenían al momento del cierre
   original (ver reglas_de_negocio.md, regla #5).
2. `scripts/publicar_firestore.py` toma ese archivo, calcula exactamente el
   mismo snapshot que arma el dashboard en el navegador (mismas reglas de
   negocio, ver comentarios en el script) y lo publica en Firestore.
3. El dashboard no necesita ningún cambio para esto — lee de Firestore igual
   que cuando alguien carga un archivo a mano.

### Por qué el disparo NO es el `schedule` de GitHub Actions

Se probó primero con un cron nativo de GitHub Actions (`schedule:`), incluso
corriendo unos minutos después de la hora en punto para evitar congestión.
Se midió con la API de GitHub durante 5 días seguidos: la corrida programada
para las 03:17 UTC arrancaba siempre entre las 07:43 y las 08:25 UTC — **una
demora de 4h30' a 5h10', todos los días**, no un pico ocasional. Ese nivel de
demora hace inútil el objetivo de tener "fotos" del día a horarios puntuales.

La solución: el workflow (`.github/workflows/descarga_diaria.yml`) hoy solo
tiene trigger `workflow_dispatch` (se puede disparar a mano, y así es como
hay que probarlo), y se dispara puntualmente desde **cron-job.org**
(gratuito) llamando a la API de GitHub — ese tipo de disparo no pasa por la
cola de `schedule` y arranca casi al instante, igual que un click manual en
"Run workflow".

### Configuración de cron-job.org (una sola vez)

**1. Generar un token de GitHub** con permiso mínimo (solo disparar
workflows de este repo, nada más):
- `github.com/settings/personal-access-tokens/new` → **Fine-grained token**.
- Resource owner: `Mercadopacks`. Repository access: **Only select
  repositories** → `mercadopacks-metricas-diarias`.
- Permissions → **Actions**: Read and write. (No hace falta ningún otro
  permiso.)
- Generar y copiar el token (empieza con `github_pat_...`) — no se comparte
  por chat ni se guarda en el repo, solo va cargado en cron-job.org.

**2. Crear una cuenta gratuita en cron-job.org** y crear **3 cronjobs** con
horario personalizado ("Custom"). Todos con la misma configuración base:
- URL: `https://api.github.com/repos/Mercadopacks/mercadopacks-metricas-diarias/actions/workflows/descarga_diaria.yml/dispatches`
- Request method: `POST`
- Headers:
  - `Authorization: Bearer <el token generado en el paso 1>`
  - `Accept: application/vnd.github+json`
  - `Content-Type: application/json`
- Body (raw JSON):
  - 2 jobs ("Hoy — día" y "Hoy — noche"): `{"ref":"main","inputs":{"modo":"hoy"}}`
  - 1 job ("Ayer"): `{"ref":"main","inputs":{"modo":"ayer"}}`

**Horarios (en UTC, tal como los pide cron-job.org — sin offset de minutos,
porque cron-job.org no sufre la congestión que tiene GitHub). Actualizado
el 2026-11-11 a cada 20 minutos hasta las 23:40 ART — ver
reglas_de_negocio.md sección 16 para por qué son 2 jobs de "hoy" en vez
de 1 (el campo de día de la semana no puede ser distinto según el tramo
horario dentro de un mismo job):**

| Job | Minutos | Horas UTC | Día semana (UTC) | Representa en ART | `modo` |
|---|---|---|---|---|---|
| "Hoy — día" | 0, 20, 40 | 14-23 | Lunes a sábado | 11:00-20:40, lunes a sábado | `hoy` |
| "Hoy — noche" | 0, 20, 40 | 0-2 | Martes a domingo | 21:00-23:40, lunes a sábado | `hoy` |
| "Ayer" | 0 | 3 | Todos menos lunes* | Cierre 00:00 | `ayer` |

\* La corrida de las 00hs en realidad ocurre al arrancar el día siguiente y
cierra el día anterior — por eso se saltea el lunes (cerraría un domingo,
que no es día operativo) pero sí corre el domingo de madrugada (cierra el
sábado). El workflow además tiene una verificación propia que saltea solo
la corrida si el día a procesar termina siendo domingo, como red de
seguridad extra por si cron-job.org se configura distinto.

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

**Cómo probarlo a mano, o rehacer un día puntual (backfill):** pestaña
**Actions** del repo → workflow "Descarga de LightData" → botón **"Run
workflow"**. Dos campos:
- **`modo`**: `hoy` o `ayer` (o vacío, que por compatibilidad se comporta
  como `ayer`). Usalo para simular cualquiera de las 5 corridas.
- **`fecha`**: una fecha puntual en formato `YYYY-MM-DD` (ej. `2026-09-01`)
  para backfill — si se completa, ignora `modo` y tiene prioridad total.
  Esto es lo que hay que usar si un día quedó con datos calculados con una
  regla de negocio vieja (ej. antes de que se excluyera "A retirar" del %
  de efectividad): como el `.xls` crudo no se guarda en ningún lado, la
  única forma de corregir un día ya cargado es volver a descargarlo y
  recalcularlo así.

Un disparo manual arranca casi al instante (a diferencia de lo que pasaba
con el `schedule` nativo, ver más arriba). Si la corrida falla, el job sube
como *artifact* descargable una captura de pantalla del momento del error
(`error-descarga-lightdata`), para diagnosticar sin tener que repetirlo a
mano.

**Limitación conocida:** el selector de fecha del calendario de LightData se
probó seleccionando el día del mes directamente; si "ayer" cae en el mes
anterior (es decir, hoy es el día 1), el calendario podría necesitar navegar
un mes atrás antes de poder elegir ese día — este caso no se probó todavía.
Si el workflow falla puntualmente el día 1 de un mes, revisar
`seleccionar_dia()` en `descargar_lightdata.py` primero.

**Incidente conocido (2026-09-08/09):** el filtro "Estados del envio" de
LightData se guarda por cuenta en el servidor, no en el navegador — quedó
aplicado a "Pendientes" (posiblemente por una sesión manual de prueba en la
misma cuenta) y el dashboard mostró ~220 envíos de menos, con las entregas
más recientes ausentes, porque el `.xls` descargado ya venía filtrado a un
solo estado. Es un multi-select de Select2 (admite varios chips a la vez),
así que la corrección saca cualquier chip existente y elige "Todos" de
forma explícita en cada corrida — ver `seleccionar_estado_todos()` en
`descargar_lightdata.py`. El arreglo tuvo dos vueltas fallidas más antes de
encontrar la causa real (documentadas en los comentarios de esa función):
1. Select2 usa un id aleatorio distinto en cada carga de página para cada
   opción del desplegable — no se puede guardar ese id.
2. Sacar un chip existente deja el desplegable **ya abierto** solo; un
   click de más para "abrirlo" en realidad lo vuelve a cerrar (Select2
   alterna abierto/cerrado en cada click).
3. `get_by_role("option", ...)` de Playwright matchea tanto la opción
   visible de Select2 como el `<option>` nativo oculto del `<select>`
   original — hay que apuntar a la clase CSS específica de Select2.

Estos tres problemas se encontraron recién al reproducir el bug en una
página local con la librería real de Select2 (en vez de seguir probando a
ciegas contra la cuenta real) — ese mismo caso quedó como test de
regresión en `scripts/tests/test_estado_lightdata.py` (corre sin
credenciales ni conexión a LightData: `cd scripts/tests && python3
test_estado_lightdata.py`). Si se vuelve a tocar esta lógica, correr ese
test antes de subir cambios. Si vuelve a aparecer un desfasaje entre el
total del dashboard y el total que se ve en LightData para el mismo día,
este filtro es el primer lugar para revisar.

**Incidente conocido (2026-09-19):** los botones "Buscar/Filtrar" y
"Exportar" se ubicaban con un selector CSS estructural sin anclar
(`.row > div:nth-child(3) > ...`), que podía "escaparse" y matchear un
botón con la misma forma en **otro módulo** de la página. Pasó de verdad:
agarró "Descarga masiva choferes" (de Liquidación de Cobranzas) en vez del
botón de Envíos. Se probaron dos arreglos que NO funcionaron antes de
encontrar la causa real — `get_by_role("button", name="FILTRAR")` y
`get_by_text("FILTRAR")` fallaron porque estos botones **no tienen texto
accesible utilizable** (ni rol ni texto real que Playwright pueda
bindear). El arreglo correcto fue volver a grabar la interacción real con
`playwright codegen` y usar el selector estructural que esa herramienta
generó, pero **anclado al contenedor del módulo** (`#envios_listado > ...`
en vez de empezar directamente en `.row`) — así queda scopeado y no puede
agarrar nada de otro módulo. Se verificó en local con un fixture que
reproduce dos módulos de forma idéntica: el selector viejo matchea 2
elementos (ambiguo), el nuevo matchea exactamente 1.

Moraleja para el futuro: ante cualquier fallo de selector contra
LightData, la única forma confiable de arreglarlo es **grabar de nuevo con
`playwright codegen`** (nunca adivinar por una captura de pantalla ni por
patrones de otros elementos del script) — y si el selector que resulta es
estructural (no por texto/rol), verificar que esté anclado a un
contenedor específico del módulo, no empezando en una clase genérica como
`.row`.

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
| 2026-09-07 | La descarga no corre los domingos (no es día operativo, solo se acumulan "A retirar" y falsearía las métricas). Las 4 corridas intradía se restringieron a lunes-sábado; la corrida de las 00hs se restringió a saltear únicamente la madrugada del lunes (que cerraría el domingo) — sigue funcionando el resto de los días, incluida la madrugada del domingo, que cierra el sábado. |
| 2026-09-08 | Se midió con la API de GitHub que el `schedule` nativo de Actions demoraba 4h30'-5h10' TODOS los días (no un pico ocasional) — incompatible con el objetivo de fotos horarias. Se sacó el `schedule` del workflow y se pasó a disparar por `workflow_dispatch` desde un cron externo (cron-job.org, gratis) que llama a la API de GitHub — ese tipo de disparo no pasa por la cola de `schedule` y arranca casi al instante. Se agregó el input `modo` (hoy/ayer) al workflow, y una verificación propia que saltea la corrida si el día a procesar resulta ser domingo (red de seguridad además de la configuración de cron-job.org). |
| 2026-09-09 | Bug de datos incompletos: el filtro de Estado de LightData (que se guarda por cuenta en el servidor) le quedó aplicado a un valor distinto de "Todos", y el dashboard mostró ~220 envíos de menos con las entregas recientes ausentes. Se corrigió forzando la selección explícita de "Todos" en cada corrida — ver "Incidente conocido" más arriba. El fix se armó reproduciendo el bug en local con la librería real de Select2 (en vez de iterar a ciegas contra la cuenta real), lo que además dejó un test de regresión permanente (`scripts/tests/test_estado_lightdata.py`) que corre sin credenciales. |
| 2026-09-17 | Dos mejoras pedidas después de comparar contra LightData en producción: (1) "ventana de repaso" de 3 días en la corrida de cierre, para que las entregas que tardan días en confirmarse dejen de quedar excluidas para siempre de la efectividad de su día de origen; (2) detalle de envíos por chofer (tracking, cliente, localidad, zona, estado, hora de entrega) en `envios_detalle/<fecha>/choferes/<chofer>`, visible en el dashboard al seleccionar un chofer — sin dirección exacta del destinatario, por privacidad (reglas de Firestore abiertas). **Pendiente: agregar la colección `envios_detalle` a las reglas de Firestore en la consola de Firebase** (ver bloque de reglas más arriba) — sin eso, la escritura del detalle va a fallar silenciosamente. |
| 2026-09-19 | Los botones "Buscar/Filtrar" y "Exportar" se ubicaban con un selector estructural sin anclar, que se "escapó" y agarró un botón de otro módulo de LightData. Se probaron dos arreglos por texto/rol que no funcionaron (estos botones no tienen texto accesible real); el arreglo correcto fue volver a grabar con `playwright codegen` y anclar el selector estructural resultante al contenedor `#envios_listado` — verificado en local reproduciendo la ambigüedad del selector viejo contra el nuevo. Ver "Incidente conocido" más arriba. |
| 2026-10-01 | Bug de calendario en el límite de mes: `seleccionar_dia()` clickeaba el número de día en el mes que el date picker de LightData tuviera abierto por default, sin navegar. La corrida de cierre de las 00hs ART del 1° de octubre pidió los días 30/29/28 de septiembre, pero el calendario abría en octubre — como esos números de día también existen ahí, clickeó la fecha equivocada sin error visible, LightData devolvió 0 filas, y `envios_daily/2026-09-30`, `2026-09-29` y `2026-09-28` quedaron sin actualizar EN SILENCIO (GitHub Actions marcó esa corrida como "success" igual). Se agregó `navegar_a_mes()`, que lee el mes/año actual de los `<select>` nativos que Materialize mantiene ocultos y sincronizados (`select.orig-select-month`/`select.orig-select-year`) y navega con `button.month-prev`/`button.month-next` las veces que haga falta — con test de regresión sin navegador (`scripts/tests/test_navegacion_calendario.py`). Un primer intento asumió (a partir de una sola captura) que el picker era de Angular Material y leía el mes de un botón de texto; falló en producción con timeout apenas se probó — el picker real es el de Materialize CSS, confirmado inspeccionando el HTML real (no adivinado) antes de escribir el fix definitivo. Además, `publicar_firestore.py` ahora corta con error explícito si un archivo descargado no genera ningún snapshot o si el día que contiene no coincide con el día pedido, para que este tipo de falla silenciosa deje de pasar desapercibida. El primer backfill con este fix volvió a fallar en producción: resultó que LightData tiene más de una instancia del date picker en el DOM al mismo tiempo (`select.orig-select-month` resolvió a 2 elementos), algo que no se reprodujo en pruebas manuales — causa de fondo todavía sin confirmar. Se corrigió escaleando `navegar_a_mes()` y `seleccionar_dia()` al contenedor `.modal.open` (convención propia de Materialize para marcar cuál modal está activo), en vez de buscar los controles en toda la página — así deja de importar cuántas instancias viejas queden dando vueltas en el DOM. **Pendiente: backfill manual de 2026-09-28, 2026-09-29 y 2026-09-30** (workflow "Descarga de LightData" → Run workflow → input `fecha`, una corrida por cada día) ahora que este segundo fix está en `main`. |
| 2026-10-15 | Se agregaron 6 indicadores nuevos ("Envíos correctos", "Entregas pre 21", "Entregas post 21", "Envíos incorrectos", "Reprogramado post 21", "Demora") arriba de los KPIs principales del dashboard, replicando el panel "Mis métricas" que Mercado Libre comparte con los transportistas. Se calculan enteramente a partir de `porEstadoHora` (desglose por estado × franja horaria), que ya se guardaba desde antes — no hizo falta tocar la descarga ni la publicación. Ver `reglas_de_negocio.md` sección 12 para las definiciones exactas. |
| 2026-10-16 | Cada indicador ahora muestra "de TOTAL" junto a sus números, el bloque de definiciones/días cargados pasó a un link colapsable, y los 4 reportes que antes iban apilados (Entregas por hora, Cruce por hora, Por zona, Ranking de choferes) pasaron a ser pestañas. |
| 2026-10-23 | Se sacaron del todo los 4 KPIs originales (quedaron redundantes), "Envíos correctos" pasó a llamarse "Entregas Efectivas" con la definición del viejo KPI homónimo, y "Entregas Pre 21" ganó un % como valor principal (antes solo mostraba el total). El dashboard pasó de tema oscuro a tema claro (fondo gris clarito, tarjetas blancas, marca dorado/negro en títulos/bordes/botones) manteniendo el semáforo de puntualidad verde/amarillo/rojo sin cambios en los gráficos. De paso se corrigió un bug real preexistente: el cuadro de "filtros activos" se mostraba vacío con borde dorado aun sin filtros, porque su regla CSS tenía más especificidad que el atributo `hidden`. Ver `reglas_de_negocio.md` sección 12 para el detalle completo. |
| 2026-10-24 | Se agregó un segundo reporte al dashboard: **Seguimiento de Repartidores** (botones arriba para navegar entre los dos). Lee dos planillas de Google Sheets publicadas como CSV directo desde el navegador — sin Firestore ni automatización nueva, a pedido explícito. Dos modos ("Operación en vivo" con objetivo de asistencia según día de semana, Centro de alertas, flota confirmada por zona, heatmap zona × turno; y "Rendimiento histórico" con ranking de repartidores, heatmap de cuellos de botella y tabla completa) para separar monitoreo en vivo de análisis histórico. Se usó la skill de dataviz para la paleta de colores de los vehículos (validada contra daltonismo con el script de la skill). De paso se corrigió un bug real preexistente en todo el dashboard: `setChip()` sin acotar borraba la clase "active" de todos los `.chip` de la página en cada carga. Ver `reglas_de_negocio.md` sección 13 para el detalle completo, incluidas las limitaciones conocidas (score del ranking sin piso de muestra; hoja de disponibilidad de sábados conectada el mismo día, ver entrada siguiente). |
| 2026-10-24 | Se conectó la tercera hoja ("Listado de Choferes") para la disponibilidad de sábados — resultó ser otra pestaña del mismo documento de Google Sheets ya compartido (se había publicado "todo el documento", no solo una hoja), así que no hizo falta pedir un link nuevo. Los sábados, el dashboard ahora excluye del denominador de Asistencia confirmada / Pallet retirado a los repartidores marcados como no habilitados en el roster, y el objetivo de esos indicadores volvió a 95% (reemplaza el 70% de arranque que se usaba antes de tener el roster). Se agregó una nota debajo de los indicadores con la cantidad excluida cuando aplica. |
| 2026-10-24 | La tabla "Todos los repartidores" (Repartidores → Rendimiento histórico) ahora se puede ordenar haciendo click en cualquier columna (alterna ascendente/descendente, con una flecha dorada que marca cuál y en qué sentido) — antes los headers no hacían nada. Se aprovechó para revisar el resto del dashboard: "Ranking de choferes" (Envíos) ya tenía la lógica de orden pero sin ningún indicador visual, así que no se notaba que ya era clickeable; ahora también muestra la flecha. Ambas tablas comparten el mismo componente genérico (`wireSortableTable`/`ordenarPorClave`), documentado en `reglas_de_negocio.md` sección 13.5. |
| 2026-10-31 | Bug real en Repartidores: la hoja "viva" (editada a mano por el equipo de depósito) cambió el nombre de dos columnas sin avisar — `ASISTE A DEPOSITO (SOPORTE)` pasó a ser `ASISTENCIA`, y la columna de alertas quedó sin nombre en el CSV publicado. Asistencia confirmada y Pallet retirado mostraban 0% todo el tiempo aunque la hoja sí tuviera datos de hoy (eso lo hacía parecer "no muestra datos de hoy"), y el Centro de alertas siempre decía "Sin alertas". Se corrigió para que el dashboard tolere el cambio de nombre y ubique la columna de alertas por posición en vez de por nombre. Detalle completo en `reglas_de_negocio.md` sección 13.6. |
| 2026-11-06 | La tarjeta "Entregas Efectivas" (Envíos) ahora incluye una sub-sección "Solo Flex de Mercado Libre" con el mismo % y números de siempre pero limitados a envíos Flex. No hay columna "Flex" en el export de LightData, así que se usó `Origen` = `"ML"` o `"ML TURBO"` (criterio confirmado con el equipo). `publicar_firestore.py` agrega ese desglose a cada snapshot diario nuevo; los días ya publicados antes de este cambio muestran "—" en esa sub-sección hasta que se reprocesen. Detalle completo en `reglas_de_negocio.md` sección 12. |
| 2026-11-11 | Se escribió `descargar_lightdata_api.py`, una alternativa a la descarga por Playwright usando la API externa de LightData (`POST /externa/consultar-fecha`) — sin navegador, sin LibreOffice, pensada para que cada corrida del workflow tarde segundos en vez de minutos. Todavía no reemplaza a Playwright en producción: el endpoint devuelve "Empresa no habilitada" para la cuenta de Mercadopacks (hay que pedirle a LightData que lo habilite) y faltan validar algunos mapeos de campo contra datos reales. Detalle completo, incluidos los puntos pendientes de validar, en `reglas_de_negocio.md` sección 14. |
| 2026-11-11 | Independiente de lo anterior (no depende de LightData): el workflow de descarga diaria ahora corre dentro de una imagen Docker propia (Chromium/Playwright + LibreOffice + dependencias de Python ya instalados, publicada en GitHub Container Registry), en vez de reinstalar todo eso en cada corrida. Baja el tiempo de cada corrida de ~2 min a segundos. Detalle completo en `reglas_de_negocio.md` sección 15. |
| 2026-11-11 | Las corridas intradía se extendieron de "hasta las 18:00 ART" a "cada 20 minutos hasta las 23:40 ART" para seguimiento en vivo de repartidores. De paso se corrigió un bug real: todo el cálculo de "hoy"/"ayer" usaba la fecha UTC cruda asumiendo que coincidía con la de Argentina — cierto solo entre las 14:00 y 21:00 UTC, por eso nunca se había notado. Al extender el horario, las corridas de 21:00 a 23:40 ART caen en la madrugada del día UTC siguiente, y con el cálculo viejo se habrían saltado solas (o publicado bajo la fecha equivocada) en silencio. Corregido restando 3 horas antes de calcular fecha/día de semana. Detalle completo, incluido el nuevo esquema de cron-job.org (2 jobs de "hoy" en vez de 1), en `reglas_de_negocio.md` sección 16. |
| 2026-11-11 | Nuevo modo "🚚 Seguimiento en ruta" dentro de Repartidores (junto a "Operación en vivo" e "Histórico") — progreso (asignados vs. entregados), hora de la 1ª entrega, paquetes por hora, entregados antes de las 21hs vs. pendientes (para evaluar si el chofer va a terminar o no), y demora de cada chofer durante el reparto. La demora se mide contra el tiempo entre una entrega y la siguiente (≤5 min óptimo, 6-20 a tiempo, >20 demorado), no contra un horario planificado. Incluye filtro por zona (mapa de localidades ML Flex: CABA/Norte/Sur/Oeste), lista "Demorados ahora" para accionar rápido, y tabla ordenable con highlight visual (naranja/rojo). Distinto del modo "vivo" existente, que es asistencia (quién se presentó), no rendimiento en ruta. Corre sobre datos mockeados hasta definir una fuente real de progreso de ruta en vivo — ver `reglas_de_negocio.md` sección 17. |
| 2026-11-11 | Se agregó filtro por columna (además de poder ordenar) a "Choferes en ruta", "Todos los repartidores" y "Ranking de choferes" — `<select>` para columnas con pocos valores fijos (Zona/Turno/Estado), texto libre para el resto. De paso se unificó el estilo de los 4 buscadores de tabla del dashboard (antes cada uno era un input chico sin estilo propio), y los mini-kpis de "Seguimiento en ruta" pasaron a una sola fila compacta con un ícono ⓘ por tarjeta explicando qué mide cada número. Detalle completo en `reglas_de_negocio.md` sección 18. |
| 2026-11-11 | QA sobre el punto anterior: se reemplazó el `<select>` nativo de los filtros de Zona/Turno/Estado por un combo propio (botón + lista, con el estilo del dashboard) — la lista desplegada de un `<select>` real la pinta el sistema operativo/navegador y no se puede estilar con CSS, solo el recuadro cerrado. Se corrigió que esa fila de filtros desalineaba columnas en mobile, se mejoraron los `aria-label` (antes mostraban el nombre interno de la variable), se agrandó un poco más el número de los mini-kpis en línea, y se encontró/corrigió un bug real preexistente: la fila "(sin chofer asignado)" del Ranking de choferes se mostraba siempre, incluso con un filtro o búsqueda activo que no la incluía. Detalle completo en `reglas_de_negocio.md` sección 18.1. |
| 2026-11-11 | Antes de pasar a producción se encontraron y corrigieron dos bugs reales: "Operación en vivo" no traía datos porque el link de la hoja "viva" apuntaba (sin darse cuenta) a una pestaña de referencia en vez de a la operativa, y esa hoja además tenía una fila en blanco antes del header que vaciaba toda la lectura. De paso, "Seguimiento en ruta" pasó de datos mockeados a datos reales — ahora lee el detalle por chofer de LightData que ya alimenta el resto del dashboard (`envios_detalle/<hoy>/choferes`), sin la columna "Turno" (no es un dato que LightData registre). Detalle completo en `reglas_de_negocio.md` sección 19. |
| 2026-11-11 | Corrección sobre el punto anterior: la zona de "Seguimiento en ruta" se había calculado con el campo `Zona` de LightData, pero ese no es el criterio — el criterio real (confirmado con el equipo) es el mapa de localidades ML Flex (CABA/Norte/Sur/Oeste). Además esa zona de LightData resultó inconsistente (la misma localidad aparecía con distinto valor según el envío). Ahora se clasifica por la `Localidad` de cada envío contra un mapa de partidos armado y verificado con datos reales (solo 3.4% de los choferes del día quedan sin poder clasificarse). Detalle completo en `reglas_de_negocio.md` sección 19.3. |
| 2026-11-11 | Se reemplazó ese mapa de localidades por el listado oficial y completo que mandó el equipo (por partido y por cordón 1/2/3). Cobertura verificada de nuevo: 4 de 122 choferes (3.3%) sin poder clasificarse. Detalle completo, incluida la única ambigüedad encontrada ("Villa Bosch", resuelta a Zona Norte), en `reglas_de_negocio.md` sección 19.4. |
| 2026-11-12 | "Operación en vivo"/"Histórico" dejaron de traer datos de nuevo (causa distinta de la del 2026-11-11): alguien tipeó los datos de un chofer directo en la fila de encabezados de la hoja "viva" en Google Sheets. El dashboard ahora reconoce ese caso y usa un encabezado fijo en vez de intentar leerlo de la hoja — igual se recomienda corregir la fila de encabezados a mano en Sheets cuando puedan. Además, "Seguimiento en ruta" ahora deja ver días anteriores (chips Hoy/Ayer/Elegir fecha…), no solo la jornada en curso. Detalle completo en `reglas_de_negocio.md` sección 20. |
| 2026-11-12 | Bug real en "Seguimiento en ruta": algunos choferes aparecían como "Sin zona" aunque repartieran en una zona reconocida, porque LightData a veces no trae la localidad de algún paquete puntual y esos paquetes sin dato le ganaban por cantidad a la zona real. Corregido para que "Sin zona" solo se use cuando ningún paquete del chofer tiene zona reconocible. Detalle en `reglas_de_negocio.md` sección 20.3. |
| 2026-11-12 | Se agregaron Zárate y Campana al mapa de localidades (Zona Norte) — eran los 2 choferes que seguían quedando en "Sin zona" tras el fix anterior. Con esto, 0 de 131 choferes reales quedan sin zona. |
| 2026-11-12 | Bug real reportado por el usuario: algunos choferes aparecían en "Seguimiento en ruta" con paquetes asignados que ya no tenían en LightData (se habían reasignado a otro chofer durante el día). La causa estaba en `publicar_firestore.py`, no en el dashboard: nunca se borraba el documento de un chofer que se quedaba sin envíos de una corrida a la otra, así que quedaba con la foto de una corrida vieja para siempre. Corregido para que cada corrida borre los documentos de choferes que ya no tienen nada asignado. Se autocorrige en los próximos días y en los últimos 3 (ventana de repaso); días más viejos ya afectados necesitan un backfill manual. Detalle completo en `reglas_de_negocio.md` sección 20.4. |
