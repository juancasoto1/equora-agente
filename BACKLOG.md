# Backlog — Voco

Documento vivo. Se actualiza en cada sesión para no perder el historial si la
conversación con Claude se reinicia. Cada item tiene estado, lo que ya existe
en el código (evita reconstruir lo que ya está hecho) y lo que falta.

Convención de estado: `🟡 pendiente` · `🔵 en progreso` · `✅ hecho` · `⛔ bloqueado`

---

## 1. 🟡 Bandeja unificada multi-canal (Instagram, Facebook, LinkedIn, TikTok)

Agrupar en una sola bandeja de Conversaciones (y en Escalaciones) los mensajes
de WhatsApp + redes sociales, como en la referencia que compartió Juan
(panel con ícono de red social superpuesto al avatar del cliente).

**Estado actual del código:** nada construido.
- Providers hoy: solo `agent/providers/meta.py` (WhatsApp Cloud API) y
  `agent/providers/twilio.py`. No hay provider de Instagram/Messenger/LinkedIn/TikTok.
- `Mensaje`, `Cliente`, `EstadoConversacion` (`agent/memory.py`) no tienen
  campo de canal/plataforma. Solo la tabla `Deal` del Pipeline ya previó un
  campo `source` (whatsapp|instagram|messenger|manual) — pensado para esto,
  pero no conectado a nada todavía.
- El panel de Conversaciones (`agent/inbox.py`) está diseñado 100% alrededor
  de "un teléfono = un cliente de WhatsApp".

**⚠️ Restricción técnica real (no es solo "más trabajo"):**
- **Instagram DM y Facebook Messenger** corren sobre la misma Meta Graph API
  que ya usamos para WhatsApp — reutilizable en buena parte (mismo patrón de
  provider, webhooks, tokens).
- **LinkedIn** no ofrece una API de mensajería abierta para bots/CRM de
  terceros — solo a partners aprobados por LinkedIn caso por caso.
- **TikTok** no tiene API pública de mensajes directos para integraciones de
  este tipo.
- **Pendiente de decidir con Juan:** ¿arrancamos con Instagram + Messenger
  (viable, vía Meta) y dejamos LinkedIn/TikTok fuera de alcance (o como
  "más adelante si Meta/esas plataformas abren acceso")?

**Para construirlo (si se confirma alcance Instagram+Messenger):**
- [ ] Agregar campo `canal` a `Mensaje`, `Cliente`, `EstadoConversacion` (migración Postgres)
- [ ] Extender `agent/providers/meta.py` o crear provider nuevo para Instagram/Messenger (Meta ya permite manejar varias plataformas con el mismo Business Account)
- [ ] Webhook handler que distinga el canal de origen
- [ ] UI: ícono de plataforma superpuesto al avatar en la lista de Conversaciones y en Escalaciones (igual que la referencia)
- [ ] Filtro por canal en la bandeja

---

## 2. ✅ Carrito de compras omnichannel (agente humano arma/edita carrito desde el panel)

**Hecho y desplegado (2026-06-22, commit `32a186c`).**

**Fix post-deploy (2026-06-22):** Juan probó en producción y reportó que al
darle "Guardar" no pasaba nada visible — el carrito sí se guardaba en BD,
pero el cliente nunca se enteraba (no se le mandaba ningún mensaje). Faltaba
conectar con `_enviar_resumen_carrito()` (`agent/main.py:1100`), la misma
función que ya usa el flujo del bot para mandar el resumen + botón
"Confirmar pedido ✅" cuando el cliente arma su propio carrito. Ahora el
endpoint `POST /inbox/api/carrito/{telefono}` llama a esa función después de
guardar, así que el cliente recibe exactamente el mismo mensaje sin importar
si lo armó él o un agente humano. El frontend recarga el chat (`loadMsgs`)
para que se vea el mensaje saliente de inmediato. Si Meta rechaza el envío,
queda igual que cualquier otro mensaje fallido: triángulo rojo + motivo real
en el tooltip (ver fix del item de fecha/errores de Meta de esta misma sesión).
Probado end-to-end localmente (incluida la falla real de un token expirado).
Pendiente desplegar este fix.

Para que un agente humano pueda agregar productos al carrito de un cliente
directamente desde Conversaciones (clientes con dificultad para usar la
tecnología), y crear/editar el pedido desde Voco sin depender de que el
cliente lo arme solo por WhatsApp.

**Estado actual del código: ~80% del backend ya existe.**
- `Cliente.carrito_activo` (JSON) + `Cliente.carrito_activo_at` ya existen (`agent/memory.py`)
- Ya existen `guardar_carrito_activo()`, `obtener_carrito_activo()`, `limpiar_carrito_activo()` (`agent/memory.py`)
- Catálogo Shopify disponible vía `obtener_catalogo_shopify()` (`agent/tools.py`) y `obtener_productos_admin()` (`agent/shopify_admin.py`) — se puede reusar para el selector de productos
- **Falta:** ningún endpoint `/inbox/api/...` para que el panel lea/edite el carrito, y ninguna UI en Conversaciones para verlo/editarlo.

**Construido:**
- [x] Endpoint `GET /inbox/api/carrito/{telefono}` (`agent/main.py`) — lee el carrito activo + total
- [x] Endpoint `POST /inbox/api/carrito/{telefono}` (`agent/main.py`) — reemplaza el carrito completo con la lista que mande el panel (valida cantidad/precio, filtra items inválidos, vacía el carrito si la lista llega vacía)
- [x] Modal "🛒 Carrito del cliente" en Conversaciones (`agent/inbox.py`) — botón nuevo en el header del chat junto a llamar/WhatsApp Web. Reusa el buscador de `/inbox/api/catalogo/buscar` (mismo que ya usaba "Enviar producto del catálogo"). Cantidades +/-, quitar item, total en vivo, Guardar/Cancelar/Vaciar.
- [x] Probado end-to-end localmente (server de preview + sesión real): guardar, leer, agregar, cambiar cantidad, quitar, vaciar — todo persiste correcto en BD.
- [x] Decisión: el carrito armado por el humano usa el mismo `carrito_activo` que ya usa Andrea — mismo flujo de checkout (link Shopify), no se inventó un flujo de cierre de pedido aparte. No se setea `retailer_id` (carrito manual ≠ checkout nativo de WhatsApp, ver comentario en el endpoint).
- [ ] Pendiente: commitear y desplegar a producción (confirmar con Juan)

---

## 3. ✅ Módulo de Pipeline (kanban de oportunidades/deals)

**Hecho (2026-06-22).** Probado end-to-end localmente (servidor de preview, sesión real): crear pipeline automático con stages default, crear deal, mover de stage (con registro de actividad), heurística de `closed_at` al llegar a Ganado/Perdido, editar valor/notas, agregar nota al timeline, eliminar deal, toggle del módulo on/off. Sin desplegar todavía.

**Construido:**
- [x] Backend en `agent/memory.py`: `obtener_pipeline_activo()` (auto-crea con stages default la primera vez), `actualizar_stages_pipeline()`, `listar_deals()`, `crear_deal()`, `actualizar_deal()` (registra `DealActivity` tipo `stage_change` cuando cambia el stage, setea `closed_at` con heurística por nombre de stage — ver `_STAGES_GANADOS`/`_STAGES_PERDIDOS`), `eliminar_deal()`, `listar_actividades_deal()`, `agregar_actividad_deal()`.
- [x] Endpoints en `agent/main.py`: `GET /inbox/api/pipeline` (pipeline + deals en una sola llamada), `POST /inbox/api/pipeline/{id}/stages`, `POST /inbox/api/deals`, `PATCH /inbox/api/deals/{id}`, `DELETE /inbox/api/deals/{id}`, `GET/POST /inbox/api/deals/{id}/actividades`.
- [x] Frontend en `agent/inbox.py`: reemplazado el placeholder "Módulo en construcción" por un kanban real — columnas por stage (con conteo + valor total), tarjetas con cliente/valor/chip de canal, selector de stage por tarjeta (sin drag&drop — ver pendientes), modal "Nueva oportunidad", modal de detalle (editar valor/notas, timeline de actividad, agregar nota, eliminar).
- [x] Deals en un stage que ya no existe (tras renombrar stages) caen en una columna "Otros" aparte — no se pierden ni se reasignan solos.
- [x] Decisión: por ahora la creación de deals es manual desde el botón "+ Nueva oportunidad" en Pipeline. No se conectó un botón "Crear oportunidad" desde Conversaciones — queda como fast-follow si se necesita.

**Pendiente / fast-follows (no bloquean el lanzamiento):**
- [ ] Mover de stage hoy es con un `<select>` por tarjeta, no drag & drop — más simple de mantener pero menos "kanban clásico". Evaluar si vale la pena agregar drag&drop después.
- [ ] UI para renombrar/reordenar los stages del pipeline (el endpoint `POST /inbox/api/pipeline/{id}/stages` ya existe, falta la pantalla)

**Desplegado y activado en producción para Equora (2026-06-22).**

---

## 3b. 🟡 Pipeline → mini-CRM (visión ampliada, 2026-06-22)

Juan quiere que el Pipeline deje de ser solo CRUD manual y se convierta en algo
parecido a un CRM real. Principios que dio:

1. El pipeline es **de Voco** (la plataforma), no de "Andrea" — debe funcionar
   igual sin importar qué agente de ventas o qué canal lo alimente.
2. Debe funcionar con lo que se viene de conectar Instagram y Facebook (item #1).
3. Debe **crear el deal automáticamente y moverlo de etapa según avance la
   charla** — casi un CRM.
4. Integraciones en primera instancia: **HubSpot, Calendly y Google Calendar**
   (para crear citas).
5. Agendamiento de citas, recordatorios de citas, mensajes de seguimiento de
   negocio, y cotizaciones.

**Decisiones tomadas (2026-06-22):**
- **Orden de fases:** 1️⃣ Auto-creación/movimiento de deals por el LLM → 2️⃣ Multi-canal (Instagram/Messenger, item #1) → 3️⃣ Calendly (agendamiento) → 4️⃣ HubSpot → 5️⃣ Cotización.
  - **Por qué Fase 1 antes que multi-canal:** conectar Instagram/Messenger depende de que Meta apruebe esos productos en el Business Manager — algo fuera de nuestro control que puede tardar días. La lógica de auto-creación de deals ya queda diseñada channel-agnostic (`Deal.source` ya es genérico), así que construirla ahora sobre WhatsApp no se vuelve a hacer cuando llegue Instagram/Facebook — solo se conecta el canal nuevo a la misma lógica.
- **Calendario:** solo **Calendly**, no integración directa con Google Calendar. Calendly ya lee la disponibilidad desde el Google Calendar del negocio por debajo — resuelve lo que pedía Juan (que Voco sepa qué espacios están libres) sin construir disponibilidad propia sobre la API de Google.
- **HubSpot:** sync **un solo sentido, Voco → HubSpot** (Voco es la fuente de verdad, HubSpot es espejo/reporte). Sin resolución de conflictos bidireccional.
- **Cotización:** **PDF formal**, no mensaje de WhatsApp estructurado. Requiere un generador de PDF nuevo (librería tipo `weasyprint`/`reportlab`, agregar a `requirements.txt`).

### Estado actual del código (auditado 2026-06-22)
- ✅ Ya existe: BD de Pipeline/Deal/DealActivity, kanban manual, `IntegrationConfig` (tabla con `tipo ∈ {calendly, sendgrid, hubspot, pipedrive}` pero **cero CRUD/lógica** — solo las columnas), el loop periódico de seguimientos (`_loop_seguimientos` + watchdog en `agent/main.py`) — **reusable para recordatorios de citas, no hay que construir un loop nuevo**.
- ⛔ No existe nada de: wrappers de API para Calendly/HubSpot/Google Calendar, modelo de `Cita`/`Appointment`, generación de PDF, marcadores `[[DEAL:]]`/`[[STAGE:]]` para que el LLM cree/mueva deals.

### Fase 1 — ✅ Andrea crea/mueve deals sola (hecho 2026-06-23, sin desplegar)

**Construido:**
- [x] Marcador `[[DEAL_STAGE:Nombre exacto de la etapa]]` registrado en `agent/markers.py` (`handle_deal_stage`), siguiendo el patrón existente de `@register_marker` (igual que `[[ESCALAR:]]`/`[[PEDIDO:]]`).
- [x] Deduplicación: `obtener_deal_abierto()` (nuevo, `agent/memory.py`) busca el deal con `closed_at IS NULL` más reciente del cliente — si existe, el marcador lo actualiza; si no, crea uno nuevo. Un deal cerrado (Ganado/Perdido) no bloquea que se cree uno nuevo más adelante (probado).
- [x] `source="whatsapp"` automático al crear; si hay carrito activo, el deal nuevo arranca con `valor_cop` = total del carrito (dato gratis, no le pedimos nada extra al LLM).
- [x] Inyección dinámica en `agent/brain.py`: lista de stages reales del pipeline + la oportunidad abierta del cliente (si existe) + reglas de cuándo sí/no usar el marcador, con ejemplos positivos y negativos.
- [x] Gateado al módulo `pipeline` de `Agent.modules_json` — **ojo:** es un sistema de toggles DISTINTO al `_mod()`/`ACTIVE_MODULES` que usa el resto de `brain.py` (confirmado explícitamente con comentario en el código para no repetir la confusión). Doble gate: si el módulo está apagado, ni se inyecta el prompt ni el handler actúa aunque el LLM emita el marcador por error.
- [x] Validación fail-safe: si el LLM inventa un nombre de etapa que no existe en el pipeline, el marcador se ignora (se loguea warning) en vez de corromper el kanban.

**Calibración de prompt (importante para quien edite esto después):** la primera versión del prompt era demasiado tímida (Claude no usaba el marcador ni en confirmaciones de compra explícitas). Reforzarlo de más hizo que se disparara hasta con un simple "hola". La versión final, probada con 6+ casos reales contra la API de Claude (no mocks), distingue bien entre intención de compra real vs. saludos/preguntas genéricas — ver ejemplos positivos/negativos en el bloque de `agent/brain.py`. Si se vuelve a tocar este prompt, volver a probar con casos variados antes de confiar en el comportamiento.

**Pendiente:**
- [ ] Decidir: asignación de owner automática (round-robin, reusando el sistema de escalaciones) vs deals sin asignar hasta que un humano los reclama — quedó sin asignar (`owner_id=None`) por ahora.
- [ ] Decidir: ¿se notifica al equipo cuando un deal llega a una etapa "caliente" o se estanca? (reusar sistema de tickets/escalación) — no implementado todavía.
- [ ] Probado solo con `agent_id=1` (Equora) localmente, llamando a la API real de Claude. Falta probar en producción con conversaciones reales antes de confiar plenamente en la calibración.
- [ ] Pendiente: commitear y desplegar a producción (confirmar con Juan)

### Fase 2 — Calendly + agendamiento — 🔵 en progreso (2026-06-23)

**Decisión de arquitectura (importante, define todo lo que sigue):** Voco es SaaS — cada cliente de Voco conecta SU PROPIA cuenta de Calendly (igual que ya hacen con Shopify), no hay una cuenta maestra. Dos niveles de integración, no uno:
- **Nivel 1 — link de agendamiento:** Andrea comparte el link público de Calendly del negocio. Funciona en el plan **gratis** de Calendly, cero API.
- **Nivel 2 — agendar sin salir de WhatsApp:** Andrea muestra horarios libres y agenda directo via la Scheduling API de Calendly (`GET /event_types` → `GET /event_type_available_times` → `POST /invitees`, ver [docs](https://developer.calendly.com/schedule-events-with-ai-agents)). Requiere que ESE cliente tenga Calendly en **plan pago** (Standard+, $10/mes) + un Personal Access Token. Si no lo tiene, Voco cae de vuelta al nivel 1 sin romper nada.
- Calendly ya soporta conectar Google Calendar U Outlook/Office 365 como calendario de origen incluso en su plan gratis — un cliente de Voco no tiene que migrar de calendario, solo conectar el que ya usa a Calendly.
- Equora (Juan) no tiene Calendly pago — va a usar el trial gratis de 14 días (sin tarjeta) para darme un Personal Access Token y probar el nivel 2 de verdad antes de desplegarlo.

**Construido hoy — backend genérico (testable sin credenciales de Calendly):**
- [x] Modelo `Appointment` en `agent/memory.py` (cliente, fecha_inicio/fin, estado, origen, links de cancelar/reprogramar de Calendly, reminder_sent_at) + índices.
- [x] CRUD de `IntegrationConfig` (`obtener_integration_config`, `listar_integration_configs`, `guardar_integration_config`) — genérico por `(agent_id, tipo)`, reusable para Calendly/HubSpot/Pipedrive/SendGrid.
- [x] Endpoints en `agent/main.py`: `GET/POST /inbox/api/agents/{id}/integrations/{tipo}` y `GET .../integrations` (listar todas). El token nunca se devuelve en claro al frontend (reusa `_ofuscar_secreto`, mismo patrón que Meta/Shopify). Enviar `api_token` vacío NO borra el token ya guardado (mismo patrón que el resto de Configuración). `settings` hace merge superficial, no reemplaza el dict completo.
- [x] Probado end-to-end localmente vía HTTP directo: guardar settings sin token, agregar token real, verificar enmascarado, confirmar que blank no borra, merge de settings, tipo inválido rechazado, listar todas.

**Construido hoy — UI:**
- [x] Tarjeta "Calendly" en Configuración → Integraciones (`agent/inbox.py`), mismo patrón visual que la tarjeta de Shopify: pregunta ¿tienes cuenta? (sí/no, autoguardado), si sí pregunta plan (pago/gratis, autoguardado), si plan=pago muestra el campo de Personal Access Token (con ayuda inline de cómo generarlo en Calendly), botón "Crear cuenta en Calendly" (abre `calendly.com/signup` en pestaña nueva) si no tiene cuenta. Pill de estado + entrada en el overview de Integraciones. Probado end-to-end localmente incluyendo recarga completa de página (el estado persiste y se reconstruye bien).
- [x] Wizard de onboarding (paso 5, "Integraciones"): al activar el toggle de Calendly aparece la misma pregunta (¿ya tienes cuenta? ¿pago o gratis?) con el botón de crear cuenta. Se guarda en `IntegrationConfig` del agente recién creado al terminar el wizard. Probado end-to-end (creé un agente de prueba real vía wizard, confirmé que `settings_json` quedó con `{"tiene_cuenta": true, "plan": "gratis"}`, luego lo borré).

**Wrapper de la Scheduling API — ✅ construido y probado con credenciales reales (2026-06-23).**

Juan generó un Personal Access Token real de Calendly (scopes: `event_types:read`, `scheduled_events:read/write`, `webhooks:read/write`, `users:read`) y lo guardó vía el sistema de `IntegrationConfig`. Con eso:
- [x] `agent/calendly.py` (nuevo módulo, mismo patrón que `agent/shopify_admin.py`): `obtener_usuario()`, `obtener_event_types()`, `obtener_horarios_disponibles()`, `crear_cita()`.
- [x] El schema de `POST /invitees` (creación de cita) **no está en la doc HTML de Calendly** (su doc es una SPA) — se reconstruyó probando campo por campo contra la API real con el error de validación de cada uno, hasta tener el JSON completo: `{event_type, start_time, invitee:{email,name,timezone}, location:{kind}}`.
- [x] `obtener_usuario()`, `obtener_event_types()` y `obtener_horarios_disponibles()` probados contra la cuenta real de Juan — funcionan, devuelven datos reales (su event type "30 Minute Meeting" vía Google Meet, horarios libres reales).
- [x] `crear_cita()` probado el manejo de error (rate limit) — **no probado el camino de éxito todavía** (ver bloqueante abajo).

**⚠️ Hallazgo importante — rate limit de Calendly:** la cuenta de Juan quedó en tier `trial`, que limita `POST /invitees` a **5 requests/día** (se resetea cada 24h). Se agotó reconstruyendo el schema. Esto confirma que agendar en vivo con volumen real necesita que ESE cliente de Voco tenga Calendly en plan pago — el límite de trial/gratis no alcanza para producción. El primer test de éxito real de `crear_cita()` queda pendiente para cuando el límite se resetee.

**Pendiente:**
- [ ] Confirmar el shape de la respuesta exitosa de `POST /invitees` (200/201) — el código asume que viene envuelta en `"resource"` igual que `/users/me`, pero nunca se confirmó con una reserva real exitosa. Revisar y ajustar `crear_cita()` en la primera prueba de éxito.
- [ ] Flujo conversacional: marcador(es) para que Andrea ofrezca horarios y agende sin salir de WhatsApp — diseño de prompt pendiente (mismo tipo de calibración que costó con `[[DEAL_STAGE:]]`).
- [ ] Recordatorios: nueva función en el loop de seguimientos existente (`_loop_seguimientos` en `agent/main.py`, ya tiene watchdog — no construir un loop nuevo).
- [ ] **⚠️ Bloqueante real, separado del token:** recordatorios y seguimientos casi siempre caen fuera de la ventana de servicio de 24h de Meta (lo vivimos en esta misma sesión con el error 131047) — necesitan **plantillas (HSM) pre-aprobadas por Meta**, no texto libre. Hay que gestionar esa aprobación antes de poder mandar recordatorios reales.
- [ ] UI: sección de Citas en el panel (similar a Pipeline) para ver/gestionar citas agendadas.
- [ ] Pendiente: commitear y desplegar a producción lo ya construido (confirmar con Juan)

### Fase 3 — HubSpot
- [ ] Wrapper de API de HubSpot (crear/actualizar contacto + deal)
- [ ] Trigger de sync: ¿en cada cambio de deal, o batch periódico?

### Fase 4 — Cotización (PDF)
- [ ] Generador de PDF (elegir librería, agregar a `requirements.txt`)
- [ ] Plantilla con membrete del negocio
- [ ] Endpoint para generar + enviar la cotización por WhatsApp (como documento adjunto)

---

## 4. 🟡 Logo de agente (subir imagen JPG/PNG en vez de solo emoji+color) — despriorizado (2026-06-22)

**No es prioridad por ahora**, según Juan. Queda documentado tal cual para retomar cuando aplique.

Reemplazar/complementar el emoji+color actual con un logo real subido por el
cliente, con validación de especificaciones (formato, proporción, tamaño) en
el momento de subirlo.

**Estado actual del código: no existe nada, y hay una decisión de infraestructura pendiente.**
- `Agent` solo tiene `emoji` (string) y `color` (hex) — no hay `logo_url` ni campo similar (`agent/memory.py` ~línea 49-78)
- El wizard de onboarding (`agent/inbox.py` ~línea 11792) solo tiene selector de emoji + color picker, sin file upload
- **No existe un mecanismo de subida de archivos persistente en el proyecto.** Railway no tiene disco persistente entre deploys por defecto — cualquier imagen guardada en disco local se pierde en el próximo deploy.

**⛔ Bloqueante a decidir antes de construir:** ¿dónde se guardan las imágenes?
Opciones típicas: bucket S3-compatible (Cloudflare R2, AWS S3, Backblaze B2),
Cloudinary (más simple, con resize/validación incluida), Railway Volumes
(disco persistente con costo extra), o subirlas directo a Shopify Files API
(si Equora ya paga Shopify, podría reusarse sin costo nuevo).

**Para construirlo (una vez resuelto el storage):**
- [ ] Decidir proveedor de storage
- [ ] Campo `logo_url` en `Agent` (migración)
- [ ] Endpoint `POST /inbox/api/agents/{id}/logo` con `UploadFile`, validar formato (PNG/JPG), proporción 1:1, tamaño máx.
- [ ] UI de subida en wizard/configuración con las specs visibles (ej. "PNG o JPG, cuadrada 1:1, mínimo 256×256px, máx 2MB")
- [ ] Mostrar el logo en vez del emoji donde aparezca la identidad del agente (sidebar, "Mis agentes", header del panel)

---

## Decisiones confirmadas (2026-06-22)

- **#1 alcance:** arrancamos con Instagram + Messenger (vía Meta Graph API, reutilizando `agent/providers/meta.py`). LinkedIn y TikTok quedan fuera de alcance por ahora — revisar más adelante si esas plataformas abren una API de mensajería apta para esto.
- **#4 storage:** Cloudflare R2 (S3-compatible, sin costo de egress). Falta crear el bucket + credenciales y agregarlas a `.env`/Railway. **Item despriorizado** — no se construye por ahora.
- **Orden de trabajo (actualizado 2026-06-23):** 1️⃣ Carrito omnichannel ✅ → 2️⃣ Pipeline (kanban manual) ✅ → 3️⃣ Pipeline Fase 1 (auto-creación de deals por el LLM) ✅ sin desplegar → 4️⃣ Multi-canal (Instagram/Messenger) → 5️⃣ Calendly (agendamiento) → 6️⃣ HubSpot → 7️⃣ Cotización PDF. Logo de agente sale de la cola por ahora.

---

## Ideas / ajustes sueltos detectados en el camino

_(se va llenando en la medida que aparezcan — no necesariamente parte del backlog formal de arriba)_
