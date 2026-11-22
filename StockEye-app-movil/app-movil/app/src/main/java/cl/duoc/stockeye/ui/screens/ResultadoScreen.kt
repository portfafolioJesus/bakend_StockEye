package cl.duoc.stockeye.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.AutoAwesome
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import cl.duoc.stockeye.data.Imagen
import cl.duoc.stockeye.ui.components.EspacioV
import cl.duoc.stockeye.ui.components.pct
import cl.duoc.stockeye.ui.repositorio
import cl.duoc.stockeye.ui.theme.Marca
import coil.compose.AsyncImage
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** Resultado del modelo para una foto nueva. El ticket se crea solo si el reponedor lo confirma. */
@Composable
fun ResultadoScreen(imagenId: Long, umbralRecinto: Double, volver: () -> Unit, alCrear: (String) -> Unit) {
    val repo = repositorio()
    var imagen by remember { mutableStateOf<Imagen?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var titulo by remember { mutableStateOf("") }
    var producto by remember { mutableStateOf("") }
    var comentario by remember { mutableStateOf("") }
    var creando by remember { mutableStateOf(false) }
    val alcance = rememberCoroutineScope()

    // Consulta hasta que el worker termine (≈2 s) y luego, un rato, la sugerencia de la IA
    LaunchedEffect(imagenId) {
        var intentos = 0
        while (intentos < 60) {
            runCatching { repo.imagen(imagenId) }
                .onSuccess {
                    imagen = it
                    if (titulo.isBlank() && it.gondola != null) {
                        titulo = "Vacío detectado en ${it.gondola.codigo}${it.gondola.categoria?.let { c -> " · $c" } ?: ""}"
                    }
                }
                .onFailure { error = it.message }
            val i = imagen
            val listo = i != null && !i.enAnalisis && i.ia.estado != "pendiente"
            if (listo || i?.estado == "ERROR") break
            intentos++
            delay(if (i?.enAnalisis != false) 700 else 1500)
        }
    }

    Column(Modifier.fillMaxSize().background(Marca.Fondo).statusBarsPadding().navigationBarsPadding().imePadding()) {
        Row(Modifier.fillMaxWidth().background(Color.White).padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = volver) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Volver") }
            Text("Resultado del análisis", style = MaterialTheme.typography.titleLarge)
        }
        val i = imagen
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(16.dp)) {
            Box(
                Modifier.fillMaxWidth().aspectRatio(4f / 3f).clip(RoundedCornerShape(16.dp)).background(Color(0xFF1E293B)),
                contentAlignment = Alignment.Center
            ) {
                val url = repo.urlAbsoluta(i?.urlAnotada ?: i?.url)
                if (url != null) AsyncImage(model = url, contentDescription = "Foto con los vacíos marcados",
                    contentScale = ContentScale.Fit, modifier = Modifier.fillMaxSize())
                if (i == null || i.enAnalisis) Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    CircularProgressIndicator(color = Color.White)
                    EspacioV(8)
                    Text("Analizando con el modelo…", color = Color.White)
                }
            }
            EspacioV(16)
            val p = i?.prediccion
            when {
                i?.estado == "ERROR" -> Text("No se pudo analizar la foto: ${i?.error ?: ""}", color = MaterialTheme.colorScheme.error)
                p != null -> {
                    val supera = p.superaUmbral
                    Row(
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp))
                            .background(if (supera) Marca.NaranjoSuave else Marca.VerdeSuave)
                            .border(1.dp, if (supera) Color(0xFFFDBA74) else Color(0xFF86EFAC), RoundedCornerShape(16.dp))
                            .padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(pct(p.porcentajeVacio), fontSize = 36.sp, fontWeight = FontWeight.Bold,
                            color = if (supera) Marca.NaranjoTexto else Marca.Verde, modifier = Modifier.padding(end = 16.dp))
                        Column {
                            Text(
                                if (supera) "Supera el umbral de ${pct(p.umbralAplicado, 0)}" else "Bajo el umbral de ${pct(p.umbralAplicado, 0)}",
                                fontWeight = FontWeight.Bold, color = if (supera) Marca.NaranjoTexto else Marca.Verde
                            )
                            Text(
                                "${p.numVacios} espacio${if (p.numVacios == 1) "" else "s"} vacío${if (p.numVacios == 1) "" else "s"}" +
                                    (i?.gondola?.let { " · ${it.codigo}${it.categoria?.let { c -> " · $c" } ?: ""}" } ?: ""),
                                color = if (supera) Marca.NaranjoTexto else Marca.Verde
                            )
                        }
                    }
                    if (!supera) {
                        EspacioV(8)
                        Text("Bajo el umbral del recinto (${pct(umbralRecinto, 0)}): puedes descartar o reportarlo igual.", color = Marca.Gris)
                    }
                }
            }
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            if (p != null) {
                EspacioV(16)
                Text("Título", fontWeight = FontWeight.SemiBold)
                OutlinedTextField(titulo, { titulo = it }, Modifier.fillMaxWidth(), singleLine = true)
                EspacioV(12)
                Text("Producto faltante", fontWeight = FontWeight.SemiBold)
                OutlinedTextField(producto, { producto = it }, Modifier.fillMaxWidth(), singleLine = true,
                    placeholder = { Text("¿Qué producto falta?") })
                SugerenciaIA(i) { producto = it }
                EspacioV(12)
                Text("Comentario", fontWeight = FontWeight.SemiBold)
                OutlinedTextField(comentario, { comentario = it }, Modifier.fillMaxWidth().height(96.dp),
                    placeholder = { Text("Ej.: quedan 2 cajas en bodega") })
            }
        }
        Row(Modifier.fillMaxWidth().background(Color.White).padding(16.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedButton(onClick = volver, modifier = Modifier.weight(1f).height(52.dp), shape = MaterialTheme.shapes.small) {
                Text("Descartar", color = Marca.Tinta)
            }
            Button(
                onClick = {
                    creando = true
                    alcance.launch {
                        runCatching { repo.crearTicket(imagenId, titulo, producto, comentario) }
                            .onSuccess { alCrear(it.ticket.numero) }
                            .onFailure { error = it.message }
                        creando = false
                    }
                },
                enabled = i?.prediccion != null && !creando,
                modifier = Modifier.weight(2f).height(52.dp), shape = MaterialTheme.shapes.small,
                colors = ButtonDefaults.buttonColors(containerColor = Marca.Azul)
            ) {
                if (creando) CircularProgressIndicator(Modifier.size(20.dp), color = Color.White, strokeWidth = 2.dp)
                else Text("Crear ticket", fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
private fun SugerenciaIA(imagen: Imagen?, usar: (String) -> Unit) {
    val ia = imagen?.ia ?: return
    val mejor = ia.productos.firstOrNull()
    if (ia.estado == "pendiente" || mejor != null) {
        EspacioV(8)
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Marca.IaSuave).padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(Icons.Filled.AutoAwesome, null, tint = Marca.Ia, modifier = Modifier.size(16.dp))
            Text(
                if (mejor != null) "IA: ${mejor.producto}${mejor.confianza?.let { " · ${(it * 100).toInt()} %" } ?: ""}"
                else "La IA está identificando el producto…",
                color = Marca.Ia, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f).padding(start = 8.dp)
            )
            if (mejor != null) Button(
                onClick = { usar(mejor.producto) }, shape = MaterialTheme.shapes.small,
                colors = ButtonDefaults.buttonColors(containerColor = Marca.Ia)
            ) { Text("Usar") }
        }
    }
}
