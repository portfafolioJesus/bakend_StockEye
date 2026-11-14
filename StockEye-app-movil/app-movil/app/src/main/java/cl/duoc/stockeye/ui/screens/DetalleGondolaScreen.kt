package cl.duoc.stockeye.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Info
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import cl.duoc.stockeye.data.EstadoAlerta
import cl.duoc.stockeye.data.Semaforo
import cl.duoc.stockeye.ui.StockEyeViewModel
import cl.duoc.stockeye.ui.components.EsquemaGondola
import cl.duoc.stockeye.ui.components.EtiquetaPequena
import cl.duoc.stockeye.ui.components.colorTextoDe
import cl.duoc.stockeye.ui.components.Punto
import cl.duoc.stockeye.ui.components.SemaforoChip
import cl.duoc.stockeye.ui.components.Tarjeta
import cl.duoc.stockeye.ui.components.TituloSeccion
import cl.duoc.stockeye.ui.components.colorPrioridad
import cl.duoc.stockeye.ui.components.pct
import cl.duoc.stockeye.ui.components.tiempoRelativo
import cl.duoc.stockeye.ui.theme.Marca

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DetalleGondolaScreen(vm: StockEyeViewModel, gondolaId: Int, onVolver: () -> Unit) {
    val g = vm.gondola(gondolaId)

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(g?.nombre ?: "Góndola")
                        if (g != null) {
                            Text(
                                "${g.categoria}, pasillo ${g.pasillo}",
                                style = MaterialTheme.typography.labelMedium,
                                color = Color.White.copy(alpha = 0.75f)
                            )
                        }
                    }
                },
                navigationIcon = {
                    IconButton(onClick = onVolver) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Volver")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = Marca.Azul,
                    titleContentColor = Color.White,
                    navigationIconContentColor = Color.White
                )
            )
        }
    ) { padding ->
        if (g == null) {
            Box(
                Modifier
                    .padding(padding)
                    .fillMaxSize(),
                contentAlignment = Alignment.Center
            ) { Text("No se encontró la góndola.") }
        } else {
            val estado = vm.estadoGondola(g)
            val medidas = g.repisas.filter { it.medida }
            val stockMin = vm.stockMinimo(g)
            val abiertas = vm.alertas.filter { it.gondolaId == g.id && it.estado != EstadoAlerta.RESUELTA }

            LazyColumn(
                modifier = Modifier
                    .padding(padding)
                    .fillMaxSize(),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                item {
                    Tarjeta(Modifier.fillMaxWidth()) {
                        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.Top) {
                            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                SemaforoChip(estado)
                                Text(
                                    if (medidas.size == g.repisas.size) "Se vieron todas las repisas"
                                    else "Se vieron ${medidas.size} de ${g.repisas.size} repisas",
                                    style = MaterialTheme.typography.bodyMedium,
                                    fontWeight = FontWeight.SemiBold
                                )
                                Text(
                                    if (g.tipo == "refrigerador") "Refrigerador" else "Estantería",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                                Text(
                                    "Última foto ${tiempoRelativo(g.ultimaFoto)}",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                            Column(horizontalAlignment = Alignment.End) {
                                Text(
                                    stockMin?.let { "${pct(it)}%" } ?: "-",
                                    style = MaterialTheme.typography.headlineMedium,
                                    color = colorTextoDe(estado)
                                )
                                Text("stock mín.", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                }

                item {
                    Column {
                        TituloSeccion("Repisas")
                        Tarjeta(Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(14.dp)) {
                                EsquemaGondola(g.repisas) { vm.semaforo(it) }
                                Spacer(Modifier.width(1.dp))
                                Text(
                                    "Lo de color es producto, lo claro es espacio vacío.",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    modifier = Modifier.padding(top = 10.dp)
                                )
                                if (g.repisas.any { !it.medida }) {
                                    Text(
                                        "Las grises no se vieron bien en la foto, hay que ir a mirarlas.",
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        modifier = Modifier.padding(top = 4.dp)
                                    )
                                }
                            }
                        }
                    }
                }

                item {
                    Column {
                        TituloSeccion("Alertas (${abiertas.size})")
                        Tarjeta(Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                                if (abiertas.isEmpty()) {
                                    Text(
                                        if (estado == Semaforo.ROJO) "Hay repisas en rojo sin alerta abierta."
                                        else "No hay alertas.",
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                                abiertas.forEach { a ->
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Punto(colorPrioridad(a.prioridad))
                                        Spacer(Modifier.width(10.dp))
                                        Column(Modifier.weight(1f)) {
                                            Text(
                                                "Repisa ${a.nivel}: ${pct(a.pctVacio)}% vacío",
                                                style = MaterialTheme.typography.bodyMedium,
                                                fontWeight = FontWeight.SemiBold
                                            )
                                            Text(
                                                vm.nombreUsuario(a.asignadaA)?.let { "La tiene $it" } ?: "Nadie la ha tomado",
                                                style = MaterialTheme.typography.bodySmall,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant
                                            )
                                        }
                                        EtiquetaPequena(a.estado.etiqueta, MaterialTheme.colorScheme.primary)
                                    }
                                }
                            }
                        }
                    }
                }

                // TODO: mostrar la foto cuando este el backend
                item {
                    Column {
                        TituloSeccion("Foto")
                        Tarjeta(Modifier.fillMaxWidth()) {
                            Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Filled.Info, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                                Spacer(Modifier.width(12.dp))
                                Text(
                                    "Acá va a ir la foto con los vacíos marcados cuando conectemos el backend.",
                                    style = MaterialTheme.typography.bodySmall
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
