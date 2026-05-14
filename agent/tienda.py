"""
agent/tienda.py — Mini-tienda web para Equora Distribuciones
El catálogo se inyecta directamente en el HTML para evitar una segunda petición
que podía fallar por problemas de CORS, cache o timing.
"""

import json

_HTML = """\
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1"/>
<title>Equora Distribuciones</title>
<style>
:root{--azul:#1a3a6b;--verde:#2d7d3a;--verde-c:#4caf50;--verde-f:#e8f5e9;--gris:#f5f5f5;--txt:#1a1a1a;--borde:#e0e0e0}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--gris);color:var(--txt);min-height:100vh}
header{background:var(--azul);color:#fff;padding:10px 14px;display:flex;align-items:center;gap:10px;position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,.25)}
.logo-wrap{width:44px;height:44px;flex-shrink:0;border-radius:50%;overflow:hidden;background:#fff;display:flex;align-items:center;justify-content:center}
.logo-wrap img{width:100%;height:100%;object-fit:contain}
.logo-fb{font-size:1.6rem}
header h1{font-size:1rem;font-weight:700;flex:1;line-height:1.2}
header small{display:block;font-size:.7rem;font-weight:400;opacity:.8}
#btn-c{position:relative;background:rgba(255,255,255,.15);border:1.5px solid rgba(255,255,255,.4);color:#fff;width:46px;height:46px;border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:1.3rem;flex-shrink:0}
#bdg{position:absolute;top:-4px;right:-4px;background:#f44336;color:#fff;border-radius:50%;width:18px;height:18px;display:none;align-items:center;justify-content:center;font-size:.65rem;font-weight:700;border:2px solid var(--azul)}
#banner{background:linear-gradient(90deg,var(--azul),var(--verde));color:#fff;text-align:center;padding:7px 14px;font-size:.78rem;font-weight:600}
#filtros{display:flex;gap:8px;padding:10px 14px;overflow-x:auto;background:#fff;border-bottom:1px solid var(--borde);-webkit-overflow-scrolling:touch}
#filtros::-webkit-scrollbar{display:none}
.fb{white-space:nowrap;padding:6px 14px;border-radius:20px;border:1.5px solid var(--azul);background:#fff;color:var(--azul);font-size:.78rem;font-weight:600;cursor:pointer}
.fb.on{background:var(--azul);color:#fff}
#grid{padding:12px 14px;display:grid;grid-template-columns:repeat(auto-fill,minmax(155px,1fr));gap:12px}
.card{background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)}
.img-w{width:100%;height:130px;overflow:hidden;background:#f9f9f9;display:flex;align-items:center;justify-content:center}
.img-w img{width:100%;height:100%;object-fit:cover}
.no-img{font-size:2.2rem}
.cb{padding:10px}
.cn{font-size:.8rem;font-weight:700;margin-bottom:2px;line-height:1.3}
.cp{font-size:.72rem;color:#777;margin-bottom:6px}
.cpr{font-size:.95rem;font-weight:700;color:var(--azul);margin-bottom:8px}
.qc{display:flex;align-items:center;gap:8px}
.qb{width:30px;height:30px;border-radius:50%;border:1.5px solid var(--verde);background:#fff;color:var(--verde);font-size:1.1rem;font-weight:700;cursor:pointer;display:flex;align-items:center;justify-content:center}
.qn{font-size:.9rem;font-weight:700;min-width:20px;text-align:center}
.ab{width:100%;background:var(--verde);color:#fff;border:none;border-radius:8px;padding:7px 0;font-size:.82rem;font-weight:600;cursor:pointer}
#ov{display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:200}
#ov.on{display:block}
#cp{position:fixed;bottom:0;left:0;right:0;max-height:82vh;background:#fff;border-radius:20px 20px 0 0;z-index:201;display:flex;flex-direction:column;transform:translateY(100%);transition:transform .3s cubic-bezier(.4,0,.2,1)}
#cp::before{content:'';display:block;width:40px;height:4px;background:#ddd;border-radius:2px;margin:10px auto 0}
#cp.on{transform:translateY(0)}
#ch{padding:12px 16px 10px;border-bottom:1px solid var(--borde);display:flex;align-items:center;justify-content:space-between}
#ch h2{font-size:.95rem;font-weight:700;color:var(--azul)}
#xc{background:none;border:none;font-size:1.3rem;cursor:pointer;color:#888;padding:4px}
#ci{overflow-y:auto;flex:1;padding:0 14px}
.ci{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid #f0f0f0}
.ci-im{width:48px;height:48px;border-radius:8px;overflow:hidden;flex-shrink:0;background:#f5f5f5;display:flex;align-items:center;justify-content:center}
.ci-im img{width:100%;height:100%;object-fit:cover}
.ci-info{flex:1;min-width:0}
.ci-n{font-size:.82rem;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ci-pr{font-size:.72rem;color:#777}
.ci-sub{font-size:.82rem;color:var(--azul);font-weight:700;margin-top:2px}
.ci-q{display:flex;align-items:center;gap:6px;flex-shrink:0}
.ci-q button{width:26px;height:26px;border-radius:50%;border:1.5px solid var(--verde);background:#fff;color:var(--verde);font-size:1rem;font-weight:700;cursor:pointer}
.ci-q span{min-width:18px;text-align:center;font-weight:700;font-size:.88rem}
#cf{padding:12px 16px 20px;border-top:1px solid var(--borde)}
.tr{display:flex;justify-content:space-between;font-size:.83rem;color:#666;margin-bottom:6px}
.tr.grat span:last-child{color:var(--verde);font-weight:700}
#tf{display:flex;justify-content:space-between;font-size:1rem;font-weight:700;color:var(--azul);margin:8px 0 14px;padding-top:8px;border-top:1px solid var(--borde)}
#ok{width:100%;padding:14px;background:linear-gradient(135deg,var(--azul),var(--verde));color:#fff;border:none;border-radius:12px;font-size:1rem;font-weight:700;cursor:pointer}
#ok:disabled{opacity:.5;cursor:not-allowed}
#vacio{text-align:center;padding:40px 0;color:#bbb}
#ex{display:none;position:fixed;inset:0;background:#fff;z-index:300;flex-direction:column;align-items:center;justify-content:center;gap:14px;padding:28px;text-align:center}
#ex.on{display:flex}
#ex .ic{font-size:4rem}
#ex h2{color:var(--azul);font-size:1.4rem;font-weight:800}
#ex p{color:#555;font-size:.88rem;max-width:280px;line-height:1.5}
#ex a{display:block;margin-top:6px;background:linear-gradient(135deg,var(--azul),var(--verde));color:#fff;text-decoration:none;padding:14px 32px;border-radius:12px;font-size:1rem;font-weight:700}
#ex .sub{font-size:.78rem;color:#bbb;margin-top:4px}
#toast{position:fixed;bottom:90px;left:50%;transform:translateX(-50%);background:rgba(26,26,26,.88);color:#fff;padding:9px 20px;border-radius:24px;font-size:.83rem;opacity:0;transition:opacity .25s;pointer-events:none;white-space:nowrap;z-index:400}
#toast.on{opacity:1}
</style>
</head>
<body>
<header>
  <div class="logo-wrap">LOGO_AQUI</div>
  <h1>Equora Distribuciones<small>Productos Biotú 🌿</small></h1>
  <button id="btn-c" onclick="abrirC()" aria-label="Carrito">🛒<span id="bdg"></span></button>
</header>
<div id="banner">🎁 Envío GRATIS en pedidos desde $60.000</div>
<div id="filtros"></div>
<div id="grid"></div>
<div id="ov" onclick="cerrarC()"></div>
<div id="cp">
  <div id="ch"><h2>🛒 Tu pedido</h2><button id="xc" onclick="cerrarC()">✕</button></div>
  <div id="ci"><div id="vacio"><p style="font-size:1.5rem">🛒</p><p>Tu carrito está vacío</p></div></div>
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
  <p>Ingresa tu dirección de entrega en el siguiente paso.<br>El pago es <strong>contra entrega</strong>.</p>
  <a id="lnk" href="#" target="_blank">Completar pedido →</a>
  <p class="sub">Puedes cerrar esta ventana y volver a WhatsApp</p>
</div>
<div id="toast"></div>
<script>
var ENVIO=7000,MIN_G=60000;
var productos=CATALOGO_AQUI;
var carrito={};
var catAct='Todos';
var tel=new URLSearchParams(location.search).get('tel')||'';

function fmt(n){return '$'+Number(n).toLocaleString('es-CO');}
function he(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function clave(p){return p.producto+'||'+p.presentacion;}

// FILTROS
var ORDEN_CATS=['Todos','Lavanderia','Cocina','Hogar','Talleres / Industrial','Higiene Personal','Otros'];
function renderFiltros(){
  var disp=new Set(productos.map(function(p){return p.categoria;}));
  var cats=ORDEN_CATS.filter(function(c){return c==='Todos'||disp.has(c);});
  var h='';
  for(var i=0;i<cats.length;i++){
    var c=cats[i];
    h+='<button class="fb'+(c===catAct?' on':'')+'" onclick="filtrar(this,\''+c.replace(/'/g,"\\'")+'\')">'
      +he(c)+'</button>';
  }
  document.getElementById('filtros').innerHTML=h;
}

function filtrar(btn,cat){
  catAct=cat;
  var bts=document.querySelectorAll('.fb');
  for(var i=0;i<bts.length;i++) bts[i].classList.remove('on');
  btn.classList.add('on');
  renderGrid();
}

// GRID
function renderGrid(){
  var lista=catAct==='Todos'?productos:productos.filter(function(p){return p.categoria===catAct;});
  if(!lista.length){document.getElementById('grid').innerHTML='<p style="color:#bbb;text-align:center;padding:40px;grid-column:1/-1">Sin productos</p>';return;}
  var h='';
  for(var i=0;i<lista.length;i++){
    var p=lista[i];
    var k=clave(p);
    var qty=(carrito[k]&&carrito[k].qty)||0;
    var st=typeof p.stock==='number'?p.stock:9999;
    var im=p.imagen?'<img src="'+he(p.imagen)+'" loading="lazy" onerror="this.parentElement.innerHTML=\'<span class=&quot;no-img&quot;>🧴</span>\'">':'<span class="no-img">🧴</span>';
    var acc='';
    if(st<=0){acc='<p style="text-align:center;font-size:.75rem;color:#bbb">Agotado</p>';}
    else if(qty===0){acc='<button class="ab" onclick="add(\''+esc(k)+'\')">+ Agregar</button>';}
    else{acc='<div class="qc"><button class="qb" onclick="dec(\''+esc(k)+'\')">&#8722;</button><span class="qn">'+qty+'</span><button class="qb" onclick="inc(\''+esc(k)+'\','+st+')">+</button></div>';}
    h+='<div class="card"><div class="img-w">'+im+'</div><div class="cb"><div class="cn">'+he(p.producto)+'</div><div class="cp">'+he(p.presentacion)+'</div><div class="cpr">'+fmt(p.precio)+'</div>'+acc+'</div></div>';
  }
  document.getElementById('grid').innerHTML=h;
}

function esc(s){return s.replace(/\\/g,'\\\\').replace(/'/g,'\\x27');}
function buscar(k){var a=k.split('||');return productos.filter(function(p){return p.producto===a[0]&&p.presentacion===a[1];})[0]||null;}

// CARRITO
function add(k){
  var p=buscar(k);if(!p)return;
  var st=typeof p.stock==='number'?p.stock:9999;
  carrito[k]={info:p,qty:1,stock:st};
  ui();toast('Agregado 🌿');
}
function inc(k,st){if(carrito[k]){if(carrito[k].qty<st){carrito[k].qty++;ui();}else toast('Stock máximo');}}
function dec(k){if(carrito[k]){carrito[k].qty--;if(carrito[k].qty<=0)delete carrito[k];ui();}}

function ui(){
  var items=Object.keys(carrito);
  var tot=0;for(var i=0;i<items.length;i++)tot+=carrito[items[i]].qty;
  var b=document.getElementById('bdg');
  if(tot>0){b.style.display='flex';b.textContent=tot;}else b.style.display='none';
  renderGrid();
  renderCarrito();
}

function renderCarrito(){
  var items=Object.keys(carrito);
  var ci=document.getElementById('ci');
  var cf=document.getElementById('cf');
  var ok=document.getElementById('ok');
  if(!items.length){ci.innerHTML='<div id="vacio"><p style="font-size:1.5rem">🛒</p><p>Tu carrito está vacío</p></div>';cf.style.display='none';return;}
  cf.style.display='block';
  var sub=0,h='';
  for(var i=0;i<items.length;i++){
    var k=items[i];var v=carrito[k];var s=v.info.precio*v.qty;sub+=s;
    var im=v.info.imagen?'<img src="'+he(v.info.imagen)+'" alt="">':'<span style="font-size:1.2rem">🧴</span>';
    h+='<div class="ci"><div class="ci-im">'+im+'</div><div class="ci-info"><div class="ci-n">'+he(v.info.producto)+'</div><div class="ci-pr">'+he(v.info.presentacion)+'</div><div class="ci-sub">'+fmt(s)+'</div></div><div class="ci-q"><button onclick="dec(\''+esc(k)+'\')">&#8722;</button><span>'+v.qty+'</span><button onclick="inc(\''+esc(k)+'\','+v.stock+')">+</button></div></div>';
  }
  ci.innerHTML=h;
  var env=sub>=MIN_G?0:ENVIO;
  document.getElementById('sv').textContent=fmt(sub);
  document.getElementById('ev').textContent=env===0?'¡Gratis! 🎉':fmt(env);
  document.getElementById('el').textContent=sub>=MIN_G?'Envío (gratis ≥$60.000)':'Envío (gratis desde $60.000)';
  document.getElementById('er').className='tr'+(env===0?' grat':'');
  document.getElementById('tv').textContent=fmt(sub+env);
  ok.disabled=false;
}

function abrirC(){renderCarrito();document.getElementById('ov').classList.add('on');document.getElementById('cp').classList.add('on');}
function cerrarC(){document.getElementById('ov').classList.remove('on');document.getElementById('cp').classList.remove('on');}

// CONFIRMAR
function confirmar(){
  var ok=document.getElementById('ok');
  ok.disabled=true;ok.textContent='Procesando…';
  var items=Object.keys(carrito).map(function(k){var v=carrito[k];return{producto:v.info.producto,presentacion:v.info.presentacion,cantidad:v.qty,precio_unitario:v.info.precio,subtotal:v.info.precio*v.qty};});
  var body=JSON.stringify({telefono:tel,productos:items});
  fetch('/tienda/confirmar',{method:'POST',headers:{'Content-Type':'application/json'},body:body})
    .then(function(r){return r.json();})
    .then(function(d){
      if(d.checkout_url){
        cerrarC();
        document.getElementById('lnk').href=d.checkout_url;
        document.getElementById('ex').classList.add('on');
        window.open(d.checkout_url,'_blank');
      }else{toast('Error: '+(d.error||'intenta de nuevo'),3500);ok.disabled=false;ok.textContent='Confirmar pedido →';}
    })
    .catch(function(){toast('Error de conexión. Intenta de nuevo.',3500);ok.disabled=false;ok.textContent='Confirmar pedido →';});
}

var _tt;
function toast(m,ms){
  var el=document.getElementById('toast');el.textContent=m;el.classList.add('on');
  clearTimeout(_tt);_tt=setTimeout(function(){el.classList.remove('on');},ms||2000);
}

// INICIO
renderFiltros();
renderGrid();
</script>
</body>
</html>
"""


def obtener_tienda_html(logo_url: str = "", productos: list = None) -> str:
    """Genera el HTML de la tienda inyectando logo y catálogo directamente."""
    # Logo
    if logo_url:
        logo_tag = '<img src="' + logo_url + '" alt="Equora">'
    else:
        logo_tag = '<span class="logo-fb">💧</span>'

    # Catálogo embebido como variable JS (evita el fetch secundario)
    catalogo_js = json.dumps(productos or [], ensure_ascii=False)

    html = _HTML.replace("LOGO_AQUI", logo_tag)
    html = html.replace("CATALOGO_AQUI", catalogo_js)
    return html
