"""
agent/billing.py — Stripe billing para Voco SaaS.

Env vars requeridas:
  STRIPE_SECRET_KEY     → sk_live_... / sk_test_...
  STRIPE_WEBHOOK_SECRET → whsec_...
  STRIPE_PRICE_BASIC    → price_... ($59/mes — plan Básico)
  STRIPE_PRICE_PRO      → price_... ($149/mes — plan Pro)
  PUBLIC_URL            → https://myvoco.ai (base para redirect URLs)

Opcional:
  STRIPE_COUPON_BETA    → coupon_... (se crea automáticamente si no existe)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

logger = logging.getLogger("agentkit")


def _s():
    import stripe as _stripe
    _stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
    return _stripe


def _base() -> str:
    return os.getenv("PUBLIC_URL", "https://myvoco.ai").rstrip("/")


PRICE_IDS: dict[str, str] = {
    "basic": os.getenv("STRIPE_PRICE_BASIC", ""),
    "pro":   os.getenv("STRIPE_PRICE_PRO",   ""),
}

PLAN_LABELS = {"basic": "Básico", "pro": "Pro"}
PLAN_PRICES = {"basic": 59, "pro": 149}


# ── Checkout ──────────────────────────────────────────────────────────────────

async def crear_checkout_session(
    user_id: int,
    email: str,
    plan: str,
    promo_code: str = "",
    customer_id: str = "",
) -> str:
    """Crea una Stripe Checkout Session y retorna la URL de pago."""
    stripe = _s()
    price_id = PRICE_IDS.get(plan)
    if not price_id:
        raise ValueError(f"STRIPE_PRICE_{plan.upper()} no está configurado")

    params: dict = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": f"{_base()}/stripe/success?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url":  f"{_base()}/pricing?canceled=1",
        "metadata": {"user_id": str(user_id), "plan": plan},
        "subscription_data": {"metadata": {"user_id": str(user_id), "plan": plan}},
    }
    if customer_id:
        params["customer"] = customer_id
    else:
        params["customer_email"] = email

    if promo_code:
        try:
            promos = await asyncio.to_thread(
                stripe.PromotionCode.list, code=promo_code, limit=1
            )
            if promos.data:
                params["discounts"] = [{"promotion_code": promos.data[0].id}]
            else:
                params["allow_promotion_codes"] = True
        except Exception:
            params["allow_promotion_codes"] = True
    else:
        params["allow_promotion_codes"] = True

    session = await asyncio.to_thread(stripe.checkout.Session.create, **params)
    return session.url


# ── Customer Portal ───────────────────────────────────────────────────────────

async def crear_portal_session(customer_id: str) -> str:
    """URL del portal de Stripe para que el cliente gestione su suscripción."""
    stripe = _s()
    portal = await asyncio.to_thread(
        stripe.billing_portal.Session.create,
        customer=customer_id,
        return_url=f"{_base()}/inbox",
    )
    return portal.url


# ── Beta invite codes ─────────────────────────────────────────────────────────

async def _obtener_o_crear_cupon_beta(stripe, meses: int) -> str:
    coupon_id = os.getenv("STRIPE_COUPON_BETA", "")
    if coupon_id:
        return coupon_id
    existing = await asyncio.to_thread(stripe.Coupon.list, limit=100)
    beta = next((c for c in existing.data if "Voco Beta" in (c.name or "")), None)
    if beta:
        return beta.id
    c = await asyncio.to_thread(
        stripe.Coupon.create,
        percent_off=100,
        duration="repeating",
        duration_in_months=meses,
        name="Voco Beta",
    )
    return c.id


async def crear_invite_beta(nombre: str, meses: int = 6) -> dict:
    """Genera un Stripe Promotion Code 100% off para amigos beta.
    Retorna {code, checkout_url, expires_at, meses}."""
    stripe = _s()
    coupon_id = await _obtener_o_crear_cupon_beta(stripe, meses)

    slug = nombre.upper().replace(" ", "")[:8]
    suffix = str(int(time.time()))[-4:]
    code_str = f"BETA-{slug}-{suffix}"
    expires_ts = int(time.time()) + (meses * 30 * 24 * 3600)

    promo = await asyncio.to_thread(
        stripe.PromotionCode.create,
        coupon=coupon_id,
        code=code_str,
        max_redemptions=1,
        expires_at=expires_ts,
        metadata={"tipo": "beta_invite", "nombre": nombre, "meses": str(meses)},
    )
    return {
        "code": promo.code,
        "checkout_url": f"{_base()}/pricing?promo={promo.code}",
        "expires_at": promo.expires_at,
        "meses": meses,
    }


async def listar_invites_beta() -> list[dict]:
    """Lista los promotion codes beta (activos e inactivos)."""
    stripe = _s()
    try:
        promos = await asyncio.to_thread(stripe.PromotionCode.list, limit=100)
        beta = [p for p in promos.data if p.metadata.get("tipo") == "beta_invite"]
        return [
            {
                "code":             p.code,
                "nombre":           p.metadata.get("nombre", ""),
                "meses":            p.metadata.get("meses", "6"),
                "times_redeemed":   p.times_redeemed,
                "max_redemptions":  p.max_redemptions,
                "expires_at":       p.expires_at,
                "active":           p.active,
            }
            for p in beta
        ]
    except Exception as e:
        logger.error(f"[billing] listar_invites_beta: {e}")
        return []


# ── Webhooks ──────────────────────────────────────────────────────────────────

def verificar_webhook(payload: bytes, sig_header: str):
    """Verifica la firma del webhook. Retorna el evento Stripe o None."""
    stripe = _s()
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    try:
        return stripe.Webhook.construct_event(payload, sig_header, secret)
    except Exception as e:
        logger.warning(f"[billing] Webhook firma inválida: {e}")
        return None


def plan_desde_price_id(price_id: str) -> str:
    """Dado un Stripe price_id retorna 'basic' | 'pro' | 'unknown'."""
    for plan, pid in PRICE_IDS.items():
        if pid and pid == price_id:
            return plan
    return "unknown"


# ── Acceso ────────────────────────────────────────────────────────────────────

def plan_activo(user: dict) -> bool:
    """True si el usuario puede acceder al panel (trial vigente o suscripción activa)."""
    from datetime import datetime, timedelta

    plan        = user.get("plan", "trial")
    plan_status = user.get("plan_status", "trialing")

    if plan_status in ("active", "trialing") and plan in ("basic", "pro"):
        return True

    if plan == "trial":
        created_raw = user.get("created_at", "")
        if created_raw:
            try:
                created_dt = datetime.fromisoformat(created_raw)
                return datetime.utcnow() < created_dt + timedelta(days=14)
            except Exception:
                pass

    return False


def dias_trial_restantes(user: dict) -> int:
    """Días restantes de trial (0 si ya venció o tiene suscripción)."""
    from datetime import datetime, timedelta
    if user.get("plan", "trial") != "trial":
        return 0
    created_raw = user.get("created_at", "")
    if not created_raw:
        return 0
    try:
        created_dt = datetime.fromisoformat(created_raw)
        delta = (created_dt + timedelta(days=14)) - datetime.utcnow()
        return max(0, delta.days)
    except Exception:
        return 0
