# Barrio Pizza — Motor de Alertas de Compras

API que revisa las órdenes de compra semanales de las 10 sucursales, proyecta el
consumo esperado a partir del histórico y genera alertas automáticas cuando una
orden se aleja de lo que realmente se necesita (sobre-pedido, riesgo de quiebre
o insumos olvidados).

Este repositorio contiene únicamente la **capa de datos/API**. El dashboard
(frontend) se desarrolla en un repositorio/carpeta aparte y consume esta API.

## Estructura del proyecto

```
barrio-pizza-alertas/
├── app/
│   ├── api/        # Endpoints de FastAPI
│   ├── core/        # Lógica de negocio: conversión de unidades, proyección, alertas
│   └── models/       # Schemas Pydantic (contrato con el frontend)
├── data/            # CSVs de entrada (ingredientes, consumo, inventario, órdenes)
├── tests/           # Tests con pytest
├── main.py          # Punto de entrada de la app FastAPI
└── requirements.txt
```

## Cómo correrlo localmente

```bash
# 1. Crear y activar entorno virtual
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Levantar el servidor
uvicorn main:app --reload
```

La API queda disponible en `http://127.0.0.1:8000` y la documentación
interactiva (Swagger) en `http://127.0.0.1:8000/docs`.

## Correr los tests

```bash
pytest
```

## Estado actual

- [x] Esqueleto del proyecto + FastAPI corriendo
- [x] Endpoints definidos con datos de ejemplo (`/api/alertas`, `/api/proyeccion/...`)
- [ ] Carga y validación de los 4 CSV
- [ ] Conversión de formatos de compra a unidad base
- [ ] Motor de proyección de consumo (tendencia + fallback a promedio ponderado)
- [ ] Cálculo de necesidad real y comparación contra la orden
- [ ] Motor de alertas conectado a datos reales
- [ ] Chat con los datos (DeepSeek)

## Supuestos

_(se va completando a medida que se toman decisiones de diseño)_

## Cómo se conectaría a Odoo en producción

_(pendiente — se documenta antes de la entrega final)_

## Uso de IA en el desarrollo

_(pendiente — se documenta antes de la entrega final)_
