package cl.duoc.stockeye.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import cl.duoc.stockeye.data.EstadoAlerta
import cl.duoc.stockeye.data.Semaforo
import cl.duoc.stockeye.ui.StockEyeViewModel
import cl.duoc.stockeye.ui.components.Avatar
import cl.duoc.stockeye.ui.components.KpiCard
import cl.duoc.stockeye.ui.components.MiniRepisas
import cl.duoc.stockeye.ui.components.Tarjeta
import cl.duoc.stockeye.ui.components.TituloSeccion
import cl.duoc.stockeye.ui.components.pct
import cl.duoc.stockeye.ui.theme.ColoresSemaforo

// CU-S04 va abajo
@Composable
fun ResumenScreen(vm: StockEyeViewModel, onAbrirGondola: (Int) -> Unit) {
    val estados = vm.gondolas.associateWith { vm.estadoGondola(it) }
    val enRojo = estados.filterValues { it == Semaforo.ROJO }.keys
        .sortedBy { vm.stockMinimo(it) ?: 100.0 }
    val revisar = estados.count { it.value == Semaforo.INDETERMINADO }
    val abiertas = vm.alertasAbiertas()
    val sinAsignar = abiertas.count { it.asignadaA == null }
    val salud = vm.saludSala()

    val resueltas = vm.alertas.filter { it.estado == EstadoAlerta.RESUELTA && it.resueltaEn != null }
    val minutosPromedio = resueltas
        .map { ((it.resueltaEn ?: it.creadaEn) - it.creadaEn) / 60_000.0 }
        .takeIf { it.isNotEmpty() }?.average()

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item {
            Tarjeta(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp)) {
                    Row(verticalAlignment = Alignment.Bottom) {
                        Text("Repisas bien surtidas", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                        Text("${(salud * 100).toInt()}%", style = MaterialTheme.typography.headlineSmall)
                    }
                    Spacer(Modifier.height(8.dp))
                    LinearProgressIndicator(
                        progress = { salud },
                        modifier = Modifier.fillMaxWidth(),
                        color = if (salud >= 0.7f) ColoresSemaforo.Verde else if (salud >= 0.4f) ColoresSemaforo.Amarillo else ColoresSemaforo.Rojo,
                        trackColor = MaterialTheme.colorScheme.surfaceVariant
                    )
                }
            }
        }

        item {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                KpiCard("Por reponer", "${enRojo.size}", ColoresSemaforo.Rojo, Modifier.weight(1f))
                KpiCard("Por revisar", "$revisar", ColoresSemaforo.Gris, Modifier.weight(1f))
            }
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                KpiCard("Alertas pendientes", "${abiertas.size}", MaterialTheme.colorScheme.primary, Modifier.weight(1f))
                KpiCard("Sin nadie a cargo", "$sinAsignar", ColoresSemaforo.Amarillo, Modifier.weight(1f))
            }
        }

        item { TituloSeccion("Hay que reponer") }
        if (enRojo.isEmpty()) {
            item {
                Text(
                    "Ninguna por ahora.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodyMedium
                )
            }
        }
        enRojo.forEach { g ->
            item(key = "rojo-${g.id}") {
                Card(
                    onClick = { onAbrirGondola(g.id) },
                    modifier = Modifier.fillMaxWidth(),
                    shape = MaterialTheme.shapes.medium,
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                    elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
                ) {
                    Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("${g.categoria} (${g.nombre})", style = MaterialTheme.typography.titleMedium)
                            Text(
                                "Pasillo ${g.pasillo}",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                        Column(Modifier.width(90.dp)) {
                            MiniRepisas(g.repisas) { vm.semaforo(it) }
                        }
                        Spacer(Modifier.width(12.dp))
                        vm.stockMinimo(g)?.let {
                            Text("${pct(it)}%", color = ColoresSemaforo.Rojo, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }

        item { TituloSeccion("Cómo vamos hoy") }
        item {
            Tarjeta(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Row {
                        Column(Modifier.weight(1f)) {
                            Text("${resueltas.size}", style = MaterialTheme.typography.headlineSmall)
                            Text("alertas resueltas", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        Column(Modifier.weight(1f)) {
                            Text(
                                minutosPromedio?.let { "${pct(it)} min" } ?: "—",
                                style = MaterialTheme.typography.headlineSmall
                            )
                            Text("tiempo promedio", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                    val maxResueltas = vm.reponedores().maxOfOrNull { r -> resueltas.count { it.asignadaA == r.id } } ?: 0
                    vm.reponedores().forEach { r ->
                        val suyas = resueltas.count { it.asignadaA == r.id }
                        val enCurso = abiertas.count { it.asignadaA == r.id }
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Avatar(r.nombre, MaterialTheme.colorScheme.primaryContainer, MaterialTheme.colorScheme.onPrimaryContainer, 34)
                            Spacer(Modifier.width(12.dp))
                            Column(Modifier.weight(1f)) {
                                Row {
                                    Text(r.nombre, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                                    Text(
                                        "$suyas listas, $enCurso en curso",
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                                Spacer(Modifier.height(4.dp))
                                LinearProgressIndicator(
                                    progress = { if (maxResueltas == 0) 0f else suyas.toFloat() / maxResueltas },
                                    modifier = Modifier.fillMaxWidth(),
                                    color = ColoresSemaforo.Verde,
                                    trackColor = MaterialTheme.colorScheme.surfaceVariant
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
