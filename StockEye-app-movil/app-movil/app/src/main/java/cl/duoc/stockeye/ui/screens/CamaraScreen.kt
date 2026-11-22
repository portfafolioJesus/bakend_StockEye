package cl.duoc.stockeye.ui.screens

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.util.Size
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.FlashOff
import androidx.compose.material.icons.filled.FlashOn
import androidx.compose.material.icons.filled.FlipCameraAndroid
import androidx.compose.material.icons.filled.PhotoLibrary
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import cl.duoc.stockeye.data.Gondola
import cl.duoc.stockeye.data.Recinto
import cl.duoc.stockeye.ui.components.EspacioV
import cl.duoc.stockeye.ui.repositorio
import cl.duoc.stockeye.ui.theme.Marca
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

private const val MAX_BYTES = 14 * 1024 * 1024

/**
 * Foto de góndola (nueva o de verificación de cierre). La foto se sube a la
 * API, que la guarda en la carpeta del recinto y la deja en cola para el modelo.
 */
@Composable
fun CamaraScreen(recinto: Recinto?, numeroCierre: String?, cerrar: () -> Unit, alSubir: (Long) -> Unit) {
    val contexto = LocalContext.current
    val ciclo = LocalLifecycleOwner.current
    val repo = repositorio()
    val alcance = rememberCoroutineScope()

    var permiso by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(contexto, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED)
    }
    val pedirPermiso = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { permiso = it }
    LaunchedEffect(Unit) { if (!permiso) pedirPermiso.launch(Manifest.permission.CAMERA) }

    var gondolas by remember { mutableStateOf<List<Gondola>>(emptyList()) }
    var gondola by remember { mutableStateOf<Gondola?>(null) }
    var menu by remember { mutableStateOf(false) }
    var flash by remember { mutableStateOf(false) }
    var trasera by remember { mutableStateOf(true) }
    var subiendo by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(recinto?.id) {
        if (recinto != null && numeroCierre == null) {
            runCatching { repo.gondolas(recinto.id) }.onSuccess { gondolas = it }.onFailure { error = it.message }
        }
    }

    val captura = remember {
        ImageCapture.Builder()
            .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
            // ~2,7 MP bastan: el modelo trabaja a ≤740 mil píxeles y la subida es rápida en 4G
            .setResolutionSelector(
                ResolutionSelector.Builder().setResolutionStrategy(
                    ResolutionStrategy(Size(1920, 1440), ResolutionStrategy.FALLBACK_RULE_CLOSEST_LOWER_THEN_HIGHER)
                ).build()
            )
            .build()
    }
    LaunchedEffect(flash) { captura.flashMode = if (flash) ImageCapture.FLASH_MODE_ON else ImageCapture.FLASH_MODE_OFF }

    fun subir(bytes: ByteArray) {
        if (numeroCierre == null && gondola == null) {
            error = "Elige la góndola antes de tomar la foto"
            return
        }
        if (bytes.size > MAX_BYTES) {
            error = "La foto es muy grande (máx. 14 MB)"
            return
        }
        subiendo = true
        error = null
        alcance.launch {
            runCatching {
                if (numeroCierre != null) repo.subirFotoCierre(numeroCierre, bytes) else repo.subirFoto(gondola!!.id, bytes)
            }.onSuccess { alSubir(it) }.onFailure { error = it.message }
            subiendo = false
        }
    }

    val galeria = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri: Uri? ->
        if (uri != null) alcance.launch {
            val bytes = withContext(Dispatchers.IO) { contexto.contentResolver.openInputStream(uri)?.use { it.readBytes() } }
            if (bytes != null) subir(bytes) else error = "No se pudo leer la imagen"
        }
    }

    Column(Modifier.fillMaxSize().background(Marca.Camara).systemBarsPadding().padding(16.dp)) {
        // Barra superior
        Row(verticalAlignment = Alignment.CenterVertically) {
            BotonRedondo(Icons.Filled.Close, "Cerrar", onClick = cerrar)
            Text(
                if (numeroCierre != null) "Foto de verificación" else "Nueva foto",
                Modifier.weight(1f), color = Color.White, textAlign = TextAlign.Center,
                style = MaterialTheme.typography.titleMedium
            )
            BotonRedondo(if (flash) Icons.Filled.FlashOn else Icons.Filled.FlashOff, "Flash", onClick = { flash = !flash })
        }
        EspacioV(12)
        if (numeroCierre == null) {
            Text("Góndola · ${recinto?.nombre ?: ""}", color = Color(0xFFCBD5E1), style = MaterialTheme.typography.bodySmall)
            EspacioV(6)
            Box {
                Row(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Color(0xFF1E293B))
                        .border(1.dp, Color(0xFF334155), RoundedCornerShape(12.dp))
                        .clickable { menu = true }.padding(horizontal = 16.dp, vertical = 14.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(gondola?.etiqueta ?: "Elige la góndola", Modifier.weight(1f), color = Color.White, fontWeight = FontWeight.Bold)
                    Icon(Icons.Filled.ArrowDropDown, null, tint = Color.White)
                    IconButton(onClick = { escanearQr(contexto, gondolas, { gondola = it }, { error = it }) }) {
                        Icon(Icons.Filled.QrCodeScanner, contentDescription = "Escanear QR de la góndola", tint = Color.White)
                    }
                }
                DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                    gondolas.forEach { g ->
                        DropdownMenuItem(text = { Text(g.etiqueta) }, onClick = { gondola = g; menu = false })
                    }
                }
            }
        } else {
            Text("Ticket $numeroCierre · repón y fotografía la misma góndola", color = Color(0xFFCBD5E1), textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth())
        }

        // Visor con guías
        Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
            if (permiso) {
                Box(Modifier.fillMaxWidth().aspectRatio(4f / 3f).clip(RoundedCornerShape(8.dp))) {
                    VistaCamara(captura, trasera, ciclo)
                    GuiasEsquinas(Modifier.fillMaxSize())
                }
            } else {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("StockEye necesita la cámara para fotografiar las góndolas.", color = Color.White, textAlign = TextAlign.Center)
                    EspacioV(12)
                    Button(onClick = { pedirPermiso.launch(Manifest.permission.CAMERA) }) { Text("Permitir cámara") }
                }
            }
            if (subiendo) {
                Column(
                    Modifier.fillMaxSize().background(Color(0xAA000000)),
                    verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    CircularProgressIndicator(color = Color.White)
                    EspacioV(12)
                    Text("Subiendo foto…", color = Color.White)
                }
            }
        }
        Text("Encuadra la góndola completa, de frente y sin personas", color = Color.White, textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth())
        Text(
            "Se guarda en ${recinto?.carpetaImagenes ?: "la carpeta del recinto"} y la analiza el modelo",
            color = Color(0xFF94A3B8), textAlign = TextAlign.Center, style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.fillMaxWidth()
        )
        error?.let {
            EspacioV(8)
            Text(it, color = Color(0xFFFCA5A5), textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
        }
        EspacioV(16)
        // Galería · disparador · cambiar cámara
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly, verticalAlignment = Alignment.CenterVertically) {
            BotonRedondo(Icons.Filled.PhotoLibrary, "Elegir de la galería", cuadrado = true) {
                galeria.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
            }
            Box(
                Modifier.size(80.dp).clip(CircleShape).border(BorderStroke(4.dp, Color.White), CircleShape).padding(8.dp)
                    .clip(CircleShape).background(Color.White)
                    .clickable(enabled = permiso && !subiendo) { tomarFoto(contexto, captura, ::subir) { error = it } }
            )
            BotonRedondo(Icons.Filled.FlipCameraAndroid, "Cambiar cámara") { trasera = !trasera }
        }
    }
}

@Composable
private fun VistaCamara(captura: ImageCapture, trasera: Boolean, ciclo: androidx.lifecycle.LifecycleOwner) {
    val contexto = LocalContext.current
    val vista = remember { PreviewView(contexto).apply { scaleType = PreviewView.ScaleType.FILL_CENTER } }
    DisposableEffect(trasera) {
        val futuro = ProcessCameraProvider.getInstance(contexto)
        futuro.addListener({
            val proveedor = futuro.get()
            val vistaPrevia = Preview.Builder().build().also { it.setSurfaceProvider(vista.surfaceProvider) }
            val selector = if (trasera) CameraSelector.DEFAULT_BACK_CAMERA else CameraSelector.DEFAULT_FRONT_CAMERA
            proveedor.unbindAll()
            runCatching { proveedor.bindToLifecycle(ciclo, selector, vistaPrevia, captura) }
        }, ContextCompat.getMainExecutor(contexto))
        onDispose { runCatching { futuro.get().unbindAll() } }
    }
    AndroidView(factory = { vista }, modifier = Modifier.fillMaxSize())
}

@Composable
private fun GuiasEsquinas(modifier: Modifier) {
    Canvas(modifier) {
        val largo = size.minDimension * 0.12f
        val grosor = 4.dp.toPx()
        val esquinas = listOf(
            Offset(0f, 0f) to Offset(1f, 1f), Offset(size.width, 0f) to Offset(-1f, 1f),
            Offset(0f, size.height) to Offset(1f, -1f), Offset(size.width, size.height) to Offset(-1f, -1f)
        )
        esquinas.forEach { (p, d) ->
            drawLine(Color.White, p, Offset(p.x + d.x * largo, p.y), grosor, StrokeCap.Round)
            drawLine(Color.White, p, Offset(p.x, p.y + d.y * largo), grosor, StrokeCap.Round)
        }
    }
}

@Composable
private fun BotonRedondo(icono: androidx.compose.ui.graphics.vector.ImageVector, descripcion: String, cuadrado: Boolean = false, onClick: () -> Unit) {
    val forma = if (cuadrado) RoundedCornerShape(12.dp) else CircleShape
    Box(
        Modifier.size(52.dp).clip(forma).background(Color(0xFF1E293B)).border(1.dp, Color(0xFF334155), forma).clickable(onClick = onClick),
        contentAlignment = Alignment.Center
    ) { Icon(icono, contentDescription = descripcion, tint = Color.White) }
}

private fun tomarFoto(contexto: Context, captura: ImageCapture, alListo: (ByteArray) -> Unit, alError: (String) -> Unit) {
    val archivo = File(contexto.cacheDir, "foto_${System.currentTimeMillis()}.jpg")
    captura.takePicture(
        ImageCapture.OutputFileOptions.Builder(archivo).build(),
        ContextCompat.getMainExecutor(contexto),
        object : ImageCapture.OnImageSavedCallback {
            override fun onImageSaved(resultado: ImageCapture.OutputFileResults) {
                val bytes = archivo.readBytes()
                archivo.delete()
                alListo(bytes)    // la API rota la foto según su EXIF
            }

            override fun onError(e: ImageCaptureException) = alError("No se pudo tomar la foto: ${e.message}")
        }
    )
}

/** Escáner QR de Google (no requiere permiso de cámara). El QR trae el código de la góndola. */
private fun escanearQr(contexto: Context, gondolas: List<Gondola>, alEncontrar: (Gondola) -> Unit, alError: (String) -> Unit) {
    GmsBarcodeScanning.getClient(contexto).startScan()
        .addOnSuccessListener { codigo ->
            val texto = codigo.rawValue?.uppercase() ?: ""
            val g = gondolas.firstOrNull { texto == it.codigo.uppercase() || texto.endsWith("/" + it.codigo.uppercase()) }
            if (g != null) alEncontrar(g) else alError("El QR ($texto) no corresponde a una góndola de este recinto")
        }
        .addOnFailureListener { alError("No se pudo leer el QR") }
}
