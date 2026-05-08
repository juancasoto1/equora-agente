import os
import json
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, select, Integer
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./agentkit.db")

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Mensaje(Base):
    __tablename__ = "mensajes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Cliente(Base):
    __tablename__ = "clientes"

    telefono: Mapped[str] = mapped_column(String(50), primary_key=True)
    nombres: Mapped[str] = mapped_column(String(100), default="")
    apellidos: Mapped[str] = mapped_column(String(100), default="")
    razon_social: Mapped[str] = mapped_column(String(200), default="")
    cc_nit: Mapped[str] = mapped_column(String(50), default="")
    direccion: Mapped[str] = mapped_column(String(200), default="")
    barrio: Mapped[str] = mapped_column(String(100), default="")
    ciudad: Mapped[str] = mapped_column(String(100), default="")
    departamento: Mapped[str] = mapped_column(String(100), default="")
    email: Mapped[str] = mapped_column(String(100), default="")
    pedidos_realizados: Mapped[int] = mapped_column(Integer, default=0)
    pedido_pendiente: Mapped[str] = mapped_column(Text, default="")
    pedido_pendiente_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    actualizado: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


CAMPOS_CLIENTE = (
    "nombres", "apellidos", "razon_social", "cc_nit",
    "direccion", "barrio", "ciudad", "departamento", "email",
)


async def inicializar_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migración: agregar columnas nuevas si la tabla ya existía sin ellas
        for sql in (
            "ALTER TABLE clientes ADD COLUMN pedido_pendiente TEXT DEFAULT ''",
            "ALTER TABLE clientes ADD COLUMN pedido_pendiente_at DATETIME",
        ):
            try:
                await conn.exec_driver_sql(sql)
            except Exception:
                pass  # ya existe


async def guardar_mensaje(telefono: str, role: str, content: str):
    async with async_session() as session:
        mensaje = Mensaje(
            telefono=telefono,
            role=role,
            content=content,
            timestamp=datetime.utcnow()
        )
        session.add(mensaje)
        await session.commit()


async def obtener_historial(telefono: str, limite: int = 20) -> list[dict]:
    async with async_session() as session:
        query = (
            select(Mensaje)
            .where(Mensaje.telefono == telefono)
            .order_by(Mensaje.timestamp.desc())
            .limit(limite)
        )
        result = await session.execute(query)
        mensajes = result.scalars().all()
        mensajes.reverse()
        return [
            {"role": msg.role, "content": msg.content}
            for msg in mensajes
        ]


async def limpiar_historial(telefono: str):
    async with async_session() as session:
        query = select(Mensaje).where(Mensaje.telefono == telefono)
        result = await session.execute(query)
        mensajes = result.scalars().all()
        for msg in mensajes:
            await session.delete(msg)
        await session.commit()


async def guardar_cliente(telefono: str, datos: dict):
    """Crea o actualiza el perfil del cliente. Solo guarda campos no vacíos."""
    async with async_session() as session:
        cliente = await session.get(Cliente, telefono)
        if cliente:
            for campo in CAMPOS_CLIENTE:
                valor = datos.get(campo)
                if valor:
                    setattr(cliente, campo, str(valor))
            cliente.pedidos_realizados = (cliente.pedidos_realizados or 0) + 1
            cliente.actualizado = datetime.utcnow()
        else:
            valores = {c: str(datos.get(c, "")) for c in CAMPOS_CLIENTE}
            cliente = Cliente(telefono=telefono, pedidos_realizados=1, **valores)
            session.add(cliente)
        await session.commit()


async def obtener_cliente(telefono: str) -> dict | None:
    """Devuelve los datos guardados del cliente o None si no existe."""
    async with async_session() as session:
        cliente = await session.get(Cliente, telefono)
        if not cliente:
            return None
        return {
            "telefono": cliente.telefono,
            "nombres": cliente.nombres,
            "apellidos": cliente.apellidos,
            "razon_social": cliente.razon_social,
            "cc_nit": cliente.cc_nit,
            "direccion": cliente.direccion,
            "barrio": cliente.barrio,
            "ciudad": cliente.ciudad,
            "departamento": cliente.departamento,
            "email": cliente.email,
            "pedidos_realizados": cliente.pedidos_realizados or 0,
        }


PEDIDO_PENDIENTE_TTL_HORAS = 48


async def guardar_pedido_pendiente(telefono: str, productos: list[dict]):
    """Guarda el carrito que el cliente confirmó pero aún no completó en Shopify.
    Sirve para retomarlo si vuelve a escribir antes de finalizar el checkout."""
    if not productos:
        return
    async with async_session() as session:
        cliente = await session.get(Cliente, telefono)
        ahora = datetime.utcnow()
        if not cliente:
            cliente = Cliente(telefono=telefono)
            session.add(cliente)
        cliente.pedido_pendiente = json.dumps(productos, ensure_ascii=False)
        cliente.pedido_pendiente_at = ahora
        cliente.actualizado = ahora
        await session.commit()


async def obtener_pedido_pendiente(telefono: str) -> list[dict] | None:
    """Devuelve el carrito pendiente si existe y no ha expirado."""
    async with async_session() as session:
        cliente = await session.get(Cliente, telefono)
        if not cliente or not cliente.pedido_pendiente or not cliente.pedido_pendiente_at:
            return None
        if datetime.utcnow() - cliente.pedido_pendiente_at > timedelta(hours=PEDIDO_PENDIENTE_TTL_HORAS):
            return None
        try:
            return json.loads(cliente.pedido_pendiente)
        except Exception:
            return None


async def limpiar_pedido_pendiente(telefono: str):
    """Borra el carrito pendiente — cliente completó el pedido en Shopify."""
    async with async_session() as session:
        cliente = await session.get(Cliente, telefono)
        if cliente:
            cliente.pedido_pendiente = ""
            cliente.pedido_pendiente_at = None
            cliente.actualizado = datetime.utcnow()
            await session.commit()
