"""
agent/tienda.py — Mini-tienda web para Equora Distribuciones
Sirve una página móvil donde el cliente elige productos, cantidades y genera el checkout.
"""

TIENDA_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1"/>
<title>Equora Distribuciones — Catálogo</title>
<style>
  :root{
    --verde:#2d6a4f;
    --verde-claro:#52b788;
    --verde-fondo:#d8f3dc;
    --gris-bg:#f4f4f4;
    --texto:#222;
    --borde:#ddd;
    --rojo:#e63946;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
       background:var(--gris-bg);color:var(--texto);min-height:100vh}

  /* HEADER */
  header{background:var(--verde);color:#fff;padding:14px 16px;
         display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:100}
  header img{width:40px;height:40px;border-radius:50%;object-fit:cover}
  header h1{font-size:1.1rem;font-weight:700;flex:1}
  #btn-carrito{background:var(--verde-claro);border:none;color:#fff;
               padding:8px 14px;border-radius:20px;font-size:.85rem;
               font-weight:600;cursor:pointer;display:flex;align-items:center;gap:6px}
  #badge{background:#fff;color:var(--verde);border-radius:50%;
         width:20px;height:20px;display:inline-flex;align-items:center;
         justify-content:center;font-size:.75rem;font-weight:700;
         display:none}

  /* FILTROS CATEGORÍAS */
  #filtros{display:flex;gap:8px;padding:12px 16px;overflow-x:auto;
           background:#fff;border-bottom:1px solid var(--borde)}
  #filtros::-webkit-scrollbar{display:none}
  .filtro-btn{white-space:nowrap;padding:6px 14px;border-radius:20px;
              border:1.5px solid var(--verde);background:#fff;
              color:var(--verde);font-size:.8rem;font-weight:600;cursor:pointer}
  .filtro-btn.activo{background:var(--verde);color:#fff}

  /* GRID PRODUCTOS */
  #productos{padding:12px 16px;display:grid;
             grid-template-columns:repeat(auto-fill,minmax(160px,1fr));
             gap:12px}

  .card{background:#fff;border-radius:12px;overflow:hidden;
        box-shadow:0 1px 4px rgba(0,0,0,.08)}
  .card img{width:100%;height:120px;object-fit:cover;display:block}
  .card-no-img{width:100%;height:80px;background:var(--verde-fondo);
               display:flex;align-items:center;justify-content:center;
               font-size:1.8rem}
  .card-body{padding:10px}
  .card-nombre{font-size:.82rem;font-weight:700;margin-bottom:2px;
               line-height:1.3;color:var(--texto)}
  .card-pres{font-size:.75rem;color:#666;margin-bottom:6px}
  .card-precio{font-size:.95rem;font-weight:700;color:var(--verde);
               margin-bottom:8px}

  /* Contador de cantidad */
  .qty-ctrl{display:flex;align-items:center;gap:8px}
  .qty-btn{width:30px;height:30px;border-radius:50%;border:1.5px solid var(--verde);
           background:#fff;color:var(--verde);font-size:1.1rem;font-weight:700;
           cursor:pointer;display:flex;align-items:center;justify-content:center}
  .qty-num{font-size:.9rem;font-weight:700;min-width:18px;text-align:center}
  .agregar-btn{flex:1;background:var(--verde);color:#fff;border:none;
               border-radius:8px;padding:6px 0;font-size:.8rem;font-weight:600;
               cursor:pointer;transition:opacity .15s}
  .agregar-btn:hover{opacity:.85}
  .agregado-badge{background:var(--verde-fondo);color:var(--verde);
                  border-radius:8px;padding:6px 0;font-size:.8rem;
                  font-weight:600;text-align:center}

  /* CARRITO MODAL */
  #overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:200}
  #overlay.abierto{display:block}
  #carrito-panel{position:fixed;bottom:0;left:0;right:0;max-height:80vh;
                 background:#fff;border-radius:20px 20px 0 0;
                 z-index:201;display:flex;flex-direction:column;
                 transform:translateY(100%);transition:transform .3s ease}
  #carrito-panel.abierto{transform:translateY(0)}
  #carrito-header{padding:16px;border-bottom:1px solid var(--borde);
                  display:flex;align-items:center;justify-content:space-between}
  #carrito-header h2{font-size:1rem;font-weight:700}
  #cerrar-carrito{background:none;border:none;font-size:1.4rem;cursor:pointer;color:#666}
  #carrito-items{overflow-y:auto;flex:1;padding:12px 16px}
  .ci{display:flex;align-items:center;gap:10px;padding:10px 0;
      border-bottom:1px solid #eee}
  .ci-info{flex:1}
  .ci-nombre{font-size:.85rem;font-weight:600}
  .ci-pres{font-size:.75rem;color:#666}
  .ci-precio{font-size:.85rem;color:var(--verde);font-weight:700;margin-top:2px}
  .ci-qty{display:flex;align-items:center;gap:6px}
  .ci-qty button{width:26px;height:26px;border-radius:50%;border:1.5px solid var(--verde);
                 background:#fff;color:var(--verde);font-size:1rem;font-weight:700;cursor:pointer}
  .ci-qty span{min-width:18px;text-align:center;font-weight:700;font-size:.9rem}
  #carrito-footer{padding:16px;border-top:1px solid var(--borde)}
  #total-line{display:flex;justify-content:space-between;margin-bottom:8px;
              font-size:.85rem;color:#555}
  #envio-line{display:flex;justify-content:space-between;margin-bottom:12px;
              font-size:.85rem;color:#555}
  #total-final{display:flex;justify-content:space-between;font-size:1rem;
               font-weight:700;margin-bottom:14px}
  #btn-confirmar{width:100%;padding:14px;background:var(--verde);color:#fff;
                 border:none;border-radius:12px;font-size:1rem;font-weight:700;
                 cursor:pointer}
  #btn-confirmar:disabled{opacity:.5;cursor:not-allowed}
  #carrito-vacio{text-align:center;padding:30px 0;color:#999;font-size:.9rem}

  /* PANTALLA ÉXITO */
  #exito{display:none;position:fixed;inset:0;background:#fff;z-index:300;
         flex-direction:column;align-items:center;justify-content:center;
         gap:16px;padding:24px;text-align:center}
  #exito.visible{display:flex}
  #exito .icono{font-size:3.5rem}
  #exito h2{color:var(--verde);font-size:1.4rem}
  #exito p{color:#555;font-size:.9rem;max-width:280px}
  #exito a{display:block;margin-top:8px;background:var(--verde);color:#fff;
           text-decoration:none;padding:14px 32px;border-radius:12px;
           font-size:1rem;font-weight:700}

  /* LOADING */
  #loading{display:flex;flex-direction:column;align-items:center;
           justify-content:center;min-height:40vh;gap:12px;color:#888}
  .spinner{width:36px;height:36px;border:4px solid var(--verde-fondo);
           border-top-color:var(--verde);border-radius:50%;
           animation:spin .8s linear infinite}
  @keyframes spin{to{transform:rotate(360deg)}}

  /* Toast */
  #toast{position:fixed;bottom:80px;left:50%;transform:translateX(-50%);
         background:#333;color:#fff;padding:8px 18px;border-radius:20px;
         font-size:.85rem;opacity:0;transition:opacity .3s;pointer-events:none;
         white-space:nowrap;z-index:400}
  #toast.show{opacity:1}
</style>
</head>
<body>

<header>
  <div style="width:40px;height:40px;border-radius:50%;background:var(--verde-claro);
       display:flex;align-items:center;justify-content:center;font-size:1.4rem">🌿</div>
  <h1>Equora Distribuciones</h1>
  <button id="btn-carrito" onclick="abrirCarrito()">
    🛒 Carrito <span id="badge">0</span>
  </button>
</header>

<div id="filtros"></div>
<div id="productos"><div id="loading"><div class="spinner"></div><p>Cargando catálogo…</p></div></div>

<!-- MODAL CARRITO -->
<div id="overlay" onclick="cerrarCarrito()"></div>
<div id="carrito-panel">
  <div id="carrito-header">
    <h2>🛒 Tu pedido</h2>
    <button id="cerrar-carrito" onclick="cerrarCarrito()">✕</button>
  </div>
  <div id="carrito-items">
    <div id="carrito-vacio">Tu carrito está vacío 🌿</div>
  </div>
  <div id="carrito-footer">
    <div id="total-line"><span>Subtotal</span><span id="subtotal-val">$0</span></div>
    <div id="envio-line"><span id="envio-label">Envío</span><span id="envio-val">—</span></div>
    <div id="total-final"><span>Total</span><span id="total-val">$0</span></div>
    <button id="btn-confirmar" onclick="confirmarPedido()" disabled>
      Confirmar pedido →
    </button>
  </div>
</div>

<!-- PANTALLA ÉXITO -->
<div id="exito">
  <div class="icono">🎉</div>
  <h2>¡Pedido confirmado!</h2>
  <p>Toca el botón para ingresar tu dirección de entrega. El pago es contra entrega.</p>
  <a id="checkout-link" href="#" target="_blank">Completar pedido →</a>
  <p style="margin-top:8px;font-size:.8rem;color:#aaa">
    Ya puedes cerrar esta ventana y volver a WhatsApp
  </p>
</div>

<div id="toast"></div>

<script>
const COSTO_ENVIO = 7000;
const MINIMO_ENVIO_GRATIS = 60000;

let productos = [];
let carrito = {};        // clave: "producto||presentacion" → {info, qty}
let categoriaActiva = 'Todos';

// Leer telefono y canal desde URL
const params = new URLSearchParams(location.search);
const telefono = params.get('tel') || '';

// ── CARGA INICIAL ─────────────────────────────────────────────────────────────
async function cargarProductos() {
  try {
    const r = await fetch('/tienda/productos');
    if (!r.ok) throw new Error('Error cargando productos');
    productos = await r.json();
    renderFiltros();
    renderProductos();
  } catch(e) {
    document.getElementById('loading').innerHTML =
      '<p>⚠️ No se pudo cargar el catálogo.<br>Recarga la página para intentar de nuevo.</p>';
  }
}

// ── FILTROS ───────────────────────────────────────────────────────────────────
function renderFiltros() {
  const cats = ['Todos', ...new Set(productos.map(p => p.categoria).filter(Boolean))];
  const cont = document.getElementById('filtros');
  cont.innerHTML = cats.map(c =>
    `<button class="filtro-btn${c===categoriaActiva?' activo':''}"
      onclick="filtrar('${c}')">${c}</button>`
  ).join('');
}

function filtrar(cat) {
  categoriaActiva = cat;
  renderFiltros();
  renderProductos();
}

// ── GRID DE PRODUCTOS ─────────────────────────────────────────────────────────
function renderProductos() {
  const lista = categoriaActiva === 'Todos'
    ? productos
    : productos.filter(p => p.categoria === categoriaActiva);

  const cont = document.getElementById('productos');
  if (!lista.length) {
    cont.innerHTML = '<p style="color:#999;text-align:center;padding:30px">Sin productos en esta categoría</p>';
    return;
  }
  cont.innerHTML = lista.map(p => {
    const k = clave(p);
    const qty = carrito[k]?.qty || 0;
    const precio = '$' + p.precio.toLocaleString('es-CO');
    const img = p.imagen
      ? `<img src="${p.imagen}" alt="${p.producto}" loading="lazy"/>`
      : `<div class="card-no-img">🧴</div>`;
    const stock = typeof p.stock === 'number' ? p.stock : 9999;
    const agotado = stock <= 0;

    let accion = '';
    if (agotado) {
      accion = `<div style="text-align:center;font-size:.75rem;color:#999">Agotado</div>`;
    } else if (qty === 0) {
      accion = `<button class="agregar-btn" onclick="agregar('${escK(k)}')">+ Agregar</button>`;
    } else {
      accion = `
        <div class="qty-ctrl">
          <button class="qty-btn" onclick="restar('${escK(k)}')">−</button>
          <span class="qty-num">${qty}</span>
          <button class="qty-btn" onclick="sumar('${escK(k)}',${stock})">+</button>
        </div>`;
    }

    return `<div class="card" id="card-${escK(k)}">
      ${img}
      <div class="card-body">
        <div class="card-nombre">${p.producto}</div>
        <div class="card-pres">${p.presentacion}</div>
        <div class="card-precio">${precio}</div>
        ${accion}
      </div>
    </div>`;
  }).join('');
}

function clave(p) { return p.producto + '||' + p.presentacion; }
function escK(k) { return k.replace(/'/g,"&#39;"); }

// ── ACCIONES CARRITO ──────────────────────────────────────────────────────────
function agregar(k) {
  const p = buscarProducto(desescK(k));
  if (!p) return;
  const stock = typeof p.stock === 'number' ? p.stock : 9999;
  carrito[desescK(k)] = { info: p, qty: 1, stock };
  actualizarUI();
  toast('Agregado al carrito 🌿');
}

function sumar(k, stock) {
  const rk = desescK(k);
  if (!carrito[rk]) return;
  if (carrito[rk].qty < stock) carrito[rk].qty++;
  actualizarUI();
}

function restar(k) {
  const rk = desescK(k);
  if (!carrito[rk]) return;
  carrito[rk].qty--;
  if (carrito[rk].qty <= 0) delete carrito[rk];
  actualizarUI();
}

function desescK(k) { return k.replace(/&#39;/g,"'"); }

function buscarProducto(k) {
  const [prod, pres] = k.split('||');
  return productos.find(p => p.producto === prod && p.presentacion === pres);
}

// ── ACTUALIZAR TODA LA UI ─────────────────────────────────────────────────────
function actualizarUI() {
  const items = Object.entries(carrito);
  const total_items = items.reduce((a,[,v]) => a + v.qty, 0);
  const badge = document.getElementById('badge');
  if (total_items > 0) { badge.style.display='inline-flex'; badge.textContent=total_items; }
  else badge.style.display='none';

  // Actualizar solo las cards afectadas (sin re-render completo para no perder scroll)
  renderProductos();
  renderCarritoPanel();
}

function renderCarritoPanel() {
  const items = Object.entries(carrito);
  const cont = document.getElementById('carrito-items');
  const vacio = document.getElementById('carrito-vacio');
  const footer = document.getElementById('carrito-footer');
  const btn = document.getElementById('btn-confirmar');

  if (!items.length) {
    cont.innerHTML = '<div id="carrito-vacio">Tu carrito está vacío 🌿</div>';
    footer.style.display = 'none';
    return;
  }
  footer.style.display = 'block';

  let subtotal = 0;
  cont.innerHTML = items.map(([k, {info, qty}]) => {
    const sub = info.precio * qty;
    subtotal += sub;
    return `<div class="ci">
      <div class="ci-info">
        <div class="ci-nombre">${info.producto}</div>
        <div class="ci-pres">${info.presentacion}</div>
        <div class="ci-precio">$${sub.toLocaleString('es-CO')}</div>
      </div>
      <div class="ci-qty">
        <button onclick="restar('${escK(k)}')">−</button>
        <span>${qty}</span>
        <button onclick="sumar('${escK(k)}',${info.stock||9999})">+</button>
      </div>
    </div>`;
  }).join('');

  const envio = subtotal >= MINIMO_ENVIO_GRATIS ? 0 : COSTO_ENVIO;
  const total = subtotal + envio;

  document.getElementById('subtotal-val').textContent = '$'+subtotal.toLocaleString('es-CO');
  document.getElementById('envio-val').textContent = envio === 0
    ? '¡Gratis! 🎉' : '$'+envio.toLocaleString('es-CO');
  document.getElementById('envio-label').textContent = subtotal >= MINIMO_ENVIO_GRATIS
    ? 'Envío (gratis ≥$60.000)' : `Envío (gratis desde $60.000)`;
  document.getElementById('total-val').textContent = '$'+total.toLocaleString('es-CO');
  btn.disabled = false;
}

// ── MODAL ─────────────────────────────────────────────────────────────────────
function abrirCarrito() {
  document.getElementById('overlay').classList.add('abierto');
  document.getElementById('carrito-panel').classList.add('abierto');
}
function cerrarCarrito() {
  document.getElementById('overlay').classList.remove('abierto');
  document.getElementById('carrito-panel').classList.remove('abierto');
}

// ── CONFIRMAR PEDIDO ──────────────────────────────────────────────────────────
async function confirmarPedido() {
  const btn = document.getElementById('btn-confirmar');
  btn.disabled = true;
  btn.textContent = 'Procesando…';

  const items = Object.values(carrito).map(({info, qty}) => ({
    producto: info.producto,
    presentacion: info.presentacion,
    cantidad: qty,
    precio_unitario: info.precio,
    subtotal: info.precio * qty,
  }));

  try {
    const r = await fetch('/tienda/confirmar', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ telefono, productos: items }),
    });
    const data = await r.json();
    if (data.checkout_url) {
      cerrarCarrito();
      document.getElementById('checkout-link').href = data.checkout_url;
      document.getElementById('exito').classList.add('visible');
      // Abrir checkout automáticamente
      window.open(data.checkout_url, '_blank');
    } else {
      toast('⚠️ ' + (data.error || 'No se pudo generar el pedido'), 3000);
      btn.disabled = false;
      btn.textContent = 'Confirmar pedido →';
    }
  } catch(e) {
    toast('⚠️ Error de conexión. Intenta de nuevo.', 3000);
    btn.disabled = false;
    btn.textContent = 'Confirmar pedido →';
  }
}

// ── TOAST ─────────────────────────────────────────────────────────────────────
let toastTimer;
function toast(msg, ms=2000) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), ms);
}

cargarProductos();
</script>
</body>
</html>
"""
