# StockEye - app móvil

App Android (Kotlin + Jetpack Compose). Por ahora funciona con datos de prueba, todavía no está conectada al backend.

## Cómo correrla

1. Abrir esta carpeta en Android Studio (File > Open).
2. Esperar el Gradle sync. Si pide JDK, usar el 21.
3. Prender un emulador y darle a Run.

Usuarios (clave `1234`): `reponedor`, `reponedor2`, `supervisor`, `admin`.

## Estructura

- `data/` modelos y datos de prueba (`DemoRepository`)
- `ui/StockEyeViewModel.kt` estado y acciones
- `ui/StockEyeApp.kt` navegación según el rol
- `ui/screens/` pantallas (login, alertas, mapa, detalle, resumen, ajustes)
- `ui/components/` cosas reutilizables
- `ui/theme/` colores

## Pendiente

- Conectar a la API (crear un `ApiRepository` que implemente `StockEyeRepository`)
- Mostrar la foto analizada
- Notificaciones push
