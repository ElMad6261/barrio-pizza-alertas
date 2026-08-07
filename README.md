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

## Endpoints disponibles

| Endpoint | Qué devuelve |
|---|---|
| `GET /api/health` | Chequeo de que la API está viva |
| `GET /api/sucursales` | Las sucursales válidas (para dropdowns/filtros, sin hardcodear) |
| `GET /api/proveedores` | Los proveedores del catálogo |
| `GET /api/ingredientes` | Catálogo completo de ingredientes |
| `GET /api/alertas` | Todas las alertas de la semana, ordenadas por urgencia |
| `GET /api/alertas/{sucursal}` | Alertas filtradas por una sucursal (404 si la sucursal no existe) |
| `GET /api/proyecciones` | Tabla completa (o filtrada con `?sucursal=`) con proyección, r2, semanas excluidas y necesidad de cada combinación |
| `GET /api/proyeccion/{sucursal}/{ingrediente_id}` | Detalle de una proyección puntual, con el histórico de 6 semanas marcando outliers (para graficar) |
| `GET /api/pedido-corregido-por-proveedor` | Orden corregida, agrupada por proveedor |

Todos documentados e interactivos en `/docs` (Swagger).

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
- [x] Carga y validación de los 4 CSV
- [x] Conversión de formatos de compra a unidad base
- [x] Motor de proyección de consumo (tendencia + fallback a promedio ponderado)
- [x] Cálculo de necesidad real y comparación contra la orden
- [x] Motor de alertas conectado a datos reales (`/api/alertas`, `/api/alertas/{sucursal}`)
- [x] Pedido corregido agrupado por proveedor (`/api/pedido-corregido-por-proveedor`)
- [ ] Chat con los datos (DeepSeek)

## Supuestos

- Los CSV se leen con encoding `utf-8-sig` porque traen BOM (típico al exportar desde Excel/Google Sheets).
- Un ingrediente que falta en `orden_compra_semana.csv` para una sucursal **no se trata como error**: es justamente la señal de "insumo olvidado" que el reto pide detectar como alerta.
- Un ingrediente que aparece en `orden_compra_semana.csv` (o inventario/consumo) pero **no existe en `ingredientes.csv`** se marca como "ingrediente desconocido" — no se puede convertir a unidad base porque no hay factor de conversión, así que se excluye del cálculo de necesidad y se reporta aparte (ej. `aji_chombo` en Costa del Este).
- Un ingrediente que falta en `inventario_actual.csv` sí se considera un problema real de datos, porque sin stock actual no se puede calcular la necesidad real.
- Se valida que no existan valores negativos en stock, consumo o cantidad pedida.

### Metodología de proyección

Para cada sucursal-ingrediente, sobre las 6 semanas de histórico:

1. **Detección de outliers dentro de la serie**: se usa el z-score modificado (basado en desviación absoluta respecto a la mediana), con umbral 3.5 — más robusto que el desvío estándar clásico para series de solo 6 puntos, porque un único valor extremo no infla la propia medida de dispersión de referencia. Si la serie es prácticamente constante, no se marca ningún outlier (no hay forma confiable de distinguirlo del ruido normal).
2. **Ajuste de tendencia**: con los puntos no-atípicos, si quedan al menos 4 de las 6 semanas se ajusta una regresión lineal. Si el R² ≥ 0.5, se usa esa tendencia para proyectar la semana siguiente.
3. **Fallback a promedio ponderado**: si no hay suficiente señal de tendencia (R² bajo o muy pocos puntos), se usa un promedio ponderado que le da más peso a las semanas recientes.
4. Ninguna proyección puede dar un valor negativo (se acota a 0 como mínimo).

Sobre los datos reales del reto: 3 de las 88 combinaciones muestran tendencia real (ej. harina en Costa del Este, R²=0.999), y el pico artificial de pepperoni en Marbella (semana 3) se detecta y excluye correctamente antes de proyectar.

### Motor de alertas

- `necesidad_real = max(0, consumo_proyectado - inventario_actual)`. Se acota a un mínimo de 0: si ya sobra inventario, no tiene sentido una "necesidad negativa" — y evita que una sucursal con stock de sobra que no pide nada termine marcada como sobre-pedido sobre una orden que ni siquiera existe.
- `delta = cantidad_pedida - necesidad_real`. Una diferencia menor a **un formato completo** del ingrediente se considera redondeo normal (no existe medio saco) y no genera alerta.
- Un ingrediente sin pedido y con necesidad real por encima de la tolerancia se marca como **insumo olvidado**, distinto de un riesgo de quiebre genérico — la causa raíz es otra (nunca se pidió, vs. se pidió de menos).
- Un ingrediente pedido que no existe en el catálogo (ver `aji_chombo`) no se puede convertir a unidad base, pero **sí genera su propia alerta visible** ("ingrediente desconocido") en vez de desaparecer silenciosamente del dashboard.
- Las alertas se devuelven ordenadas de mayor a menor cantidad, para que lo más urgente se vea primero.

Con los datos reales del reto, el motor genera 5 alertas: 1 insumo olvidado (mozzarella en Brisas del Golf, ~178 kg), 1 riesgo de quiebre (harina en Costa del Este, ~150 kg de menos), 2 sobre-pedidos (cebolla en Brisas del Golf, albahaca en Via Argentina) y 1 ingrediente desconocido (aji_chombo en Costa del Este).

### Pedido corregido por proveedor

`GET /api/pedido-corregido-por-proveedor` propone la cantidad que cada sucursal debería pedir (necesidad real redondeada **hacia arriba** al formato completo más cercano — no se puede comprar medio saco) y agrupa el resultado por proveedor, para poder reenviarle a cada uno directamente su parte de la orden corregida.

- Una línea con necesidad real de 0 no se incluye — no tiene sentido reenviarle al proveedor un pedido en cero.
- Cada línea indica si la cantidad corregida difiere de la original (`cambio: true/false`), para que el frontend pueda resaltar solo lo que realmente cambió.
- Con los datos del reto, esto agrupa correctamente en los 8 proveedores reales del catálogo (Molinos Central, Distrib. Bella Italia, AgroFresco, Verduras La Huerta, Importadora Istmo, Hongos del Valle, EmpaqueTodo, Deli Gourmet).

## Cómo se conectaría a Odoo en producción

_(pendiente — se documenta antes de la entrega final)_

## Uso de IA en el desarrollo

_(pendiente — se documenta antes de la entrega final)_
