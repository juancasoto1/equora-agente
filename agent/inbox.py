"""
agent/inbox.py — Panel de administración SaaS: inbox de conversaciones de Andrea
Login: POST /inbox/login  |  Acceso: /inbox  |  Logout: /inbox/logout
"""

# ══════════════════════════════════════════════════════════════════════════════
# DESIGN SYSTEM (Sprint visual refactor) — Tailwind CDN + Inter + Lucide + tema
# ══════════════════════════════════════════════════════════════════════════════
# Bloque compartido entre todas las plantillas HTML del panel. Inyectar dentro
# de <head> ANTES del <style> existente. No rompe estilos legacy — añade capa
# encima. El refactor de cada módulo irá reemplazando CSS legacy por utilities
# de Tailwind progresivamente.

_DESIGN_SYSTEM_HEAD = """
<!-- Voco Design System v1: Tailwind + Inter + Lucide -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.tailwindcss.com?plugins=forms,typography"></script>
<script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>
<script>
  /* Tema persistente — leer antes de pintar para evitar flash.
     Default = light si no hay preferencia guardada. */
  (function() {
    try {
      var saved = localStorage.getItem('voco-theme');
      var theme = saved || 'light';
      if (theme === 'dark') document.documentElement.classList.add('dark');
      document.documentElement.setAttribute('data-voco-theme', theme);
    } catch(e) {}
  })();

  /* Config Tailwind con tokens del Design System Voco */
  tailwind.config = {
    darkMode: 'class',
    theme: {
      extend: {
        fontFamily: {
          sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
        },
        colors: {
          /* Primario — Indigo */
          brand: {
            50:  '#eef2ff', 100: '#e0e7ff', 200: '#c7d2fe', 300: '#a5b4fc',
            400: '#818cf8', 500: '#6366f1', 600: '#4f46e5', 700: '#4338ca',
            800: '#3730a3', 900: '#312e81',
          },
          /* Acento — Emerald (éxito, activo) */
          accent: {
            50:  '#ecfdf5', 100: '#d1fae5', 400: '#34d399', 500: '#10b981',
            600: '#059669', 700: '#047857',
          },
          /* Superficie — Slate neutro */
          surface: {
            50:  '#f8fafc', 100: '#f1f5f9', 200: '#e2e8f0', 300: '#cbd5e1',
            400: '#94a3b8', 500: '#64748b', 600: '#475569', 700: '#334155',
            800: '#1e293b', 900: '#0f172a', 950: '#020617',
          },
        },
        boxShadow: {
          'voco-sm': '0 1px 2px 0 rgba(15, 23, 42, .04)',
          'voco':    '0 1px 3px 0 rgba(15, 23, 42, .06), 0 1px 2px -1px rgba(15, 23, 42, .04)',
          'voco-md': '0 4px 6px -1px rgba(15, 23, 42, .07), 0 2px 4px -2px rgba(15, 23, 42, .05)',
          'voco-lg': '0 10px 15px -3px rgba(15, 23, 42, .08), 0 4px 6px -4px rgba(15, 23, 42, .05)',
          'voco-xl': '0 20px 25px -5px rgba(15, 23, 42, .10), 0 8px 10px -6px rgba(15, 23, 42, .05)',
        },
        borderRadius: {
          'voco-sm': '6px', 'voco': '8px', 'voco-md': '10px',
          'voco-lg': '12px', 'voco-xl': '16px',
        },
      },
    },
  };
</script>
<style>
  /* Aplicar Inter como fuente base sin romper estilos legacy que usan -apple-system */
  body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
  /* Helper: hide en una clase para no depender de inline style */
  .voco-hidden { display: none !important; }
</style>
<script>
  /* Toggle de tema Voco — disponible en todas las plantillas */
  function vocoToggleTheme() {
    var root = document.documentElement;
    var isDark = root.classList.toggle('dark');
    var theme = isDark ? 'dark' : 'light';
    root.setAttribute('data-voco-theme', theme);
    try { localStorage.setItem('voco-theme', theme); } catch(e) {}
    if (window.lucide && typeof window.lucide.createIcons === 'function') {
      window.lucide.createIcons();
    }
  }
  /* Inicializar iconos Lucide al cargar la página */
  window.addEventListener('DOMContentLoaded', function() {
    if (window.lucide && typeof window.lucide.createIcons === 'function') {
      window.lucide.createIcons();
    }
  });
</script>
"""


def _voco_theme_toggle_html(extra_classes: str = "") -> str:
    """Genera el botón de toggle de tema con icono Lucide.
    Se puede insertar en cualquier header del panel."""
    return f"""
<button
  type="button"
  onclick="vocoToggleTheme()"
  title="Cambiar tema"
  aria-label="Cambiar tema claro/oscuro"
  class="inline-flex items-center justify-center w-9 h-9 rounded-voco
         text-surface-500 hover:bg-surface-100 dark:text-surface-400
         dark:hover:bg-surface-800 transition-colors {extra_classes}">
  <i data-lucide="sun"  class="w-4 h-4 hidden dark:inline-block"></i>
  <i data-lucide="moon" class="w-4 h-4 inline-block dark:hidden"></i>
</button>
"""


_THEME_TOGGLE_JS = """
/* Toggle de tema Voco — usar desde cualquier botón */
function vocoToggleTheme() {
  var root = document.documentElement;
  var isDark = root.classList.toggle('dark');
  var theme = isDark ? 'dark' : 'light';
  root.setAttribute('data-voco-theme', theme);
  try { localStorage.setItem('voco-theme', theme); } catch(e) {}
  /* Re-renderizar iconos Lucide que dependen del tema */
  if (window.lucide && typeof window.lucide.createIcons === 'function') {
    window.lucide.createIcons();
  }
}
/* Inicializar iconos Lucide al cargar la página */
document.addEventListener('DOMContentLoaded', function() {
  if (window.lucide && typeof window.lucide.createIcons === 'function') {
    window.lucide.createIcons();
  }
});
"""


_AUTH_STYLES = """
*{box-sizing:border-box;margin:0;padding:0}
body{min-height:100vh;background:#0f172a;display:flex;align-items:center;
     justify-content:center;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
.box{background:#1e293b;border-radius:16px;padding:40px 36px;width:360px;text-align:center;
      box-shadow:0 8px 40px rgba(0,0,0,.5);border:1px solid #334155}
.ic{font-size:2.8rem;margin-bottom:10px}
h2{color:#f1f5f9;font-size:1.15rem;font-weight:800;margin-bottom:4px}
.sub{color:#64748b;font-size:.82rem;margin-bottom:28px}
.err{color:#f87171;font-size:.82rem;display:block;margin-bottom:12px;
     background:#1a0a0a;border:1px solid #991b1b;border-radius:8px;padding:8px 12px;text-align:left}
.field{text-align:left;margin-bottom:14px}
.field label{display:block;font-size:.78rem;font-weight:600;color:#94a3b8;margin-bottom:5px}
input{width:100%;padding:11px 14px;border-radius:9px;border:1.5px solid #334155;
       background:#0f172a;color:#f1f5f9;font-size:.9rem;outline:none}
input:focus{border-color:#6366f1}
input::placeholder{color:#475569}
button{width:100%;padding:12px;border-radius:9px;border:none;
       background:linear-gradient(135deg,#6366f1,#8b5cf6);
       color:#fff;font-size:.93rem;font-weight:700;cursor:pointer;transition:opacity .2s;margin-top:4px}
button:hover{opacity:.88}
.alt-link{display:block;margin-top:18px;font-size:.8rem;color:#64748b;text-decoration:none}
.alt-link a{color:#818cf8;text-decoration:none}
.alt-link a:hover{text-decoration:underline}
"""


# ── Estilos comunes ampliados para login/registro ────────────────────────────
_AUTH_EXTRA = """
.pw-wrap{position:relative}
.pw-wrap input{padding-right:40px}
.pw-eye{position:absolute;right:12px;top:50%;transform:translateY(-50%);
  background:none;border:none;width:auto;padding:0;color:#64748b;cursor:pointer;
  font-size:1.1rem;line-height:1;margin:0;transition:color .15s}
.pw-eye:hover{color:#94a3b8}
.remember-row{display:flex;align-items:center;gap:8px;margin:8px 0 4px;text-align:left}
.remember-row input[type=checkbox]{width:15px;height:15px;cursor:pointer;accent-color:#6366f1}
.remember-row label{font-size:.8rem;color:#64748b;cursor:pointer;font-weight:400;margin:0}
.divider{display:flex;align-items:center;gap:10px;margin:20px 0 16px;color:#334155;font-size:.75rem}
.divider::before,.divider::after{content:'';flex:1;height:1px;background:#1e293b}
.social-btn{display:flex;align-items:center;justify-content:center;gap:10px;
  width:100%;padding:10px;border-radius:9px;border:1.5px solid #334155;
  background:#0f172a;color:#cbd5e1;font-size:.88rem;font-weight:600;
  cursor:pointer;transition:all .18s;margin-bottom:10px;text-decoration:none}
.social-btn:hover{border-color:#475569;background:#1e293b;color:#f1f5f9}
.social-btn svg{width:18px;height:18px;flex-shrink:0}
"""

# ── Página de login ──────────────────────────────────────────────────────────
def obtener_login_html(error: bool = False) -> str:
    err_html = (
        '<div class="mb-4 rounded-voco border border-red-200 bg-red-50 px-4 py-3 '
        'text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/40 dark:text-red-300">'
        'Credenciales incorrectas. Intenta de nuevo.</div>'
    ) if error else ''
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Voco — Iniciar sesión</title>
__VOCO_DS__
</head>
<body class="min-h-screen bg-surface-50 dark:bg-surface-950 text-surface-900 dark:text-surface-100 antialiased">

<!-- Toggle de tema esquina superior derecha -->
<div class="fixed top-4 right-4 z-10">
  <button type="button" onclick="vocoToggleTheme()" title="Cambiar tema"
    aria-label="Cambiar tema claro/oscuro"
    class="inline-flex items-center justify-center w-9 h-9 rounded-voco
      text-surface-500 hover:bg-surface-100 hover:text-surface-900
      dark:text-surface-400 dark:hover:bg-surface-800 dark:hover:text-surface-100
      transition-colors">
    <i data-lucide="sun"  class="w-4 h-4 hidden dark:inline-block"></i>
    <i data-lucide="moon" class="w-4 h-4 inline-block dark:hidden"></i>
  </button>
</div>

<main class="min-h-screen flex items-center justify-center px-4 py-12">
  <div class="w-full max-w-sm">
    <!-- Logo -->
    <div class="flex flex-col items-center mb-8">
      <div class="w-14 h-14 rounded-voco-xl bg-gradient-to-br from-brand-500 to-brand-700
        flex items-center justify-center shadow-voco-lg mb-4">
        <i data-lucide="zap" class="w-7 h-7 text-white"></i>
      </div>
      <h1 class="text-2xl font-bold tracking-tight">Voco</h1>
      <p class="mt-1 text-sm text-surface-500 dark:text-surface-400">
        Panel de Agentes IA para WhatsApp
      </p>
    </div>

    <!-- Card -->
    <div class="bg-white dark:bg-surface-900 rounded-voco-xl border border-surface-200
      dark:border-surface-800 shadow-voco p-6 sm:p-8">

      {err_html}

      <!-- Social login -->
      <div class="space-y-2.5">
        <a href="/auth/google"
          class="flex items-center justify-center gap-3 w-full px-4 py-2.5 rounded-voco
            border border-surface-300 dark:border-surface-700 bg-white dark:bg-surface-900
            text-sm font-medium text-surface-700 dark:text-surface-200
            hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors">
          <svg class="w-5 h-5 shrink-0" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
          </svg>
          Continuar con Google
        </a>
        <a href="/auth/facebook"
          class="flex items-center justify-center gap-3 w-full px-4 py-2.5 rounded-voco
            border border-surface-300 dark:border-surface-700 bg-white dark:bg-surface-900
            text-sm font-medium text-surface-700 dark:text-surface-200
            hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors">
          <svg class="w-5 h-5 shrink-0" viewBox="0 0 24 24">
            <path fill="#1877F2" d="M24 12.073C24 5.405 18.627 0 12 0S0 5.405 0 12.073C0 18.1 4.388 23.094 10.125 24v-8.437H7.078v-3.49h3.047V9.41c0-3.025 1.792-4.697 4.533-4.697 1.312 0 2.686.236 2.686.236v2.97h-1.514c-1.491 0-1.956.93-1.956 1.887v2.267h3.328l-.532 3.49h-2.796V24C19.612 23.094 24 18.1 24 12.073z"/>
          </svg>
          Continuar con Facebook
        </a>
      </div>

      <!-- Divider -->
      <div class="my-6 flex items-center gap-3">
        <div class="h-px flex-1 bg-surface-200 dark:bg-surface-800"></div>
        <span class="text-xs text-surface-400 dark:text-surface-500">o inicia con email</span>
        <div class="h-px flex-1 bg-surface-200 dark:bg-surface-800"></div>
      </div>

      <!-- Form -->
      <form method="POST" action="/inbox/login" class="space-y-4">
        <div>
          <label for="email" class="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-1.5">
            Email
          </label>
          <input type="email" id="email" name="email" placeholder="tu@email.com"
            autocomplete="email" autofocus required
            class="block w-full rounded-voco border-surface-300 dark:border-surface-700
              bg-white dark:bg-surface-950 text-surface-900 dark:text-surface-100
              placeholder:text-surface-400 dark:placeholder:text-surface-600
              shadow-sm focus:border-brand-500 focus:ring-brand-500 text-sm">
        </div>

        <div>
          <label for="pwd" class="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-1.5">
            Contraseña
          </label>
          <div class="relative">
            <input type="password" id="pwd" name="password" placeholder="••••••••"
              autocomplete="current-password" required
              class="block w-full rounded-voco border-surface-300 dark:border-surface-700
                bg-white dark:bg-surface-950 text-surface-900 dark:text-surface-100
                pr-10 shadow-sm focus:border-brand-500 focus:ring-brand-500 text-sm">
            <button type="button" id="eye1" onclick="togglePwd('pwd','eye1')"
              title="Mostrar contraseña"
              class="absolute right-2 top-1/2 -translate-y-1/2 inline-flex items-center
                justify-center w-7 h-7 rounded text-surface-400 hover:text-surface-700
                dark:hover:text-surface-200 transition-colors">
              <i data-lucide="eye" class="w-4 h-4"></i>
            </button>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <input type="checkbox" id="remember" name="remember" value="1"
            class="w-4 h-4 rounded border-surface-300 dark:border-surface-600
              text-brand-600 focus:ring-brand-500 dark:bg-surface-950">
          <label for="remember" class="text-sm text-surface-600 dark:text-surface-400 cursor-pointer">
            Mantener sesión iniciada
          </label>
        </div>

        <button type="submit"
          class="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-voco
            bg-brand-600 hover:bg-brand-700 active:bg-brand-800
            text-white font-semibold text-sm shadow-voco-sm transition-colors
            focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2
            dark:focus:ring-offset-surface-900">
          Entrar
          <i data-lucide="arrow-right" class="w-4 h-4"></i>
        </button>
      </form>

      <p class="mt-6 text-center text-sm text-surface-500 dark:text-surface-400">
        ¿No tienes cuenta?
        <a href="/auth/register" class="font-medium text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300">
          Regístrate gratis
        </a>
      </p>
    </div>

    <p class="mt-6 text-center text-xs text-surface-400 dark:text-surface-600">
      Voco · Tu agente de IA en WhatsApp
    </p>
  </div>
</main>

<script>
function togglePwd(inputId, btnId) {{
  var inp = document.getElementById(inputId);
  var btn = document.getElementById(btnId);
  var icon = btn.querySelector('i[data-lucide]');
  if (inp.type === 'password') {{
    inp.type = 'text';
    if (icon) {{ icon.setAttribute('data-lucide', 'eye-off'); window.lucide && window.lucide.createIcons(); }}
    btn.title = 'Ocultar contraseña';
  }} else {{
    inp.type = 'password';
    if (icon) {{ icon.setAttribute('data-lucide', 'eye'); window.lucide && window.lucide.createIcons(); }}
    btn.title = 'Mostrar contraseña';
  }}
}}
</script>
</body>
</html>"""
    return html.replace("__VOCO_DS__", _DESIGN_SYSTEM_HEAD)


# ── Página de registro ───────────────────────────────────────────────────────
def obtener_register_html(error: str = "") -> str:
    err_html = f'<div class="err">{error}</div>' if error else ''
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>Voco — Crear cuenta</title>
__VOCO_DS__
<style>{_AUTH_STYLES}{_AUTH_EXTRA}</style>
</head>
<body>
<div class="box" style="width:380px">
  <div class="ic">🔊</div>
  <h2>Crear cuenta en Voco</h2>
  <p class="sub">Empieza gratis · Sin tarjeta de crédito</p>
  {err_html}

  <!-- Botones sociales -->
  <a href="/auth/google" class="social-btn">
    <svg viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
    Registrarse con Google
  </a>
  <a href="/auth/facebook" class="social-btn">
    <svg viewBox="0 0 24 24"><path fill="#1877F2" d="M24 12.073C24 5.405 18.627 0 12 0S0 5.405 0 12.073C0 18.1 4.388 23.094 10.125 24v-8.437H7.078v-3.49h3.047V9.41c0-3.025 1.792-4.697 4.533-4.697 1.312 0 2.686.236 2.686.236v2.97h-1.514c-1.491 0-1.956.93-1.956 1.887v2.267h3.328l-.532 3.49h-2.796V24C19.612 23.094 24 18.1 24 12.073z"/></svg>
    Registrarse con Facebook
  </a>

  <div class="divider">o crea una cuenta con email</div>

  <form method="POST" action="/auth/register">
    <div class="field">
      <label for="nombre">Nombre completo</label>
      <input type="text" id="nombre" name="nombre" placeholder="Tu nombre"
             autocomplete="name" autofocus required>
    </div>
    <div class="field">
      <label for="email">Email</label>
      <input type="email" id="email" name="email" placeholder="tu@email.com"
             autocomplete="email" required>
    </div>
    <div class="field">
      <label for="pwd">Contraseña</label>
      <div class="pw-wrap">
        <input type="password" id="pwd" name="password" placeholder="Mínimo 8 caracteres"
               autocomplete="new-password" required minlength="8">
        <button type="button" class="pw-eye" onclick="togglePwd('pwd','eye1')" id="eye1" title="Mostrar contraseña">👁</button>
      </div>
    </div>
    <div class="field">
      <label for="confirm">Confirmar contraseña</label>
      <div class="pw-wrap">
        <input type="password" id="confirm" name="confirm_password" placeholder="Repite la contraseña"
               autocomplete="new-password" required>
        <button type="button" class="pw-eye" onclick="togglePwd('confirm','eye2')" id="eye2" title="Mostrar contraseña">👁</button>
      </div>
    </div>
    <button type="submit">Crear cuenta →</button>
  </form>
  <span class="alt-link">¿Ya tienes cuenta? <a href="/inbox/login">Inicia sesión</a></span>
</div>
<script>
function togglePwd(inputId, btnId) {{
  var inp = document.getElementById(inputId);
  var btn = document.getElementById(btnId);
  if (inp.type === 'password') {{
    inp.type = 'text';
    btn.textContent = '🙈';
    btn.title = 'Ocultar contraseña';
  }} else {{
    inp.type = 'password';
    btn.textContent = '👁';
    btn.title = 'Mostrar contraseña';
  }}
}}
</script>
</body>
</html>"""
    return html.replace("__VOCO_DS__", _DESIGN_SYSTEM_HEAD)


# ── Panel principal ──────────────────────────────────────────────────────────
_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<meta name="color-scheme" content="dark light">
<title>Voco · Panel del agente</title>
__VOCO_DS__
<style>
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;overflow:hidden}

/* ════════════════════════════════════════════════════════════════════
   VOCO Design System v1 — Variables del tema (light por defecto)
   ════════════════════════════════════════════════════════════════════ */
:root{
  /* Shell, navegación y áreas de admin (NO chat) */
  --voco-shell-bg:        #f8fafc;   /* surface-50 */
  --voco-nav-bg:          #ffffff;   /* white */
  --voco-nav-border:      #e2e8f0;   /* surface-200 */
  --voco-nav-text:        #475569;   /* surface-600 */
  --voco-nav-text-hover:  #0f172a;   /* surface-900 */
  --voco-nav-text-active: #4f46e5;   /* brand-600 */
  --voco-nav-bg-hover:    #f1f5f9;   /* surface-100 */
  --voco-nav-bg-active:   #eef2ff;   /* brand-50 */
  --voco-nav-section:     #94a3b8;   /* surface-400 */
  --voco-content-bg:      #ffffff;   /* white */
  --voco-content-bg-alt:  #f8fafc;   /* surface-50 */
  --voco-text:            #0f172a;   /* surface-900 */
  --voco-text-muted:      #64748b;   /* surface-500 */
  --voco-border:          #e2e8f0;   /* surface-200 */
  --voco-card-bg:         #ffffff;
  --voco-card-shadow:     0 1px 3px rgba(15,23,42,.06), 0 1px 2px rgba(15,23,42,.04);
  /* Acento (brand) */
  --voco-brand:           #4f46e5;   /* indigo-600 */
  --voco-brand-hover:     #4338ca;   /* indigo-700 */
  --voco-accent:          #10b981;   /* emerald-500 */
  --voco-red:             #ef4444;   /* red-500 */
  /* WA chat (siempre oscuro — estilo WhatsApp) */
  --sb:#202c33;--hd:#2a3942;--bbl:#005c4b;--bbr:#202c33;
  --az:#10b981;--tx:#e9edef;--ts:#8696a0;--bd:#313d45;--hl:#2a3942;--red:#e53935;
}

/* Tema oscuro */
html.dark{
  --voco-shell-bg:        #0f172a;   /* surface-900 */
  --voco-nav-bg:          #0b1220;   /* between 900 y 950 */
  --voco-nav-border:      #1e293b;   /* surface-800 */
  --voco-nav-text:        #94a3b8;   /* surface-400 */
  --voco-nav-text-hover:  #f1f5f9;   /* surface-100 */
  --voco-nav-text-active: #818cf8;   /* brand-400 */
  --voco-nav-bg-hover:    #1e293b;   /* surface-800 */
  --voco-nav-bg-active:   #1e1b4b;   /* indigo-950 */
  --voco-nav-section:     #475569;   /* surface-600 */
  --voco-content-bg:      #0f172a;
  --voco-content-bg-alt:  #1e293b;
  --voco-text:            #f1f5f9;
  --voco-text-muted:      #94a3b8;
  --voco-border:          #1e293b;
  --voco-card-bg:         #1e293b;
  --voco-card-shadow:     0 1px 3px rgba(0,0,0,.3), 0 1px 2px rgba(0,0,0,.2);
  --voco-brand:           #818cf8;
  --voco-brand-hover:     #a5b4fc;
}

/* ══════════════════════════════════════════════
   SHELL EXTERIOR: topbar + cuerpo
   ══════════════════════════════════════════════ */
#shell{display:flex;flex-direction:column;height:100vh;max-height:100vh;
  overflow:hidden;background:var(--voco-shell-bg);color:var(--voco-text);
  transition:background-color .15s, color .15s}

/* ── TOPBAR ── */
#topbar{
  height:56px;background:var(--voco-nav-bg);display:flex;align-items:center;
  padding:0 20px;gap:14px;flex-shrink:0;
  border-bottom:1px solid var(--voco-nav-border);
}
#topbar .logo{display:flex;align-items:center;gap:8px}
#topbar .logo-ic{width:32px;height:32px;background:var(--voco-brand);border-radius:8px;
  display:flex;align-items:center;justify-content:center;font-size:1rem;color:#fff}
#topbar .logo-txt{font-size:.95rem;font-weight:700;color:var(--voco-text)}
#topbar .logo-sub{font-size:.72rem;color:var(--voco-text-muted);margin-left:4px}
#topbar .badge{background:var(--voco-brand);color:#fff;font-size:.68rem;padding:2px 8px;
  border-radius:12px;font-weight:600;margin-left:4px}
.topbar-spacer{flex:1}
#logout-top{background:none;border:1px solid var(--voco-border);color:var(--voco-text-muted);
  border-radius:8px;padding:5px 14px;font-size:.78rem;cursor:pointer;
  transition:all .15s}
#logout-top:hover{border-color:var(--voco-text-muted);color:var(--voco-text)}

/* ── BODY: nav + main ── */
/* min-height:0 es CRÍTICO en flex column: sin él los hijos no encogen aunque
   el padre tenga overflow:hidden, porque min-height:auto (default) lo impide */
#body{display:flex;flex:1;overflow:hidden;min-height:0}

/* ── LEFT NAV ── */
#nav{
  width:220px;min-width:220px;background:var(--voco-nav-bg);display:flex;
  flex-direction:column;flex-shrink:0;border-right:1px solid var(--voco-nav-border);
  padding-top:8px;overflow:hidden;transition:background-color .15s;
}
.nav-section{padding:14px 16px 6px;font-size:.65rem;color:var(--voco-nav-section);
  text-transform:uppercase;letter-spacing:.08em;font-weight:600}
.nav-item{
  display:flex;align-items:center;gap:10px;padding:10px 18px;
  color:var(--voco-nav-text);cursor:pointer;font-size:.875rem;font-weight:500;
  transition:all .12s;border-left:3px solid transparent;user-select:none;
}
.nav-item:hover{background:var(--voco-nav-bg-hover);color:var(--voco-nav-text-hover)}
.nav-item.active{background:var(--voco-nav-bg-active);color:var(--voco-nav-text-active);
  border-left-color:var(--voco-nav-text-active);font-weight:600}
.nav-item .ni{font-size:1rem;width:22px;text-align:center;flex-shrink:0}
.nav-item .nb{font-size:.65rem;background:var(--voco-red);color:#fff;
  border-radius:8px;padding:1px 5px;font-weight:700;margin-left:auto}
.nav-footer{margin-top:auto;padding:16px 18px;border-top:1px solid var(--voco-nav-border)}
.nav-footer small{font-size:.7rem;color:var(--voco-nav-section)}

/* ── MAIN: contenedor de secciones ── */
#main{flex:1;overflow:hidden;display:flex;flex-direction:column;min-height:0}

/* Secciones (display:none por defecto) */
.sec{display:none;flex:1;overflow:hidden;min-height:0}
.sec.active{display:flex}

/* ══════════════════════════════════════════════
   SECCIÓN: CONVERSACIONES (dark WhatsApp theme)
   ══════════════════════════════════════════════ */
#sec-conversaciones{flex-direction:row;background:#0b141a}

/* sidebar conversaciones */
#sidebar{width:350px;min-width:350px;display:flex;flex-direction:column;
  background:var(--sb);border-right:1px solid var(--bd);min-height:0;overflow:hidden}
#chat-area{flex:1;display:flex;flex-direction:column;background:#0b141a;min-width:0;min-height:0;overflow:hidden}

@media(max-width:720px){
  #sidebar{width:100%;min-width:unset}
  #sidebar.oculto{display:none}
  #chat-area.oculto{display:none}
}

/* ══════════════════════════════════════════════
   SPRINT 3 — RESPONSIVE MÓVIL
   ══════════════════════════════════════════════ */
@media(max-width:768px){
  /* Nav lateral → barra inferior fija */
  #nav{
    position:fixed;bottom:0;left:0;right:0;
    width:100%!important;min-width:unset!important;
    height:58px;flex-direction:row;align-items:center;
    padding:0;border-right:none;border-top:1px solid #1e2e3d;
    z-index:500;overflow-x:auto;overflow-y:hidden;
  }
  .nav-section,.nav-footer{display:none}
  .nav-item{
    flex:1;flex-direction:column;align-items:center;justify-content:center;
    gap:2px;padding:6px 2px;border-left:none!important;
    border-top:3px solid transparent;min-width:52px;
    font-size:.58rem;letter-spacing:0;
  }
  .nav-item.active{border-top-color:var(--az);border-left-color:transparent!important}
  .nav-item .ni{font-size:1.3rem;width:auto}
  /* El badge en nav móvil */
  #esc-badge{position:absolute;top:4px;right:4px;font-size:.6rem;padding:0 5px}

  /* Body: espacio para la barra inferior */
  #body{padding-bottom:58px}

  /* Secciones: full width */
  .sec-light .sec-hdr{padding:12px 14px}
  .sec-hdr h1{font-size:1rem}

  /* Escalaciones: lista ocupa todo el ancho en móvil */
  #esc-sidebar{width:100%!important;min-width:unset!important}
  #esc-sidebar.mob-oculto{display:none!important}
  #esc-detalle.mob-oculto{display:none!important}
  #esc-detalle{position:fixed;top:0;left:0;right:0;bottom:58px;z-index:200;background:#fff}

  /* Clientes: tabla → scroll horizontal */
  #cli-tabla-wrap{overflow-x:auto}

  /* Métricas: cards 2 columnas */
  .met-grid{grid-template-columns:repeat(2,1fr)!important}
  /* tabla campañas → scroll */
  #met-camp-wrap{overflow-x:auto}

  /* Configuración: grid 1 columna */
  .cfg-grid-2{grid-template-columns:1fr!important}
  /* Config tabs scroll */
  .cfg-tabs{overflow-x:auto;white-space:nowrap;flex-wrap:nowrap!important}
  .cfg-tab{flex-shrink:0}

  /* Formulario equipo: 1 col */
  #equipo-form-wrap [style*="grid-template-columns"]{display:flex!important;flex-direction:column!important}

  /* Botones acción ticket en móvil: stack */
  #esc-ticket-hdr{flex-direction:column;align-items:flex-start;gap:6px}
  #esc-ticket-hdr > div:last-child{display:flex;flex-wrap:wrap;gap:6px;width:100%}
  #esc-ticket-hdr > div:last-child button{flex:1;min-width:80px}

  /* Back button móvil en escalaciones */
  #esc-back-btn{display:flex!important}

  /* Panel reply en móvil: más compacto */
  #esc-reply-wrap textarea{height:48px}

  /* Difusiones: stack vertical + ocultar preview WhatsApp */
  #dif-split{flex-direction:column!important;gap:12px!important}
  #dif-form-col{width:100%!important;min-width:unset!important}
  #dif-wa-prev-col,.wa-phone{display:none!important}
  .dif-form-grid{grid-template-columns:1fr!important}
  #dif-csv-wrap{flex-wrap:wrap!important}
  #dif-csv-label{flex:1 1 100%!important;text-align:center}
  .btn-dl-csv{flex:1 1 100%!important;text-align:center}

  /* Ocultar columnas no esenciales en tablas */
  .mob-hide{display:none!important}
}

/* sidebar header */
#sh{background:var(--hd);padding:12px 16px;display:flex;align-items:center;gap:8px;flex-shrink:0}
#sh h2{font-size:.9rem;font-weight:600;flex:1;color:var(--tx)}
#sh .cnt{background:var(--az);color:#fff;border-radius:12px;padding:2px 8px;font-size:.7rem;font-weight:700}
#srch{padding:8px 12px;background:var(--sb);flex-shrink:0}
#srinput{width:100%;padding:8px 14px;border-radius:8px;border:none;background:var(--hd);
  color:var(--tx);font-size:.84rem;outline:none}
#srinput::placeholder{color:var(--ts)}
#cl{flex:1;overflow-y:auto}
#cl::-webkit-scrollbar{width:4px}
#cl::-webkit-scrollbar-thumb{background:var(--bd);border-radius:2px}
.ci{display:flex;align-items:center;gap:12px;padding:12px 16px;cursor:pointer;
  border-bottom:1px solid var(--bd);transition:background .12s}
.ci:hover,.ci.sel{background:var(--hl)}
.av{width:46px;height:46px;border-radius:50%;background:#1f6b58;display:flex;
  align-items:center;justify-content:center;font-size:1.25rem;flex-shrink:0}
.inf{flex:1;min-width:0}
.nm{font-size:.88rem;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--tx)}
.lm{font-size:.77rem;color:var(--ts);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px}
.meta2{display:flex;flex-direction:column;align-items:flex-end;gap:4px;flex-shrink:0}
.cts{font-size:.68rem;color:var(--ts)}
.hmbadge{background:var(--red);color:#fff;border-radius:8px;padding:1px 6px;font-size:.64rem;font-weight:700}
.optbadge{background:#64748b;color:#fff;border-radius:8px;padding:1px 6px;font-size:.64rem;font-weight:700}

/* chat vacío */
#empty{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;color:var(--ts)}
#empty .eic{font-size:3.5rem;opacity:.25}
#empty p{font-size:.88rem}

/* chat activo */
#cv{display:none;flex-direction:column;flex:1;min-height:0;overflow:hidden}
#ch{background:var(--hd);padding:10px 16px;display:flex;align-items:center;gap:12px;flex-shrink:0}
#ch .av2{width:40px;height:40px;border-radius:50%;background:#1f6b58;display:flex;
  align-items:center;justify-content:center;font-size:1.1rem;flex-shrink:0}
#ch .inf2{flex:1;min-width:0}
#ch .nm2{font-size:.92rem;font-weight:600;color:var(--tx)}
#ch .st2{font-size:.73rem;color:var(--ts)}
#back{background:none;border:none;color:var(--az);font-size:1.3rem;cursor:pointer;padding:4px 8px 4px 0;display:none}
@media(max-width:720px){#back{display:block}}

#mbar{background:#182229;padding:6px 16px;display:flex;align-items:center;gap:10px;flex-shrink:0;border-bottom:1px solid var(--bd)}
#mbar .lbl{font-size:.78rem;color:var(--ts)}
.tog{position:relative;display:inline-block;width:40px;height:22px}
.tog input{opacity:0;width:0;height:0}
.sl{position:absolute;inset:0;background:#555;border-radius:22px;transition:.25s;cursor:pointer}
.sl::before{content:'';position:absolute;width:16px;height:16px;left:3px;bottom:3px;background:#fff;border-radius:50%;transition:.25s}
.tog input:checked+.sl{background:var(--red)}
.tog input:checked+.sl::before{transform:translateX(18px)}
#mlbl{font-size:.76rem;color:var(--red);font-weight:600;display:none}

#msgs{flex:1;overflow-y:auto;padding:12px 16px;display:flex;flex-direction:column;gap:6px;min-height:0}
#msgs::-webkit-scrollbar{width:4px}
#msgs::-webkit-scrollbar-thumb{background:var(--bd)}
.msg{max-width:72%;display:flex;flex-direction:column;gap:2px}
.msg.bot{align-self:flex-start}
.msg.usr{align-self:flex-end}
.mb{padding:8px 12px;border-radius:8px;font-size:.86rem;line-height:1.45;word-break:break-word;white-space:pre-wrap}
.bot .mb{background:var(--bbr);border-radius:0 8px 8px 8px;color:var(--tx)}
.usr .mb{background:var(--bbl);border-radius:8px 0 8px 8px;color:var(--tx)}
.mt{font-size:.67rem;color:var(--ts)}
.bot .mt{align-self:flex-start}
.usr .mt{align-self:flex-end}
.msys{align-self:center;background:#182229;color:var(--ts);font-size:.72rem;padding:4px 14px;border-radius:8px;text-align:center;margin:4px 0}

#ib{background:var(--hd);padding:10px 16px;display:flex;gap:10px;align-items:flex-end;flex-shrink:0}
#ti{flex:1;background:var(--sb);border:none;border-radius:10px;padding:10px 14px;color:var(--tx);
  font-size:.9rem;resize:none;outline:none;max-height:120px;line-height:1.4}
#ti::placeholder{color:var(--ts)}
#sendbtn{background:var(--az);color:#fff;border:none;border-radius:50%;width:42px;height:42px;
  display:flex;align-items:center;justify-content:center;cursor:pointer;flex-shrink:0;
  font-size:1.1rem;transition:opacity .2s}
#sendbtn:disabled{opacity:.4;cursor:not-allowed}

/* ══════════════════════════════════════════════
   SECCIÓN LIGHT: base compartida
   ══════════════════════════════════════════════ */
.sec-light{background:#f0f2f5;flex-direction:column;overflow:auto}
.sec-hdr{
  background:#fff;padding:18px 28px;display:flex;align-items:center;gap:12px;
  border-bottom:1px solid #e0e4e8;flex-shrink:0;
}
.sec-hdr h1{font-size:1.05rem;font-weight:700;color:#1a2332;flex:1}
.sec-hdr p{font-size:.82rem;color:#6b7a8d}
.sec-body{flex:1;padding:24px 28px;overflow-y:auto}
.sec-body::-webkit-scrollbar{width:5px}
.sec-body::-webkit-scrollbar-thumb{background:#cbd5e0;border-radius:3px}

/* Cards métricas */
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:16px;margin-bottom:24px}
.card{background:#fff;border-radius:12px;padding:20px;border:1px solid #e0e4e8;
  box-shadow:0 1px 4px rgba(0,0,0,.04)}
.card-ic{font-size:1.5rem;margin-bottom:8px}
.card-lbl{font-size:.73rem;color:#6b7a8d;font-weight:600;text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px}
.card-val{font-size:1.6rem;font-weight:700;color:#1a2332}
.card-sub{font-size:.72rem;color:#6b7a8d;margin-top:2px}

/* Tablas */
.tbl-wrap{background:#fff;border-radius:12px;border:1px solid #e0e4e8;overflow:hidden}
.tbl-head{padding:16px 20px;border-bottom:1px solid #e0e4e8;display:flex;align-items:center;gap:10px}
.tbl-head h2{font-size:.92rem;font-weight:700;color:#1a2332;flex:1}
table{width:100%;border-collapse:collapse;font-size:.84rem}
th{background:#f8f9fa;color:#6b7a8d;font-size:.72rem;font-weight:600;text-transform:uppercase;
  letter-spacing:.04em;padding:10px 16px;text-align:left;border-bottom:1px solid #e0e4e8}
td{padding:10px 16px;color:#2d3748;border-bottom:1px solid #f0f2f5;vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:#f8f9fa}
.badge-ok{background:#d4edda;color:#155724;border-radius:6px;padding:2px 8px;font-size:.72rem;font-weight:600}
.badge-warn{background:#fff3cd;color:#856404;border-radius:6px;padding:2px 8px;font-size:.72rem;font-weight:600}
.badge-err{background:#f8d7da;color:#721c24;border-radius:6px;padding:2px 8px;font-size:.72rem;font-weight:600}
.badge-pend{background:#e2e8f0;color:#4a5568;border-radius:6px;padding:2px 8px;font-size:.72rem;font-weight:600}

/* Formularios light */
.form-card{background:#fff;border-radius:12px;border:1px solid #e0e4e8;padding:24px}
/* Tabs de Configuración */
.cfg-tabs{display:flex;gap:0;border-bottom:2px solid #e8ecf0;margin-bottom:28px}
.cfg-tab{padding:10px 22px;font-size:.86rem;font-weight:600;color:#6b7a8d;cursor:pointer;
  border-bottom:2px solid transparent;margin-bottom:-2px;transition:color .15s,border-color .15s;white-space:nowrap}
.cfg-tab.active{color:var(--az);border-bottom-color:var(--az)}
.cfg-tab:hover:not(.active){color:#1a2332}
.cfg-pane{display:none}.cfg-pane.active{display:block}
/* Doc cards */
.doc-section{margin-bottom:32px}
.doc-section-title{font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;
  color:#6b7a8d;margin:0 0 14px;padding-bottom:6px;border-bottom:1px solid #e8ecf0}
.doc-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:700px){.doc-grid{grid-template-columns:1fr}}
.doc-card{background:#fff;border:1px solid #e0e4e8;border-radius:12px;padding:20px}
.doc-card-title{font-weight:700;color:#1a2332;font-size:.9rem;margin-bottom:12px;
  display:flex;align-items:center;gap:8px}
.doc-formula{background:#f5f7ff;border-left:3px solid var(--az);border-radius:0 8px 8px 0;
  padding:10px 14px;font-family:monospace;font-size:.83rem;color:#2d3a6b;margin:8px 0;line-height:1.6}
.doc-table{width:100%;border-collapse:collapse;font-size:.82rem;margin-top:10px}
.doc-table th{text-align:left;font-weight:700;color:#4a5568;padding:6px 10px;
  border-bottom:2px solid #e8ecf0;white-space:nowrap}
.doc-table td{padding:7px 10px;border-bottom:1px solid #f0f2f5;color:#2d3748;vertical-align:top}
.doc-table tr:last-child td{border-bottom:none}
.doc-chip{display:inline-block;font-size:.72rem;font-weight:700;padding:2px 8px;
  border-radius:4px;margin-left:6px}
.doc-chip-blue{background:#eef2ff;color:#4a7cf7}
.doc-chip-green{background:#eef9ee;color:#2d7d32}
.doc-chip-orange{background:#fff3e0;color:#e65100}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.form-grid.full{grid-template-columns:1fr}
.f-group{display:flex;flex-direction:column;gap:6px}
.f-label{font-size:.78rem;font-weight:600;color:#4a5568;text-transform:uppercase;letter-spacing:.04em}
.f-inp,.f-sel,.f-ta{
  padding:9px 13px;border-radius:8px;border:1.5px solid #e0e4e8;
  font-size:.88rem;color:#2d3748;background:#fff;outline:none;font-family:inherit;
  transition:border-color .15s;width:100%;box-sizing:border-box;
}
.f-inp:focus,.f-sel:focus,.f-ta:focus{border-color:var(--az)}
.f-ta{resize:vertical;min-height:100px;line-height:1.5}
.f-hint{font-size:.73rem;color:#6b7a8d;margin-top:2px}
.btn-primary{background:var(--az);color:#fff;border:none;border-radius:9px;padding:10px 22px;
  font-size:.9rem;font-weight:700;cursor:pointer;transition:opacity .2s}
.btn-primary:hover{opacity:.88}
.btn-primary:disabled{opacity:.45;cursor:not-allowed}
.btn-secondary{background:#fff;color:#4a5568;border:1.5px solid #e0e4e8;border-radius:9px;
  padding:10px 18px;font-size:.88rem;font-weight:600;cursor:pointer;transition:all .15s}
.btn-secondary:hover{border-color:#b0bec5;color:#2d3748}
.sep{height:1px;background:#e0e4e8;margin:20px 0}

/* ── DIFUSIÓN ── */
#dif-split{display:flex;gap:24px;align-items:flex-start}
#dif-form-col{flex:1;min-width:0}
/* progress */
#dif-prog-wrap{display:none;flex-direction:column;gap:6px;margin-top:12px}
.prog-bar-wrap{background:#e0e4e8;border-radius:8px;height:8px;overflow:hidden}
.prog-bar{background:var(--az);height:100%;width:0%;transition:width .3s;border-radius:8px}
.prog-txt{font-size:.78rem;color:#6b7a8d}
#dif-res-box{display:none;font-size:.83rem;padding:10px 14px;border-radius:8px;line-height:1.5;margin-top:8px}
#dif-res-box.ok{background:#d4edda;color:#155724;border:1px solid #c3e6cb}
#dif-res-box.err{background:#f8d7da;color:#721c24;border:1px solid #f5c6cb}
/* csv */
#dif-csv-wrap{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
#dif-csv-label{display:flex;align-items:center;gap:6px;background:#f0f9f6;border:1.5px dashed var(--az);
  border-radius:8px;padding:8px 14px;cursor:pointer;font-size:.83rem;color:var(--az);
  font-weight:600;flex:1;min-width:140px;justify-content:center;transition:background .2s}
#dif-csv-label:hover{background:#e0f5ee}
#dif-csv-input{display:none}
#dif-csv-stats{font-size:.78rem;margin-top:4px;padding:8px 12px;border-radius:8px;display:none;background:#f8f9fa;border:1px solid #e0e4e8}
#dif-csv-fname{font-size:.76rem;color:#6b7a8d;margin-bottom:4px}
.btn-dl-csv{display:flex;align-items:center;gap:5px;background:#fff;border:1.5px solid #e0e4e8;
  border-radius:8px;padding:8px 14px;color:#6b7a8d;font-size:.83rem;cursor:pointer;
  font-weight:600;transition:all .2s;white-space:nowrap}
.btn-dl-csv:hover{border-color:var(--az);color:var(--az)}
/* historial abajo */
#dif-hist-below{margin-top:20px}
/* ── Modal de detalle de campaña ─────────────────────── */
.modal-overlay{position:fixed;inset:0;background:rgba(10,20,40,.55);z-index:2000;
  display:flex;align-items:center;justify-content:center;padding:16px;
  animation:fadeIn .15s ease}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
.modal-box{background:#fff;border-radius:18px;max-width:780px;width:100%;
  max-height:90vh;overflow-y:auto;padding:32px;
  box-shadow:0 24px 64px rgba(0,0,0,.22);animation:slideUp .2s ease}
@keyframes slideUp{from{transform:translateY(20px);opacity:0}to{transform:translateY(0);opacity:1}}
.modal-hdr{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:24px}
.modal-title{font-size:1.1rem;font-weight:700;color:#1a2332}
.modal-sub{font-size:.78rem;color:#6b7a8d;margin-top:4px}
.modal-close{background:none;border:1.5px solid #e0e4e8;border-radius:8px;
  width:34px;height:34px;cursor:pointer;font-size:1rem;color:#6b7a8d;
  display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:all .15s}
.modal-close:hover{background:#f5f7fa;color:#1a2332;border-color:#cbd5e0}
/* stat cards del modal */
.det-cards{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:24px}
@media(max-width:600px){.det-cards{grid-template-columns:repeat(2,1fr)}}
.det-card{border-radius:12px;padding:16px 12px;text-align:center}
.det-card-val{font-size:1.7rem;font-weight:800;line-height:1.1}
.det-card-lbl{font-size:.68rem;color:#6b7a8d;margin-top:5px;font-weight:700;
  text-transform:uppercase;letter-spacing:.05em}
/* funnel */
.funnel-section{margin-bottom:24px}
.funnel-section h4{font-size:.82rem;font-weight:700;color:#4a5568;
  text-transform:uppercase;letter-spacing:.06em;margin-bottom:12px}
.funnel-row{display:flex;align-items:center;gap:10px;margin-bottom:7px}
.funnel-lbl{font-size:.75rem;color:#6b7a8d;width:82px;text-align:right;flex-shrink:0}
.funnel-wrap{flex:1;background:#f0f2f5;border-radius:6px;height:24px;overflow:hidden}
.funnel-fill{height:100%;border-radius:6px;display:flex;align-items:center;
  padding-left:10px;font-size:.74rem;font-weight:700;color:#fff;
  transition:width .7s cubic-bezier(.4,0,.2,1);min-width:2px}
.funnel-cnt{font-size:.78rem;font-weight:700;color:#2d3748;width:70px;flex-shrink:0;white-space:nowrap}
/* tabla de errores */
.det-err-section h4{font-size:.82rem;font-weight:700;color:#4a5568;
  text-transform:uppercase;letter-spacing:.06em;margin-bottom:12px}
.det-errtbl{width:100%;border-collapse:collapse;font-size:.81rem}
.det-errtbl th{background:#f8f9fa;padding:9px 12px;text-align:left;font-weight:600;
  color:#4a5568;border-bottom:2px solid #e0e4e8;white-space:nowrap}
.det-errtbl td{padding:10px 12px;border-bottom:1px solid #f0f2f5;vertical-align:top}
.det-errtbl tr:last-child td{border-bottom:none}
.err-badge{background:#fff3cd;color:#856404;border:1px solid #ffc107;
  border-radius:5px;padding:2px 8px;font-size:.7rem;font-weight:700;display:inline-block}
.err-nums{color:#6b7a8d;font-size:.73rem;margin-top:3px;font-family:'Courier New',monospace}
/* separador cargue manual */
.dif-manual-hdr{display:flex;align-items:center;gap:8px;font-size:.82rem;font-weight:700;
  color:#2d3748;margin:16px 0 8px;padding-bottom:6px;border-bottom:1px solid #e0e4e8}
/* preview WhatsApp difusión */
#dif-wa-prev-col{width:240px;flex-shrink:0;position:sticky;top:20px}
/* vars */
#dif-vars{display:flex;flex-direction:column;gap:8px}

/* ── PLANTILLAS — form enhancements ── */
.tpl-status-approved{color:#155724;font-weight:600}
.tpl-status-pending{color:#856404}
.tpl-status-rejected{color:#721c24}
.tpl-status-paused{color:#495057}
.req{color:var(--red)}
.opt-badge{background:#e2e8f0;color:#4a5568;border-radius:4px;padding:1px 7px;
  font-size:.62rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;vertical-align:middle}
.sep-label{font-size:.82rem;font-weight:700;color:#2d3748;margin:18px 0 10px;padding-bottom:7px;
  border-bottom:1.5px solid #e0e4e8;display:flex;align-items:center;gap:8px}
.info-box{background:#f0f9ff;border:1px solid #bee3f8;border-radius:8px;padding:10px 14px;
  font-size:.79rem;color:#2c5282;line-height:1.65;margin-bottom:10px}
.info-box code{background:#dbeafe;padding:1px 5px;border-radius:4px;font-family:monospace;font-size:.78rem}
.info-box b{color:#1a365d}
.char-counter{font-size:.71rem;color:#6b7a8d;text-align:right;margin-top:3px}
.char-counter.warn{color:#c05621;font-weight:600}
/* Radio styled buttons */
.radio-group{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:6px}
.radio-opt{display:flex;align-items:center;gap:6px;font-size:.83rem;color:#4a5568;cursor:pointer;
  background:#f8f9fa;border:1.5px solid #e0e4e8;border-radius:8px;padding:7px 13px;
  transition:all .12s;user-select:none}
.radio-opt input[type="radio"]{accent-color:var(--az);flex-shrink:0}
.radio-opt.chk{border-color:var(--az);background:#f0f9f6;color:#1a7a5e;font-weight:600}
/* Upload zones */
.upload-zone{border:2px dashed #cbd5e0;border-radius:10px;padding:26px 20px;text-align:center;
  cursor:pointer;transition:all .15s;background:#fafbfc;margin-bottom:6px}
.upload-zone:hover,.upload-zone.drag{border-color:var(--az);background:#f0f9f6}
.upload-zone .uz-ic{font-size:1.8rem;margin-bottom:6px}
.upload-zone .uz-title{font-size:.88rem;font-weight:600;color:#4a5568;margin-bottom:3px}
.upload-zone .uz-hint{font-size:.74rem;color:#6b7a8d}
.file-preview{display:flex;align-items:center;gap:10px;background:#f0f9f6;
  border:1px solid #9ae6b4;border-radius:8px;padding:10px 14px;margin-top:6px;font-size:.84rem}
.fp-ic{font-size:1.2rem;flex-shrink:0}
.fp-name{font-weight:600;color:#155724;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.fp-size{color:#6b7a8d;font-size:.74rem;flex-shrink:0}
.fp-remove{cursor:pointer;color:var(--red);font-size:1rem;flex-shrink:0;
  background:none;border:none;padding:0 4px;line-height:1}
/* Botones form */
.btn-remove{background:none;border:1px solid #e0e4e8;border-radius:6px;color:#6b7a8d;
  cursor:pointer;padding:5px 9px;font-size:.82rem;flex-shrink:0;transition:all .12s}
.btn-remove:hover{border-color:var(--red);color:var(--red)}
.qr-row{display:flex;gap:8px;align-items:center;margin-bottom:8px}
.cta-row{display:flex;gap:8px;align-items:flex-start;margin-bottom:10px;flex-wrap:wrap}
.cta-row .f-inp,.cta-row .f-sel{margin:0}
/* Unified button builder */
.btn-add-wrap{position:relative;display:inline-block}
.btn-type-menu{display:none;position:absolute;left:0;top:calc(100% + 4px);background:#fff;
  border:1px solid #dde1e7;border-radius:10px;box-shadow:0 6px 24px rgba(0,0,0,.13);
  z-index:300;min-width:230px;overflow:hidden}
.btn-type-menu.open{display:block}
.btn-menu-item{padding:10px 16px;font-size:.84rem;color:#1a2332;cursor:pointer;
  border-bottom:1px solid #f0f2f5;display:flex;align-items:center;gap:8px;transition:background .1s}
.btn-menu-item:last-child{border-bottom:none}
.btn-menu-item:hover{background:#f5f7ff}
.ubn-row{background:#fafbfc;border:1px solid #e0e4e8;border-radius:8px;
  padding:10px 12px;margin-bottom:8px;display:flex;flex-direction:column;gap:6px}
.ubn-hdr{display:flex;align-items:center;gap:8px}
.ubn-type-badge{font-size:.71rem;font-weight:700;padding:2px 7px;border-radius:4px;
  flex-shrink:0;white-space:nowrap}
.ubn-badge-qr{background:#eef9ee;color:#2d7d32}
.ubn-badge-url{background:#eef2ff;color:#4a7cf7}
.ubn-badge-phone{background:#fff3e0;color:#e65100}
.ubn-badge-wacall{background:#e8f5e9;color:#1b5e20}
.ubn-badge-flow{background:#f3e5f5;color:#6a1b9a}
.ubn-badge-code{background:#fff8e1;color:#f57f17}
.ubn-cnt{font-size:.7rem;color:#6b7a8d;white-space:nowrap;flex-shrink:0}
.progress-upload{display:none;align-items:center;gap:8px;font-size:.8rem;color:var(--az);
  background:#f0f9f6;border-radius:8px;padding:8px 14px;margin-top:8px}
.progress-upload .pu-spinner{animation:spin 1s linear infinite;font-size:1rem}
@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}

/* ── PREVIEW WHATSAPP ── */
.wa-phone{width:240px;flex-shrink:0;position:sticky;top:20px}
.wa-phone-shell{background:#e5ddd5;border-radius:18px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.18);border:6px solid #111;position:relative}
.wa-phone-bar{background:#075e54;padding:10px 14px;display:flex;align-items:center;gap:8px}
.wa-phone-bar .wa-av{width:30px;height:30px;border-radius:50%;background:#25d366;display:flex;align-items:center;justify-content:center;font-size:1rem}
.wa-phone-bar .wa-name{color:#fff;font-size:.82rem;font-weight:600}
.wa-phone-bar .wa-sub{color:#b2dfdb;font-size:.68rem}
.wa-chat{padding:10px 8px 16px;min-height:200px;background:#e5ddd5 url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='80' height='80' opacity='.06'%3E%3Ctext y='50' font-size='50'%3E💬%3C/text%3E%3C/svg%3E")}
.wa-bubble{background:#fff;border-radius:0 10px 10px 10px;margin:0 4px;box-shadow:0 1px 2px rgba(0,0,0,.15);overflow:hidden;max-width:220px;position:relative}
.wa-hdr-img{width:100%;background:#25d366 linear-gradient(135deg,#1a8a5a 0%,#25d366 100%);min-height:110px;display:flex;align-items:center;justify-content:center;font-size:2.5rem;color:#fff;position:relative;overflow:hidden}
.wa-hdr-img img{width:100%;height:100%;object-fit:cover;position:absolute;inset:0}
.wa-hdr-img .wa-hdr-emoji{position:relative;z-index:1}
.wa-hdr-txt{background:#128c7e;color:#fff;font-size:.78rem;font-weight:700;padding:8px 12px;text-align:center}
.wa-hdr-doc{background:#f0f0f0;padding:8px 12px;display:flex;align-items:center;gap:8px;border-bottom:1px solid #e0e0e0}
.wa-hdr-vid-wrap{position:relative}
.wa-hdr-vid-wrap .wa-play{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.3);font-size:2rem}
.wa-body-text{padding:10px 12px 2px;font-size:.8rem;line-height:1.5;color:#111;white-space:pre-wrap;word-break:break-word}
.wa-footer-text{padding:2px 12px 8px;font-size:.72rem;color:#667781;line-height:1.4}
.wa-ts{text-align:right;font-size:.65rem;color:#667781;padding:0 8px 6px;display:flex;align-items:center;justify-content:flex-end;gap:3px}
.wa-ts .wa-tick{color:#34b7f1}
.wa-btns{border-top:1px solid #e9ecef}
.wa-btn{display:flex;align-items:center;justify-content:center;gap:6px;padding:9px 12px;color:#128c7e;font-size:.78rem;font-weight:600;border-bottom:1px solid #e9ecef;cursor:default;text-align:center}
.wa-btn:last-child{border-bottom:none}
.wa-btn .wa-btn-ic{font-size:.9rem}
.wa-preview-label{font-size:.72rem;color:#6b7a8d;text-align:center;margin-top:8px;font-style:italic}

/* ── CONFIGURACIÓN — legacy (puede quedar para otros usos) ── */
.config-item{display:flex;align-items:center;gap:12px;padding:14px 20px;border-bottom:1px solid #f0f2f5}
.config-item:last-child{border-bottom:none}
.config-key{font-size:.84rem;font-weight:600;color:#2d3748;flex:1}
.config-val{font-size:.82rem;color:#6b7a8d;background:#f0f2f5;border-radius:6px;padding:3px 10px;
  font-family:monospace;max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.config-ok{color:var(--az);font-weight:700;font-size:.84rem}
.config-miss{color:var(--red);font-weight:700;font-size:.84rem}
/* ── CONFIGURACIÓN — cards interactivas ── */
.cfg-overview{display:flex;gap:12px;margin-bottom:28px;flex-wrap:wrap}
.cfg-ov-item{background:#fff;border:1px solid #e0e4e8;border-radius:12px;padding:14px 20px;
  display:flex;align-items:center;gap:12px;flex:1;min-width:160px}
.cfg-ov-icon{font-size:1.5rem;flex-shrink:0}
.cfg-ov-name{font-weight:700;color:#1a2332;font-size:.86rem}
.cfg-ov-status{font-size:.76rem;margin-top:2px}
.cfg-pill-ok{color:#2d7d32;font-weight:600}
.cfg-pill-err{color:#c62828;font-weight:600}
.cfg-pill-pend{color:#8a94a6}
.cfg-card{background:#fff;border:1px solid #e0e4e8;border-radius:14px;
  padding:24px;margin-bottom:24px;box-shadow:0 1px 4px rgba(0,0,0,.04)}
/* Sistema — luces de estado */
.sistema-item{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:14px 16px}
.sistema-hdr{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.sistema-dot{width:10px;height:10px;border-radius:50%;background:#cbd5e0;flex-shrink:0;
  transition:background .2s}
.sistema-dot.ok{background:#22c55e;box-shadow:0 0 0 3px rgba(34,197,94,.15)}
.sistema-dot.warn{background:#f59e0b;box-shadow:0 0 0 3px rgba(245,158,11,.15)}
.sistema-dot.error{background:#ef4444;box-shadow:0 0 0 3px rgba(239,68,68,.15);
  animation:dot-pulse 1.4s infinite}
.sistema-dot.loading{background:#94a3b8;animation:dot-pulse 1s infinite}
@keyframes dot-pulse{0%,100%{opacity:1}50%{opacity:.4}}
.sistema-name{font-weight:700;font-size:.86rem;color:#1a2332}
.sistema-msg{font-size:.8rem;color:#475569;margin-bottom:4px}
.sistema-detalle{font-size:.72rem;color:#94a3b8;line-height:1.4}
.sistema-sugerencia{font-size:.74rem;color:#dc2626;margin-top:6px;padding:6px 8px;
  background:#fef2f2;border-radius:6px;border-left:3px solid #ef4444}
.cfg-card-hdr{display:flex;align-items:center;justify-content:space-between;margin-bottom:22px;
  padding-bottom:16px;border-bottom:1px solid #f0f2f5}
.cfg-card-title{font-weight:700;color:#1a2332;font-size:1rem}
.cfg-status-pill{font-size:.74rem;font-weight:700;padding:4px 12px;border-radius:20px;white-space:nowrap}
.cfg-pill-connected{background:#e8f5e9;color:#2d7d32}
.cfg-pill-error{background:#fce4e4;color:#c62828}
.cfg-pill-pending{background:#f0f2f5;color:#6b7a8d}
.cfg-step{display:flex;gap:14px;margin-bottom:18px}
.cfg-step-num{width:24px;height:24px;border-radius:50%;background:#eef2ff;color:var(--az);
  font-size:.78rem;font-weight:800;display:flex;align-items:center;justify-content:center;
  flex-shrink:0;margin-top:2px}
.cfg-step-body{flex:1}
.cfg-field-lbl{font-size:.84rem;font-weight:600;color:#2d3748;margin-bottom:6px;
  display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.cfg-help-btn{background:none;border:1px solid #c9d0da;border-radius:50%;width:18px;height:18px;
  font-size:.7rem;font-weight:700;color:#6b7a8d;cursor:pointer;display:inline-flex;
  align-items:center;justify-content:center;padding:0;flex-shrink:0;line-height:1}
.cfg-help-btn:hover{background:#eef2ff;border-color:var(--az);color:var(--az)}
.cfg-help-box{display:none;background:#f5f7ff;border:1px solid #d0d8f0;border-radius:8px;
  padding:12px 14px;font-size:.79rem;color:#3a4a6b;line-height:1.65;margin-bottom:10px}
.cfg-help-box a{color:var(--az)}
.cfg-help-box.open{display:block}
.cfg-field-row{display:flex;align-items:center;gap:8px}
.cfg-input-wrap{position:relative;flex:1;display:flex;align-items:center}
.cfg-input-wrap .f-inp{padding-right:38px}
.cfg-inp{flex:1}
.cfg-eye-btn{position:absolute;right:10px;background:none;border:none;cursor:pointer;
  font-size:.85rem;padding:0;color:#8a94a6;line-height:1}
.cfg-eye-btn:hover{color:#1a2332}
.cfg-field-status{font-size:.95rem;flex-shrink:0;width:20px;text-align:center}
.cfg-actions{display:flex;gap:10px;align-items:center;margin-top:22px;
  padding-top:18px;border-top:1px solid #f0f2f5;flex-wrap:wrap}
.cfg-test-result{font-size:.82rem;padding:8px 14px;border-radius:8px;line-height:1.5;flex:1;min-width:180px}
.cfg-test-ok{background:#e8f5e9;color:#1b5e20;border:1px solid #a5d6a7}
.cfg-test-err{background:#fce4e4;color:#b71c1c;border:1px solid #ef9a9a}
.cfg-separator{border:none;border-top:1px solid #f0f2f5;margin:8px 0}

/* ── Prompt editor ─────────────────────────────────────────── */
.prompt-editor-wrap{display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:start}
@media(max-width:900px){.prompt-editor-wrap{grid-template-columns:1fr}}
.prompt-left,.prompt-right{background:#fff;border:1px solid #e0e4e8;border-radius:14px;padding:20px}
.prompt-ta{width:100%;height:420px;font-family:monospace;font-size:.8rem;line-height:1.6;
  border:1px solid #dde1e8;border-radius:8px;padding:12px;resize:vertical;
  color:#1a2332;background:#fafbfc;outline:none;box-sizing:border-box}
.prompt-ta:focus{border-color:var(--az);background:#fff}
.prompt-instruccion-ta{width:100%;height:110px;font-size:.83rem;line-height:1.6;
  border:1px solid #dde1e8;border-radius:8px;padding:10px;resize:vertical;
  color:#1a2332;outline:none;box-sizing:border-box;margin-bottom:8px}
.prompt-instruccion-ta:focus{border-color:var(--az)}
/* ── SPRINT 4: Adjuntar media ── */
.attach-opt{display:flex;align-items:center;gap:10px;padding:8px 12px;color:#e9edef;
  cursor:pointer;border-radius:6px;font-size:.86rem;transition:background .12s}
.attach-opt:hover{background:#2a3942}
.attach-opt > span:first-child{width:30px;height:30px;border-radius:50%;color:#fff;
  display:flex;align-items:center;justify-content:center;font-size:.95rem;flex-shrink:0}
/* Burbujas de media en el chat */
.media-img{max-width:280px;max-height:280px;border-radius:8px;cursor:pointer;display:block}
.media-vid{max-width:280px;max-height:280px;border-radius:8px;display:block}
.media-doc{display:flex;align-items:center;gap:10px;background:rgba(0,0,0,.15);
  padding:10px 12px;border-radius:8px;text-decoration:none;color:inherit;min-width:200px}
.media-doc-ic{font-size:1.4rem}
.media-doc-info{flex:1;min-width:0}
.media-doc-name{font-size:.85rem;font-weight:600;word-break:break-word}
.media-doc-meta{font-size:.7rem;opacity:.7}
.media-loc{display:flex;flex-direction:column;background:rgba(0,0,0,.15);
  padding:10px 12px;border-radius:8px;min-width:220px;gap:4px;text-decoration:none;color:inherit}
.media-prod{display:flex;align-items:center;gap:10px;background:rgba(0,0,0,.15);
  padding:10px;border-radius:8px;min-width:240px}
.media-prod-img{width:50px;height:50px;border-radius:6px;background:#fff;object-fit:cover;flex-shrink:0}
.media-caption{margin-top:6px;font-size:.86rem;line-height:1.35}
/* Resultados de catálogo */
.cat-item{display:flex;align-items:center;gap:10px;padding:8px;border-radius:7px;
  cursor:pointer;border:1px solid transparent;transition:all .12s}
.cat-item:hover{background:#f0f4ff;border-color:#c7d2fe}
.cat-item-img{width:42px;height:42px;border-radius:6px;background:#f1f5f9;object-fit:cover;flex-shrink:0}
.cat-item-info{flex:1;min-width:0}
.cat-item-titulo{font-weight:600;font-size:.84rem;color:#1a2332;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cat-item-precio{font-size:.78rem;color:#16a34a;font-weight:700}

/* ── Escalaciones ── */
.esc-tab{flex:1;border:none;background:none;padding:10px 4px;font-size:.75rem;font-weight:600;
  color:#64748b;cursor:pointer;border-bottom:2px solid transparent;transition:all .15s;white-space:nowrap}
.esc-tab:hover{color:#4f46e5}
.esc-tab.active{color:#4f46e5;border-bottom-color:#4f46e5}
.esc-cnt{display:inline-block;background:#ef4444;color:#fff;border-radius:10px;
  padding:1px 6px;font-size:.68rem;margin-left:4px;vertical-align:middle}
.esc-card{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:10px 12px;
  margin-bottom:6px;cursor:pointer;transition:all .15s;border-left:3px solid transparent}
.esc-card:hover{border-color:#c7d2fe;box-shadow:0 1px 4px rgba(0,0,0,.06)}
.esc-card.selected{border-left-color:#4f46e5;background:#f0f4ff}
.esc-card-nombre{font-weight:700;font-size:.87rem;color:#1a2332;margin-bottom:2px}
.esc-card-motivo{font-size:.78rem;color:#64748b;margin-bottom:4px;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.esc-card-meta{display:flex;align-items:center;gap:6px;font-size:.72rem;color:#94a3b8}
.esc-urg{padding:2px 7px;border-radius:10px;font-size:.7rem;font-weight:700}
.esc-urg-alta{background:#fee2e2;color:#b91c1c}
.esc-urg-normal{background:#fef3c7;color:#92400e}
.esc-urg-baja{background:#dcfce7;color:#15803d}
/* Burbujas de chat en panel de escalaciones */
.esc-bbl{max-width:75%;padding:7px 11px;border-radius:10px;font-size:.84rem;line-height:1.5;
  word-break:break-word;white-space:pre-wrap}
.esc-bbl-user{background:#005c4b;color:#fff;align-self:flex-end;border-radius:10px 10px 3px 10px}
.esc-bbl-bot{background:#1f2c34;color:#e9edef;align-self:flex-start;border-radius:10px 10px 10px 3px}
.esc-bbl-human{background:#2a3942;color:#e9edef;align-self:flex-start;border-radius:10px 10px 10px 3px;
  border-left:3px solid #4f46e5}
.esc-bbl-nota{background:#fef9c3;color:#713f12;align-self:stretch;border-radius:8px;
  border-left:3px solid #eab308;font-style:italic;font-size:.82rem}
/* SLA timer */
.sla-warn{color:#f59e0b;font-weight:700}
.sla-crit{color:#ef4444;font-weight:700;animation:pulse-sla .8s infinite}
@keyframes pulse-sla{0%,100%{opacity:1}50%{opacity:.5}}
/* Templates rápidos */
.tpl-picker{background:#fff;border:1px solid #e2e8f0;border-radius:8px;
  box-shadow:0 4px 16px rgba(0,0,0,.12);max-height:220px;overflow-y:auto;
  position:absolute;bottom:100%;left:0;right:0;z-index:100;margin-bottom:4px}
.tpl-item{padding:8px 12px;cursor:pointer;font-size:.83rem;border-bottom:1px solid #f1f5f9}
.tpl-item:hover{background:#f0f4ff}
.tpl-item-titulo{font-weight:700;color:#1a2332;margin-bottom:2px}
.tpl-item-prev{color:#64748b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
/* Tabs del panel de detalle ticket */
.det-tab{flex:1;border:none;background:none;padding:8px 4px;font-size:.75rem;font-weight:600;
  color:#64748b;cursor:pointer;border-bottom:2px solid transparent}
.det-tab.active{color:#4f46e5;border-bottom-color:#4f46e5}
/* Notificación toast SSE */
.esc-toast{position:fixed;top:16px;right:16px;background:#1a2332;color:#fff;
  padding:10px 16px;border-radius:8px;font-size:.83rem;z-index:9999;
  box-shadow:0 4px 16px rgba(0,0,0,.25);animation:toast-in .25s ease;
  border-left:4px solid #4f46e5;max-width:300px}
@keyframes toast-in{from{opacity:0;transform:translateY(-10px)}to{opacity:1;transform:translateY(0)}}
.esc-bbl-ts{font-size:.67rem;opacity:.6;margin-top:3px}
/* Zona adjuntos */
.img-attach-zone{border:1.5px dashed #c7d2fe;border-radius:8px;padding:8px 10px;
  background:#f8f7ff;margin-bottom:10px;transition:border-color .15s}
.img-attach-zone.drag-over{border-color:#4f46e5;background:#eef2ff}
.img-thumbs{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:6px}
.img-thumb{position:relative;width:56px;height:56px;border-radius:6px;
  overflow:hidden;border:1.5px solid #c7d2fe;cursor:default;flex-shrink:0}
.img-thumb img{width:100%;height:100%;object-fit:cover;display:block}
.img-thumb-del{position:absolute;top:1px;right:1px;width:16px;height:16px;
  background:rgba(0,0,0,.55);color:#fff;border:none;border-radius:50%;
  font-size:10px;line-height:16px;text-align:center;cursor:pointer;padding:0}
.img-attach-bar{display:flex;align-items:center;gap:8px}
.btn-attach{display:inline-flex;align-items:center;gap:5px;font-size:.77rem;
  font-weight:600;color:#4f46e5;background:#eef2ff;border:1px solid #c7d2fe;
  border-radius:6px;padding:4px 10px;cursor:pointer;white-space:nowrap;transition:background .15s}
.btn-attach:hover{background:#e0e7ff}
.img-paste-hint{font-size:.72rem;color:#94a3b8;line-height:1.3}
.btn-improve{width:100%;padding:11px;background:linear-gradient(135deg,#4f46e5,#7c3aed);
  color:#fff;border:none;border-radius:8px;font-weight:700;font-size:.88rem;cursor:pointer;
  transition:opacity .15s}
.btn-improve:hover{opacity:.88}
.btn-improve:disabled{opacity:.5;cursor:not-allowed}
/* Variables table */
.vars-table{width:100%;border-collapse:collapse;font-size:.83rem}
.vars-table th{text-align:left;padding:8px 10px;color:#6b7a8d;font-weight:600;
  border-bottom:2px solid #e8ecf0;background:#f8fafc}
.vars-table td{padding:6px 6px;border-bottom:1px solid #f0f2f5;vertical-align:middle}
.vars-key-inp{font-family:monospace;font-size:.8rem;font-weight:700;color:#4f46e5;
  border:1px solid #e0e4e8;border-radius:6px;padding:5px 8px;width:100%;background:#f5f3ff}
.vars-val-inp{font-size:.82rem;border:1px solid #e0e4e8;border-radius:6px;
  padding:5px 8px;width:100%;background:#fff}
.vars-key-inp:focus,.vars-val-inp:focus{outline:none;border-color:var(--az)}
.vars-del-btn{background:none;border:none;color:#e53935;font-size:1rem;cursor:pointer;
  padding:4px 8px;border-radius:4px}
.vars-del-btn:hover{background:#fce4e4}
/* Diff */
.prompt-diff{font-family:monospace;font-size:.76rem;line-height:1.7;
  background:#fafbfc;border:1px solid #e0e4e8;border-radius:8px;padding:12px;
  max-height:280px;overflow-y:auto;white-space:pre-wrap;word-break:break-word}
.diff-add{background:#e8f5e9;color:#1b5e20}
.diff-del{background:#fce4e4;color:#b71c1c;text-decoration:line-through}

/* ── Business type selector ── */
.biz-type-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;margin-top:12px}
.biz-type-btn{border:2px solid #e0e4e8;border-radius:10px;padding:12px 10px;text-align:center;
  cursor:pointer;background:#fff;transition:.18s;font-size:.82rem;color:#4a5568;line-height:1.4;
  user-select:none}
.biz-type-btn:hover{border-color:var(--az);background:#eef2ff}
.biz-type-btn.selected{border-color:var(--az);background:#eef2ff;color:var(--az);font-weight:700}
.biz-type-icon{font-size:1.6rem;margin-bottom:6px}
/* ── Feature toggles ── */
.toggle-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px}
@media(max-width:540px){.toggle-grid{grid-template-columns:1fr}}
.toggle-card{border:1.5px solid #e0e4e8;border-radius:10px;padding:12px 14px;
  display:flex;align-items:flex-start;gap:12px;background:#fff;transition:.18s}
.toggle-card.active{border-color:#d1fae5;background:#f0fdf4}
.toggle-card-text{flex:1;min-width:0}
.toggle-card-label{font-size:.84rem;font-weight:700;color:#1a2332;margin-bottom:2px}
.toggle-card-desc{font-size:.76rem;color:#6b7a8d;line-height:1.4}
/* pill toggle switch */
.tog-sw{position:relative;width:38px;height:22px;flex-shrink:0;margin-top:2px}
.tog-sw input{opacity:0;width:0;height:0;position:absolute}
.tog-slider{position:absolute;inset:0;border-radius:22px;background:#cbd5e1;
  cursor:pointer;transition:.2s}
.tog-slider:before{content:'';position:absolute;width:16px;height:16px;border-radius:50%;
  left:3px;bottom:3px;background:#fff;transition:.2s;box-shadow:0 1px 3px rgba(0,0,0,.15)}
.tog-sw input:checked + .tog-slider{background:#22c55e}
.tog-sw input:checked + .tog-slider:before{transform:translateX(16px)}
/* ── Test chat (Fase C) ── */
.chat-wrap{display:flex;flex-direction:column;height:540px;max-height:70vh;
  border:1.5px solid #e0e4e8;border-radius:12px;overflow:hidden;background:#ece5dd}
.chat-messages{flex:1;overflow-y:auto;padding:16px 14px;display:flex;flex-direction:column;gap:8px}
.chat-msg{max-width:78%;padding:9px 13px;border-radius:14px;font-size:.87rem;line-height:1.5;
  word-break:break-word;position:relative}
.chat-msg.user{align-self:flex-end;background:#dcf8c6;border-radius:14px 14px 4px 14px;color:#1a2332}
.chat-msg.assistant{align-self:flex-start;background:#fff;border-radius:14px 14px 14px 4px;
  box-shadow:0 1px 2px rgba(0,0,0,.08);color:#1a2332}
.chat-msg-time{font-size:.66rem;color:#94a3b8;margin-top:3px;text-align:right}
.chat-typing{align-self:flex-start;background:#fff;border-radius:14px;padding:10px 14px;
  display:flex;gap:4px;align-items:center;box-shadow:0 1px 2px rgba(0,0,0,.08)}
.chat-typing span{width:7px;height:7px;border-radius:50%;background:#94a3b8;
  animation:typing-dot 1s ease-in-out infinite}
.chat-typing span:nth-child(2){animation-delay:.2s}
.chat-typing span:nth-child(3){animation-delay:.4s}
@keyframes typing-dot{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-5px)}}
.chat-input-bar{display:flex;gap:8px;padding:10px 12px;background:#f0f0f0;
  border-top:1px solid #e0e4e8;align-items:flex-end}
.chat-inp{flex:1;border:none;border-radius:20px;padding:9px 14px;font-size:.87rem;
  background:#fff;resize:none;max-height:100px;outline:none;line-height:1.4;
  font-family:inherit;box-shadow:0 1px 2px rgba(0,0,0,.07)}
.chat-send-btn{background:var(--az);border:none;border-radius:50%;width:40px;height:40px;
  display:flex;align-items:center;justify-content:center;cursor:pointer;flex-shrink:0;
  color:#fff;font-size:1rem;transition:.18s}
.chat-send-btn:hover{filter:brightness(1.1)}
.chat-send-btn:disabled{opacity:.5;cursor:not-allowed}
/* ── loading spinner ── */
.loading-txt{color:#6b7a8d;font-size:.85rem;padding:32px;text-align:center}

/* ── Focus visible — accesibilidad teclado ── */
.nav-item:focus-visible{outline:2px solid var(--az);outline-offset:-2px;border-radius:4px}
.ci:focus-visible{outline:2px solid var(--az);outline-offset:-2px}
#srinput:focus-visible{outline:2px solid var(--az);outline-offset:0}
#ti:focus-visible{outline:2px solid var(--az);outline-offset:0}
#sendbtn:focus-visible{outline:2px solid #fff;outline-offset:2px}
.btn-primary:focus-visible,.btn-secondary:focus-visible{outline:2px solid var(--az);outline-offset:2px}
.modal-close:focus-visible{outline:2px solid var(--az);outline-offset:2px}

/* ── Reduced motion — respetar preferencias del SO ── */
@media (prefers-reduced-motion: reduce) {
  *{animation-duration:.01ms !important;animation-iteration-count:1 !important;transition-duration:.01ms !important}
  .funnel-fill{transition:none}
  .prog-bar{transition:none}
}

/* ══════════════════════════════════════════════
   SECCIÓN: CLIENTES
   ══════════════════════════════════════════════ */
#sec-clientes{flex-direction:column}

/* Stat cards de estado */
.estado-cards{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:24px}
@media(max-width:900px){.estado-cards{grid-template-columns:repeat(3,1fr)}}
@media(max-width:560px){.estado-cards{grid-template-columns:repeat(2,1fr)}}
.estado-card{border-radius:14px;padding:18px 16px;border:1px solid transparent;cursor:pointer;
  transition:transform .15s,box-shadow .15s;user-select:none;position:relative;overflow:hidden}
.estado-card:hover{transform:translateY(-2px);box-shadow:0 6px 20px rgba(0,0,0,.10)}
.estado-card.sel-estado{box-shadow:0 0 0 2px var(--az) inset}
.estado-card::before{content:'';position:absolute;top:0;right:0;width:60px;height:60px;
  border-radius:50%;opacity:.08;transform:translate(20px,-20px)}
.ec-total {background:#f0f9f6;border-color:#9ae6c4}.ec-total::before{background:#00a884}
.ec-activo{background:#f0fdf4;border-color:#86efac}.ec-activo::before{background:#16a34a}
.ec-tibio {background:#fffbeb;border-color:#fcd34d}.ec-tibio::before{background:#d97706}
.ec-frio  {background:#eff6ff;border-color:#93c5fd}.ec-frio::before{background:#2563eb}
.ec-baja  {background:#f8fafc;border-color:#cbd5e1}.ec-baja::before{background:#64748b}
.ec-val{font-size:2rem;font-weight:800;line-height:1;margin-bottom:6px}
.ec-total .ec-val{color:#00875a}
.ec-activo .ec-val{color:#15803d}
.ec-tibio  .ec-val{color:#b45309}
.ec-frio   .ec-val{color:#1d4ed8}
.ec-baja   .ec-val{color:#475569}
.ec-lbl{font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#4a5568}
.ec-sub{font-size:.7rem;color:#6b7a8d;margin-top:3px}

/* Filter pills */
.cli-filters{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:16px}
.cli-pill{padding:6px 16px;border-radius:20px;border:1.5px solid #e0e4e8;background:#fff;
  font-size:.8rem;font-weight:600;color:#4a5568;cursor:pointer;transition:all .12s;user-select:none}
.cli-pill:hover{border-color:#b0bec5;color:#2d3748}
.cli-pill.active{background:var(--az);border-color:var(--az);color:#fff}
.cli-search{flex:1;min-width:160px;max-width:280px;position:relative}
.cli-search input{width:100%;padding:7px 12px 7px 34px;border-radius:20px;border:1.5px solid #e0e4e8;
  font-size:.82rem;color:#2d3748;outline:none;transition:border-color .15s;background:#fff}
.cli-search input:focus{border-color:var(--az)}
.cli-search::before{content:'🔍';position:absolute;left:10px;top:50%;transform:translateY(-50%);
  font-size:.8rem;pointer-events:none}

/* Tabla clientes */
.cli-tbl-wrap{background:#fff;border-radius:14px;border:1px solid #e0e4e8;overflow:hidden}
.cli-tbl-info{padding:12px 20px;background:#f8f9fa;border-bottom:1px solid #e0e4e8;
  font-size:.78rem;color:#6b7a8d;display:flex;align-items:center;gap:8px}
.cli-tbl-info strong{color:#2d3748}
.cli-av{width:36px;height:36px;border-radius:50%;display:flex;align-items:center;
  justify-content:center;font-size:1rem;font-weight:700;flex-shrink:0;color:#fff}
.cli-av-activo{background:linear-gradient(135deg,#16a34a,#22c55e)}
.cli-av-tibio {background:linear-gradient(135deg,#d97706,#f59e0b)}
.cli-av-frio  {background:linear-gradient(135deg,#1d4ed8,#3b82f6)}
.cli-av-baja  {background:linear-gradient(135deg,#475569,#94a3b8)}
.est-pill{border-radius:20px;padding:3px 10px;font-size:.7rem;font-weight:700;
  display:inline-flex;align-items:center;gap:4px;white-space:nowrap}
.est-activo{background:#dcfce7;color:#15803d}
.est-tibio {background:#fef9c3;color:#854d0e}
.est-frio  {background:#dbeafe;color:#1e40af}
.est-baja  {background:#f1f5f9;color:#475569}
.cli-act-btn{background:none;border:1px solid #e0e4e8;border-radius:7px;padding:4px 10px;
  font-size:.75rem;color:#4a5568;cursor:pointer;transition:all .12s;white-space:nowrap}
.cli-act-btn:hover{border-color:var(--az);color:var(--az)}
.cli-write-btn{background:#eff6ff;color:#2563eb;border:1px solid #bfdbfe}
.cli-write-btn:hover{background:#dbeafe;border-color:#93c5fd;color:#1d4ed8}
.cli-empty{padding:64px 20px;text-align:center;color:#94a3b8}
.cli-empty-ic{font-size:3rem;margin-bottom:12px;opacity:.5}
.cli-empty-txt{font-size:.9rem;font-weight:500;color:#64748b}
</style>
</head>
<body>
<div id="shell">

  <!-- ── TOPBAR ── -->
  <div id="topbar">
    <div class="logo">
      <div class="logo-ic">🤖</div>
      <span class="logo-txt">Andrea</span>
      <span class="logo-sub">Equora Distribuciones</span>
    </div>
    <div class="topbar-spacer"></div>
    <button id="logout-top" onclick="location.href='/inbox/logout'">Salir →</button>
  </div>

  <!-- ── BODY ── -->
  <div id="body">

    <!-- ── LEFT NAV ── -->
    <nav id="nav">
      <div class="nav-section">Principal</div>
      <div class="nav-item active" role="button" tabindex="0" data-sec="conversaciones"
           onclick="showSec('conversaciones')" onkeydown="if(event.key==='Enter'||event.key===' ')showSec('conversaciones')">
        <span class="ni" aria-hidden="true">💬</span> Conversaciones
        <span class="nb" id="conv-badge" style="display:none" aria-live="polite">0</span>
      </div>
      <div class="nav-item" role="button" tabindex="0" data-sec="difusiones"
           onclick="showSec('difusiones')" onkeydown="if(event.key==='Enter'||event.key===' ')showSec('difusiones')">
        <span class="ni" aria-hidden="true">📢</span> Difusiones
      </div>
      <div class="nav-section">Gestión</div>
      <div class="nav-item" role="button" tabindex="0" data-sec="clientes"
           onclick="showSec('clientes')" onkeydown="if(event.key==='Enter'||event.key===' ')showSec('clientes')">
        <span class="ni" aria-hidden="true">👥</span> Clientes
      </div>
      <div class="nav-item" role="button" tabindex="0" data-sec="plantillas"
           onclick="showSec('plantillas')" onkeydown="if(event.key==='Enter'||event.key===' ')showSec('plantillas')">
        <span class="ni" aria-hidden="true">📋</span> Plantillas
      </div>
      <div class="nav-item" role="button" tabindex="0" data-sec="metricas"
           onclick="showSec('metricas')" onkeydown="if(event.key==='Enter'||event.key===' ')showSec('metricas')">
        <span class="ni" aria-hidden="true">📊</span> Métricas
      </div>
      <div class="nav-item" role="button" tabindex="0" data-sec="escalaciones"
           onclick="showSec('escalaciones')" onkeydown="if(event.key==='Enter'||event.key===' ')showSec('escalaciones')">
        <span class="ni" aria-hidden="true">🎯</span> Escalaciones
        <span id="esc-badge" style="display:none;margin-left:auto;background:#ef4444;color:#fff;
          border-radius:10px;padding:1px 7px;font-size:.72rem;font-weight:700"></span>
      </div>
      <div class="nav-section">Sistema</div>
      <div class="nav-item" role="button" tabindex="0" data-sec="configuracion"
           onclick="showSec('configuracion')" onkeydown="if(event.key==='Enter'||event.key===' ')showSec('configuracion')">
        <span class="ni" aria-hidden="true">⚙️</span> Configuración
      </div>
      <div class="nav-footer">
        <small>AgentKit v1.0</small>
      </div>
    </nav>

    <!-- ── MAIN ── -->
    <div id="main">

      <!-- ═══════════════════════════════════════
           SECCIÓN: CONVERSACIONES
           ═══════════════════════════════════════ -->
      <div class="sec active" id="sec-conversaciones">

        <aside id="sidebar">
          <div id="sh">
            <h2>💬 Conversaciones</h2>
            <span class="cnt" id="total">0</span>
          </div>
          <div id="srch">
            <label for="srinput" style="display:none">Buscar conversaciones</label>
            <input id="srinput" placeholder="Buscar por nombre o número…"
                   aria-label="Buscar conversaciones" oninput="filtrar()">
          </div>
          <div id="cl"></div>
        </aside>

        <section id="chat-area">
          <div id="empty">
            <div class="eic">💬</div>
            <p>Selecciona una conversación para ver el historial</p>
          </div>

          <div id="cv">
            <div id="ch">
              <button id="back" onclick="volverLista()" aria-label="Volver a conversaciones">‹</button>
              <div class="av2">👤</div>
              <div class="inf2">
                <div class="nm2" id="cnm">—</div>
                <div class="st2" id="cst">—</div>
              </div>
              <!-- Botones de acción header (Sprint 4) -->
              <div style="display:flex;gap:6px;align-items:center;margin-left:auto">
                <button onclick="llamarCliente()" title="Llamar"
                  style="background:none;border:none;color:#8696a0;cursor:pointer;font-size:1.15rem;
                  padding:6px 10px;border-radius:6px;transition:all .15s"
                  onmouseover="this.style.background='rgba(255,255,255,.08)';this.style.color='#25d366'"
                  onmouseout="this.style.background='none';this.style.color='#8696a0'">📞</button>
                <button onclick="abrirWhatsAppWeb()" title="Abrir en WhatsApp Web"
                  style="background:none;border:none;color:#8696a0;cursor:pointer;font-size:1.15rem;
                  padding:6px 10px;border-radius:6px;transition:all .15s"
                  onmouseover="this.style.background='rgba(255,255,255,.08)';this.style.color='#25d366'"
                  onmouseout="this.style.background='none';this.style.color='#8696a0'">💚</button>
              </div>
            </div>

            <!-- Modal Llamada (Sprint 4) -->
            <div id="modal-llamada" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;
              background:rgba(0,0,0,.6);z-index:1000;align-items:center;justify-content:center">
              <div style="background:#fff;border-radius:14px;padding:28px;max-width:380px;width:90%;text-align:center">
                <div style="font-size:3rem;margin-bottom:8px">📞</div>
                <h3 style="margin:0 0 6px;color:#1a2332;font-size:1.05rem" id="llamada-nombre">Llamar al cliente</h3>
                <div id="llamada-tel" style="color:#64748b;font-size:.85rem;margin-bottom:20px">—</div>
                <p style="font-size:.83rem;color:#64748b;margin:0 0 18px;line-height:1.5">
                  Elige cómo prefieres llamar:
                </p>
                <button id="btn-llamar-tel" style="width:100%;padding:12px;background:#25d366;color:#fff;border:none;border-radius:8px;font-weight:700;cursor:pointer;font-size:.9rem;margin-bottom:10px">
                  📱 Llamar por teléfono normal
                </button>
                <button id="btn-llamar-wa" style="width:100%;padding:12px;background:#075e54;color:#fff;border:none;border-radius:8px;font-weight:700;cursor:pointer;font-size:.9rem;margin-bottom:14px">
                  💬 Abrir chat en WhatsApp (llamar desde ahí)
                </button>
                <button onclick="cerrarModalLlamada()" style="width:100%;padding:9px;background:#f1f5f9;border:none;border-radius:8px;font-weight:600;cursor:pointer">Cancelar</button>
                <p style="font-size:.72rem;color:#94a3b8;margin:14px 0 0;line-height:1.4">
                  La llamada por WhatsApp se inicia desde la app/web — Meta no permite iniciar llamadas via API todavía.
                </p>
              </div>
            </div>

            <div id="mbar">
              <span class="lbl">Andrea responde</span>
              <label class="tog" aria-label="Activar modo humano">
                <input type="checkbox" id="togInput" onchange="toggleModo()"
                       aria-label="Modo humano — cuando está activo, Andrea no responde">
                <span class="sl"></span>
              </label>
              <span class="lbl">Modo humano</span>
              <span id="mlbl">● Tú estás respondiendo</span>
            </div>

            <div id="msgs"></div>

            <div id="ib">
              <!-- Botón adjuntar (Sprint 4) -->
              <div id="attach-wrap" style="position:relative">
                <button id="attach-btn" onclick="toggleAttachMenu()" aria-label="Adjuntar"
                  style="background:none;border:none;color:#8696a0;font-size:1.4rem;cursor:pointer;padding:4px 8px">📎</button>
                <!-- Menú de opciones -->
                <div id="attach-menu" style="display:none;position:absolute;bottom:42px;left:0;
                  background:#202c33;border-radius:10px;box-shadow:0 4px 16px rgba(0,0,0,.4);
                  padding:6px;min-width:200px;z-index:50">
                  <div class="attach-opt" onclick="abrirSelectorMedia('image')">
                    <span style="background:#7c3aed">🖼</span> Imagen
                  </div>
                  <div class="attach-opt" onclick="abrirSelectorMedia('video')">
                    <span style="background:#dc2626">🎥</span> Video
                  </div>
                  <div class="attach-opt" onclick="abrirSelectorMedia('document')">
                    <span style="background:#2563eb">📄</span> Documento
                  </div>
                  <div class="attach-opt" onclick="abrirUbicacion()">
                    <span style="background:#059669">📍</span> Ubicación
                  </div>
                  <div class="attach-opt" onclick="abrirCatalogoSelector()">
                    <span style="background:#ea580c">🛒</span> Producto
                  </div>
                </div>
                <input type="file" id="media-file-input" accept="image/*" style="display:none"
                  onchange="enviarMediaSeleccionada()">
              </div>
              <label for="ti" style="display:none">Mensaje</label>
              <textarea id="ti" rows="1" placeholder="Escribe un mensaje y presiona Enter…"
                aria-label="Escribe un mensaje"
                onkeydown="onKey(event)" oninput="autoResize()"></textarea>
              <button id="sendbtn" onclick="sendMsg()" aria-label="Enviar mensaje">➤</button>
            </div>

            <!-- Modal: Ubicación (Sprint 4) -->
            <div id="modal-ubicacion" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;
              background:rgba(0,0,0,.6);z-index:1000;align-items:center;justify-content:center">
              <div style="background:#fff;border-radius:12px;padding:24px;max-width:420px;width:90%">
                <h3 style="margin:0 0 14px;color:#1a2332;font-size:1.05rem">📍 Compartir ubicación</h3>
                <div style="display:flex;gap:8px;margin-bottom:10px">
                  <input id="loc-lat" type="number" step="any" placeholder="Latitud" style="flex:1;padding:8px 10px;border:1px solid #dde1e8;border-radius:7px;font-size:.85rem">
                  <input id="loc-lng" type="number" step="any" placeholder="Longitud" style="flex:1;padding:8px 10px;border:1px solid #dde1e8;border-radius:7px;font-size:.85rem">
                </div>
                <input id="loc-nombre" type="text" placeholder="Nombre del lugar (opcional)"
                  style="width:100%;padding:8px 10px;border:1px solid #dde1e8;border-radius:7px;font-size:.85rem;margin-bottom:8px;box-sizing:border-box">
                <input id="loc-dir" type="text" placeholder="Dirección (opcional)"
                  style="width:100%;padding:8px 10px;border:1px solid #dde1e8;border-radius:7px;font-size:.85rem;margin-bottom:14px;box-sizing:border-box">
                <button onclick="usarMiUbicacion()" style="width:100%;padding:8px;background:#f0f4ff;border:1px solid #c7d2fe;color:#4f46e5;border-radius:7px;font-size:.82rem;cursor:pointer;margin-bottom:10px">📡 Usar mi ubicación actual</button>
                <div style="display:flex;gap:8px">
                  <button onclick="cerrarModalUbicacion()" style="flex:1;padding:9px;background:#f1f5f9;border:none;border-radius:7px;font-weight:600;cursor:pointer">Cancelar</button>
                  <button onclick="enviarUbicacion()" style="flex:1;padding:9px;background:#059669;color:#fff;border:none;border-radius:7px;font-weight:600;cursor:pointer">Enviar</button>
                </div>
              </div>
            </div>

            <!-- Modal: Catálogo de productos (Sprint 4) -->
            <div id="modal-catalogo" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;
              background:rgba(0,0,0,.6);z-index:1000;align-items:center;justify-content:center">
              <div style="background:#fff;border-radius:12px;padding:20px;max-width:560px;width:92%;max-height:80vh;display:flex;flex-direction:column">
                <h3 style="margin:0 0 12px;color:#1a2332;font-size:1.05rem">🛒 Enviar producto del catálogo</h3>
                <input id="cat-buscar" type="text" placeholder="Buscar producto…" oninput="buscarCatalogo()"
                  style="width:100%;padding:8px 10px;border:1px solid #dde1e8;border-radius:7px;font-size:.85rem;margin-bottom:12px;box-sizing:border-box">
                <div id="cat-resultados" style="flex:1;overflow-y:auto;border:1px solid #f1f5f9;border-radius:8px;padding:6px;background:#fafbfc"></div>
                <button onclick="cerrarModalCatalogo()" style="margin-top:12px;padding:9px;background:#f1f5f9;border:none;border-radius:7px;font-weight:600;cursor:pointer">Cerrar</button>
              </div>
            </div>

            <!-- Modal: Caption antes de enviar media (Sprint 4) -->
            <div id="modal-caption" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;
              background:rgba(0,0,0,.6);z-index:1000;align-items:center;justify-content:center">
              <div style="background:#fff;border-radius:12px;padding:22px;max-width:420px;width:90%">
                <h3 id="cap-titulo" style="margin:0 0 14px;color:#1a2332;font-size:1rem">Enviar archivo</h3>
                <div id="cap-preview" style="margin-bottom:14px;text-align:center"></div>
                <textarea id="cap-texto" placeholder="Descripción (opcional)…" rows="2"
                  style="width:100%;padding:8px 10px;border:1px solid #dde1e8;border-radius:7px;font-size:.85rem;resize:vertical;box-sizing:border-box;font-family:inherit"></textarea>
                <div id="cap-progress" style="display:none;margin-top:8px;font-size:.82rem;color:#4f46e5">⏳ Enviando…</div>
                <div style="display:flex;gap:8px;margin-top:12px">
                  <button onclick="cerrarModalCaption()" style="flex:1;padding:9px;background:#f1f5f9;border:none;border-radius:7px;font-weight:600;cursor:pointer">Cancelar</button>
                  <button id="cap-enviar-btn" onclick="confirmarEnvioMedia()" style="flex:1;padding:9px;background:#25d366;color:#fff;border:none;border-radius:7px;font-weight:600;cursor:pointer">Enviar</button>
                </div>
              </div>
            </div>
          </div>
        </section>

      </div><!-- /sec-conversaciones -->

      <!-- ═══════════════════════════════════════
           SECCIÓN: DIFUSIONES
           ═══════════════════════════════════════ -->
      <div class="sec sec-light" id="sec-difusiones">
        <div class="sec-hdr">
          <div>
            <h1>📢 Difusiones</h1>
            <p>Envía mensajes masivos a múltiples contactos usando plantillas aprobadas por Meta</p>
          </div>
        </div>
        <div class="sec-body">

          <!-- Fila superior: formulario + preview WhatsApp -->
          <div id="dif-split">

            <!-- Formulario nueva difusión -->
            <div id="dif-form-col">
              <div class="form-card">
                <div style="display:flex;align-items:center;gap:10px;margin-bottom:20px">
                  <div style="font-size:1.3rem">✉️</div>
                  <div>
                    <div style="font-weight:700;color:#1a2332;font-size:.95rem">Nueva difusión</div>
                    <div style="font-size:.78rem;color:#6b7a8d">Solo plantillas aprobadas por Meta</div>
                  </div>
                </div>

                <!-- Nombre de campaña -->
                <div class="f-group" style="margin-bottom:16px">
                  <span class="f-label">Nombre de la campaña</span>
                  <input id="dif-campaign-name" class="f-inp" type="text"
                    placeholder="ej: Promo Mayo – Desengrasante Cocina"
                    maxlength="200" oninput="actualizarConteo()">
                </div>

                <!-- Plantilla -->
                <div class="f-group" style="margin-bottom:16px">
                  <span class="f-label">Plantilla aprobada ✅</span>
                  <select id="dif-tpl" class="f-sel" onchange="seleccionarTemplate()">
                    <option value="">Cargando plantillas...</option>
                  </select>
                </div>

                <!-- Variables de la plantilla -->
                <div id="dif-vars-wrap" style="display:none;margin-bottom:16px">
                  <span class="f-label" style="display:block;margin-bottom:8px">Variables de la plantilla</span>
                  <div id="dif-vars"></div>
                </div>

                <!-- ── CARGUE MASIVO CSV ── -->
                <div class="sep-label" style="margin-top:4px">📥 Cargue masivo de contactos <span class="opt-badge">CSV</span></div>
                <div id="dif-csv-wrap">
                  <label id="dif-csv-label" for="dif-csv-input">📂 Cargar CSV</label>
                  <input type="file" id="dif-csv-input" accept=".csv,text/csv" onchange="cargarArchivoCSV(this)">
                  <button class="btn-dl-csv" onclick="descargarFormatoCSV()" type="button">⬇ Formato</button>
                </div>
                <!-- Estadísticas del CSV (visible tras cargar) -->
                <div id="dif-csv-stats"></div>

                <!-- ── INGRESO MANUAL ── -->
                <div class="dif-manual-hdr">
                  <span>✏️</span> Ingreso manual de contactos
                  <span style="font-weight:400;color:#6b7a8d;font-size:.76rem;margin-left:4px">— uno por línea: número,nombre</span>
                </div>
                <textarea id="dif-phones" class="f-ta" wrap="off"
                  style="min-height:140px;font-family:'Courier New',Courier,monospace;font-size:.8rem;
                         line-height:1.7;overflow-x:auto;white-space:pre;resize:vertical"
                  placeholder="573001234567,Juan García&#10;573009876543,Supermercado La Cosecha del Valle&#10;573001112233,Carlos"
                  oninput="actualizarConteo()"></textarea>
                <div id="dif-conteo" style="font-size:.75rem;color:#6b7a8d;margin-top:4px">0 destinatarios</div>

                <!-- Barra de progreso -->
                <div id="dif-prog-wrap" style="margin-top:12px">
                  <div class="prog-bar-wrap"><div class="prog-bar" id="dif-bar"></div></div>
                  <div class="prog-txt" id="dif-ptxt">Enviando...</div>
                </div>
                <div id="dif-res-box"></div>

                <div style="margin-top:14px">
                  <button class="btn-primary" id="dif-sendbtn" onclick="enviarDifusion()" disabled style="width:100%">
                    📤 Enviar difusión
                  </button>
                </div>
              </div>
            </div><!-- /dif-form-col -->

            <!-- Preview WhatsApp -->
            <div id="dif-wa-prev-col" class="wa-phone">
              <div class="wa-phone-shell">
                <div class="wa-phone-bar">
                  <div class="wa-av">🤖</div>
                  <div>
                    <div class="wa-name">Equora Distribuciones</div>
                    <div class="wa-sub">en línea</div>
                  </div>
                </div>
                <div class="wa-chat">
                  <div class="wa-bubble" id="dif-wa-bubble">
                    <div class="wa-hdr-img" id="dif-prev-hdr-img" style="display:none">
                      <div style="position:relative;z-index:1;font-size:2.5rem">🖼️</div>
                      <img id="dif-prev-hdr-img-tag" src="" style="display:none;position:absolute;inset:0;width:100%;height:100%;object-fit:cover" alt="">
                    </div>
                    <div class="wa-hdr-vid-wrap wa-hdr-img" id="dif-prev-hdr-vid" style="display:none;background:#111">
                      <div style="font-size:2.5rem">🎥</div>
                      <div class="wa-play">▶</div>
                    </div>
                    <div class="wa-hdr-doc" id="dif-prev-hdr-doc" style="display:none">
                      <span style="font-size:1.4rem">📄</span>
                      <div>
                        <div style="font-size:.75rem;font-weight:600;color:#111">documento.pdf</div>
                        <div style="font-size:.68rem;color:#667781">PDF</div>
                      </div>
                    </div>
                    <div class="wa-hdr-txt" id="dif-prev-hdr-txt" style="display:none"></div>
                    <div class="wa-body-text" id="dif-prev-body" style="color:#999;font-style:italic">Selecciona una plantilla para ver la vista previa...</div>
                    <div class="wa-footer-text" id="dif-prev-footer" style="display:none"></div>
                    <div class="wa-ts">10:50 pm <span class="wa-tick">✓✓</span></div>
                    <div class="wa-btns" id="dif-prev-btns" style="display:none"></div>
                  </div>
                </div>
              </div>
              <div class="wa-preview-label">Vista previa · Solo referencia</div>
            </div>

          </div><!-- /dif-split -->

          <!-- Historial abajo, ancho completo -->
          <div id="dif-hist-below">
            <div class="tbl-wrap">
              <div class="tbl-head">
                <h2>📋 Historial de difusiones</h2>
                <button class="btn-secondary" style="padding:6px 14px;font-size:.8rem" onclick="cargarHistorialDif()">↺ Actualizar</button>
              </div>
              <div style="overflow-x:auto">
                <table>
                  <thead>
                    <tr>
                      <th>Campaña</th>
                      <th>Fecha</th>
                      <th style="text-align:center">Enviados</th>
                      <th style="text-align:center">📦 Entregados</th>
                      <th style="text-align:center">👁 Leídos</th>
                      <th style="text-align:center">❌ Fallidos</th>
                      <th style="text-align:center">Detalle</th>
                    </tr>
                  </thead>
                  <tbody id="dif-hist-body">
                    <tr><td colspan="7" class="loading-txt">Sin difusiones enviadas aún</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

        </div>
      </div><!-- /sec-difusiones -->

      <!-- ═══════════════════════════════════════
           SECCIÓN: PLANTILLAS
           ═══════════════════════════════════════ -->
      <div class="sec sec-light" id="sec-plantillas">
        <div class="sec-hdr">
          <div>
            <h1>📋 Plantillas</h1>
            <p>Gestiona y crea plantillas de mensajes para envío masivo</p>
          </div>
        </div>
        <div class="sec-body">
          <div style="display:flex;gap:24px;align-items:flex-start">

            <!-- Lista de plantillas -->
            <div style="flex:1;min-width:0">
              <div class="tbl-wrap" style="margin-bottom:16px">
                <div class="tbl-head">
                  <h2>Plantillas en Meta</h2>
                  <button class="btn-secondary" style="padding:6px 14px;font-size:.8rem" onclick="cargarTablaPlantillas()">↺ Actualizar</button>
                </div>
                <div style="overflow-x:auto">
                  <table>
                    <thead>
                      <tr>
                        <th>Nombre</th>
                        <th>Idioma</th>
                        <th>Estado</th>
                        <th>Variables</th>
                        <th>Header</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody id="tpl-tabla-body">
                      <tr><td colspan="6" class="loading-txt">Cargando...</td></tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <!-- Borradores locales -->
              <div class="tbl-wrap" style="margin-bottom:0">
                <div class="tbl-head">
                  <h2>💾 Borradores locales</h2>
                  <button class="btn-secondary" style="padding:6px 14px;font-size:.8rem" onclick="cargarBorradores()">↺ Actualizar</button>
                </div>
                <div style="overflow-x:auto">
                  <table>
                    <thead>
                      <tr>
                        <th>Nombre</th>
                        <th>Categoría</th>
                        <th>Idioma</th>
                        <th>Guardado</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody id="borr-tabla-body">
                      <tr><td colspan="5" class="loading-txt">Sin borradores</td></tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <!-- Formulario crear plantilla -->
            <div style="width:440px;flex-shrink:0">
              <div class="form-card" style="max-height:calc(100vh - 200px);overflow-y:auto">
                <div style="display:flex;align-items:center;gap:10px;margin-bottom:18px">
                  <div id="tpl-form-icon" style="font-size:1.3rem">✨</div>
                  <div style="flex:1">
                    <div id="tpl-form-title" style="font-weight:700;color:#1a2332;font-size:.95rem">Nueva plantilla</div>
                    <div id="tpl-form-sub" style="font-size:.76rem;color:#6b7a8d">Se envía a Meta · Aprobación en 24-48 h</div>
                  </div>
                  <button id="tpl-cancelar-btn" class="btn-secondary" onclick="cancelarEdicion()" style="display:none;padding:4px 12px;font-size:.78rem">✕ Cancelar edición</button>
                </div>
                <!-- ID oculto de la plantilla Meta (cuando se edita) -->
                <input type="hidden" id="tpl-meta-id" value="">

                <!-- Nombre + Categoría -->
                <div class="form-grid" style="margin-bottom:10px">
                  <div class="f-group">
                    <span class="f-label">Nombre <span class="req">*</span></span>
                    <input id="tpl-nombre" class="f-inp" placeholder="oferta_especial"
                      oninput="this.value=this.value.toLowerCase().replace(/[^a-z0-9_]/g,'_')">
                    <span class="f-hint">Letras minúsculas, números y _ · Sin espacios · Máx 512 chars</span>
                  </div>
                  <div class="f-group">
                    <span class="f-label">Categoría <span class="req">*</span></span>
                    <select id="tpl-cat" class="f-sel" onchange="actualizarSubcat()">
                      <option value="MARKETING">📣 Marketing</option>
                      <option value="UTILITY">🔔 Utilidad</option>
                      <option value="AUTHENTICATION">🔐 Autenticación</option>
                    </select>
                    <span class="f-hint">Marketing: promos · Utilidad: confirmaciones · Auth: OTP</span>
                  </div>
                </div>

                <!-- Subcategoría (depende de la categoría) -->
                <div class="f-group" style="margin-bottom:14px" id="subcat-wrap">
                  <span class="f-label">Tipo de plantilla</span>
                  <div id="subcat-opts" class="radio-group" style="flex-direction:column;gap:8px">
                    <!-- se rellena dinámicamente -->
                  </div>
                </div>

                <!-- Idioma -->
                <div class="f-group" style="margin-bottom:14px">
                  <span class="f-label">Idioma</span>
                  <select id="tpl-lang" class="f-sel">
                    <option value="es_CO">🇨🇴 Español (Colombia)</option>
                    <option value="es">🌎 Español (genérico)</option>
                    <option value="es_AR">🇦🇷 Español (Argentina)</option>
                    <option value="es_MX">🇲🇽 Español (México)</option>
                    <option value="en_US">🇺🇸 English (US)</option>
                    <option value="pt_BR">🇧🇷 Português (Brasil)</option>
                  </select>
                </div>

                <!-- ── CATÁLOGO (visible solo cuando subcat=CATALOG_MESSAGE) ── -->
                <div id="catalog-section" style="display:none;margin-bottom:14px">
                  <div class="sep-label">🛍️ Formato del catálogo</div>
                  <div class="info-box" style="margin-bottom:10px">
                    Conecta tu catálogo de productos para enviar mensajes de ventas directamente en WhatsApp.<br>
                    <b>Nota:</b> No se permiten archivos multimedia en plantillas de catálogo. El catálogo vinculado se mostrará automáticamente.
                  </div>
                  <div id="catalog-format-opts" style="display:flex;flex-direction:column;gap:8px;margin-bottom:10px">
                    <label class="radio-opt chk" style="flex-direction:column;align-items:flex-start;padding:10px 14px;border-radius:8px;border:1px solid #e0e4e8;background:#fafbfc;gap:2px;cursor:pointer">
                      <span style="display:flex;align-items:center;gap:8px"><input type="radio" name="catalog-format" value="FULL" checked> <b style="font-size:.84rem;color:#1a2332">Mensaje de catálogo</b></span>
                      <span style="font-size:.75rem;color:#6b7a8d;padding-left:22px">Incluye todo el catálogo para ofrecer una visión completa de todos tus productos.</span>
                    </label>
                    <label class="radio-opt" style="flex-direction:column;align-items:flex-start;padding:10px 14px;border-radius:8px;border:1px solid #e0e4e8;background:#fafbfc;gap:2px;cursor:pointer">
                      <span style="display:flex;align-items:center;gap:8px"><input type="radio" name="catalog-format" value="MULTI"> <b style="font-size:.84rem;color:#1a2332">Mensaje multiproducto</b></span>
                      <span style="font-size:.75rem;color:#6b7a8d;padding-left:22px">Incluye hasta 30 productos específicos del catálogo. Deberás especificar los productos al enviar la plantilla via API.</span>
                    </label>
                  </div>
                </div>

                <!-- ── ENCABEZADO ── -->
                <div id="hdr-section">
                <div class="sep-label">📌 Encabezado <span class="opt-badge">Opcional</span></div>

                <div class="f-group" style="margin-bottom:10px">
                  <span class="f-label">Tipo de encabezado</span>
                  <div class="radio-group" id="hdr-radio-group">
                    <label class="radio-opt chk"><input type="radio" name="hdr-type" value="NONE" checked onchange="toggleHdrType('NONE')"> Ninguno</label>
                    <label class="radio-opt"><input type="radio" name="hdr-type" value="IMAGE" onchange="toggleHdrType('IMAGE')"> 🖼️ Imagen</label>
                    <label class="radio-opt"><input type="radio" name="hdr-type" value="VIDEO" onchange="toggleHdrType('VIDEO')"> 🎥 Video</label>
                    <label class="radio-opt"><input type="radio" name="hdr-type" value="DOCUMENT" onchange="toggleHdrType('DOCUMENT')"> 📄 Documento</label>
                    <label class="radio-opt"><input type="radio" name="hdr-type" value="LOCATION" onchange="toggleHdrType('LOCATION')"> 📍 Ubicación</label>
                  </div>
                </div>

                <!-- Header: TEXTO -->
                <div id="hdr-text-wrap" style="display:none;margin-bottom:10px">
                  <div class="f-group">
                    <input id="tpl-hdr-text" class="f-inp" maxlength="60"
                      placeholder="Ej: ¡Oferta especial para ti! 🌿"
                      oninput="updateCounter('tpl-hdr-text','hdr-txt-cnt',60)">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:3px">
                      <span class="f-hint">Permite 1 variable — escribe <code>{{1}}</code> donde quieras</span>
                      <span class="char-counter"><span id="hdr-txt-cnt">0</span>/60</span>
                    </div>
                  </div>
                </div>

                <!-- Header: IMAGEN -->
                <div id="hdr-img-wrap" style="display:none;margin-bottom:10px">
                  <div class="info-box">
                    <b>📐 Especificaciones de imagen:</b><br>
                    • <b>Formato:</b> JPG o PNG<br>
                    • <b>Tamaño máximo:</b> 5 MB<br>
                    • <b>Resolución recomendada:</b> 800 × 418 px (ratio 1.91:1)<br>
                    • <b>Mínimo aceptado:</b> 250 × 250 px<br>
                    • La imagen se usa como ejemplo para que Meta revise tu plantilla
                  </div>
                  <div class="upload-zone" id="img-zone" onclick="document.getElementById('tpl-img-file').click()"
                    ondragover="e=event;e.preventDefault();this.classList.add('drag')"
                    ondragleave="this.classList.remove('drag')"
                    ondrop="e=event;e.preventDefault();this.classList.remove('drag');handleDrop(e,'img')">
                    <div class="uz-ic">🖼️</div>
                    <div class="uz-title">Haz clic o arrastra tu imagen aquí</div>
                    <div class="uz-hint">JPG o PNG · Máx 5 MB · Recomendado 800×418 px</div>
                  </div>
                  <input type="file" id="tpl-img-file" accept="image/jpeg,image/png" style="display:none"
                    onchange="seleccionarArchivo(this,'img',5)">
                  <div id="img-preview" style="display:none" class="file-preview">
                    <span class="fp-ic">🖼️</span>
                    <span class="fp-name" id="img-fname"></span>
                    <span class="fp-size" id="img-fsize"></span>
                    <button class="fp-remove" onclick="limpiarArchivo('img')" title="Quitar">✕</button>
                  </div>
                  <div id="img-upload-prog" class="progress-upload">
                    <span class="pu-spinner">⟳</span> Subiendo imagen a Meta...
                  </div>
                </div>

                <!-- Header: VIDEO -->
                <div id="hdr-vid-wrap" style="display:none;margin-bottom:10px">
                  <div class="info-box">
                    <b>🎬 Especificaciones de video:</b><br>
                    • <b>Formato:</b> MP4 (códec H.264 · audio AAC)<br>
                    • <b>Tamaño máximo:</b> 16 MB<br>
                    • <b>Duración máxima:</b> 60 segundos<br>
                    • <b>Resolución recomendada:</b> 1280 × 720 px (16:9)<br>
                    • Evita videos con subtítulos codificados (se ven mal en móvil)
                  </div>
                  <div class="upload-zone" id="vid-zone" onclick="document.getElementById('tpl-vid-file').click()"
                    ondragover="e=event;e.preventDefault();this.classList.add('drag')"
                    ondragleave="this.classList.remove('drag')"
                    ondrop="e=event;e.preventDefault();this.classList.remove('drag');handleDrop(e,'vid')">
                    <div class="uz-ic">🎥</div>
                    <div class="uz-title">Haz clic o arrastra tu video aquí</div>
                    <div class="uz-hint">MP4 (H.264) · Máx 16 MB · Máx 60 segundos</div>
                  </div>
                  <input type="file" id="tpl-vid-file" accept="video/mp4,video/3gpp" style="display:none"
                    onchange="seleccionarArchivo(this,'vid',16)">
                  <div id="vid-preview" style="display:none" class="file-preview">
                    <span class="fp-ic">🎥</span>
                    <span class="fp-name" id="vid-fname"></span>
                    <span class="fp-size" id="vid-fsize"></span>
                    <button class="fp-remove" onclick="limpiarArchivo('vid')" title="Quitar">✕</button>
                  </div>
                  <div id="vid-upload-prog" class="progress-upload">
                    <span class="pu-spinner">⟳</span> Subiendo video a Meta...
                  </div>
                </div>

                <!-- Header: DOCUMENTO -->
                <div id="hdr-doc-wrap" style="display:none;margin-bottom:10px">
                  <div class="info-box">
                    <b>📑 Especificaciones de documento:</b><br>
                    • <b>Formato:</b> PDF únicamente<br>
                    • <b>Tamaño máximo:</b> 100 MB<br>
                    • El nombre del archivo se mostrará al destinatario<br>
                    • Recomendado para catálogos, fichas técnicas, facturas
                  </div>
                  <div class="upload-zone" id="doc-zone" onclick="document.getElementById('tpl-doc-file').click()"
                    ondragover="e=event;e.preventDefault();this.classList.add('drag')"
                    ondragleave="this.classList.remove('drag')"
                    ondrop="e=event;e.preventDefault();this.classList.remove('drag');handleDrop(e,'doc')">
                    <div class="uz-ic">📄</div>
                    <div class="uz-title">Haz clic o arrastra tu PDF aquí</div>
                    <div class="uz-hint">Solo PDF · Máx 100 MB</div>
                  </div>
                  <input type="file" id="tpl-doc-file" accept="application/pdf" style="display:none"
                    onchange="seleccionarArchivo(this,'doc',100)">
                  <div id="doc-preview" style="display:none" class="file-preview">
                    <span class="fp-ic">📄</span>
                    <span class="fp-name" id="doc-fname"></span>
                    <span class="fp-size" id="doc-fsize"></span>
                    <button class="fp-remove" onclick="limpiarArchivo('doc')" title="Quitar">✕</button>
                  </div>
                  <div id="doc-upload-prog" class="progress-upload">
                    <span class="pu-spinner">⟳</span> Subiendo documento a Meta...
                  </div>
                </div>

                <!-- Header: UBICACIÓN -->
                <div id="hdr-location-wrap" style="display:none;margin-bottom:10px">
                  <div class="info-box">
                    <b>📍 Encabezado de ubicación:</b><br>
                    • El cliente verá un mapa estático como encabezado del mensaje<br>
                    • Debes enviar <code>latitude</code>, <code>longitude</code> y <code>name</code> al usar la plantilla via API<br>
                    • No requiere subir ningún archivo — Meta usa las coordenadas en tiempo real<br>
                    • Ideal para: confirmación de punto de entrega, tiendas físicas, eventos
                  </div>
                  <div style="display:flex;gap:10px;margin-top:8px">
                    <div class="f-group" style="flex:1">
                      <span class="f-label">Latitud de ejemplo</span>
                      <input id="tpl-loc-lat" class="f-inp" placeholder="3.4516" type="number" step="any">
                    </div>
                    <div class="f-group" style="flex:1">
                      <span class="f-label">Longitud de ejemplo</span>
                      <input id="tpl-loc-lng" class="f-inp" placeholder="-76.5320" type="number" step="any">
                    </div>
                  </div>
                  <div class="f-group" style="margin-top:8px">
                    <span class="f-label">Nombre del lugar (ejemplo)</span>
                    <input id="tpl-loc-name" class="f-inp" placeholder="Equora Distribuciones — Cali">
                  </div>
                </div>
                </div><!-- /hdr-section -->

                <!-- ── CUERPO ── -->
                <div class="sep-label">📝 Cuerpo del mensaje <span class="req">*</span></div>
                <div class="f-group" style="margin-bottom:4px">
                  <textarea id="tpl-body" class="f-ta" maxlength="1024"
                    placeholder="Hola {{nombre}}, tenemos una oferta especial para ti en Equora Distribuciones 🌿"
                    oninput="updateBodyCounter()"></textarea>
                  <div style="display:flex;justify-content:space-between;align-items:center;margin-top:3px">
                    <span class="f-hint">Campo requerido</span>
                    <span class="char-counter"><span id="body-cnt">0</span>/1024</span>
                  </div>
                  <div id="body-emoji-warn" style="display:none;font-size:.78rem;color:#e53935;margin-top:5px;font-weight:500">
                    ⚠️ La plantilla de marketing no debe tener más de 10 emojis
                  </div>
                </div>
                <div class="info-box" style="margin-bottom:10px">
                  <b>✏️ Formato de texto:</b> <code>*negrita*</code> &nbsp; <code>_cursiva_</code> &nbsp; <code>~tachado~</code> &nbsp; <code>```monoespaciado```</code><br>
                  <b>⚠️ No usar:</b> saltos de línea excesivos, emojis en exceso, mayúsculas totales, URLs acortadas
                </div>

                <!-- Tipo de variable -->
                <div class="f-group" style="margin-bottom:14px">
                  <span class="f-label">Tipo de variable <span class="opt-badge">Opcional</span></span>
                  <div class="radio-group" style="gap:10px">
                    <label class="radio-opt chk" id="vartype-num-lbl">
                      <input type="radio" name="var-type" value="NUMERO" checked onchange="actualizarTipoVar('NUMERO')">
                      Número &nbsp;<span style="font-size:.72rem;color:#6b7a8d">usa <code>{{1}}</code>, <code>{{2}}</code>…</span>
                    </label>
                    <label class="radio-opt" id="vartype-name-lbl">
                      <input type="radio" name="var-type" value="NOMBRE" onchange="actualizarTipoVar('NOMBRE')">
                      Nombre &nbsp;<span style="font-size:.72rem;color:#6b7a8d">usa <code>{{nombre}}</code>, <code>{{ciudad}}</code>…</span>
                    </label>
                  </div>
                  <span class="f-hint" id="vartype-hint">Escribe <code>{{1}}</code>, <code>{{2}}</code>… en el cuerpo para insertar variables posicionales</span>
                </div>

                <!-- ── PIE DE PÁGINA ── -->
                <div class="sep-label">📎 Pie de página <span class="opt-badge">Opcional</span></div>
                <div class="f-group" style="margin-bottom:14px">
                  <input id="tpl-footer" class="f-inp" maxlength="60"
                    placeholder="Responde STOP para dejar de recibir mensajes"
                    oninput="updateCounter('tpl-footer','footer-cnt',60)">
                  <div style="display:flex;justify-content:space-between;align-items:center;margin-top:3px">
                    <span class="f-hint">Texto gris pequeño debajo del cuerpo · No admite variables ni formato</span>
                    <span class="char-counter"><span id="footer-cnt">0</span>/60</span>
                  </div>
                </div>

                <!-- ── PERÍODO DE VALIDEZ (solo Marketing) ── -->
                <div id="ttl-wrap" style="display:none;margin-bottom:14px">
                  <div class="sep-label">⏱️ Período de validez <span class="opt-badge">Solo Marketing</span></div>
                  <div class="info-box" style="margin-bottom:10px">
                    <b>¿Para qué sirve?</b> Si el mensaje no se entrega dentro del período elegido, Meta lo cancela y <b>no te cobra</b> esa conversación. Útil para ofertas con fecha límite o mensajes urgentes.<br>
                    Si no activas esto, WhatsApp aplica el período estándar de <b>30 días</b>.
                  </div>
                  <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
                    <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:.84rem;font-weight:600;color:#2d3748">
                      <input type="checkbox" id="ttl-activo" onchange="toggleTTL()"
                        style="width:16px;height:16px;accent-color:var(--az);cursor:pointer">
                      Activar período de validez personalizado
                    </label>
                  </div>
                  <div id="ttl-sel-wrap" style="display:none">
                    <div class="f-group">
                      <span class="f-label">Período de validez</span>
                      <select id="tpl-ttl" class="f-sel">
                        <option value="1800">⚡ 30 minutos</option>
                        <option value="3600">🕐 1 hora</option>
                        <option value="7200">🕑 2 horas</option>
                        <option value="21600">🕕 6 horas</option>
                        <option value="43200" selected>🕛 12 horas</option>
                        <option value="86400">📅 24 horas</option>
                        <option value="172800">📅 48 horas</option>
                        <option value="259200">📅 72 horas</option>
                      </select>
                      <span class="f-hint">Si el mensaje no se entrega en este tiempo, se cancela sin costo</span>
                    </div>
                  </div>
                </div>

                <!-- ── BOTONES ── -->
                <div id="btn-section">

                <!-- Aviso fijo: catálogo (visible solo con CATALOG_MESSAGE) -->
                <div id="catalog-btn-notice" style="display:none;margin-bottom:10px">
                  <div class="sep-label">🔘 Botones</div>
                  <div class="info-box" style="background:#f0f9f6;border-color:#b2dfdb">
                    ℹ️ Solo se admite un botón para este tipo de plantilla. Meta agrega automáticamente el botón <b>"Ver catálogo"</b> y su texto no es editable.
                  </div>
                </div>

                <!-- Aviso fijo: permisos de llamada (visible solo con CALL_PERMISSION_REQUEST) -->
                <div id="call-perm-notice" style="display:none;margin-bottom:10px">
                  <div class="sep-label">🔘 Botones</div>
                  <div class="info-box" style="background:#fff8e1;border-color:#ffc107">
                    ℹ️ Solo se admite un botón para este tipo de plantilla. Meta genera automáticamente las opciones de permiso de llamada. El texto del botón no es editable.
                  </div>
                </div>

                <div id="btn-controls">
                <div class="sep-label">🔘 Botones <span class="opt-badge">Opcional</span></div>
                <div class="info-box" style="margin-bottom:10px;font-size:.8rem">
                  <b>↩️ Personalizado:</b> max 3 · <b>🔗 Sitio web:</b> max 2 · <b>📞 Teléfono:</b> max 1 · <b>🏷️ Código:</b> max 1 · <b>Total:</b> max 10
                </div>
                <div id="btn-list" style="margin-bottom:8px"></div>
                <div class="btn-add-wrap">
                  <button class="btn-secondary" style="padding:6px 14px;font-size:.8rem"
                          onclick="_toggleBtnMenu(event)" type="button" id="agregar-btn-trigger">
                    + Agregar botón ▾
                  </button>
                  <div id="btn-type-menu" class="btn-type-menu">
                    <div class="btn-menu-item" onclick="_agregarBoton('QUICK_REPLY')">↩️ Personalizado <span style="font-size:.72rem;color:#6b7a8d">(respuesta rápida)</span></div>
                    <div class="btn-menu-item" onclick="_agregarBoton('URL')">🔗 Ir al sitio web</div>
                    <div class="btn-menu-item" onclick="_agregarBoton('WHATSAPP_VOICE_CALL')">📲 Llamar en WhatsApp</div>
                    <div class="btn-menu-item" onclick="_agregarBoton('PHONE_NUMBER')">📞 Llamar a número de teléfono</div>
                    <div class="btn-menu-item" onclick="_agregarBoton('FLOW')">🔄 Flow completo</div>
                    <div class="btn-menu-item" onclick="_agregarBoton('COPY_CODE')">🏷️ Copiar código de oferta</div>
                  </div>
                </div>
                </div><!-- /btn-controls -->

                </div><!-- /btn-section -->

                <!-- Panel de aprobación (se muestra tras envío exitoso) -->
                <div id="tpl-approval-panel" style="display:none;margin-bottom:14px;background:#eaf6ff;border:1.5px solid #90caf9;border-radius:10px;padding:16px 18px">
                  <div style="font-weight:700;color:#1a5276;font-size:.95rem;margin-bottom:8px">📨 Plantilla enviada a Meta para aprobación</div>
                  <div style="font-size:.83rem;color:#154360;line-height:1.7">
                    <b>¿Qué pasa ahora?</b><br>
                    1. Meta revisa que el contenido cumpla sus <a href="https://developers.facebook.com/docs/whatsapp/message-templates/guidelines" target="_blank" style="color:#1565c0">políticas de plantillas</a>.<br>
                    2. El proceso tarda generalmente <b>entre 24 y 48 horas</b> (a veces minutos).<br>
                    3. Cuando sea aprobada, aparecerá en la tabla con estado <span style="background:#d4edda;color:#155724;padding:1px 6px;border-radius:4px;font-size:.78rem">✅ Aprobada</span>.<br>
                    4. Si es rechazada, revisa el motivo en el <a href="https://business.facebook.com/wa/manage/message-templates/" target="_blank" style="color:#1565c0">Manager de Meta</a> y edítala.<br>
                  </div>
                  <div id="tpl-approval-name" style="margin-top:10px;font-size:.82rem;color:#1a5276;font-weight:600"></div>
                </div>
                <!-- Resultado inline (errores) -->
                <div id="tpl-result" style="display:none;margin-bottom:14px;font-size:.83rem;padding:10px 14px;border-radius:8px;line-height:1.5"></div>
                <!-- Botones acción -->
                <div style="display:flex;gap:10px">
                  <button class="btn-secondary" id="tpl-borrador-btn" onclick="guardarBorrador()" style="flex:1">
                    💾 Guardar borrador
                  </button>
                  <button class="btn-primary" id="tpl-crear-btn" onclick="crearOEditarPlantilla()" style="flex:2">
                    📤 Enviar a Meta para aprobación
                  </button>
                </div>
              </div>
            </div>

            <!-- Vista previa WhatsApp -->
            <div class="wa-phone" id="wa-preview-col">
              <div class="wa-phone-shell">
                <!-- Barra de contacto estilo WhatsApp -->
                <div class="wa-phone-bar">
                  <div class="wa-av">🤖</div>
                  <div>
                    <div class="wa-name" id="prev-contact-name">Equora Distribuciones</div>
                    <div class="wa-sub">en línea</div>
                  </div>
                </div>
                <!-- Chat area -->
                <div class="wa-chat">
                  <div class="wa-bubble" id="wa-bubble">
                    <!-- Header imagen (placeholder) -->
                    <div class="wa-hdr-img" id="prev-hdr-img" style="display:none">
                      <div class="wa-hdr-emoji" id="prev-hdr-img-emoji">🖼️</div>
                      <img id="prev-hdr-img-tag" src="" style="display:none" alt="">
                    </div>
                    <!-- Header video -->
                    <div class="wa-hdr-img wa-hdr-vid-wrap" id="prev-hdr-vid" style="display:none;background:#111">
                      <div class="wa-hdr-emoji">🎥</div>
                      <div class="wa-play">▶</div>
                    </div>
                    <!-- Header documento -->
                    <div class="wa-hdr-doc" id="prev-hdr-doc" style="display:none">
                      <span style="font-size:1.4rem">📄</span>
                      <div>
                        <div style="font-size:.75rem;font-weight:600;color:#111" id="prev-doc-name">documento.pdf</div>
                        <div style="font-size:.68rem;color:#667781">PDF</div>
                      </div>
                    </div>
                    <!-- Header texto -->
                    <div class="wa-hdr-txt" id="prev-hdr-txt" style="display:none"></div>
                    <!-- Cuerpo -->
                    <div class="wa-body-text" id="prev-body">Escribe el mensaje aquí para ver la vista previa...</div>
                    <!-- Footer -->
                    <div class="wa-footer-text" id="prev-footer" style="display:none"></div>
                    <!-- Timestamp -->
                    <div class="wa-ts">10:50 pm <span class="wa-tick">✓✓</span></div>
                    <!-- Botones -->
                    <div class="wa-btns" id="prev-btns" style="display:none"></div>
                  </div>
                </div>
              </div>
              <div class="wa-preview-label">Vista previa · Solo referencia</div>
            </div>

          </div>
        </div>
      </div><!-- /sec-plantillas -->

      <!-- ═══════════════════════════════════════
           SECCIÓN: MÉTRICAS
           ═══════════════════════════════════════ -->
      <div class="sec sec-light" id="sec-metricas">
        <div class="sec-hdr">
          <div>
            <h1>📊 Métricas</h1>
            <p>Rendimiento de campañas, costo Meta y ventas atribuidas</p>
          </div>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <!-- Periodo rápido -->
            <select id="met-periodo" onchange="metAplicarPreset(this.value)" style="padding:6px 10px;border:1px solid #dde1e7;border-radius:8px;font-size:.82rem;color:#1a2332">
              <option value="7">Últimos 7 días</option>
              <option value="30" selected>Últimos 30 días</option>
              <option value="90">Últimos 90 días</option>
              <option value="custom">Rango personalizado</option>
            </select>
            <!-- Date pickers (ocultos por defecto, se muestran con "custom") -->
            <div id="met-rango-custom" style="display:none;gap:6px;align-items:center">
              <label style="font-size:.78rem;color:#475569">Desde:</label>
              <input id="met-desde" type="date" style="padding:5px 8px;border:1px solid #dde1e7;border-radius:7px;font-size:.82rem">
              <label style="font-size:.78rem;color:#475569">Hasta:</label>
              <input id="met-hasta" type="date" style="padding:5px 8px;border:1px solid #dde1e7;border-radius:7px;font-size:.82rem">
            </div>
            <!-- Granularidad -->
            <label style="font-size:.78rem;color:#475569;margin-left:6px">Agrupar:</label>
            <select id="met-granularidad" onchange="cargarMetricas()" style="padding:6px 10px;border:1px solid #dde1e7;border-radius:8px;font-size:.82rem;color:#1a2332">
              <option value="dia" selected>Diario</option>
              <option value="semana">Semanal</option>
              <option value="mes">Mensual</option>
            </select>
            <button class="btn-secondary" onclick="cargarMetricas()">↺ Actualizar</button>
          </div>
          <!-- Tabs métricas -->
          <div style="display:flex;border-bottom:1px solid #e2e8f0;margin-top:4px">
            <button class="det-tab active" id="met-tab-camp" onclick="metTab('camp',this)" style="font-size:.8rem;padding:8px 14px">📊 Campañas</button>
            <button class="det-tab" id="met-tab-equipo" onclick="metTab('equipo',this);cargarStatsEquipo()" style="font-size:.8rem;padding:8px 14px">👥 Equipo</button>
          </div>
        </div>
        <div class="sec-body">

          <!-- Fila 1: KPIs globales de difusiones -->
          <div style="margin-bottom:6px">
            <p style="font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#6b7a8d;margin:0 0 10px">📤 Difusiones del período</p>
          </div>
          <div class="cards" id="met-cards-dif">
            <div class="loading-txt" style="grid-column:1/-1">Cargando...</div>
          </div>

          <!-- Fila 2: Costo Meta + Ventas + ROI -->
          <div style="margin:24px 0 6px">
            <p style="font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#6b7a8d;margin:0 0 10px">💰 Costo & Retorno</p>
          </div>
          <div class="cards" id="met-cards-roi">
            <div class="loading-txt" style="grid-column:1/-1">Cargando...</div>
          </div>

          <!-- Fila 3: Conversaciones IA -->
          <div style="margin:24px 0 6px">
            <p style="font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#6b7a8d;margin:0 0 10px">🤖 Conversaciones IA</p>
          </div>
          <div class="cards" id="met-cards-conv">
            <div class="loading-txt" style="grid-column:1/-1">Cargando...</div>
          </div>

          <!-- Series temporales (gráfica + tabla por período) -->
          <div id="met-series-wrap"></div>

          <!-- Tabla por campaña -->
          <div class="tbl-wrap" style="margin-top:28px">
            <div class="tbl-head">
              <h2>Rendimiento por campaña</h2>
              <span id="met-aviso-tracking" style="font-size:.75rem;color:#6b7a8d;display:none">
                ⓘ % entrega/lectura solo en campañas con tracking activo
              </span>
            </div>
            <div style="overflow-x:auto">
              <table id="met-camp-tbl">
                <thead id="met-camp-thead">
                  <tr>
                    <th>Campaña</th>
                    <th>Fecha</th>
                    <th style="text-align:right">Enviados</th>
                    <th style="text-align:right">📦 Entregados</th>
                    <th style="text-align:right">👁 Leídos</th>
                    <th style="text-align:right">❌ Fallidos</th>
                    <th style="text-align:right">💵 Costo Meta</th>
                    <th style="text-align:right" id="met-th-ventas" class="met-col-roi">🛒 Ventas 7d</th>
                    <th style="text-align:right" id="met-th-roas"   class="met-col-roi">📈 ROAS</th>
                  </tr>
                </thead>
                <tbody id="met-camp-body">
                  <tr><td colspan="9" class="loading-txt">Cargando...</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Panel Equipo (supervisor) -->
          <div id="met-panel-equipo" style="display:none;padding:20px">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
              <h2 style="margin:0;font-size:1rem;color:#1a2332">👥 Métricas del equipo de soporte</h2>
              <button class="btn-secondary" style="font-size:.78rem" onclick="cargarStatsEquipo()">↺ Actualizar</button>
            </div>
            <div id="met-equipo-tabla" style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden">
              <div style="padding:14px;color:#94a3b8;font-size:.85rem;text-align:center">Cargando...</div>
            </div>
            <!-- Toggle auto-asignación -->
            <div style="margin-top:20px;padding:14px 18px;background:#f0f4ff;border:1px solid #c7d2fe;border-radius:10px;display:flex;align-items:center;gap:14px">
              <div style="flex:1">
                <div style="font-weight:700;font-size:.88rem;color:#1a2332">⚡ Asignación automática (Round-Robin)</div>
                <div style="font-size:.78rem;color:#64748b;margin-top:2px">Cuando llega un ticket, se asigna al siguiente agente disponible automáticamente</div>
              </div>
              <label style="display:flex;align-items:center;gap:8px;cursor:pointer;flex-shrink:0">
                <input type="checkbox" id="toggle-autoasignar" onchange="toggleAutoAsignar(this.checked)"
                  style="width:18px;height:18px;cursor:pointer;accent-color:#4f46e5">
                <span id="autoasignar-label" style="font-size:.82rem;font-weight:600;color:#4f46e5">Inactivo</span>
              </label>
            </div>
          </div>

        </div>
      </div><!-- /sec-metricas -->

      <!-- ═══════════════════════════════════════
           SECCIÓN: CLIENTES
           ═══════════════════════════════════════ -->
      <div class="sec sec-light" id="sec-clientes">
        <div class="sec-hdr">
          <div>
            <h1>👥 Clientes</h1>
            <p>Base de clientes segmentada por nivel de engagement</p>
          </div>
          <div style="display:flex;gap:8px">
            <button class="btn-secondary" style="padding:7px 16px;font-size:.82rem"
                    onclick="abrirImportarCSV()" aria-label="Importar clientes desde CSV">📥 Importar CSV</button>
            <button class="btn-secondary" style="padding:7px 16px;font-size:.82rem"
                    onclick="cargarClientes()" aria-label="Actualizar lista de clientes">↺ Actualizar</button>
          </div>
        </div>
        <div class="sec-body">

          <!-- Stat cards por estado -->
          <div class="estado-cards" id="cli-cards">
            <div class="estado-card ec-total" onclick="filtrarClientes('todos')" role="button" tabindex="0"
                 aria-label="Ver todos los clientes">
              <div class="ec-val" id="ec-total">—</div>
              <div class="ec-lbl">Total clientes</div>
              <div class="ec-sub">toda la base</div>
            </div>
            <div class="estado-card ec-activo" onclick="filtrarClientes('activo')" role="button" tabindex="0"
                 aria-label="Ver clientes activos">
              <div class="ec-val" id="ec-activo">—</div>
              <div class="ec-lbl">🟢 Activos</div>
              <div class="ec-sub">últimos 30 días</div>
            </div>
            <div class="estado-card ec-tibio" onclick="filtrarClientes('tibio')" role="button" tabindex="0"
                 aria-label="Ver clientes tibios">
              <div class="ec-val" id="ec-tibio">—</div>
              <div class="ec-lbl">🟡 Tibios</div>
              <div class="ec-sub">30 – 90 días</div>
            </div>
            <div class="estado-card ec-frio" onclick="filtrarClientes('frio')" role="button" tabindex="0"
                 aria-label="Ver clientes fríos">
              <div class="ec-val" id="ec-frio">—</div>
              <div class="ec-lbl">🔵 Fríos</div>
              <div class="ec-sub">más de 90 días</div>
            </div>
            <div class="estado-card ec-baja" onclick="filtrarClientes('baja')" role="button" tabindex="0"
                 aria-label="Ver clientes dados de baja">
              <div class="ec-val" id="ec-baja">—</div>
              <div class="ec-lbl">🚫 Bajas</div>
              <div class="ec-sub">opt-out activo</div>
            </div>
          </div>

          <!-- Filtros + búsqueda -->
          <div class="cli-filters" role="group" aria-label="Filtrar clientes por estado">
            <button class="cli-pill active" data-est="todos"   onclick="filtrarClientes('todos')"  >Todos</button>
            <button class="cli-pill"        data-est="activo"  onclick="filtrarClientes('activo')" >🟢 Activos</button>
            <button class="cli-pill"        data-est="tibio"   onclick="filtrarClientes('tibio')"  >🟡 Tibios</button>
            <button class="cli-pill"        data-est="frio"    onclick="filtrarClientes('frio')"   >🔵 Fríos</button>
            <button class="cli-pill"        data-est="baja"    onclick="filtrarClientes('baja')"   >🚫 Baja</button>
            <div class="cli-search" style="margin-left:auto">
              <label for="cli-q" style="display:none">Buscar cliente</label>
              <input id="cli-q" type="search" placeholder="Buscar nombre o número…"
                     aria-label="Buscar cliente" oninput="renderClientes()">
            </div>
          </div>

          <!-- Tabla -->
          <div class="cli-tbl-wrap">
            <div class="cli-tbl-info">
              Mostrando <strong id="cli-count">—</strong> clientes
            </div>
            <div style="overflow-x:auto">
              <table>
                <thead>
                  <tr>
                    <th style="width:44px"></th>
                    <th>Nombre / Teléfono</th>
                    <th>Ciudad</th>
                    <th>Último contacto</th>
                    <th>Estado</th>
                    <th style="text-align:center">Pedidos</th>
                    <th style="text-align:center">Mensajes</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody id="cli-tbody">
                  <tr><td colspan="8" class="loading-txt">Cargando clientes…</td></tr>
                </tbody>
              </table>
            </div>
          </div>

        </div>
      </div><!-- /sec-clientes -->

      <!-- ══════════════════════════════════════════════════════
           MODAL: Importar CSV de clientes
           ══════════════════════════════════════════════════════ -->
      <div id="modal-importar-csv" class="modal-overlay" style="display:none" onclick="cerrarImportarCSV(event)">
        <div class="modal-box" style="max-width:520px" onclick="event.stopPropagation()">
          <div class="modal-hdr">
            <div>
              <div class="modal-title">📥 Importar clientes desde CSV</div>
              <div class="modal-sub">
                Requeridas: <strong>telefono · nombres · apellidos</strong> · Opcionales: ciudad, departamento, email, cc_nit
                &nbsp;·&nbsp;
                <a href="/inbox/api/clientes/import/template" download="plantilla_clientes.csv"
                   style="color:#2563eb;font-weight:600;text-decoration:none">
                  ⬇ Descargar plantilla
                </a>
              </div>
            </div>
            <button class="modal-close" onclick="cerrarImportarCSV()" aria-label="Cerrar modal">✕</button>
          </div>

          <!-- Drop zone -->
          <div id="csv-dropzone" style="border:2px dashed #cbd5e1;border-radius:10px;padding:40px;text-align:center;cursor:pointer;transition:border-color .2s;margin-bottom:16px"
               onclick="document.getElementById('csv-file-input').click()"
               ondragover="event.preventDefault();this.style.borderColor='#3b82f6'"
               ondragleave="this.style.borderColor='#cbd5e1'"
               ondrop="event.preventDefault();this.style.borderColor='#cbd5e1';procesarCSV(event.dataTransfer.files[0])">
            <div style="font-size:2.5rem;margin-bottom:8px">📄</div>
            <div style="font-weight:600;color:#374151;margin-bottom:4px">Arrastra tu archivo CSV aquí</div>
            <div style="font-size:.8rem;color:#6b7a8d">o haz clic para seleccionar · Formatos: CSV, XLSX</div>
            <input id="csv-file-input" type="file" accept=".csv,.xlsx" style="display:none"
                   onchange="procesarCSV(this.files[0])">
          </div>

          <!-- Nombre del archivo seleccionado -->
          <div id="csv-file-name" style="font-size:.82rem;color:#6b7a8d;margin-bottom:12px;display:none"></div>

          <!-- Botón importar -->
          <button id="csv-import-btn" class="btn-secondary" style="width:100%;padding:10px;font-size:.9rem;display:none"
                  onclick="importarClientes()">Importar clientes</button>

          <!-- Spinner -->
          <div id="csv-loading" style="display:none;text-align:center;padding:16px;color:#6b7a8d;font-size:.85rem">
            ⏳ Procesando importación…
          </div>

          <!-- Resultados -->
          <div id="csv-resultados" style="display:none;margin-top:16px;padding:16px;background:#f8fafc;border-radius:10px;font-size:.84rem">
          </div>
        </div>
      </div>

      <!-- ══════════════════════════════════════════════════════
           MODAL: Escribir a cliente
           ══════════════════════════════════════════════════════ -->
      <div id="modal-escribir" class="modal-overlay" style="display:none" onclick="cerrarEscribir(event)">
        <div class="modal-box" style="max-width:500px" onclick="event.stopPropagation()">
          <div class="modal-hdr">
            <div>
              <div class="modal-title">✍ Escribir a cliente</div>
              <div class="modal-sub" id="escribir-sub">—</div>
            </div>
            <button class="modal-close" onclick="cerrarEscribir()" aria-label="Cerrar modal">✕</button>
          </div>

          <!-- Tabs -->
          <div style="display:flex;gap:0;border-bottom:1.5px solid #e5e7eb;margin-bottom:20px">
            <button id="tab-wa" class="escribir-tab active-tab" onclick="mostrarTabEscribir('wa')" style="flex:1;padding:9px;border:none;background:none;cursor:pointer;font-size:.84rem;font-weight:600;color:#2563eb;border-bottom:2px solid #2563eb">📱 WhatsApp Web</button>
            <button id="tab-tpl" class="escribir-tab" onclick="mostrarTabEscribir('tpl')" style="flex:1;padding:9px;border:none;background:none;cursor:pointer;font-size:.84rem;font-weight:600;color:#6b7a8d;border-bottom:2px solid transparent">📋 Plantilla API</button>
          </div>

          <!-- Tab: WhatsApp Web -->
          <div id="tab-wa-body">
            <label style="font-size:.8rem;color:#6b7a8d;display:block;margin-bottom:6px">Mensaje</label>
            <textarea id="wa-mensaje" rows="4" style="width:100%;border:1.5px solid #e5e7eb;border-radius:8px;padding:10px;font-size:.85rem;resize:vertical;box-sizing:border-box" placeholder="Escribe tu mensaje…"></textarea>
            <button onclick="enviarPorWhatsApp()" style="margin-top:12px;width:100%;padding:10px;background:#25d366;color:#fff;border:none;border-radius:8px;font-size:.9rem;font-weight:600;cursor:pointer">
              Abrir en WhatsApp →
            </button>
          </div>

          <!-- Tab: Plantilla API -->
          <div id="tab-tpl-body" style="display:none">
            <label style="font-size:.8rem;color:#6b7a8d;display:block;margin-bottom:6px">Plantilla aprobada</label>
            <select id="escribir-tpl-sel" style="width:100%;border:1.5px solid #e5e7eb;border-radius:8px;padding:8px;font-size:.84rem;margin-bottom:12px;box-sizing:border-box"
                    onchange="previewPlantilla()">
              <option value="">Cargando plantillas…</option>
            </select>
            <div id="escribir-tpl-preview" style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:12px;font-size:.83rem;color:#374151;margin-bottom:12px;min-height:48px;white-space:pre-wrap;display:none"></div>
            <div id="escribir-tpl-error" style="color:#dc2626;font-size:.8rem;display:none;margin-bottom:8px"></div>
            <button onclick="enviarPlantilla()" style="width:100%;padding:10px;background:var(--az,#2563eb);color:#fff;border:none;border-radius:8px;font-size:.9rem;font-weight:600;cursor:pointer">
              Enviar por API →
            </button>
            <div id="escribir-tpl-result" style="margin-top:10px;font-size:.82rem;display:none"></div>
          </div>
        </div>
      </div>

      <!-- ═══════════════════════════════════════
           SECCIÓN: ESCALACIONES (Sprint 1)
           ═══════════════════════════════════════ -->
      <div class="sec sec-light" id="sec-escalaciones">
        <div class="sec-hdr">
          <div><h1>🎯 Escalaciones</h1><p style="color:#64748b;font-size:.85rem;margin:0">Conversaciones que requieren atención humana</p></div>
        </div>

        <div style="display:flex;flex:1;overflow:hidden;min-height:0">
          <!-- ── Lista de tickets (izquierda) ─────────────────────────── -->
          <div id="esc-sidebar" style="width:340px;min-width:340px;display:flex;flex-direction:column;
               border-right:1px solid #e2e8f0;background:#f8fafc;overflow:hidden">

            <!-- Filtros -->
            <div style="display:flex;border-bottom:1px solid #e2e8f0;background:#fff">
              <button class="esc-tab active" data-est="sin_asignar" onclick="escFiltrar('sin_asignar',this)">Sin asignar<span class="esc-cnt" id="cnt-sin_asignar"></span></button>
              <button class="esc-tab" data-est="activo" onclick="escFiltrar('activo',this)">Activas<span class="esc-cnt" id="cnt-activo"></span></button>
              <button class="esc-tab" data-est="pendiente" onclick="escFiltrar('pendiente',this)">Pendientes<span class="esc-cnt" id="cnt-pendiente"></span></button>
              <button class="esc-tab" data-est="resuelto" onclick="escFiltrar('resuelto',this)">Resueltas</button>
            </div>

            <!-- Lista -->
            <div id="esc-lista" style="flex:1;overflow-y:auto;padding:8px"></div>
          </div>

          <!-- ── Detalle del ticket (derecha) ─────────────────────────── -->
          <div id="esc-detalle" style="flex:1;display:flex;flex-direction:column;background:#fff;overflow:hidden">

            <!-- Estado vacío -->
            <div id="esc-empty" style="flex:1;display:flex;align-items:center;justify-content:center;color:#94a3b8;flex-direction:column;gap:8px">
              <span style="font-size:2.5rem">🎯</span>
              <span>Selecciona un ticket para ver la conversación</span>
            </div>

            <!-- Detalle activo (oculto hasta seleccionar) -->
            <div id="esc-conv-wrap" style="display:none;flex-direction:column;flex:1;overflow:hidden">

              <!-- Header del ticket -->
              <div id="esc-ticket-hdr" style="padding:12px 16px;border-bottom:1px solid #e2e8f0;background:#f8fafc;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
                <button id="esc-back-btn" onclick="escVolverLista()" style="display:none;background:none;border:none;font-size:1.3rem;cursor:pointer;color:#4f46e5;padding:0 6px 0 0">←</button>
                <div style="flex:1">
                  <div id="esc-cliente-nombre" style="font-weight:700;font-size:.95rem;color:#1a2332"></div>
                  <div id="esc-cliente-tel" style="font-size:.78rem;color:#64748b"></div>
                </div>
                <span id="esc-urgencia-badge" style="font-size:.74rem;font-weight:700;padding:3px 10px;border-radius:12px"></span>
                <div style="display:flex;gap:6px">
                  <button id="btn-esc-tomar" class="btn-primary" style="font-size:.78rem;padding:5px 12px" onclick="escTomar()">✋ Tomar</button>
                  <button id="btn-esc-pendiente" class="btn-secondary" style="font-size:.78rem;padding:5px 12px;display:none" onclick="escPendiente()">⏸ Pendiente</button>
                  <button id="btn-esc-resolver" class="btn-primary" style="font-size:.78rem;padding:5px 12px;background:#16a34a;border-color:#16a34a;display:none" onclick="escResolver()">✅ Resolver</button>
                </div>
              </div>

              <!-- Motivo/contexto del ticket -->
              <div id="esc-motivo-wrap" style="padding:10px 16px;background:#fef3c7;border-bottom:1px solid #fde68a;font-size:.82rem;color:#92400e">
                <strong>Motivo:</strong> <span id="esc-motivo"></span> &nbsp;|&nbsp;
                <strong>Contexto:</strong> <span id="esc-contexto"></span>
              </div>

              <!-- Tabs: Conversación / Notas internas -->
              <div id="esc-det-tabs" style="display:none;border-bottom:1px solid #e2e8f0;background:#fff">
                <div style="display:flex">
                  <button class="det-tab active" id="det-tab-conv" onclick="escDetTab('conv',this)">💬 Conversación</button>
                  <button class="det-tab" id="det-tab-notas" onclick="escDetTab('notas',this)">📝 Notas <span id="notas-count" style="font-size:.68rem;color:#94a3b8"></span></button>
                  <button class="det-tab" id="det-tab-audit" onclick="escDetTab('audit',this)">🔍 Auditoría</button>
                </div>
              </div>

              <!-- Panel: Conversación -->
              <div id="esc-panel-conv" style="flex:1;display:flex;flex-direction:column;overflow:hidden;min-height:0">
                <div id="esc-msgs" style="flex:1;overflow-y:auto;padding:12px 16px;display:flex;flex-direction:column;gap:6px;min-height:0;background:#0b141a"></div>

                <!-- Input de respuesta (solo visible si ticket activo) -->
                <div id="esc-reply-wrap" style="padding:10px 14px;border-top:1px solid #e2e8f0;background:#fff;display:none">
                  <!-- Templates rápidos -->
                  <div style="position:relative">
                    <div id="tpl-picker" class="tpl-picker" style="display:none"></div>
                    <div style="display:flex;gap:6px;margin-bottom:6px">
                      <button class="btn-secondary" style="font-size:.74rem;padding:4px 10px" onclick="escToggleTemplates()" title="Respuestas rápidas">⚡ Templates</button>
                      <button id="btn-transferir" class="btn-secondary" style="font-size:.74rem;padding:4px 10px;display:none" onclick="escMostrarTransferir()">↗ Transferir</button>
                    </div>
                  </div>
                  <!-- Transferir (select oculto) -->
                  <div id="transferir-wrap" style="display:none;margin-bottom:6px;padding:8px;background:#f0f4ff;border-radius:8px">
                    <div style="font-size:.78rem;font-weight:600;color:#1a2332;margin-bottom:6px">Transferir a otro agente:</div>
                    <div style="display:flex;gap:6px">
                      <select id="transferir-select" style="flex:1;border:1px solid #dde1e8;border-radius:6px;padding:6px 8px;font-size:.82rem;outline:none">
                        <option value="">— Selecciona un agente —</option>
                      </select>
                      <button class="btn-primary" style="font-size:.78rem;padding:5px 12px" onclick="escConfirmarTransferir()">Transferir</button>
                      <button class="btn-secondary" style="font-size:.78rem;padding:5px 10px" onclick="document.getElementById('transferir-wrap').style.display='none'">✕</button>
                    </div>
                  </div>
                  <div style="display:flex;gap:8px">
                    <textarea id="esc-reply-input" placeholder="Escribe tu respuesta al cliente…"
                      style="flex:1;border:1px solid #dde1e8;border-radius:8px;padding:8px 10px;font-size:.85rem;
                      resize:none;height:60px;outline:none;font-family:inherit"
                      onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();escEnviarRespuesta();}"></textarea>
                    <button class="btn-primary" style="align-self:flex-end;padding:8px 14px" onclick="escEnviarRespuesta()">Enviar</button>
                  </div>
                  <div style="font-size:.72rem;color:#94a3b8;margin-top:4px">Enter para enviar · Shift+Enter nueva línea</div>
                </div>
              </div>

              <!-- Panel: Auditoría -->
              <div id="esc-panel-audit" style="display:none;flex-direction:column;flex:1;overflow:hidden;min-height:0;background:#f8fafc">
                <div id="esc-audit-list" style="flex:1;overflow-y:auto;padding:12px 16px;display:flex;flex-direction:column;gap:6px"></div>
              </div>

              <!-- Panel: Notas internas -->
              <div id="esc-panel-notas" style="display:none;flex-direction:column;flex:1;overflow:hidden;min-height:0">
                <div id="esc-notas-list" style="flex:1;overflow-y:auto;padding:12px 16px;display:flex;flex-direction:column;gap:8px;background:#fffbeb"></div>
                <div id="esc-nota-input-wrap" style="padding:10px 14px;border-top:1px solid #fde68a;background:#fff;display:none">
                  <div style="display:flex;gap:8px">
                    <textarea id="esc-nota-input" placeholder="Escribe una nota interna (solo el equipo la verá)…"
                      style="flex:1;border:1px solid #fde68a;border-radius:8px;padding:8px 10px;font-size:.83rem;
                      resize:none;height:56px;outline:none;font-family:inherit;background:#fffbeb"
                      onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();escGuardarNota();}"></textarea>
                    <button style="align-self:flex-end;padding:8px 12px;background:#eab308;border:none;border-radius:7px;color:#fff;font-weight:700;cursor:pointer;font-size:.84rem" onclick="escGuardarNota()">Guardar</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div><!-- /sec-escalaciones -->

      <!-- ═══════════════════════════════════════
           SECCIÓN: CONFIGURACIÓN
           ═══════════════════════════════════════ -->
      <div class="sec sec-light" id="sec-configuracion">
        <div class="sec-hdr">
          <div>
            <h1>⚙️ Configuración</h1>
            <p>Integraciones, estado del sistema y documentación</p>
          </div>
        </div>
        <div class="sec-body">

          <!-- Tabs -->
          <div class="cfg-tabs">
            <div class="cfg-tab active" onclick="cfgTab('integraciones',this)">⚙️ Integraciones</div>
            <div class="cfg-tab" onclick="cfgTab('prompt',this);cargarPrompt()">🧠 Prompt</div>
            <div class="cfg-tab" onclick="cfgTab('probar',this);iniciarChatTest()">🧪 Probar</div>
            <div class="cfg-tab" onclick="cfgTab('equipo',this);cargarEquipo()">👥 Equipo</div>
            <div class="cfg-tab" onclick="cfgTab('templates',this);cargarTemplatesRapidos()">⚡ Templates</div>
            <div class="cfg-tab" onclick="cfgTab('documentacion',this)">📋 Documentación</div>
          </div>

          <!-- ── Pane: Integraciones ── -->
          <div class="cfg-pane active" id="cfg-pane-integraciones">

            <!-- Overview: estado de las 3 integraciones -->
            <div class="cfg-overview" id="cfg-overview">
              <div class="cfg-ov-item">
                <span class="cfg-ov-icon">🔑</span>
                <div>
                  <div class="cfg-ov-name">Meta WhatsApp</div>
                  <div class="cfg-ov-status cfg-pill-pend" id="ov-meta-status">Verificando…</div>
                </div>
              </div>
              <div class="cfg-ov-item">
                <span class="cfg-ov-icon">🤖</span>
                <div>
                  <div class="cfg-ov-name">Anthropic IA</div>
                  <div class="cfg-ov-status cfg-pill-pend" id="ov-ai-status">Verificando…</div>
                </div>
              </div>
              <div class="cfg-ov-item">
                <span class="cfg-ov-icon">🛒</span>
                <div>
                  <div class="cfg-ov-name">Shopify</div>
                  <div class="cfg-ov-status cfg-pill-pend" id="ov-shopify-status">Verificando…</div>
                </div>
              </div>
            </div>

            <!-- ── Card: Meta ── -->
            <div class="cfg-card" id="card-meta">
              <div class="cfg-card-hdr">
                <div class="cfg-card-title">🔑 Meta WhatsApp Business API</div>
                <span class="cfg-status-pill cfg-pill-pending" id="pill-meta">Verificando…</span>
              </div>

              <div class="cfg-step">
                <div class="cfg-step-num">1</div>
                <div class="cfg-step-body">
                  <div class="cfg-field-lbl">
                    Token de acceso permanente
                    <button class="cfg-help-btn" onclick="toggleHelp('help-meta-token')" type="button" aria-label="Ayuda">?</button>
                    <span class="req">*</span>
                  </div>
                  <div class="cfg-help-box" id="help-meta-token">
                    <b>Cómo obtenerlo (paso a paso):</b><br>
                    1. Ve a <a href="https://developers.facebook.com" target="_blank">developers.facebook.com</a> e inicia sesión<br>
                    2. Abre tu app → menú izquierdo <b>WhatsApp → Configuración de la API</b><br>
                    3. En la sección <b>Token de acceso</b> haz clic en <b>Generar token</b><br>
                    4. Para producción, crea un <em>System User Token</em> permanente en Meta Business Suite → Configuración → Usuarios del sistema<br>
                    5. El token empieza con <code>EAAxxxxx…</code> — pégalo completo aquí<br>
                    <a href="#cfg-pane-documentacion" onclick="cfgTab('documentacion',document.querySelector('.cfg-tab:last-child'))">📋 Ver guía completa en Documentación →</a>
                  </div>
                  <div class="cfg-field-row">
                    <div class="cfg-input-wrap" style="flex:1">
                      <input type="password" id="cfg-meta-token" class="f-inp" placeholder="EAAxxxxx..." autocomplete="off">
                      <button class="cfg-eye-btn" onclick="togglePwd('cfg-meta-token',this)" type="button">👁</button>
                    </div>
                    <span class="cfg-field-status" id="st-META_ACCESS_TOKEN"></span>
                  </div>
                </div>
              </div>

              <div class="cfg-step">
                <div class="cfg-step-num">2</div>
                <div class="cfg-step-body">
                  <div class="cfg-field-lbl">
                    Phone Number ID
                    <button class="cfg-help-btn" onclick="toggleHelp('help-meta-pid')" type="button" aria-label="Ayuda">?</button>
                    <span class="req">*</span>
                  </div>
                  <div class="cfg-help-box" id="help-meta-pid">
                    <b>¿Qué es?</b> Es el identificador del número de WhatsApp Business, <em>no</em> el número de teléfono en sí.<br>
                    <b>Dónde está:</b> Meta for Developers → tu app → WhatsApp → Configuración de la API → sección <b>"Números de teléfono"</b> → columna <b>"ID del número de teléfono"</b><br>
                    Ejemplo: <code>123456789012345</code>
                  </div>
                  <div class="cfg-field-row">
                    <input type="text" id="cfg-meta-pid" class="f-inp" placeholder="123456789012345" autocomplete="off" style="flex:1">
                    <span class="cfg-field-status" id="st-META_PHONE_NUMBER_ID"></span>
                  </div>
                </div>
              </div>

              <div class="cfg-step">
                <div class="cfg-step-num">3</div>
                <div class="cfg-step-body">
                  <div class="cfg-field-lbl">
                    WhatsApp Business Account ID (WABA ID)
                    <button class="cfg-help-btn" onclick="toggleHelp('help-meta-waba')" type="button" aria-label="Ayuda">?</button>
                    <span class="req">*</span>
                  </div>
                  <div class="cfg-help-box" id="help-meta-waba">
                    <b>Dónde está:</b><br>
                    • Meta Business Suite → Configuración → <b>WhatsApp Business</b> → columna "ID de cuenta"<br>
                    • O en Meta for Developers → tu app → WhatsApp → Configuración → sección <b>"WhatsApp Business Account ID"</b><br>
                    Ejemplo: <code>987654321012345</code>
                  </div>
                  <div class="cfg-field-row">
                    <input type="text" id="cfg-meta-waba" class="f-inp" placeholder="987654321012345" autocomplete="off" style="flex:1">
                    <span class="cfg-field-status" id="st-META_WABA_ID"></span>
                  </div>
                </div>
              </div>

              <div class="cfg-step">
                <div class="cfg-step-num">4</div>
                <div class="cfg-step-body">
                  <div class="cfg-field-lbl">
                    Verify Token (para el webhook)
                    <button class="cfg-help-btn" onclick="toggleHelp('help-meta-verify')" type="button" aria-label="Ayuda">?</button>
                    <span class="opt-badge">Opcional</span>
                  </div>
                  <div class="cfg-help-box" id="help-meta-verify">
                    <b>¿Para qué sirve?</b> Es una contraseña que <em>tú inventas</em> para verificar que Meta es quien envía los webhooks a tu servidor.<br>
                    Cuando configures el webhook en la consola de Meta, pon exactamente el mismo texto aquí y en el campo <b>"Verify Token"</b> de Meta.<br>
                    Puede ser cualquier texto, sin espacios. Ejemplo: <code>equora-webhook-2025</code>
                  </div>
                  <div class="cfg-field-row">
                    <input type="text" id="cfg-meta-verify" class="f-inp" placeholder="equora-webhook-2025" autocomplete="off" style="flex:1">
                    <span class="cfg-field-status" id="st-META_VERIFY_TOKEN"></span>
                  </div>
                </div>
              </div>

              <div class="cfg-actions">
                <div id="cfg-meta-result" class="cfg-test-result" style="display:none"></div>
                <button class="btn-secondary" onclick="testConexion('meta')" type="button" id="btn-test-meta">
                  🔌 Probar conexión
                </button>
                <button class="btn-primary" onclick="guardarConfig('meta')" type="button" id="btn-save-meta">
                  💾 Guardar
                </button>
              </div>
            </div><!-- /card-meta -->

            <!-- ── Card: Anthropic ── -->
            <div class="cfg-card" id="card-anthropic">
              <div class="cfg-card-hdr">
                <div class="cfg-card-title">🤖 Anthropic — Motor de IA (Andrea)</div>
                <span class="cfg-status-pill cfg-pill-pending" id="pill-anthropic">Verificando…</span>
              </div>

              <div class="cfg-step">
                <div class="cfg-step-num">1</div>
                <div class="cfg-step-body">
                  <div class="cfg-field-lbl">
                    API Key de Anthropic
                    <button class="cfg-help-btn" onclick="toggleHelp('help-ant-key')" type="button" aria-label="Ayuda">?</button>
                    <span class="req">*</span>
                  </div>
                  <div class="cfg-help-box" id="help-ant-key">
                    <b>Cómo obtenerla:</b><br>
                    1. Ve a <a href="https://console.anthropic.com" target="_blank">console.anthropic.com</a> y crea una cuenta<br>
                    2. Menú → <b>Settings → API Keys → Create Key</b><br>
                    3. Dale un nombre (ej: "Equora") y cópiala <b>inmediatamente</b><br>
                    4. Empieza con <code>sk-ant-api03-…</code><br>
                    <b>⚠️ Solo se muestra una vez</b> — guárdala en un lugar seguro antes de cerrar
                  </div>
                  <div class="cfg-field-row">
                    <div class="cfg-input-wrap" style="flex:1">
                      <input type="password" id="cfg-ant-key" class="f-inp" placeholder="sk-ant-api03-..." autocomplete="off">
                      <button class="cfg-eye-btn" onclick="togglePwd('cfg-ant-key',this)" type="button">👁</button>
                    </div>
                    <span class="cfg-field-status" id="st-ANTHROPIC_API_KEY"></span>
                  </div>
                </div>
              </div>

              <div class="cfg-step">
                <div class="cfg-step-num">2</div>
                <div class="cfg-step-body">
                  <div class="cfg-field-lbl">Modelo de IA
                    <button class="cfg-help-btn" onclick="toggleHelp('help-ant-model')" type="button" aria-label="Ayuda">?</button>
                  </div>
                  <div class="cfg-help-box" id="help-ant-model">
                    <b>Haiku</b> — El más rápido y económico. Ideal para respuestas de WhatsApp. <b>Recomendado para producción.</b><br>
                    <b>Sonnet</b> — Más inteligente, pero más lento y costoso. Útil para conversaciones más complejas.<br>
                    <b>Opus</b> — El más potente, mayor costo. Para casos de uso muy avanzados.
                  </div>
                  <select id="cfg-ant-model" class="f-sel" style="max-width:360px">
                    <option value="claude-haiku-4-5">claude-haiku-4-5 — Rápido · Económico ⭐ Recomendado</option>
                    <option value="claude-sonnet-4-5">claude-sonnet-4-5 — Balanceado</option>
                    <option value="claude-opus-4-5">claude-opus-4-5 — Más inteligente · Mayor costo</option>
                  </select>
                  <span class="f-hint">El modelo Haiku es el óptimo para WhatsApp — respuestas en &lt;2 segundos al costo más bajo.</span>
                </div>
              </div>

              <div class="cfg-actions">
                <div id="cfg-anthropic-result" class="cfg-test-result" style="display:none"></div>
                <button class="btn-secondary" onclick="testConexion('anthropic')" type="button">🔌 Probar conexión</button>
                <button class="btn-primary" onclick="guardarConfig('anthropic')" type="button">💾 Guardar</button>
              </div>
            </div><!-- /card-anthropic -->

            <!-- ── Card: Shopify ── -->
            <div class="cfg-card" id="card-shopify">
              <div class="cfg-card-hdr">
                <div class="cfg-card-title">🛒 Shopify — Tienda en línea</div>
                <span class="cfg-status-pill cfg-pill-pending" id="pill-shopify">Verificando…</span>
              </div>

              <div class="cfg-step">
                <div class="cfg-step-num">1</div>
                <div class="cfg-step-body">
                  <div class="cfg-field-lbl">
                    Dominio de la tienda
                    <button class="cfg-help-btn" onclick="toggleHelp('help-sh-domain')" type="button" aria-label="Ayuda">?</button>
                    <span class="req">*</span>
                  </div>
                  <div class="cfg-help-box" id="help-sh-domain">
                    El subdominio interno de tu tienda Shopify, siempre termina en <code>.myshopify.com</code><br>
                    <b>Dónde encontrarlo:</b> Shopify Admin → <b>Configuración → Dominios</b> → busca el dominio que dice <em>"mitienda.myshopify.com"</em><br>
                    ⚠️ <b>No uses</b> el dominio personalizado (ej: <code>equoradistribuciones.com</code>) — usa el <code>.myshopify.com</code><br>
                    <b>No incluyas</b> <code>https://</code> al inicio ni <code>/</code> al final.<br>
                    Ejemplo: <code>equora-6.myshopify.com</code>
                  </div>
                  <div class="cfg-field-row">
                    <input type="text" id="cfg-sh-domain" class="f-inp" placeholder="mitienda.myshopify.com" autocomplete="off" style="flex:1">
                    <span class="cfg-field-status" id="st-SHOPIFY_STORE"></span>
                  </div>
                </div>
              </div>

              <div class="cfg-step">
                <div class="cfg-step-num">2</div>
                <div class="cfg-step-body">
                  <div class="cfg-field-lbl">
                    Token de Storefront API
                    <button class="cfg-help-btn" onclick="toggleHelp('help-sh-sftoken')" type="button" aria-label="Ayuda">?</button>
                    <span class="req">*</span>
                  </div>
                  <div class="cfg-help-box" id="help-sh-sftoken">
                    Andrea usa la <b>Storefront API</b> para leer el catálogo y crear checkouts.<br>
                    Para obtener el token debes tener instalada la app <b>Headless</b> en tu tienda:<br><br>
                    1. Shopify Admin → <b>Apps</b> → busca <b>"Headless"</b> e instálala<br>
                    2. Abre la app Headless → <b>"Add Storefront"</b> (o selecciona el existente)<br>
                    3. Verás dos tokens en la sección <b>"Storefront API"</b>:<br>
                    &nbsp;&nbsp;• <b>Token de acceso público</b> — cadena de <b>32 caracteres hex</b> sin prefijo → <em>usa este</em><br>
                    &nbsp;&nbsp;• Token de acceso privado — empieza con <code>shpat_…</code> (también funciona)<br>
                    4. Copia el <b>Token de acceso público</b> y pégalo aquí<br>
                    <small style="color:#6b7a8d">Ejemplo: <code>d6fe89xxxxxxxxxxxxxxxxxxxxxx</code> (32 chars) &nbsp;·&nbsp; <a href="https://shopify.dev/docs/api/usage/authentication#access-tokens-for-the-storefront-api" target="_blank">Documentación oficial →</a></small>
                  </div>
                  <div class="cfg-field-row">
                    <div class="cfg-input-wrap" style="flex:1">
                      <input type="password" id="cfg-sh-sftoken" class="f-inp" placeholder="Token público hex de 32 chars (o shpat_...)" autocomplete="off">
                      <button class="cfg-eye-btn" onclick="togglePwd('cfg-sh-sftoken',this)" type="button">👁</button>
                    </div>
                    <span class="cfg-field-status" id="st-SHOPIFY_STOREFRONT_TOKEN"></span>
                  </div>
                </div>
              </div>

              <div class="cfg-step">
                <div class="cfg-step-num">3</div>
                <div class="cfg-step-body">
                  <div class="cfg-field-lbl">
                    Webhook Secret
                    <button class="cfg-help-btn" onclick="toggleHelp('help-sh-whsec')" type="button" aria-label="Ayuda">?</button>
                    <span class="opt-badge">Opcional</span>
                  </div>
                  <div class="cfg-help-box" id="help-sh-whsec">
                    Permite verificar que las notificaciones de nuevas órdenes llegan <b>realmente de Shopify</b> y no de terceros.<br>
                    <b>Dónde está:</b> Shopify Admin → <b>Configuración → Notificaciones → Webhooks</b> → sección <b>"Clave secreta del webhook"</b>.<br>
                    Si no lo configuras, el sistema acepta todas las notificaciones de órdenes sin verificar su origen.
                  </div>
                  <div class="cfg-field-row">
                    <div class="cfg-input-wrap" style="flex:1">
                      <input type="password" id="cfg-sh-whsec" class="f-inp" placeholder="shpss_..." autocomplete="off">
                      <button class="cfg-eye-btn" onclick="togglePwd('cfg-sh-whsec',this)" type="button">👁</button>
                    </div>
                    <span class="cfg-field-status" id="st-SHOPIFY_WEBHOOK_SECRET"></span>
                  </div>
                </div>
              </div>

              <div class="cfg-actions">
                <div id="cfg-shopify-result" class="cfg-test-result" style="display:none"></div>
                <button class="btn-secondary" onclick="testConexion('shopify')" type="button">🔌 Probar conexión</button>
                <button class="btn-primary" onclick="guardarConfig('shopify')" type="button">💾 Guardar</button>
              </div>
            </div><!-- /card-shopify -->

            <!-- ══════════════════════════════════════════════════════════
                 REGLAS DEL NEGOCIO (Sprint 4 — multi-tenant)
                 ══════════════════════════════════════════════════════════ -->
            <div class="cfg-card" id="card-reglas">
              <div class="cfg-card-hdr">
                <div class="cfg-card-ic">📦</div>
                <div class="cfg-card-info">
                  <div class="cfg-card-title">Reglas de pedido</div>
                  <div class="cfg-card-sub">Pedido mínimo, mensaje al cliente cuando no lo alcanza</div>
                </div>
                <span class="cfg-pill" id="pill-reglas">⚙️ Opcional</span>
              </div>

              <div class="cfg-step">
                <div class="cfg-step-num">1</div>
                <div class="cfg-step-body">
                  <div class="cfg-field-lbl">
                    Pedido mínimo (COP)
                    <button class="cfg-help-btn" onclick="toggleHelp('help-pedido-min')" type="button" aria-label="Ayuda">?</button>
                    <span class="opt-badge">Opcional</span>
                  </div>
                  <div class="cfg-help-box" id="help-pedido-min">
                    Monto mínimo en pesos para que un cliente pueda confirmar un pedido.<br>
                    <b>0 o vacío</b> = sin mínimo (cualquier pedido es válido).<br>
                    Si el pedido del cliente está por debajo, el bot le responderá amablemente con cuánto le falta y le mostrará el catálogo para agregar más productos.<br>
                    También puedes usar <code>{PEDIDO_MINIMO}</code> en el prompt del agente para que mencione el mínimo de forma dinámica.
                  </div>
                  <div class="cfg-field-row">
                    <input type="number" id="cfg-pedido-min" class="f-inp" placeholder="ej: 50000" min="0" step="1000" style="flex:1">
                    <span class="cfg-field-status" id="st-PEDIDO_MINIMO"></span>
                  </div>
                </div>
              </div>

              <div class="cfg-step">
                <div class="cfg-step-num">2</div>
                <div class="cfg-step-body">
                  <div class="cfg-field-lbl">
                    Mensaje cuando el pedido no alcanza el mínimo
                    <button class="cfg-help-btn" onclick="toggleHelp('help-pedido-msg')" type="button" aria-label="Ayuda">?</button>
                    <span class="opt-badge">Opcional</span>
                  </div>
                  <div class="cfg-help-box" id="help-pedido-msg">
                    Texto que el bot envía al cliente cuando su pedido está por debajo del mínimo.<br>
                    Variables disponibles: <code>{ITEMS}</code> (lista del pedido actual), <code>{SUBTOTAL}</code>, <code>{MINIMO}</code>, <code>{FALTA}</code>.<br>
                    Si dejas vacío, se usa un mensaje genérico por defecto.
                  </div>
                  <textarea id="cfg-pedido-msg" class="f-inp" style="height:100px;resize:vertical;font-family:inherit"
                    placeholder='Ej: ¡Tu pedido va muy bien! {ITEMS}&#10;💰 Subtotal: ${SUBTOTAL}&#10;📦 Mínimo: ${MINIMO}&#10;Te faltan ${FALTA} para confirmar.'></textarea>
                  <span class="cfg-field-status" id="st-PEDIDO_MIN_MSG" style="display:block;margin-top:6px"></span>
                </div>
              </div>

              <div class="cfg-actions">
                <div id="cfg-reglas-result" class="cfg-test-result" style="display:none"></div>
                <button class="btn-primary" onclick="guardarConfig('reglas')" type="button">💾 Guardar</button>
              </div>
            </div><!-- /card-reglas -->

            <!-- ══════════════════════════════════════════════════════════
                 ESTADO DEL SISTEMA — Diagnóstico de tokens en tiempo real
                 ══════════════════════════════════════════════════════════ -->
            <div class="cfg-card" id="card-sistema">
              <div class="cfg-card-hdr">
                <div class="cfg-card-ic">🔍</div>
                <div class="cfg-card-info">
                  <div class="cfg-card-title">Estado del sistema</div>
                  <div class="cfg-card-sub">Diagnóstico en tiempo real de tokens y servicios</div>
                </div>
                <button class="btn-secondary" style="font-size:.78rem;padding:6px 12px" onclick="cargarEstadoSistema()" type="button">↺ Verificar</button>
              </div>

              <!-- Grid de estados -->
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px" id="cfg-sistema-grid">
                <!-- WhatsApp Cloud API -->
                <div class="sistema-item" id="sistema-whatsapp">
                  <div class="sistema-hdr">
                    <span class="sistema-dot" id="dot-whatsapp"></span>
                    <span class="sistema-name">📱 WhatsApp Cloud API</span>
                  </div>
                  <div class="sistema-msg" id="msg-whatsapp">Verificando…</div>
                  <div class="sistema-detalle" id="det-whatsapp"></div>
                </div>

                <!-- Conversions API (CAPI) -->
                <div class="sistema-item" id="sistema-capi">
                  <div class="sistema-hdr">
                    <span class="sistema-dot" id="dot-capi"></span>
                    <span class="sistema-name">📊 Conversions API (Pixel)</span>
                  </div>
                  <div class="sistema-msg" id="msg-capi">Verificando…</div>
                  <div class="sistema-detalle" id="det-capi"></div>
                </div>

                <!-- Catálogo de WhatsApp -->
                <div class="sistema-item" id="sistema-catalogo">
                  <div class="sistema-hdr">
                    <span class="sistema-dot" id="dot-catalogo"></span>
                    <span class="sistema-name">🛒 Catálogo WhatsApp</span>
                  </div>
                  <div class="sistema-msg" id="msg-catalogo">Verificando…</div>
                  <div class="sistema-detalle" id="det-catalogo"></div>
                </div>

                <!-- Shopify -->
                <div class="sistema-item" id="sistema-shopify">
                  <div class="sistema-hdr">
                    <span class="sistema-dot" id="dot-shopify"></span>
                    <span class="sistema-name">🏪 Shopify</span>
                  </div>
                  <div class="sistema-msg" id="msg-shopify">Verificando…</div>
                  <div class="sistema-detalle" id="det-shopify"></div>
                </div>
              </div>
            </div><!-- /card-sistema -->

            <!-- Próximas integraciones -->
            <div class="cfg-card" style="border-style:dashed;background:#fafbfc">
              <div class="cfg-card-title" style="color:#6b7a8d;margin-bottom:12px">🚀 Próximas integraciones</div>
              <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;font-size:.83rem;color:#6b7a8d">
                <div>🛒 <b style="color:#4a5568">Shopify OAuth</b><br><span style="font-size:.76rem">Conectar con un clic cuando Andrea sea app de Shopify</span></div>
                <div>📧 Email (SendGrid / Resend)</div>
                <div>📅 Calendly / Google Calendar</div>
                <div>🗃️ CRM (HubSpot / Pipedrive)</div>
                <div>💳 Pagos (Stripe / PSE)</div>
              </div>
            </div>

          </div><!-- /pane integraciones -->

          <!-- ── Pane: Prompt ── -->
          <div class="cfg-pane" id="cfg-pane-prompt">

            <!-- Intro -->
            <div style="background:#eef2ff;border:1px solid #c7d2fe;border-radius:10px;padding:14px 18px;margin-bottom:24px;font-size:.85rem;color:#3730a3;line-height:1.6">
              🧠 <b>Editor de prompt</b> — Define quién es tu agente, qué sabe y cómo habla.
              Usa <code style="background:#e0e7ff;padding:1px 5px;border-radius:4px">{VARIABLES}</code> en el texto y defínelas abajo.
              El asistente de IA te ayuda a mejorar las instrucciones en lenguaje natural.
            </div>

            <!-- ── Sección 0A: Tipo de negocio ── -->
            <div class="cfg-card" style="margin-bottom:16px">
              <div class="cfg-card-hdr" style="margin-bottom:4px">
                <div class="cfg-card-title">🏪 Tipo de negocio</div>
                <span style="font-size:.78rem;color:#6b7a8d">Optimiza las funciones del agente para tu modelo de negocio</span>
              </div>
              <div class="biz-type-grid" id="biz-type-grid">
                <div class="biz-type-btn" data-type="productos" onclick="selBizType(this)">
                  <div class="biz-type-icon">🛍️</div>
                  <div>Productos físicos</div>
                </div>
                <div class="biz-type-btn" data-type="servicios" onclick="selBizType(this)">
                  <div class="biz-type-icon">🔧</div>
                  <div>Servicios</div>
                </div>
                <div class="biz-type-btn" data-type="restaurante" onclick="selBizType(this)">
                  <div class="biz-type-icon">🍽️</div>
                  <div>Restaurante / Food</div>
                </div>
                <div class="biz-type-btn" data-type="salud" onclick="selBizType(this)">
                  <div class="biz-type-icon">💊</div>
                  <div>Salud / Belleza</div>
                </div>
                <div class="biz-type-btn" data-type="personalizado" onclick="selBizType(this)">
                  <div class="biz-type-icon">⚙️</div>
                  <div>Personalizado</div>
                </div>
              </div>
            </div>

            <!-- ── Sección 0B: Módulos activos ── -->
            <div class="cfg-card" style="margin-bottom:20px">
              <div class="cfg-card-hdr" style="margin-bottom:4px">
                <div class="cfg-card-title">🔌 Módulos del agente</div>
                <span style="font-size:.78rem;color:#6b7a8d">Activa o desactiva funciones según tu caso de uso</span>
              </div>
              <div class="toggle-grid">
                <div class="toggle-card" id="togcard-shopify_catalog">
                  <label class="tog-sw">
                    <input type="checkbox" id="tog-shopify_catalog" checked onchange="onTogModule('shopify_catalog',this)">
                    <span class="tog-slider"></span>
                  </label>
                  <div class="toggle-card-text">
                    <div class="toggle-card-label">🛒 Catálogo Shopify</div>
                    <div class="toggle-card-desc">Inyecta el catálogo de productos en el contexto del agente</div>
                  </div>
                </div>
                <div class="toggle-card" id="togcard-cart_orders">
                  <label class="tog-sw">
                    <input type="checkbox" id="tog-cart_orders" checked onchange="onTogModule('cart_orders',this)">
                    <span class="tog-slider"></span>
                  </label>
                  <div class="toggle-card-text">
                    <div class="toggle-card-label">🛍️ Carrito y pedidos</div>
                    <div class="toggle-card-desc">Muestra carrito activo y pedidos pendientes del cliente</div>
                  </div>
                </div>
                <div class="toggle-card" id="togcard-client_memory">
                  <label class="tog-sw">
                    <input type="checkbox" id="tog-client_memory" checked onchange="onTogModule('client_memory',this)">
                    <span class="tog-slider"></span>
                  </label>
                  <div class="toggle-card-text">
                    <div class="toggle-card-label">🧠 Memoria de clientes</div>
                    <div class="toggle-card-desc">Recuerda datos y pedidos previos de cada cliente</div>
                  </div>
                </div>
                <div class="toggle-card" id="togcard-campaign_context">
                  <label class="tog-sw">
                    <input type="checkbox" id="tog-campaign_context" checked onchange="onTogModule('campaign_context',this)">
                    <span class="tog-slider"></span>
                  </label>
                  <div class="toggle-card-text">
                    <div class="toggle-card-label">📣 Contexto de campaña</div>
                    <div class="toggle-card-desc">Sabe a qué difusión responde el cliente sin preguntarle</div>
                  </div>
                </div>
              </div>
            </div>

            <!-- ── Sección 1: Variables del negocio ── -->
            <div class="cfg-card" style="margin-bottom:20px">
              <div class="cfg-card-hdr" style="margin-bottom:16px">
                <div class="cfg-card-title">📋 Variables del negocio</div>
                <span style="font-size:.78rem;color:#6b7a8d">Úsalas en el prompt como <code>{NOMBRE_NEGOCIO}</code>, <code>{HORARIO}</code>…</span>
              </div>

              <table class="vars-table" id="vars-table">
                <thead>
                  <tr>
                    <th style="width:200px">Variable</th>
                    <th>Valor</th>
                    <th style="width:36px"></th>
                  </tr>
                </thead>
                <tbody id="vars-tbody">
                  <!-- filas generadas por JS -->
                </tbody>
              </table>
              <button class="btn-secondary" style="margin-top:12px;font-size:.8rem;padding:6px 14px" onclick="agregarVar()" type="button">+ Agregar variable</button>
              <p style="font-size:.76rem;color:#8a94a6;margin-top:10px">
                💡 Variables de sistema (no editables aquí): <code>{COSTO_ENVIO}</code> <code>{ENVIO_GRATIS}</code> — vienen de la configuración de Shopify
              </p>
            </div>

            <!-- ── Sección 2: Editor + Asistente ── -->
            <div class="prompt-editor-wrap">

              <!-- Editor izquierdo -->
              <div class="prompt-left">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
                  <div style="font-weight:700;color:#1a2332;font-size:.9rem">✍️ Prompt actual</div>
                  <span id="prompt-fuente" style="font-size:.73rem;color:#8a94a6"></span>
                </div>
                <textarea id="prompt-textarea" class="prompt-ta" placeholder="Escribe aquí las instrucciones de tu agente…" spellcheck="false"></textarea>
                <div style="display:flex;justify-content:space-between;align-items:center;margin-top:6px">
                  <span id="prompt-chars" style="font-size:.74rem;color:#8a94a6">0 caracteres</span>
                  <button class="btn-primary" onclick="guardarPrompt()" type="button" id="btn-save-prompt">💾 Guardar</button>
                </div>
              </div>

              <!-- Panel IA derecho -->
              <div class="prompt-right">
                <div style="font-weight:700;color:#1a2332;font-size:.9rem;margin-bottom:10px">✨ Asistente de mejora</div>

                <label style="font-size:.8rem;font-weight:600;color:#4a5568;display:block;margin-bottom:6px">
                  ¿Qué quieres mejorar o agregar?
                </label>
                <textarea id="prompt-instruccion" class="prompt-instruccion-ta" placeholder="Ej: &quot;Quiero que sea más empática cuando el cliente menciona un problema&quot;&#10;Ej: &quot;Agrega que el envío gratis aplica desde $80.000&quot;&#10;Ej: &quot;Haz que responda más corto y directo&quot;"></textarea>

                <!-- Zona de imágenes adjuntas -->
                <div class="img-attach-zone" id="img-attach-zone">
                  <div class="img-thumbs" id="img-thumbs"></div>
                  <div class="img-attach-bar">
                    <button type="button" class="btn-attach" onclick="document.getElementById('img-file-input').click()">
                      📎 Adjuntar imagen
                    </button>
                    <span class="img-paste-hint">o pega con Ctrl+V / arrastra aquí</span>
                  </div>
                  <input type="file" id="img-file-input" accept="image/*" multiple style="display:none">
                </div>

                <button class="btn-improve" onclick="mejorarPrompt()" type="button" id="btn-improve">
                  ✨ Mejorar con IA
                </button>

                <!-- Propuesta -->
                <div id="prompt-propuesta-wrap" style="display:none;margin-top:16px">
                  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
                    <span style="font-size:.82rem;font-weight:700;color:#1a2332">Propuesta de Claude</span>
                    <button class="btn-secondary" style="font-size:.76rem;padding:4px 10px" onclick="verDiff()" type="button" id="btn-diff">👁 Ver cambios</button>
                  </div>
                  <textarea id="prompt-propuesta" class="prompt-ta" style="height:220px;background:#f8fafc;border-color:#c7d2fe" readonly></textarea>
                  <div style="display:flex;gap:8px;margin-top:8px">
                    <button class="btn-secondary" style="flex:1" onclick="descartarPropuesta()" type="button">✕ Descartar</button>
                    <button class="btn-primary" style="flex:1" onclick="aplicarPropuesta()" type="button">✅ Aplicar al editor</button>
                  </div>
                </div>

                <!-- Diff -->
                <div id="prompt-diff-wrap" style="display:none;margin-top:16px">
                  <div style="font-size:.82rem;font-weight:700;color:#1a2332;margin-bottom:8px">Cambios detectados</div>
                  <div id="prompt-diff-content" class="prompt-diff"></div>
                  <button class="btn-secondary" style="margin-top:8px;font-size:.78rem" onclick="cerrarDiff()" type="button">← Volver</button>
                </div>

                <!-- Resultado de guardado -->
                <div id="prompt-save-result" class="cfg-test-result" style="display:none;margin-top:12px"></div>
              </div>
            </div>

          </div><!-- /pane prompt -->

          <!-- ── Pane: Probar (Fase C) ── -->
          <div class="cfg-pane" id="cfg-pane-probar">

            <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:14px 18px;margin-bottom:20px;font-size:.85rem;color:#166534;line-height:1.6">
              🧪 <b>Chat de prueba</b> — Habla con el agente usando las instrucciones del prompt actual.
              No envía mensajes reales por WhatsApp. El historial de prueba es independiente de las conversaciones reales.
            </div>

            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
              <div style="font-size:.85rem;color:#4a5568">
                Escribe un mensaje como si fueras un cliente para probar cómo responde el agente.
              </div>
              <button class="btn-secondary" style="font-size:.78rem;padding:6px 14px;white-space:nowrap" onclick="limpiarChatTest()" type="button">🗑 Limpiar chat</button>
            </div>

            <!-- Ventana de chat estilo WhatsApp -->
            <div class="chat-wrap">
              <div class="chat-messages" id="chat-messages">
                <div style="text-align:center;font-size:.76rem;color:#8a94a6;padding:8px 0">
                  Inicio de la conversación de prueba
                </div>
              </div>
              <div class="chat-input-bar">
                <textarea class="chat-inp" id="chat-inp" rows="1"
                  placeholder="Escribe tu mensaje…"
                  onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();enviarMsgTest()}"
                  oninput="this.style.height='auto';this.style.height=Math.min(this.scrollHeight,100)+'px'"></textarea>
                <button class="chat-send-btn" id="chat-send-btn" onclick="enviarMsgTest()" title="Enviar">
                  ➤
                </button>
              </div>
            </div>

            <div id="chat-test-error" style="display:none;margin-top:10px"></div>

          </div><!-- /pane probar -->

          <!-- ── Pane: Equipo (Sprint 1) ── -->
          <div class="cfg-pane" id="cfg-pane-equipo" style="padding:24px;overflow-y:auto">

            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">
              <div>
                <h2 style="margin:0;font-size:1.1rem;color:#1a2332">👥 Equipo de Soporte</h2>
                <p style="margin:4px 0 0;font-size:.83rem;color:#64748b">Agentes humanos que atienden escalaciones dentro del panel</p>
              </div>
              <button class="btn-primary" style="font-size:.82rem;padding:7px 14px" onclick="mostrarFormNuevoAgente()">
                + Nuevo agente
              </button>
            </div>

            <!-- Formulario nuevo agente (oculto por defecto) -->
            <div id="equipo-form-wrap" style="display:none;background:#f0f4ff;border:1px solid #c7d2fe;
                 border-radius:10px;padding:18px;margin-bottom:20px">
              <h3 style="margin:0 0 14px;font-size:.9rem;color:#1a2332">Nuevo agente</h3>
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
                <div>
                  <label style="font-size:.78rem;font-weight:600;color:#4a5568;display:block;margin-bottom:4px">Nombre completo</label>
                  <input id="eq-nombre" type="text" placeholder="Felipe García"
                    style="width:100%;border:1px solid #dde1e8;border-radius:7px;padding:8px 10px;font-size:.84rem;box-sizing:border-box;outline:none">
                </div>
                <div>
                  <label style="font-size:.78rem;font-weight:600;color:#4a5568;display:block;margin-bottom:4px">Email</label>
                  <input id="eq-email" type="email" placeholder="felipe@empresa.com"
                    style="width:100%;border:1px solid #dde1e8;border-radius:7px;padding:8px 10px;font-size:.84rem;box-sizing:border-box;outline:none">
                </div>
                <div>
                  <label style="font-size:.78rem;font-weight:600;color:#4a5568;display:block;margin-bottom:4px">Contraseña temporal</label>
                  <input id="eq-password" type="password" placeholder="Min. 6 caracteres"
                    style="width:100%;border:1px solid #dde1e8;border-radius:7px;padding:8px 10px;font-size:.84rem;box-sizing:border-box;outline:none">
                </div>
                <div>
                  <label style="font-size:.78rem;font-weight:600;color:#4a5568;display:block;margin-bottom:4px">Rol</label>
                  <select id="eq-rol" style="width:100%;border:1px solid #dde1e8;border-radius:7px;padding:8px 10px;font-size:.84rem;box-sizing:border-box;outline:none;background:#fff">
                    <option value="agente">Agente</option>
                    <option value="supervisor">Supervisor</option>
                    <option value="admin">Admin</option>
                  </select>
                </div>
              </div>
              <div style="display:flex;gap:8px;margin-top:14px">
                <button class="btn-primary" style="font-size:.82rem;padding:7px 16px" onclick="crearAgenteEquipo()">Crear agente</button>
                <button class="btn-secondary" style="font-size:.82rem;padding:7px 14px" onclick="document.getElementById('equipo-form-wrap').style.display='none'">Cancelar</button>
              </div>
              <div id="equipo-form-msg" style="margin-top:10px;font-size:.82rem"></div>
            </div>

            <!-- Tabla de agentes -->
            <div id="equipo-tabla-wrap">
              <div id="equipo-tabla" style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden">
                <div style="padding:14px 16px;color:#94a3b8;font-size:.85rem;text-align:center">Cargando equipo…</div>
              </div>
            </div>

            <!-- Info de plan -->
            <div id="equipo-plan-info" style="margin-top:14px;font-size:.78rem;color:#64748b;text-align:center"></div>
          </div><!-- /pane equipo -->

          <!-- ── Pane: Templates Rápidos (Sprint 2) ── -->
          <div class="cfg-pane" id="cfg-pane-templates" style="padding:24px;overflow-y:auto">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">
              <div>
                <h2 style="margin:0;font-size:1.1rem;color:#1a2332">⚡ Templates Rápidos</h2>
                <p style="margin:4px 0 0;font-size:.83rem;color:#64748b">Respuestas predefinidas para que tus agentes respondan más rápido</p>
              </div>
              <button class="btn-primary" style="font-size:.82rem;padding:7px 14px" onclick="mostrarFormTemplate()">+ Nuevo template</button>
            </div>

            <!-- Formulario nuevo template -->
            <div id="tpl-form-wrap" style="display:none;background:#f0f4ff;border:1px solid #c7d2fe;border-radius:10px;padding:18px;margin-bottom:20px">
              <h3 style="margin:0 0 12px;font-size:.9rem;color:#1a2332">Nuevo template</h3>
              <div style="margin-bottom:10px">
                <label style="font-size:.78rem;font-weight:600;color:#4a5568;display:block;margin-bottom:4px">Título (ej: Saludo inicial)</label>
                <input id="tpl-titulo" type="text" placeholder="Saludo inicial"
                  style="width:100%;border:1px solid #dde1e8;border-radius:7px;padding:8px 10px;font-size:.84rem;box-sizing:border-box;outline:none">
              </div>
              <div style="margin-bottom:10px">
                <label style="font-size:.78rem;font-weight:600;color:#4a5568;display:block;margin-bottom:4px">Mensaje</label>
                <textarea id="tpl-contenido" placeholder="Hola! Gracias por comunicarte con nosotros. Mi nombre es [nombre] y estoy aquí para ayudarte."
                  style="width:100%;border:1px solid #dde1e8;border-radius:7px;padding:8px 10px;font-size:.84rem;
                  box-sizing:border-box;outline:none;height:80px;resize:vertical;font-family:inherit"></textarea>
              </div>
              <div style="display:flex;gap:8px">
                <button class="btn-primary" style="font-size:.82rem;padding:7px 16px" onclick="guardarTemplateRapido()">Guardar</button>
                <button class="btn-secondary" style="font-size:.82rem;padding:7px 14px" onclick="document.getElementById('tpl-form-wrap').style.display='none'">Cancelar</button>
              </div>
              <div id="tpl-form-msg" style="margin-top:8px;font-size:.82rem"></div>
            </div>

            <!-- Lista de templates -->
            <div id="tpl-lista" style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden">
              <div style="padding:14px;color:#94a3b8;font-size:.85rem;text-align:center">Cargando templates…</div>
            </div>
          </div><!-- /pane templates -->

          <!-- ── Pane: Documentación ── -->
          <div class="cfg-pane" id="cfg-pane-documentacion">

            <!-- Métricas y fórmulas -->
            <div class="doc-section">
              <p class="doc-section-title">📊 Métricas y fórmulas de cálculo</p>
              <div class="doc-grid">

                <div class="doc-card">
                  <div class="doc-card-title">💵 Costo Meta</div>
                  <div class="doc-formula">Costo = Enviados × USD $0.0165 × TRM</div>
                  <p style="font-size:.82rem;color:#4a5568;line-height:1.6;margin:0">
                    Meta cobra <strong>por conversación de 24 horas iniciada</strong>, no por mensaje individual ni por entrega o lectura.
                    La tarifa <b>$0.0165 USD</b> aplica a conversaciones de marketing en Colombia (vigente 2024–2025).
                    El valor en COP depende de la TRM del día.
                  </p>
                </div>

                <div class="doc-card">
                  <div class="doc-card-title">📈 ROAS (Retorno sobre inversión)</div>
                  <div class="doc-formula">ROAS = Ventas atribuidas COP / Costo Meta COP</div>
                  <p style="font-size:.82rem;color:#4a5568;line-height:1.6;margin:0">
                    ROAS &gt; 1 = la campaña es rentable. Ejemplo: ROAS 3.5 significa que por cada $1 invertido en Meta, se generaron $3.50 en ventas.
                    Un ROAS &lt; 1 indica que el costo supera las ventas atribuidas en la ventana de 7 días.
                  </p>
                </div>

                <div class="doc-card">
                  <div class="doc-card-title">📦 Tasa de entrega</div>
                  <div class="doc-formula">Entrega % = Entregados / Enviados × 100</div>
                  <p style="font-size:.82rem;color:#4a5568;line-height:1.6;margin:0">
                    Requiere <strong>tracking activo</strong> via webhook de Meta (campo <code>statuses</code>).
                    Un mensaje no entregado puede deberse a: número inválido, WhatsApp desinstalado, teléfono apagado &gt;30 días, o bloqueo del usuario.
                  </p>
                </div>

                <div class="doc-card">
                  <div class="doc-card-title">👁 Tasa de lectura</div>
                  <div class="doc-formula">Lectura % = Leídos / Entregados × 100</div>
                  <p style="font-size:.82rem;color:#4a5568;line-height:1.6;margin:0">
                    Solo se registra si el destinatario tiene activados los <strong>recibos de lectura</strong> en WhatsApp.
                    Una tasa de lectura baja puede indicar que el horario de envío o el asunto de la plantilla no es atractivo.
                  </p>
                </div>

                <div class="doc-card">
                  <div class="doc-card-title">🛒 Ventas atribuidas</div>
                  <div class="doc-formula">Ventana de atribución: 7 días post-envío</div>
                  <p style="font-size:.82rem;color:#4a5568;line-height:1.6;margin:0">
                    Se cruzan las órdenes de Shopify con el número de teléfono de cada destinatario.
                    Si el cliente recibió la difusión y realizó una compra en los <strong>7 días siguientes</strong>, la venta se atribuye a esa campaña.
                    Atribución por <em>último toque</em>.
                  </p>
                </div>

                <div class="doc-card">
                  <div class="doc-card-title">🤖 Conversaciones IA</div>
                  <div class="doc-formula">Interacciones = Mensajes recibidos + Respuestas IA</div>
                  <p style="font-size:.82rem;color:#4a5568;line-height:1.6;margin:0">
                    Cada mensaje de un cliente genera una respuesta de Andrea (Claude Haiku 4.5).
                    El costo de la IA depende de los tokens usados (incluido el catálogo de Shopify y el perfil del cliente en el contexto).
                    No tiene costo adicional de Meta — Andrea solo responde dentro de la ventana de 24h abierta por el cliente.
                  </p>
                </div>

              </div>
            </div>

            <!-- Tarifas Meta -->
            <div class="doc-section">
              <p class="doc-section-title">💰 Tarifas Meta — Colombia (2025)</p>
              <div class="doc-card" style="max-width:600px">
                <table class="doc-table">
                  <thead>
                    <tr>
                      <th>Tipo de conversación</th>
                      <th>Tarifa USD</th>
                      <th>Aprox. COP</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>📣 Marketing <span class="doc-chip doc-chip-orange">difusiones</span></td>
                      <td><strong>$0.0165</strong></td>
                      <td>~$67 COP</td>
                    </tr>
                    <tr>
                      <td>🛎️ Utilidad <span class="doc-chip doc-chip-blue">transaccional</span></td>
                      <td><strong>$0.0042</strong></td>
                      <td>~$17 COP</td>
                    </tr>
                    <tr>
                      <td>🔐 Autenticación <span class="doc-chip doc-chip-green">OTP</span></td>
                      <td><strong>$0.0190</strong></td>
                      <td>~$77 COP</td>
                    </tr>
                    <tr>
                      <td>💬 Servicio (cliente inicia)</td>
                      <td><strong>Gratis</strong></td>
                      <td>$0</td>
                    </tr>
                  </tbody>
                </table>
                <p style="font-size:.76rem;color:#8a94a6;margin-top:10px;line-height:1.5">
                  TRM referencia: ~$4.100 COP/USD. Las tarifas pueden cambiar — consultar siempre la
                  <a href="https://developers.facebook.com/docs/whatsapp/pricing" target="_blank" style="color:var(--az)">tabla oficial de Meta</a>.
                  Conversación de 24h: un solo cargo sin importar cuántos mensajes se envíen en esa ventana.
                </p>
              </div>
            </div>

            <!-- Difusiones y límites -->
            <div class="doc-section">
              <p class="doc-section-title">📤 Difusiones — límites y buenas prácticas</p>
              <div class="doc-grid">

                <div class="doc-card">
                  <div class="doc-card-title">⚡ Límites de envío</div>
                  <table class="doc-table">
                    <tr><td>Nivel 1 (nuevo número)</td><td><strong>1.000/día</strong></td></tr>
                    <tr><td>Nivel 2</td><td><strong>10.000/día</strong></td></tr>
                    <tr><td>Nivel 3</td><td><strong>100.000/día</strong></td></tr>
                    <tr><td>Ilimitado</td><td><strong>Sin límite</strong></td></tr>
                  </table>
                  <p style="font-size:.78rem;color:#6b7a8d;margin-top:8px">
                    El nivel sube automáticamente cuando la tasa de mensajes enviados vs. bloqueados es buena.
                    Una calidad <em>alta</em> o <em>media</em> del número es necesaria para subir de nivel.
                  </p>
                </div>

                <div class="doc-card">
                  <div class="doc-card-title">🛡️ Anti-spam y opt-out</div>
                  <p style="font-size:.82rem;color:#4a5568;line-height:1.6;margin:0 0 8px">
                    Si un cliente responde palabras de baja (<b>STOP, BAJA, NO MÁS, CANCELAR…</b>), Andrea lo marca automáticamente y queda excluido de futuras difusiones.
                  </p>
                  <p style="font-size:.82rem;color:#4a5568;line-height:1.6;margin:0">
                    Meta penaliza números con alta tasa de bloqueos. Mantener calidad alta:
                  </p>
                  <ul style="font-size:.82rem;color:#4a5568;line-height:1.8;margin:6px 0 0 16px;padding:0">
                    <li>Incluir botón "Dar de baja" en cada plantilla</li>
                    <li>Enviar solo a contactos que dieron consentimiento</li>
                    <li>Espaciar difusiones (no todos los días al mismo segmento)</li>
                    <li>Personalizar el contenido con variables {{nombre}}</li>
                  </ul>
                </div>

              </div>
            </div>

            <!-- Sistema técnico -->
            <div class="doc-section">
              <p class="doc-section-title">🔧 Sistema técnico</p>
              <div class="doc-grid">

                <div class="doc-card">
                  <div class="doc-card-title">🔗 Webhook Meta</div>
                  <p style="font-size:.82rem;color:#4a5568;line-height:1.6;margin:0 0 8px">
                    Meta envía todos los eventos (mensajes, entregas, lecturas, estados) a:
                  </p>
                  <div class="doc-formula">POST /webhook</div>
                  <p style="font-size:.82rem;color:#4a5568;line-height:1.6;margin:8px 0 0">
                    La verificación inicial usa un GET con <code>hub.verify_token</code>.
                    Si el webhook deja de responder, Meta auto-deshabilita la suscripción — el endpoint debe estar siempre activo.
                  </p>
                </div>

                <div class="doc-card">
                  <div class="doc-card-title">🤖 Modelo de IA — Andrea</div>
                  <table class="doc-table">
                    <tr><td>Modelo</td><td><strong>Claude Haiku 4.5</strong></td></tr>
                    <tr><td>Tokens máx. respuesta</td><td>1.024</td></tr>
                    <tr><td>Contexto inyectado</td><td>System prompt + catálogo Shopify + perfil cliente + carrito activo + últimos 20 mensajes</td></tr>
                    <tr><td>Opt-out automático</td><td>STOP, BAJA, CANCELAR, DARME DE BAJA…</td></tr>
                  </table>
                </div>

                <div class="doc-card">
                  <div class="doc-card-title">🛒 Integración Shopify</div>
                  <p style="font-size:.82rem;color:#4a5568;line-height:1.6;margin:0">
                    El catálogo de productos se carga via <strong>Shopify Admin API</strong> y se cachea en memoria (actualización cada 5 min).
                    El perfil del cliente y el historial de pedidos se obtienen por número de teléfono.
                    Los checkouts se crean via la API de Shopify — el cliente recibe un link directo para completar el pago.
                  </p>
                </div>

                <div class="doc-card">
                  <div class="doc-card-title">🗄️ Base de datos</div>
                  <table class="doc-table">
                    <tr><td>Motor local</td><td>SQLite + aiosqlite</td></tr>
                    <tr><td>Motor producción</td><td>PostgreSQL (Railway)</td></tr>
                    <tr><td>Tablas principales</td><td>mensajes, clientes, estado_conversaciones, opt_outs, difusiones, difusion_destinatarios</td></tr>
                    <tr><td>Historial por cliente</td><td>Últimos 20 mensajes (configurable)</td></tr>
                  </table>
                </div>

              </div>
            </div>

          </div><!-- /pane documentacion -->

        </div>
      </div><!-- /sec-configuracion -->

    </div><!-- /main -->
  </div><!-- /body -->
</div><!-- /shell -->

<!-- ══════════════════════════════════════════════════════
     Modal de detalle de campaña de difusión
     ══════════════════════════════════════════════════════ -->
<div id="dif-detail-modal" class="modal-overlay" style="display:none" onclick="cerrarDetalleCampana(event)">
  <div class="modal-box" onclick="event.stopPropagation()">
    <div class="modal-hdr">
      <div>
        <div class="modal-title" id="dif-det-titulo">Detalle de campaña</div>
        <div class="modal-sub"  id="dif-det-sub"></div>
      </div>
      <button class="modal-close" onclick="cerrarDetalleCampana()" title="Cerrar">✕</button>
    </div>

    <!-- Cards resumen -->
    <div class="det-cards" id="dif-det-cards">
      <div class="det-card" style="background:#e8f5e9">
        <div class="det-card-val" style="color:#2e7d32" id="dc-total">—</div>
        <div class="det-card-lbl">Rastreados</div>
      </div>
      <div class="det-card" style="background:#e3f2fd">
        <div class="det-card-val" style="color:#1565c0" id="dc-entregados">—</div>
        <div class="det-card-lbl">Entregados</div>
      </div>
      <div class="det-card" style="background:#e8eaf6">
        <div class="det-card-val" style="color:#283593" id="dc-leidos">—</div>
        <div class="det-card-lbl">Leídos</div>
      </div>
      <div class="det-card" style="background:#fce4ec">
        <div class="det-card-val" style="color:#b71c1c" id="dc-fallidos">—</div>
        <div class="det-card-lbl">Fallidos</div>
      </div>
    </div>

    <!-- Funnel de entrega -->
    <div class="funnel-section" id="dif-det-funnel"></div>

    <!-- Tabla de errores agrupados -->
    <div class="det-err-section" id="dif-det-errores" style="display:none">
      <h4>⚠️ Mensajes no entregados — motivo del error</h4>
      <table class="det-errtbl">
        <thead>
          <tr>
            <th>Motivo</th>
            <th style="width:60px;text-align:center">Cant.</th>
            <th>Números afectados</th>
          </tr>
        </thead>
        <tbody id="dif-det-errbody"></tbody>
      </table>
    </div>

    <!-- Pendientes aún sin confirmar -->
    <div id="dif-det-pendientes" style="display:none;margin-top:16px;padding:12px 16px;
      background:#fffbeb;border:1px solid #fde68a;border-radius:10px;font-size:.82rem;color:#92400e">
      ⏳ <b id="dif-det-pend-cnt">0</b> mensajes aún no confirman entrega
      (el destinatario puede tener el teléfono apagado o sin conexión).
    </div>

    <div style="text-align:right;margin-top:24px">
      <button class="btn-secondary" onclick="cerrarDetalleCampana()" style="padding:8px 20px;font-size:.83rem">
        Cerrar
      </button>
    </div>
  </div>
</div>

<script>
/* ══════════════════════════════════════════════════════
   NAVEGACIÓN DE SECCIONES
   ══════════════════════════════════════════════════════ */
var _secActual = 'conversaciones';
var _secCargadas = {};

function showSec(id) {
  if (_secActual === id) return;
  document.querySelectorAll('.sec').forEach(function(s) { s.classList.remove('active'); });
  document.querySelectorAll('.nav-item').forEach(function(n) { n.classList.remove('active'); });
  var sec = document.getElementById('sec-' + id);
  if (sec) sec.classList.add('active');
  var ni = document.querySelector('.nav-item[data-sec="' + id + '"]');
  if (ni) ni.classList.add('active');
  _secActual = id;
  // Cargar datos de la sección si es la primera vez
  if (!_secCargadas[id]) {
    _secCargadas[id] = true;
    if (id === 'difusiones')    { cargarTemplates(); cargarHistorialDif(); }
    if (id === 'plantillas')    { cargarTablaPlantillas(); actualizarSubcat(); setTimeout(_hookPreview, 200); }
    if (id === 'metricas')      { cargarMetricas(); }
    if (id === 'clientes')      { cargarClientes(); }
    if (id === 'configuracion') { cargarConfiguracion(); cargarEstadoSistema(); }
    if (id === 'escalaciones')  { escCargarLista(); }
  }
  // Reflejar sección en el hash de la URL para deep-linking
  try { history.replaceState(null, '', '#' + id); } catch(e) {}
}

/* ══════════════════════════════════════════════════════
   UTILS
   ══════════════════════════════════════════════════════ */
var _dtfHoy  = new Intl.DateTimeFormat('es-CO', {hour:'2-digit', minute:'2-digit', hour12:true});
var _dtfAnio = new Intl.DateTimeFormat('es-CO', {day:'2-digit', month:'short'});

function fmt(ts) {
  if (!ts) return '';
  var d = new Date(ts.endsWith('Z') ? ts : ts + 'Z');
  var now = new Date();
  var diff = (now - d) / 1000;
  if (diff < 60)    return 'ahora';
  if (diff < 3600)  return Math.floor(diff / 60) + ' min';
  if (diff < 86400) return _dtfHoy.format(d);
  return _dtfAnio.format(d);
}
function fmtH(ts) {
  if (!ts) return '';
  var d = new Date(ts.endsWith('Z') ? ts : ts + 'Z');
  return _dtfHoy.format(d);
}
function fmtFecha(ts) {
  if (!ts) return '';
  var d = new Date(ts.endsWith('Z') ? ts : ts + 'Z');
  return d.toLocaleDateString('es-CO', {day:'2-digit', month:'2-digit', year:'2-digit'}) +
         ' ' + d.toLocaleTimeString('es-CO', {hour:'2-digit', minute:'2-digit'});
}
function he(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function api(path, opts) {
  return fetch(path, Object.assign({credentials: 'same-origin'}, opts || {}))
    .then(function(r) {
      if (r.status === 401) { location.href = '/inbox/login'; throw new Error('No autorizado'); }
      return r.json();
    });
}

/* ══════════════════════════════════════════════════════
   CONVERSACIONES
   ══════════════════════════════════════════════════════ */
var TEL = '';
var CONVS = [];
var Q = '';
var _convTimer = null;
var _msgTimer = null;

function loadConvs() {
  api('/inbox/api/conversaciones').then(function(data) {
    CONVS = Array.isArray(data) ? data : [];
    document.getElementById('total').textContent = CONVS.length;
    var badge = document.getElementById('conv-badge');
    badge.textContent = CONVS.length;
    badge.style.display = CONVS.length ? 'inline' : 'none';
    renderLista();
    if (TEL) {
      var c = CONVS.find(function(x) { return x.telefono === TEL; });
      if (c) setHeader(c);
    }
  }).catch(function() {});
}

function filtrar() {
  Q = document.getElementById('srinput').value.trim().toLowerCase();
  renderLista();
}

function renderLista() {
  var lista = Q ? CONVS.filter(function(c) {
    return c.telefono.includes(Q) ||
           (c.nombre || '').toLowerCase().includes(Q) ||
           (c.ultimo_mensaje || '').toLowerCase().includes(Q);
  }) : CONVS;

  if (!lista.length) {
    document.getElementById('cl').innerHTML =
      '<p style="text-align:center;padding:40px;color:#8696a0;font-size:.84rem">Sin conversaciones</p>';
    return;
  }
  var h = '';
  for (var i = 0; i < lista.length; i++) {
    var c = lista[i];
    var nm = (c.nombre && c.nombre !== c.telefono) ? c.nombre : ('+' + c.telefono);
    var icono = c.ultimo_role === 'user' ? '👤 ' : '🤖 ';
    var preview = he((c.ultimo_mensaje || '').substring(0, 60));
    var sel = c.telefono === TEL ? ' sel' : '';
    var badge    = c.modo_humano ? '<span class="hmbadge">HUMANO</span>' : '';
    var optBadge = c.opt_out    ? '<span class="optbadge">🚫 Baja</span>' : '';
    h += '<div class="ci' + sel + '" role="button" tabindex="0" data-tel="' + he(c.telefono) + '"'
       + ' aria-label="Conversación con ' + he(nm) + '" onkeydown="if(event.key===\'Enter\'||event.key===\' \')abrirConv(this.dataset.tel)">'
       + '<div class="av" aria-hidden="true">👤</div>'
       + '<div class="inf">'
       + '<div class="nm">' + he(nm) + '</div>'
       + '<div class="lm">' + icono + preview + '</div>'
       + '</div>'
       + '<div class="meta2"><span class="cts">' + fmt(c.timestamp) + '</span>' + optBadge + badge + '</div>'
       + '</div>';
  }
  document.getElementById('cl').innerHTML = h;
}

document.getElementById('cl').addEventListener('click', function(e) {
  var ci = e.target.closest('.ci');
  if (ci) abrirConv(ci.dataset.tel);
});

function abrirConv(tel) {
  TEL = tel;
  document.getElementById('sidebar').classList.add('oculto');
  document.getElementById('chat-area').classList.remove('oculto');
  document.getElementById('empty').style.display = 'none';
  document.getElementById('cv').style.display = 'flex';
  renderLista();
  loadMsgs(true);
  clearInterval(_msgTimer);
  _msgTimer = setInterval(function() { loadMsgs(false); }, 5000);
}

function volverLista() {
  TEL = '';
  clearInterval(_msgTimer);
  document.getElementById('sidebar').classList.remove('oculto');
  document.getElementById('chat-area').classList.add('oculto');
  document.getElementById('cv').style.display = 'none';
  document.getElementById('empty').style.display = 'flex';
}

function loadMsgs(scroll) {
  api('/inbox/api/mensajes/' + encodeURIComponent(TEL)).then(function(data) {
    renderMsgs(data.mensajes || [], scroll);
    var mh = data.modo_humano || false;
    document.getElementById('togInput').checked = mh;
    document.getElementById('mlbl').style.display = mh ? 'inline' : 'none';
    var c = CONVS.find(function(x) { return x.telefono === TEL; });
    if (c) setHeader(c);
  }).catch(function() {});
}

function setHeader(c) {
  var nm = (c.nombre && c.nombre !== c.telefono) ? c.nombre : ('+' + c.telefono);
  document.getElementById('cnm').textContent = nm;
  document.getElementById('cst').textContent = '+' + c.telefono;
}

function renderMsgs(msgs, scroll) {
  if (!msgs.length) {
    document.getElementById('msgs').innerHTML = '<div class="msys">Sin mensajes aún</div>';
    return;
  }
  var h = '';
  var lastDate = '';
  for (var i = 0; i < msgs.length; i++) {
    var m = msgs[i];
    var dia = m.timestamp ? m.timestamp.substring(0, 10) : '';
    if (dia && dia !== lastDate) {
      var ds = new Date(dia + 'T12:00:00Z');
      var dLabel = ds.toLocaleDateString('es-CO', {weekday:'long', day:'numeric', month:'long'});
      h += '<div class="msys">' + he(dLabel) + '</div>';
      lastDate = dia;
    }
    var cls = m.role === 'user' ? 'usr' : 'bot';
    var bodyHtml = renderMediaOrText(m.content);
    h += '<div class="msg ' + cls + '">'
       + '<div class="mb">' + bodyHtml + '</div>'
       + '<div class="mt">' + fmtH(m.timestamp) + '</div>'
       + '</div>';
  }
  var box = document.getElementById('msgs');
  var nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
  box.innerHTML = h;
  if (scroll || nearBottom) box.scrollTop = box.scrollHeight;
}

function toggleModo() {
  var activo = document.getElementById('togInput').checked;
  document.getElementById('mlbl').style.display = activo ? 'inline' : 'none';
  api('/inbox/api/modo/' + encodeURIComponent(TEL), {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({activo: activo})
  }).then(function() { loadConvs(); }).catch(function() {});
}

function sendMsg() {
  if (!TEL) return;
  var ti = document.getElementById('ti');
  var msg = ti.value.trim();
  if (!msg) return;
  var btn = document.getElementById('sendbtn');
  btn.disabled = true;
  api('/inbox/api/responder', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({telefono: TEL, mensaje: msg})
  }).then(function(d) {
    if (d.ok) {
      ti.value = '';
      ti.style.height = 'auto';
      loadMsgs(true);
      loadConvs();
    } else {
      alert('Error al enviar: ' + (d.error || 'intenta de nuevo'));
    }
    btn.disabled = false;
  }).catch(function() { btn.disabled = false; });
}

function onKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMsg(); }
}

function autoResize() {
  var ti = document.getElementById('ti');
  ti.style.height = 'auto';
  ti.style.height = Math.min(ti.scrollHeight, 120) + 'px';
}

/* ══════════════════════════════════════════════════════
   CLIENTES
   ══════════════════════════════════════════════════════ */
var _CLI_DATA   = [];   // todos los clientes cargados
var _CLI_ESTADO = 'todos'; // filtro activo

function cargarClientes() {
  document.getElementById('cli-tbody').innerHTML =
    '<tr><td colspan="8" class="loading-txt">Cargando…</td></tr>';
  api('/inbox/api/clientes').then(function(data) {
    _CLI_DATA = data.clientes || [];
    var r = data.resumen || {};
    document.getElementById('ec-total').textContent  = (r.total  || 0).toLocaleString('es-CO');
    document.getElementById('ec-activo').textContent = (r.activo || 0).toLocaleString('es-CO');
    document.getElementById('ec-tibio').textContent  = (r.tibio  || 0).toLocaleString('es-CO');
    document.getElementById('ec-frio').textContent   = (r.frio   || 0).toLocaleString('es-CO');
    document.getElementById('ec-baja').textContent   = (r.baja   || 0).toLocaleString('es-CO');
    renderClientes();
  }).catch(function() {
    document.getElementById('cli-tbody').innerHTML =
      '<tr><td colspan="8" class="loading-txt">Error al cargar clientes</td></tr>';
  });
}

function filtrarClientes(estado) {
  _CLI_ESTADO = estado;
  // Actualizar pills
  document.querySelectorAll('.cli-pill').forEach(function(p) {
    p.classList.toggle('active', p.dataset.est === estado);
  });
  // Highlight card seleccionada
  document.querySelectorAll('.estado-card').forEach(function(c) {
    c.classList.remove('sel-estado');
  });
  renderClientes();
}

function renderClientes() {
  var q = (document.getElementById('cli-q').value || '').trim().toLowerCase();
  var lista = _CLI_DATA.filter(function(c) {
    var estadoOk = _CLI_ESTADO === 'todos' || c.estado === _CLI_ESTADO;
    var busqOk   = !q ||
      c.telefono.includes(q) ||
      (c.nombre  || '').toLowerCase().includes(q) ||
      (c.ciudad  || '').toLowerCase().includes(q);
    return estadoOk && busqOk;
  });

  document.getElementById('cli-count').textContent = lista.length.toLocaleString('es-CO');

  if (!lista.length) {
    document.getElementById('cli-tbody').innerHTML =
      '<tr><td colspan="8">' +
      '<div class="cli-empty">' +
      '<div class="cli-empty-ic">👥</div>' +
      '<div class="cli-empty-txt">No hay clientes en este segmento</div>' +
      '</div></td></tr>';
    return;
  }

  var cfg = {
    activo: {lbl:'Activo',   cls:'est-activo', avcls:'cli-av-activo'},
    tibio:  {lbl:'Tibio',    cls:'est-tibio',  avcls:'cli-av-tibio'},
    frio:   {lbl:'Frío',     cls:'est-frio',   avcls:'cli-av-frio'},
    baja:   {lbl:'Baja',     cls:'est-baja',   avcls:'cli-av-baja'},
  };

  var h = '';
  for (var i = 0; i < lista.length; i++) {
    var c  = lista[i];
    var cf = cfg[c.estado] || cfg.frio;
    var nm = c.nombre || '';
    var ini = nm ? nm.charAt(0).toUpperCase() : c.telefono.slice(-2);
    var disp = nm || ('+' + c.telefono);
    var tel  = '+' + c.telefono;
    var lastRel = c.last_msg ? fmtRelativo(c.last_msg) : '—';
    h += '<tr>'
       + '<td><div class="cli-av ' + cf.avcls + '" aria-hidden="true">' + he(ini) + '</div></td>'
       + '<td><div style="font-weight:600;font-size:.86rem;color:#1a2332">' + he(disp) + '</div>'
       +     '<div style="font-size:.74rem;color:#6b7a8d">' + he(tel) + '</div></td>'
       + '<td style="color:#4a5568;font-size:.83rem">' + he(c.ciudad || '—') + '</td>'
       + '<td style="font-size:.82rem;color:#4a5568">' + he(lastRel) + '</td>'
       + '<td><span class="est-pill ' + cf.cls + '">' + cf.lbl + '</span></td>'
       + '<td style="text-align:center;font-weight:700;color:#2d3748">' + (c.pedidos || 0) + '</td>'
       + '<td style="text-align:center;color:#6b7a8d">' + (c.total_msgs || 0) + '</td>'
       + '<td style="display:flex;gap:6px">'
       + '<button class="cli-act-btn" onclick="verChatCliente(\'' + he(c.telefono) + '\')"'
       +    ' aria-label="Ver chat de ' + he(disp) + '">Ver chat</button>'
       + '<button class="cli-act-btn cli-write-btn" onclick="abrirEscribir(\'' + he(c.telefono) + '\',\'' + he(nm).replace(/'/g,"&#39;") + '\')"'
       +    ' aria-label="Escribir a ' + he(disp) + '" data-tel="' + he(c.telefono) + '" data-nombre="' + he(nm) + '">✍ Escribir</button>'
       + '</td>'
       + '</tr>';
  }
  document.getElementById('cli-tbody').innerHTML = h;
}

function fmtRelativo(ts) {
  if (!ts) return '—';
  try {
    var d   = new Date(ts.endsWith('Z') ? ts : ts + 'Z');
    var seg = Math.floor((Date.now() - d.getTime()) / 1000);
    if (seg < 60)    return 'Hace un momento';
    if (seg < 3600)  return 'Hace ' + Math.floor(seg / 60) + ' min';
    if (seg < 86400) return 'Hoy';
    var dias = Math.floor(seg / 86400);
    if (dias === 1)  return 'Ayer';
    if (dias < 30)   return 'Hace ' + dias + ' días';
    if (dias < 90)   return 'Hace ' + Math.floor(dias / 30) + ' mes' + (dias >= 60 ? 'es' : '');
    return 'Hace ' + Math.floor(dias / 30) + ' meses';
  } catch(e) { return '—'; }
}

function verChatCliente(tel) {
  showSec('conversaciones');
  setTimeout(function() { abrirConv(tel); }, 100);
}

/* ══════════════════════════════════════════════════════
   IMPORTAR CSV DE CLIENTES
   ══════════════════════════════════════════════════════ */
var _csvFile = null;

function abrirImportarCSV() {
  _csvFile = null;
  document.getElementById('csv-file-name').style.display = 'none';
  document.getElementById('csv-import-btn').style.display = 'none';
  document.getElementById('csv-loading').style.display = 'none';
  document.getElementById('csv-resultados').style.display = 'none';
  document.getElementById('csv-file-input').value = '';
  document.getElementById('modal-importar-csv').style.display = 'flex';
}

function cerrarImportarCSV(e) {
  if (e && e.target !== document.getElementById('modal-importar-csv')) return;
  document.getElementById('modal-importar-csv').style.display = 'none';
  _csvFile = null;
}

function procesarCSV(file) {
  if (!file) return;
  _csvFile = file;
  var nameEl = document.getElementById('csv-file-name');
  nameEl.textContent = '📄 ' + file.name + ' (' + (file.size / 1024).toFixed(1) + ' KB)';
  nameEl.style.display = 'block';
  document.getElementById('csv-import-btn').style.display = 'block';
  document.getElementById('csv-resultados').style.display = 'none';
}

async function importarClientes() {
  if (!_csvFile) return;
  document.getElementById('csv-import-btn').style.display = 'none';
  document.getElementById('csv-loading').style.display = 'block';
  document.getElementById('csv-resultados').style.display = 'none';
  try {
    var fd = new FormData();
    fd.append('file', _csvFile);
    var r = await fetch('/inbox/api/clientes/import', {method:'POST', body:fd, credentials:'include'});
    var d = await r.json();
    document.getElementById('csv-loading').style.display = 'none';
    var res = document.getElementById('csv-resultados');
    res.style.display = 'block';
    if (d.ok) {
      var html = '<div style="font-weight:700;font-size:.9rem;color:#1a2332;margin-bottom:10px">Resultado de la importación</div>';
      html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">';
      html += '<div style="background:#f0fdf4;border-radius:8px;padding:10px;text-align:center"><div style="font-size:1.3rem;font-weight:800;color:#15803d">' + (d.inserted || 0) + '</div><div style="font-size:.75rem;color:#15803d">✅ Insertados</div></div>';
      html += '<div style="background:#eff6ff;border-radius:8px;padding:10px;text-align:center"><div style="font-size:1.3rem;font-weight:800;color:#1d4ed8">' + (d.updated || 0) + '</div><div style="font-size:.75rem;color:#1d4ed8">🔄 Actualizados</div></div>';
      html += '</div>';
      if (d.errors > 0) {
        html += '<div style="margin-top:10px;padding:8px 10px;background:#fef2f2;border-radius:8px;color:#991b1b">❌ ' + d.errors + ' error(es)';
        if (d.error_rows && d.error_rows.length) {
          html += '<ul style="margin:6px 0 0 16px;font-size:.78rem">';
          d.error_rows.slice(0, 5).forEach(function(er) {
            html += '<li>Fila ' + er.fila + ': ' + he(er.razon) + '</li>';
          });
          html += '</ul>';
        }
        html += '</div>';
      }
      html += '<div style="margin-top:10px;font-size:.78rem;color:#6b7a8d">Total filas procesadas: ' + (d.total || 0) + '</div>';
      res.innerHTML = html;
      cargarClientes(); // refrescar tabla
    } else {
      res.innerHTML = '<div style="color:#dc2626;font-size:.85rem">Error: ' + he(d.detail || d.error || 'Error desconocido') + '</div>';
    }
  } catch(err) {
    document.getElementById('csv-loading').style.display = 'none';
    var res = document.getElementById('csv-resultados');
    res.style.display = 'block';
    res.innerHTML = '<div style="color:#dc2626;font-size:.85rem">Error de red: ' + he(String(err)) + '</div>';
  }
  document.getElementById('csv-import-btn').style.display = 'block';
}


/* ══════════════════════════════════════════════════════
   ESCRIBIR A CLIENTE
   ══════════════════════════════════════════════════════ */
var _escribirTel = '';
var _escribirNombre = '';
var _escribirTemplates = null;  // null = no cargado aún

function abrirEscribir(telefono, nombre) {
  _escribirTel    = telefono;
  _escribirNombre = nombre || '';
  document.getElementById('escribir-sub').textContent = (nombre ? nombre + ' · ' : '') + '+' + telefono;
  // Precargar mensaje WhatsApp con saludo
  var saludo = nombre ? ('Hola ' + nombre + '! 👋') : 'Hola! 👋';
  document.getElementById('wa-mensaje').value = saludo;
  // Reset estado tab
  mostrarTabEscribir('wa');
  document.getElementById('escribir-tpl-result').style.display = 'none';
  document.getElementById('escribir-tpl-error').style.display = 'none';
  document.getElementById('modal-escribir').style.display = 'flex';
  // Cargar plantillas en background
  if (_escribirTemplates === null) cargarTemplatesEscribir();
}

function cerrarEscribir(e) {
  if (e && e.target !== document.getElementById('modal-escribir')) return;
  document.getElementById('modal-escribir').style.display = 'none';
}

function mostrarTabEscribir(tab) {
  document.getElementById('tab-wa-body').style.display  = tab === 'wa'  ? 'block' : 'none';
  document.getElementById('tab-tpl-body').style.display = tab === 'tpl' ? 'block' : 'none';
  ['wa','tpl'].forEach(function(t) {
    var btn = document.getElementById('tab-' + t);
    if (t === tab) {
      btn.style.color       = '#2563eb';
      btn.style.borderBottom = '2px solid #2563eb';
    } else {
      btn.style.color       = '#6b7a8d';
      btn.style.borderBottom = '2px solid transparent';
    }
  });
}

function enviarPorWhatsApp() {
  var msg = document.getElementById('wa-mensaje').value.trim();
  var tel = _escribirTel;
  var url = 'https://wa.me/' + tel + '?text=' + encodeURIComponent(msg);
  window.open(url, '_blank');
}

async function cargarTemplatesEscribir() {
  var sel = document.getElementById('escribir-tpl-sel');
  sel.innerHTML = '<option value="">Cargando plantillas…</option>';
  try {
    var r = await fetch('/inbox/api/clientes/templates', {credentials:'include'});
    var d = await r.json();
    if (d.error || !d.templates || !d.templates.length) {
      sel.innerHTML = '<option value="">' + he(d.error || 'No hay plantillas aprobadas') + '</option>';
      _escribirTemplates = [];
      return;
    }
    _escribirTemplates = d.templates;
    sel.innerHTML = '<option value="">Selecciona una plantilla…</option>';
    d.templates.forEach(function(t) {
      var opt = document.createElement('option');
      opt.value = t.name + '|' + t.language;
      opt.textContent = t.name + ' (' + t.language + ')';
      sel.appendChild(opt);
    });
  } catch(err) {
    sel.innerHTML = '<option value="">Error cargando plantillas</option>';
    _escribirTemplates = [];
  }
}

function previewPlantilla() {
  var sel = document.getElementById('escribir-tpl-sel');
  var val = sel.value;
  var prev = document.getElementById('escribir-tpl-preview');
  prev.style.display = 'none';
  if (!val || !_escribirTemplates) return;
  var parts = val.split('|');
  var name  = parts[0];
  var tpl   = (_escribirTemplates || []).find(function(t) { return t.name === name; });
  if (tpl && tpl.preview) {
    prev.textContent = tpl.preview;
    prev.style.display = 'block';
  }
}

async function enviarPlantilla() {
  var sel  = document.getElementById('escribir-tpl-sel');
  var val  = sel.value;
  var resEl = document.getElementById('escribir-tpl-result');
  var errEl = document.getElementById('escribir-tpl-error');
  errEl.style.display = 'none';
  resEl.style.display = 'none';
  if (!val) { errEl.textContent = 'Selecciona una plantilla'; errEl.style.display = 'block'; return; }
  var parts = val.split('|');
  var template_name = parts[0];
  var language_code = parts[1] || 'es_CO';
  try {
    var r = await fetch('/inbox/api/clientes/message', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      credentials: 'include',
      body: JSON.stringify({telefono: _escribirTel, template_name: template_name, language_code: language_code})
    });
    var d = await r.json();
    resEl.style.display = 'block';
    if (d.ok) {
      resEl.style.color = '#15803d';
      resEl.textContent = '✅ Plantilla enviada correctamente' + (d.message_id ? ' · ID: ' + d.message_id.slice(0,20) + '…' : '');
    } else {
      resEl.style.color = '#dc2626';
      resEl.textContent = '❌ Error: ' + he(d.error || 'Error desconocido');
    }
  } catch(err) {
    resEl.style.display = 'block';
    resEl.style.color = '#dc2626';
    resEl.textContent = '❌ Error de red: ' + he(String(err));
  }
}

/* ── INIT conversaciones ── */
loadConvs();
_convTimer = setInterval(loadConvs, 8000);


/* ══════════════════════════════════════════════════════
   DIFUSIÓN — templates y envío
   ══════════════════════════════════════════════════════ */
var _dif_templates = [];
var _csvContacts   = [];   // contactos cargados vía CSV (separados del textarea manual)

async function cargarTemplates() {
  var sel = document.getElementById('dif-tpl');
  sel.innerHTML = '<option value="">Cargando...</option>';
  try {
    var r = await fetch('/inbox/broadcast/templates', {credentials:'include'});
    var d = await r.json();
    if (d.error) {
      sel.innerHTML = '<option value="">⚠️ ' + d.error + '</option>';
      return;
    }
    // Solo plantillas APPROVED para difusiones
    var todas = d.templates || [];
    _dif_templates = todas.filter(function(t) { return (t.status || '').toUpperCase() === 'APPROVED'; });
    if (!_dif_templates.length && todas.length) {
      sel.innerHTML = '<option value="">Sin plantillas APROBADAS — hay ' + todas.length + ' en otro estado</option>';
      return;
    }
    if (!_dif_templates.length) {
      sel.innerHTML = '<option value="">No hay plantillas aprobadas en Meta</option>';
      return;
    }
    sel.innerHTML = '<option value="">— Selecciona una plantilla —</option>' +
      _dif_templates.map(function(t) {
        return '<option value="' + t.name + '">✅ ' + t.name + ' (' + t.language + ')</option>';
      }).join('');
  } catch(e) {
    sel.innerHTML = '<option value="">Error cargando plantillas</option>';
  }
}

function seleccionarTemplate() {
  var name = document.getElementById('dif-tpl').value;
  var tpl  = _dif_templates.find(function(t) { return t.name === name; });
  var varsWrap = document.getElementById('dif-vars-wrap');
  var varsDiv  = document.getElementById('dif-vars');
  var sendBtn  = document.getElementById('dif-sendbtn');

  if (!tpl) {
    _difActualizarPreview(null);
    varsWrap.style.display = 'none';
    sendBtn.disabled = true;
    return;
  }

  varsDiv.innerHTML = '';
  if (tpl.variables && tpl.variables.length) {
    varsWrap.style.display = 'block';
    tpl.variables.forEach(function(n) {
      var row = document.createElement('div');
      row.style.cssText = 'display:flex;align-items:center;gap:8px;margin-bottom:6px';
      row.innerHTML =
        '<label style="font-size:.82rem;color:#6b7a8d;white-space:nowrap;min-width:50px">{{' + he(n) + '}}</label>' +
        '<input class="f-inp" id="dif-var-' + n + '" style="flex:1" placeholder="Valor de ejemplo para {{' + n + '}}" oninput="_difActualizarPreview(_dif_templates.find(function(t){return t.name===document.getElementById(\'dif-tpl\').value;}))">';
      varsDiv.appendChild(row);
    });
  } else {
    varsWrap.style.display = 'none';
  }

  _difActualizarPreview(tpl);
  sendBtn.disabled = !document.getElementById('dif-phones').value.trim() && !document.getElementById('dif-conteo').textContent.match(/[1-9]/);
}

/* Actualiza el teléfono WhatsApp de difusiones */
function _difActualizarPreview(tpl) {
  var elBody = document.getElementById('dif-prev-body');
  var elHdrImg = document.getElementById('dif-prev-hdr-img');
  var elHdrVid = document.getElementById('dif-prev-hdr-vid');
  var elHdrDoc = document.getElementById('dif-prev-hdr-doc');
  var elHdrTxt = document.getElementById('dif-prev-hdr-txt');
  var elFooter = document.getElementById('dif-prev-footer');
  var elBtns   = document.getElementById('dif-prev-btns');

  // Limpiar todos los headers
  [elHdrImg,elHdrVid,elHdrDoc,elHdrTxt].forEach(function(e) { if(e) e.style.display='none'; });

  if (!tpl) {
    elBody.textContent = 'Selecciona una plantilla para ver la vista previa...';
    elBody.style.cssText = 'color:#999;font-style:italic';
    if(elFooter) elFooter.style.display='none';
    if(elBtns)   elBtns.style.display='none';
    return;
  }

  // Header
  var hdrType = (tpl.header_type || '').toUpperCase();
  if (hdrType === 'IMAGE') {
    elHdrImg.style.display = '';
    if (tpl.header_url) {
      var imgTag = document.getElementById('dif-prev-hdr-img-tag');
      imgTag.src = tpl.header_url;
      imgTag.style.display = '';
      elHdrImg.querySelector('div').style.display = 'none';
    }
  } else if (hdrType === 'VIDEO') {
    elHdrVid.style.display = '';
  } else if (hdrType === 'DOCUMENT') {
    elHdrDoc.style.display = '';
  } else if (hdrType === 'TEXT') {
    // Buscar texto del header en components
    var hdrTxt = '';
    (tpl.components || []).forEach(function(c) {
      if ((c.type||'').toUpperCase() === 'HEADER') hdrTxt = c.text || '';
    });
    if (hdrTxt) { elHdrTxt.style.display=''; elHdrTxt.textContent = hdrTxt; }
  }

  // Body: sustituir variables con valores de ejemplo ingresados
  var text = tpl.preview || '';
  if (tpl.variables) {
    tpl.variables.forEach(function(n) {
      var inp = document.getElementById('dif-var-' + n);
      var val = (inp && inp.value) ? inp.value : ('{{' + n + '}}');
      // Escapa el nombre de variable para usarlo en split
      text = text.split('{{' + n + '}}').join(val);
    });
  }
  // Renderizar formato WhatsApp
  var bodyHtml = he(text)
    .replace(/\*([^*\n]+)\*/g,'<b>$1</b>')
    .replace(/_([^_\n]+)_/g,'<i>$1</i>')
    .replace(/~([^~\n]+)~/g,'<s>$1</s>')
    .replace(/\{\{([^}]+)\}\}/g,'<span style="background:#e8f5e9;color:#2e7d32;border-radius:3px;padding:0 2px;font-weight:600">{{$1}}</span>');
  elBody.innerHTML = bodyHtml;
  elBody.style.cssText = '';

  // Footer
  var footerTxt = '';
  (tpl.components || []).forEach(function(c) {
    if ((c.type||'').toUpperCase() === 'FOOTER') footerTxt = c.text || '';
  });
  elFooter.style.display = footerTxt ? '' : 'none';
  elFooter.textContent   = footerTxt;

  // Botones
  var btnsHtml = '';
  (tpl.components || []).forEach(function(c) {
    if ((c.type||'').toUpperCase() !== 'BUTTONS') return;
    (c.buttons || []).forEach(function(b) {
      var btype = (b.type||'').toUpperCase();
      var ic = btype === 'QUICK_REPLY' ? '↩️' : (btype === 'URL' ? '🔗' : '📞');
      btnsHtml += '<div class="wa-btn"><span class="wa-btn-ic">' + ic + '</span>' + he(b.text||'') + '</div>';
    });
  });
  elBtns.style.display = btnsHtml ? '' : 'none';
  elBtns.innerHTML     = btnsHtml;
}

function descargarFormatoCSV() {
  var name = document.getElementById('dif-tpl').value;
  var tpl  = _dif_templates.find(function(t) { return t.name === name; });
  var extraCols = tpl && tpl.variables && tpl.variables.length
    ? tpl.variables.map(function(v) { return v; })
    : ['nombre'];

  var encabezado = ['telefono'].concat(extraCols).join(',');
  var ejemplos = [
    ['573001234567', 'Juan'].concat(extraCols.slice(1).map(function() { return 'valor'; })).join(','),
    ['573009876543', 'María'].concat(extraCols.slice(1).map(function() { return 'valor'; })).join(','),
    ['573001112233', 'Carlos'].concat(extraCols.slice(1).map(function() { return 'valor'; })).join(','),
  ];
  var csv = [encabezado].concat(ejemplos).join('\r\n');
  var blob = new Blob(['﻿' + csv], {type: 'text/csv;charset=utf-8;'});
  var url  = URL.createObjectURL(blob);
  var a    = document.createElement('a');
  a.href = url; a.download = 'formato_difusion.csv';
  document.body.appendChild(a); a.click();
  document.body.removeChild(a); URL.revokeObjectURL(url);
}

function cargarArchivoCSV(input) {
  var file = input.files && input.files[0];
  if (!file) return;
  var statsEl = document.getElementById('dif-csv-stats');
  statsEl.style.display = 'none';
  var reader = new FileReader();
  reader.onload = function(e) {
    var texto = e.target.result;
    if (texto.charCodeAt(0) === 0xFEFF) texto = texto.slice(1);
    var lineas = texto.split(/\r?\n/).map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });
    if (!lineas.length) {
      statsEl.style.display = 'block';
      statsEl.innerHTML = '⚠️ El archivo no tiene datos válidos.';
      return;
    }
    // Detectar y saltar encabezado
    var primeraCol = lineas[0].split(',')[0].trim();
    var esEncabezado = isNaN(primeraCol.replace(/\D/g,'')) || primeraCol.toLowerCase() === 'telefono';
    if (esEncabezado) lineas = lineas.slice(1);

    // Validar: primer campo ≥ 10 dígitos
    var validas = [];
    var erroneas = 0;
    lineas.forEach(function(l) {
      var tel = l.split(',')[0].trim().replace(/\D/g,'');
      if (tel.length >= 10) { validas.push(l); } else { erroneas++; }
    });

    // Guardar en array separado — NO tocar el textarea manual
    _csvContacts = _csvContacts.concat(validas);
    actualizarConteo();

    // Mostrar estadísticas
    statsEl.style.display = 'block';
    var totalCSV = _csvContacts.length;
    statsEl.innerHTML =
      '<span style="color:#155724;font-weight:600">✅ ' + validas.length + ' nuevo' + (validas.length===1?'':'s') +
      ' de <b>' + he(file.name) + '</b></span>' +
      (erroneas > 0 ? ' &nbsp;<span style="color:#721c24">❌ ' + erroneas + ' ignorado' + (erroneas===1?'':'s') + ' (número inválido)</span>' : '') +
      ' &nbsp;<span style="color:#4a5568">· Total CSV: <b>' + totalCSV + '</b></span>' +
      ' &nbsp;<button onclick="limpiarCSV()" style="background:none;border:none;color:#721c24;cursor:pointer;font-size:.76rem;text-decoration:underline;padding:0">🗑️ Limpiar CSV</button>';
    input.value = '';
  };
  reader.onerror = function() {
    statsEl.style.display = 'block';
    statsEl.innerHTML = '❌ Error al leer el archivo.';
  };
  reader.readAsText(file, 'UTF-8');
}

function limpiarCSV() {
  _csvContacts = [];
  document.getElementById('dif-csv-stats').innerHTML =
    '<span style="color:#6b7a8d">CSV limpiado — 0 contactos cargados</span>';
  actualizarConteo();
}

function _parsearDestinatarios() {
  var tpl   = _dif_templates.find(function(t) { return t.name === document.getElementById('dif-tpl').value; });
  var nVars = tpl ? (tpl.variables || []).length : 0;
  // Combinar CSV (_csvContacts) + líneas del textarea manual
  var manualLineas = document.getElementById('dif-phones').value
    .split('\n')
    .map(function(l) { return l.trim(); })
    .filter(function(l) { return l.length > 5; });
  var todasLineas = _csvContacts.concat(manualLineas);
  return todasLineas.map(function(l) {
    var partes = l.split(',').map(function(p) { return p.trim(); });
    var phone  = partes[0];
    var vars = [];
    for (var i = 0; i < nVars; i++) {
      if (partes[i + 1] !== undefined && partes[i + 1] !== '') {
        vars.push(partes[i + 1]);
      } else {
        var inp = document.getElementById('dif-var-' + (tpl.variables[i] || (i+1)));
        vars.push(inp ? inp.value.trim() : '');
      }
    }
    return {phone: phone, variables: vars};
  });
}

function actualizarConteo() {
  var dests = _parsearDestinatarios();
  var n = dests.length;
  var el = document.getElementById('dif-conteo');
  if (n > 0) {
    el.innerHTML = '<span style="color:var(--az);font-weight:600">' + n + ' destinatario' + (n===1?'':'s') + ' listo' + (n===1?'':'s') + '</span>';
  } else {
    el.textContent = '0 destinatarios';
  }
  var name = document.getElementById('dif-tpl').value;
  document.getElementById('dif-sendbtn').disabled = !name || !n;
}

async function enviarDifusion() {
  var name  = document.getElementById('dif-tpl').value;
  var tpl   = _dif_templates.find(function(t) { return t.name === name; });
  var res   = document.getElementById('dif-res-box');
  if (!tpl) return;

  // Nombre de campaña (obligatorio)
  var campaignName = (document.getElementById('dif-campaign-name').value || '').trim();
  if (!campaignName) {
    res.style.display = 'block';
    res.className = 'dif-res-box err';
    res.textContent = '⚠️ Escribe un nombre para la campaña antes de enviar.';
    document.getElementById('dif-campaign-name').focus();
    return;
  }

  var recipients = _parsearDestinatarios();
  if (!recipients.length) return;

  if (tpl.variables && tpl.variables.length) {
    var sinNombre = recipients.filter(function(r) {
      return r.variables.some(function(v) { return !v || v.trim() === ''; });
    });
    if (sinNombre.length) {
      res.style.display = 'block';
      res.className = 'dif-res-box err';
      res.textContent = '⚠️ ' + sinNombre.length + ' destinatario(s) tienen variables vacías.';
      return;
    }
  }

  // ID único para agrupar todos los lotes de esta campaña en el historial
  var campaignId = 'dif_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);

  var btn  = document.getElementById('dif-sendbtn');
  var prog = document.getElementById('dif-prog-wrap');
  var bar  = document.getElementById('dif-bar');
  var ptxt = document.getElementById('dif-ptxt');
  btn.disabled = true;
  prog.style.display = 'flex';
  bar.style.width = '0%';
  ptxt.textContent = 'Enviando 0 / ' + recipients.length + '...';
  res.style.display = 'none';

  try {
    var LOTE = 50;
    var enviados = 0; var fallidos = 0; var todosErrores = [];
    for (var i = 0; i < recipients.length; i += LOTE) {
      var lote = recipients.slice(i, i + LOTE);
      var r = await fetch('/inbox/broadcast/send', {
        method: 'POST',
        credentials: 'include',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({
          template: name,
          language: tpl.language,
          var_names: tpl.variables,
          named: tpl.named === true,
          header_type: tpl.header_type || null,
          header_url:  tpl.header_url  || null,
          campaign_name: campaignName,
          campaign_id:   campaignId,
          recipients: lote,
        }),
      });
      var d = await r.json();
      enviados += d.enviados || 0;
      fallidos += d.fallidos || 0;
      todosErrores = todosErrores.concat(d.errores || []);
      var pct = Math.round(((i + lote.length) / recipients.length) * 100);
      bar.style.width = Math.min(pct, 100) + '%';
      ptxt.textContent = 'Enviando ' + Math.min(i+LOTE, recipients.length) + ' / ' + recipients.length + '...';
    }
    bar.style.width = '100%';
    ptxt.textContent = 'Listo';
    res.style.display = 'block';
    if (fallidos === 0) {
      res.className = 'dif-res-box ok';
      res.textContent = '✅ Difusión completada: ' + enviados + ' mensajes enviados correctamente.';
    } else {
      res.className = 'dif-res-box err';
      res.textContent = '⚠️ ' + enviados + ' enviados, ' + fallidos + ' fallidos.\n' + todosErrores.slice(0,5).join('\n');
    }
    // Recargar historial
    cargarHistorialDif();
  } catch(e) {
    res.style.display = 'block';
    res.className = 'dif-res-box err';
    res.textContent = 'Error de conexión: ' + e.message;
  }
  btn.disabled = false;
}

async function cargarHistorialDif() {
  var tbody = document.getElementById('dif-hist-body');
  if (!tbody) return;
  try {
    var r = await fetch('/inbox/difusiones/historial', {credentials:'include'});
    var d = await r.json();
    var rows = d.difusiones || [];
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="loading-txt">Sin difusiones enviadas aún</td></tr>';
      return;
    }
    var h = '';
    rows.forEach(function(row) {
      var env  = row.enviados || 0;
      var ent  = row.entregados;   // null si sin tracking
      var lei  = row.leidos;       // null si sin tracking
      var failWh = row.fallidos_wh; // null si sin tracking

      var pctEnt = (ent !== null && env > 0) ? Math.round(ent / env * 100) : null;
      var pctLei = (lei !== null && env > 0) ? Math.round(lei / env * 100) : null;

      var campaignLabel = he(row.campaign_name || row.template_name);
      var tplLabel = (row.campaign_name && row.campaign_name !== row.template_name)
        ? '<small style="color:#6b7a8d">📋 ' + he(row.template_name) + ' · ' + he(row.language) + '</small>'
        : '<small style="color:#6b7a8d">' + he(row.language) + '</small>';

      function fmtStat(val, pct, colorOk, colorWarn) {
        if (val === null) return '<span style="color:#cbd5e0;font-size:.75rem">—</span>';
        var color = pct !== null ? (pct >= 80 ? colorOk : (pct >= 50 ? '#856404' : colorWarn)) : colorOk;
        var badge = '<span style="font-weight:700;color:' + color + '">' + val + '</span>';
        return pct !== null ? badge + ' <small style="color:#a0aec0">(' + pct + '%)</small>' : badge;
      }

      var detBtn = row.has_tracking && row.campaign_id
        ? '<button class="btn-secondary" style="padding:3px 10px;font-size:.73rem;white-space:nowrap" '
          + 'onclick="verDetalleCampana(\'' + row.campaign_id + '\',\'' + he(row.campaign_name||row.template_name).replace(/'/g,"\\'") + '\')">'
          + '🔍 Ver detalle</button>'
        : '<span style="color:#cbd5e0;font-size:.75rem">Sin tracking</span>';

      h += '<tr>'
        + '<td><b>' + campaignLabel + '</b><br>' + tplLabel + '</td>'
        + '<td style="font-size:.78rem;color:#6b7a8d;white-space:nowrap">' + fmtFecha(row.created_at) + '</td>'
        + '<td style="text-align:center;font-weight:600">' + env + '</td>'
        + '<td style="text-align:center">' + fmtStat(ent, pctEnt, '#155724', '#721c24') + '</td>'
        + '<td style="text-align:center">' + fmtStat(lei, pctLei, '#283593', '#856404') + '</td>'
        + '<td style="text-align:center">' + (failWh !== null
            ? (failWh > 0 ? '<span class="badge-err">' + failWh + '</span>' : '<span style="color:#155724;font-weight:600">0</span>')
            : '<span style="color:#cbd5e0;font-size:.75rem">—</span>') + '</td>'
        + '<td style="text-align:center">' + detBtn + '</td>'
        + '</tr>';
    });
    tbody.innerHTML = h;
  } catch(e) {
    tbody.innerHTML = '<tr><td colspan="6" class="loading-txt" style="color:#721c24">Error cargando historial</td></tr>';
  }
}

/* ══════════════════════════════════════════════════════
   DETALLE DE CAMPAÑA — modal
   ══════════════════════════════════════════════════════ */
async function verDetalleCampana(campaignId, campaignName) {
  var modal = document.getElementById('dif-detail-modal');
  document.getElementById('dif-det-titulo').textContent = campaignName || 'Detalle de campaña';
  document.getElementById('dif-det-sub').textContent    = '⏳ Cargando estadísticas...';
  document.getElementById('dc-total').textContent     = '—';
  document.getElementById('dc-entregados').textContent = '—';
  document.getElementById('dc-leidos').textContent    = '—';
  document.getElementById('dc-fallidos').textContent  = '—';
  document.getElementById('dif-det-funnel').innerHTML  = '';
  document.getElementById('dif-det-errores').style.display   = 'none';
  document.getElementById('dif-det-pendientes').style.display = 'none';
  modal.style.display = 'flex';

  try {
    var r = await fetch('/inbox/difusiones/campana/' + encodeURIComponent(campaignId), {credentials:'include'});
    var d = await r.json();
    _renderDetalleCampana(d, campaignName);
  } catch(e) {
    document.getElementById('dif-det-sub').textContent = '❌ Error cargando datos: ' + e.message;
  }
}

function cerrarDetalleCampana(evt) {
  if (evt && evt.target !== document.getElementById('dif-detail-modal')) return;
  document.getElementById('dif-detail-modal').style.display = 'none';
}

function _renderDetalleCampana(d, campaignName) {
  var total    = d.total     || 0;
  var ent      = d.entregados|| 0;
  var lei      = d.leidos    || 0;
  var fail     = d.fallidos  || 0;
  var pend     = d.pendientes|| 0;
  var errores  = d.errores   || [];

  var pctEnt  = total > 0 ? Math.round(ent  / total * 100) : 0;
  var pctLei  = total > 0 ? Math.round(lei  / total * 100) : 0;
  var pctFail = total > 0 ? Math.round(fail / total * 100) : 0;

  document.getElementById('dif-det-sub').textContent =
    total + ' mensajes rastreados · ' + pctEnt + '% entregados · ' + pctLei + '% leídos';

  document.getElementById('dc-total').textContent      = total;
  document.getElementById('dc-entregados').textContent = ent + ' (' + pctEnt + '%)';
  document.getElementById('dc-leidos').textContent     = lei + ' (' + pctLei + '%)';
  document.getElementById('dc-fallidos').textContent   = fail + ' (' + pctFail + '%)';

  // ── Funnel de entrega ──────────────────────────────
  var funnelEl = document.getElementById('dif-det-funnel');
  function mkFunnelRow(lbl, val, pct, color) {
    var w = Math.max(pct, 2);
    return '<div class="funnel-row">'
      + '<span class="funnel-lbl">' + lbl + '</span>'
      + '<div class="funnel-wrap"><div class="funnel-fill" style="width:' + w + '%;background:' + color + '">'
      + (pct > 12 ? pct + '%' : '') + '</div></div>'
      + '<span class="funnel-cnt">' + val + ' <small style="color:#a0aec0;font-weight:400">(' + pct + '%)</small></span>'
      + '</div>';
  }
  funnelEl.innerHTML = '<h4 style="font-size:.82rem;font-weight:700;color:#4a5568;'
    + 'text-transform:uppercase;letter-spacing:.06em;margin-bottom:12px">📊 Embudo de entrega</h4>'
    + mkFunnelRow('Enviados',   total, 100,    '#4299e1')
    + mkFunnelRow('Entregados', ent,   pctEnt, '#48bb78')
    + mkFunnelRow('Leídos',     lei,   pctLei, '#667eea')
    + (fail > 0 ? mkFunnelRow('Fallidos', fail, pctFail, '#fc8181') : '');

  // ── Mensajes pendientes ─────────────────────────────
  if (pend > 0) {
    document.getElementById('dif-det-pend-cnt').textContent = pend;
    document.getElementById('dif-det-pendientes').style.display = 'block';
  }

  // ── Tabla de errores ────────────────────────────────
  if (errores.length > 0) {
    var errEl = document.getElementById('dif-det-errores');
    errEl.style.display = 'block';
    var tbody = document.getElementById('dif-det-errbody');
    tbody.innerHTML = errores.map(function(err) {
      var nums = (err.numeros || []).map(function(n) {
        // Enmascarar últimos 4 dígitos: 573001234567 → +57 300 123 ****
        var s = String(n);
        return s.length > 4 ? s.slice(0, -4).replace(/(\d{2})(\d{3})(\d*)/, '+$1 $2 $3').trim() + ' ****' : s;
      });
      var moreCount = (err.count || 0) - nums.length;
      return '<tr>'
        + '<td><b>' + he(err.description || 'Error desconocido') + '</b>'
        + (err.code ? ' <span class="err-badge">Código ' + err.code + '</span>' : '') + '</td>'
        + '<td style="text-align:center;font-weight:700;color:#b71c1c">' + err.count + '</td>'
        + '<td><div class="err-nums">' + nums.join('<br>')
          + (moreCount > 0 ? '<br><i>...y ' + moreCount + ' más</i>' : '') + '</div></td>'
        + '</tr>';
    }).join('');
  }
}

/* ══════════════════════════════════════════════════════
   PLANTILLAS
   ══════════════════════════════════════════════════════ */
// Mapa id/name→template (plantillas Meta) y id→datos (borradores locales)
var _tplMetaMap = {};
var _borrMap    = {};

async function cargarTablaPlantillas() {
  var tbody = document.getElementById('tpl-tabla-body');
  tbody.innerHTML = '<tr><td colspan="6" class="loading-txt">Cargando...</td></tr>';
  _tplMetaMap = {};
  try {
    var r = await fetch('/inbox/broadcast/templates', {credentials:'include'});
    var d = await r.json();

    // Error explícito del backend (ej: META_WABA_ID no configurado)
    if (d.error) {
      tbody.innerHTML = '<tr><td colspan="6" class="loading-txt" style="color:#c0392b">' +
        '⚠️ ' + he(d.error) + '</td></tr>';
      cargarBorradores();
      return;
    }

    var tpls = d.templates || [];
    if (!tpls.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="loading-txt">Sin plantillas en Meta · Verifica META_WABA_ID en Railway</td></tr>';
      cargarBorradores();
      return;
    }

    var h = '';
    tpls.forEach(function(t) {
      _tplMetaMap[t.id || t.name] = t;
      var status = (t.status || '').toUpperCase();
      var cls = status === 'APPROVED' ? 'badge-ok' : (status === 'PENDING' ? 'badge-warn' : (status === 'REJECTED' ? 'badge-err' : 'badge-pend'));
      var lbl = status === 'APPROVED' ? '✅ Aprobada' : (status === 'PENDING' ? '⏳ Pendiente' : (status === 'REJECTED' ? '❌ Rechazada' : status));
      var vars = t.variables ? t.variables.join(', ') : '—';
      var hdrFmt = t.header_type || '—';
      // Usar la clave del mapa (_tplMetaMap) — evita doble JSON.stringify que rompe onclick=""
      var mapKey  = t.id || t.name;
      var editBtn = '<button class="btn-secondary" style="padding:3px 10px;font-size:.75rem" onclick="cargarPlantillaParaEditar(\'' + mapKey + '\')" title="Editar componentes">✏️ Editar</button>';
      var difBtn  = status === 'APPROVED'
        ? ' <button class="btn-primary" style="padding:3px 10px;font-size:.75rem" onclick="irADifusionConPlantilla(\'' + t.name + '\')" title="Enviar difusión con esta plantilla">📤 Difusión</button>'
        : '';
      h += '<tr>'
        + '<td><b>' + he(t.name) + '</b></td>'
        + '<td>' + he(t.language || '') + '</td>'
        + '<td><span class="' + cls + '">' + lbl + '</span></td>'
        + '<td style="font-size:.78rem">' + he(vars || '—') + '</td>'
        + '<td style="font-size:.78rem">' + he(hdrFmt || '—') + '</td>'
        + '<td style="white-space:nowrap">' + editBtn + difBtn + '</td>'
        + '</tr>';
    });
    tbody.innerHTML = h || '<tr><td colspan="6" class="loading-txt">Sin plantillas</td></tr>';
  } catch(e) {
    tbody.innerHTML = '<tr><td colspan="6" class="loading-txt" style="color:#721c24">Error cargando plantillas</td></tr>';
  }
  // También cargar borradores
  cargarBorradores();
}

/* ── Ir a Difusiones con plantilla precargada ── */
function irADifusionConPlantilla(tName) {
  // 1. Navegar a difusiones (si ya está ahí, showSec hace no-op, pero
  //    igual refrescamos el select para incluir la plantilla recién aprobada)
  var eraOtraSec = (_secActual !== 'difusiones');
  showSec('difusiones');

  // 2. Si ya estábamos en difusiones, cargarTemplates no fue llamado por showSec
  //    (el flag _secCargadas ya estaba en true). Forzar recarga del select.
  if (!eraOtraSec) {
    cargarTemplates();
  }

  // 3. Intentar seleccionar la plantilla en el <select> con reintentos
  //    (el fetch es async; esperamos hasta que el select tenga opciones reales)
  var intentos = 0;
  function _intentar() {
    var sel = document.getElementById('dif-tpl');
    // Opciones listas = más de 1 (el placeholder "Cargando..." cuenta como 1)
    var optsListas = sel && sel.options.length > 1;
    if (optsListas) {
      for (var i = 0; i < sel.options.length; i++) {
        if (sel.options[i].value === tName) {
          sel.value = tName;
          seleccionarTemplate();
          sel.scrollIntoView({behavior: 'smooth', block: 'center'});
          sel.style.transition = 'box-shadow .3s';
          sel.style.boxShadow  = '0 0 0 3px rgba(18,140,126,.45)';
          setTimeout(function() { sel.style.boxShadow = ''; }, 1400);
          return;
        }
      }
      // Opciones cargadas pero la plantilla no aparece (raro: debería ser APPROVED)
      console.warn('[irADifusion] "' + tName + '" no encontrada en plantillas aprobadas');
      return;
    }
    // Todavía cargando — reintentar cada 200 ms, máx 5 segundos (25 intentos)
    if (intentos++ < 25) setTimeout(_intentar, 200);
  }
  setTimeout(_intentar, 150);
}

/* ── Borradores locales ── */
async function cargarBorradores() {
  var tbody = document.getElementById('borr-tabla-body');
  if (!tbody) return;
  try {
    var r = await fetch('/inbox/plantillas/borradores', {credentials:'include'});
    var d = await r.json();
    var borrs = d.borradores || [];
    if (!borrs.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="loading-txt">Sin borradores guardados</td></tr>';
      return;
    }
    var h = '';
    _borrMap = {};
    borrs.forEach(function(b) {
      // Guardar datos en mapa para evitar doble JSON.stringify en onclick
      _borrMap[b.id] = typeof b.datos === 'string' ? JSON.parse(b.datos) : b.datos;
      var ts = b.updated_at ? b.updated_at.replace('T',' ').substring(0,16) : '';
      h += '<tr>'
        + '<td><b>' + he(b.nombre) + '</b></td>'
        + '<td>' + he(b.categoria) + '</td>'
        + '<td>' + he(b.idioma) + '</td>'
        + '<td style="font-size:.78rem">' + he(ts) + '</td>'
        + '<td style="white-space:nowrap">'
          + '<button class="btn-secondary" style="padding:3px 9px;font-size:.75rem;margin-right:4px" onclick="cargarBorrador(' + b.id + ')">📂 Abrir</button>'
          + '<button class="btn-remove" style="padding:3px 8px;font-size:.75rem" onclick="eliminarBorrador(' + b.id + ')">🗑️</button>'
        + '</td>'
        + '</tr>';
    });
    tbody.innerHTML = h;
  } catch(e) {
    tbody.innerHTML = '<tr><td colspan="5" class="loading-txt" style="color:#721c24">Error</td></tr>';
  }
}

async function guardarBorrador() {
  var nombre = document.getElementById('tpl-nombre').value.trim();
  if (!nombre) { showTplResult('err','⚠️ El nombre es obligatorio para guardar el borrador.'); return; }
  var cat    = document.getElementById('tpl-cat').value;
  var lang   = document.getElementById('tpl-lang').value;
  var body   = document.getElementById('tpl-body').value.trim();
  var footer = document.getElementById('tpl-footer').value.trim();
  var hdrTipo  = document.querySelector('input[name="hdr-type"]:checked').value;
  var hdrTexto = hdrTipo === 'TEXT' ? document.getElementById('tpl-hdr-text').value.trim() : '';
  var buttons  = _recolectarBotones();
  var payload  = {
    name: nombre, category: cat, language: lang,
    header_type: hdrTipo !== 'NONE' ? hdrTipo : null,
    header_text: hdrTexto || null,
    body: body, footer: footer || null, buttons: buttons,
  };
  var btn = document.getElementById('tpl-borrador-btn');
  btn.disabled = true;
  btn.textContent = '⏳ Guardando...';
  try {
    var r = await fetch('/inbox/plantillas/borrador', {
      method: 'POST', credentials: 'include',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload),
    });
    var d = await r.json();
    if (d.ok) {
      showTplResult('ok','💾 Borrador <b>' + he(nombre) + '</b> guardado correctamente.');
      cargarBorradores();
    } else {
      showTplResult('err','❌ ' + he(d.error || 'Error guardando borrador'));
    }
  } catch(e) {
    showTplResult('err','Error: ' + e.message);
  }
  btn.disabled = false;
  btn.textContent = '💾 Guardar borrador';
}

async function eliminarBorrador(bid) {
  if (!confirm('¿Eliminar este borrador?')) return;
  try {
    var r = await fetch('/inbox/plantillas/borrador/' + bid, {method:'DELETE', credentials:'include'});
    if (r.ok) cargarBorradores();
  } catch(e) {}
}

function cargarBorrador(bid) {
  try {
    var datos = _borrMap[bid];
    if (!datos) { console.error('[borrador] No encontrado en mapa:', bid); return; }
    _poblarFormulario(datos);
    // Modo creación (no edición Meta)
    document.getElementById('tpl-meta-id').value = '';
    document.getElementById('tpl-form-icon').textContent = '📂';
    document.getElementById('tpl-form-title').textContent = 'Borrador: ' + (datos.name || '');
    document.getElementById('tpl-form-sub').textContent   = 'Cargado desde borrador local';
    document.getElementById('tpl-cancelar-btn').style.display = 'none';
    document.getElementById('tpl-crear-btn').textContent  = '📤 Enviar a Meta para aprobación';
    showTplResult('warn','📂 Borrador cargado. Revisa el contenido y envíalo a Meta cuando esté listo.');
    // Scroll al form
    document.getElementById('tpl-nombre').scrollIntoView({behavior:'smooth', block:'center'});
  } catch(e) { alert('Error cargando borrador'); }
}

/* ── Editar plantilla Meta ── */
function cargarPlantillaParaEditar(keyOrObj) {
  try {
    // Acepta: clave del mapa (string/number) o objeto directo (legacy)
    var t = (typeof keyOrObj === 'object' && keyOrObj !== null)
      ? keyOrObj
      : _tplMetaMap[keyOrObj];
    if (!t) { console.error('[editar] Plantilla no encontrada en mapa:', keyOrObj); return; }
    // Extraer campos de los componentes
    var datos = {
      name: t.name,
      category: '',    // Meta no devuelve categoría en templates list — dejamos en blanco
      language: t.language,
      body: '',
      footer: null,
      header_type: null,
      header_text: null,
      buttons: [],
    };
    (t.components || []).forEach(function(c) {
      var tipo = (c.type || '').toUpperCase();
      if (tipo === 'BODY')   datos.body   = c.text || '';
      if (tipo === 'FOOTER') datos.footer = c.text || '';
      if (tipo === 'HEADER') {
        datos.header_type = c.format || 'TEXT';
        datos.header_text = c.text || '';
      }
      if (tipo === 'BUTTONS') {
        datos.buttons = (c.buttons || []).map(function(b) {
          return {type: b.type, text: b.text, url: b.url || '', phone_number: b.phone_number || ''};
        });
      }
    });
    _poblarFormulario(datos);
    // Poner en modo edición
    var mid = t.id || '';
    document.getElementById('tpl-meta-id').value = mid;
    document.getElementById('tpl-form-icon').textContent = '✏️';
    document.getElementById('tpl-form-title').textContent = 'Editando: ' + t.name;
    document.getElementById('tpl-form-sub').textContent   = 'Se enviará a Meta · Volverá a estado PENDIENTE';
    document.getElementById('tpl-cancelar-btn').style.display = '';
    document.getElementById('tpl-crear-btn').textContent  = '✏️ Guardar cambios en Meta';
    document.getElementById('tpl-nombre').disabled = true;
    document.getElementById('tpl-cat').disabled    = true;
    document.getElementById('tpl-lang').disabled   = true;
    showTplResult('warn','✏️ Modo edición — solo puedes cambiar los componentes (cuerpo, encabezado, botones). Al guardar la plantilla vuelve a estado <b>PENDIENTE</b>.');
    document.getElementById('tpl-nombre').scrollIntoView({behavior:'smooth', block:'center'});
  } catch(e) { alert('Error cargando plantilla para edición: ' + e); }
}

function cancelarEdicion() {
  document.getElementById('tpl-meta-id').value = '';
  document.getElementById('tpl-form-icon').textContent  = '✨';
  document.getElementById('tpl-form-title').textContent = 'Nueva plantilla';
  document.getElementById('tpl-form-sub').textContent   = 'Se envía a Meta · Aprobación en 24-48 h';
  document.getElementById('tpl-cancelar-btn').style.display = 'none';
  document.getElementById('tpl-crear-btn').textContent  = '📤 Enviar a Meta para aprobación';
  document.getElementById('tpl-nombre').disabled = false;
  document.getElementById('tpl-cat').disabled    = false;
  document.getElementById('tpl-lang').disabled   = false;
  _limpiarFormulario();
  document.getElementById('tpl-result').style.display = 'none';
  document.getElementById('tpl-approval-panel').style.display = 'none';
}

function _poblarFormulario(datos) {
  document.getElementById('tpl-nombre').value = datos.name || '';
  if (datos.category) document.getElementById('tpl-cat').value = datos.category;
  if (datos.language) document.getElementById('tpl-lang').value = datos.language;
  // Renderizar subcategorías para la categoría seleccionada (también aplica reglas del subcat)
  actualizarSubcat();
  document.getElementById('tpl-body').value   = datos.body || '';
  document.getElementById('tpl-footer').value = datos.footer || '';
  updateBodyCounter();
  updateCounter('tpl-footer','footer-cnt',60);
  // Header
  var hdrTipo = datos.header_type || 'NONE';
  var radios = document.querySelectorAll('input[name="hdr-type"]');
  radios.forEach(function(r) { if (r.value === hdrTipo) r.checked = true; });
  toggleHdrType(hdrTipo);
  if (hdrTipo === 'TEXT') document.getElementById('tpl-hdr-text').value = datos.header_text || '';
  // Botones — restaurar en lista unificada
  var btnList = document.getElementById('btn-list');
  if (btnList) btnList.innerHTML = '';
  var buttons = datos.buttons || [];
  buttons.forEach(function(b) {
    var tipo = b.type || 'QUICK_REPLY';
    if (tipo === 'VOICE_CALL') tipo = 'WHATSAPP_VOICE_CALL';
    _agregarBoton(tipo);
    var rows = document.querySelectorAll('#btn-list .ubn-row');
    var row = rows[rows.length - 1];
    if (!row) return;
    if (tipo === 'COPY_CODE') {
      var ci = row.querySelector('.ubn-code'); if (ci) ci.value = b.example_code || b.text || '';
    } else {
      var ti = row.querySelector('.ubn-text'); if (ti) ti.value = b.text || '';
      if (tipo === 'URL')          { var ui = row.querySelector('.ubn-url');     if (ui) ui.value = b.url || ''; }
      if (tipo === 'PHONE_NUMBER') { var pi = row.querySelector('.ubn-phone');   if (pi) pi.value = b.phone_number || ''; }
      if (tipo === 'FLOW')         { var fi = row.querySelector('.ubn-flow-id'); if (fi) fi.value = b.flow_id || ''; }
    }
  });
}

function _limpiarFormulario() {
  document.getElementById('tpl-nombre').value  = '';
  document.getElementById('tpl-body').value    = '';
  document.getElementById('tpl-footer').value  = '';
  document.getElementById('tpl-hdr-text').value = '';
  document.querySelector('input[name="hdr-type"][value="NONE"]').checked = true;
  toggleHdrType('NONE');
  var btnList = document.getElementById('btn-list'); if (btnList) btnList.innerHTML = '';
  ['img','vid','doc'].forEach(limpiarArchivo);
  updateBodyCounter();
  updateCounter('tpl-footer','footer-cnt',60);
  var emojiWarn = document.getElementById('body-emoji-warn'); if (emojiWarn) emojiWarn.style.display = 'none';
  var prevBody = document.getElementById('prev-body'); if (prevBody) prevBody.style.color = '';
  // Resetear campos nuevos
  document.querySelector('input[name="var-type"][value="NUMERO"]').checked = true;
  actualizarTipoVar('NUMERO');
  var ttlCb = document.getElementById('ttl-activo');
  if (ttlCb) { ttlCb.checked = false; toggleTTL(); }
  var locLat = document.getElementById('tpl-loc-lat'); if (locLat) locLat.value = '';
  var locLng = document.getElementById('tpl-loc-lng'); if (locLng) locLng.value = '';
  var locNm  = document.getElementById('tpl-loc-name'); if (locNm) locNm.value = '';
  actualizarSubcat();
}

/* ── Helper compartido: recolectar botones del form ── */
function _recolectarBotones() {
  var buttons = [];
  var list = document.getElementById('btn-list');
  if (!list) return buttons;
  list.querySelectorAll('.ubn-row').forEach(function(row) {
    var tipo = row.dataset.btype;
    if (tipo === 'QUICK_REPLY') {
      var txt = ((row.querySelector('.ubn-text') || {}).value || '').trim();
      if (txt) buttons.push({type:'QUICK_REPLY', text: txt});
    } else if (tipo === 'URL') {
      var texto = ((row.querySelector('.ubn-text') || {}).value || '').trim();
      var url   = ((row.querySelector('.ubn-url')  || {}).value || '').trim();
      if (texto && url) buttons.push({type:'URL', text: texto, url: url});
    } else if (tipo === 'PHONE_NUMBER') {
      var texto2 = ((row.querySelector('.ubn-text')  || {}).value || '').trim();
      var tel    = ((row.querySelector('.ubn-phone') || {}).value || '').trim();
      if (texto2 && tel) buttons.push({type:'PHONE_NUMBER', text: texto2, phone_number: tel});
    } else if (tipo === 'WHATSAPP_VOICE_CALL') {
      var texto3 = ((row.querySelector('.ubn-text') || {}).value || '').trim();
      if (texto3) buttons.push({type:'VOICE_CALL', text: texto3});
    } else if (tipo === 'FLOW') {
      var texto4 = ((row.querySelector('.ubn-text')    || {}).value || '').trim();
      var flowId = ((row.querySelector('.ubn-flow-id') || {}).value || '').trim();
      if (texto4) buttons.push({type:'FLOW', text: texto4, flow_id: flowId || null});
    } else if (tipo === 'COPY_CODE') {
      var code = ((row.querySelector('.ubn-code') || {}).value || '').trim();
      if (code) buttons.push({type:'COPY_CODE', example_code: code});
    }
  });
  return buttons;
}

/* ══════════════════════════════════════════════════════
   PLANTILLAS — form interactivo
   ══════════════════════════════════════════════════════ */
// Archivos seleccionados (guardados en memoria hasta el envío)
var _tplFiles = { img: null, vid: null, doc: null };
// Handle de media obtenido al subir a Meta
var _tplHandles = { img: null, vid: null, doc: null };

function updateCounter(inputId, counterId, max) {
  var val = document.getElementById(inputId).value.length;
  var el  = document.getElementById(counterId);
  if (!el) return;
  el.textContent = val;
  el.parentElement.className = 'char-counter' + (val > max * .85 ? ' warn' : '');
}

function updateBodyCounter() {
  var inp = document.getElementById('tpl-body');
  if (!inp) return;
  var val = inp.value;
  var charLen = val.length;
  var el = document.getElementById('body-cnt');
  if (el) {
    el.textContent = charLen;
    el.parentElement.className = 'char-counter' + (charLen > 1024 * .85 ? ' warn' : '');
  }
  // Count emojis (Extended_Pictographic covers all actual emoji glyphs, excludes 0-9/#/*)
  var emojiCount = 0;
  try {
    emojiCount = (val.match(/\p{Extended_Pictographic}/gu) || []).length;
  } catch(e) {
    // fallback for older browsers
    emojiCount = (val.match(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu) || []).length;
  }
  var tooMany = emojiCount > 10;
  var warnEl = document.getElementById('body-emoji-warn');
  if (warnEl) warnEl.style.display = tooMany ? '' : 'none';
  var prevBody = document.getElementById('prev-body');
  if (prevBody) prevBody.style.color = tooMany ? '#e53935' : '';
  actualizarPreview();
}

/* ── Subcategoría según categoría ── */
var _SUBCATS = {
  MARKETING: [
    {value:'DEFAULT',                  label:'Predeterminado',               desc:'Envía mensajes con contenido multimedia y botones personalizados para captar el interés de tus clientes.'},
    {value:'CATALOG_MESSAGE',          label:'Catálogo',                     desc:'Conecta tu catálogo de productos para enviar mensajes que impulsen las ventas.'},
    {value:'CALL_PERMISSION_REQUEST',  label:'Solicitud de permisos de llamada', desc:'Pide permiso al cliente para poder llamarle por WhatsApp.'},
  ],
  UTILITY: [
    {value:'DEFAULT',                  label:'Predeterminado',               desc:'Envía mensajes sobre un pedido o una cuenta existentes.'},
    {value:'CALL_PERMISSION_REQUEST',  label:'Solicitud de permisos de llamada', desc:'Ask customers if you can call them on WhatsApp.'},
  ],
  AUTHENTICATION: [
    {value:'DEFAULT',                  label:'OTP estándar',                 desc:'Envía contraseñas de un solo uso (códigos de verificación).'},
  ],
};

function actualizarSubcat() {
  var cat  = document.getElementById('tpl-cat').value;
  var opts = _SUBCATS[cat] || _SUBCATS.MARKETING;
  var el   = document.getElementById('subcat-opts');
  el.innerHTML = opts.map(function(o, i) {
    return '<label class="radio-opt' + (i===0?' chk':'') + '" style="flex-direction:column;align-items:flex-start;padding:10px 14px;border-radius:8px;border:1px solid #e0e4e8;background:#fafbfc;gap:2px;cursor:pointer">'
      + '<span style="display:flex;align-items:center;gap:8px"><input type="radio" name="tpl-subcat" value="' + o.value + '"' + (i===0?' checked':'') + '> <b style="font-size:.84rem;color:#1a2332">' + o.label + '</b></span>'
      + '<span style="font-size:.75rem;color:#6b7a8d;padding-left:22px">' + o.desc + '</span>'
      + '</label>';
  }).join('');
  // Re-hook radio style + aplicar reglas al cambiar subcategoría
  el.querySelectorAll('input[type=radio]').forEach(function(r) {
    r.addEventListener('change', function() {
      el.querySelectorAll('.radio-opt').forEach(function(l) { l.classList.remove('chk'); });
      r.closest('.radio-opt').classList.add('chk');
      _aplicarReglaSubcat();
    });
  });
  // Mostrar período de validez solo para MARKETING
  var ttlWrap = document.getElementById('ttl-wrap');
  if (ttlWrap) ttlWrap.style.display = (cat === 'MARKETING') ? '' : 'none';
  // Aplicar reglas según la subcategoría seleccionada
  _aplicarReglaSubcat();
}

/* ── Reglas por subcategoría (CATALOG_MESSAGE / CALL_PERMISSION_REQUEST / DEFAULT) ── */
function _aplicarReglaSubcat() {
  var subcat = (document.querySelector('input[name="tpl-subcat"]:checked') || {}).value || 'DEFAULT';
  var hdrSec      = document.getElementById('hdr-section');
  var catSec      = document.getElementById('catalog-section');
  var btnControls = document.getElementById('btn-controls');
  var catNotice   = document.getElementById('catalog-btn-notice');
  var callNotice  = document.getElementById('call-perm-notice');

  if (subcat === 'CATALOG_MESSAGE') {
    // Ocultar encabezado (no permite multimedia)
    if (hdrSec)    hdrSec.style.display    = 'none';
    // Mostrar selector de formato catálogo
    if (catSec)    catSec.style.display    = '';
    // Ocultar controles normales de botones, mostrar aviso catálogo
    if (btnControls) btnControls.style.display = 'none';
    if (catNotice)   catNotice.style.display   = '';
    if (callNotice)  callNotice.style.display  = 'none';
    // Reset header a NONE
    var r = document.querySelector('input[name="hdr-type"][value="NONE"]');
    if (r) { r.checked = true; toggleHdrType('NONE'); }

  } else if (subcat === 'CALL_PERMISSION_REQUEST') {
    // Ocultar encabezado
    if (hdrSec)    hdrSec.style.display    = 'none';
    if (catSec)    catSec.style.display    = 'none';
    // Ocultar controles normales de botones, mostrar aviso llamada
    if (btnControls) btnControls.style.display = 'none';
    if (catNotice)   catNotice.style.display   = 'none';
    if (callNotice)  callNotice.style.display  = '';
    // Reset header a NONE
    var r2 = document.querySelector('input[name="hdr-type"][value="NONE"]');
    if (r2) { r2.checked = true; toggleHdrType('NONE'); }

  } else {
    // DEFAULT u otros: mostrar todo normal
    if (hdrSec)    hdrSec.style.display    = '';
    if (catSec)    catSec.style.display    = 'none';
    if (btnControls) btnControls.style.display = '';
    if (catNotice)   catNotice.style.display   = 'none';
    if (callNotice)  callNotice.style.display  = 'none';
  }
  actualizarPreview();
}

/* ── Tipo de encabezado ── */
function toggleHdrType(tipo) {
  // Mapa explícito: valor del radio → ID del wrapper en el DOM
  var idMap = {
    TEXT:     'hdr-text-wrap',
    IMAGE:    'hdr-img-wrap',
    VIDEO:    'hdr-vid-wrap',
    DOCUMENT: 'hdr-doc-wrap',
    LOCATION: 'hdr-location-wrap',
  };
  Object.keys(idMap).forEach(function(t) {
    var w = document.getElementById(idMap[t]);
    if (w) w.style.display = (t === tipo) ? 'block' : 'none';
  });
  // Actualizar estilo radio buttons
  document.querySelectorAll('#hdr-radio-group .radio-opt').forEach(function(lbl) {
    var inp = lbl.querySelector('input');
    lbl.classList.toggle('chk', inp && inp.value === tipo);
  });
  actualizarPreview();
}

/* ── Tipo de variable ── */
function actualizarTipoVar(tipo) {
  var hint = document.getElementById('vartype-hint');
  document.querySelectorAll('[name=var-type]').forEach(function(r) {
    r.closest('.radio-opt').classList.toggle('chk', r.value === tipo);
  });
  if (tipo === 'NOMBRE') {
    hint.innerHTML = 'Escribe <code>{{nombre}}</code>, <code>{{ciudad}}</code>… en el cuerpo · Las variables deben coincidir exactamente al enviar';
  } else {
    hint.innerHTML = 'Escribe <code>{{1}}</code>, <code>{{2}}</code>… en el cuerpo para insertar variables posicionales';
  }
}

/* ── Período de validez ── */
function toggleTTL() {
  var activo = document.getElementById('ttl-activo').checked;
  document.getElementById('ttl-sel-wrap').style.display = activo ? '' : 'none';
}

/* ── Dropdown de tipo de botón ── */
function _toggleBtnMenu(e) {
  e.stopPropagation();
  var menu = document.getElementById('btn-type-menu');
  if (!menu) return;
  menu.classList.toggle('open');
}
// Cerrar menú al hacer clic fuera
document.addEventListener('click', function(e) {
  var menu = document.getElementById('btn-type-menu');
  if (menu && !menu.closest('.btn-add-wrap').contains(e.target)) menu.classList.remove('open');
});

/* ── Agregar botón unificado ── */
function _agregarBoton(tipo) {
  var menu = document.getElementById('btn-type-menu');
  if (menu) menu.classList.remove('open');
  var list = document.getElementById('btn-list');
  if (!list) return;
  // Límites
  var total = list.querySelectorAll('.ubn-row').length;
  if (total >= 10) { alert('Máximo 10 botones en total'); return; }
  var typeCnt = list.querySelectorAll('.ubn-row[data-btype="' + tipo + '"]').length;
  var maxPerType = {QUICK_REPLY:3, URL:2, PHONE_NUMBER:1, WHATSAPP_VOICE_CALL:1, FLOW:1, COPY_CODE:1};
  var lim = maxPerType[tipo];
  if (lim && typeCnt >= lim) { alert('Máximo ' + lim + ' botón(es) de este tipo'); return; }

  var badges = {
    QUICK_REPLY:'<span class="ubn-type-badge ubn-badge-qr">↩️ Personalizado</span>',
    URL:'<span class="ubn-type-badge ubn-badge-url">🔗 Sitio web</span>',
    PHONE_NUMBER:'<span class="ubn-type-badge ubn-badge-phone">📞 Teléfono</span>',
    WHATSAPP_VOICE_CALL:'<span class="ubn-type-badge ubn-badge-wacall">📲 WhatsApp Call</span>',
    FLOW:'<span class="ubn-type-badge ubn-badge-flow">🔄 Flow</span>',
    COPY_CODE:'<span class="ubn-type-badge ubn-badge-code">🏷️ Código de oferta</span>',
  };
  var row = document.createElement('div');
  row.className = 'ubn-row';
  row.dataset.btype = tipo;
  var removeBtn = '<button class="btn-remove" onclick="_eliminarBoton(this)" type="button">✕</button>';
  var hdr = '<div class="ubn-hdr">' + (badges[tipo]||tipo) + '{FIELD}' + removeBtn + '</div>';
  var html = '';
  if (tipo === 'QUICK_REPLY') {
    html = hdr.replace('{FIELD}','<input class="f-inp ubn-text" maxlength="25" placeholder="Ej: Sí, me interesa" style="flex:1" oninput="actualizarPreview()">'
      + '<span class="ubn-cnt">0/25</span>');
  } else if (tipo === 'URL') {
    html = hdr.replace('{FIELD}','<input class="f-inp ubn-text" maxlength="25" placeholder="Texto del botón" style="flex:1" oninput="actualizarPreview()">')
      + '<input class="f-inp ubn-url" placeholder="https://equoradistribuciones.com/{{1}}" oninput="actualizarPreview()" style="margin-top:2px">'
      + '<span class="f-hint">La URL puede incluir <code>{{1}}</code> para personalizar por destinatario</span>';
  } else if (tipo === 'PHONE_NUMBER') {
    html = hdr.replace('{FIELD}','<input class="f-inp ubn-text" maxlength="25" placeholder="Texto del botón" style="flex:1" oninput="actualizarPreview()">')
      + '<input class="f-inp ubn-phone" placeholder="+573001234567" oninput="actualizarPreview()" style="margin-top:2px">'
      + '<span class="f-hint">Número con código de país — el cliente inicia la llamada al tocarlo</span>';
  } else if (tipo === 'WHATSAPP_VOICE_CALL') {
    html = hdr.replace('{FIELD}','<input class="f-inp ubn-text" maxlength="25" placeholder="Texto del botón" style="flex:1" oninput="actualizarPreview()">')
      + '<span class="f-hint">Permite al cliente llamarte directamente por WhatsApp</span>';
  } else if (tipo === 'FLOW') {
    html = hdr.replace('{FIELD}','<input class="f-inp ubn-text" maxlength="25" placeholder="Texto del botón" style="flex:1" oninput="actualizarPreview()">')
      + '<input class="f-inp ubn-flow-id" placeholder="ID del Flow de WhatsApp" oninput="actualizarPreview()" style="margin-top:2px">'
      + '<span class="f-hint">Requiere un Flow publicado en tu cuenta de WhatsApp Business</span>';
  } else if (tipo === 'COPY_CODE') {
    html = '<div class="ubn-hdr">' + (badges[tipo]||tipo)
      + '<input class="f-inp ubn-code" placeholder="Código de oferta (ej: EQUORA20)" style="flex:1" oninput="actualizarPreview()">'
      + removeBtn + '</div>'
      + '<span class="f-hint">El cliente toca el botón para copiar el código al portapapeles</span>';
  }
  row.innerHTML = html;
  // Contador de caracteres para QR
  if (tipo === 'QUICK_REPLY') {
    var inp = row.querySelector('.ubn-text');
    var cnt = row.querySelector('.ubn-cnt');
    if (inp && cnt) { inp.addEventListener('input', function() { cnt.textContent = this.value.length + '/25'; }); }
  }
  list.appendChild(row);
  actualizarPreview();
}

function _eliminarBoton(btn) {
  btn.closest('.ubn-row').remove();
  actualizarPreview();
}

/* ── Tipo de botones (legacy — no-op para compatibilidad) ── */
function toggleBtnType(tipo) { /* replaced by _agregarBoton */ }

/* ── Upload zona ── */
function seleccionarArchivo(input, tipo, maxMB) {
  var file = input.files && input.files[0];
  if (!file) return;
  if (file.size > maxMB * 1024 * 1024) {
    alert('El archivo supera el límite de ' + maxMB + ' MB. Por favor elige uno más pequeño.');
    input.value = '';
    return;
  }
  _tplFiles[tipo]  = file;
  _tplHandles[tipo] = null;  // resetear handle anterior
  // Mostrar preview
  document.getElementById(tipo + '-fname').textContent = file.name;
  document.getElementById(tipo + '-fsize').textContent = (file.size / 1024 / 1024).toFixed(2) + ' MB';
  document.getElementById(tipo + '-preview').style.display = 'flex';
  document.getElementById(tipo + '-zone').classList.add('has-file');
  input.value = '';
  actualizarPreview();
}

function handleDrop(e, tipo) {
  var file = e.dataTransfer.files && e.dataTransfer.files[0];
  if (!file) return;
  // Simular selección
  var dt = new DataTransfer();
  dt.items.add(file);
  var inputId = 'tpl-' + tipo + '-file';
  document.getElementById(inputId).files = dt.files;
  document.getElementById(inputId).dispatchEvent(new Event('change'));
}

function limpiarArchivo(tipo) {
  _tplFiles[tipo]  = null;
  _tplHandles[tipo] = null;
  document.getElementById(tipo + '-preview').style.display = 'none';
  document.getElementById(tipo + '-zone').classList.remove('has-file');
  document.getElementById('tpl-' + tipo + '-file').value = '';
  actualizarPreview();
}

/* ── agregarBotonQR / agregarBotonCTA — legacy stubs (usar _agregarBoton) ── */
function agregarBotonQR()  { _agregarBoton('QUICK_REPLY'); }
function agregarBotonCTA() { _agregarBoton('URL'); }
function toggleCtaTipo(sel) { /* no-op legacy */ }

/* ── Subir media a Meta antes de crear la plantilla ── */
async function subirHeaderMedia(tipo) {
  var file = _tplFiles[tipo];
  if (!file) return null;
  if (_tplHandles[tipo]) return _tplHandles[tipo]; // ya subido

  var progEl = document.getElementById(tipo + '-upload-prog');
  if (progEl) progEl.style.display = 'flex';

  try {
    var fd = new FormData();
    fd.append('file', file, file.name);
    fd.append('file_type', file.type);
    var r = await fetch('/inbox/plantillas/subir-header', {
      method: 'POST',
      credentials: 'include',
      body: fd,
    });
    var d = await r.json();
    if (d.handle) {
      _tplHandles[tipo] = d.handle;
      return d.handle;
    } else {
      console.warn('[tpl] subir-header error:', d.error);
      return null;
    }
  } catch(e) {
    console.warn('[tpl] subir-header excepción:', e);
    return null;
  } finally {
    if (progEl) progEl.style.display = 'none';
  }
}

/* ── Crear o editar plantilla (router) ── */
async function crearOEditarPlantilla() {
  var metaId = document.getElementById('tpl-meta-id').value.trim();
  if (metaId) {
    await _editarPlantilla(metaId);
  } else {
    await crearPlantilla();
  }
}

/* ── Crear plantilla nueva ── */
async function crearPlantilla() {
  var nombre = document.getElementById('tpl-nombre').value.trim();
  var cat    = document.getElementById('tpl-cat').value;
  var lang   = document.getElementById('tpl-lang').value;
  var body   = document.getElementById('tpl-body').value.trim();
  var footer = document.getElementById('tpl-footer').value.trim();
  var btn    = document.getElementById('tpl-crear-btn');

  // Tipo header activo
  var hdrTipo  = document.querySelector('input[name="hdr-type"]:checked').value;
  var hdrTexto = hdrTipo === 'TEXT' ? document.getElementById('tpl-hdr-text').value.trim() : '';

  // Validaciones
  if (!nombre) { showTplResult('err','⚠️ El nombre es obligatorio.'); return; }
  if (!body)   { showTplResult('err','⚠️ El cuerpo del mensaje es obligatorio.'); return; }
  if (hdrTipo === 'TEXT' && !hdrTexto) { showTplResult('err','⚠️ Escribe el texto del encabezado o cambia el tipo a "Ninguno".'); return; }

  btn.disabled = true;
  btn.textContent = '⏳ Enviando...';
  document.getElementById('tpl-result').style.display = 'none';
  document.getElementById('tpl-approval-panel').style.display = 'none';

  // Subir media si aplica
  var headerHandle = null;
  if (['IMAGE','VIDEO','DOCUMENT'].includes(hdrTipo)) {
    var tipoKey = hdrTipo === 'IMAGE' ? 'img' : (hdrTipo === 'VIDEO' ? 'vid' : 'doc');
    if (_tplFiles[tipoKey]) {
      btn.textContent = '⏳ Subiendo archivo...';
      headerHandle = await subirHeaderMedia(tipoKey);
    }
  }

  var buttons  = _recolectarBotones();
  var subcat   = document.querySelector('input[name="tpl-subcat"]:checked');
  subcat = subcat ? subcat.value : 'DEFAULT';
  var catalogFmt = (document.querySelector('input[name="catalog-format"]:checked') || {}).value || 'FULL';
  var varType  = document.querySelector('input[name="var-type"]:checked');
  varType = varType ? varType.value : 'NUMERO';
  var ttlActivo = document.getElementById('ttl-activo') ? document.getElementById('ttl-activo').checked : false;
  var ttlSecs   = document.getElementById('tpl-ttl') ? parseInt(document.getElementById('tpl-ttl').value) : 43200;
  var locLat    = document.getElementById('tpl-loc-lat') ? document.getElementById('tpl-loc-lat').value : '';
  var locLng    = document.getElementById('tpl-loc-lng') ? document.getElementById('tpl-loc-lng').value : '';
  var locName   = document.getElementById('tpl-loc-name') ? document.getElementById('tpl-loc-name').value.trim() : '';
  btn.textContent = '⏳ Creando plantilla...';

  try {
    var payload = {
      name: nombre, category: cat, language: lang,
      sub_category: subcat,
      catalog_format: catalogFmt,
      header_type: hdrTipo !== 'NONE' ? hdrTipo : null,
      header_text: hdrTexto || null,
      header_handle: headerHandle,
      body: body, footer: footer || null, buttons: buttons,
      var_type: varType,
      ttl_activo: ttlActivo,
      ttl: ttlSecs,
      loc_lat: locLat || null,
      loc_lng: locLng || null,
      loc_name: locName || null,
    };
    var r = await fetch('/inbox/plantillas/crear', {
      method: 'POST', credentials: 'include',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload),
    });
    var d = await r.json();
    if (d.ok) {
      // Mostrar panel de aprobación prominente
      document.getElementById('tpl-approval-name').textContent = '📋 Plantilla "' + nombre + '" — ID Meta: ' + (d.id || '—');
      document.getElementById('tpl-approval-panel').style.display = 'block';
      document.getElementById('tpl-result').style.display = 'none';
      _limpiarFormulario();
      cargarTablaPlantillas();
    } else {
      showTplResult('err','❌ Error de Meta: ' + he(d.error || 'Error desconocido'));
    }
  } catch(e) {
    showTplResult('err','Error de conexión: ' + e.message);
  }
  btn.disabled = false;
  btn.textContent = '📤 Enviar a Meta para aprobación';
}

/* ── Editar plantilla existente ── */
async function _editarPlantilla(metaId) {
  var body     = document.getElementById('tpl-body').value.trim();
  var footer   = document.getElementById('tpl-footer').value.trim();
  var hdrTipo  = document.querySelector('input[name="hdr-type"]:checked').value;
  var hdrTexto = hdrTipo === 'TEXT' ? document.getElementById('tpl-hdr-text').value.trim() : '';
  var btn      = document.getElementById('tpl-crear-btn');

  if (!body) { showTplResult('err','⚠️ El cuerpo del mensaje es obligatorio.'); return; }

  btn.disabled = true;
  btn.textContent = '⏳ Guardando cambios...';
  document.getElementById('tpl-result').style.display = 'none';
  document.getElementById('tpl-approval-panel').style.display = 'none';

  // Subir media si aplica
  var headerHandle = null;
  if (['IMAGE','VIDEO','DOCUMENT'].includes(hdrTipo)) {
    var tipoKey = hdrTipo === 'IMAGE' ? 'img' : (hdrTipo === 'VIDEO' ? 'vid' : 'doc');
    if (_tplFiles[tipoKey]) {
      btn.textContent = '⏳ Subiendo archivo...';
      headerHandle = await subirHeaderMedia(tipoKey);
    }
  }

  var buttons = _recolectarBotones();

  try {
    var payload = {
      template_id: metaId,
      header_type: hdrTipo !== 'NONE' ? hdrTipo : null,
      header_text: hdrTexto || null,
      header_handle: headerHandle,
      body: body, footer: footer || null, buttons: buttons,
    };
    var r = await fetch('/inbox/plantillas/editar', {
      method: 'POST', credentials: 'include',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload),
    });
    var d = await r.json();
    if (d.ok) {
      var nombre = document.getElementById('tpl-nombre').value.trim();
      document.getElementById('tpl-approval-name').textContent = '✏️ Plantilla "' + nombre + '" actualizada — vuelve a estado PENDIENTE.';
      document.getElementById('tpl-approval-panel').style.display = 'block';
      document.getElementById('tpl-approval-panel').style.background = '#fff8e1';
      document.getElementById('tpl-approval-panel').style.borderColor = '#f9a825';
      document.getElementById('tpl-approval-panel').querySelector('div').style.color = '#7b5e00';
      cancelarEdicion();
      cargarTablaPlantillas();
    } else {
      showTplResult('err','❌ Error: ' + he(d.error || 'Error desconocido'));
    }
  } catch(e) {
    showTplResult('err','Error de conexión: ' + e.message);
  }
  btn.disabled = false;
  btn.textContent = '✏️ Guardar cambios en Meta';
}

function showTplResult(tipo, html) {
  var el = document.getElementById('tpl-result');
  el.style.display = 'block';
  el.innerHTML = html;
  el.style.cssText = 'display:block;margin-bottom:14px;font-size:.83rem;padding:10px 14px;border-radius:8px;line-height:1.6;' +
    (tipo === 'ok'   ? 'background:#d4edda;color:#155724;border:1px solid #c3e6cb' :
     tipo === 'warn' ? 'background:#fff3cd;color:#856404;border:1px solid #ffeaa7' :
                       'background:#f8d7da;color:#721c24;border:1px solid #f5c6cb');
}

/* ══════════════════════════════════════════════════════
   VISTA PREVIA WHATSAPP EN TIEMPO REAL
   ══════════════════════════════════════════════════════ */

function actualizarPreview() {
  // ── Header ──
  var hdrTipo = document.querySelector('input[name="hdr-type"]:checked');
  hdrTipo = hdrTipo ? hdrTipo.value : 'NONE';

  var elHdrImg = document.getElementById('prev-hdr-img');
  var elHdrVid = document.getElementById('prev-hdr-vid');
  var elHdrDoc = document.getElementById('prev-hdr-doc');
  var elHdrTxt = document.getElementById('prev-hdr-txt');
  [elHdrImg, elHdrVid, elHdrDoc, elHdrTxt].forEach(function(e) { if(e) e.style.display = 'none'; });

  if (hdrTipo === 'IMAGE') {
    elHdrImg.style.display = '';
    var file = _tplFiles.img;
    var imgTag = document.getElementById('prev-hdr-img-tag');
    var emoji  = document.getElementById('prev-hdr-img-emoji');
    if (file) {
      var reader = new FileReader();
      reader.onload = function(ev) {
        imgTag.src = ev.target.result;
        imgTag.style.display = '';
        emoji.style.display  = 'none';
      };
      reader.readAsDataURL(file);
    } else {
      imgTag.style.display  = 'none';
      emoji.style.display   = '';
      emoji.textContent     = '🖼️';
    }
  } else if (hdrTipo === 'VIDEO') {
    elHdrVid.style.display = '';
    var fileV = _tplFiles.vid;
    // Video: si hay archivo local mostrar thumbnail aproximado
    document.getElementById('prev-hdr-vid').querySelector('.wa-hdr-emoji').textContent = fileV ? '🎥' : '🎥';
  } else if (hdrTipo === 'DOCUMENT') {
    elHdrDoc.style.display = '';
    var fileD = _tplFiles.doc;
    document.getElementById('prev-doc-name').textContent = fileD ? fileD.name : 'documento.pdf';
  } else if (hdrTipo === 'LOCATION') {
    elHdrImg.style.display = '';
    var imgTagL = document.getElementById('prev-hdr-img-tag');
    var emojiL  = document.getElementById('prev-hdr-img-emoji');
    var locName = (document.getElementById('tpl-loc-name') || {}).value || '';
    imgTagL.style.display = 'none';
    emojiL.style.display  = '';
    emojiL.textContent    = '📍';
    // Mostrar nombre del lugar debajo del emoji en la preview
    elHdrImg.style.flexDirection = 'column';
    elHdrImg.style.gap = '4px';
    var locLabel = elHdrImg.querySelector('.wa-loc-label');
    if (!locLabel) { locLabel = document.createElement('span'); locLabel.className = 'wa-loc-label'; locLabel.style.cssText='font-size:.72rem;color:#fff;font-weight:600;text-align:center;padding:0 8px'; elHdrImg.appendChild(locLabel); }
    locLabel.textContent = locName || 'Ubicación';
  } else if (hdrTipo === 'TEXT') {
    // Limpiar label de ubicación si cambian el tipo
    var locLbl = document.querySelector('.wa-loc-label'); if (locLbl) locLbl.remove();
    var hdrTexto = (document.getElementById('tpl-hdr-text').value || '').trim();
    if (hdrTexto) {
      elHdrTxt.style.display = '';
      elHdrTxt.textContent   = hdrTexto;
    }
  }

  // ── Cuerpo ──
  var bodyRaw = (document.getElementById('tpl-body').value || '').trim();
  var bodyEl  = document.getElementById('prev-body');
  if (bodyRaw) {
    // Resaltar variables {{...}} con color verde
    var bodyHtml = he(bodyRaw)
      .replace(/\*([^*]+)\*/g, '<b>$1</b>')
      .replace(/_([^_]+)_/g, '<i>$1</i>')
      .replace(/~([^~]+)~/g, '<s>$1</s>')
      .replace(/\{\{([^}]+)\}\}/g, '<span style="background:#e8f5e9;color:#2e7d32;border-radius:3px;padding:0 2px;font-weight:600">{{$1}}</span>');
    bodyEl.innerHTML = bodyHtml;
  } else {
    bodyEl.textContent = 'Escribe el cuerpo del mensaje...';
  }

  // ── Footer ──
  var footer    = (document.getElementById('tpl-footer').value || '').trim();
  var footerEl  = document.getElementById('prev-footer');
  footerEl.style.display = footer ? '' : 'none';
  footerEl.textContent   = footer;

  // ── Botones ──
  var btnsEl   = document.getElementById('prev-btns');
  var btnsHtml = '';
  var btnList  = document.getElementById('btn-list');
  var btnIcons = {QUICK_REPLY:'↩️', URL:'🔗', PHONE_NUMBER:'📞',
                  WHATSAPP_VOICE_CALL:'📲', FLOW:'🔄', COPY_CODE:'🏷️'};
  if (btnList) {
    btnList.querySelectorAll('.ubn-row').forEach(function(row) {
      var tipo = row.dataset.btype;
      var ic   = btnIcons[tipo] || '🔘';
      var txt  = tipo === 'COPY_CODE'
        ? ((row.querySelector('.ubn-code') || {}).value || 'Código').trim()
        : ((row.querySelector('.ubn-text') || {}).value || '').trim();
      if (txt) btnsHtml += '<div class="wa-btn"><span class="wa-btn-ic">' + ic + '</span>' + he(txt) + '</div>';
    });
  }
  btnsEl.style.display = btnsHtml ? '' : 'none';
  btnsEl.innerHTML     = btnsHtml;
}

/* Cerrar modal de detalle con Escape */
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    var modal = document.getElementById('dif-detail-modal');
    if (modal && modal.style.display !== 'none') {
      modal.style.display = 'none';
    }
  }
});

/* Delegación de eventos para botones de remoción */
document.addEventListener('click', function(e) {
  if (e.target && (e.target.classList.contains('btn-remove') || e.target.closest('.btn-remove'))) {
    setTimeout(actualizarPreview, 50);
  }
});

/* Hook: conectar preview a todos los campos del form */
function _hookPreview() {
  var ids = ['tpl-hdr-text','tpl-body','tpl-footer','tpl-loc-name','tpl-loc-lat','tpl-loc-lng'];
  ids.forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener('input', actualizarPreview);
  });
  // Radio header
  document.querySelectorAll('input[name="hdr-type"]').forEach(function(r) {
    r.addEventListener('change', actualizarPreview);
  });
  // btn-list: MutationObserver para re-hookear inputs cuando se agregan botones
  var observer = new MutationObserver(function() {
    var bl = document.getElementById('btn-list');
    if (!bl) return;
    bl.querySelectorAll('input').forEach(function(inp) {
      if (!inp._previewHooked) {
        inp._previewHooked = true;
        inp.addEventListener('input', actualizarPreview);
      }
    });
    actualizarPreview();
  });
  var btnListEl = document.getElementById('btn-list');
  if (btnListEl) observer.observe(btnListEl, {childList:true, subtree:true});
  // Disparo inicial
  actualizarPreview();
}

/* ══════════════════════════════════════════════════════
   MÉTRICAS
   ══════════════════════════════════════════════════════ */

/* Preset de rango rápido — al cambiar el select muestra/oculta date pickers */
function metAplicarPreset(valor) {
  var custom = document.getElementById('met-rango-custom');
  if (!custom) return;
  if (valor === 'custom') {
    custom.style.display = 'flex';
    // Si no hay fecha previa, prepoblar últimos 30 días
    var d_desde = document.getElementById('met-desde');
    var d_hasta = document.getElementById('met-hasta');
    if (!d_desde.value) {
      var hoy = new Date();
      var hace30 = new Date(hoy.getTime() - 30*86400000);
      d_desde.value = hace30.toISOString().slice(0,10);
      d_hasta.value = hoy.toISOString().slice(0,10);
    }
  } else {
    custom.style.display = 'none';
    cargarMetricas();
  }
}

async function cargarMetricas() {
  var cardsDif  = document.getElementById('met-cards-dif');
  var cardsRoi  = document.getElementById('met-cards-roi');
  var cardsConv = document.getElementById('met-cards-conv');
  var campBody  = document.getElementById('met-camp-body');
  var aviso     = document.getElementById('met-aviso-tracking');
  var periodo   = document.getElementById('met-periodo').value || '30';
  var granularidad = (document.getElementById('met-granularidad') || {}).value || 'dia';
  var ld = '<div class="loading-txt" style="grid-column:1/-1">Cargando...</div>';

  cardsDif.innerHTML  = ld;
  cardsRoi.innerHTML  = ld;
  cardsConv.innerHTML = ld;
  campBody.innerHTML  = '<tr><td colspan="9" class="loading-txt">Cargando...</td></tr>';
  if (aviso) aviso.style.display = 'none';

  // Construir querystring según preset o rango custom
  var qs = 'granularidad=' + encodeURIComponent(granularidad);
  if (periodo === 'custom') {
    var desde = document.getElementById('met-desde').value;
    var hasta = document.getElementById('met-hasta').value;
    if (!desde || !hasta) {
      cardsDif.innerHTML = cardsRoi.innerHTML = cardsConv.innerHTML =
        '<div class="loading-txt" style="grid-column:1/-1;color:#721c24">⚠️ Selecciona fecha desde y hasta</div>';
      return;
    }
    qs += '&desde=' + encodeURIComponent(desde) + '&hasta=' + encodeURIComponent(hasta);
  } else {
    qs += '&dias=' + encodeURIComponent(periodo);
  }

  try {
    var r = await fetch('/inbox/metricas/interno?' + qs, {credentials:'include'});
    var d = await r.json();

    if (d.error) {
      var msg = '<div class="loading-txt" style="grid-column:1/-1;color:#721c24">⚠️ ' + he(d.error) + '</div>';
      cardsDif.innerHTML = cardsRoi.innerHTML = cardsConv.innerHTML = msg;
      campBody.innerHTML = '<tr><td colspan="9" class="loading-txt" style="color:#721c24">Error al cargar</td></tr>';
      return;
    }

    var shopifyOk = !!d.shopify_habilitado;
    var tarifa    = d.tarifa_meta_usd || 0.0165;
    var el = document.getElementById('met-tarifa');
    if (el) el.textContent = tarifa.toFixed(4);

    // Ocultar columnas ROI si Shopify no está habilitado
    document.querySelectorAll('.met-col-roi').forEach(function(el){
      el.style.display = shopifyOk ? '' : 'none';
    });

    // ── Fila 1: KPIs difusiones ──────────────────────────────────────────
    var dif  = d.difusiones || {};
    var ra   = dif.rastreados     || 0;
    var en   = dif.entregados     || 0;
    var le   = dif.leidos         || 0;
    var fa   = dif.fallidos       || 0;
    var env  = dif.total_enviados || 0;
    var camps= dif.total_campanas || 0;
    var pctE = dif.tasa_entrega   || 0;
    var pctL = dif.tasa_lectura   || 0;

    cardsDif.innerHTML =
      mkCard('📣', 'Campañas', camps, 'en el período') +
      mkCard('📤', 'Enviados', env.toLocaleString('es-CO'), 'conversaciones Meta') +
      mkCard('📦', 'Entregados', ra > 0 ? en.toLocaleString('es-CO') : '—',
             ra > 0 ? pctE + '% de rastreados' : 'Sin tracking aún') +
      mkCard('👁',  'Leídos',     ra > 0 ? le.toLocaleString('es-CO') : '—',
             ra > 0 ? pctL + '% de rastreados' : 'Sin tracking aún') +
      mkCard('❌', 'Fallidos',   ra > 0 ? fa.toLocaleString('es-CO') : '—',
             ra > 0 ? (fa > 0 ? 'Ver detalle en Difusiones' : 'Sin errores') : 'Sin tracking aún');

    // ── Fila 2: Costo Meta + Ventas + ROI ───────────────────────────────
    var costoTotalUsd  = dif.costo_total_usd   || 0;
    var ventasTotalCop = d.ventas_total_cop     || 0;
    var costoStr  = 'USD $' + costoTotalUsd.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2});
    var ventasStr = ventasTotalCop > 0
      ? '$' + ventasTotalCop.toLocaleString('es-CO', {minimumFractionDigits:0, maximumFractionDigits:0})
      : (shopifyOk ? '$0' : 'Shopify no conectado');
    var costoPorEnv = env > 0
      ? 'USD $' + (costoTotalUsd / env).toFixed(4) + ' / conv.'
      : 'Sin envíos';

    var roiCards = mkCard('💵', 'Costo Meta', costoStr, costoPorEnv)
                 + mkCard('💱', 'Tarifa / conv.', 'USD $' + tarifa.toFixed(4), 'marketing · Colombia');
    if (shopifyOk) {
      roiCards += mkCard('🛒', 'Ventas atribuidas', ventasStr, 'COP · 7 días post-envío');
      if (costoTotalUsd > 0 && ventasTotalCop > 0) {
        // ROAS en ratio puro (ventas COP / costo USD — comparativo relativo)
        // Para un ROAS real en misma moneda se necesita TRM; mostramos ratio
        var roas = (ventasTotalCop / costoTotalUsd).toFixed(1);
        roiCards += mkCard('📈', 'ROAS', roas + 'x', 'COP ventas / USD costo');
      } else {
        roiCards += mkCard('📈', 'ROAS', '—', 'Sin ventas atribuidas aún');
      }
    } else {
      roiCards += mkCard('🛒', 'Ventas Shopify', '—', 'Configura SHOPIFY_ADMIN_TOKEN') +
                  mkCard('📈', 'ROAS', '—', 'Requiere integración Shopify');
    }
    cardsRoi.innerHTML = roiCards;

    // ── Fila 3: Conversaciones IA ────────────────────────────────────────
    var conv  = d.conversaciones || {};
    var chats = conv.chats_activos      || 0;
    var recv  = conv.mensajes_recibidos || 0;
    var aiMsg = conv.mensajes_ai        || 0;

    cardsConv.innerHTML =
      mkCard('💬', 'Chats activos', chats.toLocaleString('es-CO'), 'números únicos') +
      mkCard('📨', 'Mensajes recibidos', recv.toLocaleString('es-CO'), 'de clientes') +
      mkCard('🤖', 'Respuestas IA', aiMsg.toLocaleString('es-CO'), 'generadas por Claude') +
      mkCard('⚡', 'Total interacciones', (recv + aiMsg).toLocaleString('es-CO'), 'en el período');

    // ── Tabla por campaña ────────────────────────────────────────────────
    var campanas = d.campanas || [];
    var colSpan  = shopifyOk ? 9 : 7;
    if (!campanas.length) {
      campBody.innerHTML = '<tr><td colspan="' + colSpan + '" class="loading-txt">Sin campañas en este período</td></tr>';
      return;
    }

    var hasTracking = campanas.some(function(c){ return c.rastreados > 0; });
    if (aviso && hasTracking) aviso.style.display = 'inline';

    var h = '';
    campanas.forEach(function(c) {
      var fecha = c.fecha ? c.fecha.substring(0,10) : '—';
      var pE = c.pct_entrega != null ? c.pct_entrega.toFixed(1) + '%' : '—';
      var pL = c.pct_lectura != null ? c.pct_lectura.toFixed(1) + '%' : '—';
      var enStr = c.rastreados > 0
        ? c.entregados.toLocaleString('es-CO') + ' <small style="color:#6b7a8d">(' + pE + ')</small>'
        : '<span style="color:#aaa">—</span>';
      var leStr = c.rastreados > 0
        ? c.leidos.toLocaleString('es-CO') + ' <small style="color:#6b7a8d">(' + pL + ')</small>'
        : '<span style="color:#aaa">—</span>';
      var faStr = c.rastreados > 0
        ? '<span style="color:' + (c.fallidos > 0 ? '#c62828' : '#4caf50') + '">' + c.fallidos + '</span>'
        : '<span style="color:#aaa">—</span>';
      var costoStr2 = c.costo_usd > 0
        ? 'USD $' + c.costo_usd.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})
        : '<span style="color:#aaa">—</span>';
      var ventasStr2 = shopifyOk
        ? (c.ventas_cop > 0
            ? '<span style="color:#2e7d32;font-weight:600">$' + c.ventas_cop.toLocaleString('es-CO',{minimumFractionDigits:0,maximumFractionDigits:0}) + '</span>'
            : '<span style="color:#aaa">$0</span>')
        : '';
      var roasStr = '';
      if (shopifyOk) {
        roasStr = (c.costo_usd > 0 && c.ventas_cop > 0)
          ? '<span style="color:#1565c0;font-weight:700">' + (c.ventas_cop / c.costo_usd).toFixed(1) + 'x</span>'
          : '<span style="color:#aaa">—</span>';
      }

      h += '<tr>'
        + '<td><b>' + he(c.campaign_name || '—') + '</b></td>'
        + '<td style="color:#6b7a8d;font-size:.8rem">' + fecha + '</td>'
        + '<td style="text-align:right">' + (c.enviados || 0).toLocaleString('es-CO') + '</td>'
        + '<td style="text-align:right">' + enStr + '</td>'
        + '<td style="text-align:right">' + leStr + '</td>'
        + '<td style="text-align:right">' + faStr + '</td>'
        + '<td style="text-align:right;font-family:monospace;font-size:.82rem">' + costoStr2 + '</td>'
        + (shopifyOk ? '<td style="text-align:right" class="met-col-roi">' + ventasStr2 + '</td>' : '')
        + (shopifyOk ? '<td style="text-align:right" class="met-col-roi">' + roasStr + '</td>' : '')
        + '</tr>';
    });
    campBody.innerHTML = h;

    // ── Renderizar series temporales (gráfica simple con barras) ──
    _renderSeriesTemporales(d.series, d.granularidad);

  } catch(e) {
    var errMsg = '<div class="loading-txt" style="grid-column:1/-1;color:#721c24">Error al cargar métricas: ' + he(String(e)) + '</div>';
    cardsDif.innerHTML = cardsRoi.innerHTML = cardsConv.innerHTML = errMsg;
    campBody.innerHTML = '<tr><td colspan="9" class="loading-txt" style="color:#721c24">Error al cargar</td></tr>';
  }
}

/* ── Render de series temporales (gráfica simple sin librerías) ── */
function _renderSeriesTemporales(series, granularidad) {
  var wrap = document.getElementById('met-series-wrap');
  if (!wrap || !series) return;
  var dif  = series.difusiones    || [];
  var trk  = series.tracking      || [];
  var conv = series.conversaciones || [];

  // Si todo está vacío, ocultar
  if (!dif.length && !trk.length && !conv.length) {
    wrap.innerHTML = '<div style="color:#94a3b8;text-align:center;padding:16px;font-size:.84rem">Sin datos en el rango seleccionado</div>';
    return;
  }

  var fmtPeriodo = function(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    if (granularidad === 'mes') {
      return d.toLocaleDateString('es-CO', {month:'short', year:'numeric'});
    } else if (granularidad === 'semana') {
      return 'Sem ' + d.toLocaleDateString('es-CO', {day:'2-digit', month:'short'});
    }
    return d.toLocaleDateString('es-CO', {day:'2-digit', month:'short'});
  };

  // Mostrar serie de mensajes (recibidos + IA) como mini-gráfica de barras
  var maxMsg = 1;
  conv.forEach(function(p){ var t = (p.recibidos||0) + (p.enviados_ai||0); if (t > maxMsg) maxMsg = t; });

  var barrasConv = conv.map(function(p) {
    var total = (p.recibidos||0) + (p.enviados_ai||0);
    var pctR = maxMsg > 0 ? (p.recibidos||0)/maxMsg*100 : 0;
    var pctA = maxMsg > 0 ? (p.enviados_ai||0)/maxMsg*100 : 0;
    return '<div style="display:flex;flex-direction:column;align-items:center;flex:1;min-width:50px">' +
      '<div style="font-size:.7rem;color:#475569;font-weight:700;margin-bottom:4px">' + total + '</div>' +
      '<div style="width:24px;height:100px;background:#f1f5f9;border-radius:4px;display:flex;flex-direction:column;justify-content:flex-end;overflow:hidden;position:relative">' +
        '<div style="background:#4f46e5;height:' + pctA + '%" title="IA enviados: ' + (p.enviados_ai||0) + '"></div>' +
        '<div style="background:#22c55e;height:' + pctR + '%" title="Recibidos: ' + (p.recibidos||0) + '"></div>' +
      '</div>' +
      '<div style="font-size:.66rem;color:#94a3b8;margin-top:4px;text-align:center">' + fmtPeriodo(p.periodo) + '</div>' +
    '</div>';
  }).join('');

  // Tabla simple de difusiones por período
  var filasDif = dif.map(function(p) {
    var t = trk.find(function(x){ return x.periodo === p.periodo; }) || {};
    return '<tr style="border-bottom:1px solid #f1f5f9">' +
      '<td style="padding:6px 10px;font-size:.82rem">' + fmtPeriodo(p.periodo) + '</td>' +
      '<td style="padding:6px 10px;font-size:.82rem;text-align:center">' + p.campanas + '</td>' +
      '<td style="padding:6px 10px;font-size:.82rem;text-align:right">' + (p.enviados||0).toLocaleString('es-CO') + '</td>' +
      '<td style="padding:6px 10px;font-size:.82rem;text-align:right;color:#16a34a">' + (t.entregados||0).toLocaleString('es-CO') + '</td>' +
      '<td style="padding:6px 10px;font-size:.82rem;text-align:right;color:#2563eb">' + (t.leidos||0).toLocaleString('es-CO') + '</td>' +
      '<td style="padding:6px 10px;font-size:.82rem;text-align:right;color:#ef4444">' + (t.fallidos||0).toLocaleString('es-CO') + '</td>' +
    '</tr>';
  }).join('');

  wrap.innerHTML =
    '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:16px;margin-top:24px">' +
      '<div style="font-weight:700;color:#1a2332;font-size:.92rem;margin-bottom:14px">📈 Tendencia por ' +
        (granularidad === 'mes' ? 'mes' : (granularidad === 'semana' ? 'semana' : 'día')) + '</div>' +

      (conv.length ? (
        '<div style="margin-bottom:18px">' +
          '<div style="font-size:.78rem;color:#475569;margin-bottom:10px">' +
            '<span style="display:inline-block;width:10px;height:10px;background:#22c55e;border-radius:2px;margin-right:4px"></span> Mensajes recibidos &nbsp; ' +
            '<span style="display:inline-block;width:10px;height:10px;background:#4f46e5;border-radius:2px;margin-right:4px"></span> Respuestas IA' +
          '</div>' +
          '<div style="display:flex;gap:4px;overflow-x:auto;padding-bottom:8px">' + barrasConv + '</div>' +
        '</div>'
      ) : '') +

      (dif.length ? (
        '<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse">' +
          '<thead><tr style="background:#f8fafc;font-size:.72rem;color:#94a3b8;text-transform:uppercase">' +
            '<th style="padding:6px 10px;text-align:left">Período</th>' +
            '<th style="padding:6px 10px;text-align:center">Campañas</th>' +
            '<th style="padding:6px 10px;text-align:right">Enviados</th>' +
            '<th style="padding:6px 10px;text-align:right">Entregados</th>' +
            '<th style="padding:6px 10px;text-align:right">Leídos</th>' +
            '<th style="padding:6px 10px;text-align:right">Fallidos</th>' +
          '</tr></thead><tbody>' + filasDif + '</tbody>' +
        '</table></div>'
      ) : '') +
    '</div>';
}

function mkCard(ic, lbl, val, sub) {
  // val puede ser número o string formateado (ej: "USD $1.23", "—", "5x")
  var valStr = (typeof val === 'number')
    ? val.toLocaleString('es-CO')
    : String(val === null || val === undefined ? '—' : val);
  return '<div class="card">'
    + '<div class="card-ic">' + ic + '</div>'
    + '<div class="card-lbl">' + he(lbl) + '</div>'
    + '<div class="card-val">' + valStr + '</div>'
    + '<div class="card-sub">' + he(sub) + '</div>'
    + '</div>';
}

/* ══════════════════════════════════════════════════════
   CONFIGURACIÓN — tabs + gestión interactiva
   ══════════════════════════════════════════════════════ */
function cfgTab(id, el) {
  document.querySelectorAll('.cfg-tab').forEach(function(t) { t.classList.remove('active'); });
  document.querySelectorAll('.cfg-pane').forEach(function(p) { p.classList.remove('active'); });
  el.classList.add('active');
  var pane = document.getElementById('cfg-pane-' + id);
  if (pane) pane.classList.add('active');
}

/* ── Helpers de estado ── */
function _setCfgPill(pillId, state) {
  var pill = document.getElementById(pillId);
  if (!pill) return;
  pill.className = 'cfg-status-pill';
  if (state === 'ok')      { pill.classList.add('cfg-pill-connected'); pill.textContent = '✅ Conectado'; }
  else if (state === 'error') { pill.classList.add('cfg-pill-error');  pill.textContent = '⚠️ Sin conectar'; }
  else                     { pill.classList.add('cfg-pill-pending');   pill.textContent = 'Verificando…'; }
}

function _setCfgOvStatus(ovId, state, txt) {
  var el = document.getElementById(ovId);
  if (!el) return;
  el.className = 'cfg-ov-status';
  if (state === 'ok')      { el.classList.add('cfg-pill-connected'); }
  else if (state === 'error') { el.classList.add('cfg-pill-error'); }
  else                     { el.classList.add('cfg-pill-pend'); }
  el.textContent = txt || (state === 'ok' ? '✅ Conectado' : state === 'error' ? '⚠️ Sin configurar' : 'Verificando…');
}

function _setCfgFieldStatus(statusId, state) {
  var el = document.getElementById(statusId);
  if (!el) return;
  if (state === 'ok')    { el.textContent = '✓'; el.style.color = '#2e7d32'; el.style.fontWeight = '700'; }
  else if (state === 'err') { el.textContent = '✗'; el.style.color = '#c62828'; el.style.fontWeight = '700'; }
  else                   { el.textContent = ''; }
}

function _showCfgResult(divId, ok, msg) {
  var div = document.getElementById(divId);
  if (!div) return;
  div.style.display = '';
  div.className = 'cfg-test-result';
  if (ok === true)        div.classList.add('cfg-test-ok');
  else if (ok === false)  div.classList.add('cfg-test-err');
  div.textContent = msg || '';
  // Auto-ocultar tras 8 s si hay resultado definitivo
  if (ok !== null) {
    var _msg = msg;
    setTimeout(function() { if (div.textContent === _msg) div.style.display = 'none'; }, 8000);
  }
}

/* ── toggleHelp: muestra / oculta caja de ayuda inline ── */
function toggleHelp(id) {
  var box = document.getElementById(id);
  if (box) box.classList.toggle('open');
}

/* ── togglePwd: alterna visibilidad del campo contraseña ── */
function togglePwd(inputId, btn) {
  var inp = document.getElementById(inputId);
  if (!inp) return;
  if (inp.type === 'password') { inp.type = 'text';     btn.textContent = '🙈'; }
  else                         { inp.type = 'password'; btn.textContent = '👁'; }
}

/* ══════════════════════════════════════════════════════════════
   ESTADO DEL SISTEMA — diagnóstico en tiempo real de tokens
   ══════════════════════════════════════════════════════════════ */
function _setSistemaEstado(servicio, estado, mensaje, detalle, sugerencia) {
  /* estado: 'ok' | 'warn' | 'error' | 'loading' */
  var dot = document.getElementById('dot-' + servicio);
  var msg = document.getElementById('msg-' + servicio);
  var det = document.getElementById('det-' + servicio);
  if (!dot || !msg) return;
  dot.className = 'sistema-dot ' + estado;
  msg.textContent = mensaje || '';
  if (det) {
    var detHtml = detalle || '';
    if (sugerencia) {
      detHtml += '<div class="sistema-sugerencia">💡 ' + he(sugerencia) + '</div>';
    }
    det.innerHTML = detHtml;
  }
}

async function _verificarCAPI() {
  _setSistemaEstado('capi', 'loading', 'Verificando…', '');
  try {
    var r = await fetch('/inbox/api/sistema/capi-status', {credentials:'include'});
    var d = await r.json();
    if (d.estado === 'ok_activo' || d.estado === 'ok') {
      var detalle_capi = 'Pixel ID: ' + he(d.pixel_id_partial || '—');
      if (d.eventos_recibidos != null) {
        detalle_capi += '<br>Eventos aceptados en el test: ' + d.eventos_recibidos;
      }
      _setSistemaEstado('capi', 'ok',
        d.mensaje || 'Token válido y activo',
        detalle_capi);
    } else if (d.estado === 'ok_inactivo_reciente') {
      _setSistemaEstado('capi', 'ok',
        d.mensaje || 'Token válido',
        'Pixel: ' + he(d.pixel_id_partial || '—'));
    } else if (d.estado === 'ok_sin_actividad') {
      _setSistemaEstado('capi', 'warn',
        d.mensaje || 'Sin actividad reciente',
        'Pixel: ' + he(d.pixel_id_partial || '—'));
    } else if (d.estado === 'no_configurado') {
      _setSistemaEstado('capi', 'warn',
        'No configurado (opcional)',
        'CAPI mejora la atribución en Facebook Ads pero no es necesario para Andrea.');
    } else if (d.estado === 'token_invalido') {
      _setSistemaEstado('capi', 'error',
        '❌ Token inválido o expirado',
        he(d.mensaje || ''), d.sugerencia);
    } else if (d.estado === 'sin_acceso_pixel') {
      _setSistemaEstado('capi', 'error',
        '❌ Token sin acceso al pixel',
        he(d.mensaje || ''), d.sugerencia);
    } else {
      _setSistemaEstado('capi', 'warn', d.mensaje || 'Estado desconocido', '');
    }
  } catch(e) {
    _setSistemaEstado('capi', 'error', 'Error de red verificando CAPI', he(String(e)));
  }
}

async function _verificarWhatsApp() {
  _setSistemaEstado('whatsapp', 'loading', 'Verificando…', '');
  try {
    var r = await fetch('/inbox/api/config/test/meta', {
      method:'POST', credentials:'include',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({})
    });
    var d = await r.json();
    if (d.ok) {
      _setSistemaEstado('whatsapp', 'ok',
        '✅ Token válido y activo',
        he(d.detalle || d.message || 'Conexión con Meta Cloud API funcionando'));
    } else {
      var sug = '';
      if ((d.error || '').toLowerCase().includes('invalid') ||
          (d.error || '').toLowerCase().includes('expired') ||
          (d.error || '').toLowerCase().includes('190')) {
        sug = 'Renueva el token: Meta Business Manager → Usuarios del sistema → equora-andreabot → Generar token (selecciona la app de WhatsApp con permisos whatsapp_business_messaging y whatsapp_business_management, expiración "Nunca").';
      }
      _setSistemaEstado('whatsapp', 'error',
        '❌ ' + (d.error || 'Error al verificar token'),
        '', sug);
    }
  } catch(e) {
    _setSistemaEstado('whatsapp', 'error', 'Error de red', he(String(e)));
  }
}

async function _verificarCatalogo() {
  _setSistemaEstado('catalogo', 'loading', 'Verificando…', '');
  try {
    var r = await fetch('/inbox/api/sistema/fallas-catalogo', {credentials:'include'});
    var d = await r.json();
    var total = d.total_24h || 0;
    if (total === 0) {
      _setSistemaEstado('catalogo', 'ok',
        '✅ Catálogo nativo funcionando',
        'Sin fallas registradas en las últimas 24 horas');
    } else if (total < 5) {
      var tipos = Object.keys(d.por_tipo || {}).join(', ');
      _setSistemaEstado('catalogo', 'warn',
        '⚠️ ' + total + ' falla(s) en 24h',
        'Tipos: ' + he(tipos),
        'Revisa los logs o reabre el panel para diagnosticar. Cliente puede haber recibido el fallback web.');
    } else {
      var tipos2 = Object.keys(d.por_tipo || {}).join(', ');
      _setSistemaEstado('catalogo', 'error',
        '❌ ' + total + ' fallas en 24h — problema sostenido',
        'Tipos: ' + he(tipos2),
        'Verifica META_CATALOG_ID y que los SKUs estén sincronizados Shopify → Facebook Catalog.');
    }
  } catch(e) {
    _setSistemaEstado('catalogo', 'warn', 'No pude verificar', he(String(e)));
  }
}

async function _verificarShopify() {
  _setSistemaEstado('shopify', 'loading', 'Verificando…', '');
  try {
    var r = await fetch('/inbox/api/config/test/shopify', {
      method:'POST', credentials:'include',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({})
    });
    var d = await r.json();
    if (d.ok) {
      _setSistemaEstado('shopify', 'ok',
        '✅ Conexión Shopify activa',
        he(d.detalle || d.message || 'Storefront API respondiendo'));
    } else {
      _setSistemaEstado('shopify', 'warn',
        '⚠️ ' + (d.error || 'No configurado'),
        '');
    }
  } catch(e) {
    _setSistemaEstado('shopify', 'warn', 'No verificable', he(String(e)));
  }
}

async function cargarEstadoSistema() {
  // Ejecutar las 4 verificaciones en paralelo para velocidad
  await Promise.all([
    _verificarWhatsApp(),
    _verificarCAPI(),
    _verificarCatalogo(),
    _verificarShopify(),
  ]);
}

/* ── cargarConfiguracion: pide GET /inbox/api/config y rellena indicadores ── */
async function cargarConfiguracion() {
  // Mapeo campo_db → id del <input> / <select>
  var fieldMap = {
    META_ACCESS_TOKEN:    'cfg-meta-token',
    META_PHONE_NUMBER_ID: 'cfg-meta-pid',
    META_WABA_ID:         'cfg-meta-waba',
    META_VERIFY_TOKEN:    'cfg-meta-verify',
    ANTHROPIC_API_KEY:       'cfg-ant-key',
    AI_MODEL:                'cfg-ant-model',
    SHOPIFY_STORE:           'cfg-sh-domain',
    SHOPIFY_STOREFRONT_TOKEN:'cfg-sh-sftoken',
    SHOPIFY_WEBHOOK_SECRET:  'cfg-sh-whsec',
    PEDIDO_MINIMO:           'cfg-pedido-min',
    PEDIDO_MIN_MSG:          'cfg-pedido-msg',
  };

  try {
    var r = await fetch('/inbox/api/config', {credentials:'include'});
    var d = await r.json();

    Object.keys(d).forEach(function(key) {
      var info    = d[key];
      var fieldId = fieldMap[key];
      var inp     = fieldId ? document.getElementById(fieldId) : null;

      // Indicador ✓ / ✗ junto al campo
      _setCfgFieldStatus('st-' + key, info.configurado ? 'ok' : '');

      if (!inp) return;

      if (info.configurado) {
        if (inp.tagName === 'SELECT') {
          // Para el selector de modelo mostramos el valor real
          if (info.display) inp.value = info.display;
        } else if (inp.type === 'password') {
          // Secretos: solo actualizar el placeholder para señalar que ya está guardado
          inp.placeholder = '••••••••  (guardado)';
          // NO rellenamos el input — que el usuario escriba el nuevo valor si quiere cambiarlo
        } else {
          // Campos de texto plano (dominio, ID, etc.): mostrar valor real
          inp.value = info.display || '';
        }
      }
    });

    // ── Calcular estado por servicio ──
    var ok = function(k) { return d[k] && d[k].configurado; };
    var metaOk  = ok('META_ACCESS_TOKEN') && ok('META_PHONE_NUMBER_ID');
    var aiOk    = ok('ANTHROPIC_API_KEY');
    var shopOk  = ok('SHOPIFY_STOREFRONT_TOKEN') && ok('SHOPIFY_STORE');

    _setCfgPill('pill-meta',       metaOk ? 'ok' : 'error');
    _setCfgPill('pill-anthropic',  aiOk   ? 'ok' : 'error');
    _setCfgPill('pill-shopify',    shopOk ? 'ok' : 'error');
    _setCfgOvStatus('ov-meta-status',    metaOk ? 'ok' : 'error');
    _setCfgOvStatus('ov-ai-status',      aiOk   ? 'ok' : 'error');
    _setCfgOvStatus('ov-shopify-status', shopOk ? 'ok' : 'error');

  } catch(e) {
    console.error('Error cargando configuración:', e);
  }
}

/* ── guardarConfig: POST /inbox/api/config/save con campos del servicio ── */
async function guardarConfig(service) {
  var payload    = {};
  var resultId   = 'cfg-' + service + '-result';

  if (service === 'meta') {
    var t = (document.getElementById('cfg-meta-token').value  || '').trim();
    var p = (document.getElementById('cfg-meta-pid').value    || '').trim();
    var w = (document.getElementById('cfg-meta-waba').value   || '').trim();
    var v = (document.getElementById('cfg-meta-verify').value || '').trim();
    if (t) payload.META_ACCESS_TOKEN    = t;
    if (p) payload.META_PHONE_NUMBER_ID = p;
    if (w) payload.META_WABA_ID         = w;
    if (v) payload.META_VERIFY_TOKEN    = v;
  } else if (service === 'anthropic') {
    var k = (document.getElementById('cfg-ant-key').value   || '').trim();
    var m = (document.getElementById('cfg-ant-model').value || '').trim();
    if (k) payload.ANTHROPIC_API_KEY = k;
    if (m) payload.AI_MODEL          = m;
  } else if (service === 'shopify') {
    var sd = (document.getElementById('cfg-sh-domain').value  || '').trim();
    var sf = (document.getElementById('cfg-sh-sftoken').value || '').trim();
    var sw = (document.getElementById('cfg-sh-whsec').value   || '').trim();
    if (sd) payload.SHOPIFY_STORE            = sd;
    if (sf) payload.SHOPIFY_STOREFRONT_TOKEN = sf;
    if (sw) payload.SHOPIFY_WEBHOOK_SECRET   = sw;
  } else if (service === 'reglas') {
    var pm  = (document.getElementById('cfg-pedido-min').value || '').trim();
    var pmm = (document.getElementById('cfg-pedido-msg').value || '').trim();
    // Pedido mínimo: enviar siempre (incluso vacío para que se guarde 0)
    payload.PEDIDO_MINIMO  = pm || '0';
    payload.PEDIDO_MIN_MSG = pmm;
  }

  if (!Object.keys(payload).length) {
    _showCfgResult(resultId, false, 'No hay valores para guardar — escribe al menos un campo.');
    return;
  }

  // Feedback visual en el botón
  var btnId  = service === 'anthropic' ? 'card-anthropic' : 'card-' + service;
  var btnEl  = document.querySelector('#' + btnId + ' .btn-primary');
  if (btnEl) { btnEl.disabled = true; btnEl.textContent = 'Guardando…'; }

  try {
    var r = await fetch('/inbox/api/config/save', {
      method: 'POST', credentials: 'include',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    var d = await r.json();
    if (d.ok) {
      var n = d.saved ? d.saved.length : 0;
      _showCfgResult(resultId, true, '✅ Guardado correctamente (' + n + ' campo' + (n !== 1 ? 's' : '') + ')');
      await cargarConfiguracion();   // refrescar indicadores
    } else {
      _showCfgResult(resultId, false, '⚠️ Error al guardar — intenta de nuevo.');
    }
  } catch(e) {
    _showCfgResult(resultId, false, 'Error de red: ' + String(e));
  } finally {
    if (btnEl) { btnEl.disabled = false; btnEl.textContent = '💾 Guardar'; }
  }
}

/* ── testConexion: POST /inbox/api/config/test/{service} ── */
async function testConexion(service) {
  var payload  = {};
  var resultId = 'cfg-' + service + '-result';
  var pillId   = service === 'anthropic' ? 'pill-anthropic' : 'pill-' + service;
  var ovId     = service === 'meta' ? 'ov-meta-status'
               : service === 'anthropic' ? 'ov-ai-status' : 'ov-shopify-status';

  // Pasar los valores del form (si están vacíos, el servidor usará lo que tenga en BD / env)
  if (service === 'meta') {
    var t = (document.getElementById('cfg-meta-token').value || '').trim();
    var p = (document.getElementById('cfg-meta-pid').value   || '').trim();
    if (t) payload.META_ACCESS_TOKEN    = t;
    if (p) payload.META_PHONE_NUMBER_ID = p;
  } else if (service === 'anthropic') {
    var k = (document.getElementById('cfg-ant-key').value   || '').trim();
    var m = (document.getElementById('cfg-ant-model').value || '').trim();
    if (k) payload.ANTHROPIC_API_KEY = k;
    if (m) payload.AI_MODEL          = m;
  } else if (service === 'shopify') {
    var sd = (document.getElementById('cfg-sh-domain').value  || '').trim();
    var sf = (document.getElementById('cfg-sh-sftoken').value || '').trim();
    if (sd) payload.SHOPIFY_STORE            = sd;
    if (sf) payload.SHOPIFY_STOREFRONT_TOKEN = sf;
  }

  _showCfgResult(resultId, null, '🔄 Probando conexión…');
  _setCfgPill(pillId, 'pending');

  // Deshabilitar botón mientras prueba
  var btnTest = document.querySelector('#' + (service === 'anthropic' ? 'card-anthropic' : 'card-' + service) + ' .btn-secondary');
  if (btnTest) { btnTest.disabled = true; btnTest.textContent = '🔄 Probando…'; }

  try {
    var r = await fetch('/inbox/api/config/test/' + service, {
      method: 'POST', credentials: 'include',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    var d = await r.json();
    if (d.ok) {
      _showCfgResult(resultId, true,  d.msg   || '✅ Conexión exitosa');
      _setCfgPill(pillId, 'ok');
      _setCfgOvStatus(ovId, 'ok');
    } else {
      _showCfgResult(resultId, false, d.error || '⚠️ No se pudo conectar');
      _setCfgPill(pillId, 'error');
      _setCfgOvStatus(ovId, 'error');
    }
  } catch(e) {
    _showCfgResult(resultId, false, 'Error de red: ' + String(e));
    _setCfgPill(pillId, 'error');
    _setCfgOvStatus(ovId, 'error');
  } finally {
    if (btnTest) { btnTest.disabled = false; btnTest.textContent = '🔌 Probar conexión'; }
  }
}

/* ══════════════════════════════════════════════════════
   PROMPT EDITOR  (Fase A + B)
   ══════════════════════════════════════════════════════ */

var _promptPropuesta = '';   // guarda la propuesta pendiente de Claude
var _activeModules   = {};   // estado actual de los módulos

/* ── Tipo de negocio ── */
function selBizType(el) {
  document.querySelectorAll('.biz-type-btn').forEach(function(b){ b.classList.remove('selected'); });
  el.classList.add('selected');
}

function _getBizType() {
  var sel = document.querySelector('.biz-type-btn.selected');
  return sel ? sel.getAttribute('data-type') : 'productos';
}

function _setBizType(type) {
  document.querySelectorAll('.biz-type-btn').forEach(function(b){
    b.classList.toggle('selected', b.getAttribute('data-type') === type);
  });
}

/* ── Toggles de módulos ── */
function onTogModule(key, chk) {
  _activeModules[key] = chk.checked;
  var card = document.getElementById('togcard-' + key);
  if (card) card.classList.toggle('active', chk.checked);
}

function _setModules(mods) {
  var keys = ['shopify_catalog', 'cart_orders', 'client_memory', 'campaign_context'];
  keys.forEach(function(k) {
    var val = (k in mods) ? mods[k] : true;  // default true
    _activeModules[k] = val;
    var chk  = document.getElementById('tog-' + k);
    var card = document.getElementById('togcard-' + k);
    if (chk)  chk.checked = val;
    if (card) card.classList.toggle('active', val);
  });
}

function _getModules() {
  return Object.assign({}, _activeModules);
}

/* ── cargarPrompt: llamado cuando el usuario abre la pestaña Prompt ── */
async function cargarPrompt() {
  try {
    var r = await fetch('/inbox/api/prompt', {credentials:'include'});
    var d = await r.json();

    // Rellenar textarea con el prompt actual
    var ta = document.getElementById('prompt-textarea');
    if (ta) {
      ta.value = d.prompt || '';
      _actualizarContadorPrompt();
    }

    // Indicar fuente
    var fuente = document.getElementById('prompt-fuente');
    if (fuente) fuente.textContent = d.fuente === 'db' ? '🗄 Guardado en BD' : '📄 Desde archivo';

    // Rellenar tabla de variables
    _renderVarsTable(d.business_vars || {});

    // Tipo de negocio
    _setBizType(d.business_type || 'productos');

    // Módulos activos
    _setModules(d.active_modules || {});

  } catch(e) {
    console.error('Error cargando prompt:', e);
  }
}

/* ── Contador de caracteres ── */
function _actualizarContadorPrompt() {
  var ta = document.getElementById('prompt-textarea');
  var el = document.getElementById('prompt-chars');
  if (ta && el) el.textContent = ta.value.length.toLocaleString('es-CO') + ' caracteres';
}
document.addEventListener('DOMContentLoaded', function() {
  var ta = document.getElementById('prompt-textarea');
  if (ta) ta.addEventListener('input', _actualizarContadorPrompt);
});

/* ── Tabla de variables ── */
function _renderVarsTable(vars) {
  var tbody = document.getElementById('vars-tbody');
  if (!tbody) return;
  tbody.innerHTML = '';
  Object.keys(vars).forEach(function(k) {
    _agregarFilaVar(k, vars[k]);
  });
}

function _agregarFilaVar(key, val) {
  var tbody = document.getElementById('vars-tbody');
  if (!tbody) return;
  var tr = document.createElement('tr');
  tr.innerHTML =
    '<td><input class="vars-key-inp" value="' + he(key) + '" placeholder="NOMBRE_VAR" style="text-transform:uppercase" oninput="this.value=this.value.toUpperCase().replace(/\\s/g,\'_\')"></td>' +
    '<td><input class="vars-val-inp" value="' + he(val) + '" placeholder="Valor de la variable"></td>' +
    '<td><button class="vars-del-btn" onclick="this.closest(\'tr\').remove()" type="button" title="Eliminar">✕</button></td>';
  tbody.appendChild(tr);
}

function agregarVar() {
  _agregarFilaVar('', '');
  // Enfocar el nuevo campo
  var inputs = document.querySelectorAll('#vars-tbody .vars-key-inp');
  if (inputs.length) inputs[inputs.length - 1].focus();
}

function _recolectarVars() {
  var vars = {};
  document.querySelectorAll('#vars-tbody tr').forEach(function(tr) {
    var key = (tr.querySelector('.vars-key-inp').value || '').trim().toUpperCase().replace(/\s/g,'_');
    var val = (tr.querySelector('.vars-val-inp').value || '').trim();
    if (key && val) vars[key] = val;
  });
  return vars;
}

/* ── Guardar prompt + variables + tipo + módulos ── */
async function guardarPrompt() {
  var prompt   = (document.getElementById('prompt-textarea').value || '').trim();
  var vars     = _recolectarVars();
  var bizType  = _getBizType();
  var modules  = _getModules();
  var btn      = document.getElementById('btn-save-prompt');

  if (!prompt) { _showCfgResult('prompt-save-result', false, 'El prompt no puede estar vacío'); return; }
  if (btn) { btn.disabled = true; btn.textContent = 'Guardando…'; }

  try {
    var r = await fetch('/inbox/api/prompt/save', {
      method: 'POST', credentials: 'include',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        prompt:         prompt,
        business_vars:  vars,
        business_type:  bizType,
        active_modules: modules
      })
    });
    var d = await r.json();
    if (d.ok) {
      _showCfgResult('prompt-save-result', true, '✅ Guardado. El agente usará este prompt desde ahora.');
      document.getElementById('prompt-fuente').textContent = '🗄 Guardado en BD';
    } else {
      _showCfgResult('prompt-save-result', false, 'Error al guardar');
    }
  } catch(e) {
    _showCfgResult('prompt-save-result', false, 'Error de red: ' + String(e));
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '💾 Guardar'; }
  }
}

/* ══════════════════════════════════════════════════════
   ADJUNTAR IMÁGENES — zona de adjuntos del asistente IA
   ══════════════════════════════════════════════════════ */
var _attachedImages = [];   // [{dataUrl, mediaType}]

function _imgToBase64(file) {
  return new Promise(function(resolve, reject) {
    var reader = new FileReader();
    reader.onload  = function(e) { resolve(e.target.result); };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function _renderThumbs() {
  var container = document.getElementById('img-thumbs');
  if (!container) return;
  container.innerHTML = '';
  _attachedImages.forEach(function(img, idx) {
    var wrap = document.createElement('div');
    wrap.className = 'img-thumb';
    var el = document.createElement('img');
    el.src = img.dataUrl;
    el.alt = 'imagen ' + (idx+1);
    var del = document.createElement('button');
    del.className = 'img-thumb-del';
    del.type = 'button';
    del.title = 'Eliminar';
    del.textContent = '×';
    del.onclick = function() { _attachedImages.splice(idx,1); _renderThumbs(); };
    wrap.appendChild(el);
    wrap.appendChild(del);
    container.appendChild(wrap);
  });
}

async function _addImageFiles(files) {
  for (var i = 0; i < files.length; i++) {
    var file = files[i];
    if (!file.type.startsWith('image/')) continue;
    if (_attachedImages.length >= 5) { alert('Máximo 5 imágenes por consulta.'); break; }
    var dataUrl = await _imgToBase64(file);
    _attachedImages.push({ dataUrl: dataUrl, mediaType: file.type });
  }
  _renderThumbs();
}

/* Inicializar listeners de adjuntos (llamado al cargar la sección de config) */
function _initImgAttach() {
  var fileInput = document.getElementById('img-file-input');
  var zone      = document.getElementById('img-attach-zone');
  var ta        = document.getElementById('prompt-instruccion');
  if (!fileInput || !zone || !ta) return;
  if (fileInput._initDone) return;
  fileInput._initDone = true;

  /* Selector de archivo */
  fileInput.addEventListener('change', function() {
    _addImageFiles(fileInput.files);
    fileInput.value = '';
  });

  /* Pegar con Ctrl+V en el textarea de instrucción */
  ta.addEventListener('paste', function(e) {
    var items = (e.clipboardData || {}).items || [];
    var hasImg = false;
    for (var i = 0; i < items.length; i++) {
      if (items[i].type.startsWith('image/')) {
        hasImg = true;
        _addImageFiles([items[i].getAsFile()]);
      }
    }
    if (hasImg) e.preventDefault();
  });

  /* Drag & drop sobre la zona */
  zone.addEventListener('dragover', function(e) {
    e.preventDefault();
    zone.classList.add('drag-over');
  });
  zone.addEventListener('dragleave', function() {
    zone.classList.remove('drag-over');
  });
  zone.addEventListener('drop', function(e) {
    e.preventDefault();
    zone.classList.remove('drag-over');
    _addImageFiles(e.dataTransfer.files);
  });
}

/* Inicializar listeners al cargar — funcionan aunque el elemento esté oculto */
document.addEventListener('DOMContentLoaded', _initImgAttach);

/* ── Mejorar con IA ── */
async function mejorarPrompt() {
  var prompt      = (document.getElementById('prompt-textarea').value || '').trim();
  var instruccion = (document.getElementById('prompt-instruccion').value || '').trim();
  var vars        = _recolectarVars();
  var btn         = document.getElementById('btn-improve');

  if (!prompt)      { alert('El prompt está vacío. Escribe o carga el prompt primero.'); return; }
  if (!instruccion) { alert('Cuéntame qué quieres mejorar.'); return; }

  btn.disabled = true;
  btn.innerHTML = '⏳ Mejorando…';
  document.getElementById('prompt-propuesta-wrap').style.display = 'none';
  document.getElementById('prompt-diff-wrap').style.display = 'none';

  /* Preparar imágenes para el payload (base64 sin el prefijo data:...) */
  var imagenes = _attachedImages.map(function(img) {
    var parts = img.dataUrl.split(',');
    return { media_type: img.mediaType, data: parts[1] || '' };
  });

  try {
    var r = await fetch('/inbox/api/prompt/improve', {
      method: 'POST', credentials: 'include',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        prompt: prompt,
        instruccion: instruccion,
        business_vars: vars,
        imagenes: imagenes
      })
    });
    var d = await r.json();
    if (d.ok) {
      _promptPropuesta = d.improved_prompt;
      document.getElementById('prompt-propuesta').value = _promptPropuesta;
      document.getElementById('prompt-propuesta-wrap').style.display = '';
      /* Limpiar imágenes tras enviar */
      _attachedImages = [];
      _renderThumbs();
    } else {
      alert('Error: ' + (d.error || 'No se pudo generar'));
    }
  } catch(e) {
    alert('Error de red: ' + String(e));
  } finally {
    btn.disabled = false;
    btn.innerHTML = '✨ Mejorar con IA';
  }
}

/* ── Aplicar propuesta al editor ── */
function aplicarPropuesta() {
  if (!_promptPropuesta) return;
  document.getElementById('prompt-textarea').value = _promptPropuesta;
  _actualizarContadorPrompt();
  document.getElementById('prompt-propuesta-wrap').style.display = 'none';
  document.getElementById('prompt-diff-wrap').style.display = 'none';
  document.getElementById('prompt-instruccion').value = '';
  _promptPropuesta = '';
}

function descartarPropuesta() {
  document.getElementById('prompt-propuesta-wrap').style.display = 'none';
  document.getElementById('prompt-diff-wrap').style.display = 'none';
  _promptPropuesta = '';
}

/* ── Ver diferencias (diff simple línea a línea) ── */
function verDiff() {
  var original = (document.getElementById('prompt-textarea').value || '').split('\n');
  var propuesta = (_promptPropuesta || '').split('\n');
  var maxLen = Math.max(original.length, propuesta.length);
  var html = '';

  for (var i = 0; i < maxLen; i++) {
    var lineO = original[i] !== undefined ? original[i] : null;
    var lineP = propuesta[i] !== undefined ? propuesta[i] : null;
    if (lineO === lineP) {
      html += '<span>' + he(lineO || '') + '\n</span>';
    } else {
      if (lineO !== null) html += '<span class="diff-del">- ' + he(lineO) + '\n</span>';
      if (lineP !== null) html += '<span class="diff-add">+ ' + he(lineP) + '\n</span>';
    }
  }

  document.getElementById('prompt-diff-content').innerHTML = html;
  document.getElementById('prompt-propuesta-wrap').style.display = 'none';
  document.getElementById('prompt-diff-wrap').style.display = '';
}

function cerrarDiff() {
  document.getElementById('prompt-diff-wrap').style.display = 'none';
  document.getElementById('prompt-propuesta-wrap').style.display = _promptPropuesta ? '' : 'none';
}

/* ══════════════════════════════════════════════════════
   CHAT DE PRUEBA  (Fase C)
   ══════════════════════════════════════════════════════ */

var _chatTestIniciado = false;

/* ── iniciarChatTest: llamado al abrir la pestaña Probar ── */
async function iniciarChatTest() {
  if (_chatTestIniciado) return;
  _chatTestIniciado = true;
  await _cargarHistorialChat();
}

async function _cargarHistorialChat() {
  try {
    var r = await fetch('/inbox/api/chat/test/history', {credentials:'include'});
    var d = await r.json();
    var msgs = d.mensajes || [];
    var box = document.getElementById('chat-messages');
    if (!box) return;
    // Limpiar (excepto el primer div de "Inicio")
    while (box.children.length > 1) box.removeChild(box.lastChild);
    msgs.forEach(function(m) {
      _appendMsg(m.role, m.content, m.timestamp);
    });
    _scrollChatBottom();
  } catch(e) {
    console.error('Error cargando historial de prueba:', e);
  }
}

function _appendMsg(role, text, ts) {
  var box = document.getElementById('chat-messages');
  if (!box) return;
  var div = document.createElement('div');
  div.className = 'chat-msg ' + (role === 'user' ? 'user' : 'assistant');
  var time = '';
  if (ts) {
    try {
      var d = new Date(ts);
      time = d.toLocaleTimeString('es-CO', {hour:'2-digit', minute:'2-digit'});
    } catch(e) {}
  }
  div.innerHTML = _nl2br(he(text)) +
    (time ? '<div class="chat-msg-time">' + time + '</div>' : '');
  box.appendChild(div);
}

function _appendTyping() {
  var box = document.getElementById('chat-messages');
  if (!box) return null;
  var div = document.createElement('div');
  div.className = 'chat-typing';
  div.id = 'chat-typing-indicator';
  div.innerHTML = '<span></span><span></span><span></span>';
  box.appendChild(div);
  _scrollChatBottom();
  return div;
}

function _scrollChatBottom() {
  var box = document.getElementById('chat-messages');
  if (box) box.scrollTop = box.scrollHeight;
}

function _nl2br(str) {
  return str.replace(/\n/g, '<br>');
}

async function enviarMsgTest() {
  var inp  = document.getElementById('chat-inp');
  var btn  = document.getElementById('chat-send-btn');
  var texto = (inp ? inp.value : '').trim();
  if (!texto) return;

  inp.value = '';
  inp.style.height = 'auto';

  // Mostrar mensaje del usuario
  var now = new Date().toISOString();
  _appendMsg('user', texto, now);
  _scrollChatBottom();

  // Deshabilitar envío mientras espera
  if (btn) btn.disabled = true;

  // Mostrar indicador de typing
  var typingEl = _appendTyping();

  var errEl = document.getElementById('chat-test-error');
  if (errEl) errEl.style.display = 'none';

  try {
    var r = await fetch('/inbox/api/chat/test', {
      method: 'POST', credentials: 'include',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({mensaje: texto})
    });
    var d = await r.json();

    if (typingEl) typingEl.remove();

    if (d.ok) {
      _appendMsg('assistant', d.respuesta, new Date().toISOString());
      _scrollChatBottom();
    } else {
      if (errEl) {
        errEl.textContent = '⚠️ Error: ' + (d.error || 'No se pudo obtener respuesta');
        errEl.style.display = '';
      }
    }
  } catch(e) {
    if (typingEl) typingEl.remove();
    if (errEl) {
      errEl.textContent = '⚠️ Error de red: ' + String(e);
      errEl.style.display = '';
    }
  } finally {
    if (btn) btn.disabled = false;
    if (inp) inp.focus();
  }
}

async function limpiarChatTest() {
  if (!confirm('¿Borrar el historial del chat de prueba?')) return;
  try {
    await fetch('/inbox/api/chat/test/clear', {method:'DELETE', credentials:'include'});
    var box = document.getElementById('chat-messages');
    if (box) {
      while (box.children.length > 1) box.removeChild(box.lastChild);
    }
    _chatTestIniciado = false;  // permite recargar historial si vuelve a abrir la pestaña
  } catch(e) {
    alert('Error al limpiar: ' + String(e));
  }
}

/* ══════════════════════════════════════════════════════════════
   SPRINT 1 — SISTEMA DE ESCALACIONES
   ══════════════════════════════════════════════════════════════ */
var _escEstadoActual = 'sin_asignar';
var _escTicketActual = null;   // ticket seleccionado
var _escAgentId      = 1;      // agent_id activo (SaaS multi-tenant)
var _escUsuarioId    = 0;      // usuario_interno_id del agente logueado (si aplica)

/* ── Polling de badges (cada 15s) ────────────────────────── */
function _escActualizarBadges() {
  fetch('/inbox/api/tickets/counts?agent_id=' + _escAgentId, {credentials:'include'})
    .then(function(r){ return r.json(); })
    .then(function(d) {
      var total = d.total || 0;
      var badge = document.getElementById('esc-badge');
      if (badge) {
        if (total > 0) { badge.textContent = total; badge.style.display = ''; }
        else           { badge.style.display = 'none'; }
      }
      var estados = ['sin_asignar','activo','pendiente'];
      estados.forEach(function(est) {
        var el = document.getElementById('cnt-' + est);
        if (el) { el.textContent = d[est] || 0; el.style.display = d[est] ? '' : 'none'; }
      });
    }).catch(function(){});
}
// Iniciar polling al cargar
document.addEventListener('DOMContentLoaded', function() {
  _escActualizarBadges();
  setInterval(_escActualizarBadges, 15000);
});

/* ── Cargar lista de tickets ─────────────────────────────── */
async function escCargarLista() {
  _escActualizarBadges();
  var url = '/inbox/api/tickets?agent_id=' + _escAgentId + (
    _escEstadoActual ? '&estado=' + _escEstadoActual : ''
  );
  var lista = document.getElementById('esc-lista');
  lista.innerHTML = '<div style="padding:20px;text-align:center;color:#94a3b8;font-size:.84rem">Cargando…</div>';
  try {
    var r = await fetch(url, {credentials:'include'});
    var d = await r.json();
    _escRenderLista(d.tickets || []);
  } catch(e) {
    lista.innerHTML = '<div style="padding:16px;color:#ef4444;font-size:.82rem">Error al cargar</div>';
  }
}

function _escRenderLista(tickets) {
  var lista = document.getElementById('esc-lista');
  if (!tickets.length) {
    lista.innerHTML = '<div style="padding:24px;text-align:center;color:#94a3b8;font-size:.84rem">Sin conversaciones en esta categoría</div>';
    return;
  }
  lista.innerHTML = '';
  tickets.forEach(function(t) {
    var urgClass = 'esc-urg-' + (t.urgencia || 'normal');
    var tiempo = _escTiempoRelativo(t.actualizado_at);
    var card = document.createElement('div');
    card.className = 'esc-card' + (_escTicketActual && _escTicketActual.id === t.id ? ' selected' : '');
    card.onclick = function() { escSeleccionarTicket(t); };
    // Mostrar nombre + rol del último agente que gestionó (sea admin, supervisor o agente)
    var agenteLabel = '';
    if (t.agente_nombre) {
      var rol = t.agente_rol || '';
      var rolPretty = rol ? ' · ' + rol : '';
      agenteLabel = '<span>👤 ' + _escEsc(t.agente_nombre) + _escEsc(rolPretty) + '</span>';
    }
    card.innerHTML =
      '<div class="esc-card-nombre">' + _escEsc(t.nombre_cliente || t.telefono_cliente) + '</div>' +
      '<div class="esc-card-motivo">' + _escEsc(t.motivo) + '</div>' +
      '<div class="esc-card-meta">' +
        '<span class="esc-urg ' + urgClass + '">' + (t.urgencia||'normal') + '</span>' +
        agenteLabel +
        '<span style="margin-left:auto">' + tiempo + '</span>' +
      '</div>';
    lista.appendChild(card);
  });
}

function _escEsc(s) { return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function _escTiempoRelativo(iso) {
  if (!iso) return '';
  var diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60)  return 'hace ' + diff + 's';
  if (diff < 3600) return 'hace ' + Math.floor(diff/60) + 'min';
  return 'hace ' + Math.floor(diff/3600) + 'h';
}

/* ── Filtrar por estado ──────────────────────────────────── */
function escFiltrar(estado, btn) {
  _escEstadoActual = estado;
  document.querySelectorAll('.esc-tab').forEach(function(t){ t.classList.remove('active'); });
  btn.classList.add('active');
  escCargarLista();
}

/* ── Seleccionar ticket y cargar historial ───────────────── */
async function escSeleccionarTicket(ticket) {
  _escTicketActual = ticket;
  // Marcar card seleccionada
  document.querySelectorAll('.esc-card').forEach(function(c){ c.classList.remove('selected'); });
  event.currentTarget.classList.add('selected');

  // Mostrar detalle
  document.getElementById('esc-empty').style.display = 'none';
  var wrap = document.getElementById('esc-conv-wrap');
  wrap.style.display = 'flex';

  // Header — agregamos línea con agente + rol si existe
  var headerNombre = (ticket.nombre_cliente || ticket.telefono_cliente);
  if (ticket.agente_nombre) {
    var rolHdr = ticket.agente_rol ? ' · ' + ticket.agente_rol : '';
    headerNombre += '  ·  👤 ' + ticket.agente_nombre + rolHdr;
  }
  document.getElementById('esc-cliente-nombre').textContent = headerNombre;
  document.getElementById('esc-cliente-tel').textContent    = '+' + ticket.telefono_cliente;
  document.getElementById('esc-motivo').textContent         = ticket.motivo;
  document.getElementById('esc-contexto').textContent       = ticket.contexto || '—';

  var urgBadge = document.getElementById('esc-urgencia-badge');
  urgBadge.textContent = ticket.urgencia || 'normal';
  urgBadge.className = 'esc-urg esc-urg-' + (ticket.urgencia || 'normal');

  // Botones según estado
  var btnTomar     = document.getElementById('btn-esc-tomar');
  var btnPendiente = document.getElementById('btn-esc-pendiente');
  var btnResolver  = document.getElementById('btn-esc-resolver');
  var replyWrap    = document.getElementById('esc-reply-wrap');
  btnTomar.style.display     = (ticket.estado !== 'activo') ? '' : 'none';
  btnPendiente.style.display = (ticket.estado === 'activo') ? '' : 'none';
  btnResolver.style.display  = (ticket.estado === 'activo') ? '' : 'none';
  replyWrap.style.display    = (ticket.estado === 'activo') ? '' : 'none';

  // Historial
  var msgsEl = document.getElementById('esc-msgs');
  msgsEl.innerHTML = '<div style="color:#94a3b8;text-align:center;padding:12px;font-size:.82rem">Cargando historial…</div>';
  try {
    var r = await fetch('/inbox/api/tickets/' + ticket.id + '/historial', {credentials:'include'});
    var d = await r.json();
    _escRenderMensajes(d.mensajes || []);
  } catch(e) {
    msgsEl.innerHTML = '<div style="color:#ef4444;padding:12px">Error cargando mensajes</div>';
  }
}

function _escRenderMensajes(mensajes) {
  var el = document.getElementById('esc-msgs');
  el.innerHTML = '';
  if (!mensajes.length) {
    el.innerHTML = '<div style="color:#64748b;text-align:center;padding:12px;font-size:.82rem">Sin mensajes aún</div>';
    return;
  }
  mensajes.forEach(function(m) {
    var wrap = document.createElement('div');
    wrap.style.display = 'flex';
    wrap.style.flexDirection = 'column';
    wrap.style.alignItems = m.role === 'user' ? 'flex-end' : 'flex-start';

    var cls = m.role === 'user' ? 'esc-bbl-user' : (m.human ? 'esc-bbl-human' : 'esc-bbl-bot');
    var label = m.role !== 'user' ? (m.human ? '👤 Agente' : '🤖 Andrea') : '';

    // Renderizar usando la misma función del módulo Conversaciones — soporta
    // marcadores __MEDIA__ (imagen, video, doc, ubicación, producto) y
    // __ORDEN_CATALOGO__ (pedidos desde catálogo nativo).
    var bodyHtml = (typeof renderMediaOrText === 'function')
      ? renderMediaOrText(m.content)
      : _escEsc(m.content);

    wrap.innerHTML =
      (label ? '<div style="font-size:.68rem;color:#94a3b8;margin-bottom:2px;padding:0 4px">' + label + '</div>' : '') +
      '<div class="esc-bbl ' + cls + '">' + bodyHtml + '<div class="esc-bbl-ts">' +
        (m.timestamp ? new Date(m.timestamp).toLocaleTimeString('es-CO',{hour:'2-digit',minute:'2-digit'}) : '') +
      '</div></div>';
    el.appendChild(wrap);
  });
  el.scrollTop = el.scrollHeight;
}

/* ── Acciones sobre el ticket ───────────────────────────── */
async function escTomar() {
  if (!_escTicketActual) return;
  try {
    var r = await fetch('/inbox/api/tickets/' + _escTicketActual.id + '/tomar', {
      method:'POST', credentials:'include',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({agente_humano_id: _escUsuarioId || 0})
    });
    var d = await r.json();
    if (d.ok) {
      _escTicketActual = d.ticket;
      // Actualizar botones
      document.getElementById('btn-esc-tomar').style.display     = 'none';
      document.getElementById('btn-esc-pendiente').style.display = '';
      document.getElementById('btn-esc-resolver').style.display  = '';
      document.getElementById('esc-reply-wrap').style.display    = '';
      escCargarLista();
    }
  } catch(e) { alert('Error al tomar el ticket'); }
}

async function escPendiente() {
  if (!_escTicketActual) return;
  var r = await fetch('/inbox/api/tickets/' + _escTicketActual.id + '/pendiente', {
    method:'POST', credentials:'include'
  });
  var d = await r.json();
  if (d.ok) { _escTicketActual = d.ticket; escCargarLista(); escFiltrar('pendiente', document.querySelector('.esc-tab[data-est="pendiente"]')); }
}

async function escResolver() {
  if (!_escTicketActual) return;
  if (!confirm('¿Marcar como resuelto? El bot retomará automáticamente la conversación.')) return;
  var r = await fetch('/inbox/api/tickets/' + _escTicketActual.id + '/resolver?agent_id=' + _escAgentId, {
    method:'POST', credentials:'include'
  });
  var d = await r.json();
  if (d.ok) {
    _escTicketActual = null;
    document.getElementById('esc-empty').style.display = '';
    document.getElementById('esc-conv-wrap').style.display = 'none';
    escFiltrar('resuelto', document.querySelector('.esc-tab[data-est="resuelto"]') ||
      document.querySelector('.esc-tab'));
    escCargarLista();
  }
}

/* ── Enviar respuesta desde el panel ────────────────────── */
async function escEnviarRespuesta() {
  if (!_escTicketActual) return;
  var input = document.getElementById('esc-reply-input');
  var texto = (input.value || '').trim();
  if (!texto) return;
  input.value = '';
  try {
    // Reutilizar endpoint existente /inbox/api/responder
    var r = await fetch('/inbox/api/responder', {
      method:'POST', credentials:'include',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({telefono: _escTicketActual.telefono_cliente, mensaje: texto})
    });
    var d = await r.json();
    if (d.ok) {
      // Agregar burbuja local inmediatamente (sin esperar recarga)
      var msgs = document.getElementById('esc-msgs');
      var wrap = document.createElement('div');
      wrap.style.cssText = 'display:flex;flex-direction:column;align-items:flex-start';
      wrap.innerHTML = '<div style="font-size:.68rem;color:#94a3b8;margin-bottom:2px;padding:0 4px">👤 Agente</div>' +
        '<div class="esc-bbl esc-bbl-human">' + _escEsc(texto) +
        '<div class="esc-bbl-ts">' + new Date().toLocaleTimeString('es-CO',{hour:'2-digit',minute:'2-digit'}) + '</div></div>';
      msgs.appendChild(wrap);
      msgs.scrollTop = msgs.scrollHeight;
    } else {
      alert('Error enviando mensaje: ' + (d.error || 'desconocido'));
      input.value = texto;
    }
  } catch(e) { alert('Error de red'); input.value = texto; }
}

/* ══════════════════════════════════════════════════════════════
   SPRINT 1 — GESTIÓN DE EQUIPO (Usuarios Internos)
   ══════════════════════════════════════════════════════════════ */
async function cargarEquipo() {
  var wrap = document.getElementById('equipo-tabla');
  if (!wrap) return;
  wrap.innerHTML = '<div style="padding:14px 16px;color:#94a3b8;font-size:.85rem">Cargando…</div>';
  try {
    var r = await fetch('/inbox/api/equipo?agent_id=' + _escAgentId, {credentials:'include'});
    var d = await r.json();
    _renderTablaEquipo(d.equipo || []);
  } catch(e) {
    wrap.innerHTML = '<div style="padding:14px;color:#ef4444">Error cargando equipo</div>';
  }
}

function _renderTablaEquipo(equipo) {
  var wrap = document.getElementById('equipo-tabla');
  if (!equipo.length) {
    wrap.innerHTML = '<div style="padding:20px;text-align:center;color:#94a3b8;font-size:.85rem">' +
      'No hay agentes de soporte aún. Crea el primero con el botón "Nuevo agente".</div>';
    return;
  }
  var rolColor = {agente:'#e0f2fe;color:#0369a1', supervisor:'#fef3c7;color:#92400e', admin:'#f3e8ff;color:#7c3aed'};
  var filas = equipo.map(function(u) {
    var rc = rolColor[u.rol] || '#f1f5f9;color:#475569';
    var onlineColor = u.ultimo_ping_at && (Date.now() - new Date(u.ultimo_ping_at).getTime() < 60000)
      ? '#22c55e' : '#d1d5db';
    return '<tr style="border-bottom:1px solid #f1f5f9">' +
      '<td style="padding:10px 14px;font-weight:600;font-size:.86rem;color:#1a2332">' +
        '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + onlineColor + ';margin-right:6px"></span>' +
        _escEsc(u.nombre) + '</td>' +
      '<td style="padding:10px 14px;font-size:.83rem;color:#64748b">' + _escEsc(u.email) + '</td>' +
      '<td style="padding:10px 14px"><span style="background:' + rc + ';padding:2px 8px;border-radius:10px;font-size:.73rem;font-weight:700">' + u.rol + '</span></td>' +
      '<td style="padding:10px 14px"><span style="background:' + (u.activo ? '#dcfce7;color:#15803d' : '#fee2e2;color:#b91c1c') +
        ';padding:2px 8px;border-radius:10px;font-size:.73rem;font-weight:700">' + (u.activo ? 'Activo' : 'Inactivo') + '</span></td>' +
      '<td style="padding:10px 14px;font-size:.82rem">' +
        (u.activo ? '<button onclick="desactivarAgenteEquipo(' + u.id + ')" style="color:#ef4444;background:none;border:none;cursor:pointer;font-size:.78rem">Desactivar</button>' : '') +
      '</td></tr>';
  });
  wrap.innerHTML = '<table style="width:100%;border-collapse:collapse">' +
    '<thead><tr style="background:#f8fafc;font-size:.75rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.04em">' +
    '<th style="padding:8px 14px;text-align:left;font-weight:600">Nombre</th>' +
    '<th style="padding:8px 14px;text-align:left;font-weight:600">Email</th>' +
    '<th style="padding:8px 14px;text-align:left;font-weight:600">Rol</th>' +
    '<th style="padding:8px 14px;text-align:left;font-weight:600">Estado</th>' +
    '<th style="padding:8px 14px"></th>' +
    '</thead><tbody>' + filas.join('') + '</tbody></table>';
}

function mostrarFormNuevoAgente() {
  var wrap = document.getElementById('equipo-form-wrap');
  if (wrap) wrap.style.display = wrap.style.display === 'none' ? '' : 'none';
}

async function crearAgenteEquipo() {
  var nombre   = (document.getElementById('eq-nombre').value   || '').trim();
  var email    = (document.getElementById('eq-email').value    || '').trim();
  var password = (document.getElementById('eq-password').value || '').trim();
  var rol      = document.getElementById('eq-rol').value;
  var msg      = document.getElementById('equipo-form-msg');

  if (!nombre || !email || !password) { msg.innerHTML = '<span style="color:#ef4444">Completa todos los campos.</span>'; return; }
  if (password.length < 6) { msg.innerHTML = '<span style="color:#ef4444">La contraseña debe tener al menos 6 caracteres.</span>'; return; }

  msg.innerHTML = 'Creando…';
  try {
    var r = await fetch('/inbox/api/equipo?agent_id=' + _escAgentId, {
      method:'POST', credentials:'include',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({nombre, email, password, rol})
    });
    var d = await r.json();
    if (d.ok) {
      msg.innerHTML = '<span style="color:#16a34a">✅ Agente creado correctamente.</span>';
      document.getElementById('eq-nombre').value = '';
      document.getElementById('eq-email').value = '';
      document.getElementById('eq-password').value = '';
      cargarEquipo();
    } else {
      msg.innerHTML = '<span style="color:#ef4444">' + (d.error || 'Error') + '</span>';
    }
  } catch(e) {
    msg.innerHTML = '<span style="color:#ef4444">Error de red.</span>';
  }
}

async function desactivarAgenteEquipo(uid) {
  if (!confirm('¿Desactivar este agente? No podrá iniciar sesión.')) return;
  var r = await fetch('/inbox/api/equipo/' + uid, {method:'DELETE', credentials:'include'});
  var d = await r.json();
  if (d.ok) cargarEquipo();
  else alert('Error al desactivar');
}

/* ══════════════════════════════════════════════════════════════
   SPRINT 3 — MOBILE: navegación y master-detail
   ══════════════════════════════════════════════════════════════ */
var _isMobile = function() { return window.innerWidth <= 768; };

/* Escalaciones: mostrar lista en móvil */
function escVolverLista() {
  if (!_isMobile()) return;
  var sidebar = document.getElementById('esc-sidebar');
  var detalle = document.getElementById('esc-detalle');
  if (sidebar) sidebar.classList.remove('mob-oculto');
  if (detalle) detalle.classList.add('mob-oculto');
  _escTicketActual = null;
}

/* Override de escSeleccionarTicket para añadir comportamiento móvil */
var _escSelBase = escSeleccionarTicket;
escSeleccionarTicket = async function(ticket) {
  await _escSelBase(ticket);
  if (_isMobile()) {
    var sidebar = document.getElementById('esc-sidebar');
    var detalle = document.getElementById('esc-detalle');
    if (sidebar) sidebar.classList.add('mob-oculto');
    if (detalle) detalle.classList.remove('mob-oculto');
  }
};

/* Ajustar layout en resize */
window.addEventListener('resize', function() {
  if (!_isMobile()) {
    var sidebar = document.getElementById('esc-sidebar');
    var detalle = document.getElementById('esc-detalle');
    if (sidebar) sidebar.classList.remove('mob-oculto');
    if (detalle) detalle.classList.remove('mob-oculto');
  }
});

/* ══════════════════════════════════════════════════════════════
   SPRINT 3 — AUDITORÍA de tickets
   ══════════════════════════════════════════════════════════════ */
var _AUDIT_ICONOS = {
  creado:      '🆕', tomado: '✋', pendiente: '⏸',
  resuelto:    '✅', transferido: '↗', nota: '📝', respuesta: '💬'
};

async function escCargarAuditoria(ticketId) {
  var lista = document.getElementById('esc-audit-list');
  if (!lista) return;
  lista.innerHTML = '<div style="color:#94a3b8;font-size:.82rem;padding:8px">Cargando auditoría…</div>';
  try {
    var r = await fetch('/inbox/api/tickets/' + ticketId + '/eventos', {credentials:'include'});
    var d = await r.json();
    var eventos = d.eventos || [];
    if (!eventos.length) {
      lista.innerHTML = '<div style="color:#94a3b8;font-size:.83rem;padding:12px;text-align:center">Sin eventos registrados</div>';
      return;
    }
    lista.innerHTML = '';
    eventos.forEach(function(ev) {
      var icono = _AUDIT_ICONOS[ev.tipo] || '•';
      var hora = new Date(ev.created_at).toLocaleString('es-CO', {
        hour:'2-digit', minute:'2-digit', day:'2-digit', month:'short'
      });
      var el = document.createElement('div');
      el.style.cssText = 'display:flex;gap:10px;align-items:flex-start;padding:8px 10px;' +
        'background:#fff;border-radius:8px;border:1px solid #e2e8f0;font-size:.82rem';
      el.innerHTML = '<span style="font-size:1.1rem">' + icono + '</span>' +
        '<div style="flex:1">' +
          '<div style="font-weight:600;color:#1a2332">' + _escEsc(ev.actor_nombre) + '</div>' +
          '<div style="color:#4a5568;margin-top:1px">' + _escEsc(ev.detalle) + '</div>' +
        '</div>' +
        '<div style="font-size:.7rem;color:#94a3b8;white-space:nowrap">' + hora + '</div>';
      lista.appendChild(el);
    });
    lista.scrollTop = lista.scrollHeight;
  } catch(e) {
    lista.innerHTML = '<div style="color:#ef4444;font-size:.82rem">Error cargando auditoría</div>';
  }
}

/* Override escDetTab para incluir auditoría */
var _escDetTabOrig = escDetTab;
escDetTab = function(id, btn) {
  _escDetTabOrig(id, btn);
  document.getElementById('esc-panel-audit').style.display = id === 'audit' ? 'flex' : 'none';
  if (id === 'audit' && _escTicketActual) escCargarAuditoria(_escTicketActual.id);
};

/* Override escSeleccionarTicket para añadir auditoría al resumen */
var _escSelAudit = escSeleccionarTicket;
escSeleccionarTicket = async function(ticket) {
  await _escSelAudit(ticket);
  // Resetear panel auditoría
  var auditList = document.getElementById('esc-audit-list');
  if (auditList) auditList.innerHTML = '';
};

/* ══════════════════════════════════════════════════════════════
   SPRINT 3 — DASHBOARD SUPERVISOR
   ══════════════════════════════════════════════════════════════ */
function metTab(id, btn) {
  document.querySelectorAll('#met-tab-camp, #met-tab-equipo').forEach(function(t){
    t.classList.remove('active');
  });
  btn.classList.add('active');
  var secBody = document.querySelector('#sec-metricas .sec-body');
  if (secBody) {
    // Mostrar/ocultar paneles dentro del sec-body
    var campPanel = document.getElementById('met-panel-equipo') ?
      secBody.querySelector(':not(#met-panel-equipo)') : secBody;
  }
  // Toggle simple: ocultar/mostrar contenido de campañas vs equipo
  document.querySelectorAll('#sec-metricas .sec-body > *:not(#met-panel-equipo)').forEach(function(el){
    el.style.display = id === 'camp' ? '' : 'none';
  });
  var panelEq = document.getElementById('met-panel-equipo');
  if (panelEq) panelEq.style.display = id === 'equipo' ? '' : 'none';
}

async function cargarStatsEquipo() {
  var wrap = document.getElementById('met-equipo-tabla');
  if (!wrap) return;
  wrap.innerHTML = '<div style="padding:14px;color:#94a3b8;font-size:.85rem;text-align:center">Cargando...</div>';

  // Cargar config auto-asignar
  try {
    var rc = await fetch('/inbox/api/config?agent_id=' + _escAgentId, {credentials:'include'});
    var dc = await rc.json();
    var aa = document.getElementById('toggle-autoasignar');
    var aaLabel = document.getElementById('autoasignar-label');
    if (aa && dc) {
      var isActive = (dc['AUTO_ASIGNAR'] === '1');
      aa.checked = isActive;
      if (aaLabel) aaLabel.textContent = isActive ? 'Activo' : 'Inactivo';
    }
  } catch(e) {}

  try {
    var r = await fetch('/inbox/api/equipo/stats?agent_id=' + _escAgentId, {credentials:'include'});
    var d = await r.json();
    var stats = d.stats || [];
    _renderStatsEquipo(stats);
  } catch(e) {
    wrap.innerHTML = '<div style="padding:14px;color:#ef4444">Error cargando stats</div>';
  }
}

function _renderStatsEquipo(stats) {
  var wrap = document.getElementById('met-equipo-tabla');
  if (!stats.length) {
    wrap.innerHTML = '<div style="padding:20px;text-align:center;color:#94a3b8;font-size:.85rem">' +
      'Sin agentes de soporte configurados. Crea agentes en Configuración → Equipo.</div>';
    return;
  }
  var filas = stats.map(function(s) {
    var onlineDot = '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;' +
      'background:' + (s.online ? '#22c55e' : '#d1d5db') + ';margin-right:5px"></span>';
    var rolColor = {agente:'#e0f2fe;color:#0369a1', supervisor:'#fef3c7;color:#92400e', admin:'#f3e8ff;color:#7c3aed'};
    var rc = rolColor[s.rol] || '#f1f5f9;color:#475569';
    var avgStr = s.avg_resolucion_min != null
      ? (s.avg_resolucion_min < 60
          ? s.avg_resolucion_min + ' min'
          : (s.avg_resolucion_min / 60).toFixed(1) + ' h')
      : '—';
    return '<tr style="border-bottom:1px solid #f1f5f9">' +
      '<td style="padding:10px 14px;font-weight:600;font-size:.85rem;color:#1a2332">' + onlineDot + _escEsc(s.nombre) + '</td>' +
      '<td style="padding:10px 14px"><span style="background:' + rc + ';padding:2px 8px;border-radius:10px;font-size:.72rem;font-weight:700">' + s.rol + '</span></td>' +
      '<td style="padding:10px 14px;text-align:center;font-weight:700;color:' + (s.tickets_activos > 0 ? '#4f46e5' : '#94a3b8') + '">' + s.tickets_activos + '</td>' +
      '<td style="padding:10px 14px;text-align:center;font-weight:700;color:#16a34a">' + s.tickets_resueltos + '</td>' +
      '<td style="padding:10px 14px;text-align:center;color:#64748b">' + avgStr + '</td>' +
      '</tr>';
  });
  wrap.innerHTML = '<table style="width:100%;border-collapse:collapse">' +
    '<thead><tr style="background:#f8fafc;font-size:.72rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.04em">' +
    '<th style="padding:8px 14px;text-align:left;font-weight:600">Agente</th>' +
    '<th style="padding:8px 14px;text-align:left;font-weight:600">Rol</th>' +
    '<th style="padding:8px 14px;text-align:center;font-weight:600">Activos</th>' +
    '<th style="padding:8px 14px;text-align:center;font-weight:600">Resueltos</th>' +
    '<th style="padding:8px 14px;text-align:center;font-weight:600">Tiempo prom.</th>' +
    '</thead><tbody>' + filas.join('') + '</tbody></table>';
}

/* ══════════════════════════════════════════════════════════════
   SPRINT 4 — Llamadas al cliente
   ══════════════════════════════════════════════════════════════ */
function llamarCliente() {
  if (!TEL) return;
  var nombre = document.getElementById('cnm').textContent || '';
  document.getElementById('llamada-nombre').textContent = nombre === '—' ? 'Llamar al cliente' : nombre;
  document.getElementById('llamada-tel').textContent = '+' + TEL;
  // Configurar acciones
  document.getElementById('btn-llamar-tel').onclick = function() {
    window.location.href = 'tel:+' + TEL;
    cerrarModalLlamada();
  };
  document.getElementById('btn-llamar-wa').onclick = function() {
    window.open('https://wa.me/' + TEL, '_blank');
    cerrarModalLlamada();
  };
  document.getElementById('modal-llamada').style.display = 'flex';
}
function cerrarModalLlamada() {
  document.getElementById('modal-llamada').style.display = 'none';
}
function abrirWhatsAppWeb() {
  if (!TEL) return;
  window.open('https://wa.me/' + TEL, '_blank');
}

/* ══════════════════════════════════════════════════════════════
   SPRINT 4 — MENSAJES MULTIMEDIA EN EL CHAT
   ══════════════════════════════════════════════════════════════ */
var _mediaTipoActual = '';  // image | video | document
var _mediaFile       = null;

/* Renderiza una burbuja: texto plano o media según marcador */
function renderMediaOrText(content) {
  if (!content) return '';
  // Detectar marcador __MEDIA__
  if (content.indexOf('__MEDIA__:') === 0) {
    try {
      var data = JSON.parse(content.substring(10));
      return renderMediaBurbuja(data);
    } catch(e) {
      return he(content);
    }
  }
  // Detectar marcador __ORDEN_CATALOGO__ (pedido del cliente)
  if (content.indexOf('__ORDEN_CATALOGO__:') === 0) {
    try {
      var items = JSON.parse(content.substring('__ORDEN_CATALOGO__:'.length));
      var lineas = items.map(function(it) {
        return '🛒 ' + (it.quantity || 1) + 'x ' + he(it.product_retailer_id || '');
      });
      return '<div style="font-size:.82rem">📦 <b>Pedido desde catálogo</b><br>' +
        lineas.join('<br>') + '</div>';
    } catch(e) { return he(content); }
  }
  return he(content);
}

function renderMediaBurbuja(d) {
  var tipo = d.tipo || '';
  var cap = d.caption ? '<div class="media-caption">' + he(d.caption) + '</div>' : '';

  if (tipo === 'image') {
    var src = '/inbox/api/media/' + encodeURIComponent(d.media_id);
    return '<img class="media-img" src="' + src + '" alt="imagen" onclick="window.open(\'' + src + '\',\'_blank\')">' + cap;
  }
  if (tipo === 'video') {
    var src = '/inbox/api/media/' + encodeURIComponent(d.media_id);
    return '<video class="media-vid" src="' + src + '" controls preload="metadata"></video>' + cap;
  }
  if (tipo === 'document') {
    var src = '/inbox/api/media/' + encodeURIComponent(d.media_id);
    var nombre = d.filename || 'Documento';
    return '<a class="media-doc" href="' + src + '" target="_blank" download="' + he(nombre) + '">' +
      '<div class="media-doc-ic">📄</div>' +
      '<div class="media-doc-info">' +
        '<div class="media-doc-name">' + he(nombre) + '</div>' +
        '<div class="media-doc-meta">Abrir/Descargar</div>' +
      '</div></a>' + cap;
  }
  if (tipo === 'audio') {
    var src = '/inbox/api/media/' + encodeURIComponent(d.media_id);
    return '<audio src="' + src + '" controls style="max-width:280px"></audio>';
  }
  if (tipo === 'location') {
    var mapsUrl = 'https://www.google.com/maps?q=' + d.latitud + ',' + d.longitud;
    return '<a class="media-loc" href="' + mapsUrl + '" target="_blank">' +
      '<div style="font-weight:700">📍 ' + he(d.nombre || 'Ubicación compartida') + '</div>' +
      (d.direccion ? '<div style="font-size:.78rem;opacity:.85">' + he(d.direccion) + '</div>' : '') +
      '<div style="font-size:.72rem;opacity:.6">' + d.latitud + ', ' + d.longitud + '</div>' +
      '</a>';
  }
  if (tipo === 'product') {
    var cuerpo = d.cuerpo ? '<div style="font-size:.82rem;margin-bottom:4px">' + he(d.cuerpo) + '</div>' : '';
    return cuerpo + '<div class="media-prod">' +
      '<div class="media-prod-img" style="font-size:1.6rem;display:flex;align-items:center;justify-content:center">🛒</div>' +
      '<div><div style="font-weight:700;font-size:.84rem">Producto del catálogo</div>' +
      '<div style="font-size:.72rem;opacity:.7">SKU: ' + he(d.retailer_id) + '</div></div></div>';
  }
  return '<i style="opacity:.6">Mensaje multimedia</i>';
}

/* Menú adjuntar */
function toggleAttachMenu() {
  var m = document.getElementById('attach-menu');
  if (m) m.style.display = m.style.display === 'none' ? '' : 'none';
}
// Cerrar al click fuera
document.addEventListener('click', function(e) {
  var menu = document.getElementById('attach-menu');
  var btn  = document.getElementById('attach-btn');
  if (menu && menu.style.display !== 'none' && e.target !== btn && !menu.contains(e.target)) {
    menu.style.display = 'none';
  }
});

function abrirSelectorMedia(tipo) {
  toggleAttachMenu();
  _mediaTipoActual = tipo;
  var input = document.getElementById('media-file-input');
  if (tipo === 'image')    input.accept = 'image/*';
  else if (tipo === 'video') input.accept = 'video/mp4,video/3gpp';
  else                      input.accept = '.pdf,application/pdf,.doc,.docx,.xls,.xlsx,.csv,.txt';
  input.value = '';
  input.click();
}

function enviarMediaSeleccionada() {
  var input = document.getElementById('media-file-input');
  if (!input.files || !input.files[0]) return;
  _mediaFile = input.files[0];

  // Mostrar modal con preview y caption
  var titulo = document.getElementById('cap-titulo');
  var prev   = document.getElementById('cap-preview');
  titulo.textContent = 'Enviar ' + (
    _mediaTipoActual === 'image' ? 'imagen' :
    _mediaTipoActual === 'video' ? 'video' : 'documento'
  );

  if (_mediaTipoActual === 'image') {
    var url = URL.createObjectURL(_mediaFile);
    prev.innerHTML = '<img src="' + url + '" style="max-width:100%;max-height:240px;border-radius:8px">';
  } else if (_mediaTipoActual === 'video') {
    var url = URL.createObjectURL(_mediaFile);
    prev.innerHTML = '<video src="' + url + '" controls style="max-width:100%;max-height:240px;border-radius:8px"></video>';
  } else {
    prev.innerHTML = '<div style="padding:14px;background:#f1f5f9;border-radius:8px;color:#1a2332">📄 ' +
      he(_mediaFile.name) + '<br><small style="color:#64748b">' +
      (_mediaFile.size / 1024 / 1024).toFixed(2) + ' MB</small></div>';
  }
  document.getElementById('cap-texto').value = '';
  document.getElementById('cap-progress').style.display = 'none';
  document.getElementById('cap-enviar-btn').disabled = false;
  document.getElementById('modal-caption').style.display = 'flex';
}

function cerrarModalCaption() {
  document.getElementById('modal-caption').style.display = 'none';
  _mediaFile = null;
}

async function confirmarEnvioMedia() {
  if (!_mediaFile || !TEL) return;
  var btn = document.getElementById('cap-enviar-btn');
  var prog = document.getElementById('cap-progress');
  btn.disabled = true;
  prog.style.display = '';
  prog.textContent = '⏳ Subiendo archivo…';

  var fd = new FormData();
  fd.append('file',     _mediaFile);
  fd.append('telefono', TEL);
  fd.append('caption',  document.getElementById('cap-texto').value || '');

  try {
    var r = await fetch('/inbox/api/responder/media', {
      method: 'POST', credentials: 'include', body: fd
    });
    var d = await r.json();
    if (d.ok) {
      cerrarModalCaption();
      loadMsgs(true);  // recargar para ver la burbuja
    } else {
      prog.textContent = '❌ ' + (d.error || 'Error');
      btn.disabled = false;
    }
  } catch(e) {
    prog.textContent = '❌ Error de red';
    btn.disabled = false;
  }
}

/* Ubicación */
function abrirUbicacion() {
  toggleAttachMenu();
  document.getElementById('loc-lat').value = '';
  document.getElementById('loc-lng').value = '';
  document.getElementById('loc-nombre').value = '';
  document.getElementById('loc-dir').value = '';
  document.getElementById('modal-ubicacion').style.display = 'flex';
}
function cerrarModalUbicacion() {
  document.getElementById('modal-ubicacion').style.display = 'none';
}
function usarMiUbicacion() {
  if (!navigator.geolocation) { alert('Tu navegador no soporta geolocalización'); return; }
  navigator.geolocation.getCurrentPosition(function(pos) {
    document.getElementById('loc-lat').value = pos.coords.latitude.toFixed(6);
    document.getElementById('loc-lng').value = pos.coords.longitude.toFixed(6);
  }, function(err) {
    alert('No se pudo obtener tu ubicación: ' + err.message);
  });
}
async function enviarUbicacion() {
  if (!TEL) return;
  var lat = parseFloat(document.getElementById('loc-lat').value);
  var lng = parseFloat(document.getElementById('loc-lng').value);
  if (isNaN(lat) || isNaN(lng)) { alert('Latitud y longitud son requeridas'); return; }
  var nombre = document.getElementById('loc-nombre').value || '';
  var dir    = document.getElementById('loc-dir').value || '';
  try {
    var r = await fetch('/inbox/api/responder/ubicacion', {
      method: 'POST', credentials: 'include',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({telefono: TEL, latitud: lat, longitud: lng, nombre: nombre, direccion: dir})
    });
    var d = await r.json();
    if (d.ok) {
      cerrarModalUbicacion();
      loadMsgs(true);
    } else { alert('Error: ' + (d.error || 'desconocido')); }
  } catch(e) { alert('Error de red'); }
}

/* Catálogo */
function abrirCatalogoSelector() {
  toggleAttachMenu();
  document.getElementById('cat-buscar').value = '';
  document.getElementById('cat-resultados').innerHTML = '<div style="padding:20px;text-align:center;color:#94a3b8">Cargando catálogo…</div>';
  document.getElementById('modal-catalogo').style.display = 'flex';
  buscarCatalogo();
}
function cerrarModalCatalogo() {
  document.getElementById('modal-catalogo').style.display = 'none';
}
var _catTimer = null;
function buscarCatalogo() {
  clearTimeout(_catTimer);
  _catTimer = setTimeout(_buscarCatalogoExec, 200);
}
async function _buscarCatalogoExec() {
  var q = document.getElementById('cat-buscar').value || '';
  var box = document.getElementById('cat-resultados');
  try {
    var r = await fetch('/inbox/api/catalogo/buscar?q=' + encodeURIComponent(q), {credentials:'include'});
    var d = await r.json();
    var prods = d.productos || [];
    if (!prods.length) {
      box.innerHTML = '<div style="padding:20px;text-align:center;color:#94a3b8;font-size:.84rem">' +
        (q ? 'Sin resultados para "' + he(q) + '"' : 'Sin productos en el catálogo') + '</div>';
      return;
    }
    box.innerHTML = prods.map(function(p) {
      var img = p.image ? '<img class="cat-item-img" src="' + he(p.image) + '">' :
        '<div class="cat-item-img" style="display:flex;align-items:center;justify-content:center">🛒</div>';
      var label = he(p.title) + (p.variant && p.variant !== 'Default Title' ? ' · ' + he(p.variant) : '');
      var precio = p.price ? '$' + Number(p.price).toLocaleString('es-CO') : '';
      var rid = p.retailer_id || '';
      var sinSku = !rid;
      var click = sinSku ? '' :
        ' onclick="enviarProducto(\'' + rid.replace(/'/g, "&#39;") + '\')"';
      var style = sinSku ? ' style="opacity:.5;cursor:not-allowed"' : '';
      var skuMostrar = p.sku_legible || rid;
      var skuInfo = sinSku
        ? '<div style="font-size:.7rem;color:#ef4444">⚠️ Sin SKU — no se puede enviar</div>'
        : '<div style="font-size:.7rem;color:#94a3b8">SKU: ' + he(skuMostrar) + '</div>';
      return '<div class="cat-item"' + click + style + '>' +
        img +
        '<div class="cat-item-info">' +
          '<div class="cat-item-titulo">' + label + '</div>' +
          '<div class="cat-item-precio">' + precio + '</div>' +
          skuInfo +
        '</div></div>';
    }).join('');
  } catch(e) {
    box.innerHTML = '<div style="padding:20px;color:#ef4444;font-size:.84rem">Error: ' + he(String(e)) + '</div>';
  }
}
async function enviarProducto(retailerId) {
  if (!TEL) return;
  try {
    var r = await fetch('/inbox/api/responder/producto', {
      method: 'POST', credentials: 'include',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({telefono: TEL, retailer_id: retailerId})
    });
    var d = await r.json();
    if (d.ok) {
      cerrarModalCatalogo();
      loadMsgs(true);
    } else { alert('Error: ' + (d.error || 'desconocido')); }
  } catch(e) { alert('Error de red'); }
}

async function toggleAutoAsignar(activo) {
  var label = document.getElementById('autoasignar-label');
  try {
    var r = await fetch('/inbox/api/config/auto-asignar?agent_id=' + _escAgentId, {
      method:'POST', credentials:'include',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({activo: activo})
    });
    var d = await r.json();
    if (d.ok && label) label.textContent = activo ? 'Activo' : 'Inactivo';
    else if (!d.ok) alert('Error al cambiar configuración');
  } catch(e) { alert('Error de red'); }
}

/* ══════════════════════════════════════════════════════════════
   SPRINT 2 — SSE: notificaciones en tiempo real
   ══════════════════════════════════════════════════════════════ */
var _sseSource = null;

function escConectarSSE() {
  if (_sseSource) return;
  var url = '/inbox/api/eventos?agent_id=' + _escAgentId;
  _sseSource = new EventSource(url, {withCredentials: true});

  _sseSource.onmessage = function(e) {
    if (!e.data || e.data.startsWith(':')) return;  // keepalive
    try {
      var evt = JSON.parse(e.data);
      _escManejarEvento(evt);
    } catch(err) {}
  };

  _sseSource.onerror = function() {
    // Reconectar automáticamente tras 5s
    _sseSource.close();
    _sseSource = null;
    setTimeout(escConectarSSE, 5000);
  };
}

function _escManejarEvento(evt) {
  var tipo   = evt.tipo || '';
  var ticket = evt.ticket || {};

  // Actualizar badges siempre
  _escActualizarBadges();

  // Si la sección de escalaciones está abierta, recargar lista
  if (_secActual === 'escalaciones') {
    escCargarLista();
  }

  // Mostrar toast de notificación
  var mensajes = {
    ticket_nuevo:       '🚨 Nuevo ticket: ' + (ticket.nombre_cliente || ticket.telefono_cliente),
    ticket_tomado:      '✋ Ticket tomado por ' + (ticket.agente_nombre || 'un agente'),
    ticket_pendiente:   '⏸ Ticket marcado como pendiente',
    ticket_resuelto:    '✅ Ticket resuelto — bot reactivado',
    ticket_transferido: '↗ Ticket transferido a ' + (ticket.agente_nombre || 'otro agente'),
  };
  var msg = mensajes[tipo];
  if (msg) _escToast(msg, tipo === 'ticket_nuevo' ? '#ef4444' : '#4f46e5');
}

function _escToast(msg, color) {
  var toast = document.createElement('div');
  toast.className = 'esc-toast';
  toast.style.borderLeftColor = color || '#4f46e5';
  toast.textContent = msg;
  document.body.appendChild(toast);
  setTimeout(function() {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity .3s';
    setTimeout(function() { toast.remove(); }, 300);
  }, 4000);
}

// Iniciar SSE al cargar la página
document.addEventListener('DOMContentLoaded', escConectarSSE);

/* ══════════════════════════════════════════════════════════════
   SPRINT 2 — SLA: timer visual en tarjetas de tickets
   ══════════════════════════════════════════════════════════════ */
var _escSlaMinutos = 5;   // alerta en amarillo
var _escSlaCritico = 15;  // alerta en rojo

function _escSlaClase(creadoAt, estado) {
  if (estado !== 'sin_asignar') return '';
  var mins = Math.floor((Date.now() - new Date(creadoAt).getTime()) / 60000);
  if (mins >= _escSlaCritico) return 'sla-crit';
  if (mins >= _escSlaMinutos) return 'sla-warn';
  return '';
}

function _escSlaLabel(creadoAt, estado) {
  if (estado !== 'sin_asignar') return '';
  var mins = Math.floor((Date.now() - new Date(creadoAt).getTime()) / 60000);
  if (mins < 1) return '';
  return ' · ' + mins + 'min sin atender';
}

// Regenerar lista cada 60s para actualizar timers SLA
setInterval(function() {
  if (_secActual === 'escalaciones' && _escEstadoActual === 'sin_asignar') {
    escCargarLista();
  }
}, 60000);

/* ══════════════════════════════════════════════════════════════
   SPRINT 2 — Tabs detalle ticket (Conversación / Notas)
   ══════════════════════════════════════════════════════════════ */
var _escTabActual = 'conv';

function escDetTab(id, btn) {
  _escTabActual = id;
  document.querySelectorAll('.det-tab').forEach(function(t){ t.classList.remove('active'); });
  btn.classList.add('active');
  document.getElementById('esc-panel-conv').style.display   = id === 'conv'  ? 'flex' : 'none';
  document.getElementById('esc-panel-notas').style.display  = id === 'notas' ? 'flex' : 'none';
  if (id === 'notas' && _escTicketActual) escCargarNotas(_escTicketActual.id);
}

/* ══════════════════════════════════════════════════════════════
   SPRINT 2 — Notas internas
   ══════════════════════════════════════════════════════════════ */
async function escCargarNotas(ticketId) {
  var lista = document.getElementById('esc-notas-list');
  if (!lista) return;
  lista.innerHTML = '<div style="color:#94a3b8;font-size:.82rem;padding:8px">Cargando notas…</div>';
  try {
    var r = await fetch('/inbox/api/tickets/' + ticketId + '/notas', {credentials:'include'});
    var d = await r.json();
    var notas = d.notas || [];
    var cntEl = document.getElementById('notas-count');
    if (cntEl) cntEl.textContent = notas.length ? '(' + notas.length + ')' : '';

    if (!notas.length) {
      lista.innerHTML = '<div style="color:#94a3b8;font-size:.83rem;padding:12px;text-align:center">Sin notas aún. Agrega la primera 👇</div>';
      return;
    }
    lista.innerHTML = '';
    notas.forEach(function(n) {
      var el = document.createElement('div');
      el.className = 'esc-bbl esc-bbl-nota';
      el.innerHTML = '<div style="font-size:.72rem;font-weight:700;color:#92400e;margin-bottom:3px">📝 ' +
        _escEsc(n.agente_nombre) + ' · ' + new Date(n.created_at).toLocaleTimeString('es-CO',{hour:'2-digit',minute:'2-digit'}) + '</div>' +
        _escEsc(n.contenido);
      lista.appendChild(el);
    });
    lista.scrollTop = lista.scrollHeight;
  } catch(e) {
    lista.innerHTML = '<div style="color:#ef4444;font-size:.82rem">Error cargando notas</div>';
  }
}

async function escGuardarNota() {
  if (!_escTicketActual) return;
  var input = document.getElementById('esc-nota-input');
  var texto = (input.value || '').trim();
  if (!texto) return;
  input.value = '';
  await fetch('/inbox/api/tickets/' + _escTicketActual.id + '/notas', {
    method:'POST', credentials:'include',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      contenido: texto,
      agente_humano_id: _escUsuarioId || 0,
      agente_nombre: 'Agente',
    })
  });
  escCargarNotas(_escTicketActual.id);
}

/* ══════════════════════════════════════════════════════════════
   SPRINT 2 — Transferencia entre agentes
   ══════════════════════════════════════════════════════════════ */
var _equipoCache = [];

async function escMostrarTransferir() {
  var wrap = document.getElementById('transferir-wrap');
  if (!wrap) return;
  wrap.style.display = wrap.style.display === 'none' ? '' : 'none';
  if (wrap.style.display === 'none') return;

  // Cargar equipo si no está en caché
  if (!_equipoCache.length) {
    var r = await fetch('/inbox/api/equipo?agent_id=' + _escAgentId, {credentials:'include'});
    var d = await r.json();
    _equipoCache = (d.equipo || []).filter(function(u){ return u.activo; });
  }
  var sel = document.getElementById('transferir-select');
  sel.innerHTML = '<option value="">— Selecciona un agente —</option>';
  _equipoCache.forEach(function(u) {
    if (_escTicketActual && u.id === _escTicketActual.agente_humano_id) return; // no mostrar al actual
    var opt = document.createElement('option');
    opt.value = u.id;
    opt.textContent = u.nombre + ' (' + u.rol + ')';
    sel.appendChild(opt);
  });
}

async function escConfirmarTransferir() {
  if (!_escTicketActual) return;
  var sel   = document.getElementById('transferir-select');
  var nuevoId = parseInt(sel.value);
  if (!nuevoId) { alert('Selecciona un agente'); return; }
  var r = await fetch('/inbox/api/tickets/' + _escTicketActual.id + '/transferir?agent_id=' + _escAgentId, {
    method:'POST', credentials:'include',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({agente_humano_id: nuevoId})
  });
  var d = await r.json();
  if (d.ok) {
    document.getElementById('transferir-wrap').style.display = 'none';
    _escTicketActual = d.ticket;
    escCargarLista();
    _escToast('↗ Ticket transferido correctamente', '#4f46e5');
  } else {
    alert('Error al transferir');
  }
}

/* ══════════════════════════════════════════════════════════════
   SPRINT 2 — Templates rápidos en el panel de respuesta
   ══════════════════════════════════════════════════════════════ */
var _templatesCache = [];

async function escCargarTemplatesParaPanel() {
  if (_templatesCache.length) return;
  try {
    var r = await fetch('/inbox/api/templates?agent_id=' + _escAgentId, {credentials:'include'});
    var d = await r.json();
    _templatesCache = d.templates || [];
  } catch(e) {}
}

function escToggleTemplates() {
  var picker = document.getElementById('tpl-picker');
  if (!picker) return;
  if (picker.style.display !== 'none') { picker.style.display = 'none'; return; }
  escCargarTemplatesParaPanel().then(function() {
    if (!_templatesCache.length) {
      picker.innerHTML = '<div class="tpl-item" style="color:#94a3b8">Sin templates. Crea uno en Configuración → ⚡ Templates</div>';
    } else {
      picker.innerHTML = '';
      _templatesCache.forEach(function(tpl) {
        var el = document.createElement('div');
        el.className = 'tpl-item';
        el.innerHTML = '<div class="tpl-item-titulo">' + _escEsc(tpl.titulo) + '</div>' +
                       '<div class="tpl-item-prev">' + _escEsc(tpl.contenido.slice(0,70)) + (tpl.contenido.length>70?'…':'') + '</div>';
        el.onclick = function() {
          document.getElementById('esc-reply-input').value = tpl.contenido;
          picker.style.display = 'none';
          document.getElementById('esc-reply-input').focus();
        };
        picker.appendChild(el);
      });
    }
    picker.style.display = '';
  });
}

// Cerrar picker al hacer click fuera
document.addEventListener('click', function(e) {
  var picker = document.getElementById('tpl-picker');
  if (picker && !picker.contains(e.target) && e.target.textContent !== '⚡ Templates') {
    picker.style.display = 'none';
  }
});

/* ── Gestión de templates desde Configuración ────────────────── */
async function cargarTemplatesRapidos() {
  var lista = document.getElementById('tpl-lista');
  if (!lista) return;
  lista.innerHTML = '<div style="padding:14px;color:#94a3b8;font-size:.85rem">Cargando…</div>';
  try {
    var r = await fetch('/inbox/api/templates?agent_id=' + _escAgentId, {credentials:'include'});
    var d = await r.json();
    _templatesCache = d.templates || [];
    _renderListaTemplates(_templatesCache);
  } catch(e) {
    lista.innerHTML = '<div style="padding:14px;color:#ef4444">Error al cargar</div>';
  }
}

function _renderListaTemplates(templates) {
  var lista = document.getElementById('tpl-lista');
  if (!templates.length) {
    lista.innerHTML = '<div style="padding:20px;text-align:center;color:#94a3b8;font-size:.85rem">' +
      'Sin templates aún. Crea el primero con el botón "Nuevo template".</div>';
    return;
  }
  var filas = templates.map(function(t) {
    return '<tr style="border-bottom:1px solid #f1f5f9">' +
      '<td style="padding:10px 14px;font-weight:700;font-size:.85rem;color:#1a2332">' + _escEsc(t.titulo) + '</td>' +
      '<td style="padding:10px 14px;font-size:.82rem;color:#4a5568;max-width:320px">' +
        _escEsc(t.contenido.slice(0,100)) + (t.contenido.length>100?'…':'') + '</td>' +
      '<td style="padding:10px 14px">' +
        '<button onclick="eliminarTemplateRapido(' + t.id + ')" style="color:#ef4444;background:none;border:none;cursor:pointer;font-size:.78rem">Eliminar</button>' +
      '</td></tr>';
  });
  lista.innerHTML = '<table style="width:100%;border-collapse:collapse">' +
    '<thead><tr style="background:#f8fafc;font-size:.75rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.04em">' +
    '<th style="padding:8px 14px;text-align:left;font-weight:600">Título</th>' +
    '<th style="padding:8px 14px;text-align:left;font-weight:600">Mensaje</th>' +
    '<th style="padding:8px 14px"></th>' +
    '</thead><tbody>' + filas.join('') + '</tbody></table>';
}

function mostrarFormTemplate() {
  var wrap = document.getElementById('tpl-form-wrap');
  if (wrap) wrap.style.display = wrap.style.display === 'none' ? '' : 'none';
}

async function guardarTemplateRapido() {
  var titulo   = (document.getElementById('tpl-titulo').value   || '').trim();
  var contenido = (document.getElementById('tpl-contenido').value || '').trim();
  var msg      = document.getElementById('tpl-form-msg');
  if (!titulo || !contenido) { msg.innerHTML = '<span style="color:#ef4444">Completa título y mensaje.</span>'; return; }
  msg.innerHTML = 'Guardando…';
  var r = await fetch('/inbox/api/templates?agent_id=' + _escAgentId, {
    method:'POST', credentials:'include',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({titulo, contenido})
  });
  var d = await r.json();
  if (d.ok) {
    msg.innerHTML = '<span style="color:#16a34a">✅ Template guardado.</span>';
    document.getElementById('tpl-titulo').value = '';
    document.getElementById('tpl-contenido').value = '';
    _templatesCache = [];  // forzar recarga
    cargarTemplatesRapidos();
  } else {
    msg.innerHTML = '<span style="color:#ef4444">' + (d.error || 'Error') + '</span>';
  }
}

async function eliminarTemplateRapido(id) {
  if (!confirm('¿Eliminar este template?')) return;
  var r = await fetch('/inbox/api/templates/' + id, {method:'DELETE', credentials:'include'});
  var d = await r.json();
  if (d.ok) { _templatesCache = []; cargarTemplatesRapidos(); }
  else alert('Error al eliminar');
}

/* ══════════════════════════════════════════════════════════════
   SPRINT 2 — Overrides sobre funciones del Sprint 1 para incluir
   tabs, SLA y botón transferir al seleccionar un ticket
   ══════════════════════════════════════════════════════════════ */
var _escSeleccionarTicketOriginal = escSeleccionarTicket;
escSeleccionarTicket = async function(ticket) {
  await _escSeleccionarTicketOriginal(ticket);

  // Mostrar tabs
  var tabs = document.getElementById('esc-det-tabs');
  if (tabs) tabs.style.display = '';

  // Mostrar input de nota si ticket activo
  var notaInputWrap = document.getElementById('esc-nota-input-wrap');
  if (notaInputWrap) notaInputWrap.style.display = ticket.estado === 'activo' ? '' : 'none';

  // Mostrar botón transferir si activo
  var btnTransferir = document.getElementById('btn-transferir');
  if (btnTransferir) btnTransferir.style.display = ticket.estado === 'activo' ? '' : 'none';

  // Resetear a tab Conversación
  escDetTab('conv', document.getElementById('det-tab-conv'));

  // Reset notas count
  var cntEl = document.getElementById('notas-count');
  if (cntEl) cntEl.textContent = '';
};

// Override _escRenderLista para incluir SLA
var _escRenderListaOriginal = _escRenderLista;
_escRenderLista = function(tickets) {
  var lista = document.getElementById('esc-lista');
  if (!tickets.length) {
    lista.innerHTML = '<div style="padding:24px;text-align:center;color:#94a3b8;font-size:.84rem">Sin conversaciones en esta categoría</div>';
    return;
  }
  lista.innerHTML = '';
  tickets.forEach(function(t) {
    var urgClass = 'esc-urg-' + (t.urgencia || 'normal');
    var slaClass = _escSlaClase(t.creado_at, t.estado);
    var slaLabel = _escSlaLabel(t.creado_at, t.estado);
    var tiempo   = _escTiempoRelativo(t.actualizado_at);
    var card = document.createElement('div');
    card.className = 'esc-card' + (_escTicketActual && _escTicketActual.id === t.id ? ' selected' : '');
    card.onclick = function() { escSeleccionarTicket(t); };
    // Nombre + rol del último agente (admin / supervisor / agente)
    var agLabel = '';
    if (t.agente_nombre) {
      var rolStr = t.agente_rol ? ' · ' + t.agente_rol : '';
      agLabel = '<span>👤 ' + _escEsc(t.agente_nombre) + _escEsc(rolStr) + '</span>';
    }
    card.innerHTML =
      '<div class="esc-card-nombre">' + _escEsc(t.nombre_cliente || t.telefono_cliente) + '</div>' +
      '<div class="esc-card-motivo">' + _escEsc(t.motivo) + '</div>' +
      '<div class="esc-card-meta">' +
        '<span class="esc-urg ' + urgClass + '">' + (t.urgencia||'normal') + '</span>' +
        agLabel +
        '<span style="margin-left:auto" class="' + slaClass + '">' + tiempo + slaLabel + '</span>' +
      '</div>';
    lista.appendChild(card);
  });
};
</script>
</body>
</html>"""


def obtener_inbox_html(agent: dict | None = None, user: dict | None = None) -> str:
    """Devuelve el HTML del inbox scoped al agente indicado."""
    import json as _json
    _agent = agent or {"id": 1, "slug": "equora", "name": "Equora Distribuciones",
                       "agent_name": "Andrea", "color": "#22c55e", "emoji": "🌿", "status": "active"}
    agent_json = _json.dumps(_agent, ensure_ascii=False)
    inject_head = f"<script>var VOCO_AGENT={agent_json};</script>"

    # Barra superior mini con nombre del agente y link al panel global
    color  = _agent.get("color", "#6366f1")
    emoji  = _agent.get("emoji", "🤖")
    name   = _agent.get("name", "Mi Agente")
    aname  = _agent.get("agent_name", "Agente")
    status = _agent.get("status", "active")
    status_label = {"active": "● Activo", "paused": "⏸ Pausado", "draft": "✎ Borrador"}.get(status, status)
    status_color = {"active": "#22c55e", "paused": "#f59e0b", "draft": "#94a3b8"}.get(status, "#94a3b8")

    # Info del usuario autenticado en la barra
    if user:
        rol = user.get("rol", "user")
        plan = user.get("plan", "trial")
        nombre_u = user.get("nombre") or user.get("email", "")
        if rol == "admin":
            user_badge = '<span style="background:#4f46e5;color:#c7d2fe;font-size:.68rem;padding:2px 8px;border-radius:10px;font-weight:700">Administrador</span>'
        else:
            plan_colors = {"trial": "#64748b", "starter": "#0891b2", "growth": "#059669", "pro": "#7c3aed"}
            plan_bg = {"trial": "#1e293b", "starter": "#0c4a6e", "growth": "#064e3b", "pro": "#2e1065"}
            pc = plan_colors.get(plan, "#64748b")
            pb = plan_bg.get(plan, "#1e293b")
            user_badge = f'<span style="background:{pb};color:{pc};font-size:.68rem;padding:2px 8px;border-radius:10px;font-weight:700;text-transform:capitalize">{plan}</span>'
        user_info = f'<span style="color:#94a3b8;font-size:.76rem;margin-right:6px">{nombre_u}</span>{user_badge}'
    else:
        user_info = ""

    agent_bar = f"""<div style="background:var(--voco-nav-bg);padding:7px 20px;display:flex;align-items:center;
justify-content:space-between;border-bottom:2px solid {color};flex-shrink:0">
  <div style="display:flex;align-items:center;gap:10px">
    <span style="font-size:1.3rem">{emoji}</span>
    <div>
      <div style="color:var(--voco-text);font-weight:700;font-size:.85rem;line-height:1.2">{name}</div>
      <div style="color:var(--voco-text-muted);font-size:.72rem">{aname} &nbsp;·&nbsp;
        <span style="color:{status_color}">{status_label}</span></div>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:10px">
    {user_info}
    <button type="button" onclick="vocoToggleTheme()" title="Cambiar tema"
      aria-label="Cambiar tema claro/oscuro"
      style="background:transparent;border:1px solid var(--voco-border);color:var(--voco-text-muted);
        width:30px;height:30px;border-radius:6px;cursor:pointer;
        display:inline-flex;align-items:center;justify-content:center;transition:.15s"
      onmouseover="this.style.color='var(--voco-text)';this.style.background='var(--voco-nav-bg-hover)'"
      onmouseout="this.style.color='var(--voco-text-muted)';this.style.background='transparent'">
      <i data-lucide="sun"  class="hidden dark:inline-block" style="width:15px;height:15px"></i>
      <i data-lucide="moon" class="inline-block dark:hidden" style="width:15px;height:15px"></i>
    </button>
    <a href="/inbox" style="color:var(--voco-text-muted);font-size:.76rem;text-decoration:none;
      padding:4px 12px;border:1px solid var(--voco-border);border-radius:6px;
      transition:.15s;white-space:nowrap"
      onmouseover="this.style.color='var(--voco-text)';this.style.background='var(--voco-nav-bg-hover)'"
      onmouseout="this.style.color='var(--voco-text-muted)';this.style.background='transparent'">
      ← Voco
    </a>
    <a href="/inbox/logout" style="color:var(--voco-text-muted);font-size:.72rem;text-decoration:none;
      padding:4px 10px;border:1px solid var(--voco-border);border-radius:6px">Salir</a>
  </div>
</div>"""

    html = _HTML.replace("<head>", f"<head>\n{inject_head}", 1)
    # agent_bar va DENTRO de #shell (primer hijo) para no empujar el shell fuera del viewport.
    # También ocultamos el #topbar interno que duplica información.
    hide_topbar = '<style>#topbar{display:none!important}</style>'
    html = html.replace("<body>\n<div id=\"shell\">\n", f"<body>\n<div id=\"shell\">\n{agent_bar}\n", 1)
    html = html.replace("</head>", f"{hide_topbar}\n</head>", 1)
    return html.replace("__VOCO_DS__", _DESIGN_SYSTEM_HEAD)


def _build_user_topbar(user: dict | None) -> str:
    """Genera el HTML del badge de usuario en la topbar del panel global."""
    if not user:
        return '<span class="topbar-user">🔐 Admin</span>'
    rol = user.get("rol", "user")
    plan = user.get("plan", "trial")
    nombre = user.get("nombre") or user.get("email", "Usuario")
    if rol == "admin":
        badge = '<span style="background:#4f46e5;color:#c7d2fe;font-size:.68rem;padding:2px 8px;border-radius:10px;font-weight:700;margin-left:6px">Administrador</span>'
    else:
        plan_colors = {"trial": "#64748b", "starter": "#0891b2", "growth": "#059669", "pro": "#7c3aed"}
        plan_bg    = {"trial": "#1e293b",  "starter": "#0c4a6e",  "growth": "#064e3b",  "pro": "#2e1065"}
        pc = plan_colors.get(plan, "#64748b")
        pb = plan_bg.get(plan, "#1e293b")
        badge = f'<span style="background:{pb};color:{pc};font-size:.68rem;padding:2px 8px;border-radius:10px;font-weight:700;text-transform:capitalize;margin-left:6px">{plan}</span>'
    return f'<span class="topbar-user">{nombre}{badge}</span>'


def obtener_global_html(agents: list[dict], user: dict | None = None) -> str:
    """Panel global de Voco — lista de todos los agentes + wizard de creación."""
    import json as _json

    _PROMPT_TEMPLATES = {
        "productos": """Eres {NOMBRE_AGENTE}, el asistente virtual de {NOMBRE_NEGOCIO}.

## Tu identidad
Representas a {NOMBRE_NEGOCIO} en WhatsApp. Eres amable, útil y conoces bien los productos.

## Sobre el negocio
{DESCRIPCION_NEGOCIO}

## Tus capacidades
- Presentar el catálogo de productos con precios y presentaciones
- Ayudar al cliente a armar su pedido
- Calcular totales y verificar disponibilidad
- Informar sobre envíos, tiempos de entrega y formas de pago
- Generar el link de checkout cuando el cliente confirma su pedido

## Horario de atención
{HORARIO}

## Reglas
- Responde siempre en español de forma cálida y cercana
- Nunca inventes precios ni productos que no estén en tu catálogo
- Si no sabes algo, ofrece conectar con el equipo humano
- Mantén respuestas concisas (máximo 3-4 párrafos)""",

        "servicios": """Eres {NOMBRE_AGENTE}, asistente virtual de {NOMBRE_NEGOCIO}.

## Tu identidad
Ayudas a los clientes a conocer los servicios, resolver dudas y agendar citas.

## Sobre el negocio
{DESCRIPCION_NEGOCIO}

## Tus capacidades
- Presentar el portafolio de servicios con precios y duraciones
- Verificar disponibilidad de agenda
- Agendar, confirmar y recordar citas
- Calificar leads: preguntar presupuesto, urgencia y necesidad
- Escalar a un asesor humano cuando el cliente está listo para contratar

## Horario de atención
{HORARIO}

## Reglas
- Sé profesional y empático — los clientes de servicios buscan confianza
- Siempre confirma los datos de la cita antes de registrarla
- No des precios exactos sin conocer el alcance del proyecto""",

        "restaurante": """Eres {NOMBRE_AGENTE}, asistente de {NOMBRE_NEGOCIO}.

## Tu identidad
Atiendes pedidos, informas el menú y gestionas reservas con rapidez y simpatía.

## Sobre el negocio
{DESCRIPCION_NEGOCIO}

## Tus capacidades
- Compartir el menú del día con precios
- Tomar pedidos para domicilio o para llevar
- Informar tiempos de entrega y cobertura de domicilios
- Gestionar reservas de mesa
- Informar sobre alérgenos o ingredientes a petición

## Horario de atención
{HORARIO}

## Reglas
- Confirma siempre la dirección de entrega y el método de pago
- Si hay demora, comunícala proactivamente
- Usa emojis de comida con moderación 🍕🥗""",

        "salud": """Eres {NOMBRE_AGENTE}, asistente de {NOMBRE_NEGOCIO}.

## Tu identidad
Asistes a pacientes y clientes con información sobre servicios de salud y belleza.

## Sobre el negocio
{DESCRIPCION_NEGOCIO}

## Tus capacidades
- Informar sobre tratamientos, servicios y precios
- Agendar citas con el especialista correcto
- Recordar preparación previa a los procedimientos
- Responder preguntas frecuentes sobre tratamientos

## Horario de atención
{HORARIO}

## Reglas
- Nunca des diagnósticos médicos ni reemplaces la consulta profesional
- Mantén la privacidad: no solicites información médica sensible por chat
- Ante emergencias, indica llamar al número de emergencias local""",

        "personalizado": """Eres {NOMBRE_AGENTE}, asistente virtual de {NOMBRE_NEGOCIO}.

## Tu identidad
Representas a {NOMBRE_NEGOCIO} y ayudas a los clientes según las instrucciones de tu configuración.

## Sobre el negocio
{DESCRIPCION_NEGOCIO}

## Horario de atención
{HORARIO}

## Reglas
- Responde siempre en español
- Sé amable y profesional
- Si no sabes algo, ofrece conectar con el equipo humano"""
    }

    templates_js = _json.dumps(_PROMPT_TEMPLATES, ensure_ascii=False)

    cards_html = ""
    if not agents:
        cards_html = """<div style="grid-column:1/-1;text-align:center;padding:60px 20px;color:var(--text-soft)">
          <div style="font-size:3rem;margin-bottom:12px">🤖</div>
          <div style="font-size:1rem;font-weight:600;color:var(--text);margin-bottom:6px">No hay agentes aún</div>
          <div style="font-size:.84rem">Crea tu primer agente con el botón de arriba</div>
        </div>"""
    else:
        for ag in agents:
            color   = ag.get("color", "#6366f1")
            emoji   = ag.get("emoji", "🤖")
            name    = ag.get("name", "Mi Agente")
            aname   = ag.get("agent_name", "Agente")
            slug    = ag.get("slug", "")
            status  = ag.get("status", "draft")
            btype   = ag.get("business_type", "personalizado")
            pill_c  = {"active": "#22c55e", "paused": "#f59e0b", "draft": "#94a3b8"}.get(status, "#94a3b8")
            pill_bg = {"active": "#052e16", "paused": "#422006", "draft": "#1e293b"}.get(status, "#1e293b")
            pill_lbl = {"active": "● Activo", "paused": "⏸ Pausado", "draft": "✎ Borrador"}.get(status, status)
            btype_lbl = {"productos": "🛍 Productos", "servicios": "🔧 Servicios",
                         "restaurante": "🍽 Restaurante", "salud": "💊 Salud",
                         "personalizado": "⚙ Personalizado"}.get(btype, btype)
            agent_id = ag.get("id", 1)
            # En light mode el pill usa colores semánticos limpios; en dark usa tonos oscuros
            pill_c_light  = {"active": "#047857", "paused": "#b45309", "draft": "#475569"}.get(status, "#475569")
            pill_bg_light = {"active": "#ecfdf5", "paused": "#fef3c7", "draft": "#f1f5f9"}.get(status, "#f1f5f9")
            cards_html += f"""
        <div class="agent-card" style="border-top:3px solid {color}">
          <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:14px">
            <div style="display:flex;align-items:center;gap:10px">
              <div style="width:44px;height:44px;border-radius:12px;background:{color}22;
                display:flex;align-items:center;justify-content:center;font-size:1.5rem">{emoji}</div>
              <div>
                <div style="font-weight:700;color:var(--text);font-size:.95rem">{name}</div>
                <div style="font-size:.77rem;color:var(--text-soft)">{aname} · {btype_lbl}</div>
              </div>
            </div>
            <span class="agent-pill agent-pill-{status}"
              style="--pill-bg-light:{pill_bg_light};--pill-c-light:{pill_c_light};
              --pill-bg-dark:{pill_bg};--pill-c-dark:{pill_c};
              padding:3px 10px;border-radius:20px;font-size:.72rem;font-weight:600;
              background:var(--pill-bg-light);color:var(--pill-c-light)">{pill_lbl}</span>
          </div>
          <div style="display:flex;gap:8px;margin-top:auto">
            <a href="/inbox/{slug}" class="btn-card-primary" style="background:{color}">
              Abrir panel →
            </a>
            <button class="btn-card-sec" onclick="editarAgente({agent_id})" type="button"
              aria-label="Configurar agente">⚙</button>
          </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Voco — Plataforma de Agentes IA</title>
__VOCO_DS__
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#f8fafc; --bg-card:#ffffff; --bg-soft:#f1f5f9;
  --border:#e2e8f0; --border-soft:#f1f5f9;
  --text:#0f172a; --text-soft:#475569; --text-muted:#94a3b8;
  --brand:#4f46e5; --brand-hover:#4338ca;
}}
html.dark{{
  --bg:#0f172a; --bg-card:#1e293b; --bg-soft:#0b1220;
  --border:#1e293b; --border-soft:#334155;
  --text:#f1f5f9; --text-soft:#94a3b8; --text-muted:#64748b;
  --brand:#818cf8; --brand-hover:#a5b4fc;
}}
body{{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);
  min-height:100vh;transition:background-color .15s, color .15s}}
.topbar{{background:var(--bg-card);border-bottom:1px solid var(--border);padding:0 28px;
  display:flex;align-items:center;justify-content:space-between;height:58px}}
.voco-logo{{display:flex;align-items:center;gap:10px;text-decoration:none}}
.voco-logo-ic{{width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,#6366f1,#8b5cf6);
  display:flex;align-items:center;justify-content:center;font-size:1.1rem;box-shadow:0 2px 8px #6366f144;color:#fff}}
.voco-logo-txt{{font-weight:800;font-size:1.15rem;color:var(--text);letter-spacing:-.5px}}
.voco-logo-txt span{{color:var(--brand)}}
.topbar-right{{display:flex;align-items:center;gap:12px}}
.topbar-user{{font-size:.78rem;color:var(--text-soft);padding:4px 10px;
  border:1px solid var(--border);border-radius:6px}}
.content{{max-width:1100px;margin:0 auto;padding:36px 24px}}
.page-hdr{{display:flex;align-items:center;justify-content:space-between;margin-bottom:28px}}
.page-title{{font-size:1.5rem;font-weight:800;color:var(--text)}}
.page-sub{{font-size:.84rem;color:var(--text-soft);margin-top:3px}}
.btn-new-agent{{background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;
  border:none;padding:10px 20px;border-radius:10px;font-weight:700;font-size:.87rem;
  cursor:pointer;display:flex;align-items:center;gap:8px;transition:.18s;white-space:nowrap;
  box-shadow:0 2px 6px rgba(99,102,241,.25)}}
.btn-new-agent:hover{{filter:brightness(1.12);transform:translateY(-1px);
  box-shadow:0 4px 12px rgba(99,102,241,.35)}}
.agents-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:18px}}
.agent-card{{background:var(--bg-card);border-radius:14px;padding:20px;
  display:flex;flex-direction:column;transition:.2s;border:1px solid var(--border);
  box-shadow:0 1px 3px rgba(15,23,42,.04)}}
.agent-card:hover{{border-color:var(--border-soft);transform:translateY(-2px);
  box-shadow:0 8px 24px rgba(15,23,42,.08)}}
.btn-card-primary{{flex:1;background:var(--brand);color:#fff;text-decoration:none;
  padding:8px 14px;border-radius:8px;font-size:.82rem;font-weight:700;text-align:center;
  transition:.15s;display:block}}
.btn-card-primary:hover{{background:var(--brand-hover);filter:brightness(1.05)}}
.btn-card-sec{{background:var(--bg-soft);color:var(--text-soft);border:1px solid var(--border);
  padding:8px 12px;border-radius:8px;font-size:.85rem;cursor:pointer;transition:.15s}}
.btn-card-sec:hover{{background:var(--bg);color:var(--text);border-color:var(--border-soft)}}
/* Wizard modal */
.modal-overlay{{position:fixed;inset:0;background:rgba(15,23,42,.55);z-index:1000;
  display:flex;align-items:center;justify-content:center;padding:20px;backdrop-filter:blur(2px)}}
.modal{{background:var(--bg-card);border-radius:16px;width:100%;max-width:620px;
  max-height:90vh;overflow-y:auto;border:1px solid var(--border);
  box-shadow:0 20px 50px rgba(15,23,42,.15)}}
.modal-hdr{{padding:20px 24px 0;display:flex;align-items:center;justify-content:space-between;
  border-bottom:1px solid var(--border);padding-bottom:16px}}
.modal-title{{font-weight:800;font-size:1.05rem;color:var(--text)}}
.modal-close{{background:none;border:none;color:var(--text-muted);font-size:1.3rem;cursor:pointer;
  padding:4px 8px;border-radius:6px;transition:.15s}}
.modal-close:hover{{background:var(--bg-soft);color:var(--text)}}
.modal-body{{padding:24px}}
.step-indicator{{display:flex;gap:6px;margin-bottom:20px}}
.step-dot{{width:28px;height:4px;border-radius:2px;background:var(--border);transition:.3s}}
.step-dot.done{{background:#10b981}}.step-dot.active{{background:var(--brand)}}
.step-label{{font-size:.75rem;color:var(--text-soft);margin-bottom:16px}}
.wiz-field{{margin-bottom:16px}}
.wiz-label{{font-size:.8rem;font-weight:600;color:var(--text-soft);margin-bottom:6px;display:block}}
.wiz-inp{{width:100%;background:var(--bg);border:1.5px solid var(--border);border-radius:8px;
  color:var(--text);padding:9px 12px;font-size:.87rem;font-family:inherit;outline:none;transition:.15s}}
.wiz-inp:focus{{border-color:var(--brand)}}
.wiz-inp::placeholder{{color:var(--text-muted)}}
textarea.wiz-inp{{resize:vertical;min-height:120px}}
.wiz-type-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}}
.wiz-type-btn{{border:2px solid var(--border);border-radius:10px;padding:10px 8px;text-align:center;
  cursor:pointer;background:var(--bg);color:var(--text-soft);font-size:.78rem;line-height:1.4;
  transition:.18s;user-select:none}}
.wiz-type-btn:hover{{border-color:var(--brand);background:rgba(99,102,241,.05)}}
.wiz-type-btn.selected{{border-color:var(--brand);background:rgba(99,102,241,.08);color:var(--brand);font-weight:700}}
.wiz-type-icon{{font-size:1.4rem;margin-bottom:4px}}
.wiz-emoji-grid{{display:flex;flex-wrap:wrap;gap:8px}}
.wiz-emoji-btn{{width:38px;height:38px;border:2px solid var(--border);border-radius:8px;
  background:var(--bg);font-size:1.2rem;cursor:pointer;display:flex;align-items:center;
  justify-content:center;transition:.15s}}
.wiz-emoji-btn.selected,.wiz-emoji-btn:hover{{border-color:var(--brand)}}
.color-swatches{{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px}}
.color-swatch{{width:28px;height:28px;border-radius:50%;cursor:pointer;
  border:3px solid transparent;transition:.15s}}
.color-swatch.selected{{border-color:var(--text);transform:scale(1.15)}}
.modal-footer{{display:flex;justify-content:space-between;padding:0 24px 20px;gap:10px}}
.btn-wiz-prev{{background:var(--bg);color:var(--text-soft);border:1px solid var(--border);
  padding:9px 18px;border-radius:8px;font-size:.85rem;cursor:pointer;transition:.15s}}
.btn-wiz-prev:hover{{background:var(--bg-soft);color:var(--text);border-color:var(--border-soft)}}
.btn-wiz-next{{background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;
  border:none;padding:9px 20px;border-radius:8px;font-size:.85rem;font-weight:700;
  cursor:pointer;transition:.15s;flex:1}}
.btn-wiz-next:hover{{filter:brightness(1.1)}}
.btn-wiz-next:disabled{{opacity:.5;cursor:not-allowed}}
.wiz-result{{padding:10px 14px;border-radius:8px;font-size:.83rem;margin-top:10px;display:none}}
.wiz-result.ok{{background:#ecfdf5;color:#047857;border:1px solid #a7f3d0}}
.wiz-result.err{{background:#fef2f2;color:#b91c1c;border:1px solid #fecaca}}
html.dark .wiz-result.ok{{background:#052e16;color:#4ade80;border-color:#15803d}}
html.dark .wiz-result.err{{background:#1a0a0a;color:#f87171;border-color:#991b1b}}
/* Toggle */
.tog-sw{{position:relative;width:38px;height:22px;flex-shrink:0}}
.tog-sw input{{opacity:0;width:0;height:0;position:absolute}}
.tog-slider{{position:absolute;inset:0;border-radius:22px;background:var(--border);cursor:pointer;transition:.2s}}
.tog-slider:before{{content:'';position:absolute;width:16px;height:16px;border-radius:50%;
  left:3px;bottom:3px;background:#fff;transition:.2s;box-shadow:0 1px 2px rgba(0,0,0,.15)}}
.tog-sw input:checked+.tog-slider{{background:#10b981}}
.tog-sw input:checked+.tog-slider:before{{transform:translateX(16px)}}
.toggle-row{{display:flex;align-items:center;justify-content:space-between;
  padding:10px 0;border-bottom:1px solid var(--border-soft)}}
.toggle-row:last-child{{border:none}}
.toggle-lbl{{font-size:.84rem;color:var(--text);font-weight:600}}
.toggle-desc{{font-size:.74rem;color:var(--text-soft);margin-top:2px}}
/* Vars table */
.vars-tbl{{width:100%;border-collapse:collapse;font-size:.82rem}}
.vars-tbl td{{padding:5px 4px;border-bottom:1px solid var(--border-soft);vertical-align:middle}}
.var-key-inp{{font-family:monospace;font-size:.78rem;font-weight:700;color:var(--brand);
  border:1px solid var(--border);border-radius:6px;padding:5px 8px;width:100%;background:var(--bg)}}
.var-val-inp{{border:1px solid var(--border);border-radius:6px;padding:5px 8px;width:100%;
  background:var(--bg);color:var(--text);font-size:.82rem}}
.var-key-inp:focus,.var-val-inp:focus{{outline:none;border-color:var(--brand)}}
.var-del-btn{{background:none;border:none;color:#ef4444;cursor:pointer;font-size:.95rem;padding:4px 7px}}
/* Agent pills cambian colores según tema */
html.dark .agent-pill{{background:var(--pill-bg-dark)!important;color:var(--pill-c-dark)!important}}
</style>
</head>
<body>

<!-- TOPBAR -->
<div class="topbar">
  <div class="voco-logo">
    <div class="voco-logo-ic">🔊</div>
    <div class="voco-logo-txt">Vo<span>co</span></div>
  </div>
  <div class="topbar-right">
    {_build_user_topbar(user)}
    <button type="button" onclick="vocoToggleTheme()" title="Cambiar tema"
      aria-label="Cambiar tema claro/oscuro"
      style="background:transparent;border:1px solid var(--border);color:var(--text-soft);
        width:32px;height:32px;border-radius:6px;cursor:pointer;
        display:inline-flex;align-items:center;justify-content:center;transition:.15s"
      onmouseover="this.style.color='var(--text)';this.style.borderColor='var(--border-soft)'"
      onmouseout="this.style.color='var(--text-soft)';this.style.borderColor='var(--border)'">
      <i data-lucide="sun"  class="hidden dark:inline-block" style="width:16px;height:16px"></i>
      <i data-lucide="moon" class="inline-block dark:hidden" style="width:16px;height:16px"></i>
    </button>
    <a href="/inbox/logout" style="color:var(--text-soft);font-size:.76rem;text-decoration:none;
      padding:4px 10px;border:1px solid var(--border);border-radius:6px">Salir</a>
  </div>
</div>

<div class="content">
  <div class="page-hdr">
    <div>
      <div class="page-title">Mis agentes</div>
      <div class="page-sub">{len(agents)} agente{'s' if len(agents) != 1 else ''} configurado{'s' if len(agents) != 1 else ''}</div>
    </div>
    <button class="btn-new-agent" onclick="abrirWizard()">
      ＋ Nuevo agente
    </button>
  </div>

  <div class="agents-grid">
    {cards_html}
  </div>
</div>

<!-- WIZARD MODAL -->
<div class="modal-overlay" id="wizard-overlay" style="display:none" onclick="if(event.target===this)cerrarWizard()">
  <div class="modal" id="wizard-modal">
    <div class="modal-hdr">
      <div class="modal-title" id="wiz-title">Paso 1 de 6 — Identidad</div>
      <button class="modal-close" onclick="cerrarWizard()">✕</button>
    </div>
    <div class="modal-body" id="wiz-body">
      <!-- contenido inyectado por JS -->
    </div>
    <div class="modal-footer">
      <button class="btn-wiz-prev" id="wiz-prev" onclick="wizPrev()">← Atrás</button>
      <button class="btn-wiz-next" id="wiz-next" onclick="wizNext()">Siguiente →</button>
    </div>
  </div>
</div>

<script>
var _PROMPT_TEMPLATES = {templates_js};
var _wizStep = 1;
var _wizData = {{}};
var _wizPropTypes = ['productos','servicios','restaurante','salud','personalizado'];

/* ── Wizard ── */
function abrirWizard() {{
  _wizStep = 1;
  _wizData = {{business_type:'productos',emoji:'🤖',color:'#6366f1',
    modules:{{shopify_catalog:true,cart_orders:true,client_memory:true,campaign_context:true}}}};
  renderWizStep();
  document.getElementById('wizard-overlay').style.display = 'flex';
}}

function cerrarWizard() {{
  document.getElementById('wizard-overlay').style.display = 'none';
}}

function wizDots() {{
  var dots = '';
  for(var i=1;i<=6;i++) {{
    var cls = i < _wizStep ? 'done' : (i === _wizStep ? 'active' : '');
    dots += '<div class="step-dot '+cls+'"></div>';
  }}
  return dots;
}}

var _WIZ_TITLES = ['','Identidad del negocio','WhatsApp (Meta)','Prompt del agente',
  'Variables del negocio','Integraciones','Activar agente'];

function renderWizStep() {{
  document.getElementById('wiz-title').textContent = 'Paso '+_wizStep+' de 6 — '+_WIZ_TITLES[_wizStep];
  document.getElementById('wiz-prev').style.display = _wizStep === 1 ? 'none' : '';
  document.getElementById('wiz-next').textContent = _wizStep === 6 ? '🚀 Crear agente' : 'Siguiente →';
  var body = document.getElementById('wiz-body');
  var dots = '<div class="step-indicator">'+wizDots()+'</div>';

  if (_wizStep === 1) {{
    var types = [['productos','🛍','Productos físicos'],['servicios','🔧','Servicios'],
                 ['restaurante','🍽','Restaurante'],['salud','💊','Salud/Belleza'],
                 ['personalizado','⚙','Personalizado']];
    var typeBtns = types.map(function(t) {{
      var sel = (_wizData.business_type===t[0]) ? ' selected' : '';
      return '<div class="wiz-type-btn'+sel+'" data-type="'+t[0]+'" onclick="selType(this)"><div class="wiz-type-icon">'+t[1]+'</div>'+t[2]+'</div>';
    }}).join('');
    var emojis = ['🤖','🌿','🔧','🛍','🍽','💊','✨','🚀','💼','🎯','🌟','🔊'];
    var emojiGrid = emojis.map(function(e) {{
      var sel = (_wizData.emoji===e) ? ' selected' : '';
      return '<button class="wiz-emoji-btn'+sel+'" data-emoji="'+e+'" onclick="selEmoji(this,this.dataset.emoji)" type="button">'+e+'</button>';
    }}).join('');
    var swatches = ['#22c55e','#6366f1','#f59e0b','#ef4444','#ec4899','#06b6d4','#8b5cf6','#14b8a6','#f97316'];
    var swatchHtml = swatches.map(function(c) {{
      var sel = (_wizData.color===c) ? ' selected' : '';
      return '<div class="color-swatch'+sel+'" style="background:'+c+'" data-color="'+c+'" onclick="selColor(this,this.dataset.color)"></div>';
    }}).join('');
    body.innerHTML = dots +
      '<div class="wiz-field"><label class="wiz-label">Nombre del negocio *</label>'+
      '<input class="wiz-inp" id="wiz-name" placeholder="Ej: Salon Bella, TallerMec, Pizzería Luna" value="'+((_wizData.name)||'')+'"></div>'+
      '<div class="wiz-field"><label class="wiz-label">Tipo de negocio *</label>'+
      '<div class="wiz-type-grid">'+typeBtns+'</div></div>'+
      '<div class="wiz-field"><label class="wiz-label">Nombre del agente *</label>'+
      '<input class="wiz-inp" id="wiz-aname" placeholder="Ej: Sofía, Carlos, Max" value="'+((_wizData.agent_name)||'')+'"></div>'+
      '<div style="display:flex;gap:16px">'+
      '<div class="wiz-field" style="flex:1"><label class="wiz-label">Emoji del agente</label>'+
      '<div class="wiz-emoji-grid">'+emojiGrid+'</div></div>'+
      '<div class="wiz-field" style="flex:1"><label class="wiz-label">Color</label>'+
      '<div class="color-swatches">'+swatchHtml+'</div></div></div>';
  }} else if (_wizStep === 2) {{
    body.innerHTML = dots +
      '<div class="wiz-field"><label class="wiz-label">Access Token de Meta *</label>'+
      '<input class="wiz-inp" id="wiz-mat" type="password" placeholder="EAAxxxxx..." value="'+((_wizData.meta_access_token)||'')+'"></div>'+
      '<div class="wiz-field"><label class="wiz-label">Phone Number ID *</label>'+
      '<input class="wiz-inp" id="wiz-mpid" placeholder="1234567890" value="'+((_wizData.phone_number_id)||'')+'"></div>'+
      '<div class="wiz-field"><label class="wiz-label">WABA ID</label>'+
      '<input class="wiz-inp" id="wiz-waba" placeholder="WhatsApp Business Account ID" value="'+((_wizData.waba_id)||'')+'"></div>'+
      '<div class="wiz-field"><label class="wiz-label">Verify Token (puedes inventar uno)</label>'+
      '<input class="wiz-inp" id="wiz-vt" placeholder="mi-agente-2024" value="'+((_wizData.verify_token)||'voco-verify-'+Math.random().toString(36).slice(2,8))+'"></div>'+
      '<button class="btn-wiz-next" style="width:100%;margin-top:4px" onclick="probarMetaWiz()" type="button">🔌 Probar conexión</button>'+
      '<div class="wiz-result" id="wiz-conn-result"></div>';
  }} else if (_wizStep === 3) {{
    var tmpl = _PROMPT_TEMPLATES[_wizData.business_type] || _PROMPT_TEMPLATES['personalizado'];
    var name = _wizData.name || 'Mi Negocio';
    var aname = _wizData.agent_name || 'Agente';
    tmpl = tmpl.replace(/\\{{NOMBRE_AGENTE\\}}/g,aname).replace(/\\{{NOMBRE_NEGOCIO\\}}/g,name);
    body.innerHTML = dots +
      '<p style="font-size:.78rem;color:#64748b;margin-bottom:12px">'+
      'Prompt generado según el tipo de negocio. Puedes editarlo ahora o ajustarlo después en la pestaña Prompt.</p>'+
      '<div class="wiz-field"><label class="wiz-label">Descripción del negocio (se incluirá en el prompt)</label>'+
      '<textarea class="wiz-inp" id="wiz-desc" style="height:80px" placeholder="Ej: Ofrecemos servicios de corte, coloración y tratamientos capilares...">'+((_wizData.descripcion)||'')+'</textarea></div>'+
      '<div class="wiz-field"><label class="wiz-label">Horario de atención</label>'+
      '<input class="wiz-inp" id="wiz-horario" placeholder="Ej: Lunes a Sábado 9am-7pm" value="'+((_wizData.horario)||'')+'"></div>'+
      '<div class="wiz-field"><label class="wiz-label">Prompt del agente</label>'+
      '<textarea class="wiz-inp" id="wiz-prompt" style="height:200px;font-family:monospace;font-size:.78rem">'+he(tmpl)+'</textarea></div>';
  }} else if (_wizStep === 4) {{
    var filas = '';
    var varsObj = _wizData.business_vars || {{}};
    Object.keys(varsObj).forEach(function(k) {{
      filas += varRow(k, varsObj[k]);
    }});
    body.innerHTML = dots +
      '<p style="font-size:.78rem;color:#64748b;margin-bottom:12px">'+
      'Define variables que puedes usar en el prompt como <code style="color:#818cf8">{{HORARIO}}</code></p>'+
      '<table class="vars-tbl"><thead><tr><th style="color:#64748b;padding:6px 4px;text-align:left">Variable</th>'+
      '<th style="color:#64748b;padding:6px 4px;text-align:left">Valor</th><th></th></tr></thead>'+
      '<tbody id="wiz-vars-body">'+filas+'</tbody></table>'+
      '<button onclick="agregarVarWiz()" type="button" style="margin-top:10px;background:#0f172a;'+
      'border:1px solid #334155;color:#94a3b8;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:.8rem">+ Agregar variable</button>';
  }} else if (_wizStep === 5) {{
    var mods = _wizData.modules || {{}};
    function togRow(key, label, desc) {{
      var chk = (key in mods) ? mods[key] : true;
      return '<div class="toggle-row"><div><div class="toggle-lbl">'+label+'</div>'+
        '<div class="toggle-desc">'+desc+'</div></div>'+
        '<label class="tog-sw"><input type="checkbox" id="wtog-'+key+'"'+(chk?' checked':'')+'>'+
        '<span class="tog-slider"></span></label></div>';
    }}
    body.innerHTML = dots +
      '<p style="font-size:.78rem;color:#64748b;margin-bottom:14px">Activa los módulos que apliquen a tu tipo de negocio.</p>'+
      togRow('shopify_catalog','🛒 Catálogo Shopify','Inyecta el catálogo en el contexto del agente')+
      togRow('cart_orders','🛍 Carrito y pedidos','Muestra carrito activo y pedidos pendientes')+
      togRow('client_memory','🧠 Memoria de clientes','Recuerda datos y pedidos previos')+
      togRow('campaign_context','📣 Contexto de campaña','Sabe a qué difusión responde el cliente');
  }} else if (_wizStep === 6) {{
    var name = _wizData.name || '—';
    var aname = _wizData.agent_name || '—';
    var btype = _wizData.business_type || '—';
    body.innerHTML = dots +
      '<div style="background:#052e16;border:1px solid #15803d;border-radius:10px;padding:16px;margin-bottom:16px">'+
      '<div style="font-size:.84rem;font-weight:700;color:#4ade80;margin-bottom:10px">✅ Resumen del agente</div>'+
      '<div style="font-size:.82rem;color:#cbd5e1;line-height:2">'+
      '<b>Negocio:</b> '+he(name)+'<br>'+
      '<b>Agente:</b> '+he(aname)+' &nbsp; <b>Tipo:</b> '+he(btype)+'<br>'+
      '<b>Phone Number ID:</b> '+he(_wizData.phone_number_id||'(no configurado)')+'<br>'+
      '</div></div>'+
      '<div style="font-size:.8rem;color:#64748b;line-height:1.7">'+
      'Una vez creado el agente:<br>'+
      '1. Configura el webhook de Meta apuntando a <code style="color:#818cf8">https://tu-app.railway.app/webhook</code><br>'+
      '2. Suscríbete al campo <code style="color:#818cf8">messages</code><br>'+
      '3. El agente comenzará a responder cuando reciba el primer mensaje.</div>'+
      '<div class="wiz-result" id="wiz-create-result"></div>';
  }}
}}

function selType(el) {{
  document.querySelectorAll('.wiz-type-btn').forEach(function(b){{b.classList.remove('selected')}});
  el.classList.add('selected');
  _wizData.business_type = el.getAttribute('data-type');
}}

function selEmoji(el, e) {{
  document.querySelectorAll('.wiz-emoji-btn').forEach(function(b){{b.classList.remove('selected')}});
  el.classList.add('selected');
  _wizData.emoji = e;
}}

function selColor(el, c) {{
  document.querySelectorAll('.color-swatch').forEach(function(b){{b.classList.remove('selected')}});
  el.classList.add('selected');
  _wizData.color = c;
}}

function he(s) {{
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}

function varRow(k, v) {{
  return '<tr><td><input class="var-key-inp" value="'+he(k)+'" placeholder="CLAVE" '+
    'oninput="this.value=this.value.toUpperCase().replace(/\\\\s/g,\\'_\\')"></td>'+
    '<td><input class="var-val-inp" value="'+he(v)+'" placeholder="Valor"></td>'+
    '<td><button class="var-del-btn" onclick="this.closest(\\'tr\\').remove()" type="button">✕</button></td></tr>';
}}

function agregarVarWiz() {{
  var tbody = document.getElementById('wiz-vars-body');
  if(tbody) {{
    var tr = document.createElement('tr');
    tr.innerHTML = varRow('','');
    tbody.appendChild(tr);
  }}
}}

function _recogerVarsWiz() {{
  var vars = {{}};
  document.querySelectorAll('#wiz-vars-body tr').forEach(function(tr) {{
    var k = (tr.querySelector('.var-key-inp').value||'').trim().toUpperCase().replace(/\\s/g,'_');
    var v = (tr.querySelector('.var-val-inp').value||'').trim();
    if(k && v) vars[k] = v;
  }});
  return vars;
}}

function _generarSlug(name) {{
  return name.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'')
    .replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,30);
}}

async function probarMetaWiz() {{
  var at = (document.getElementById('wiz-mat').value||'').trim();
  var pid = (document.getElementById('wiz-mpid').value||'').trim();
  var res = document.getElementById('wiz-conn-result');
  if(!at||!pid){{ res.className='wiz-result err'; res.textContent='Completa el Token y el Phone Number ID'; res.style.display=''; return; }}
  res.className='wiz-result'; res.textContent='🔄 Probando...'; res.style.display='';
  try {{
    var r = await fetch('/inbox/api/config/test/meta', {{
      method:'POST', credentials:'include',
      headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{META_ACCESS_TOKEN:at, META_PHONE_NUMBER_ID:pid}})
    }});
    var d = await r.json();
    if(d.ok){{ res.className='wiz-result ok'; res.textContent='✅ '+( d.msg||'Conexión exitosa'); }}
    else {{ res.className='wiz-result err'; res.textContent='⚠️ '+(d.error||'No se pudo conectar'); }}
  }} catch(e) {{ res.className='wiz-result err'; res.textContent='Error de red: '+e; }}
}}

async function wizNext() {{
  // Guardar datos del paso actual antes de avanzar
  if(_wizStep===1) {{
    var name = (document.getElementById('wiz-name').value||'').trim();
    var aname = (document.getElementById('wiz-aname').value||'').trim();
    if(!name||!aname){{ alert('Completa el nombre del negocio y del agente'); return; }}
    _wizData.name = name;
    _wizData.agent_name = aname;
    _wizData.slug = _generarSlug(name);
  }} else if(_wizStep===2) {{
    var at = (document.getElementById('wiz-mat').value||'').trim();
    var pid = (document.getElementById('wiz-mpid').value||'').trim();
    _wizData.meta_access_token = at;
    _wizData.phone_number_id = pid;
    _wizData.waba_id = (document.getElementById('wiz-waba').value||'').trim();
    _wizData.verify_token = (document.getElementById('wiz-vt').value||'').trim();
  }} else if(_wizStep===3) {{
    _wizData.prompt = (document.getElementById('wiz-prompt').value||'').trim();
    _wizData.descripcion = (document.getElementById('wiz-desc').value||'').trim();
    _wizData.horario = (document.getElementById('wiz-horario').value||'').trim();
  }} else if(_wizStep===4) {{
    _wizData.business_vars = _recogerVarsWiz();
  }} else if(_wizStep===5) {{
    _wizData.modules = {{
      shopify_catalog: document.getElementById('wtog-shopify_catalog').checked,
      cart_orders:     document.getElementById('wtog-cart_orders').checked,
      client_memory:   document.getElementById('wtog-client_memory').checked,
      campaign_context:document.getElementById('wtog-campaign_context').checked,
    }};
  }} else if(_wizStep===6) {{
    // Crear el agente
    await crearAgente();
    return;
  }}
  if(_wizStep < 6) {{ _wizStep++; renderWizStep(); }}
}}

function wizPrev() {{
  if(_wizStep > 1) {{ _wizStep--; renderWizStep(); }}
}}

async function crearAgente() {{
  var btn = document.getElementById('wiz-next');
  var res = document.getElementById('wiz-create-result');
  btn.disabled = true; btn.textContent = '⏳ Creando...';
  try {{
    // 1. Crear agente base
    var r1 = await fetch('/inbox/api/agents', {{
      method:'POST', credentials:'include',
      headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{
        name: _wizData.name,
        slug: _wizData.slug,
        agent_name: _wizData.agent_name,
        business_type: _wizData.business_type,
        phone_number_id: _wizData.phone_number_id || '',
        waba_id: _wizData.waba_id || '',
        color: _wizData.color || '#6366f1',
        emoji: _wizData.emoji || '🤖',
      }})
    }});
    var d1 = await r1.json();
    if(!d1.ok) throw new Error(d1.error || 'No se pudo crear el agente');
    var newId = d1.agent.id;
    var newSlug = d1.agent.slug;

    // 2. Guardar prompt + vars + módulos + meta credentials
    await fetch('/inbox/api/prompt/save?agent_id='+newId, {{
      method:'POST', credentials:'include',
      headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{
        prompt: _wizData.prompt || '',
        business_vars: _wizData.business_vars || {{}},
        business_type: _wizData.business_type,
        active_modules: _wizData.modules || {{}},
      }})
    }});

    // 3. Guardar credenciales Meta para este agente
    if(_wizData.meta_access_token || _wizData.phone_number_id) {{
      await fetch('/inbox/api/config/save?agent_id='+newId, {{
        method:'POST', credentials:'include',
        headers:{{'Content-Type':'application/json'}},
        body: JSON.stringify({{
          META_ACCESS_TOKEN:    _wizData.meta_access_token || '',
          META_PHONE_NUMBER_ID: _wizData.phone_number_id  || '',
          META_WABA_ID:         _wizData.waba_id          || '',
          META_VERIFY_TOKEN:    _wizData.verify_token      || '',
        }})
      }});
    }}

    // 4. Activar el agente
    await fetch('/inbox/api/agents/'+newId+'/activate', {{
      method:'POST', credentials:'include'
    }});

    res.className='wiz-result ok';
    res.textContent = '✅ ¡Agente creado! Redirigiendo al panel...';
    res.style.display='';
    setTimeout(function(){{ window.location.href = '/inbox/'+newSlug; }}, 1500);
  }} catch(e) {{
    res.className='wiz-result err';
    res.textContent = '⚠️ Error: '+String(e);
    res.style.display='';
    btn.disabled=false; btn.textContent='🚀 Crear agente';
  }}
}}

async function editarAgente(agentId) {{
  window.location.href = '/inbox/' + agentId;
}}

</script>
</body>
</html>""".replace("__VOCO_DS__", _DESIGN_SYSTEM_HEAD)
