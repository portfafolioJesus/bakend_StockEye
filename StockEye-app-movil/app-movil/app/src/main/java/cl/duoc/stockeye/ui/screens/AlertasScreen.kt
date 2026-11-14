package cl.duoc.stockeye.ui.screens

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Done
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import cl.duoc.stockeye.data.Alerta
import cl.duoc.stockeye.data.EstadoAlerta
import cl.duoc.stockeye.data.Rol
import cl.duoc.stockeye.data.Usuario
import cl.duoc.stockeye.ui.StockEyeViewModel
import cl.duoc.stockeye.ui.components.AlertaCard
import cl.duoc.stockeye.ui.components.EstadoVacio

// CU-R02, R03, R04 y S02
@Composable
fun AlertasScreen(vm: StockEyeViewModel, usuario: Usuario, onAbrirGondola: (Int) -> Unit) {
    var filtro by rememberSaveable { mutableStateOf(EstadoAlerta.NUEVA) }
    val esReponedor = usuario.rol == Rol.REPONEDOR
    val visibles = vm.alertasPara(usuario)
    val lista = visibles
        .filter { it.estado == filtro }
        .sortedWith(compareBy<Alerta>({ it.prioridad.ordinal }, { -it.pctVacio }, { it.creadaEn }))

    Column(Modifier.fillMaxSize()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState())
                .padding(horizontal = 16.dp, vertical = 10.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            EstadoAlerta.entries.forEach { e ->
                val n = visibles.count { it.estado == e }
                FilterChip(
                    selected = filtro == e,
                    onClick = { filtro = e },
                    label = { Text("${e.etiqueta} ($n)") }
                )
            }
        }

        if (lista.isEmpty()) {
            Box(Modifier.fillMaxSize()) {
                when (filtro) {
                    EstadoAlerta.NUEVA -> EstadoVacio(
                        Icons.Filled.CheckCircle,
                        "Sin alertas nuevas",
                        "Cuando falte producto en alguna repisa va a salir acá."
                    )
                    EstadoAlerta.EN_ATENCION -> EstadoVacio(
                        Icons.Filled.Notifications,
                        "Nada en curso",
                        "Toma una de las nuevas."
                    )
                    EstadoAlerta.RESUELTA -> EstadoVacio(
                        Icons.Filled.Done,
                        "Todavía nada",
                        "Acá quedan las que vayas terminando."
                    )
                }
            }
        } else {
            LazyColumn(
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                items(lista, key = { it.id }) { a ->
                    AlertaCard(
                        alerta = a,
                        gondola = vm.gondola(a.gondolaId),
                        asignadaA = vm.nombreUsuario(a.asignadaA),
                        onAbrir = { onAbrirGondola(a.gondolaId) }
                    ) {
                        if (esReponedor) {
                            when (a.estado) {
                                EstadoAlerta.NUEVA ->
                                    Button(onClick = { vm.marcarEnAtencion(a) }, modifier = Modifier.fillMaxWidth()) {
                                        Text("Me encargo")
                                    }
                                EstadoAlerta.EN_ATENCION ->
                                    Button(onClick = { vm.marcarResuelta(a) }, modifier = Modifier.fillMaxWidth()) {
                                        Text("Listo, repuesto")
                                    }
                                EstadoAlerta.RESUELTA -> Unit
                            }
                        } else if (a.estado != EstadoAlerta.RESUELTA) {
                            MenuAsignar(vm, a)
                            OutlinedButton(onClick = { vm.cambiarPrioridad(a) }) {
                                Text("Prioridad")
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun MenuAsignar(vm: StockEyeViewModel, alerta: Alerta) {
    var abierto by remember { mutableStateOf(false) }
    Box {
        Button(onClick = { abierto = true }) {
            Text(if (alerta.asignadaA == null) "Asignar" else "Reasignar")
        }
        DropdownMenu(expanded = abierto, onDismissRequest = { abierto = false }) {
            vm.reponedores().forEach { r ->
                DropdownMenuItem(
                    text = { Text(r.nombre + (r.zona?.let { " ($it)" } ?: "")) },
                    onClick = {
                        vm.asignar(alerta, r.id)
                        abierto = false
                    }
                )
            }
        }
    }
}
