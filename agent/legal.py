"""Páginas legales públicas de Voco (política de privacidad y términos).

Se sirven en /privacy y /terms desde el mismo backend FastAPI (myvoco.ai),
sin necesidad de un sitio web aparte. Requisito de Meta App Review para el
registro como proveedor de tecnología (Tech Provider).

Nota: revisar CONTACTO_EMAIL y RAZON_SOCIAL antes de publicar en producción.
"""

CONTACTO_EMAIL = "soporte@myvoco.ai"
RAZON_SOCIAL = "Juan Carlos Soto López"   # empresa unipersonal; marca comercial: Voco
ULTIMA_ACTUALIZACION = "1 de julio de 2026"

_BASE_CSS = """
:root{color-scheme:light}
*{box-sizing:border-box}
body{margin:0;background:#f6f7f9;color:#1f2430;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  line-height:1.65;-webkit-font-smoothing:antialiased}
.wrap{max-width:760px;margin:0 auto;padding:48px 24px 96px}
.brand{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.brand-dot{width:26px;height:26px;border-radius:7px;background:#16a34a;flex-shrink:0}
.brand-name{font-weight:700;font-size:1.15rem;letter-spacing:-.01em}
h1{font-size:1.9rem;line-height:1.2;margin:24px 0 4px;letter-spacing:-.02em}
.updated{color:#6b7280;font-size:.9rem;margin-bottom:32px}
h2{font-size:1.2rem;margin:36px 0 10px;letter-spacing:-.01em}
p,li{font-size:1rem;color:#374151}
ul{padding-left:22px}
li{margin:6px 0}
a{color:#16a34a;text-decoration:none}
a:hover{text-decoration:underline}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:8px 28px 28px;
  box-shadow:0 1px 2px rgba(0,0,0,.04)}
footer{margin-top:40px;color:#9ca3af;font-size:.85rem;text-align:center}
"""


def _pagina(titulo: str, cuerpo_html: str) -> str:
    return f"""<!doctype html>
<html lang="es"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="index,follow">
<title>{titulo} · Voco</title>
<style>{_BASE_CSS}</style>
</head><body>
<div class="wrap">
  <div class="brand"><div class="brand-dot"></div><div class="brand-name">Voco</div></div>
  <div class="card">
    {cuerpo_html}
    <footer>© 2026 {RAZON_SOCIAL} · <a href="https://myvoco.ai">myvoco.ai</a></footer>
  </div>
</div>
</body></html>"""


def politica_privacidad_html() -> str:
    cuerpo = f"""
<h1>Política de Privacidad</h1>
<p class="updated">Última actualización: {ULTIMA_ACTUALIZACION}</p>

<p>Voco (operado por {RAZON_SOCIAL}, en adelante «Voco», «nosotros») es una
plataforma que automatiza la atención al cliente por WhatsApp con inteligencia
artificial, en nombre de negocios que contratan nuestro servicio (nuestros
«Clientes»). Esta política explica qué datos tratamos, con qué fin y cómo los
protegemos.</p>

<h2>1. Nuestro rol frente a tus datos</h2>
<p>Cuando escribes por WhatsApp a un negocio que usa Voco, ese negocio es el
<strong>responsable</strong> de tus datos y Voco actúa como
<strong>encargado del tratamiento</strong>: procesamos la información
únicamente para prestarle el servicio a ese negocio, según sus instrucciones.</p>

<h2>2. Qué información tratamos</h2>
<ul>
  <li><strong>Número de teléfono de WhatsApp</strong> y nombre de perfil.</li>
  <li><strong>Contenido de los mensajes</strong> que envías (texto, notas de
      voz, imágenes y selecciones de botones o catálogo).</li>
  <li><strong>Datos de pedido y carrito</strong> (productos, cantidades,
      dirección de envío) cuando compras a través del chat.</li>
  <li><strong>Metadatos técnicos</strong> necesarios para la entrega de
      mensajes (identificadores de conversación, marcas de tiempo).</li>
</ul>

<h2>3. Para qué usamos la información</h2>
<ul>
  <li>Responder tus consultas y gestionar tus pedidos de forma automatizada.</li>
  <li>Transcribir notas de voz para poder entender tu solicitud.</li>
  <li>Dar seguimiento a carritos y pedidos, y coordinar el envío.</li>
  <li>Mejorar la calidad de las respuestas del asistente.</li>
</ul>
<p>No vendemos tus datos ni los usamos para publicidad de terceros.</p>

<h2>4. Proveedores que nos ayudan (encargados)</h2>
<p>Para operar el servicio compartimos lo estrictamente necesario con:</p>
<ul>
  <li><strong>Meta Platforms</strong> — WhatsApp Business Platform (envío y
      recepción de mensajes).</li>
  <li><strong>Anthropic</strong> — generación de las respuestas del asistente
      (modelos Claude).</li>
  <li><strong>OpenAI</strong> — transcripción de notas de voz.</li>
  <li><strong>Shopify</strong> — catálogo y checkout, cuando aplica.</li>
  <li><strong>HubSpot</strong> — gestión de la relación con el cliente, cuando
      el negocio lo tenga activo.</li>
  <li><strong>Proveedores de infraestructura en la nube</strong> — alojamiento
      seguro de la aplicación y la base de datos.</li>
</ul>

<h2>5. Conservación</h2>
<p>Conservamos los mensajes y datos de pedido mientras el negocio mantenga
activo su servicio con Voco y por el tiempo que exija la ley aplicable. Cuando
dejan de ser necesarios, se eliminan o anonimizan.</p>

<h2>6. Tus derechos</h2>
<p>Puedes solicitar acceso, rectificación o eliminación de tus datos, así como
darte de baja de los mensajes de difusión respondiendo <em>«BAJA»</em> en el
chat. Para ejercer estos derechos, escríbenos a
<a href="mailto:{CONTACTO_EMAIL}">{CONTACTO_EMAIL}</a> o contacta directamente
al negocio con el que conversaste.</p>

<h2>7. Seguridad</h2>
<p>Aplicamos medidas técnicas y organizativas razonables (cifrado en tránsito,
control de acceso) para proteger tu información contra accesos no autorizados.</p>

<h2>8. Menores</h2>
<p>El servicio está dirigido a personas mayores de edad. No recopilamos
conscientemente datos de menores.</p>

<h2>9. Cambios</h2>
<p>Podemos actualizar esta política. Publicaremos la versión vigente en esta
misma página con su fecha de actualización.</p>

<h2>10. Contacto</h2>
<p>{RAZON_SOCIAL} — <a href="mailto:{CONTACTO_EMAIL}">{CONTACTO_EMAIL}</a> —
<a href="https://myvoco.ai">myvoco.ai</a></p>
"""
    return _pagina("Política de Privacidad", cuerpo)


def terminos_html() -> str:
    cuerpo = f"""
<h1>Términos del Servicio</h1>
<p class="updated">Última actualización: {ULTIMA_ACTUALIZACION}</p>

<p>Estos términos regulan el uso de la plataforma Voco, operada por
{RAZON_SOCIAL}. Al contratar o utilizar el servicio, aceptas lo siguiente.</p>

<h2>1. Descripción del servicio</h2>
<p>Voco provee un asistente automatizado de WhatsApp con inteligencia
artificial para atención al cliente, ventas y seguimiento, que los negocios
integran con su propia cuenta de WhatsApp Business.</p>

<h2>2. Uso aceptable</h2>
<ul>
  <li>No usar el servicio para enviar spam, contenido ilegal, fraudulento o
      que viole las políticas de WhatsApp y Meta.</li>
  <li>No intentar vulnerar la seguridad ni el funcionamiento de la plataforma.</li>
  <li>Cumplir la normativa de protección de datos aplicable respecto de los
      usuarios finales.</li>
</ul>

<h2>3. Responsabilidades del negocio Cliente</h2>
<p>El negocio es responsable del contenido de su cuenta, de contar con base
legal para contactar a sus clientes y de la exactitud de su catálogo y
precios. Voco actúa como herramienta y encargado del tratamiento.</p>

<h2>4. Disponibilidad</h2>
<p>Trabajamos para mantener el servicio disponible, pero puede haber
interrupciones por mantenimiento o por dependencias de terceros (por ejemplo,
la disponibilidad de WhatsApp).</p>

<h2>5. Limitación de responsabilidad</h2>
<p>El servicio se presta «tal cual». En la medida permitida por la ley, Voco no
será responsable por daños indirectos o lucro cesante derivados del uso o la
imposibilidad de uso del servicio.</p>

<h2>6. Cambios</h2>
<p>Podemos modificar estos términos; la versión vigente se publicará en esta
página con su fecha de actualización.</p>

<h2>7. Contacto</h2>
<p>{RAZON_SOCIAL} — <a href="mailto:{CONTACTO_EMAIL}">{CONTACTO_EMAIL}</a> —
<a href="https://myvoco.ai">myvoco.ai</a></p>
"""
    return _pagina("Términos del Servicio", cuerpo)
