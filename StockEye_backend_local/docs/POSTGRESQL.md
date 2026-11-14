# PostgreSQL en StockEye

La cola activa utiliza PostgreSQL. SQLite queda como origen histórico de importación y respaldo; un fallo PostgreSQL no provoca retorno silencioso a SQLite.

## Bases locales

| Proyecto | Base |
|---|---|
| StockEye_backend_local | stockeye_dev |
| bakend_StockEye/StockEye_backend_local | stockeye_copia_dev |
| Pruebas aisladas | stockeye_test |

Servidor: 127.0.0.1:5432. Android sigue consultando la API del puerto 8000, sin contraseña de base de datos. Las dos copias conservan historiales separados.

## Configuración y credenciales

El bloque `base_datos` de `config.json` contiene `dsn` sin contraseña, `variable_entorno` (STOCKEYE_DATABASE_URL), `connect_timeout` y `statement_timeout_ms`.

La cuenta técnica `stockeye_app` no es superusuario. En Windows se obtiene su contraseña del archivo privado `%APPDATA%/postgresql/pgpass.conf`, fuera de Git y OneDrive. El archivo contiene contraseña en texto, por lo que se restringe a su usuario y SYSTEM. No copie su contenido al APK o al chat.

No se carga .env automáticamente. La variable de entorno, si existe, sustituye el DSN configurado; no use globalmente la base de una copia como sustitución de todas.

## Esquema y exclusión

`public.trabajos` y `public.observaciones` conservan la cola; `public.schema_migrations` registra versiones y huellas SHA-256.

No edite `migraciones/001_cola.sql` después de aplicarla. Añada una migración nueva para cambiar tablas. El servicio comprueba versión y huella antes de recuperar trabajos.

Las fechas ISO permanecen en TEXT para preservar el contrato, `visto_desde` en DOUBLE PRECISION y `registrado` en BOOLEAN.

Una sesión PostgreSQL con advisory lock impide que dos carpetas apunten a la misma base y recuperen trabajos simultáneamente. Se conserva también el bloqueo de carpeta. Si se pierde la sesión, se detiene el procesamiento; no se promete inferencia exactamente una vez ante una caída.

Fotos, máscaras, JSON y pesos permanecen fuera de PostgreSQL.

## Importación

`migrar_postgres.py` no inicia API ni modelo:

| Opción | Función |
|---|---|
| --inventario | Lee SQLite y muestra conteos y huellas. |
| --snapshot --respaldo RUTA_NUEVA | Crea una copia consistente sin reemplazar archivos. |
| --preparar-esquema | Aplica SQL y verifica huellas ya registradas. |
| --importar --respaldo RUTA_NUEVA | Importa a destino vacío y compara todas las columnas antes del commit. |
| --verificar | Compara PostgreSQL con el origen congelado, antes de reanudar procesamiento. |
| --config RUTA | Selecciona la configuración. |
| --sqlite RUTA | Selecciona el origen explícito. |

Conserva IDs de 32 caracteres, nulos, estados, fechas, intentos y secuencias. Se respeta también el contador histórico de SQLite. El origen y las fotografías no se eliminan. Las operaciones toman los bloqueos; no matan procesos.

### Rutas absolutas de la segunda copia

La SQLite copiada conservaba rutas de pendientes hacia el proyecto referencia. `--reubicar-copias` permite reparar exclusivamente las referencias de trabajos pendientes/procesando:

1. Busca el mismo nombre en `datos/pendientes` del proyecto seleccionado.
2. Exige archivo local dentro de esa carpeta y SHA-256 coincidente.
3. Cambia solo la referencia `copia` importada y registra ID/anterior/nueva.
4. No cambia SQLite ni mueve, borra o sobrescribe imágenes.

Use la opción también al verificar. Revise primero `--inventario --reubicar-copias`. La copia de este equipo requirió reubicar 138 referencias activas.

## Administrar desde pgAdmin

Conecte a 127.0.0.1:5432 usando la cuenta administrativa creada en el instalador. La contraseña administrativa no está en el proyecto.

Consultas de inspección:

```sql
SELECT current_database(), current_user;
SELECT estado, COUNT(*) FROM public.trabajos GROUP BY estado;
SELECT sucursal_id, estado, COUNT(*)
FROM public.trabajos GROUP BY sucursal_id, estado;
SELECT version, aplicado_en FROM public.schema_migrations ORDER BY version;
```

Edite reglas de negocio en Python y estructura mediante migraciones nuevas. La edición directa de filas puede saltarse validaciones: no la use para forzar estados o eludir bloqueos sin procedimiento registrado.

## Arranque y gestión

PostgreSQL debe funcionar antes de iniciar StockEye. `iniciar.py` conserva su función de iniciar API, cargar modelo y procesar pendientes; no hace falta ejecutarlo para migrar.

`gestionar.py estado` consulta conteos y `gestionar.py reintentar-errores` devuelve errores a pendientes con el backend detenido. Ambas herramientas usan PostgreSQL y no cargan el modelo.

## Pruebas

La fixture exige `STOCKEYE_TEST_DATABASE_URL` y verifica que la base sea exactamente `stockeye_test` antes de crear/limpiar tablas.

```powershell
$env:STOCKEYE_TEST_DATABASE_URL = "host=127.0.0.1 port=5432 dbname=stockeye_test user=stockeye_app"
.\.venv\Scripts\python.exe -m pytest tests/test_cola.py tests/test_api.py tests/test_postgres_migracion.py -q -k "not api_sigue_respondiendo_durante_inferencia and not arranca_sin_pt"
```

La base de pruebas se limpia entre casos. La selección usa motor controlado e imágenes temporales, no pesos ni entradas reales. La suite completa incluye pruebas adicionales de modelo y proceso HTTP; es otro alcance.

Las nuevas pruebas cubren filas, secuencia, rechazo de sobrescritura, snapshots, SQL alterado, bloqueos, pérdida de sesión y reparación de rutas con hash válido/inválido.

## Respaldo y alcance

Respaldar PostgreSQL no incluye automáticamente fotos, resultados o pesos externos. Conserve ambos conjuntos. Volver a SQLite no incorpora por sí solo datos nuevos que se hayan guardado en PostgreSQL.

Esta migración conserva la API actual. Todavía no implementa tickets, usuarios reales, asignaciones o cámara del mockup; esos cambios se añadirán explícitamente después.

Fuentes: [PostgreSQL Windows](https://www.postgresql.org/download/windows/), [pgAdmin Query Tool](https://www.pgadmin.org/docs/pgadmin4/latest/query_tool.html), [archivo de contraseñas](https://www.postgresql.org/docs/current/libpq-pgpass.html).
