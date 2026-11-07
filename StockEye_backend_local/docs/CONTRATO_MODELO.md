# Archivo único acordado con el responsable del modelo

El backend recibe un `.pt` de SegFormer StockEye v6. La extensión por sí sola no determina el formato: un checkpoint YOLO, un `state_dict` sin metadatos o un objeto Python serializado completo no cumplen este contrato.

## Forma recomendada

`preparar_modelo.py` genera un archivo con estas claves:

| Clave | Contenido |
|---|---|
| `formato` | `stockeye-local-1` |
| `pipeline` | `stockeye-v6-corregido-1` |
| `clases` | `{"0":"fondo","1":"ocupado","2":"vacio"}` |
| `modelo` | `state_dict` de `SegformerForSemanticSegmentation` |
| `model_config` | Diccionario de arquitectura de `SegformerConfig` |
| `config` | Configuración de preprocesamiento, geometría y semáforos del notebook |
| `operacion` | `modo` y `umbral_vacio` validados en Colab |
| `procedencia` | Checkpoint o bundle exportado |
| `checkpoint_original_sha256` | Identificación del origen |

Los tensores se cargan con `weights_only=True`, `map_location="cpu"` y `strict=True`; después se mueve el modelo al dispositivo elegido. La arquitectura se construye desde el diccionario guardado. No se consulta Hugging Face durante la carga.

También se acepta `best.pt` del notebook sin el empaquetado si contiene `modelo`, `model_config`, `config` y `pipeline`, y se indican modo y umbral en `config.json`. El empaquetado permite cambiar solamente el `.pt` en futuras entregas, incluyendo esos valores en el archivo.

Se utiliza el mismo orden de clases y normalización RGB del código de inferencia del notebook. Cambiar las clases o entregar otra familia de modelo exige adaptar el cargador, no solo renombrar el archivo. Si cambia el modo o el umbral, deben actualizarse junto con los pesos y volver a validarse sus resultados y consumo en el PC.

## Preparar desde el checkpoint actual

Ejemplo, sustituyendo los valores por los validados en `[6.3]`:

```powershell
.\.venv\Scripts\python.exe preparar_modelo.py --checkpoint "C:\entrenamiento\best.pt" --modo "mosaicos+tta" --umbral 0.5 --salida modelos\modelo.pt
```

Puede ejecutarse en el PC de quien prepara la entrega. No requiere editar ni volver a ejecutar todo el notebook. No sobrescribe el checkpoint original ni una salida existente.

## Reparto del trabajo

- Responsable del modelo: entrenar, revisar etiquetas, validar el foco en vacíos, elegir modo/umbral y entregar el `.pt` compatible.
- Responsable del backend: vigilar las dos carpetas, asignar sucursal, conservar la cola, ejecutar la inferencia y entregar archivos/JSON mediante la API.

La revisión por sucursal pertenece al backend. El `.pt` no necesita aprender ni recibir el número de sucursal. El entrenamiento utiliza ocupado como referencia y conserva el foco en vacío; la API preserva los estados parciales y no convierte un resultado desconocido en cero.
