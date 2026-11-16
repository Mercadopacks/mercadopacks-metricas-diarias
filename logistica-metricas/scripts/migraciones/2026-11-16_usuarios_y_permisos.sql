-- Usuarios del dashboard beta + permisos por vista (pedido 2026-11-16).
--
-- El LOGIN sigue siendo 100% Supabase Auth (auth.users, email/password) —
-- esta tabla es METADATA sobre ese usuario (nombre, apellido, sector, qué
-- vistas del sidebar puede ver), enlazada 1 a 1 por auth_user_id.
--
-- Decisión de seguridad importante: esta tabla NO tiene política de
-- INSERT para `authenticated`. Dar de alta un usuario nuevo requiere crear
-- primero su cuenta en auth.users, y eso solo se puede hacer con la
-- service role key — por eso el alta pasa SIEMPRE por la Edge Function
-- `crear-usuario` (ver supabase/functions/crear-usuario/index.ts), nunca
-- insertando esta tabla a mano desde el navegador. Si se le diera INSERT a
-- `authenticated` acá, cualquier usuario logueado podría insertarse un
-- perfil con es_admin=true sin haber pasado el chequeo de esa función.
--
-- Editar un usuario YA existente (sector, vistas, admin, activo) sí se
-- hace directo desde el dashboard con un simple `.update()` — la política
-- de UPDATE de abajo exige que quien edita sea, él mismo, es_admin=true.
create table if not exists public.perfiles_usuario (
  id bigint generated always as identity primary key,
  auth_user_id uuid not null unique references auth.users(id) on delete cascade,
  nombre text not null,
  apellido text not null,
  email text not null unique,
  sector text,
  es_admin boolean not null default false,
  activo boolean not null default true,
  -- Claves válidas hoy (deben coincidir con las keys del objeto `vistas`
  -- en dashboard/beta/index.html): envios, fallidos, repa-ruta,
  -- repa-asistencia, repa-vivo, admin.
  vistas_permitidas text[] not null default '{}',
  created_at timestamptz not null default now()
);

alter table public.perfiles_usuario enable row level security;

grant select, update on public.perfiles_usuario to authenticated;
-- El service role (lo usa la Edge Function crear-usuario) necesita el
-- GRANT igual que cualquier otro rol — RLS solo filtra FILAS, no decide
-- si el rol puede tocar la tabla para empezar. `service_role` tiene
-- BYPASSRLS a nivel de Postgres, pero sin este GRANT explícito el INSERT
-- fallaba con "permission denied for table perfiles_usuario" (error real
-- 2026-11-16) porque nunca se le había dado permiso sobre esta tabla en
-- particular.
grant select, insert, update, delete on public.perfiles_usuario to service_role;

drop policy if exists "perfiles_usuario_select" on public.perfiles_usuario;
create policy "perfiles_usuario_select" on public.perfiles_usuario
  for select to authenticated using (true);

-- Solo un admin puede editar perfiles (el suyo o el de cualquier otro) —
-- sin esta condición, cualquier usuario autenticado podría otorgarse a sí
-- mismo es_admin=true o todas las vistas con un simple PATCH.
drop policy if exists "perfiles_usuario_update_admin" on public.perfiles_usuario;
create policy "perfiles_usuario_update_admin" on public.perfiles_usuario
  for update to authenticated
  using (exists (
    select 1 from public.perfiles_usuario p
    where p.auth_user_id = auth.uid() and p.es_admin
  ));

-- ---------------------------------------------------------------------
-- Paso manual único, a correr DESPUÉS de este script (no automatizado a
-- propósito — nadie más que vos debería decidir quién es el primer admin):
-- 1. Buscá tu propio auth_user_id:
--      select id, email from auth.users;
-- 2. Insertá tu perfil como admin (reemplazá los valores):
--      insert into public.perfiles_usuario
--        (auth_user_id, nombre, apellido, email, sector, es_admin, vistas_permitidas)
--      values
--        ('<tu-auth-user-id>', 'Tu Nombre', 'Tu Apellido', 'tu-email@dominio.com', 'Administración', true, '{}');
--    (a un admin las vistas_permitidas no le aplican — ve todo igual, ver
--    aplicarPermisosVistas() en el dashboard.)
-- 3. El resto de los usuarios que ya estaban logueados ANTES de esta
--    migración (sin perfil todavía) van a seguir viendo todo el sidebar
--    hasta que les crees su perfil desde Administración > Usuarios — es
--    un fail-open a propósito, para no dejar a nadie bloqueado el día del
--    deploy (ver cargarPerfilSesion() en el dashboard). Dales de alta su
--    perfil cuanto antes para que sus permisos queden realmente acotados.
