"""
agent/tienda.py — Mini-tienda web Equora Distribuciones
Usa raw-string r\"\"\"...\"\"\" para el template: el JS se escribe exactamente
como aparece en el navegador, sin niveles de escape adicionales de Python.
"""
import json

# LOGO_AQUI y CATALOGO_AQUI se reemplazan en obtener_tienda_html()
_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1"/>
<title>Equora Distribuciones</title>
<style>
:root{--az:#1a3a6b;--ve:#2d7d3a;--vc:#4caf50;--gr:#f5f5f5;--tx:#1a1a1a;--bd:#e0e0e0}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--gr);color:var(--tx)}
header{background:var(--az);color:#fff;padding:10px 14px;display:flex;align-items:center;gap:10px;position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,.25)}
.lw{width:44px;height:44px;flex-shrink:0;border-radius:50%;overflow:hidden;background:#fff;display:flex;align-items:center;justify-content:center}
.lw img{width:100%;height:100%;object-fit:contain}
.lf{font-size:1.6rem;line-height:1}
h1{font-size:1rem;font-weight:700;flex:1;line-height:1.2}
h1 small{display:block;font-size:.7rem;font-weight:400;opacity:.8}
#bc{position:relative;background:rgba(255,255,255,.15);border:1.5px solid rgba(255,255,255,.4);color:#fff;width:46px;height:46px;border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:1.3rem;flex-shrink:0}
#bdg{position:absolute;top:-4px;right:-4px;background:#f44336;color:#fff;border-radius:50%;width:18px;height:18px;display:none;align-items:center;justify-content:center;font-size:.65rem;font-weight:700;border:2px solid var(--az)}
#ban{background:linear-gradient(90deg,var(--az),var(--ve));color:#fff;text-align:center;padding:7px 14px;font-size:.78rem;font-weight:600}
#fil{display:flex;gap:8px;padding:10px 14px;overflow-x:auto;background:#fff;border-bottom:1px solid var(--bd)}
#fil::-webkit-scrollbar{display:none}
.fb{white-space:nowrap;padding:6px 14px;border-radius:20px;border:1.5px solid var(--az);background:#fff;color:var(--az);font-size:.78rem;font-weight:600;cursor:pointer}
.fb.on{background:var(--az);color:#fff}
#grd{padding:12px 14px;display:grid;grid-template-columns:repeat(auto-fill,minmax(155px,1fr));gap:12px}
.card{background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)}
.iw{width:100%;height:150px;overflow:hidden;background:#fff;display:flex;align-items:center;justify-content:center;padding:6px}
.iw img{width:100%;height:100%;object-fit:contain}
.ni{font-size:2.2rem}
.cb{padding:10px}
.cn{font-size:.8rem;font-weight:700;margin-bottom:2px;line-height:1.3}
.cs{font-size:.72rem;color:#777;margin-bottom:6px}
.cpr{font-size:.95rem;font-weight:700;color:var(--az);margin-bottom:8px}
.qc{display:flex;align-items:center;gap:8px}
.qb{width:30px;height:30px;border-radius:50%;border:1.5px solid var(--vc);background:#fff;color:var(--vc);font-size:1.1rem;font-weight:700;cursor:pointer;display:flex;align-items:center;justify-content:center}
.qn{font-size:.9rem;font-weight:700;min-width:20px;text-align:center}
.ab{width:100%;background:var(--vc);color:#fff;border:none;border-radius:8px;padding:7px 0;font-size:.82rem;font-weight:600;cursor:pointer}
#ov{display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:200}
#ov.on{display:block}
#pan{position:fixed;bottom:0;left:0;right:0;max-height:82vh;background:#fff;border-radius:20px 20px 0 0;z-index:201;display:flex;flex-direction:column;transform:translateY(100%);transition:transform .3s ease}
#pan.on{transform:translateY(0)}
#pan::before{content:'';display:block;width:40px;height:4px;background:#ddd;border-radius:2px;margin:10px auto 0}
#ch{padding:12px 16px 10px;border-bottom:1px solid var(--bd);display:flex;align-items:center;justify-content:space-between}
#ch h2{font-size:.95rem;font-weight:700;color:var(--az)}
#xc{background:none;border:none;font-size:1.3rem;cursor:pointer;color:#888;padding:4px}
#ci{overflow-y:auto;flex:1;padding:0 14px}
.ci{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid #f0f0f0}
.cii{width:48px;height:48px;border-radius:8px;overflow:hidden;flex-shrink:0;background:#f5f5f5;display:flex;align-items:center;justify-content:center}
.cii img{width:100%;height:100%;object-fit:cover}
.cio{flex:1;min-width:0}
.cin{font-size:.82rem;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cip{font-size:.72rem;color:#777}
.cis{font-size:.82rem;color:var(--az);font-weight:700;margin-top:2px}
.ciq{display:flex;align-items:center;gap:6px;flex-shrink:0}
.ciq button{width:26px;height:26px;border-radius:50%;border:1.5px solid var(--vc);background:#fff;color:var(--vc);font-size:1rem;font-weight:700;cursor:pointer}
.ciq span{min-width:18px;text-align:center;font-weight:700;font-size:.88rem}
#cf{padding:12px 16px 20px;border-top:1px solid var(--bd)}
.tr{display:flex;justify-content:space-between;font-size:.83rem;color:#666;margin-bottom:6px}
.tr.grat span:last-child{color:var(--vc);font-weight:700}
#tf{display:flex;justify-content:space-between;font-size:1rem;font-weight:700;color:var(--az);margin:8px 0 14px;padding-top:8px;border-top:1px solid var(--bd)}
#ok{width:100%;padding:14px;background:linear-gradient(135deg,var(--az),var(--ve));color:#fff;border:none;border-radius:12px;font-size:1rem;font-weight:700;cursor:pointer}
#ok:disabled{opacity:.5;cursor:not-allowed}
#ex{display:none;position:fixed;inset:0;background:#fff;z-index:300;flex-direction:column;align-items:center;justify-content:center;gap:14px;padding:28px;text-align:center}
#ex.on{display:flex}
#ex .ic{font-size:4rem}
#ex h2{color:var(--az);font-size:1.4rem;font-weight:800}
#ex p{color:#555;font-size:.88rem;max-width:280px;line-height:1.5}
#ex a{display:block;margin-top:6px;background:linear-gradient(135deg,var(--az),var(--ve));color:#fff;text-decoration:none;padding:14px 32px;border-radius:12px;font-size:1rem;font-weight:700}
.sub{font-size:.78rem;color:#bbb;margin-top:4px}
#tst{position:fixed;bottom:90px;left:50%;transform:translateX(-50%);background:rgba(26,26,26,.9);color:#fff;padding:9px 20px;border-radius:24px;font-size:.83rem;opacity:0;transition:opacity .25s;pointer-events:none;z-index:400}
#tst.on{opacity:1}
</style>
</head>
<body>
<header>
  <div class="lw">LOGO_AQUI</div>
  <h1>Equora Distribuciones<small>Productos Biotú 🌿</small></h1>
  <button id="bc" onclick="abrirC()">🛒<span id="bdg"></span></button>
</header>
<div id="ban">🎁 Envío GRATIS en pedidos desde $60.000</div>
<div id="fil"></div>
<div id="grd"><p style="color:#aaa;text-align:center;padding:40px;grid-column:1/-1" id="grd-msg">Cargando...</p></div>

<div id="ov" onclick="cerrarC()"></div>
<div id="pan">
  <div id="ch">
    <h2>🛒 Tu pedido</h2>
    <button id="xc" onclick="cerrarC()">✕</button>
  </div>
  <div id="ci"></div>
  <div id="cf" style="display:none">
    <div class="tr"><span>Subtotal</span><span id="sv">$0</span></div>
    <div class="tr" id="er"><span id="el">Envío</span><span id="ev">$7.000</span></div>
    <div id="tf"><span>Total a pagar</span><span id="tv">$0</span></div>
    <button id="ok" onclick="confirmar()" disabled>Confirmar pedido →</button>
  </div>
</div>

<div id="ex">
  <div class="ic">🎉</div>
  <h2>¡Pedido confirmado!</h2>
  <p>Ingresa tu dirección de entrega.<br>El pago es <strong>contra entrega</strong>.</p>
  <a id="lnk" href="#" target="_blank">Completar pedido →</a>
  <p class="sub">Puedes cerrar y volver a WhatsApp</p>
</div>
<div id="tst"></div>

<script>
var ENV = 7000, MG = 60000;
var P = [];
var C = {};
var CAT = 'Todos';
var TEL = new URLSearchParams(location.search).get('tel') || '';
var LISTA = [];
var CK = [];
var ORDEN = ['Todos','Lavandería','Cocina','Hogar','Talleres / Industrial','Higiene Personal','Otros'];

function fmt(n) { return '$' + Number(n).toLocaleString('es-CO'); }
function he(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
function cl(p) { return p.producto + '||' + p.presentacion; }

/* ── FILTROS ── */
function renderFil() {
  var d = new Set(P.map(function(p) { return p.categoria; }));
  var cats = ORDEN.filter(function(c) { return c === 'Todos' || d.has(c); });
  var h = '';
  for (var i = 0; i < cats.length; i++) {
    var cls = 'fb' + (cats[i] === CAT ? ' on' : '');
    h += '<button class="' + cls + '" data-c="' + he(cats[i]) + '">' + he(cats[i]) + '</button>';
  }
  document.getElementById('fil').innerHTML = h;
}

document.addEventListener('click', function(e) {
  var b = e.target.closest('.fb');
  if (b) { CAT = b.dataset.c; renderFil(); renderGrd(); }
});

/* ── GRID ── */
function renderGrd() {
  LISTA = CAT === 'Todos' ? P : P.filter(function(p) { return p.categoria === CAT; });
  if (!LISTA.length) {
    document.getElementById('grd').innerHTML =
      '<p style="color:#bbb;text-align:center;padding:40px;grid-column:1/-1">Sin productos en esta categoría</p>';
    return;
  }
  var h = '';
  for (var i = 0; i < LISTA.length; i++) {
    var p = LISTA[i];
    var k = cl(p);
    var qty = C[k] ? C[k].qty : 0;
    var st = (typeof p.stock === 'number') ? p.stock : 9999;
    var im = p.imagen
      ? '<img src="' + he(p.imagen) + '" loading="lazy">'
      : '<span class="ni">🧴</span>';
    var acc;
    if (st <= 0) {
      acc = '<p style="text-align:center;font-size:.75rem;color:#bbb">Agotado</p>';
    } else if (qty === 0) {
      acc = '<button class="ab" data-gi="' + i + '">+ Agregar</button>';
    } else {
      acc = '<div class="qc">'
          + '<button class="qb" data-di="' + i + '">−</button>'
          + '<span class="qn">' + qty + '</span>'
          + '<button class="qb" data-ii="' + i + '" data-st="' + st + '">+</button>'
          + '</div>';
    }
    h += '<div class="card">'
       + '<div class="iw">' + im + '</div>'
       + '<div class="cb">'
       + '<div class="cn">' + he(p.producto) + '</div>'
       + '<div class="cs">' + he(p.presentacion) + '</div>'
       + '<div class="cpr">' + fmt(p.precio) + '</div>'
       + acc
       + '</div></div>';
  }
  document.getElementById('grd').innerHTML = h;
}

/* Delegación de eventos para grid — evita onclick con strings */
document.addEventListener('click', function(e) {
  var gi = e.target.dataset.gi;
  var di = e.target.dataset.di;
  var ii = e.target.dataset.ii;
  if (gi !== undefined) add(parseInt(gi, 10));
  else if (di !== undefined) dec(parseInt(di, 10));
  else if (ii !== undefined) inc(parseInt(ii, 10), parseInt(e.target.dataset.st, 10));
});

/* ── CARRITO ACTIONS ── */
function add(i) {
  var p = LISTA[i]; if (!p) return;
  var k = cl(p);
  C[k] = { info: p, qty: 1, stock: (typeof p.stock === 'number' ? p.stock : 9999) };
  ui(); tst('Agregado 🌿');
}
function inc(i, st) {
  var p = LISTA[i]; if (!p) return;
  var k = cl(p);
  if (C[k] && C[k].qty < st) { C[k].qty++; ui(); } else tst('Stock máximo');
}
function dec(i) {
  var p = LISTA[i]; if (!p) return;
  var k = cl(p);
  if (C[k]) { C[k].qty--; if (C[k].qty <= 0) delete C[k]; ui(); }
}
function decC(i) {
  var k = CK[i]; if (!k) return;
  if (C[k]) { C[k].qty--; if (C[k].qty <= 0) delete C[k]; ui(); }
}
function incC(i) {
  var k = CK[i]; if (!k) return;
  if (C[k] && C[k].qty < C[k].stock) { C[k].qty++; ui(); }
}

function ui() {
  var ks = Object.keys(C), tot = 0;
  for (var i = 0; i < ks.length; i++) tot += C[ks[i]].qty;
  var b = document.getElementById('bdg');
  if (tot > 0) { b.style.display = 'flex'; b.textContent = tot; }
  else b.style.display = 'none';
  renderGrd();
  renderCar();
}

/* ── PANEL CARRITO ── */
function renderCar() {
  CK = Object.keys(C);
  var ci = document.getElementById('ci');
  var cf = document.getElementById('cf');
  if (!CK.length) {
    ci.innerHTML = '<div style="text-align:center;padding:40px;color:#bbb"><p style="font-size:2rem">🛒</p><p>Tu carrito está vacío</p></div>';
    cf.style.display = 'none'; return;
  }
  cf.style.display = 'block';
  var sub = 0, h = '';
  for (var i = 0; i < CK.length; i++) {
    var k = CK[i], v = C[k], s = v.info.precio * v.qty; sub += s;
    var im = v.info.imagen
      ? '<img src="' + he(v.info.imagen) + '" alt="">'
      : '<span style="font-size:1.2rem">🧴</span>';
    h += '<div class="ci">'
       + '<div class="cii">' + im + '</div>'
       + '<div class="cio">'
       + '<div class="cin">' + he(v.info.producto) + '</div>'
       + '<div class="cip">' + he(v.info.presentacion) + '</div>'
       + '<div class="cis">' + fmt(s) + '</div>'
       + '</div>'
       + '<div class="ciq">'
       + '<button data-dci="' + i + '">−</button>'
       + '<span>' + v.qty + '</span>'
       + '<button data-ici="' + i + '">+</button>'
       + '</div></div>';
  }
  ci.innerHTML = h;
  var env = sub >= MG ? 0 : ENV;
  document.getElementById('sv').textContent = fmt(sub);
  document.getElementById('ev').textContent = env === 0 ? '¡Gratis! 🎉' : fmt(env);
  document.getElementById('el').textContent = sub >= MG ? 'Envío (gratis ≥$60.000)' : 'Envío (gratis desde $60.000)';
  document.getElementById('er').className = 'tr' + (env === 0 ? ' grat' : '');
  document.getElementById('tv').textContent = fmt(sub + env);
  document.getElementById('ok').disabled = false;
}

/* Delegación de eventos para carrito */
document.addEventListener('click', function(e) {
  var dci = e.target.dataset.dci;
  var ici = e.target.dataset.ici;
  if (dci !== undefined) decC(parseInt(dci, 10));
  else if (ici !== undefined) incC(parseInt(ici, 10));
});

function abrirC() { renderCar(); document.getElementById('ov').classList.add('on'); document.getElementById('pan').classList.add('on'); }
function cerrarC() { document.getElementById('ov').classList.remove('on'); document.getElementById('pan').classList.remove('on'); }

/* ── CONFIRMAR ── */
function confirmar() {
  var ok = document.getElementById('ok');
  ok.disabled = true; ok.textContent = 'Procesando...';
  var items = CK.map(function(k) {
    var v = C[k];
    return { producto: v.info.producto, presentacion: v.info.presentacion,
             cantidad: v.qty, precio_unitario: v.info.precio, subtotal: v.info.precio * v.qty };
  });
  fetch('/tienda/confirmar', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ telefono: TEL, productos: items })
  })
  .then(function(r) { return r.json(); })
  .then(function(d) {
    if (d.checkout_url) {
      cerrarC();
      document.getElementById('lnk').href = d.checkout_url;
      document.getElementById('ex').classList.add('on');
      window.open(d.checkout_url, '_blank');
    } else {
      tst('Error: ' + (d.error || 'intenta de nuevo'), 3500);
      ok.disabled = false; ok.textContent = 'Confirmar pedido →';
    }
  })
  .catch(function() {
    tst('Error de conexión. Intenta de nuevo.', 3500);
    ok.disabled = false; ok.textContent = 'Confirmar pedido →';
  });
}

/* ── TOAST ── */
var _tt;
function tst(m, ms) {
  var el = document.getElementById('tst');
  el.textContent = m; el.classList.add('on');
  clearTimeout(_tt); _tt = setTimeout(function() { el.classList.remove('on'); }, ms || 2000);
}

/* ── INICIO: carga catálogo desde servidor ── */
document.getElementById('grd').innerHTML =
  '<p style="color:#aaa;text-align:center;padding:40px;grid-column:1/-1">Cargando catálogo...</p>';

fetch('/tienda/productos')
  .then(function(r) {
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  })
  .then(function(data) {
    /* Actualizar logo si el servidor lo devuelve */
    if (data && data.logo) {
      var lw = document.querySelector('.lw');
      if (lw) lw.innerHTML = '<img src="' + he(data.logo) + '" alt="Equora">';
    }
    P = (data && data.productos) ? data.productos : (Array.isArray(data) ? data : []);
    renderFil();
    renderGrd();
  })
  .catch(function(err) {
    document.getElementById('grd').innerHTML =
      '<p style="color:#c00;text-align:center;padding:40px;grid-column:1/-1">'
      + 'Error cargando catálogo. Recarga la página.<br><small>' + err + '</small></p>';
  });
</script>
</body>
</html>
"""


def obtener_tienda_html(logo_url: str = "", productos: list = None) -> str:
    """Genera el HTML con el logo inyectado. El catálogo lo carga el JS via fetch."""
    logo_tag = ('<img src="' + logo_url + '" alt="Equora">') if logo_url else '<span class="lf">💧</span>'
    return _HTML.replace('LOGO_AQUI', logo_tag)
