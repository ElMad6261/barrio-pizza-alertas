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
    INGREDIENTE_DESCONOCIDO = "ingrediente_desconocido"  # está en la orden pero no en el catálogo
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


class PuntoHistorico(BaseModel):
    semana: int
    consumo: float
    es_outlier: bool = Field(..., description="True si esta semana se excluyó del ajuste de tendencia")


class ProyeccionResumen(BaseModel):
    """Fila liviana para una tabla con todas las combinaciones sucursal-ingrediente."""

    sucursal: str
    ingrediente: str
    ingrediente_id: str
    consumo_proyectado: float
    inventario_actual: float
    necesidad_real: float
    cantidad_pedida: float
    unidad: str
    metodo: MetodoProyeccion
    r2: Optional[float] = Field(None, description="Solo aplica si hubo suficientes puntos para ajustar una tendencia")
    semanas_excluidas: list[int] = Field(default_factory=list)
    delta_vs_pedido: float


class ProyeccionDetalle(ProyeccionResumen):
    """Mismo contenido que ProyeccionResumen, más el histórico para graficar."""

    historico: list[PuntoHistorico]


class ResumenSemanal(BaseModel):
    total_alertas: int
    riesgo_quiebre: int
    sobre_pedido: int
    insumos_olvidados: int
    ingredientes_desconocidos: int
    alertas: list[Alerta]


class LineaPedidoCorregido(BaseModel):
    sucursal: str
    ingrediente: str
    formato_compra: str
    unidad_base: str
    cantidad_formatos_original: float = Field(..., description="Lo que la sucursal pidió, en formatos")
    cantidad_formatos_corregida: float = Field(..., description="Lo que debería pedir según la proyección, en formatos")
    cambio: bool = Field(..., description="True si la cantidad corregida difiere de la original")


class PedidoPorProveedor(BaseModel):
    proveedor: str
    lineas: list[LineaPedidoCorregido]
    total_lineas_corregidas: int = Field(..., description="Cuántas líneas de este proveedor difieren de lo pedido")


class IngredienteInfo(BaseModel):
    ingrediente_id: str
    nombre: str
    proveedor: str
    unidad_base: str
    formato_compra: str
    es_perecedero: bool


class PreguntaChat(BaseModel):
    pregunta: str = Field(..., min_length=1, max_length=500, description="Pregunta en español sobre los datos de la semana")


class RespuestaChat(BaseModel):
    respuesta: str
