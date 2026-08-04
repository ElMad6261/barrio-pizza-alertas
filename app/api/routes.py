"""
Endpoints de la API.

Por ahora devuelven datos de ejemplo (dummy) para poder levantar el
servidor y validar el contrato con el frontend desde ya. En los
siguientes pasos, cada endpoint va a llamar a app/core/ en vez de
devolver datos fijos.
"""

from fastapi import APIRouter

from app.models.schemas import (
    Alerta,
    MetodoProyeccion,
    ProyeccionDetalle,
    ResumenSemanal,
    TipoAlerta,
)

router = APIRouter()


@router.get("/health")
def health_check():
    """Chequeo simple de que la API está viva."""
    return {"status": "ok"}


@router.get("/alertas", response_model=ResumenSemanal)
def obtener_alertas():
    """
    Devuelve todas las alertas de la semana actual.

    TODO: reemplazar el contenido dummy por una llamada a
    app.core.alertas.generar_alertas() una vez esté implementado.
    """
    alertas_dummy = [
        Alerta(
            sucursal="Sucursal Centro",
            ingrediente="Queso mozzarella",
            tipo=TipoAlerta.RIESGO_QUIEBRE,
            cantidad=18.5,
            unidad="kg",
            mensaje=(
                "ALERTA: Sucursal Centro está pidiendo 18.5 kg de "
                "Queso mozzarella menos que lo proyectado → riesgo de quiebre."
            ),
        ),
        Alerta(
            sucursal="Sucursal Este",
            ingrediente="Harina 000",
            tipo=TipoAlerta.SOBRE_PEDIDO,
            cantidad=40.0,
            unidad="kg",
            mensaje=(
                "ALERTA: Sucursal Este está pidiendo 40.0 kg de "
                "Harina 000 más que lo proyectado → capital inmovilizado."
            ),
        ),
    ]

    return ResumenSemanal(
        total_alertas=len(alertas_dummy),
        riesgo_quiebre=1,
        sobre_pedido=1,
        insumos_olvidados=0,
        alertas=alertas_dummy,
    )


@router.get("/alertas/{sucursal}", response_model=list[Alerta])
def obtener_alertas_por_sucursal(sucursal: str):
    """Devuelve solo las alertas de una sucursal puntual."""
    # TODO: filtrar por sucursal real una vez conectado al motor de datos.
    return []


@router.get("/proyeccion/{sucursal}/{ingrediente}", response_model=ProyeccionDetalle)
def obtener_proyeccion(sucursal: str, ingrediente: str):
    """
    Devuelve el detalle completo de una proyección puntual.
    Útil para debug y para mostrar el "por qué" de una alerta en el dashboard.
    """
    # TODO: reemplazar por el cálculo real.
    return ProyeccionDetalle(
        sucursal=sucursal,
        ingrediente=ingrediente,
        consumo_proyectado=120.0,
        inventario_actual=101.5,
        necesidad_real=18.5,
        cantidad_pedida=0.0,
        unidad="kg",
        metodo=MetodoProyeccion.TENDENCIA,
        delta_vs_pedido=-18.5,
    )
