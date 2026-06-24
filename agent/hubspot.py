# agent/hubspot.py — Sync Voco → HubSpot CRM (Pipeline Fase 3, ver BACKLOG.md)
#
# Direccionalidad: Voco → HubSpot ÚNICAMENTE. Voco es la fuente de verdad;
# HubSpot es el espejo/reporte para el equipo de ventas. Sin resolución de
# conflictos bidireccional — si alguien edita el deal en HubSpot, Voco lo
# sobreescribe en la próxima sincronización.
#
# Auth: Private App Token (HubSpot > Integraciones > Aplicaciones privadas).
# Scopes mínimos: crm.objects.contacts.read/write, crm.objects.deals.read/write,
# crm.associations.deals.read/write.
#
# Los IDs de HubSpot se guardan en Deal.hs_deal_id para evitar crear duplicados
# en syncs posteriores. El contact_id se re-busca por teléfono cada vez (búsqueda
# barata, evita agregar columna a Cliente).

from __future__ import annotations

import logging
from typing import Any

import httpx

from agent.memory import obtener_integration_config

logger = logging.getLogger("agentkit")

API_BASE = "https://api.hubapi.com"

# Mapeo heurístico Voco stage → HubSpot default Sales Pipeline stage IDs.
_STAGE_MAP: list[tuple[list[str], str]] = [
    (["ganado", "won", "exitoso", "compra confirmada", "cerrado ganado"], "closedwon"),
    (["perdido", "lost", "cancelado", "rechazado", "cerrado perdido"],    "closedlost"),
    (["negoci", "cotizac", "propuesta", "contract"],                      "contractsent"),
    (["interesado", "calificado", "qualified", "contactado"],             "qualifiedtobuy"),
    (["contac", "inicial", "nuevo", "lead"],                              "appointmentscheduled"),
]


def _mapear_stage(nombre: str) -> str:
    lower = nombre.lower()
    for keywords, hs_stage in _STAGE_MAP:
        if any(k in lower for k in keywords):
            return hs_stage
    return "presentationscheduled"


async def _token(agent_id: int) -> str | None:
    cfg = await obtener_integration_config(agent_id, "hubspot")
    if not cfg or not cfg.get("api_token"):
        return None
    return cfg["api_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def obtener_portal_info(agent_id: int) -> dict[str, Any]:
    """GET /account-info/v3/details — valida el token y devuelve info del portal."""
    token = await _token(agent_id)
    if not token:
        return {"ok": False, "error": "HubSpot no está conectado para este agente"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{API_BASE}/account-info/v3/details", headers=_headers(token))
        if r.status_code == 401:
            return {"ok": False, "error": "Token de HubSpot inválido o vencido"}
        if r.status_code != 200:
            logger.error(f"[hubspot] /account-info {r.status_code}: {r.text[:200]}")
            return {"ok": False, "error": f"Error de HubSpot ({r.status_code})"}
        data = r.json()
        return {
            "ok":       True,
            "portal_id": data.get("portalId", ""),
            "timezone":  data.get("timeZone", ""),
            "currency":  data.get("companyCurrency", ""),
        }
    except Exception as e:
        logger.error(f"[hubspot] Error en obtener_portal_info: {e}")
        return {"ok": False, "error": "Error de red consultando HubSpot"}


async def _buscar_contacto_por_telefono(token: str, telefono: str) -> str | None:
    """Busca un contacto en HubSpot por número de teléfono. Retorna su ID o None."""
    body = {
        "filterGroups": [{"filters": [{"propertyName": "phone", "operator": "EQ", "value": telefono}]}],
        "properties": ["phone"],
        "limit": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{API_BASE}/crm/v3/objects/contacts/search",
                headers=_headers(token), json=body,
            )
        if r.status_code == 200 and r.json().get("total", 0) > 0:
            return r.json()["results"][0]["id"]
    except Exception as e:
        logger.warning(f"[hubspot] Error buscando contacto por teléfono: {e}")
    return None


async def upsert_contacto(
    agent_id: int, telefono: str, nombre: str = "", email: str = ""
) -> dict[str, Any]:
    """Crea o actualiza un contacto en HubSpot buscando primero por teléfono."""
    token = await _token(agent_id)
    if not token:
        return {"ok": False, "error": "HubSpot no conectado"}

    partes    = nombre.strip().split(" ", 1)
    firstname = partes[0] if partes else nombre
    lastname  = partes[1] if len(partes) > 1 else ""

    props: dict[str, str] = {"phone": telefono}
    if firstname: props["firstname"] = firstname
    if lastname:  props["lastname"]  = lastname
    if email:     props["email"]     = email

    hs_id = await _buscar_contacto_por_telefono(token, telefono)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if hs_id:
                r = await client.patch(
                    f"{API_BASE}/crm/v3/objects/contacts/{hs_id}",
                    headers=_headers(token), json={"properties": props},
                )
            else:
                r = await client.post(
                    f"{API_BASE}/crm/v3/objects/contacts",
                    headers=_headers(token), json={"properties": props},
                )
        if r.status_code in (200, 201):
            return {"ok": True, "hs_id": r.json().get("id", hs_id or ""), "created": not bool(hs_id)}
        logger.error(f"[hubspot] upsert_contacto {r.status_code}: {r.text[:300]}")
        return {"ok": False, "error": f"Error HubSpot ({r.status_code})"}
    except Exception as e:
        logger.error(f"[hubspot] Error en upsert_contacto: {e}")
        return {"ok": False, "error": "Error de red en HubSpot"}


async def upsert_deal(
    agent_id: int,
    hs_contact_id: str,
    deal: dict,
    existing_hs_deal_id: str = "",
) -> dict[str, Any]:
    """Crea o actualiza un deal en HubSpot y lo asocia con el contacto."""
    token = await _token(agent_id)
    if not token:
        return {"ok": False, "error": "HubSpot no conectado"}

    props: dict[str, Any] = {
        "dealname":   deal.get("titulo") or f"Lead {deal.get('cliente_telefono', '')}",
        "dealstage":  _mapear_stage(deal.get("stage", "")),
        "pipeline":   "default",
        "description": f"Stage en Voco: {deal.get('stage', '')}",
    }
    if deal.get("valor_cop"):
        props["amount"] = str(deal["valor_cop"])

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if existing_hs_deal_id:
                r = await client.patch(
                    f"{API_BASE}/crm/v3/objects/deals/{existing_hs_deal_id}",
                    headers=_headers(token), json={"properties": props},
                )
            else:
                r = await client.post(
                    f"{API_BASE}/crm/v3/objects/deals",
                    headers=_headers(token), json={"properties": props},
                )

            if r.status_code not in (200, 201):
                logger.error(f"[hubspot] upsert_deal {r.status_code}: {r.text[:300]}")
                return {"ok": False, "error": f"Error HubSpot ({r.status_code})"}

            hs_deal_id = r.json().get("id", existing_hs_deal_id)

            # Asociar deal con contacto (v4, idempotente)
            if hs_contact_id and hs_deal_id:
                await client.put(
                    f"{API_BASE}/crm/v4/objects/deals/{hs_deal_id}"
                    f"/associations/default/contacts/{hs_contact_id}",
                    headers=_headers(token),
                )

        return {"ok": True, "hs_deal_id": hs_deal_id, "created": not bool(existing_hs_deal_id)}
    except Exception as e:
        logger.error(f"[hubspot] Error en upsert_deal: {e}")
        return {"ok": False, "error": "Error de red en HubSpot"}


async def sincronizar_deal(agent_id: int, deal: dict, cliente: dict) -> dict[str, Any]:
    """Orquesta: upsert_contacto → upsert_deal → retorna IDs de HubSpot."""
    token = await _token(agent_id)
    if not token:
        return {"ok": False, "error": "HubSpot no conectado"}

    telefono = deal.get("cliente_telefono", "")
    nombre   = deal.get("cliente_nombre") or " ".join(filter(None, [
        cliente.get("nombres", ""), cliente.get("apellidos", ""),
    ])).strip()
    email    = deal.get("cliente_email") or cliente.get("email", "")

    r_contacto = await upsert_contacto(agent_id, telefono, nombre, email)
    if not r_contacto.get("ok"):
        return r_contacto

    r_deal = await upsert_deal(
        agent_id, r_contacto["hs_id"], deal, deal.get("hs_deal_id", "")
    )
    if not r_deal.get("ok"):
        return r_deal

    return {
        "ok":            True,
        "hs_deal_id":    r_deal["hs_deal_id"],
        "hs_contact_id": r_contacto["hs_id"],
    }


async def sincronizar_deal_bg(agent_id: int, deal_id: int, telefono: str) -> None:
    """Background task lanzado con asyncio.create_task() desde markers.py.
    No bloquea el webhook — los errores se loguean y no se propagan.
    """
    try:
        from agent.memory import obtener_deal_por_id, obtener_cliente, set_hs_deal_id
        deal = await obtener_deal_por_id(deal_id)
        if not deal:
            return
        cliente = await obtener_cliente(telefono, agent_id=agent_id) or {}
        resultado = await sincronizar_deal(agent_id, deal, cliente)
        if resultado.get("ok"):
            await set_hs_deal_id(deal_id, resultado["hs_deal_id"])
            logger.info(
                f"[hubspot] Deal {deal_id} sincronizado → hs_deal={resultado['hs_deal_id']}"
            )
        else:
            logger.warning(
                f"[hubspot] Sync deal {deal_id} fallido: {resultado.get('error')}"
            )
    except Exception as e:
        logger.error(f"[hubspot] Error en sincronizar_deal_bg(deal_id={deal_id}): {e}")
