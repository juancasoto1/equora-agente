# Voco

Agente de WhatsApp impulsado por IA (Claude) para atención al cliente y
ventas. Multi-tenant: cada negocio configura su propio agente, prompt,
catálogo y proveedor de WhatsApp desde un panel propio.

Cliente actual: **Equora Distribuciones** (Biotú — limpieza biodegradable,
Colombia).

## Qué hace

- Responde consultas de clientes por WhatsApp usando Claude.
- Muestra catálogo y arma carritos de compra (integración Shopify).
- Genera links de checkout y hace seguimiento de pedidos/carritos abandonados.
- Transcribe notas de voz (OpenAI Whisper).
- Escala conversaciones a un agente humano cuando hace falta.
- Corre campañas de difusión y registra opt-outs.
- Incluye un panel de administración (`/inbox`) con dashboard de
  conversaciones, clientes, configuración y métricas.

## Setup local

Requisitos: Python 3.11+.

```bash
pip install -r requirements.txt
# crear .env en la raíz con las variables de abajo (no hay .env.example)
uvicorn agent.main:app --reload --port 8000
```

O con Docker:

```bash
docker compose up
```

El servidor queda en `http://localhost:8000`. Panel de administración en
`/inbox`. Healthcheck en `/health`.

### Variables de entorno mínimas

```
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
WHATSAPP_PROVIDER=meta   # o twilio
DATABASE_URL=             # opcional, default SQLite local
```

Ver [CLAUDE.md](CLAUDE.md) para la lista completa de variables y detalle de
la arquitectura interna.

## Estructura del proyecto

```
agent/        # backend FastAPI: webhooks, panel, lógica del agente
config/       # prompt base y metadata del negocio
tests/        # tests
knowledge/    # archivos privados del negocio (no versionado)
```

## Documentación

- [CLAUDE.md](CLAUDE.md) — arquitectura, convenciones y guía para trabajar en el código.
- [AUDITORIA_UI_VOCO.md](AUDITORIA_UI_VOCO.md) — auditoría de UI/UX del panel, con hallazgos pendientes.

## Deploy

Producción en [Railway](https://railway.app) vía `Dockerfile` y
`railway.json` (build con Docker, healthcheck en `/health`, reinicio
automático ante fallos).
