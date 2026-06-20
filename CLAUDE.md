# Voco — agente de WhatsApp con IA

Plataforma SaaS multi-tenant que automatiza atención al cliente, ventas y
seguimiento por WhatsApp usando Claude. Cliente actual: **Equora
Distribuciones** (productos de limpieza biodegradable Biotú, Colombia).

## Stack

- **Backend:** Python 3.11 + FastAPI (async), servido con Uvicorn.
- **BD:** SQLAlchemy 2.0 async — SQLite local (`agentkit.db`) / Postgres en
  producción vía `DATABASE_URL` (`asyncpg`/`aiosqlite`).
- **IA:** Anthropic SDK (`claude-haiku-4-5` por defecto, configurable con
  `AI_MODEL` env var o desde el panel) + OpenAI Whisper para transcripción de
  notas de voz.
- **WhatsApp:** Meta Cloud API (proveedor principal) o Twilio, seleccionable
  por agente (`WHATSAPP_PROVIDER`).
- **Frontend:** panel SaaS HTML/CSS/JS embebido directamente en
  `agent/inbox.py` (no es un proyecto frontend separado).
- **Deploy:** Docker + Railway (`railway.json`, healthcheck en `/health`).

## Estructura

```
agent/
  main.py          # rutas FastAPI: webhooks, auth, API del panel (~90 endpoints bajo /inbox/api/*)
  brain.py         # arma el system prompt y llama a Claude (generar_respuesta)
  inbox.py         # panel SaaS embebido (dashboard, chats, config, métricas)
  memory.py        # ORM — clientes, mensajes, carrito, tickets, config editable
  transcriber.py   # baja audio de Meta y lo transcribe con Whisper (falla silenciosa)
  tools.py         # herramientas del agente: catálogo Shopify, costo de envío
  markers.py       # sintaxis [[TIENDA:]], [[PRODUCTO:x]], [[ESCALAR:]] etc.
  capi.py          # Meta Conversions API (tracking de eventos)
  mensajes.py      # plantillas de mensajes
  shopify_admin.py # administración de catálogo Shopify
  providers/
    meta.py        # Meta WhatsApp Cloud API (webhooks, envío, descarga de media)
    twilio.py       # Twilio como proveedor alternativo
    base.py
config/
  prompts.yaml     # system prompt base de Andrea (fallback si no hay override en BD)
  business.yaml     # metadata del negocio (Equora)
tests/
  test_local.py
knowledge/          # archivos privados del negocio (gitignored, no versionar)
```

El system prompt real que ve el agente sigue esta prioridad: **valor en BD
(`SYSTEM_PROMPT`, editable desde el panel) → `config/prompts.yaml`**. No
asumas que editar el YAML cambia el comportamiento en producción si ya hay un
override guardado en BD.

## Multi-tenant

Cada agente (tenant) tiene su propio proveedor de WhatsApp, prompt, módulos
activos y configuración — todo resuelto por `agent_id`, normalmente derivado
del `phone_number_id` entrante en el webhook. Al tocar lógica de
carrito/seguimientos/notificaciones, evitar asumir un único provider o agente
global (bug recurrente, ver historial de commits `fix(multi-tenant)` /
`fix(carrito)`).

## Correr en local

```bash
pip install -r requirements.txt
# completar .env (ver variables abajo)
uvicorn agent.main:app --reload --port 8000
# o con Docker:
docker compose up
```

### Variables de entorno (`.env`)

| Variable | Uso |
|---|---|
| `ANTHROPIC_API_KEY` | requerida — Claude |
| `OPENAI_API_KEY` | transcripción de voz (Whisper); si falta, las notas de voz se ignoran silenciosamente |
| `DATABASE_URL` | Postgres en producción; si no está, usa SQLite local |
| `WHATSAPP_PROVIDER` | `meta` o `twilio` |
| `META_CAPI_TOKEN`, `META_PIXEL_ID` | Meta Conversions API |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` | si se usa Twilio |
| `AI_MODEL` | override del modelo Claude (default `claude-haiku-4-5`) |
| `AI_CLIENT_MAX_AGE_SEG` | recicla el cliente Anthropic/OpenAI cada N seg (default 6h) para evitar conexiones stale en Railway |
| `PORT`, `ENVIRONMENT` | infraestructura |

`knowledge/` y `*.db` están en `.gitignore` — no son parte del repo, son
estado local/privado del negocio.

## Convenciones notadas en el código

- Los clientes async (Anthropic, OpenAI) se recrean periódicamente
  (`_get_client()` / `_cliente_openai()`) para evitar pools de conexión
  stale en contenedores de larga duración (ver comentarios `#78` en
  `brain.py` / `transcriber.py`).
- El carrito en BD es la fuente de verdad única — no reconstruir su estado
  desde el historial de chat.
- Carritos originados en el catálogo nativo de WhatsApp (`retailer_id`) y
  carritos web no se comunican entre sí; el prompt se lo advierte
  explícitamente a Claude para no mezclar flujos.
