package cl.duoc.stockeye.ui.theme

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

// Colores de los mockups de StockEye
object Marca {
    val Naranjo = Color(0xFFEA580C)          // botón "Tomar foto", vacíos
    val NaranjoSuave = Color(0xFFFFF4EC)
    val NaranjoTexto = Color(0xFFC2410C)
    val Azul = Color(0xFF1D3FD1)             // acción principal
    val Tinta = Color(0xFF0F172A)
    val Fondo = Color(0xFFF3F4F6)
    val Borde = Color(0xFFE2E8F0)
    val Gris = Color(0xFF64748B)
    val Ia = Color(0xFF6D28D9)
    val IaSuave = Color(0xFFF3EFFF)
    val Verde = Color(0xFF15803D)
    val VerdeSuave = Color(0xFFF0FDF4)
    val Camara = Color(0xFF0B1220)          // fondo oscuro de la pantalla de cámara
}

object ColoresPrioridad {
    val Baja = Color(0xFF94A3B8)
    val Media = Color(0xFFF59E0B)
    val Alta = Color(0xFFDC2626)
    val Critica = Color(0xFF7F1D1D)
}

private val Esquema = lightColorScheme(
    primary = Marca.Azul,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFE0E7FF),
    onPrimaryContainer = Color(0xFF1E1B4B),
    secondary = Marca.Naranjo,
    onSecondary = Color.White,
    background = Marca.Fondo,
    onBackground = Marca.Tinta,
    surface = Color.White,
    onSurface = Marca.Tinta,
    surfaceVariant = Color(0xFFF1F5F9),
    onSurfaceVariant = Marca.Gris,
    outline = Color(0xFFCBD5E1),
    error = Color(0xFFB91C1C)
)

private val Formas = Shapes(
    extraSmall = RoundedCornerShape(6.dp),
    small = RoundedCornerShape(10.dp),
    medium = RoundedCornerShape(16.dp),
    large = RoundedCornerShape(20.dp),
    extraLarge = RoundedCornerShape(28.dp)
)

private val base = Typography()
private val Tipografia = base.copy(
    headlineMedium = base.headlineMedium.copy(fontWeight = FontWeight.Bold),
    headlineSmall = base.headlineSmall.copy(fontWeight = FontWeight.Bold),
    titleLarge = base.titleLarge.copy(fontWeight = FontWeight.Bold),
    titleMedium = base.titleMedium.copy(fontWeight = FontWeight.SemiBold),
    labelSmall = TextStyle(fontSize = 11.sp, fontWeight = FontWeight.Medium, letterSpacing = 0.4.sp)
)

@Composable
fun StockEyeTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = Esquema,
        typography = Tipografia,
        shapes = Formas,
        content = content
    )
}
