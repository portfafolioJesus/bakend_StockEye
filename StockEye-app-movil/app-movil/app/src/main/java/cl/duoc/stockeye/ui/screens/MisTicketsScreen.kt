package cl.duoc.stockeye.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.outlined.PhotoCamera
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import cl.duoc.stockeye.data.Bandeja
import cl.duoc.stockeye.data.Ticket
import cl.duoc.stockeye.data.Usuario
import cl.duoc.stockeye.ui.components.Cargando
import cl.duoc.stockeye.ui.components.ChipEstado
import cl.duoc.stockeye.ui.components.ChipIA
import cl.duoc.stockeye.ui.components.EspacioV
import cl.duoc.stockeye.ui.components.EstadoVacio
import cl.duoc.stockeye.ui.components.NumeroTicket
import cl.duoc.stockeye.ui.components.Prioridad
import cl.duoc.stockeye.ui.components.Tarjeta
import cl.duoc.stockeye.ui.components.hace
import cl.duoc.stockeye.ui.components.hora
import cl.duoc.stockeye.ui.components.pct
import cl.duoc.stockeye.ui.components.tituloCorto
import cl.duoc.stockeye.ui.repositorio
import cl.duoc.stockeye.ui.theme.Marca
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MisTicketsScreen(usuario: Usuario?, abrirTicket: (String) -> Unit, tomarFoto: () -> Unit, abrirAlertas: () -> Unit) {
    val repo = repositorio()
    var pestana by remember { mutableStateOf("activos") }
    var activos by remember { mutableStateOf<Bandeja?>(null) }
    var cerrados by remember { mutableStateOf<Bandeja?>(null) }
    var noLeidas by remember { mutableStateOf(0) }
    var error by remember { mutableStateOf<String?>(null) }
    var refrescando by remember { mutableStateOf(false) }
    val alcance = rememberCoroutineScope()
    val ciclo = LocalLifecycleOwner.current.lifecycle

    suspend fun cargar() {
        runCatching {
            activos = repo.misTickets("activos")
            cerrados = repo.misTickets("cerrados_hoy")
            noLeidas = repo.notificaciones().noLeidas
            error = null
        }.onFailure { error = it.message }
    }

    // Refresca al volver a la pantalla y cada 30 s mientras está visible (el push avisa al instante)
    LaunchedEffect(Unit) {
        ciclo.repeatOnLifecycle(Lifecycle.State.RESUMED) {
            while (true) {
                cargar()
                delay(30_000)
            }
        }
    }

    val recinto = usuario?.recintos?.firstOrNull()
    Column(Modifier.fillMaxSize().background(Marca.Fondo)) {
        // Encabezado
        Row(
            Modifier.fillMaxWidth().background(Color.White).statusBarsPadding().padding(horizontal = 20.dp, vertical = 16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(Modifier.weight(1f)) {
                Text("Mis tickets", style = MaterialTheme.typography.headlineSmall)
                Text(listOfNotNull(usuario?.nombreCompleto, recinto?.nombre).joinToString(" · "), color = Marca.Gris)
            }
            Box {
                IconButton(onClick = abrirAlertas, modifier = Modifier.clip(CircleShape).background(Marca.Fondo)) {
                    Icon(Icons.Filled.Notifications, contentDescription = "Alertas", tint = Marca.Tinta)
                }
                if (noLeidas > 0) Box(Modifier.align(Alignment.TopEnd).padding(8.dp).size(10.dp).clip(CircleShape).background(Marca.Naranjo))
            }
        }
        // Activos / Cerrados hoy
        Row(
            Modifier.padding(16.dp).fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Color(0xFFE5E7EB)).padding(4.dp)
        ) {
            listOf("activos" to "Activos · ${activos?.tickets?.size ?: 0}", "cerrados" to "Cerrados hoy · ${cerrados?.tickets?.size ?: 0}")
                .forEach { (clave, texto) ->
                    Text(
                        texto,
                        Modifier.weight(1f).clip(RoundedCornerShape(10.dp))
                            .background(if (pestana == clave) Color.White else Color.Transparent)
                            .clickable { pestana = clave }.padding(vertical = 10.dp),
                        textAlign = TextAlign.Center,
                        fontWeight = if (pestana == clave) FontWeight.Bold else FontWeight.Normal,
                        color = if (pestana == clave) Marca.Tinta else Marca.Gris
                    )
                }
        }
        val lista = if (pestana == "activos") activos else cerrados
        PullToRefreshBox(
            isRefreshing = refrescando,
            onRefresh = { alcance.launch { refrescando = true; cargar(); refrescando = false } },
            modifier = Modifier.weight(1f)
        ) {
            when {
                lista == null && error == null -> Cargando()
                lista == null -> EstadoVacio("No se pudieron cargar los tickets", error)
                else -> LazyColumn(
                    contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                    modifier = Modifier.fillMaxSize()
                ) {
                    items(lista.tickets, key = { it.id }) { t ->
                        TarjetaTicket(t, abrir = { abrirTicket(t.numero) }, empezar = {
                            alcance.launch {
                                runCatching { repo.empezar(t.numero) }.onFailure { error = it.message }
                                cargar()
                            }
                        })
                    }
                    if (lista.tickets.isEmpty()) item {
                        EstadoVacio(if (pestana == "activos") "No tienes tickets activos" else "Aún no cierras tickets hoy")
                    }
                    if (pestana == "activos") item {
                        Text(
                            "¿Viste un vacío que la cámara no cubre? Saca una foto y se abre un ticket.",
                            Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
                            textAlign = TextAlign.Center, color = Marca.Gris
                        )
                    }
                }
            }
        }
        Button(
            onClick = tomarFoto,
            modifier = Modifier.fillMaxWidth().padding(16.dp).height(56.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Marca.Naranjo),
            shape = MaterialTheme.shapes.small
        ) {
            Icon(Icons.Outlined.PhotoCamera, contentDescription = null)
            Spacer(Modifier.size(10.dp))
            Text("Tomar foto de góndola", style = MaterialTheme.typography.titleMedium)
        }
    }
}

@Composable
private fun TarjetaTicket(t: Ticket, abrir: () -> Unit, empezar: () -> Unit) {
    val nuevo = t.estado == "ASIGNADO"      // recién asignado por el supervisor: destacado y con "Empezar"
    Tarjeta(Modifier.clickable(onClick = abrir), destacada = nuevo) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            NumeroTicket(t.numero)
            Spacer(Modifier.weight(1f))
            ChipEstado(t.estado, nuevo = nuevo)
        }
        EspacioV(8)
        Text(tituloCorto(t.titulo), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        EspacioV(4)
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(
                "${pct(t.porcentajeVacio)} de vacío",
                color = if (t.estado == "CERRADO") Marca.Verde else Marca.NaranjoTexto,
                fontWeight = FontWeight.SemiBold
            )
            Prioridad(t.prioridad)
        }
        if (!t.productoFaltante.isNullOrBlank()) {
            EspacioV(8)
            if (t.enriquecidoIa) ChipIA("Falta: ${t.productoFaltante}") else Text("Falta: ${t.productoFaltante}", color = Marca.Tinta)
        }
        EspacioV(8)
        when (t.estado) {
            "ASIGNADO" -> {
                Text(
                    "Asignado${t.asignadoPorNombre?.let { " por $it" } ?: ""} · ${hace(t.asignadoEn ?: t.creadoEn)}",
                    color = Marca.Gris, style = MaterialTheme.typography.bodyMedium
                )
                EspacioV(12)
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedButton(onClick = abrir, modifier = Modifier.weight(1f).height(48.dp), shape = MaterialTheme.shapes.small) {
                        Text("Ver detalle", color = Marca.Tinta)
                    }
                    Button(
                        onClick = empezar, modifier = Modifier.weight(1f).height(48.dp), shape = MaterialTheme.shapes.small,
                        colors = ButtonDefaults.buttonColors(containerColor = Marca.Azul)
                    ) { Text("Empezar", fontWeight = FontWeight.Bold) }
                }
            }
            "EN_PROGRESO" -> Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "Desde las ${hora(t.asignadoEn ?: t.creadoEn)} · ${t.numComentarios} comentario${if (t.numComentarios == 1) "" else "s"}",
                    color = Marca.Gris, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f)
                )
                Text("Cerrar", color = Marca.Azul, fontWeight = FontWeight.Bold)
                Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, null, tint = Marca.Azul)
            }
            "ABIERTO" -> Text(
                "Reportado ${hace(t.creadoEn)} · esperando que el supervisor lo asigne",
                color = Marca.Gris, style = MaterialTheme.typography.bodyMedium
            )
            else -> Text(
                "Cerrado ${hora(t.cerradoEn)}${if (t.cierreVerificado) " · verificado con foto" else ""}",
                color = Marca.Gris, style = MaterialTheme.typography.bodyMedium
            )
        }
    }
}
