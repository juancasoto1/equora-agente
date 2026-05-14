"""
agent/tienda.py — Mini-tienda web para Equora Distribuciones
Sirve una página móvil donde el cliente elige productos, cantidades y genera el checkout.
"""

_TIENDA_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1"/>
<title>Equora Distribuciones — Catálogo</title>
<style>
  :root{
    --azul:#1a3a6b;
    --verde:#2d7d3a;
    --verde-claro:#4caf50;
    --verde-fondo:#e8f5e9;
    --gris-bg:#f5f5f5;
    --texto:#1a1a1a;
    --borde:#e0e0e0;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
       background:var(--gris-bg);color:var(--texto);min-height:100vh}

  /* HEADER */
  header{background:var(--azul);color:#fff;padding:10px 14px;
         display:flex;align-items:center;gap:10px;
         position:sticky;top:0;z-index:100;
         box-shadow:0 2px 8px rgba(0,0,0,.25)}
  .logo-wrap{width:44px;height:44px;flex-shrink:0;
             border-radius:50%;overflow:hidden;background:#fff;
             display:flex;align-items:center;justify-content:center}
  .logo-wrap img{width:100%;height:100%;object-fit:contain}
  .logo-fallback{font-size:1.6rem;line-height:1}
  header h1{font-size:1rem;font-weight:700;flex:1;line-height:1.2}
  header small{display:block;font-size:.7rem;font-weight:400;opacity:.8}

  /* BOTÓN CARRITO */
  #btn-carrito{position:relative;background:rgba(255,255,255,.15);
               border:1.5px solid rgba(255,255,255,.4);
               color:#fff;width:46px;height:46px;border-radius:50%;
               cursor:pointer;display:flex;align-items:center;
               justify-content:center;font-size:1.3rem;flex-shrink:0;
               transition:background .2s}
  #btn-carrito:hover{background:rgba(255,255,255,.25)}
  #badge{position:absolute;top:-4px;right:-4px;
         background:#f44336;color:#fff;border-radius:50%;
         width:18px;height:18px;display:none;align-items:center;
         justify-content:center;font-size:.65rem;font-weight:700;
         border:2px solid var(--azul)}

  /* FILTROS */
  #filtros{display:flex;gap:8px;padding:10px 14px;overflow-x:auto;
           background:#fff;border-bottom:1px solid var(--borde);
           -webkit-overflow-scrolling:touch}
  #filtros::-webkit-scrollbar{display:none}
  .filtro-btn{white-space:nowrap;padding:6px 14px;border-radius:20px;
              border:1.5px solid var(--azul);background:#fff;
              color:var(--azul);font-size:.78rem;font-weight:600;cursor:pointer;
              transition:all .15s}
  .filtro-btn.activo{background:var(--azul);color:#fff;border-color:var(--azul)}

  /* GRID PRODUCTOS */
  #productos{padding:12px 14px;
             display:grid;
             grid-template-columns:repeat(auto-fill,minmax(155px,1fr));
             gap:12px}

  .card{background:#fff;border-radius:12px;overflow:hidden;
        box-shadow:0 1px 4px rgba(0,0,0,.08);
        transition:box-shadow .2s}
  .card:active{box-shadow:0 3px 10px rgba(0,0,0,.15)}
  .card-img-wrap{width:100%;height:130px;overflow:hidden;background:#f9f9f9;
                 display:flex;align-items:center;justify-content:center}
  .card-img-wrap img{width:100%;height:100%;object-fit:cover;display:block;
                     transition:opacity .3s}
  .card-img-wrap img.loading{opacity:0}
  .card-no-img{font-size:2.2rem}
  .card-body{padding:10px}
  .card-nombre{font-size:.8rem;font-weight:700;margin-bottom:2px;
               line-height:1.3;color:var(--texto)}
  .card-pres{font-size:.72rem;color:#777;margin-bottom:6px}
  .card-precio{font-size:.95rem;font-weight:700;
               color:var(--azul);margin-bottom:8px}

  /* Controles cantidad */
  .qty-ctrl{display:flex;align-items:center;gap:8px}
  .qty-btn{width:30px;height:30px;border-radius:50%;
           border:1.5px solid var(--verde);background:#fff;
           color:var(--verde);font-size:1.1rem;font-weight:700;
           cursor:pointer;display:flex;align-items:center;justify-content:center;
           transition:all .15s}
  .qty-btn:active{background:var(--verde);color:#fff}
  .qty-num{font-size:.9rem;font-weight:700;min-width:20px;text-align:center}
  .agregar-btn{width:100%;background:var(--verde);color:#fff;border:none;
               border-radius:8px;padding:7px 0;font-size:.82rem;font-weight:600;
               cursor:pointer;transition:opacity .15s}
  .agregar-btn:hover{opacity:.85}

  /* MODAL CARRITO */
  #overlay{display:none;position:fixed;inset:0;
           background:rgba(0,0,0,.5);z-index:200;
           backdrop-filter:blur(2px)}
  #overlay.abierto{display:block}
  #carrito-panel{position:fixed;bottom:0;left:0;right:0;max-height:82vh;
                 background:#fff;border-radius:20px 20px 0 0;
                 z-index:201;display:flex;flex-direction:column;
                 transform:translateY(100%);
                 transition:transform .3s cubic-bezier(.4,0,.2,1)}
  #carrito-panel.abierto{transform:translateY(0)}

  /* Handle visual */
  #carrito-panel::before{content:'';display:block;width:40px;height:4px;
                         background:#ddd;border-radius:2px;
                         margin:10px auto 0}

  #carrito-header{padding:12px 16px 10px;border-bottom:1px solid var(--borde);
                  display:flex;align-items:center;justify-content:space-between}
  #carrito-header h2{font-size:.95rem;font-weight:700;color:var(--azul)}
  #cerrar-carrito{background:none;border:none;font-size:1.3rem;
                  cursor:pointer;color:#888;padding:4px}

  #carrito-items{overflow-y:auto;flex:1;padding:0 14px}
  .ci{display:flex;align-items:center;gap:10px;padding:10px 0;
      border-bottom:1px solid #f0f0f0}
  .ci-img{width:48px;height:48px;border-radius:8px;overflow:hidden;
          flex-shrink:0;background:#f5f5f5;
          display:flex;align-items:center;justify-content:center}
  .ci-img img{width:100%;height:100%;object-fit:cover}
  .ci-img .noimg{font-size:1.4rem}
  .ci-info{flex:1;min-width:0}
  .ci-nombre{font-size:.82rem;font-weight:700;
             white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .ci-pres{font-size:.72rem;color:#777}
  .ci-precio{font-size:.82rem;color:var(--azul);font-weight:700;margin-top:2px}
  .ci-qty{display:flex;align-items:center;gap:6px;flex-shrink:0}
  .ci-qty button{width:26px;height:26px;border-radius:50%;
                 border:1.5px solid var(--verde);background:#fff;
                 color:var(--verde);font-size:1rem;font-weight:700;
                 cursor:pointer;display:flex;align-items:center;justify-content:center}
  .ci-qty span{min-width:18px;text-align:center;
               font-weight:700;font-size:.88rem}

  #carrito-footer{padding:12px 16px 20px;border-top:1px solid var(--borde)}
  .total-row{display:flex;justify-content:space-between;
             font-size:.83rem;color:#666;margin-bottom:6px}
  .total-row.envio-gratis span:last-child{color:var(--verde);font-weight:700}
  #total-final{display:flex;justify-content:space-between;
               font-size:1rem;font-weight:700;color:var(--azul);
               margin:8px 0 14px;padding-top:8px;
               border-top:1px solid var(--borde)}
  #btn-confirmar{width:100%;padding:14px;
                 background:linear-gradient(135deg,var(--azul),var(--verde));
                 color:#fff;border:none;border-radius:12px;
                 font-size:1rem;font-weight:700;cursor:pointer;
                 letter-spacing:.3px;transition:opacity .2s}
  #btn-confirmar:disabled{opacity:.5;cursor:not-allowed}
  #carrito-vacio{text-align:center;padding:40px 0;color:#bbb}
  #carrito-vacio .icono{font-size:2.5rem;margin-bottom:8px}
  #carrito-vacio p{font-size:.88rem}

  /* PANTALLA ÉXITO */
  #exito{display:none;position:fixed;inset:0;background:#fff;
         z-index:300;flex-direction:column;align-items:center;
         justify-content:center;gap:14px;padding:28px;text-align:center}
  #exito.visible{display:flex}
  #exito .icono{font-size:4rem}
  #exito h2{color:var(--azul);font-size:1.4rem;font-weight:800}
  #exito p{color:#555;font-size:.88rem;max-width:280px;line-height:1.5}
  #checkout-link{display:block;margin-top:6px;
                 background:linear-gradient(135deg,var(--azul),var(--verde));
                 color:#fff;text-decoration:none;
                 padding:14px 32px;border-radius:12px;
                 font-size:1rem;font-weight:700}
  #exito .sub{font-size:.78rem;color:#bbb;margin-top:4px}

  /* LOADING */
  #loading{display:flex;flex-direction:column;align-items:center;
           justify-content:center;min-height:40vh;gap:12px;color:#aaa}
  .spinner{width:36px;height:36px;
           border:4px solid var(--verde-fondo);
           border-top-color:var(--verde);border-radius:50%;
           animation:spin .7s linear infinite}
  @keyframes spin{to{transform:rotate(360deg)}}

  /* TOAST */
  #toast{position:fixed;bottom:90px;left:50%;
         transform:translateX(-50%);
         background:rgba(26,26,26,.88);color:#fff;
         padding:9px 20px;border-radius:24px;
         font-size:.83rem;opacity:0;
         transition:opacity .25s;pointer-events:none;
         white-space:nowrap;z-index:400;
         backdrop-filter:blur(4px)}
  #toast.show{opacity:1}

  /* BANNER envío gratis */
  #banner-envio{background:linear-gradient(90deg,var(--azul),var(--verde));
                color:#fff;text-align:center;padding:7px 14px;
                font-size:.78rem;font-weight:600;
                display:flex;align-items:center;justify-content:center;gap:6px}
</style>
</head>
<body>

<header>
  <div class="logo-wrap">
    __LOGO_TAG__
  </div>
  <h1>Equora Distribuciones<small>Productos Biotú 🌿</small></h1>
  <button id="btn-carrito" onclick="abrirCarrito()" aria-label="Ver carrito">
    🛒
    <span id="badge"></span>
  </button>
</header>

<div id="banner-envio">🎁 Envío GRATIS en pedidos desde $60.000</div>
<div id="filtros"></div>
<div id="productos">
  <div id="loading"><div class="spinner"></div><p>Cargando catálogo…</p></div>
</div>

<!-- MODAL CARRITO -->
<div id="overlay" onclick="cerrarCarrito()"></div>
<div id="carrito-panel">
  <div id="carrito-header">
    <h2>🛒 Tu pedido</h2>
    <button id="cerrar-carrito" onclick="cerrarCarrito()">✕</button>
  </div>
  <div id="carrito-items">
    <div id="carrito-vacio">
      <div class="icono">🛒</div>
      <p>Tu carrito está vacío</p>
    </div>
  </div>
  <div id="carrito-footer" style="display:none">
    <div class="total-row"><span>Subtotal</span><span id="subtotal-val">$0</span></div>
    <div class="total-row" id="envio-row">
      <span id="envio-label">Envío</span>
      <span id="envio-val">$7.000</span>
    </div>
    <div id="total-final">
      <span>Total a pagar</span><span id="total-val">$0</span>
    </div>
    <button id="btn-confirmar" onclick="confirmarPedido()" disabled>
      Confirmar pedido →
    </button>
  </div>
</div>

<!-- PANTALLA ÉXITO -->
<div id="exito">
  <div class="icono">🎉</div>
  <h2>¡Pedido confirmado!</h2>
  <p>Ingresa tu dirección de entrega en el siguiente paso.<br>El pago es <strong>contra entrega</strong>.</p>
  <a id="checkout-link" href="#" target="_blank">Completar pedido →</a>
  <p class="sub">Puedes cerrar esta ventana y volver a WhatsApp</p>
</div>

<div id="toast"></div>

<script>
const COSTO_ENVIO = 7000;
const MINIMO_GRATIS = 60000;

let productos = [];
let carrito = {};
let categoriaActiva = 'Todos';

const params = new URLSearchParams(location.search);
const telefono = params.get('tel') || '';

// ── CARGA ────────────────────────────────────────────────────────────────────
async function cargarProductos() {
  try {
    const r = await fetch('/tienda/productos');
    if (!r.ok) throw new Error();
    productos = await r.json();
    renderFiltros();
    renderProductos();
  } catch {
    document.getElementById('loading').innerHTML =
      '<p style="color:#f44336">⚠️ No se pudo cargar el catálogo.<br>Recarga la página.</p>';
  }
}

// ── FILTROS ───────────────────────────────────────────────────────────────────
function renderFiltros() {
  const orden = ['Todos','Lavandería','Cocina','Hogar','Talleres / Industrial','Higiene Personal','Otros'];
  const disponibles = new Set(productos.map(p => p.categoria).filter(Boolean));
  const cats = orden.filter(c => c === 'Todos' || disponibles.has(c));

  document.getElementById('filtros').innerHTML = cats.map(c =>
    `<button class="filtro-btn${c===categoriaActiva?' activo':''}" onclick="filtrar('${esc(c)}')">${c}</button>`
  ).join('');
}

function filtrar(cat) {
  categoriaActiva = cat;
  renderFiltros();
  renderProductos();
}

// ── GRID ───────────────────────────────────────────────────────────────────
function renderProductos() {
  const lista = categoriaActiva === 'Todos'
    ? productos
    : productos.filter(p => p.categoria === categoriaActiva);

  const cont = document.getElementById('productos');
  if (!lista.length) {
    cont.innerHTML = '<p style="color:#bbb;text-align:center;padding:40px;grid-column:1/-1">Sin productos en esta categoría</p>';
    return;
  }

  cont.innerHTML = lista.map(p => {
    const k = clave(p);
    const qty = carrito[k]?.qty || 0;
    const fmt = n => '$' + n.toLocaleString('es-CO');
    const stock = typeof p.stock === 'number' ? p.stock : 9999;
    const agotado = stock <= 0;

    const imgHtml = p.imagen
      ? `<img src="${p.imagen}" alt="${htmlEnc(p.presentacion)}" class="loading"
           onload="this.classList.remove('loading')"
           onerror="this.parentElement.innerHTML='<span class=\\'card-no-img\\'>🧴</span>'">`
      : '<span class="card-no-img">🧴</span>';

    let accion;
    if (agotado) {
      accion = '<p style="text-align:center;font-size:.75rem;color:#bbb">Agotado</p>';
    } else if (qty === 0) {
      accion = `<button class="agregar-btn" onclick="agregar('${esc(k)}')">+ Agregar</button>`;
    } else {
      accion = `<div class="qty-ctrl">
        <button class="qty-btn" onclick="restar('${esc(k)}')">−</button>
        <span class="qty-num">${qty}</span>
        <button class="qty-btn" onclick="sumar('${esc(k)}',${stock})">+</button>
      </div>`;
    }

    return `<div class="card" id="card-${esc(k)}">
      <div class="card-img-wrap">${imgHtml}</div>
      <div class="card-body">
        <div class="card-nombre">${htmlEnc(p.producto)}</div>
        <div class="card-pres">${htmlEnc(p.presentacion)}</div>
        <div class="card-precio">${fmt(p.precio)}</div>
        ${accion}
      </div>
    </div>`;
  }).join('');
}

// ── HELPERS ───────────────────────────────────────────────────────────────────
function clave(p) { return p.producto + '||' + p.presentacion; }
function esc(s) { return s.replace(/\\/g,'\\\\').replace(/'/g,"\\'"); }
function htmlEnc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function buscarProducto(k) {
  const [prod,pres] = k.split('||');
  return productos.find(p => p.producto===prod && p.presentacion===pres);
}

// ── CARRITO ───────────────────────────────────────────────────────────────────
function agregar(k) {
  const p = buscarProducto(k);
  if (!p) return;
  const stock = typeof p.stock === 'number' ? p.stock : 9999;
  carrito[k] = {info:p, qty:1, stock};
  actualizarUI();
  toast('Agregado 🌿');
}
function sumar(k, stock) {
  if (!carrito[k]) return;
  if (carrito[k].qty < stock) { carrito[k].qty++; actualizarUI(); }
  else toast('Stock máximo alcanzado');
}
function restar(k) {
  if (!carrito[k]) return;
  carrito[k].qty--;
  if (carrito[k].qty <= 0) delete carrito[k];
  actualizarUI();
}

function actualizarUI() {
  const items = Object.entries(carrito);
  const totalItems = items.reduce((a,[,v]) => a+v.qty, 0);
  const badge = document.getElementById('badge');
  if (totalItems > 0) { badge.style.display='flex'; badge.textContent=totalItems; }
  else badge.style.display='none';
  renderProductos();
  renderCarritoPanel();
}

function renderCarritoPanel() {
  const items = Object.entries(carrito);
  const cont = document.getElementById('carrito-items');
  const footer = document.getElementById('carrito-footer');
  const btn = document.getElementById('btn-confirmar');
  const fmt = n => '$' + n.toLocaleString('es-CO');

  if (!items.length) {
    cont.innerHTML = '<div id="carrito-vacio"><div class="icono">🛒</div><p>Tu carrito está vacío</p></div>';
    footer.style.display = 'none';
    return;
  }
  footer.style.display = 'block';

  let subtotal = 0;
  cont.innerHTML = items.map(([k,{info,qty}]) => {
    const sub = info.precio * qty;
    subtotal += sub;
    const imgHtml = info.imagen
      ? `<img src="${info.imagen}" alt="">`
      : '<span class="noimg">🧴</span>';
    return `<div class="ci">
      <div class="ci-img">${imgHtml}</div>
      <div class="ci-info">
        <div class="ci-nombre">${htmlEnc(info.producto)}</div>
        <div class="ci-pres">${htmlEnc(info.presentacion)}</div>
        <div class="ci-precio">${fmt(sub)}</div>
      </div>
      <div class="ci-qty">
        <button onclick="restar('${esc(k)}')">−</button>
        <span>${qty}</span>
        <button onclick="sumar('${esc(k)}',${info.stock||9999})">+</button>
      </div>
    </div>`;
  }).join('');

  const envio = subtotal >= MINIMO_GRATIS ? 0 : COSTO_ENVIO;
  const total = subtotal + envio;
  const envioRow = document.getElementById('envio-row');

  document.getElementById('subtotal-val').textContent = fmt(subtotal);
  document.getElementById('envio-val').textContent = envio === 0 ? '¡Gratis! 🎉' : fmt(envio);
  document.getElementById('envio-label').textContent =
    subtotal >= MINIMO_GRATIS ? 'Envío (gratis ≥$60.000)' : 'Envío (gratis desde $60.000)';
  envioRow.className = 'total-row' + (envio===0 ? ' envio-gratis' : '');
  document.getElementById('total-val').textContent = fmt(total);
  btn.disabled = false;
}

// ── MODAL ─────────────────────────────────────────────────────────────────────
function abrirCarrito() {
  renderCarritoPanel();
  document.getElementById('overlay').classList.add('abierto');
  document.getElementById('carrito-panel').classList.add('abierto');
}
function cerrarCarrito() {
  document.getElementById('overlay').classList.remove('abierto');
  document.getElementById('carrito-panel').classList.remove('abierto');
}

// ── CONFIRMAR ─────────────────────────────────────────────────────────────────
async function confirmarPedido() {
  const btn = document.getElementById('btn-confirmar');
  btn.disabled = true;
  btn.textContent = 'Procesando…';

  const items = Object.values(carrito).map(({info,qty}) => ({
    producto: info.producto,
    presentacion: info.presentacion,
    cantidad: qty,
    precio_unitario: info.precio,
    subtotal: info.precio * qty,
  }));

  try {
    const r = await fetch('/tienda/confirmar', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({telefono, productos:items}),
    });
    const data = await r.json();
    if (data.checkout_url) {
      cerrarCarrito();
      document.getElementById('checkout-link').href = data.checkout_url;
      document.getElementById('exito').classList.add('visible');
      window.open(data.checkout_url, '_blank');
    } else {
      toast('⚠️ ' + (data.error || 'No se pudo generar el pedido'), 3500);
      btn.disabled = false;
      btn.textContent = 'Confirmar pedido →';
    }
  } catch {
    toast('⚠️ Error de conexión. Intenta de nuevo.', 3500);
    btn.disabled = false;
    btn.textContent = 'Confirmar pedido →';
  }
}

// ── TOAST ─────────────────────────────────────────────────────────────────────
let _tt;
function toast(msg, ms=2000) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(_tt);
  _tt = setTimeout(() => el.classList.remove('show'), ms);
}

cargarProductos();
</script>
</body>
</html>
"""


def obtener_tienda_html(logo_url: str = "") -> str:
    """Retorna el HTML de la tienda inyectando el logo de Equora."""
    if logo_url:
        logo_tag = f'<img src="{logo_url}" alt="Equora" onerror="this.parentElement.innerHTML=\'<span class=\\\'logo-fallback\\\'>💧</span>\'">'
    else:
        logo_tag = '<span class="logo-fallback">💧</span>'
    return _TIENDA_HTML_TEMPLATE.replace("__LOGO_TAG__", logo_tag)
