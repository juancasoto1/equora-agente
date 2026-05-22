"""
agent/inbox.py — Panel de administración: inbox de conversaciones de Andrea
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
body{{min-height:100vh;background:#111b21;display:flex;align-items:center;
     justify-content:center;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}}
.box{{background:#202c33;border-radius:16px;padding:40px 36px;width:320px;text-align:center;
      box-shadow:0 8px 32px rgba(0,0,0,.4)}}
.ic{{font-size:2.8rem;margin-bottom:10px}}
h2{{color:#e9edef;font-size:1.15rem;font-weight:700;margin-bottom:4px}}
.sub{{color:#8696a0;font-size:.82rem;margin-bottom:28px}}
.err{{color:#ef5350;font-size:.82rem;display:block;margin-bottom:12px}}
input{{width:100%;padding:12px 16px;border-radius:10px;border:1.5px solid #313d45;
       background:#2a3942;color:#e9edef;font-size:.92rem;outline:none;margin-bottom:14px}}
input:focus{{border-color:#00a884}}
input::placeholder{{color:#8696a0}}
button{{width:100%;padding:13px;border-radius:10px;border:none;background:#00a884;
        color:#fff;font-size:.95rem;font-weight:700;cursor:pointer;transition:opacity .2s}}
button:hover{{opacity:.88}}
</style>
</head>
<body>
<div class="box">
  <div class="ic">💬</div>
  <h2>Inbox Andrea</h2>
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
<title>Inbox — Andrea · Equora</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#111b21;color:#e9edef}
:root{--sb:#202c33;--hd:#2a3942;--bbl:#005c4b;--bbr:#202c33;--az:#00a884;--tx:#e9edef;--ts:#8696a0;--bd:#313d45;--hl:#2a3942;--red:#e53935}

/* ── LAYOUT ── */
#app{display:flex;height:100vh;overflow:hidden}
#sidebar{width:350px;min-width:350px;display:flex;flex-direction:column;background:var(--sb);border-right:1px solid var(--bd)}
#chat-area{flex:1;display:flex;flex-direction:column;background:#0b141a;min-width:0}
@media(max-width:720px){
  #sidebar{width:100%;min-width:unset}
  #sidebar.oculto{display:none}
  #chat-area.oculto{display:none}
}

/* ── SIDEBAR ── */
#sh{background:var(--hd);padding:13px 16px;display:flex;align-items:center;gap:10px;flex-shrink:0}
#sh h2{font-size:.95rem;font-weight:600;flex:1}
#sh .cnt{background:var(--az);color:#fff;border-radius:12px;padding:2px 8px;font-size:.72rem;font-weight:700}
#logout{background:none;border:1px solid var(--bd);color:var(--ts);border-radius:8px;padding:4px 10px;font-size:.72rem;cursor:pointer}
#logout:hover{color:var(--tx);border-color:var(--ts)}
#srch{padding:8px 12px;background:var(--sb);flex-shrink:0}
#srinput{width:100%;padding:8px 14px;border-radius:8px;border:none;background:var(--hd);color:var(--tx);font-size:.84rem;outline:none}
#srinput::placeholder{color:var(--ts)}
#cl{flex:1;overflow-y:auto}
#cl::-webkit-scrollbar{width:4px}
#cl::-webkit-scrollbar-thumb{background:var(--bd);border-radius:2px}
.ci{display:flex;align-items:center;gap:12px;padding:12px 16px;cursor:pointer;border-bottom:1px solid var(--bd);transition:background .12s}
.ci:hover,.ci.sel{background:var(--hl)}
.av{width:46px;height:46px;border-radius:50%;background:#1f6b58;display:flex;align-items:center;justify-content:center;font-size:1.25rem;flex-shrink:0}
.inf{flex:1;min-width:0}
.nm{font-size:.88rem;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lm{font-size:.77rem;color:var(--ts);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px}
.meta{display:flex;flex-direction:column;align-items:flex-end;gap:4px;flex-shrink:0}
.cts{font-size:.68rem;color:var(--ts)}
.hmbadge{background:var(--red);color:#fff;border-radius:8px;padding:1px 6px;font-size:.64rem;font-weight:700}

/* ── CHAT VACÍO ── */
#empty{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;color:var(--ts)}
#empty .eic{font-size:3.5rem;opacity:.25}
#empty p{font-size:.88rem}

/* ── CHAT ACTIVO ── */
#cv{display:none;flex-direction:column;height:100%}
#ch{background:var(--hd);padding:10px 16px;display:flex;align-items:center;gap:12px;flex-shrink:0}
#ch .av2{width:40px;height:40px;border-radius:50%;background:#1f6b58;display:flex;align-items:center;justify-content:center;font-size:1.1rem;flex-shrink:0}
#ch .inf2{flex:1;min-width:0}
#ch .nm2{font-size:.92rem;font-weight:600}
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
.bot .mb{background:var(--bbr);border-radius:0 8px 8px 8px}
.usr .mb{background:var(--bbl);border-radius:8px 0 8px 8px}
.mt{font-size:.67rem;color:var(--ts)}
.bot .mt{align-self:flex-start}
.usr .mt{align-self:flex-end}
.msys{align-self:center;background:#182229;color:var(--ts);font-size:.72rem;padding:4px 14px;border-radius:8px;text-align:center;margin:4px 0}

#ib{background:var(--hd);padding:10px 16px;display:flex;gap:10px;align-items:flex-end;flex-shrink:0}
#ti{flex:1;background:var(--sb);border:none;border-radius:10px;padding:10px 14px;color:var(--tx);font-size:.9rem;resize:none;outline:none;max-height:120px;line-height:1.4}
#ti::placeholder{color:var(--ts)}
#sendbtn{background:var(--az);color:#fff;border:none;border-radius:50%;width:42px;height:42px;display:flex;align-items:center;justify-content:center;cursor:pointer;flex-shrink:0;font-size:1.1rem;transition:opacity .2s}
#sendbtn:disabled{opacity:.4;cursor:not-allowed}

/* ── DIFUSIÓN MODAL ── */
#dif-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:200;align-items:center;justify-content:center}
#dif-overlay.open{display:flex}
#dif-box{background:#202c33;border-radius:14px;width:520px;max-width:96vw;max-height:90vh;display:flex;flex-direction:column;box-shadow:0 12px 48px rgba(0,0,0,.5)}
#dif-head{background:#2a3942;padding:14px 18px;border-radius:14px 14px 0 0;display:flex;align-items:center;gap:10px}
#dif-head h3{flex:1;font-size:.95rem;font-weight:700}
#dif-close{background:none;border:none;color:#8696a0;font-size:1.4rem;cursor:pointer;line-height:1;padding:0 2px}
#dif-close:hover{color:#e9edef}
#dif-body{flex:1;overflow-y:auto;padding:18px;display:flex;flex-direction:column;gap:14px}
#dif-body::-webkit-scrollbar{width:4px}
#dif-body::-webkit-scrollbar-thumb{background:#313d45}
.dif-lbl{font-size:.78rem;color:#8696a0;margin-bottom:5px;font-weight:600;text-transform:uppercase;letter-spacing:.04em}
.dif-sel,.dif-inp,.dif-ta{width:100%;background:#2a3942;border:1.5px solid #313d45;border-radius:8px;padding:9px 13px;color:#e9edef;font-size:.88rem;outline:none;font-family:inherit}
.dif-sel:focus,.dif-inp:focus,.dif-ta:focus{border-color:#00a884}
.dif-ta{resize:vertical;min-height:90px;line-height:1.5}
#dif-preview{background:#0b141a;border-radius:8px;padding:12px 14px;font-size:.84rem;line-height:1.5;color:#e9edef;white-space:pre-wrap;min-height:48px;border:1px solid #313d45}
#dif-preview .ph{color:#00a884;font-weight:600}
#dif-vars{display:flex;flex-direction:column;gap:8px}
/* CSV upload */
#dif-csv-wrap{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
#dif-csv-label{display:flex;align-items:center;gap:6px;background:#2a3942;border:1.5px dashed #00a884;border-radius:8px;padding:8px 14px;cursor:pointer;font-size:.83rem;color:#00a884;font-weight:600;transition:background .2s;flex:1;min-width:160px;justify-content:center}
#dif-csv-label:hover{background:#1a2e35}
#dif-csv-input{display:none}
#dif-csv-fname{font-size:.76rem;color:#8696a0;margin-top:3px;text-align:center}
.btn-dl-csv{display:flex;align-items:center;gap:5px;background:none;border:1.5px solid #313d45;border-radius:8px;padding:8px 14px;color:#8696a0;font-size:.83rem;cursor:pointer;font-weight:600;transition:all .2s;white-space:nowrap}
.btn-dl-csv:hover{border-color:#00a884;color:#00a884}
#dif-foot{padding:14px 18px;border-top:1px solid #313d45;display:flex;flex-direction:column;gap:10px}
#dif-prog{display:none;flex-direction:column;gap:6px}
.prog-bar-wrap{background:#313d45;border-radius:8px;height:8px;overflow:hidden}
.prog-bar{background:#00a884;height:100%;width:0%;transition:width .3s;border-radius:8px}
.prog-txt{font-size:.78rem;color:#8696a0}
#dif-sendbtn{background:#00a884;color:#fff;border:none;border-radius:10px;padding:12px;font-size:.92rem;font-weight:700;cursor:pointer;width:100%;transition:opacity .2s}
#dif-sendbtn:disabled{opacity:.45;cursor:not-allowed}
#dif-result{display:none;font-size:.82rem;padding:10px 14px;border-radius:8px;line-height:1.5}
#dif-result.ok{background:#1f6b3320;color:#25d366;border:1px solid #1f6b33}
#dif-result.err{background:#e5393520;color:#ef9a9a;border:1px solid #e53935}
#dif-btn{background:none;border:1px solid #313d45;color:#8696a0;border-radius:8px;padding:5px 11px;font-size:.76rem;cursor:pointer;white-space:nowrap}
#dif-btn:hover{color:#e9edef;border-color:#8696a0}
</style>
</head>
<body>
<div id="app">

  <aside id="sidebar">
    <div id="sh">
      <h2>💬 Inbox Andrea</h2>
      <span class="cnt" id="total">0</span>
      <button id="dif-btn" onclick="abrirDifusion()">📢 Difusión</button>
      <button id="logout" onclick="location.href='/inbox/logout'">Salir</button>
    </div>
    <div id="srch">
      <input id="srinput" placeholder="Buscar por nombre o número..." oninput="filtrar()">
    </div>
    <div id="cl"></div>
  </aside>

  <!-- ── MODAL DIFUSIÓN ── -->
  <div id="dif-overlay" onclick="if(event.target===this)cerrarDifusion()">
    <div id="dif-box">
      <div id="dif-head">
        <span style="font-size:1.2rem">📢</span>
        <h3>Nueva Difusión</h3>
        <button id="dif-close" onclick="cerrarDifusion()">✕</button>
      </div>
      <div id="dif-body">
        <div>
          <div class="dif-lbl">Plantilla aprobada</div>
          <select id="dif-tpl" class="dif-sel" onchange="seleccionarTemplate()">
            <option value="">Cargando plantillas...</option>
          </select>
        </div>
        <div id="dif-vars-wrap" style="display:none">
          <div class="dif-lbl">Variables de la plantilla</div>
          <div id="dif-vars"></div>
        </div>
        <div>
          <div class="dif-lbl">Vista previa</div>
          <div id="dif-preview">Selecciona una plantilla para ver la vista previa.</div>
        </div>
        <div>
          <div class="dif-lbl">Destinatarios <span id="dif-formato-hint" style="font-weight:400;text-transform:none">(uno por línea: número,nombre)</span></div>
          <!-- CSV upload + descarga formato -->
          <div id="dif-csv-wrap">
            <label id="dif-csv-label" for="dif-csv-input">
              📂 Cargar desde CSV
            </label>
            <input type="file" id="dif-csv-input" accept=".csv,text/csv" onchange="cargarArchivoCSV(this)">
            <button class="btn-dl-csv" onclick="descargarFormatoCSV()" type="button" title="Descargar plantilla CSV de ejemplo">
              ⬇ Formato CSV
            </button>
          </div>
          <div id="dif-csv-fname"></div>
          <textarea id="dif-phones" class="dif-ta" style="margin-top:8px" placeholder="573001234567,Juan&#10;573009876543,María&#10;573001112233,Carlos" oninput="actualizarConteo()"></textarea>
          <div id="dif-conteo" style="font-size:.75rem;color:#8696a0;margin-top:4px">0 destinatarios</div>
        </div>
      </div>
      <div id="dif-foot">
        <div id="dif-result"></div>
        <div id="dif-prog">
          <div class="prog-bar-wrap"><div class="prog-bar" id="dif-bar"></div></div>
          <div class="prog-txt" id="dif-ptxt">Enviando...</div>
        </div>
        <button id="dif-sendbtn" onclick="enviarDifusion()" disabled>Enviar difusión</button>
      </div>
    </div>
  </div>

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

</div>
<script>
var TEL = '';
var CONVS = [];
var Q = '';
var _convTimer = null;
var _msgTimer = null;

/* ── UTILS ── */
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
function he(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
/* Las cookies se envían automáticamente — no necesitamos pasar token en la URL */
function api(path, opts) {
  return fetch(path, Object.assign({credentials: 'same-origin'}, opts || {}))
    .then(function(r) {
      if (r.status === 401) { location.href = '/inbox/login'; throw new Error('No autorizado'); }
      return r.json();
    });
}

/* ── LISTA CONVERSACIONES ── */
function loadConvs() {
  api('/inbox/api/conversaciones').then(function(data) {
    CONVS = Array.isArray(data) ? data : [];
    document.getElementById('total').textContent = CONVS.length;
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
       + '<div class="meta"><span class="cts">' + fmt(c.timestamp) + '</span>' + badge + '</div>'
       + '</div>';
  }
  document.getElementById('cl').innerHTML = h;
}

document.getElementById('cl').addEventListener('click', function(e) {
  var ci = e.target.closest('.ci');
  if (ci) abrirConv(ci.dataset.tel);
});

/* ── ABRIR CONVERSACIÓN ── */
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

/* ── MENSAJES ── */
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

/* ── MODO HUMANO ── */
function toggleModo() {
  var activo = document.getElementById('togInput').checked;
  document.getElementById('mlbl').style.display = activo ? 'inline' : 'none';
  api('/inbox/api/modo/' + encodeURIComponent(TEL), {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({activo: activo})
  }).then(function() { loadConvs(); }).catch(function() {});
}

/* ── ENVIAR MENSAJE ── */
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

/* ── INIT ── */
loadConvs();
_convTimer = setInterval(loadConvs, 8000);

/* ══════════════════════════════════════════════════
   DIFUSIÓN
   ══════════════════════════════════════════════════ */
var _dif_templates = [];

function abrirDifusion() {
  document.getElementById('dif-overlay').classList.add('open');
  cargarTemplates();
}
function cerrarDifusion() {
  document.getElementById('dif-overlay').classList.remove('open');
  document.getElementById('dif-result').style.display = 'none';
  document.getElementById('dif-prog').style.display = 'none';
  document.getElementById('dif-sendbtn').disabled = false;
  document.getElementById('dif-csv-fname').textContent = '';
  document.getElementById('dif-csv-input').value = '';
}

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
      _dif_templates.map(t =>
        '<option value="' + t.name + '">' + t.name + ' (' + t.language + ')</option>'
      ).join('');
  } catch(e) {
    sel.innerHTML = '<option value="">Error cargando plantillas</option>';
  }
}

function seleccionarTemplate() {
  var name = document.getElementById('dif-tpl').value;
  var tpl  = _dif_templates.find(t => t.name === name);
  var prev = document.getElementById('dif-preview');
  var varsWrap = document.getElementById('dif-vars-wrap');
  var varsDiv  = document.getElementById('dif-vars');
  var sendBtn  = document.getElementById('dif-sendbtn');

  if (!tpl) {
    prev.textContent = 'Selecciona una plantilla para ver la vista previa.';
    varsWrap.style.display = 'none';
    sendBtn.disabled = true;
    return;
  }

  // Mostrar variables si las hay
  varsDiv.innerHTML = '';
  if (tpl.variables && tpl.variables.length) {
    varsWrap.style.display = 'block';
    tpl.variables.forEach(function(n) {
      var row = document.createElement('div');
      row.style.display = 'flex'; row.style.alignItems = 'center'; row.style.gap = '8px';
      row.innerHTML =
        '<label style="font-size:.82rem;color:#8696a0;white-space:nowrap;min-width:40px">{{' + n + '}}</label>' +
        '<input class="dif-inp" id="dif-var-' + n + '" placeholder="Valor para {{' + n + '}}" oninput="actualizarPreview()">';
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
  var tpl  = _dif_templates.find(t => t.name === name);
  if (!tpl) return;
  var text = tpl.preview || '(Sin vista previa disponible)';
  if (tpl.variables) {
    tpl.variables.forEach(function(n) {
      var inp = document.getElementById('dif-var-' + n);
      var val = inp ? (inp.value || '{{' + n + '}}') : '{{' + n + '}}';
      text = text.split('{{' + n + '}}').join(val);
    });
  }
  document.getElementById('dif-preview').textContent = text;
}

/* ── DESCARGA FORMATO CSV ── */
function descargarFormatoCSV() {
  // Genera un CSV de ejemplo con los encabezados correctos según la plantilla activa
  var name = document.getElementById('dif-tpl').value;
  var tpl  = _dif_templates.find(t => t.name === name);
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
  a.href = url;
  a.download = 'formato_difusion.csv';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/* ── CARGAR ARCHIVO CSV ── */
function cargarArchivoCSV(input) {
  var file = input.files && input.files[0];
  if (!file) return;
  document.getElementById('dif-csv-fname').textContent = '📄 ' + file.name;

  var reader = new FileReader();
  reader.onload = function(e) {
    var texto = e.target.result;
    // Eliminar BOM si existe
    if (texto.charCodeAt(0) === 0xFEFF) texto = texto.slice(1);

    var lineas = texto.split(/\r?\n/).map(l => l.trim()).filter(l => l.length > 0);
    if (!lineas.length) return;

    // Detectar si la primera línea es encabezado (empieza con texto no numérico)
    var primeraCol = lineas[0].split(',')[0].trim();
    var esEncabezado = isNaN(primeraCol.replace(/\D/g,'')) || primeraCol.toLowerCase() === 'telefono';
    if (esEncabezado) lineas = lineas.slice(1);

    // Verificar que queden datos
    if (!lineas.length) {
      document.getElementById('dif-csv-fname').textContent = '⚠️ El archivo no tiene datos válidos';
      return;
    }

    // Pegar en el textarea (reemplaza el contenido actual)
    document.getElementById('dif-phones').value = lineas.join('\n');
    actualizarConteo();

    // Feedback
    document.getElementById('dif-csv-fname').textContent =
      '✅ ' + file.name + ' — ' + lineas.length + ' fila(s) cargada(s)';

    // Limpiar el input para poder volver a cargar el mismo archivo
    input.value = '';
  };
  reader.onerror = function() {
    document.getElementById('dif-csv-fname').textContent = '❌ Error al leer el archivo';
  };
  reader.readAsText(file, 'UTF-8');
}

function _parsearDestinatarios() {
  /* Parsea el textarea y retorna [{phone, variables:[]}]
     Formato soportado:
       573001234567,Juan        → phone + nombre
       573001234567             → phone solo (sin variables)
       573001234567,Juan,Extra  → múltiples variables
  */
  var tpl  = _dif_templates.find(t => t.name === document.getElementById('dif-tpl').value);
  var nVars = tpl ? (tpl.variables || []).length : 0;
  return document.getElementById('dif-phones').value
    .split('\n')
    .map(l => l.trim())
    .filter(l => l.length > 5)
    .map(function(l) {
      var partes = l.split(',').map(p => p.trim());
      var phone  = partes[0];
      // Variables: las columnas 1..N de la línea; si faltan, usar campo fijo
      var vars = [];
      for (var i = 0; i < nVars; i++) {
        if (partes[i + 1] !== undefined && partes[i + 1] !== '') {
          vars.push(partes[i + 1]);
        } else {
          // Fallback: valor del campo fijo (si existe)
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
  var tpl   = _dif_templates.find(t => t.name === name);
  if (!tpl) return;

  var recipients = _parsearDestinatarios();
  if (!recipients.length) return;

  // Validar: si la plantilla tiene variables, ningún destinatario puede tenerlas vacías
  if (tpl.variables && tpl.variables.length) {
    var sinNombre = recipients.filter(function(r) {
      return r.variables.some(function(v) { return !v || v.trim() === ''; });
    });
    if (sinNombre.length) {
      var res = document.getElementById('dif-result');
      res.style.display = 'block';
      res.className = 'dif-result err';
      res.textContent = '⚠️ ' + sinNombre.length + ' destinatario(s) tienen variables vacías. ' +
        'Usa el formato "número,nombre" o rellena el campo fijo arriba.';
      return;
    }
  }

  // UI: mostrar progreso
  var btn  = document.getElementById('dif-sendbtn');
  var prog = document.getElementById('dif-prog');
  var bar  = document.getElementById('dif-bar');
  var ptxt = document.getElementById('dif-ptxt');
  var res  = document.getElementById('dif-result');
  btn.disabled = true;
  prog.style.display = 'flex';
  bar.style.width = '0%';
  ptxt.textContent = 'Enviando 0 / ' + recipients.length + '...';
  res.style.display = 'none';

  try {
    // Enviamos en lotes de 50 para poder mostrar progreso
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
      res.className = 'dif-result ok';
      res.textContent = '✅ Difusión completada: ' + enviados + ' mensajes enviados correctamente.';
    } else {
      res.className = 'dif-result err';
      res.textContent = '⚠️ ' + enviados + ' enviados, ' + fallidos + ' fallidos.\n' + todosErrores.slice(0,5).join('\n');
    }
  } catch(e) {
    res.style.display = 'block';
    res.className = 'dif-result err';
    res.textContent = 'Error de conexión: ' + e.message;
  }
  btn.disabled = false;
}
</script>
</body>
</html>"""


def obtener_inbox_html() -> str:
    return _HTML
