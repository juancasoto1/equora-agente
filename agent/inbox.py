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
</style>
</head>
<body>
<div id="app">

  <aside id="sidebar">
    <div id="sh">
      <h2>💬 Inbox Andrea</h2>
      <span class="cnt" id="total">0</span>
      <button id="logout" onclick="location.href='/inbox/logout'">Salir</button>
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
</script>
</body>
</html>"""


def obtener_inbox_html() -> str:
    return _HTML
