package cl.duoc.stockeye.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import cl.duoc.stockeye.data.Alerta
import cl.duoc.stockeye.data.EstadoAlerta
import cl.duoc.stockeye.data.Gondola
import cl.duoc.stockeye.data.Prioridad
import cl.duoc.stockeye.data.Repisa
import cl.duoc.stockeye.data.Semaforo
import cl.duoc.stockeye.ui.theme.ColoresSemaforo
import java.util.Locale

fun colorDe(s: Semaforo): Color = when (s) {
    Semaforo.VERDE -> ColoresSemaforo.Verde
    Semaforo.AMARILLO -> ColoresSemaforo.Amarillo
    Semaforo.ROJO -> ColoresSemaforo.Rojo
    Semaforo.INDETERMINADO -> ColoresSemaforo.Gris
}

// el amarillo normal no se lee como texto
fun colorTextoDe(s: Semaforo): Color =
    if (s == Semaforo.AMARILLO) ColoresSemaforo.AmarilloTexto else colorDe(s)

fun colorPrioridad(p: Prioridad): Color = when (p) {
    Prioridad.ALTA -> ColoresSemaforo.Rojo
    Prioridad.MEDIA -> ColoresSemaforo.Amarillo
    Prioridad.BAJA -> ColoresSemaforo.Gris
}

fun pct(valor: Double): String = String.format(Locale.US, "%.0f", valor)

fun tiempoRelativo(millis: Long): String {
    val min = ((System.currentTimeMillis() - millis) / 60_000L).toInt()
    return when {
        min < 1 -> "recién"
        min < 60 -> "hace $min min"
        min < 1440 -> "hace ${min / 60} h"
        else -> "hace ${min / 1440} d"
    }
}

fun iniciales(nombre: String): String =
    nombre.split(" ").filter { it.isNotBlank() }.take(2).joinToString("") { it.first().uppercase() }

@Composable
fun Punto(color: Color, tamano: Int = 10) {
    Box(
        Modifier
            .size(tamano.dp)
            .clip(CircleShape)
            .background(color)
    )
}

@Composable
fun SemaforoChip(s: Semaforo, modifier: Modifier = Modifier) {
    val c = colorDe(s)
    Surface(color = c.copy(alpha = 0.14f), shape = RoundedCornerShape(50), modifier = modifier) {
        Row(
            Modifier.padding(horizontal = 10.dp, vertical = 5.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Punto(c, 8)
            Spacer(Modifier.width(6.dp))
            Text(
                s.etiqueta,
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.SemiBold,
                color = colorTextoDe(s)
            )
        }
    }
}

@Composable
fun TituloSeccion(texto: String, modifier: Modifier = Modifier) {
    Text(
        texto,
        style = MaterialTheme.typography.titleSmall,
        modifier = modifier.padding(top = 8.dp, bottom = 4.dp)
    )
}

@Composable
fun Tarjeta(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Card(
        modifier = modifier,
        shape = MaterialTheme.shapes.medium,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) { content() }
}

@Composable
fun Avatar(nombre: String, fondo: Color, texto: Color = Color.White, tamano: Int = 36) {
    Box(
        Modifier
            .size(tamano.dp)
            .clip(CircleShape)
            .background(fondo),
        contentAlignment = Alignment.Center
    ) {
        Text(iniciales(nombre), color = texto, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelLarge)
    }
}

@Composable
fun KpiCard(titulo: String, valor: String, color: Color, modifier: Modifier = Modifier) {
    Tarjeta(modifier) {
        Column(Modifier.padding(14.dp)) {
            Text(valor, style = MaterialTheme.typography.headlineMedium, color = color)
            Text(titulo, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
fun IndicadorCircular(valor: Float, color: Color, texto: String, subtexto: String, tamano: Int = 104) {
    Box(Modifier.size(tamano.dp), contentAlignment = Alignment.Center) {
        CircularProgressIndicator(
            progress = { valor.coerceIn(0f, 1f) },
            modifier = Modifier.fillMaxSize(),
            color = color,
            strokeWidth = 10.dp,
            trackColor = MaterialTheme.colorScheme.surfaceVariant
        )
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(texto, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            Text(subtexto, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
fun EstadoVacio(icono: ImageVector, titulo: String, texto: String, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Box(
            Modifier
                .size(64.dp)
                .clip(CircleShape)
                .background(MaterialTheme.colorScheme.secondaryContainer),
            contentAlignment = Alignment.Center
        ) {
            Icon(icono, contentDescription = null, tint = MaterialTheme.colorScheme.secondary, modifier = Modifier.size(32.dp))
        }
        Spacer(Modifier.height(12.dp))
        Text(titulo, style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.Center)
        Text(
            texto,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center
        )
    }
}

// barritas del mapa, una por repisa
@Composable
fun MiniRepisas(repisas: List<Repisa>, semaforoDe: (Repisa) -> Semaforo) {
    Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
        repisas.sortedBy { it.nivel }.forEach { r ->
            val c = colorDe(semaforoDe(r))
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(6.dp)
                    .clip(RoundedCornerShape(3.dp))
                    .background(MaterialTheme.colorScheme.surfaceVariant)
            ) {
                val vacio = r.pctVacio
                val stock = if (vacio == null) 1f else ((100.0 - vacio) / 100.0).coerceIn(0.0, 1.0).toFloat()
                Box(
                    Modifier
                        .fillMaxHeight()
                        .fillMaxWidth(stock)
                        .background(if (vacio == null) c.copy(alpha = 0.35f) else c)
                )
            }
        }
    }
}

// dibujo del mueble: color = producto, gris claro = vacio
@Composable
fun EsquemaGondola(repisas: List<Repisa>, semaforoDe: (Repisa) -> Semaforo) {
    val madera = Color(0xFF5B6475)
    Column(
        Modifier
            .fillMaxWidth()
            .border(3.dp, madera, RoundedCornerShape(10.dp))
            .padding(horizontal = 8.dp, vertical = 6.dp)
    ) {
        repisas.sortedBy { it.nivel }.forEach { r ->
            val s = semaforoDe(r)
            val c = colorDe(s)
            val vacio = r.pctVacio
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(44.dp)
                    .padding(top = 6.dp)
                    .clip(RoundedCornerShape(4.dp))
                    .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f))
            ) {
                if (vacio != null) {
                    val stock = ((100.0 - vacio) / 100.0).coerceIn(0.0, 1.0).toFloat()
                    Box(
                        Modifier
                            .fillMaxHeight()
                            .fillMaxWidth(stock)
                            .background(c.copy(alpha = 0.85f))
                    )
                } else {
                    Box(
                        Modifier
                            .fillMaxSize()
                            .background(c.copy(alpha = 0.25f))
                    )
                }
                Row(
                    Modifier
                        .fillMaxSize()
                        .padding(horizontal = 10.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        "N${r.nivel}",
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.Bold,
                        color = Color.White,
                        modifier = Modifier
                            .clip(RoundedCornerShape(4.dp))
                            .background(Color.Black.copy(alpha = 0.35f))
                            .padding(horizontal = 6.dp, vertical = 2.dp)
                    )
                    Spacer(Modifier.weight(1f))
                    Text(
                        if (vacio == null) "No se ve bien" else "${pct(vacio)}% vacío",
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.SemiBold,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                }
            }
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(4.dp)
                    .background(madera)
            )
        }
    }
}

@Composable
fun AlertaCard(
    alerta: Alerta,
    gondola: Gondola?,
    asignadaA: String?,
    onAbrir: () -> Unit,
    acciones: @Composable RowScope.() -> Unit
) {
    Card(
        onClick = onAbrir,
        modifier = Modifier.fillMaxWidth(),
        shape = MaterialTheme.shapes.medium,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) {
        Row(Modifier.height(IntrinsicSize.Min)) {
            Box(
                Modifier
                    .width(6.dp)
                    .fillMaxHeight()
                    .background(colorPrioridad(alerta.prioridad))
            )
            Column(
                Modifier
                    .weight(1f)
                    .padding(14.dp)
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(
                            gondola?.let { "${it.categoria} (${it.nombre})" } ?: "Góndola ${alerta.gondolaId}",
                            style = MaterialTheme.typography.titleMedium
                        )
                        if (gondola != null) {
                            Text(
                                "Pasillo ${gondola.pasillo}, repisa ${alerta.nivel}",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text(
                            "${pct(alerta.pctVacio)}%",
                            style = MaterialTheme.typography.headlineSmall,
                            color = ColoresSemaforo.Rojo
                        )
                        Text("vacío", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                Spacer(Modifier.height(8.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    EtiquetaPequena("Prioridad ${alerta.prioridad.etiqueta.lowercase()}", colorPrioridad(alerta.prioridad))
                    Spacer(Modifier.width(6.dp))
                    EtiquetaPequena(
                        when (alerta.estado) {
                            EstadoAlerta.NUEVA -> "Nueva"
                            EstadoAlerta.EN_ATENCION -> "En curso"
                            EstadoAlerta.RESUELTA -> "Lista"
                        },
                        MaterialTheme.colorScheme.primary
                    )
                    Spacer(Modifier.weight(1f))
                    Text(
                        tiempoRelativo(alerta.creadaEn),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                Text(
                    if (asignadaA != null) "La tiene $asignadaA" else "Nadie la ha tomado",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 6.dp)
                )
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 10.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    content = acciones
                )
            }
        }
    }
}

@Composable
fun EtiquetaPequena(texto: String, color: Color) {
    Text(
        texto,
        style = MaterialTheme.typography.labelSmall,
        color = color,
        modifier = Modifier
            .clip(RoundedCornerShape(50))
            .background(color.copy(alpha = 0.12f))
            .padding(horizontal = 8.dp, vertical = 3.dp)
    )
}
