-- Módulo "Fallidos y Cambios" (dashboard/beta) — ver reglas_de_negocio.md
-- sección 21 y el análisis conversado con el usuario (2026-11-16).
--
-- Correr esto a mano en el SQL Editor del proyecto de Supabase del
-- ecosistema beta (el mismo que ya tiene `envios`/`parametros_*`).
--
-- Decisiones de diseño (no repetir el análisis acá, solo el resultado):
-- - Una sola tabla de seguimiento (`fallidos_seguimiento`), no 3 hojas
--   como en el Sheet viejo. Un paquete fallido que nadie tocó todavía NO
--   tiene fila acá — se cruza en vivo con `envios` filtrado por el mapeo
--   de estados. Solo se inserta fila cuando alguien actúa sobre el caso
--   (cambia estatus, o lo marca como duplicado).
-- - `id_interno` NO es único en esta tabla a propósito: un duplicado
--   (mismo paquete físico, un solo ID en Lightdata) genera una SEGUNDA
--   fila que referencia el mismo `id_interno`, en vez de datos propios.
-- - Antigüedad para el semáforo: envios.fecha_mercadopacks (día de
--   ingreso a depósito), no fecha_estado (confirmado con el usuario:
--   fecha_estado se actualiza con cada cambio de estado y no sirve para
--   medir cuánto tiempo lleva un paquete sin entregar).

-- El Estado de Lightdata NO define un Cambio: describe el paquete NUEVO que
-- se entrega, no si el chofer ya devolvió el producto ORIGINAL. La señal
-- real está en estas dos columnas de texto libre, sin estandarizar (ver
-- diccionario_de_datos.md) — se promueven del `raw` jsonb a columnas propias
-- para poder filtrarlas sin parsear jsonb en cada consulta del dashboard.
-- Quedan NULL en las filas ya cargadas hasta que se reprocesen (el upsert de
-- publicar_supabase.py las completa solo en la próxima corrida).
alter table public.envios add column if not exists logistica_inversa text;
alter table public.envios add column if not exists observaciones text;

create table if not exists public.fallidos_seguimiento (
  id bigint generated always as identity primary key,
  id_interno text not null references public.envios(id_interno),
  duplicado boolean not null default false,
  estatus text not null default 'pendiente'
    check (estatus in ('pendiente','devuelto_tienda','recibido_planta','descontar','cerrado_manual')),
  fecha_cierre date,
  motivo_cierre text,
  precio_descuento numeric,
  observaciones text,
  created_at timestamptz not null default now()
);
create index if not exists fallidos_seguimiento_id_interno_idx
  on public.fallidos_seguimiento(id_interno);

alter table public.fallidos_seguimiento enable row level security;
grant select, insert, update on public.fallidos_seguimiento to authenticated;
drop policy if exists "fallidos_seguimiento_select" on public.fallidos_seguimiento;
drop policy if exists "fallidos_seguimiento_insert" on public.fallidos_seguimiento;
drop policy if exists "fallidos_seguimiento_update" on public.fallidos_seguimiento;
create policy "fallidos_seguimiento_select" on public.fallidos_seguimiento
  for select to authenticated using (true);
create policy "fallidos_seguimiento_insert" on public.fallidos_seguimiento
  for insert to authenticated with check (true);
create policy "fallidos_seguimiento_update" on public.fallidos_seguimiento
  for update to authenticated using (true) with check (true);

-- Mapeo Estado (Lightdata) -> Tipo / Destino. Editable desde Administración
-- (mismo patrón ABM que Vehículos/Zonas/Localidades), copiado del Config
-- de la planilla vieja.
create table if not exists public.parametros_fallidos_mapeo (
  id bigint generated always as identity primary key,
  estado text not null unique,
  tipo text not null check (tipo in ('Fallido','Cambio')),
  destino text not null check (destino in ('Vuelve a salir','Devolver a tienda'))
);
alter table public.parametros_fallidos_mapeo enable row level security;
grant select, insert, update, delete on public.parametros_fallidos_mapeo to authenticated;
drop policy if exists "parametros_fallidos_mapeo_all" on public.parametros_fallidos_mapeo;
create policy "parametros_fallidos_mapeo_all" on public.parametros_fallidos_mapeo
  for all to authenticated using (true) with check (true);

insert into public.parametros_fallidos_mapeo (estado, tipo, destino) values
  ('Cancelado','Fallido','Devolver a tienda'),
  ('En camino reprogramado','Fallido','Vuelve a salir'),
  ('Nadie','Fallido','Vuelve a salir'),
  ('Nadie 2da visita','Fallido','Vuelve a salir'),
  ('No entregado','Fallido','Vuelve a salir'),
  ('Rechazado por el comprador','Fallido','Devolver a tienda'),
  ('Reprogramado por meli','Fallido','Vuelve a salir'),
  ('Cambio (con Logística Inversa)','Cambio','Devolver a tienda')
on conflict (estado) do nothing;

-- Umbrales de días del semáforo (3 filas fijas, solo edición — mismo
-- patrón que parametros_alertas, pero en días en vez de minutos).
create table if not exists public.parametros_alertas_fallidos (
  clave text primary key,
  valor_dias integer not null,
  descripcion text
);
alter table public.parametros_alertas_fallidos enable row level security;
grant select, update on public.parametros_alertas_fallidos to authenticated;
drop policy if exists "parametros_alertas_fallidos_select" on public.parametros_alertas_fallidos;
drop policy if exists "parametros_alertas_fallidos_update" on public.parametros_alertas_fallidos;
create policy "parametros_alertas_fallidos_select" on public.parametros_alertas_fallidos
  for select to authenticated using (true);
create policy "parametros_alertas_fallidos_update" on public.parametros_alertas_fallidos
  for update to authenticated using (true) with check (true);

insert into public.parametros_alertas_fallidos (clave, valor_dias, descripcion) values
  ('pedir', 2, 'A partir de cuántos días el caso pasa a "Pedir" (empezar a reclamarlo al chofer).'),
  ('prioridad', 3, 'A partir de cuántos días el caso pasa a "Prioridad".'),
  ('revisar', 5, 'A partir de cuántos días el caso pasa a "Revisar" (máxima urgencia).')
on conflict (clave) do nothing;
