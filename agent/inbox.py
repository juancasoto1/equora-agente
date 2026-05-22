"""
agent/inbox.py — Panel de administración SaaS: inbox de conversaciones de Andrea
Login: POST /inbox/login  |  Acceso: /inbox  |  Logout: /inbox/logout
"""

# ── Página de login ──────────────────────────────────────────────────────────
def obtener_login_html(error: bool = False) -> str:
    err = '<span class="err">Contraseña incorrecta. Intenta de nuevo.</span>' if error else ''
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Inbox — Equora</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{min-height:100vh;background:#0f1923;display:flex;align-items:center;
     justify-content:center;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}}
.box{{background:#1b2631;border-radius:16px;padding:40px 36px;width:340px;text-align:center;
      box-shadow:0 8px 40px rgba(0,0,0,.5);border:1px solid #243342}}
.ic{{font-size:2.8rem;margin-bottom:10px}}
h2{{color:#e9edef;font-size:1.15rem;font-weight:700;margin-bottom:4px}}
.sub{{color:#8696a0;font-size:.82rem;margin-bottom:28px}}
.err{{color:#ef5350;font-size:.82rem;display:block;margin-bottom:12px}}
input{{width:100%;padding:12px 16px;border-radius:10px;border:1.5px solid #2c3e50;
       background:#243342;color:#e9edef;font-size:.92rem;outline:none;margin-bottom:14px}}
input:focus{{border-color:#00a884}}
input::placeholder{{color:#8696a0}}
button{{width:100%;padding:13px;border-radius:10px;border:none;background:#00a884;
        color:#fff;font-size:.95rem;font-weight:700;cursor:pointer;transition:opacity .2s}}
button:hover{{opacity:.88}}
</style>
</head>
<body>
<div class="box">
  <div class="ic">🤖</div>
  <h2>Andrea — Panel de Control</h2>
  <p class="sub">Equora Distribuciones</p>
  {err}
  <form method="POST" action="/inbox/login">
    <input type="password" name="password" placeholder="Contraseña de acceso" autofocus required>
    <button type="submit">Entrar →</button>
  </form>
</div>
</body>
</html>"""


# ── Panel principal ──────────────────────────────────────────────────────────
_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>Andrea · Equora</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;overflow:hidden}
/* ── WA Dark theme vars (usados en sección conversaciones) ── */
:root{
  --sb:#202c33;--hd:#2a3942;--bbl:#005c4b;--bbr:#202c33;
  --az:#00a884;--tx:#e9edef;--ts:#8696a0;--bd:#313d45;--hl:#2a3942;--red:#e53935;
}

/* ══════════════════════════════════════════════
   SHELL EXTERIOR: topbar + cuerpo
   ══════════════════════════════════════════════ */
#shell{display:flex;flex-direction:column;height:100vh;overflow:hidden;background:#0f1923}

/* ── TOPBAR ── */
#topbar{
  height:56px;background:#1b2631;display:flex;align-items:center;
  padding:0 20px;gap:14px;flex-shrink:0;
  border-bottom:1px solid #0e1921;
}
#topbar .logo{display:flex;align-items:center;gap:8px}
#topbar .logo-ic{width:32px;height:32px;background:var(--az);border-radius:8px;
  display:flex;align-items:center;justify-content:center;font-size:1rem}
#topbar .logo-txt{font-size:.95rem;font-weight:700;color:#e9edef}
#topbar .logo-sub{font-size:.72rem;color:#8696a0;margin-left:4px}
#topbar .badge{background:var(--az);color:#fff;font-size:.68rem;padding:2px 8px;
  border-radius:12px;font-weight:600;margin-left:4px}
.topbar-spacer{flex:1}
#logout-top{background:none;border:1px solid #2c3e50;color:#8696a0;
  border-radius:8px;padding:5px 14px;font-size:.78rem;cursor:pointer;
  transition:all .15s}
#logout-top:hover{border-color:#8696a0;color:#e9edef}

/* ── BODY: nav + main ── */
#body{display:flex;flex:1;overflow:hidden}

/* ── LEFT NAV ── */
#nav{
  width:220px;min-width:220px;background:#162030;display:flex;
  flex-direction:column;flex-shrink:0;border-right:1px solid #0e1921;
  padding-top:8px;
}
.nav-section{padding:14px 16px 6px;font-size:.65rem;color:#4a6078;
  text-transform:uppercase;letter-spacing:.08em;font-weight:600}
.nav-item{
  display:flex;align-items:center;gap:10px;padding:10px 18px;
  color:#8696a0;cursor:pointer;font-size:.875rem;font-weight:500;
  transition:all .12s;border-left:3px solid transparent;user-select:none;
}
.nav-item:hover{background:rgba(255,255,255,.04);color:#c5cdd2}
.nav-item.active{background:rgba(0,168,132,.10);color:var(--az);border-left-color:var(--az)}
.nav-item .ni{font-size:1rem;width:22px;text-align:center;flex-shrink:0}
.nav-item .nb{font-size:.65rem;background:var(--red);color:#fff;
  border-radius:8px;padding:1px 5px;font-weight:700;margin-left:auto}
.nav-footer{margin-top:auto;padding:16px 18px;border-top:1px solid #1e2e3d}
.nav-footer small{font-size:.7rem;color:#4a6078}

/* ── MAIN: contenedor de secciones ── */
#main{flex:1;overflow:hidden;display:flex;flex-direction:column}

/* Secciones (display:none por defecto) */
.sec{display:none;flex:1;overflow:hidden}
.sec.active{display:flex}

/* ══════════════════════════════════════════════
   SECCIÓN: CONVERSACIONES (dark WhatsApp theme)
   ══════════════════════════════════════════════ */
#sec-conversaciones{flex-direction:row;background:#0b141a}

/* sidebar conversaciones */
#sidebar{width:350px;min-width:350px;display:flex;flex-direction:column;
  background:var(--sb);border-right:1px solid var(--bd)}
#chat-area{flex:1;display:flex;flex-direction:column;background:#0b141a;min-width:0}

@media(max-width:720px){
  #sidebar{width:100%;min-width:unset}
  #sidebar.oculto{display:none}
  #chat-area.oculto{display:none}
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

/* chat vacío */
#empty{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;color:var(--ts)}
#empty .eic{font-size:3.5rem;opacity:.25}
#empty p{font-size:.88rem}

/* chat activo */
#cv{display:none;flex-direction:column;height:100%}
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

#msgs{flex:1;overflow-y:auto;padding:12px 16px;display:flex;flex-direction:column;gap:6px}
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
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.form-grid.full{grid-template-columns:1fr}
.f-group{display:flex;flex-direction:column;gap:6px}
.f-label{font-size:.78rem;font-weight:600;color:#4a5568;text-transform:uppercase;letter-spacing:.04em}
.f-inp,.f-sel,.f-ta{
  padding:9px 13px;border-radius:8px;border:1.5px solid #e0e4e8;
  font-size:.88rem;color:#2d3748;background:#fff;outline:none;font-family:inherit;
  transition:border-color .15s;
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

/* ── DIFUSIÓN inline (vista full-page) ── */
#dif-split{display:flex;gap:24px;align-items:flex-start}
#dif-form-col{flex:1;min-width:0}
#dif-hist-col{width:340px;flex-shrink:0}
/* preview */
#dif-preview-box{background:#f8f9fa;border-radius:8px;padding:12px 14px;
  font-size:.84rem;line-height:1.5;color:#2d3748;white-space:pre-wrap;min-height:52px;
  border:1px solid #e0e4e8}
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
#dif-csv-fname{font-size:.76rem;color:#6b7a8d;margin-bottom:4px}
.btn-dl-csv{display:flex;align-items:center;gap:5px;background:#fff;border:1.5px solid #e0e4e8;
  border-radius:8px;padding:8px 14px;color:#6b7a8d;font-size:.83rem;cursor:pointer;
  font-weight:600;transition:all .2s;white-space:nowrap}
.btn-dl-csv:hover{border-color:var(--az);color:var(--az)}
/* vars */
#dif-vars{display:flex;flex-direction:column;gap:8px}

/* ── PLANTILLAS ── */
.tpl-status-approved{color:#155724;font-weight:600}
.tpl-status-pending{color:#856404}
.tpl-status-rejected{color:#721c24}
.tpl-status-paused{color:#495057}

/* ── CONFIGURACIÓN ── */
.config-item{display:flex;align-items:center;gap:12px;padding:14px 20px;border-bottom:1px solid #f0f2f5}
.config-item:last-child{border-bottom:none}
.config-key{font-size:.84rem;font-weight:600;color:#2d3748;flex:1}
.config-val{font-size:.82rem;color:#6b7a8d;background:#f0f2f5;border-radius:6px;padding:3px 10px;
  font-family:monospace;max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.config-ok{color:var(--az);font-weight:700;font-size:.84rem}
.config-miss{color:var(--red);font-weight:700;font-size:.84rem}

/* ── loading spinner ── */
.loading-txt{color:#6b7a8d;font-size:.85rem;padding:32px;text-align:center}
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
      <div class="nav-item active" data-sec="conversaciones" onclick="showSec('conversaciones')">
        <span class="ni">💬</span> Conversaciones
        <span class="nb" id="conv-badge" style="display:none">0</span>
      </div>
      <div class="nav-item" data-sec="difusiones" onclick="showSec('difusiones')">
        <span class="ni">📢</span> Difusiones
      </div>
      <div class="nav-section">Gestión</div>
      <div class="nav-item" data-sec="plantillas" onclick="showSec('plantillas')">
        <span class="ni">📋</span> Plantillas
      </div>
      <div class="nav-item" data-sec="metricas" onclick="showSec('metricas')">
        <span class="ni">📊</span> Métricas
      </div>
      <div class="nav-section">Sistema</div>
      <div class="nav-item" data-sec="configuracion" onclick="showSec('configuracion')">
        <span class="ni">⚙️</span> Configuración
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
            <input id="srinput" placeholder="Buscar por nombre o número..." oninput="filtrar()">
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
              <button id="back" onclick="volverLista()">‹</button>
              <div class="av2">👤</div>
              <div class="inf2">
                <div class="nm2" id="cnm">—</div>
                <div class="st2" id="cst">—</div>
              </div>
            </div>

            <div id="mbar">
              <span class="lbl">Andrea responde</span>
              <label class="tog">
                <input type="checkbox" id="togInput" onchange="toggleModo()">
                <span class="sl"></span>
              </label>
              <span class="lbl">Modo humano</span>
              <span id="mlbl">● Tú estás respondiendo</span>
            </div>

            <div id="msgs"></div>

            <div id="ib">
              <textarea id="ti" rows="1" placeholder="Escribe un mensaje y presiona Enter..."
                onkeydown="onKey(event)" oninput="autoResize()"></textarea>
              <button id="sendbtn" onclick="sendMsg()">➤</button>
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
          <div id="dif-split">

            <!-- Formulario nueva difusión -->
            <div id="dif-form-col">
              <div class="form-card">
                <div style="display:flex;align-items:center;gap:10px;margin-bottom:20px">
                  <div style="font-size:1.3rem">✉️</div>
                  <div>
                    <div style="font-weight:700;color:#1a2332;font-size:.95rem">Nueva difusión</div>
                    <div style="font-size:.78rem;color:#6b7a8d">Selecciona plantilla y destinatarios</div>
                  </div>
                </div>

                <div class="f-group" style="margin-bottom:16px">
                  <span class="f-label">Plantilla aprobada</span>
                  <select id="dif-tpl" class="f-sel" onchange="seleccionarTemplate()">
                    <option value="">Cargando plantillas...</option>
                  </select>
                </div>

                <div id="dif-vars-wrap" style="display:none;margin-bottom:16px">
                  <span class="f-label" style="display:block;margin-bottom:8px">Variables de la plantilla</span>
                  <div id="dif-vars"></div>
                </div>

                <div class="f-group" style="margin-bottom:16px">
                  <span class="f-label">Vista previa</span>
                  <div id="dif-preview-box">Selecciona una plantilla para ver la vista previa.</div>
                </div>

                <div class="f-group" style="margin-bottom:16px">
                  <span class="f-label">
                    Destinatarios
                    <span id="dif-formato-hint" style="font-weight:400;text-transform:none;letter-spacing:0">
                      — uno por línea: número,nombre
                    </span>
                  </span>
                  <div id="dif-csv-wrap">
                    <label id="dif-csv-label" for="dif-csv-input">📂 Cargar CSV</label>
                    <input type="file" id="dif-csv-input" accept=".csv,text/csv" onchange="cargarArchivoCSV(this)">
                    <button class="btn-dl-csv" onclick="descargarFormatoCSV()" type="button">⬇ Formato</button>
                  </div>
                  <div id="dif-csv-fname"></div>
                  <textarea id="dif-phones" class="f-ta" style="min-height:120px"
                    placeholder="573001234567,Juan&#10;573009876543,María&#10;573001112233,Carlos"
                    oninput="actualizarConteo()"></textarea>
                  <div id="dif-conteo" style="font-size:.75rem;color:#6b7a8d;margin-top:4px">0 destinatarios</div>
                </div>

                <div id="dif-res-box"></div>
                <div id="dif-prog-wrap">
                  <div class="prog-bar-wrap"><div class="prog-bar" id="dif-bar"></div></div>
                  <div class="prog-txt" id="dif-ptxt">Enviando...</div>
                </div>

                <div style="display:flex;gap:10px;margin-top:8px">
                  <button class="btn-primary" id="dif-sendbtn" onclick="enviarDifusion()" disabled>
                    📤 Enviar difusión
                  </button>
                </div>
              </div>
            </div><!-- /dif-form-col -->

            <!-- Historial difusiones -->
            <div id="dif-hist-col">
              <div class="tbl-wrap">
                <div class="tbl-head">
                  <h2>Historial</h2>
                  <button class="btn-secondary" style="padding:6px 14px;font-size:.8rem" onclick="cargarHistorialDif()">↺ Actualizar</button>
                </div>
                <div id="dif-hist-body" style="max-height:520px;overflow-y:auto">
                  <div class="loading-txt">Cargando...</div>
                </div>
              </div>
            </div>

          </div><!-- /dif-split -->
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
              <div class="tbl-wrap" style="margin-bottom:0">
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
                      </tr>
                    </thead>
                    <tbody id="tpl-tabla-body">
                      <tr><td colspan="5" class="loading-txt">Cargando...</td></tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <!-- Formulario crear plantilla -->
            <div style="width:360px;flex-shrink:0">
              <div class="form-card">
                <div style="font-weight:700;color:#1a2332;font-size:.95rem;margin-bottom:4px">✨ Nueva plantilla</div>
                <div style="font-size:.78rem;color:#6b7a8d;margin-bottom:18px">Se enviará a Meta para aprobación (24-48h)</div>

                <div class="form-grid" style="margin-bottom:14px">
                  <div class="f-group">
                    <span class="f-label">Nombre</span>
                    <input id="tpl-nombre" class="f-inp" placeholder="mi_plantilla" oninput="this.value=this.value.toLowerCase().replace(/[^a-z0-9_]/g,'_')">
                    <span class="f-hint">Solo letras, números y _</span>
                  </div>
                  <div class="f-group">
                    <span class="f-label">Categoría</span>
                    <select id="tpl-cat" class="f-sel">
                      <option value="MARKETING">Marketing</option>
                      <option value="UTILITY">Utilidad</option>
                      <option value="AUTHENTICATION">Autenticación</option>
                    </select>
                  </div>
                </div>

                <div class="f-group" style="margin-bottom:14px">
                  <span class="f-label">Idioma</span>
                  <select id="tpl-lang" class="f-sel">
                    <option value="es_CO">Español (Colombia)</option>
                    <option value="es">Español</option>
                    <option value="es_AR">Español (Argentina)</option>
                    <option value="es_MX">Español (México)</option>
                    <option value="en_US">English (US)</option>
                  </select>
                </div>

                <div class="f-group" style="margin-bottom:14px">
                  <span class="f-label">Encabezado <span style="font-weight:400;text-transform:none;letter-spacing:0">(opcional)</span></span>
                  <input id="tpl-header" class="f-inp" placeholder="Título del mensaje (max 60 chars)" maxlength="60">
                </div>

                <div class="f-group" style="margin-bottom:14px">
                  <span class="f-label">Cuerpo del mensaje *</span>
                  <textarea id="tpl-body" class="f-ta" placeholder="Hola {{nombre}}, tenemos una oferta especial para ti..."></textarea>
                  <span class="f-hint">Usa {{variable}} para personalizar. Ej: {{nombre}}</span>
                </div>

                <div class="f-group" style="margin-bottom:14px">
                  <span class="f-label">Pie de página <span style="font-weight:400;text-transform:none;letter-spacing:0">(opcional)</span></span>
                  <input id="tpl-footer" class="f-inp" placeholder="Responde STOP para salir" maxlength="60">
                </div>

                <div id="tpl-result" style="display:none;margin-bottom:14px;font-size:.83rem;padding:10px 14px;border-radius:8px;line-height:1.5"></div>

                <button class="btn-primary" id="tpl-crear-btn" onclick="crearPlantilla()" style="width:100%">
                  📤 Enviar a Meta para aprobación
                </button>
              </div>
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
            <p>Rendimiento de mensajes y plantillas — últimos 30 días</p>
          </div>
          <button class="btn-secondary" onclick="cargarMetricas()">↺ Actualizar</button>
        </div>
        <div class="sec-body">
          <div class="cards" id="met-cards">
            <div class="loading-txt" style="grid-column:1/-1">Cargando métricas...</div>
          </div>

          <div class="tbl-wrap">
            <div class="tbl-head">
              <h2>Analíticas por plantilla</h2>
            </div>
            <div style="overflow-x:auto">
              <table>
                <thead>
                  <tr>
                    <th>Plantilla</th>
                    <th>Enviados</th>
                    <th>Entregados</th>
                    <th>Leídos</th>
                    <th>Clics botón</th>
                    <th>% Lectura</th>
                  </tr>
                </thead>
                <tbody id="met-tpl-body">
                  <tr><td colspan="6" class="loading-txt">Cargando...</td></tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div><!-- /sec-metricas -->

      <!-- ═══════════════════════════════════════
           SECCIÓN: CONFIGURACIÓN
           ═══════════════════════════════════════ -->
      <div class="sec sec-light" id="sec-configuracion">
        <div class="sec-hdr">
          <div>
            <h1>⚙️ Configuración</h1>
            <p>Estado de las integraciones y variables del sistema</p>
          </div>
        </div>
        <div class="sec-body">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px">

            <div class="form-card">
              <div style="font-weight:700;color:#1a2332;margin-bottom:16px">🔑 Credenciales Meta</div>
              <div id="cfg-meta" class="loading-txt">Cargando...</div>
            </div>

            <div class="form-card">
              <div style="font-weight:700;color:#1a2332;margin-bottom:16px">🤖 Anthropic / IA</div>
              <div id="cfg-ai" class="loading-txt">Cargando...</div>
            </div>

            <div class="form-card">
              <div style="font-weight:700;color:#1a2332;margin-bottom:16px">🛒 Shopify</div>
              <div id="cfg-shopify" class="loading-txt">Cargando...</div>
            </div>

            <div class="form-card">
              <div style="font-weight:700;color:#1a2332;margin-bottom:16px">🚀 Próximas integraciones</div>
              <div style="color:#6b7a8d;font-size:.85rem;line-height:1.7">
                Las siguientes integraciones estarán disponibles próximamente:<br><br>
                • 📧 Email (SendGrid / Resend)<br>
                • 📅 Calendly / Google Calendar<br>
                • 🗃️ CRM (HubSpot / Pipedrive)<br>
                • 💳 Pagos en línea (Stripe / PSE)
              </div>
            </div>

          </div>
        </div>
      </div><!-- /sec-configuracion -->

    </div><!-- /main -->
  </div><!-- /body -->
</div><!-- /shell -->

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
    if (id === 'plantillas')    { cargarTablaPlantillas(); }
    if (id === 'metricas')      { cargarMetricas(); }
    if (id === 'configuracion') { cargarConfiguracion(); }
  }
}

/* ══════════════════════════════════════════════════════
   UTILS
   ══════════════════════════════════════════════════════ */
function fmt(ts) {
  if (!ts) return '';
  var d = new Date(ts.endsWith('Z') ? ts : ts + 'Z');
  var now = new Date();
  var diff = (now - d) / 1000;
  if (diff < 60) return 'ahora';
  if (diff < 3600) return Math.floor(diff / 60) + ' min';
  if (diff < 86400) return d.toLocaleTimeString('es-CO', {hour:'2-digit', minute:'2-digit'});
  return d.toLocaleDateString('es-CO', {day:'2-digit', month:'2-digit'});
}
function fmtH(ts) {
  if (!ts) return '';
  var d = new Date(ts.endsWith('Z') ? ts : ts + 'Z');
  return d.toLocaleTimeString('es-CO', {hour:'2-digit', minute:'2-digit'});
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
    var badge = c.modo_humano ? '<span class="hmbadge">HUMANO</span>' : '';
    h += '<div class="ci' + sel + '" data-tel="' + he(c.telefono) + '">'
       + '<div class="av">👤</div>'
       + '<div class="inf">'
       + '<div class="nm">' + he(nm) + '</div>'
       + '<div class="lm">' + icono + preview + '</div>'
       + '</div>'
       + '<div class="meta2"><span class="cts">' + fmt(c.timestamp) + '</span>' + badge + '</div>'
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
    h += '<div class="msg ' + cls + '">'
       + '<div class="mb">' + he(m.content) + '</div>'
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

/* ── INIT conversaciones ── */
loadConvs();
_convTimer = setInterval(loadConvs, 8000);


/* ══════════════════════════════════════════════════════
   DIFUSIÓN — templates y envío
   ══════════════════════════════════════════════════════ */
var _dif_templates = [];

async function cargarTemplates() {
  var sel = document.getElementById('dif-tpl');
  sel.innerHTML = '<option value="">Cargando...</option>';
  try {
    var r = await fetch('/inbox/broadcast/templates', {credentials:'include'});
    var d = await r.json();
    if (d.error) {
      sel.innerHTML = '<option value="">Error: ' + d.error + '</option>';
      return;
    }
    _dif_templates = d.templates || [];
    if (!_dif_templates.length) {
      sel.innerHTML = '<option value="">No hay plantillas aprobadas en Meta</option>';
      return;
    }
    sel.innerHTML = '<option value="">— Selecciona una plantilla —</option>' +
      _dif_templates.map(function(t) {
        return '<option value="' + t.name + '">' + t.name + ' (' + t.language + ')</option>';
      }).join('');
  } catch(e) {
    sel.innerHTML = '<option value="">Error cargando plantillas</option>';
  }
}

function seleccionarTemplate() {
  var name = document.getElementById('dif-tpl').value;
  var tpl  = _dif_templates.find(function(t) { return t.name === name; });
  var prev = document.getElementById('dif-preview-box');
  var varsWrap = document.getElementById('dif-vars-wrap');
  var varsDiv  = document.getElementById('dif-vars');
  var sendBtn  = document.getElementById('dif-sendbtn');

  if (!tpl) {
    prev.textContent = 'Selecciona una plantilla para ver la vista previa.';
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
        '<label style="font-size:.82rem;color:#6b7a8d;white-space:nowrap;min-width:50px">{{' + n + '}}</label>' +
        '<input class="f-inp" id="dif-var-' + n + '" style="flex:1" placeholder="Valor para {{' + n + '}}" oninput="actualizarPreview()">';
      varsDiv.appendChild(row);
    });
  } else {
    varsWrap.style.display = 'none';
  }

  actualizarPreview();
  sendBtn.disabled = !document.getElementById('dif-phones').value.trim();
}

function actualizarPreview() {
  var name = document.getElementById('dif-tpl').value;
  var tpl  = _dif_templates.find(function(t) { return t.name === name; });
  if (!tpl) return;
  var text = tpl.preview || '(Sin vista previa disponible)';
  if (tpl.variables) {
    tpl.variables.forEach(function(n) {
      var inp = document.getElementById('dif-var-' + n);
      var val = inp ? (inp.value || '{{' + n + '}}') : '{{' + n + '}}';
      text = text.split('{{' + n + '}}').join(val);
    });
  }
  document.getElementById('dif-preview-box').textContent = text;
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
  document.getElementById('dif-csv-fname').textContent = '📄 ' + file.name;
  var reader = new FileReader();
  reader.onload = function(e) {
    var texto = e.target.result;
    if (texto.charCodeAt(0) === 0xFEFF) texto = texto.slice(1);
    var lineas = texto.split(/\r?\n/).map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });
    if (!lineas.length) return;
    var primeraCol = lineas[0].split(',')[0].trim();
    var esEncabezado = isNaN(primeraCol.replace(/\D/g,'')) || primeraCol.toLowerCase() === 'telefono';
    if (esEncabezado) lineas = lineas.slice(1);
    if (!lineas.length) {
      document.getElementById('dif-csv-fname').textContent = '⚠️ El archivo no tiene datos válidos';
      return;
    }
    document.getElementById('dif-phones').value = lineas.join('\n');
    actualizarConteo();
    document.getElementById('dif-csv-fname').textContent =
      '✅ ' + file.name + ' — ' + lineas.length + ' fila(s)';
    input.value = '';
  };
  reader.onerror = function() {
    document.getElementById('dif-csv-fname').textContent = '❌ Error al leer el archivo';
  };
  reader.readAsText(file, 'UTF-8');
}

function _parsearDestinatarios() {
  var tpl  = _dif_templates.find(function(t) { return t.name === document.getElementById('dif-tpl').value; });
  var nVars = tpl ? (tpl.variables || []).length : 0;
  return document.getElementById('dif-phones').value
    .split('\n')
    .map(function(l) { return l.trim(); })
    .filter(function(l) { return l.length > 5; })
    .map(function(l) {
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
  document.getElementById('dif-conteo').textContent =
    dests.length + ' destinatario' + (dests.length === 1 ? '' : 's');
  var name = document.getElementById('dif-tpl').value;
  document.getElementById('dif-sendbtn').disabled = !name || !dests.length;
}

async function enviarDifusion() {
  var name  = document.getElementById('dif-tpl').value;
  var tpl   = _dif_templates.find(function(t) { return t.name === name; });
  if (!tpl) return;

  var recipients = _parsearDestinatarios();
  if (!recipients.length) return;

  if (tpl.variables && tpl.variables.length) {
    var sinNombre = recipients.filter(function(r) {
      return r.variables.some(function(v) { return !v || v.trim() === ''; });
    });
    if (sinNombre.length) {
      var res = document.getElementById('dif-res-box');
      res.style.display = 'block';
      res.className = 'dif-result err';
      res.textContent = '⚠️ ' + sinNombre.length + ' destinatario(s) tienen variables vacías.';
      return;
    }
  }

  var btn  = document.getElementById('dif-sendbtn');
  var prog = document.getElementById('dif-prog-wrap');
  var bar  = document.getElementById('dif-bar');
  var ptxt = document.getElementById('dif-ptxt');
  var res  = document.getElementById('dif-res-box');
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
  var box = document.getElementById('dif-hist-body');
  try {
    var r = await fetch('/inbox/difusiones/historial', {credentials:'include'});
    var d = await r.json();
    var rows = d.difusiones || [];
    if (!rows.length) {
      box.innerHTML = '<div class="loading-txt">Sin difusiones enviadas aún</div>';
      return;
    }
    var h = '<table style="width:100%"><thead><tr><th>Plantilla</th><th>Fecha</th><th>✅</th><th>❌</th></tr></thead><tbody>';
    rows.forEach(function(row) {
      var pct = row.destinatarios > 0 ? Math.round(row.enviados / row.destinatarios * 100) : 0;
      var cls = row.fallidos === 0 ? 'badge-ok' : (row.fallidos < row.destinatarios ? 'badge-warn' : 'badge-err');
      h += '<tr>'
        + '<td><b>' + he(row.template_name) + '</b><br><small style="color:#6b7a8d">' + he(row.language) + ' · ' + row.destinatarios + ' dest.</small></td>'
        + '<td style="font-size:.78rem;color:#6b7a8d">' + fmtFecha(row.created_at) + '</td>'
        + '<td><span class="' + cls + '">' + row.enviados + '</span></td>'
        + '<td style="color:' + (row.fallidos > 0 ? '#721c24' : '#6b7a8d') + '">' + row.fallidos + '</td>'
        + '</tr>';
    });
    h += '</tbody></table>';
    box.innerHTML = h;
  } catch(e) {
    box.innerHTML = '<div class="loading-txt" style="color:#721c24">Error cargando historial</div>';
  }
}

/* ══════════════════════════════════════════════════════
   PLANTILLAS
   ══════════════════════════════════════════════════════ */
async function cargarTablaPlantillas() {
  var tbody = document.getElementById('tpl-tabla-body');
  tbody.innerHTML = '<tr><td colspan="5" class="loading-txt">Cargando...</td></tr>';
  try {
    var r = await fetch('/inbox/broadcast/templates', {credentials:'include'});
    var d = await r.json();
    var tpls = d.templates || [];

    // También intentar traer todas (no solo aprobadas) via raw
    var rRaw = await fetch('/inbox/broadcast/templates/raw', {credentials:'include'});
    var dRaw = await rRaw.json();
    var todas = (dRaw.data || []);

    if (!todas.length && !tpls.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="loading-txt">Sin plantillas</td></tr>';
      return;
    }

    var h = '';
    todas.forEach(function(t) {
      var status = (t.status || '').toUpperCase();
      var cls = status === 'APPROVED' ? 'badge-ok' : (status === 'PENDING' ? 'badge-warn' : (status === 'REJECTED' ? 'badge-err' : 'badge-pend'));
      var lbl = status === 'APPROVED' ? 'Aprobada' : (status === 'PENDING' ? 'Pendiente' : (status === 'REJECTED' ? 'Rechazada' : status));
      var vars = '';
      var hdrFmt = '';
      (t.components || []).forEach(function(c) {
        if (c.type === 'BODY') {
          var ex = c.example || {};
          if (ex.body_text_named_params) vars = ex.body_text_named_params.map(function(p) { return '{{'+p.param_name+'}}'; }).join(', ');
          else vars = (c.text || '').match(/\{\{[^}]+\}\}/g)?.join(', ') || '—';
        }
        if (c.type === 'HEADER') hdrFmt = c.format || '—';
      });
      h += '<tr>'
        + '<td><b>' + he(t.name) + '</b></td>'
        + '<td>' + he(t.language || '') + '</td>'
        + '<td><span class="' + cls + '">' + lbl + '</span></td>'
        + '<td style="font-size:.78rem">' + he(vars || '—') + '</td>'
        + '<td style="font-size:.78rem">' + he(hdrFmt || '—') + '</td>'
        + '</tr>';
    });
    tbody.innerHTML = h || '<tr><td colspan="5" class="loading-txt">Sin plantillas</td></tr>';
  } catch(e) {
    tbody.innerHTML = '<tr><td colspan="5" class="loading-txt" style="color:#721c24">Error cargando plantillas</td></tr>';
  }
}

async function crearPlantilla() {
  var nombre  = document.getElementById('tpl-nombre').value.trim();
  var cat     = document.getElementById('tpl-cat').value;
  var lang    = document.getElementById('tpl-lang').value;
  var header  = document.getElementById('tpl-header').value.trim();
  var body    = document.getElementById('tpl-body').value.trim();
  var footer  = document.getElementById('tpl-footer').value.trim();
  var res     = document.getElementById('tpl-result');
  var btn     = document.getElementById('tpl-crear-btn');

  if (!nombre || !body) {
    res.style.display = 'block';
    res.style.cssText += ';background:#f8d7da;color:#721c24;border:1px solid #f5c6cb';
    res.textContent = '⚠️ El nombre y el cuerpo son obligatorios.';
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Enviando...';
  res.style.display = 'none';

  try {
    var r = await fetch('/inbox/plantillas/crear', {
      method: 'POST',
      credentials: 'include',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: nombre, category: cat, language: lang, header_text: header, body: body, footer: footer}),
    });
    var d = await r.json();
    res.style.display = 'block';
    if (d.ok) {
      res.style.cssText += ';background:#d4edda;color:#155724;border:1px solid #c3e6cb';
      res.textContent = '✅ Plantilla enviada a Meta — Estado: ' + (d.status || 'PENDING') + '. La aprobación puede tardar 24-48h.';
      // Limpiar form
      document.getElementById('tpl-nombre').value = '';
      document.getElementById('tpl-header').value = '';
      document.getElementById('tpl-body').value = '';
      document.getElementById('tpl-footer').value = '';
      cargarTablaPlantillas();
    } else {
      res.style.cssText += ';background:#f8d7da;color:#721c24;border:1px solid #f5c6cb';
      res.textContent = '❌ Error: ' + (d.error || 'Error desconocido');
    }
  } catch(e) {
    res.style.display = 'block';
    res.style.cssText += ';background:#f8d7da;color:#721c24;border:1px solid #f5c6cb';
    res.textContent = 'Error de conexión: ' + e.message;
  }
  btn.disabled = false;
  btn.textContent = '📤 Enviar a Meta para aprobación';
}

/* ══════════════════════════════════════════════════════
   MÉTRICAS
   ══════════════════════════════════════════════════════ */
async function cargarMetricas() {
  var cards = document.getElementById('met-cards');
  var tplBody = document.getElementById('met-tpl-body');
  cards.innerHTML = '<div class="loading-txt" style="grid-column:1/-1">Cargando métricas...</div>';
  tplBody.innerHTML = '<tr><td colspan="6" class="loading-txt">Cargando...</td></tr>';

  // Resumen general
  try {
    var r = await fetch('/inbox/metricas/resumen', {credentials:'include'});
    var d = await r.json();
    if (d.error) {
      cards.innerHTML = '<div class="loading-txt" style="grid-column:1/-1;color:#721c24">⚠️ ' + he(d.error) + '<br><small>La Analytics API de Meta requiere permisos especiales en tu WABA.</small></div>';
    } else {
      var res = d.resumen || {};
      var sent = res.sent || 0;
      var del = res.delivered || 0;
      var read = res.read || 0;
      var noEntregados = sent - del;
      var pctLectura = sent > 0 ? Math.round(read / sent * 100) : 0;
      cards.innerHTML =
        mkCard('📤', 'Enviados', sent, 'Total últimos 30 días') +
        mkCard('✅', 'Entregados', del, sent > 0 ? Math.round(del/sent*100)+'% de enviados' : '—') +
        mkCard('👁️', 'Leídos', read, pctLectura + '% de lectura') +
        mkCard('⚠️', 'No entregados', noEntregados, 'Posibles números inválidos');
    }
  } catch(e) {
    cards.innerHTML = '<div class="loading-txt" style="grid-column:1/-1;color:#721c24">Error consultando Analytics API</div>';
  }

  // Por plantilla
  try {
    var r2 = await fetch('/inbox/metricas/plantillas', {credentials:'include'});
    var d2 = await r2.json();
    var analytics = d2.analytics || [];
    if (!analytics.length) {
      tplBody.innerHTML = '<tr><td colspan="6" class="loading-txt">Sin datos de plantillas o API no disponible</td></tr>';
      return;
    }
    var h = '';
    analytics.forEach(function(item) {
      var dp = (item.data_points || [])[0] || {};
      var s = dp.sent || 0;
      var dl = dp.delivered || 0;
      var rd = dp.read || 0;
      var clicks = dp.clicked || 0;
      var pct = s > 0 ? Math.round(rd/s*100) + '%' : '—';
      h += '<tr>'
        + '<td><b>' + he(item.template_id || '—') + '</b></td>'
        + '<td>' + s + '</td>'
        + '<td>' + dl + '</td>'
        + '<td>' + rd + '</td>'
        + '<td>' + clicks + '</td>'
        + '<td>' + pct + '</td>'
        + '</tr>';
    });
    tplBody.innerHTML = h;
  } catch(e) {
    tplBody.innerHTML = '<tr><td colspan="6" class="loading-txt" style="color:#721c24">Error cargando analíticas de plantillas</td></tr>';
  }
}

function mkCard(ic, lbl, val, sub) {
  return '<div class="card">'
    + '<div class="card-ic">' + ic + '</div>'
    + '<div class="card-lbl">' + he(lbl) + '</div>'
    + '<div class="card-val">' + Number(val).toLocaleString('es-CO') + '</div>'
    + '<div class="card-sub">' + he(sub) + '</div>'
    + '</div>';
}

/* ══════════════════════════════════════════════════════
   CONFIGURACIÓN
   ══════════════════════════════════════════════════════ */
async function cargarConfiguracion() {
  // Inferimos estado de config desde los endpoints que ya tenemos
  // (sin exponer las keys reales)
  try {
    var r = await fetch('/inbox/broadcast/templates', {credentials:'include'});
    var d = await r.json();
    var metaOk = !d.error;

    document.getElementById('cfg-meta').innerHTML = cfgRow('META_ACCESS_TOKEN', metaOk, metaOk ? '••••••••' : 'No configurado') +
      cfgRow('META_PHONE_NUMBER_ID', metaOk, metaOk ? 'Configurado' : 'No configurado') +
      cfgRow('META_WABA_ID', metaOk, metaOk ? 'Configurado' : 'No configurado') +
      cfgRow('META_VERIFY_TOKEN', true, 'Configurado');

    document.getElementById('cfg-ai').innerHTML =
      cfgRow('ANTHROPIC_API_KEY', true, 'Configurado') +
      cfgRow('Modelo IA', true, 'claude-sonnet-4-6');

    document.getElementById('cfg-shopify').innerHTML =
      cfgRow('SHOPIFY_ACCESS_TOKEN', true, 'Configurado') +
      cfgRow('SHOPIFY_STORE_DOMAIN', true, 'equoradistribuciones.com') +
      cfgRow('SHOPIFY_WEBHOOK_SECRET', true, 'Configurado');
  } catch(e) {
    document.getElementById('cfg-meta').innerHTML = '<div class="loading-txt">Error cargando configuración</div>';
  }
}

function cfgRow(key, ok, val) {
  return '<div class="config-item">'
    + '<span class="config-key">' + he(key) + '</span>'
    + '<span class="' + (ok ? 'config-ok' : 'config-miss') + '">' + (ok ? '✓' : '✗') + '</span>'
    + '<span class="config-val">' + he(val) + '</span>'
    + '</div>';
}
</script>
</body>
</html>"""


def obtener_inbox_html() -> str:
    return _HTML
