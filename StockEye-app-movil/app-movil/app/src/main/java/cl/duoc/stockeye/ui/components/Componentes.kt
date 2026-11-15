package cl.duoc.stockeye.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import cl.duoc.stockeye.ui.theme.ColoresPrioridad
import cl.duoc.stockeye.ui.theme.Marca
import java.time.Duration
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

// ---------------------------------------------------------------- formato

private val zona: ZoneId = ZoneId.of("America/Santiago")
private val formatoHora = DateTimeFormatter.ofPattern("HH:mm")
private val chile = Locale("es", "CL")

/** 22.1 → "22,1 %" */
fun pct(valor: Double?, decimales: Int = 1): String =
    valor?.let { String.format(chile, "%.${decimales}f %%", it) } ?: "—"

fun fecha(iso: String?): OffsetDateTime? = iso?.let { runCatching { OffsetDateTime.parse(it) }.getOrNull() }

fun hora(iso: String?): String = fecha(iso)?.atZoneSameInstant(zona)?.format(formatoHora) ?: "—"

fun hace(iso: String?): String {
    val f = fecha(iso) ?: return ""
    val min = Duration.between(f, OffsetDateTime.now()).toMinutes()
    return when {
        min < 1 -> "recién"
        min < 60 -> "hace $min min"
        min < 1440 -> "hace ${min / 60} h"
        else -> "hace ${min / 1440} d"
    }
}

fun iniciales(nombre: String): String =
    nombre.split(" ").filter { it.isNotBlank() }.take(2).joinToString("") { it.first().uppercase() }

fun nombrePrioridad(p: String) = when (p) {
    "CRITICA" -> "Crítica"; "ALTA" -> "Alta"; "MEDIA" -> "Media"; else -> "Baja"
}

fun colorPrioridad(p: String): Color = when (p) {
    "CRITICA" -> ColoresPrioridad.Critica
    "ALTA" -> ColoresPrioridad.Alta
    "MEDIA" -> ColoresPrioridad.Media
    else -> ColoresPrioridad.Baja
}

/** "Vacío detectado en P05-G03 · Limpieza" → "Vacío en P05-G03 · Limpieza" (como en las tarjetas del mockup) */
fun tituloCorto(titulo: String) = titulo.replace("Vacío detectado en", "Vacío en")

// ---------------------------------------------------------------- piezas

@Composable
fun Punto(color: Color, tamano: Int = 8) {
    Box(Modifier.size(tamano.dp).clip(CircleShape).background(color))
}

@Composable
fun Etiqueta(texto: String, fondo: Color, color: Color, modifier: Modifier = Modifier) {
    Text(
        texto,
        modifier = modifier.clip(RoundedCornerShape(50)).background(fondo).padding(horizontal = 10.dp, vertical = 4.dp),
        color = color,
        style = MaterialTheme.typography.labelMedium,
        fontWeight = FontWeight.SemiBold
    )
}

@Composable
fun ChipEstado(estado: String, nuevo: Boolean = false) {
    when (estado) {
        "ASIGNADO" -> if (nuevo) Etiqueta("Nuevo · Asignado", Marca.NaranjoSuave, Marca.NaranjoTexto)
        else Etiqueta("Asignado", Color(0xFFEEF2FF), Color(0xFF4338CA))
        "EN_PROGRESO" -> Etiqueta("En progreso", Color(0xFFEDE9FE), Marca.Ia)
        "CERRADO" -> Etiqueta("Cerrado", Marca.VerdeSuave, Marca.Verde)
        "CANCELADO" -> Etiqueta("Cancelado", Color(0xFFF1F5F9), Marca.Gris)
        else -> Etiqueta("Abierto", Color(0xFFF1F5F9), Marca.Tinta)
    }
}

@Composable
fun Prioridad(prioridad: String) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Punto(colorPrioridad(prioridad))
        Text("Prioridad ${nombrePrioridad(prioridad).lowercase()}", style = MaterialTheme.typography.bodyMedium, color = Marca.Gris)
    }
}

/** Chip violeta de la IA: "✧ Falta: Arroz grado 1, 1 kg" */
@Composable
fun ChipIA(texto: String, modifier: Modifier = Modifier) {
    Row(
        modifier.clip(RoundedCornerShape(8.dp)).background(Marca.IaSuave).padding(horizontal = 10.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        Icon(Icons.Filled.AutoAwesome, null, tint = Marca.Ia, modifier = Modifier.size(14.dp))
        Text(texto, color = Marca.Ia, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
fun NumeroTicket(numero: String) {
    Text(numero, fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold, fontSize = 15.sp, color = Marca.Tinta)
}

@Composable
fun Tarjeta(modifier: Modifier = Modifier, destacada: Boolean = false, contenido: @Composable () -> Unit) {
    Card(
        modifier = modifier
            .fillMaxWidth()
            .border(1.dp, if (destacada) Color(0xFFFDBA74) else Marca.Borde, MaterialTheme.shapes.medium),
        shape = MaterialTheme.shapes.medium,
        colors = CardDefaults.cardColors(containerColor = Color.White),
        elevation = CardDefaults.cardElevation(0.dp)
    ) { Column(Modifier.padding(16.dp)) { contenido() } }
}

@Composable
fun Cargando(texto: String = "Cargando…", modifier: Modifier = Modifier.fillMaxSize()) {
    Column(modifier, verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
        CircularProgressIndicator(color = MaterialTheme.colorScheme.primary)
        Spacer(Modifier.height(12.dp))
        Text(texto, color = Marca.Gris)
    }
}

@Composable
fun EstadoVacio(titulo: String, detalle: String? = null, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth().padding(32.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text(titulo, style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.Center)
        detalle?.let {
            Spacer(Modifier.height(6.dp))
            Text(it, color = Marca.Gris, textAlign = TextAlign.Center)
        }
    }
}

@Composable
fun Avatar(nombre: String) {
    Box(
        Modifier.size(36.dp).clip(CircleShape).background(Color(0xFFEEF2FF)),
        contentAlignment = Alignment.Center
    ) { Text(iniciales(nombre), color = Color(0xFF4338CA), fontWeight = FontWeight.Bold, fontSize = 13.sp) }
}

@Composable
fun Dato(titulo: String, valor: String, color: Color = Marca.Tinta, modifier: Modifier = Modifier) {
    Column(modifier) {
        Text(titulo, style = MaterialTheme.typography.bodySmall, color = Marca.Gris)
        Text(valor, style = MaterialTheme.typography.titleMedium, color = color, fontWeight = FontWeight.Bold)
    }
}

@Composable
fun Separador() {
    Box(Modifier.fillMaxWidth().height(1.dp).background(Marca.Borde))
}

@Composable
fun EspacioH(ancho: Int) = Spacer(Modifier.width(ancho.dp))

@Composable
fun EspacioV(alto: Int) = Spacer(Modifier.height(alto.dp))
