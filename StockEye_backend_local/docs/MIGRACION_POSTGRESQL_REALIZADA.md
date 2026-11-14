# Migración a PostgreSQL realizada

Fecha: 14 de noviembre de 2026.

| Proyecto | Base activa | Trabajos | Análisis completados | Observaciones |
|---|---|---:|---:|---:|
| StockEye_backend_local | stockeye_dev | 159 | 98 | 159 |
| bakend_StockEye/StockEye_backend_local | stockeye_copia_dev | 157 | 19 | 157 |

Se conservaron identificadores, estados, fechas, intentos, porcentajes, archivos y pesos.
En la copia se ajustaron 138 referencias activas a sus propios archivos, comprobando cada SHA-256.
Las SQLite originales permanecen en datos/cola.sqlite3 como origen histórico; ya no son la cola activa.
No se fusionaron historiales ni se ejecutó inferencia.

## Verificación

- Comparación completa de todas las columnas de trabajos y observaciones contra SQLite; en la copia, después de la transformación explícita de rutas.
- 35 pruebas aprobadas en stockeye_test; 2 pruebas con otros alcances excluidas.
- Consultas de salud, listados por sucursal, trabajos, análisis y descarga de original/marcada verificadas con HTTP en memoria sobre ambos proyectos instalados.
- No se inició el servidor real ni se cargó el modelo entrenado.
- PostgreSQL 18.7 y Psycopg 3.3.9; conexión restringida a 127.0.0.1:5432.
- Base de pruebas separada; cuenta stockeye_app sin superusuario.
- La contraseña de conexión permanece en el perfil privado de Windows, fuera de OneDrive y Git. La contraseña administrativa no se persistió.

Un trabajo de cada historial conserva su estado procesando de origen.
Al iniciar normalmente el backend, su recuperación lo devolverá a pendiente.
No se ha iniciado ese procesamiento durante la migración.

## Respaldos

C:\Users\janto\OneDrive\Desktop\duoc\Respaldos\StockEye-antes-postgresql-20261114-184402

Contiene código/configuración previos, snapshots SQLite y archivos PostgreSQL .dump de ambos historiales.
Los respaldos PostgreSQL se comprobaron mediante lectura de catálogo con pg_restore.
No incluyen los bytes de fotografías ni del modelo; esos archivos originales siguen en sus carpetas.

## Administración

Consultar [POSTGRESQL.md](POSTGRESQL.md) para pgAdmin, conexión, migraciones y respaldos.
Para abrir pgAdmin, utilizar la aplicación instalada con PostgreSQL.
Registrar servidor 127.0.0.1, puerto5432 y usuario administrativo postgres con la contraseña elegida en el instalador.
Las bases son stockeye_dev, stockeye_copia_dev y stockeye_test.

Cambios de estructura deben quedar en migraciones SQL versionadas.
No editar una migración aplicada: crear otra.
No volver a importar sobre las bases activas; el importador lo rechaza si contienen filas.

Las reglas y tablas futuras de tickets/evidencias del mockup aún no se implementaron.
Esta entrega migra la cola y sus registros, manteniendo el contrato Android existente.

## Retorno

El respaldo de código y SQLite conserva el estado anterior a esta migración.
Si se añaden datos nuevos a PostgreSQL, restaurar el estado anterior no los incorpora automáticamente.
No cambiar de motor ni restaurar archivos mientras algún backend esté procesando.
