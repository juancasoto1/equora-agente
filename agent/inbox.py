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
<meta name="color-scheme" content="dark">
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
    <label for="pwd" style="display:none">Contraseña</label>
    <input type="password" id="pwd" name="password" placeholder="Contraseña de acceso"
           autocomplete="current-password" autofocus required>
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
<meta name="color-scheme" content="dark light">
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
.optbadge{background:#64748b;color:#fff;border-radius:8px;padding:1px 6px;font-size:.64rem;font-weight:700}

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
              <label for="ti" style="display:none">Mensaje</label>
              <textarea id="ti" rows="1" placeholder="Escribe un mensaje y presiona Enter…"
                aria-label="Escribe un mensaje"
                onkeydown="onKey(event)" oninput="autoResize()"></textarea>
              <button id="sendbtn" onclick="sendMsg()" aria-label="Enviar mensaje">➤</button>
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
                    oninput="updateCounter('tpl-body','body-cnt',1024)"></textarea>
                  <div style="display:flex;justify-content:space-between;align-items:center;margin-top:3px">
                    <span class="f-hint">Campo requerido</span>
                    <span class="char-counter"><span id="body-cnt">0</span>/1024</span>
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
                <div class="f-group" style="margin-bottom:10px">
                  <span class="f-label">Tipo de botones</span>
                  <div class="radio-group" id="btn-radio-group">
                    <label class="radio-opt chk"><input type="radio" name="btn-type" value="NONE" checked onchange="toggleBtnType('NONE')"> Ninguno</label>
                    <label class="radio-opt"><input type="radio" name="btn-type" value="QUICK_REPLY" onchange="toggleBtnType('QUICK_REPLY')"> ↩️ Respuesta rápida</label>
                    <label class="radio-opt"><input type="radio" name="btn-type" value="CTA" onchange="toggleBtnType('CTA')"> 🔗 Llamada a la acción</label>
                  </div>
                </div>

                <!-- Quick reply -->
                <div id="btns-qr-wrap" style="display:none;margin-bottom:14px">
                  <div class="info-box">
                    <b>↩️ Respuesta rápida:</b> el cliente toca el botón y envía ese texto como mensaje<br>
                    • Hasta <b>3 botones</b> · Máx <b>25 caracteres</b> por botón · Sin URLs<br>
                    • Ideales para: Sí/No, opciones de menú, confirmaciones
                  </div>
                  <div id="qr-list"></div>
                  <button class="btn-secondary" style="padding:6px 14px;font-size:.8rem" onclick="agregarBotonQR()" type="button">
                    + Agregar botón
                  </button>
                </div>

                <!-- CTA -->
                <div id="btns-cta-wrap" style="display:none;margin-bottom:14px">
                  <div class="info-box">
                    <b>🔗 Llamada a la acción:</b> hasta <b>2 botones</b> (1 URL + 1 teléfono)<br>
                    • <b>URL:</b> texto máx 20 chars · La URL puede tener <code>{{1}}</code> al final<br>
                    • <b>Teléfono:</b> texto máx 20 chars · Número con código de país (ej: +573001234567)<br>
                    • El botón abre el navegador o el marcador del teléfono del cliente
                  </div>
                  <div id="cta-list"></div>
                  <button class="btn-secondary" style="padding:6px 14px;font-size:.8rem" onclick="agregarBotonCTA()" type="button">
                    + Agregar botón
                  </button>
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
          <div style="display:flex;gap:8px;align-items:center">
            <select id="met-periodo" onchange="cargarMetricas()" style="padding:6px 10px;border:1px solid #dde1e7;border-radius:8px;font-size:.82rem;color:#1a2332">
              <option value="7">Últimos 7 días</option>
              <option value="30" selected>Últimos 30 días</option>
              <option value="90">Últimos 90 días</option>
            </select>
            <button class="btn-secondary" onclick="cargarMetricas()">↺ Actualizar</button>
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
            <p style="font-size:.72rem;color:#8a94a6;margin-top:8px">
              💵 Costo Meta = enviados × USD $<span id="met-tarifa">0.0165</span> (conversación de marketing).
              Meta cobra al iniciar la conversación, no por entrega ni lectura.
              <span class="met-col-roi"> | 🛒 Ventas = órdenes Shopify de destinatarios en los 7 días siguientes al envío.</span>
            </p>
          </div>

          <!-- Nota informativa -->
          <div style="margin-top:20px;padding:12px 16px;background:#f0f4ff;border-radius:10px;border-left:3px solid #4a7cf7;font-size:.78rem;color:#3a4a6b;line-height:1.6">
            ℹ️ <strong>Métricas propias de Equora.</strong>
            Entrega y lectura: tracking via webhook de Meta.
            Costo: tarifa oficial Meta conversaciones de marketing (Colombia).
            Ventas atribuidas: órdenes Shopify cruzadas por teléfono del destinatario en ventana de 7 días.
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
          <button class="btn-secondary" style="padding:7px 16px;font-size:.82rem"
                  onclick="cargarClientes()" aria-label="Actualizar lista de clientes">↺ Actualizar</button>
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
    if (id === 'configuracion') { cargarConfiguracion(); }
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
       + '<td><button class="cli-act-btn" onclick="verChatCliente(' + JSON.stringify(c.telefono) + ')"'
       +    ' aria-label="Ver chat de ' + he(disp) + '">Ver chat</button></td>'
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
      sel.innerHTML = '<option value="">Error: ' + d.error + '</option>';
      return;
    }
    // Solo plantillas APPROVED para difusiones
    var todas = d.templates || [];
    _dif_templates = todas.filter(function(t) { return (t.status || '').toUpperCase() === 'APPROVED'; });
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
    var tpls = d.templates || [];

    if (!tpls.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="loading-txt">Sin plantillas · Verifica META_WABA_ID</td></tr>';
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
  var btnTipo  = document.querySelector('input[name="btn-type"]:checked').value;
  var buttons  = _recolectarBotones(btnTipo);
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
  updateCounter('tpl-body','body-cnt',1024);
  updateCounter('tpl-footer','footer-cnt',60);
  // Header
  var hdrTipo = datos.header_type || 'NONE';
  var radios = document.querySelectorAll('input[name="hdr-type"]');
  radios.forEach(function(r) { if (r.value === hdrTipo) r.checked = true; });
  toggleHdrType(hdrTipo);
  if (hdrTipo === 'TEXT') document.getElementById('tpl-hdr-text').value = datos.header_text || '';
  // Botones
  var buttons = datos.buttons || [];
  document.getElementById('qr-list').innerHTML  = '';
  document.getElementById('cta-list').innerHTML = '';
  if (buttons.length) {
    var hasQR  = buttons.some(function(b) { return b.type === 'QUICK_REPLY'; });
    var hasCTA = buttons.some(function(b) { return b.type === 'URL' || b.type === 'PHONE_NUMBER'; });
    if (hasQR) {
      document.querySelector('input[name="btn-type"][value="QUICK_REPLY"]').checked = true;
      toggleBtnType('QUICK_REPLY');
      document.getElementById('qr-list').innerHTML = '';
      buttons.filter(function(b) { return b.type === 'QUICK_REPLY'; }).forEach(function(b) {
        agregarBotonQR();
        var rows = document.querySelectorAll('#qr-list .qr-text');
        if (rows.length) rows[rows.length-1].value = b.text || '';
      });
    } else if (hasCTA) {
      document.querySelector('input[name="btn-type"][value="CTA"]').checked = true;
      toggleBtnType('CTA');
      document.getElementById('cta-list').innerHTML = '';
      buttons.filter(function(b) { return b.type !== 'QUICK_REPLY'; }).forEach(function(b) {
        agregarBotonCTA();
        var rows = document.querySelectorAll('#cta-list .cta-row');
        var row  = rows[rows.length-1];
        if (!row) return;
        row.querySelector('.cta-tipo').value   = b.type;
        row.querySelector('.cta-texto').value  = b.text || '';
        if (b.type === 'URL')          { row.querySelector('.cta-valor-url').value = b.url || ''; }
        else if (b.type === 'PHONE_NUMBER') { row.querySelector('.cta-valor-tel').value = b.phone_number || ''; }
        toggleCtaTipo(row.querySelector('.cta-tipo'));
      });
    }
  } else {
    document.querySelector('input[name="btn-type"][value="NONE"]').checked = true;
    toggleBtnType('NONE');
  }
}

function _limpiarFormulario() {
  document.getElementById('tpl-nombre').value  = '';
  document.getElementById('tpl-body').value    = '';
  document.getElementById('tpl-footer').value  = '';
  document.getElementById('tpl-hdr-text').value = '';
  document.querySelector('input[name="hdr-type"][value="NONE"]').checked = true;
  toggleHdrType('NONE');
  document.querySelector('input[name="btn-type"][value="NONE"]').checked = true;
  toggleBtnType('NONE');
  document.getElementById('qr-list').innerHTML  = '';
  document.getElementById('cta-list').innerHTML = '';
  ['img','vid','doc'].forEach(limpiarArchivo);
  updateCounter('tpl-body','body-cnt',1024);
  updateCounter('tpl-footer','footer-cnt',60);
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
function _recolectarBotones(btnTipo) {
  var buttons = [];
  if (btnTipo === 'QUICK_REPLY') {
    document.querySelectorAll('#qr-list .qr-text').forEach(function(inp) {
      var txt = inp.value.trim();
      if (txt) buttons.push({type:'QUICK_REPLY', text: txt});
    });
  } else if (btnTipo === 'CTA') {
    document.querySelectorAll('#cta-list .cta-row').forEach(function(row) {
      var tipo2  = row.querySelector('.cta-tipo').value;
      var texto2 = row.querySelector('.cta-texto').value.trim();
      if (!texto2) return;
      if (tipo2 === 'URL') {
        var url = row.querySelector('.cta-valor-url').value.trim();
        if (url) buttons.push({type:'URL', text: texto2, url: url});
      } else {
        var tel = row.querySelector('.cta-valor-tel').value.trim();
        if (tel) buttons.push({type:'PHONE_NUMBER', text: texto2, phone_number: tel});
      }
    });
  }
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

/* ── Tipo de botones ── */
function toggleBtnType(tipo) {
  document.getElementById('btns-qr-wrap').style.display  = tipo === 'QUICK_REPLY' ? 'block' : 'none';
  document.getElementById('btns-cta-wrap').style.display = tipo === 'CTA'         ? 'block' : 'none';
  document.querySelectorAll('#btn-radio-group .radio-opt').forEach(function(lbl) {
    var inp = lbl.querySelector('input');
    lbl.classList.toggle('chk', inp && inp.value === tipo);
  });
  // Inicializar lista si está vacía
  if (tipo === 'QUICK_REPLY' && !document.getElementById('qr-list').children.length) agregarBotonQR();
  if (tipo === 'CTA'         && !document.getElementById('cta-list').children.length) agregarBotonCTA();
}

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

/* ── Botones Quick Reply ── */
function agregarBotonQR() {
  var list = document.getElementById('qr-list');
  if (list.children.length >= 3) { alert('Máximo 3 botones de respuesta rápida'); return; }
  var row = document.createElement('div');
  row.className = 'qr-row';
  row.innerHTML = '<input class="f-inp qr-text" maxlength="25" placeholder="Ej: Sí, me interesa" style="flex:1">' +
    '<span style="font-size:.7rem;color:#6b7a8d;white-space:nowrap;flex-shrink:0" id="qr-cnt-' + list.children.length + '">0/25</span>' +
    '<button class="btn-remove" onclick="this.parentElement.remove()" type="button">✕</button>';
  var inp = row.querySelector('.qr-text');
  var cntId = 'qr-cnt-' + list.children.length;
  inp.addEventListener('input', function() {
    var c = document.getElementById(cntId);
    if (c) c.textContent = this.value.length + '/25';
  });
  list.appendChild(row);
}

/* ── Botones CTA ── */
function agregarBotonCTA() {
  var list = document.getElementById('cta-list');
  if (list.children.length >= 2) { alert('Máximo 2 botones de llamada a la acción'); return; }
  var idx = list.children.length;
  var row = document.createElement('div');
  row.className = 'cta-row';
  row.innerHTML =
    '<div style="display:flex;flex-direction:column;gap:6px;width:100%">' +
      '<div style="display:flex;gap:8px;align-items:center">' +
        '<select class="f-sel cta-tipo" style="width:160px" onchange="toggleCtaTipo(this)">' +
          '<option value="URL">🔗 URL</option>' +
          '<option value="PHONE_NUMBER">📞 Teléfono</option>' +
        '</select>' +
        '<input class="f-inp cta-texto" maxlength="20" placeholder="Texto del botón" style="flex:1">' +
        '<button class="btn-remove" onclick="this.closest(\'.cta-row\').remove()" type="button">✕</button>' +
      '</div>' +
      '<input class="f-inp cta-valor-url" placeholder="https://equoradistribuciones.com/{{1}}" style="width:100%">' +
      '<span class="f-hint cta-hint-url">La URL puede incluir <code>{{1}}</code> para personalizar por destinatario</span>' +
      '<input class="f-inp cta-valor-tel" placeholder="+573001234567" style="width:100%;display:none">' +
      '<span class="f-hint cta-hint-tel" style="display:none">Número con código de país. El cliente iniciará la llamada al tocarlo</span>' +
    '</div>';
  list.appendChild(row);
}

function toggleCtaTipo(sel) {
  var row = sel.closest('.cta-row');
  var esURL = sel.value === 'URL';
  row.querySelector('.cta-valor-url').style.display = esURL ? '' : 'none';
  row.querySelector('.cta-hint-url').style.display  = esURL ? '' : 'none';
  row.querySelector('.cta-valor-tel').style.display = esURL ? 'none' : '';
  row.querySelector('.cta-hint-tel').style.display  = esURL ? 'none' : '';
}

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
  var btnTipo  = document.querySelector('input[name="btn-type"]:checked').value;

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

  var buttons  = _recolectarBotones(btnTipo);
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
  var btnTipo  = document.querySelector('input[name="btn-type"]:checked').value;
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

  var buttons = _recolectarBotones(btnTipo);

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
  var btnTipo = document.querySelector('input[name="btn-type"]:checked');
  btnTipo = btnTipo ? btnTipo.value : 'NONE';
  var btnsEl  = document.getElementById('prev-btns');
  var btnsHtml = '';

  if (btnTipo === 'QUICK_REPLY') {
    document.querySelectorAll('#qr-list .qr-text').forEach(function(inp) {
      var txt = inp.value.trim();
      if (txt) btnsHtml += '<div class="wa-btn"><span class="wa-btn-ic">↩️</span>' + he(txt) + '</div>';
    });
  } else if (btnTipo === 'CTA') {
    document.querySelectorAll('#cta-list .cta-row').forEach(function(row) {
      var tipo2  = row.querySelector('.cta-tipo') ? row.querySelector('.cta-tipo').value : 'URL';
      var texto2 = row.querySelector('.cta-texto') ? row.querySelector('.cta-texto').value.trim() : '';
      if (!texto2) return;
      var ic = tipo2 === 'URL' ? '🔗' : '📞';
      btnsHtml += '<div class="wa-btn"><span class="wa-btn-ic">' + ic + '</span>' + he(texto2) + '</div>';
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
  // Radios header y botones
  document.querySelectorAll('input[name="hdr-type"], input[name="btn-type"]').forEach(function(r) {
    r.addEventListener('change', actualizarPreview);
  });
  // Botones QR y CTA: usar MutationObserver para detectar cuando se agregan
  var observer = new MutationObserver(function() {
    // Re-hookear los inputs nuevos dentro de qr-list y cta-list
    ['#qr-list','#cta-list'].forEach(function(sel) {
      var el = document.querySelector(sel);
      if (!el) return;
      el.querySelectorAll('input').forEach(function(inp) {
        if (!inp._previewHooked) {
          inp._previewHooked = true;
          inp.addEventListener('input', actualizarPreview);
          inp.addEventListener('change', actualizarPreview);
        }
      });
    });
    actualizarPreview();
  });
  var qrEl  = document.getElementById('qr-list');
  var ctaEl = document.getElementById('cta-list');
  if (qrEl)  observer.observe(qrEl,  {childList:true, subtree:true});
  if (ctaEl) observer.observe(ctaEl, {childList:true, subtree:true});
  // Disparo inicial
  actualizarPreview();
}

/* ══════════════════════════════════════════════════════
   MÉTRICAS
   ══════════════════════════════════════════════════════ */
async function cargarMetricas() {
  var cardsDif  = document.getElementById('met-cards-dif');
  var cardsRoi  = document.getElementById('met-cards-roi');
  var cardsConv = document.getElementById('met-cards-conv');
  var campBody  = document.getElementById('met-camp-body');
  var aviso     = document.getElementById('met-aviso-tracking');
  var periodo   = document.getElementById('met-periodo').value || '30';
  var ld = '<div class="loading-txt" style="grid-column:1/-1">Cargando...</div>';

  cardsDif.innerHTML  = ld;
  cardsRoi.innerHTML  = ld;
  cardsConv.innerHTML = ld;
  campBody.innerHTML  = '<tr><td colspan="9" class="loading-txt">Cargando...</td></tr>';
  if (aviso) aviso.style.display = 'none';

  try {
    var r = await fetch('/inbox/metricas/interno?dias=' + periodo, {credentials:'include'});
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

  } catch(e) {
    var errMsg = '<div class="loading-txt" style="grid-column:1/-1;color:#721c24">Error al cargar métricas: ' + he(String(e)) + '</div>';
    cardsDif.innerHTML = cardsRoi.innerHTML = cardsConv.innerHTML = errMsg;
    campBody.innerHTML = '<tr><td colspan="9" class="loading-txt" style="color:#721c24">Error al cargar</td></tr>';
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
