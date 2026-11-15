# StockEye · app del reponedor (Android)

Kotlin + Jetpack Compose. Se conecta a la API de StockEye (`/api/v1`) y usa estas piezas:
- CameraX para las fotos de góndola;
- Retrofit con kotlinx-serialization para la API;
- DataStore para la sesión (JWT con renovación automática);
- Coil para las imágenes anotadas;
- Firebase Cloud Messaging para el push;
- el escáner QR de Google Play services.

## Cómo correrla

1. Abrir esta carpeta en Android Studio (File > Open), con el JDK 21.
2. **Push (opcional):** copiar `google-services.json` del proyecto Firebase en `app/`. Sin ese archivo la app compila igual, pero sin push.
3. Levantar el backend (`docker compose up -d` en la raíz del repo).
4. Ejecutarla:
   - **Emulador:** Run. La versión debug apunta a `http://10.0.2.2:8080/`.
   - **Celular real:** en el login, *Configurar servidor* → `http://IP-del-servidor:8080/`.
   - **Release:** `./gradlew assembleRelease -Pstockeye.apiUrl=https://stockeye.tu-empresa.cl/` (solo HTTPS).

Usuario de demo: `dsoto@stockeye.test` / `StockEye2026!` (reponedor del Recinto 1).

## Pantallas (según los mockups)

| Pantalla | Archivo |
|---|---|
| Login (con servidor configurable) | `ui/screens/LoginScreen.kt` |
| Mis tickets: Activos / Cerrados hoy, Empezar, Tomar foto | `ui/screens/MisTicketsScreen.kt` |
| Nueva foto: CameraX, góndola o QR, flash, galería | `ui/screens/CamaraScreen.kt` |
| Resultado del análisis: %, cajas, sugerencia IA, crear ticket | `ui/screens/ResultadoScreen.kt` |
| Detalle y cierre con foto de verificación | `ui/screens/DetalleTicketScreen.kt` |
| Alertas y Perfil | `ui/screens/AlertasScreen.kt`, `PerfilScreen.kt` |

Datos: `data/StockEyeApi.kt` (endpoints), `data/Repositorio.kt` (JWT, renovación, errores), `data/Sesion.kt` (DataStore). Push: `push/StockEyeMessagingService.kt`.

> AGP 8.7.3 con el wrapper Gradle 9.7.1. Si Android Studio reclama incompatibilidad, usa *Tools → AGP Upgrade Assistant* o baja el wrapper a Gradle 8.11.
