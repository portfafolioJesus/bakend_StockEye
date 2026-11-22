package cl.duoc.stockeye.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import cl.duoc.stockeye.data.Notificaciones
import cl.duoc.stockeye.ui.components.Cargando
import cl.duoc.stockeye.ui.components.EstadoVacio
import cl.duoc.stockeye.ui.components.Punto
import cl.duoc.stockeye.ui.components.Tarjeta
import cl.duoc.stockeye.ui.components.hace
import cl.duoc.stockeye.ui.repositorio
import cl.duoc.stockeye.ui.theme.Marca
import kotlinx.coroutines.launch

private val titulos = mapOf(
    "TICKET_ASIGNADO" to "Nuevo ticket asignado",
    "COMENTARIO" to "Nuevo comentario",
    "ALERTA_VACIO" to "Vacío detectado",
    "TICKET_CERRADO" to "Ticket cerrado"
)

@Composable
fun AlertasScreen(abrirTicket: (String) -> Unit) {
    val repo = repositorio()
    var datos by remember { mutableStateOf<Notificaciones?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    val alcance = rememberCoroutineScope()
    LaunchedEffect(Unit) {
        runCatching { repo.notificaciones() }.onSuccess { datos = it }.onFailure { error = it.message }
    }
    Column(Modifier.fillMaxSize().background(Marca.Fondo)) {
        Column(Modifier.fillMaxWidth().background(Color.White).statusBarsPadding().padding(20.dp)) {
            Text("Alertas", style = MaterialTheme.typography.headlineSmall)
            Text("${datos?.noLeidas ?: 0} sin leer", color = Marca.Gris)
        }
        val d = datos
        when {
            d == null && error != null -> EstadoVacio("No se pudieron cargar las alertas", error)
            d == null -> Cargando()
            d.notificaciones.isEmpty() -> EstadoVacio("Sin alertas", "Aquí verás los tickets que te asignen y los comentarios.")
            else -> LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                items(d.notificaciones, key = { it.id }) { n ->
                    Tarjeta(Modifier.clickable {
                        alcance.launch {
                            if (!n.leida) runCatching { repo.marcarLeida(n.id) }
                            n.ticketNumero?.let(abrirTicket)
                        }
                    }) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            if (!n.leida) {
                                Punto(Marca.Naranjo)
                                Text(" ", Modifier.padding(end = 4.dp))
                            }
                            Text(titulos[n.tipo] ?: "Aviso", fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                            Text(hace(n.creadaEn), color = Marca.Gris, style = MaterialTheme.typography.bodySmall)
                        }
                        Text(n.mensaje, color = if (n.leida) Marca.Gris else Marca.Tinta)
                    }
                }
            }
        }
    }
}
