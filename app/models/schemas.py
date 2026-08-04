"""
Schemas Pydantic compartidos por toda la API.

Estos modelos son el "contrato" entre el motor de datos y el frontend.
Cualquier frontend (Streamlit, React, lo que sea) va a consumir JSON
con esta forma exacta, sin necesidad de leer código Python.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TipoAlerta(str, Enum):
    RIESGO_QUIEBRE = "riesgo_quiebre"      # están pidiendo menos de lo necesario
    SOBRE_PEDIDO = "sobre_pedido"          # están pidiendo de más
    INSUMO_OLVIDADO = "insumo_olvidado"    # no aparece en la orden pero se proyecta consumo
    ANOMALIA = "anomalia"                  # (extra) outlier vs. otras sucursales


class MetodoProyeccion(str, Enum):
    TENDENCIA = "tendencia"                # regresión lineal sobre el histórico
    PROMEDIO_PONDERADO = "promedio_ponderado"  # fallback cuando no hay señal de tendencia clara


class Alerta(BaseModel):
    sucursal: str
    ingrediente: str
    tipo: TipoAlerta
    cantidad: float = Field(..., description="Diferencia en unidad base (kg, L, unidades)")
    unidad: str
    mensaje: str = Field(..., description="Texto legible listo para mostrar en el dashboard")


class ProyeccionDetalle(BaseModel):
    sucursal: str
    ingrediente: str
    consumo_proyectado: float
    inventario_actual: float
    necesidad_real: float
    cantidad_pedida: float
    unidad: str
    metodo: MetodoProyeccion
    delta_vs_pedido: float


class ResumenSemanal(BaseModel):
    total_alertas: int
    riesgo_quiebre: int
    sobre_pedido: int
    insumos_olvidados: int
    alertas: list[Alerta]
