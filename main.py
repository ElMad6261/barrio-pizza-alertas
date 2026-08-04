"""
Punto de entrada de la API de alertas de compras — Barrio Pizza.

Correr localmente:
    uvicorn main:app --reload

Docs interactivas una vez levantado:
    http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router

app = FastAPI(
    title="Barrio Pizza — Motor de Alertas de Compras",
    description=(
        "API que revisa las órdenes de compra semanales de cada sucursal "
        "y genera alertas automáticas de sobre-pedido, riesgo de quiebre "
        "e insumos olvidados."
    ),
    version="0.1.0",
)

# Habilitado ampliamente por ahora porque el frontend se desarrolla aparte
# y todavía no se sabe en qué dominio/puerto va a correr.
# TODO: restringir allow_origins antes de producción.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
def root():
    return {
        "proyecto": "Barrio Pizza — Motor de Alertas de Compras",
        "docs": "/docs",
    }
