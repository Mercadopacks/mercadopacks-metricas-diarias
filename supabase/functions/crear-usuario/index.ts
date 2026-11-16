// Edge Function: crea un usuario nuevo del dashboard beta.
//
// Es la ÚNICA forma de dar de alta un usuario, porque crear una cuenta de
// Supabase Auth requiere la service role key — una clave que nunca puede
// vivir en el navegador (con ella se saltea toda política RLS). Esta
// función corre en el servidor de Supabase, no en el navegador, así que
// puede usarla de forma segura (ver scripts/migraciones/2026-11-16_usuarios_y_permisos.sql
// para la tabla `perfiles_usuario` y por qué esa tabla no tiene INSERT
// habilitado para `authenticated`).
//
// Seguridad: antes de crear nada, valida que quien llama esté autenticado
// Y tenga es_admin=true en su propio perfil — sin este chequeo, cualquier
// usuario logueado podría invocar esta función igual (es un endpoint
// público, protegido solo por pedir un JWT válido) y darse de alta a sí
// mismo, o a otro, como admin.
import { createClient } from "jsr:@supabase/supabase-js@2";

// SUPABASE_URL, SUPABASE_ANON_KEY y SUPABASE_SERVICE_ROLE_KEY los inyecta
// Supabase automáticamente en toda Edge Function — no hace falta
// configurarlos a mano con `supabase secrets set`.
const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY")!;
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
  });
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS_HEADERS });

  try {
    const authHeader = req.headers.get("Authorization") || "";
    if (!authHeader) return json({ error: "Falta autenticación." }, 401);

    // Cliente "como el usuario que llama" (respeta RLS) — solo para
    // averiguar quién es y si tiene es_admin.
    const clienteLlamador = createClient(SUPABASE_URL, ANON_KEY, {
      global: { headers: { Authorization: authHeader } },
    });
    const { data: { user }, error: errUser } = await clienteLlamador.auth.getUser();
    if (errUser || !user) return json({ error: "Token inválido." }, 401);

    const { data: perfilLlamador, error: errPerfil } = await clienteLlamador
      .from("perfiles_usuario")
      .select("es_admin")
      .eq("auth_user_id", user.id)
      .single();
    if (errPerfil || !perfilLlamador || !perfilLlamador.es_admin) {
      return json({ error: "No tenés permiso para dar de alta usuarios." }, 403);
    }

    const body = await req.json();
    const { email, password, nombre, apellido, sector, vistas_permitidas } = body || {};
    if (!email || !password || !nombre || !apellido) {
      return json({ error: "Faltan campos obligatorios (email, password, nombre, apellido)." }, 400);
    }
    if (String(password).length < 6) {
      return json({ error: "La contraseña debe tener al menos 6 caracteres." }, 400);
    }

    // Cliente con service role — el único con permiso para crear usuarios
    // de Auth e insertar en perfiles_usuario.
    const admin = createClient(SUPABASE_URL, SERVICE_ROLE_KEY);
    const { data: nuevo, error: errCrear } = await admin.auth.admin.createUser({
      email,
      password,
      email_confirm: true, // no hay flujo de "confirmá tu email" — lo da de alta un admin, ya sabe que es real
    });
    if (errCrear) return json({ error: errCrear.message }, 400);

    const { error: errInsert } = await admin.from("perfiles_usuario").insert({
      auth_user_id: nuevo.user.id,
      nombre,
      apellido,
      email,
      sector: sector || null,
      vistas_permitidas: vistas_permitidas || [],
      es_admin: false,
      activo: true,
    });
    if (errInsert) {
      // Si falló guardar el perfil, no dejar una cuenta de Auth huérfana
      // (sin perfil) dando vueltas.
      await admin.auth.admin.deleteUser(nuevo.user.id);
      return json({ error: errInsert.message }, 400);
    }

    return json({ ok: true });
  } catch (e) {
    return json({ error: String(e) }, 500);
  }
});
