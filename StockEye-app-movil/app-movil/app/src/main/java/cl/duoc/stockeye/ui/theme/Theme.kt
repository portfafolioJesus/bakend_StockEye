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

object Marca {
    val Azul = Color(0xFF12355E)
    val AzulClaro = Color(0xFF1E5AA8)
    val Fondo = Color(0xFFF3F5F9)
}

object ColoresSemaforo {
    val Verde = Color(0xFF2E9E5B)
    val Amarillo = Color(0xFFF2B705)
    val AmarilloTexto = Color(0xFF9A6B00)
    val Rojo = Color(0xFFE5484D)
    val Gris = Color(0xFF8A94A6)
}

private val Esquema = lightColorScheme(
    primary = Marca.AzulClaro,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFDCE8F7),
    onPrimaryContainer = Color(0xFF0B2545),
    secondary = Color(0xFF0F8A7E),
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFD3EFEA),
    onSecondaryContainer = Color(0xFF06302B),
    background = Marca.Fondo,
    onBackground = Color(0xFF161A20),
    surface = Color.White,
    onSurface = Color(0xFF161A20),
    surfaceVariant = Color(0xFFE8ECF2),
    onSurfaceVariant = Color(0xFF5A6270),
    outline = Color(0xFFC9D0DA),
    error = ColoresSemaforo.Rojo
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
    titleLarge = base.titleLarge.copy(fontWeight = FontWeight.SemiBold),
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
