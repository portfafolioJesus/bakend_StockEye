package cl.duoc.stockeye.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.outlined.PhotoCamera
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import cl.duoc.stockeye.data.DetalleTicket
import cl.duoc.stockeye.data.Evidencia
import cl.duoc.stockeye.ui.components.Cargando
import cl.duoc.stockeye.ui.components.ChipEstado
import cl.duoc.stockeye.ui.components.ChipIA
import cl.duoc.stockeye.ui.components.Dato
import cl.duoc.stockeye.ui.components.EspacioV
import cl.duoc.stockeye.ui.components.EstadoVacio
import cl.duoc.stockeye.ui.components.NumeroTicket
import cl.duoc.stockeye.ui.components.Separador
import cl.duoc.stockeye.ui.components.Tarjeta
import cl.duoc.stockeye.ui.components.hora
import cl.duoc.stockeye.ui.components.nombrePrioridad
import cl.duoc.stockeye.ui.components.pct
import cl.duoc.stockeye.ui.repositorio
import cl.duoc.stockeye.ui.theme.Marca
import coil.compose.AsyncImage
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** Detalle del ticket y cierre con foto de verificación. */
@Composable
fun DetalleTicketScreen(numero: String, volver: () -> Unit, fotoCierre: () -> Unit) {
    val repo = repositorio()
    var d by remember { mutableStateOf<DetalleTicket?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var comentarioCierre by remember { mutableStateOf("") }
    var nuevoComentario by remember { mutableStateOf("") }
    var ocupado by remember { mutableStateOf(false) }
    val alcance = rememberCoroutineScope()
    val ciclo = LocalLifecycleOwner.current.lifecycle

    // Al volver de la cámara se recarga; si la foto de cierre aún se analiza, se consulta seguido.
    LaunchedEffect(numero) {
        ciclo.repeatOnLifecycle(Lifecycle.State.RESUMED) {
            while (true) {
                runCatching { repo.ticket(numero) }.onSuccess { d = it; error = null }.onFailure { error = it.message }
                val ultima = d?.evidencias?.lastOrNull { it.tipo == "CIERRE" }
                delay(if (ultima != null && ultima.porcentajeVacio == null) 1000 else 20_000)
            }
        }
    }

    val detalle = d
    Column(Modifier.fillMaxSize().background(Marca.Fondo).statusBarsPadding().navigationBarsPadding().imePadding()) {
        Row(Modifier.fillMaxWidth().background(Color.White).padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = volver) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Volver") }
            NumeroTicket(numero)
            Spacer(Modifier.weight(1f))
            detalle?.let { ChipEstado(it.ticket.estado) }
            Spacer(Modifier.width(8.dp))
        }
        if (detalle == null) {
            if (error != null) EstadoVacio("No se pudo abrir el ticket", error) else Cargando()
            return@Column
        }
        val t = detalle.ticket
        val cierre = detalle.evidencias.lastOrNull { it.tipo == "CIERRE" }
        val enCurso = t.estado == "ASIGNADO" || t.estado == "EN_PROGRESO"
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Tarjeta {
                Text(t.titulo, style = MaterialTheme.typography.titleLarge)
                EspacioV(12)
                Row {
                    Dato("Vacío actual", pct(t.porcentajeVacio), Marca.NaranjoTexto, Modifier.weight(1f))
                    Dato("Prioridad", nombrePrioridad(t.prioridad), modifier = Modifier.weight(1f))
                }
                EspacioV(12)
                Row {
                    Dato("Ubicación", listOfNotNull(t.pasillo?.let { "Pasillo $it" }, t.gondolaCodigo).joinToString(" · ").ifBlank { "—" },
                        modifier = Modifier.weight(1f))
                    Dato("Abierto", "${hora(t.creadoEn)} · ${if (t.origen == "CAMARA") "cámara" else if (t.origen == "MOVIL") "foto móvil" else "manual"}",
                        modifier = Modifier.weight(1f))
                }
                if (!t.productoFaltante.isNullOrBlank()) {
                    EspacioV(12)
                    if (t.enriquecidoIa) ChipIA("Falta: ${t.productoFaltante}") else Text("Falta: ${t.productoFaltante}", fontWeight = FontWeight.SemiBold)
                } else if (detalle.iaPendiente) {
                    EspacioV(12)
                    ChipIA("La IA está identificando el producto…")
                }
                detalle.comentarios.lastOrNull()?.let { c ->
                    EspacioV(12)
                    Separador()
                    EspacioV(12)
                    Text(buildAnnotatedString {
                        withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(c.nombre.substringBefore(" ") + ": ") }
                        append(c.texto)
                    })
                }
            }

            if (detalle.permisos.empezar) {
                Button(
                    onClick = { alcance.launch { ocupado = true; runCatching { repo.empezar(numero) }.onSuccess { d = it }.onFailure { error = it.message }; ocupado = false } },
                    modifier = Modifier.fillMaxWidth().height(52.dp), shape = MaterialTheme.shapes.small,
                    colors = ButtonDefaults.buttonColors(containerColor = Marca.Azul), enabled = !ocupado
                ) { Text("Empezar", fontWeight = FontWeight.Bold) }
            }

            if (enCurso && detalle.permisos.cerrar) Tarjeta {
                Text("Cerrar ticket", style = MaterialTheme.typography.titleLarge)
                EspacioV(12)
                if (cierre != null) FotoVerificacion(cierre, repo.urlAbsoluta(cierre.urlAnotada ?: cierre.url))
                else Text("Después de reponer, toma una foto de la góndola: si queda bajo el umbral, el cierre queda verificado.",
                    color = Marca.Gris)
                EspacioV(12)
                OutlinedButton(onClick = fotoCierre, modifier = Modifier.fillMaxWidth().height(48.dp), shape = MaterialTheme.shapes.small) {
                    Icon(Icons.Outlined.PhotoCamera, null, tint = Marca.Tinta)
                    Spacer(Modifier.width(8.dp))
                    Text(if (cierre == null) "Tomar foto de verificación" else "Repetir foto", color = Marca.Tinta)
                }
                EspacioV(12)
                Text("Comentario de cierre", fontWeight = FontWeight.SemiBold)
                OutlinedTextField(comentarioCierre, { comentarioCierre = it }, Modifier.fillMaxWidth().height(96.dp),
                    placeholder = {
                        Text(if (cierre?.superaUmbral == false) "Ej.: repuesto con 2 cajas de bodega"
                        else "Obligatorio si cierras sin foto bajo el umbral")
                    })
            }

            // Comentarios
            Tarjeta {
                Text("Comentarios · ${detalle.comentarios.size}", style = MaterialTheme.typography.titleMedium)
                detalle.comentarios.forEach { c ->
                    EspacioV(10)
                    Text(buildAnnotatedString {
                        withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(c.nombre) }
                        withStyle(SpanStyle(color = Marca.Gris)) { append(" · ${hora(c.creadoEn)}") }
                    })
                    Text(c.texto)
                }
                if (detalle.permisos.comentar) {
                    EspacioV(10)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        OutlinedTextField(nuevoComentario, { nuevoComentario = it }, Modifier.weight(1f), singleLine = true,
                            placeholder = { Text("Escribe un comentario") })
                        IconButton(
                            onClick = {
                                val texto = nuevoComentario.trim()
                                if (texto.isNotEmpty()) alcance.launch {
                                    runCatching { repo.comentar(numero, texto); repo.ticket(numero) }
                                        .onSuccess { d = it; nuevoComentario = "" }.onFailure { error = it.message }
                                }
                            }
                        ) { Icon(Icons.AutoMirrored.Filled.Send, "Enviar", tint = Marca.Azul) }
                    }
                }
            }
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        }
        if (enCurso && detalle.permisos.cerrar) {
            val analizando = cierre != null && cierre.porcentajeVacio == null
            Box(Modifier.fillMaxWidth().background(Color.White).padding(16.dp)) {
                Button(
                    onClick = {
                        alcance.launch {
                            ocupado = true
                            runCatching { repo.cerrar(numero, comentarioCierre) }
                                .onSuccess { d = it; volver() }
                                .onFailure { error = it.message }
                            ocupado = false
                        }
                    },
                    enabled = !ocupado && !analizando,
                    modifier = Modifier.fillMaxWidth().height(56.dp), shape = MaterialTheme.shapes.small,
                    colors = ButtonDefaults.buttonColors(containerColor = Marca.Verde)
                ) {
                    if (ocupado) CircularProgressIndicator(Modifier.size(20.dp), color = Color.White, strokeWidth = 2.dp)
                    else {
                        Icon(Icons.Filled.Check, null)
                        Spacer(Modifier.width(8.dp))
                        Text(if (analizando) "Analizando la foto…" else "Cerrar ticket", fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }
}

@Composable
private fun FotoVerificacion(e: Evidencia, url: String?) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(width = 120.dp, height = 84.dp).clip(RoundedCornerShape(10.dp)).background(Color(0xFF1E293B)),
            contentAlignment = Alignment.Center) {
            if (url != null) AsyncImage(model = url, contentDescription = "Foto de verificación", contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize())
        }
        Column(Modifier.padding(start = 12.dp)) {
            Text("Foto de verificación · ${hora(e.capturadaEn)}", color = Marca.Gris, style = MaterialTheme.typography.bodySmall)
            when {
                e.porcentajeVacio == null -> Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
                    Text("  Analizando…", color = Marca.Gris)
                }
                e.superaUmbral == false -> {
                    Text("${pct(e.porcentajeVacio)} de vacío", color = Marca.Verde, style = MaterialTheme.typography.titleLarge)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Filled.Check, null, tint = Marca.Verde, modifier = Modifier.size(16.dp))
                        Text(" Bajo el umbral: cierre verificado", color = Marca.Verde, fontWeight = FontWeight.SemiBold)
                    }
                }
                else -> {
                    Text("${pct(e.porcentajeVacio)} de vacío", color = Marca.NaranjoTexto, style = MaterialTheme.typography.titleLarge)
                    Text("Aún sobre el umbral: repón y repite la foto", color = Marca.NaranjoTexto)
                }
            }
        }
    }
}
