# Verificación de esta entrega

Resultado: **39 pruebas aprobadas** mediante `python -m pytest -q`, en 10,60 segundos.

## Qué se comprobó

- Dos carpetas con 100 archivos cada una: 200 trabajos encolados una sola vez y un único procesador tomando el siguiente.
- Nombre de imagen repetido en sucursales distintas, sin confundir sus identificadores.
- Confirmación de estabilidad en dos revisiones, archivos temporales, vacíos y excesos de tamaño.
- Copia de entrada que conserva los bytes aunque se sobrescriba después la fotografía de origen.
- Persistencia SQLite, orden FIFO, recuperación de trabajos interrumpidos y reintentos explícitos de errores.
- Recuperación de resultados atómicos existentes después de una caída entre el guardado y la confirmación de la cola.
- Rechazo de una segunda instancia que intente usar la misma cola.
- Continuación después de una imagen dañada y conservación de un análisis completado aunque falle la limpieza temporal.
- Filtros de sucursal, paginación, detalle, descarga de original/máscara/JPEG y formato de lista compatible con la demo Kotlin.
- Conservación de `parcial`, `revisar` y porcentaje completo `null`.
- Superposición amarilla sobre vacío y conservación visual del área ocupada.
- Rechazo de rutas externas en los archivos de resultados y respuesta explícita ante JSON corrupto.
- Consultas HTTP y revisión de nuevas imágenes mientras hay una inferencia en curso.
- Arranque sin modelo, con API disponible y pendientes conservados.
- Preparación de un único `.pt`, comprobación de tensores y clases, integridad del bundle, ausencia de descarga de arquitectura y cambio de identidad al sustituir pesos.
- Aplicación del presupuesto de tiempo y del límite de píxeles.
- Arranque de `iniciar.py` en un proceso independiente, revisión automática, inferencia CPU real con un modelo de prueba, guardado, descarga HTTP por sucursal y cierre normal.

## Entorno y límites de la prueba

Se ejecutó en Linux con Python 3.12.14, PyTorch 2.7.1+cpu, Transformers 4.57.6, FastAPI 0.162.0, OpenCV 5.0.0 y Pillow 12.3.0. `pip check` no encontró dependencias incompatibles.

Las pruebas del modelo usaron un SegFormer pequeño de pesos controlados, generado temporalmente para comprobar la carga y el recorrido técnico. **No es el modelo entrenado del proyecto y no se incluye en el ZIP.** Otras pruebas utilizaron un doble de inferencia identificado explícitamente como prueba.

La verificación no mide precisión de vacíos, falsos positivos, recall ni rendimiento del modelo de tu compañero. Sigue pendiente comprobar el `.pt` real, sus valores validados de modo/umbral y el consumo/tiempo en el PC Windows destino. No se ha ejecutado ni configurado el equipo del usuario y no se ha comprobado la conexión con su teléfono o OneDrive.

El cliente HTTP de pruebas emitió una advertencia de deprecación de Starlette/httpx. No hubo pruebas fallidas. Esa advertencia corresponde al entorno de pruebas, no a una predicción o un endpoint de la aplicación.
