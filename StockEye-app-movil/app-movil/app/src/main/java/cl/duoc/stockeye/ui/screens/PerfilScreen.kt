package cl.duoc.stockeye.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import cl.duoc.stockeye.data.Alerta
import cl.duoc.stockeye.data.EstadoAlerta
import cl.duoc.stockeye.data.Rol
import cl.duoc.stockeye.data.Umbrales
import cl.duoc.stockeye.data.Usuario
import cl.duoc.stockeye.ui.StockEyeViewModel
import cl.duoc.stockeye.ui.components.Avatar
import cl.duoc.stockeye.ui.components.Tarjeta
import cl.duoc.stockeye.ui.components.TituloSeccion
import cl.duoc.stockeye.ui.components.tiempoRelativo
import cl.duoc.stockeye.ui.theme.ColoresSemaforo
import cl.duoc.stockeye.ui.theme.Marca
import kotlin.math.roundToInt

// el mismo perfil para todos, cambia lo que se muestra segun el rol
@Composable
fun PerfilScreen(vm: StockEyeViewModel, usuario: Usuario, onAbrirGondola: (Int) -> Unit) {
    val esReponedor = usuario.rol == Rol.REPONEDOR

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Cabecera(usuario)

        if (esReponedor) {
            DiaReponedor(vm, usuario, onAbrirGondola)
        } else {
            DiaSupervisor(vm)
            TituloSeccion("Tienda")
            TarjetaSemaforo(vm)
            if (usuario.rol == Rol.ADMINISTRADOR) {
                Tarjeta(Modifier.fillMaxWidth()) {
                    Fila("Modelo", vm.gondolas.firstOrNull()?.versionModelo ?: "-")
                }
            }
        }

        TituloSeccion("Cuenta")
        Cuenta(vm, usuario, onAbrirGondola)

        Spacer(Modifier.height(8.dp))
        OutlinedButton(
            onClick = { vm.cerrarSesion() },
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.outlinedButtonColors(contentColor = ColoresSemaforo.Rojo)
        ) { Text("Cerrar sesión") }
        Spacer(Modifier.height(8.dp))
    }
}

@Composable
private fun Cabecera(usuario: Usuario) {
    Tarjeta(Modifier.fillMaxWidth()) {
        Column(
            Modifier
                .fillMaxWidth()
                .padding(vertical = 20.dp, horizontal = 16.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Avatar(usuario.nombre, Marca.Azul, Color.White, 64)
            Spacer(Modifier.height(10.dp))
            Text("Hola, ${usuario.nombre.substringBefore(" ")}", style = MaterialTheme.typography.titleLarge)
            Text(
                usuario.rol.etiqueta,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            if (usuario.zona != null) {
                Spacer(Modifier.height(8.dp))
                Text(
                    "Tu zona: ${usuario.zona}",
                    style = MaterialTheme.typography.labelLarge,
                    color = Marca.AzulClaro,
                    modifier = Modifier
                        .clip(RoundedCornerShape(50))
                        .background(MaterialTheme.colorScheme.primaryContainer)
                        .padding(horizontal = 12.dp, vertical = 4.dp)
                )
            }
        }
    }
}

@Composable
private fun DiaReponedor(vm: StockEyeViewModel, usuario: Usuario, onAbrirGondola: (Int) -> Unit) {
    val mias = vm.alertas.filter { it.asignadaA == usuario.id }
    val enCurso = mias.filter { it.estado == EstadoAlerta.EN_ATENCION }
    val listas = mias.count { it.estado == EstadoAlerta.RESUELTA }
    val porTomar = vm.alertas.count { it.estado == EstadoAlerta.NUEVA && it.asignadaA == null }

    TituloSeccion("Tu día")
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        CajaNumero("Listas", "$listas", ColoresSemaforo.Verde, Modifier.weight(1f))
        CajaNumero("En curso", "${enCurso.size}", Marca.AzulClaro, Modifier.weight(1f))
        CajaNumero("Por tomar", "$porTomar", ColoresSemaforo.Rojo, Modifier.weight(1f))
    }

    TituloSeccion("Lo que tienes ahora")
    Tarjeta(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) {
            if (enCurso.isEmpty()) {
                Text(
                    "Nada por ahora. Puedes tomar una alerta nueva.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(vertical = 12.dp)
                )
            }
            enCurso.forEachIndexed { i, a ->
                if (i > 0) HorizontalDivider()
                val g = vm.gondola(a.gondolaId)
                Row(
                    Modifier
                        .fillMaxWidth()
                        .clickable { onAbrirGondola(a.gondolaId) }
                        .padding(vertical = 12.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(g?.categoria ?: "Góndola", style = MaterialTheme.typography.bodyLarge)
                        Text(
                            "Pasillo ${g?.pasillo ?: "-"}, repisa ${a.nivel}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    Text("Ver", color = Marca.AzulClaro, style = MaterialTheme.typography.labelLarge)
                }
            }
        }
    }
}

@Composable
private fun DiaSupervisor(vm: StockEyeViewModel) {
    val pendientes = vm.alertasAbiertas()
    val sinNadie = pendientes.count { it.asignadaA == null }
    val listas = vm.alertas.count { it.estado == EstadoAlerta.RESUELTA }

    TituloSeccion("Hoy en la tienda")
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        CajaNumero("Pendientes", "${pendientes.size}", Marca.AzulClaro, Modifier.weight(1f))
        CajaNumero("Sin nadie", "$sinNadie", ColoresSemaforo.Rojo, Modifier.weight(1f))
        CajaNumero("Listas", "$listas", ColoresSemaforo.Verde, Modifier.weight(1f))
    }

    TituloSeccion("Tu equipo")
    Tarjeta(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) {
            vm.reponedores().forEachIndexed { i, r ->
                if (i > 0) HorizontalDivider()
                val enCurso = pendientes.count { it.asignadaA == r.id }
                Row(Modifier.padding(vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                    Avatar(r.nombre, MaterialTheme.colorScheme.primaryContainer, Marca.AzulClaro, 36)
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(r.nombre, style = MaterialTheme.typography.bodyLarge)
                        Text(
                            r.zona ?: "",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    Text(
                        if (enCurso == 0) "Libre" else "$enCurso en curso",
                        style = MaterialTheme.typography.labelLarge,
                        color = if (enCurso == 0) ColoresSemaforo.Verde else Marca.AzulClaro
                    )
                }
            }
        }
    }
}

// muestra el 70/30 y al apretar Cambiar se abren los sliders
@Composable
private fun TarjetaSemaforo(vm: StockEyeViewModel) {
    var abierto by rememberSaveable { mutableStateOf(false) }
    var verde by remember(vm.umbrales) { mutableFloatStateOf(vm.umbrales.stockVerde.toFloat()) }
    var rojo by remember(vm.umbrales) { mutableFloatStateOf(vm.umbrales.stockRojo.toFloat()) }

    Tarjeta(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Semáforo", style = MaterialTheme.typography.bodyLarge)
                    Text(
                        "Verde desde ${vm.umbrales.stockVerde}%, rojo bajo ${vm.umbrales.stockRojo}%",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                TextButton(onClick = { abierto = !abierto }) { Text(if (abierto) "Cerrar" else "Cambiar") }
            }

            if (abierto) {
                Spacer(Modifier.height(12.dp))
                Row(
                    Modifier
                        .fillMaxWidth()
                        .height(12.dp)
                        .clip(RoundedCornerShape(6.dp))
                ) {
                    Box(Modifier.weight(rojo.coerceAtLeast(1f)).fillMaxHeight().background(ColoresSemaforo.Rojo))
                    Box(Modifier.weight((verde - rojo).coerceAtLeast(1f)).fillMaxHeight().background(ColoresSemaforo.Amarillo))
                    Box(Modifier.weight((100f - verde).coerceAtLeast(1f)).fillMaxHeight().background(ColoresSemaforo.Verde))
                }
                Spacer(Modifier.height(12.dp))
                Text("Verde desde ${verde.roundToInt()}%", color = ColoresSemaforo.Verde)
                Slider(
                    value = verde,
                    onValueChange = {
                        verde = it.roundToInt().toFloat()
                        if (rojo > verde - 5f) rojo = verde - 5f
                    },
                    valueRange = 40f..95f
                )
                Text("Rojo bajo ${rojo.roundToInt()}%", color = ColoresSemaforo.Rojo)
                Slider(
                    value = rojo,
                    onValueChange = {
                        rojo = it.roundToInt().toFloat()
                        if (verde < rojo + 5f) verde = rojo + 5f
                    },
                    valueRange = 5f..60f
                )
                Text(
                    "Si una repisa queda en rojo se crea una alerta.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Row(Modifier.padding(top = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { verde = 70f; rojo = 30f }, modifier = Modifier.weight(1f)) {
                        Text("Volver a 70/30")
                    }
                    Button(
                        onClick = {
                            vm.guardarUmbrales(Umbrales(verde.roundToInt(), rojo.roundToInt()))
                            abierto = false
                        },
                        modifier = Modifier.weight(1f)
                    ) { Text("Guardar") }
                }
            }
        }
    }
}

@Composable
private fun Cuenta(vm: StockEyeViewModel, usuario: Usuario, onAbrirGondola: (Int) -> Unit) {
    var editarIp by rememberSaveable { mutableStateOf(false) }
    var verTareas by rememberSaveable { mutableStateOf(false) }
    val esReponedor = usuario.rol == Rol.REPONEDOR
    // reponedor: sus tareas. supervisor: todo lo que esta abierto
    val tareas = if (esReponedor) vm.alertas.filter { it.asignadaA == usuario.id } else vm.alertasAbiertas()
    val ordenadas = tareas.sortedWith(compareBy<Alerta>({ it.estado.ordinal }, { -it.creadaEn }))
    val textoTareas = if (esReponedor) {
        "${tareas.count { it.estado == EstadoAlerta.EN_ATENCION }} en curso, ${tareas.count { it.estado == EstadoAlerta.RESUELTA }} listas"
    } else {
        "${tareas.size} pendientes"
    }
    Tarjeta(Modifier.fillMaxWidth()) {
        Column {
            Fila("Usuario", usuario.usuario)
            HorizontalDivider(Modifier.padding(horizontal = 16.dp))
            Row(
                Modifier
                    .fillMaxWidth()
                    .clickable { verTareas = !verTareas }
                    .padding(16.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(Modifier.weight(1f)) {
                    Text(if (esReponedor) "Mis tareas" else "Tareas del equipo", style = MaterialTheme.typography.bodyLarge)
                    Text(textoTareas, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Text(if (verTareas) "Ocultar" else "Ver", style = MaterialTheme.typography.labelLarge, color = Marca.AzulClaro)
            }
            if (verTareas) {
                if (ordenadas.isEmpty()) {
                    Text(
                        "No hay tareas todavía.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(start = 16.dp, end = 16.dp, bottom = 12.dp)
                    )
                }
                ordenadas.forEach { t ->
                    val g = vm.gondola(t.gondolaId)
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .clickable { onAbrirGondola(t.gondolaId) }
                            .padding(horizontal = 16.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Box(
                            Modifier
                                .width(4.dp)
                                .height(36.dp)
                                .clip(RoundedCornerShape(2.dp))
                                .background(
                                    when (t.estado) {
                                        EstadoAlerta.NUEVA -> ColoresSemaforo.Rojo
                                        EstadoAlerta.EN_ATENCION -> Marca.AzulClaro
                                        EstadoAlerta.RESUELTA -> ColoresSemaforo.Verde
                                    }
                                )
                        )
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Text(
                                "${g?.categoria ?: "Góndola"}, pasillo ${g?.pasillo ?: "-"}, repisa ${t.nivel}",
                                style = MaterialTheme.typography.bodyMedium
                            )
                            Text(
                                when (t.estado) {
                                    EstadoAlerta.NUEVA -> "Nueva, ${t.pctVacio.roundToInt()}% vacío"
                                    EstadoAlerta.EN_ATENCION -> "En curso" + (vm.nombreUsuario(t.asignadaA)?.let { if (esReponedor) "" else ", la tiene $it" } ?: "")
                                    EstadoAlerta.RESUELTA -> "Lista " + (t.resueltaEn?.let { tiempoRelativo(it) } ?: "")
                                },
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                        Text(tiempoRelativo(t.creadaEn), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                Spacer(Modifier.height(8.dp))
            }
            HorizontalDivider(Modifier.padding(horizontal = 16.dp))
            Fila(
                "Última actualización",
                if (vm.ultimaActualizacion == 0L) "-" else tiempoRelativo(vm.ultimaActualizacion)
            )
            HorizontalDivider(Modifier.padding(horizontal = 16.dp))
            Row(
                Modifier
                    .fillMaxWidth()
                    .clickable { editarIp = !editarIp }
                    .padding(16.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(Modifier.weight(1f)) {
                    Text("Conexión", style = MaterialTheme.typography.bodyLarge)
                    Text(
                        "Sin servidor, usando datos de prueba",
                        style = MaterialTheme.typography.bodySmall,
                        color = ColoresSemaforo.AmarilloTexto
                    )
                }
                Text(
                    if (editarIp) "Listo" else "Editar",
                    style = MaterialTheme.typography.labelLarge,
                    color = Marca.AzulClaro
                )
            }
            if (editarIp) {
                OutlinedTextField(
                    value = vm.direccionBackend,
                    onValueChange = { vm.direccionBackend = it },
                    label = { Text("IP del servidor") },
                    singleLine = true,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(start = 16.dp, end = 16.dp, bottom = 16.dp)
                )
            }
        }
    }
}

@Composable
private fun Fila(etiqueta: String, valor: String) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(16.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(etiqueta, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f))
        Text(valor, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun CajaNumero(etiqueta: String, valor: String, color: Color, modifier: Modifier = Modifier) {
    Tarjeta(modifier) {
        Column(
            Modifier
                .fillMaxWidth()
                .padding(vertical = 14.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(valor, style = MaterialTheme.typography.headlineSmall, color = color)
            Text(etiqueta, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}
