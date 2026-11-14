package cl.duoc.stockeye.ui.screens

import androidx.compose.foundation.BorderStroke
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
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import cl.duoc.stockeye.data.Gondola
import cl.duoc.stockeye.data.Semaforo
import cl.duoc.stockeye.ui.StockEyeViewModel
import cl.duoc.stockeye.ui.components.MiniRepisas
import cl.duoc.stockeye.ui.components.Punto
import cl.duoc.stockeye.ui.components.Tarjeta
import cl.duoc.stockeye.ui.components.TituloSeccion
import cl.duoc.stockeye.ui.components.colorDe
import cl.duoc.stockeye.ui.components.colorTextoDe
import cl.duoc.stockeye.ui.components.pct

// CU-R01 / CU-S01
@Composable
fun MapaScreen(vm: StockEyeViewModel, onAbrirGondola: (Int) -> Unit) {
    var soloProblemas by rememberSaveable { mutableStateOf(false) }
    val porPasillo = vm.gondolas.groupBy { it.pasillo }.toSortedMap()
    val estados = vm.gondolas.map { vm.estadoGondola(it) }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item(key = "resumen") {
            Tarjeta(Modifier.fillMaxWidth()) {
                Row(Modifier.padding(vertical = 14.dp)) {
                    Semaforo.entries.forEach { s ->
                        Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(
                                "${estados.count { it == s }}",
                                style = MaterialTheme.typography.headlineSmall,
                                color = colorTextoDe(s)
                            )
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Punto(colorDe(s), 7)
                                Spacer(Modifier.width(4.dp))
                                Text(
                                    when (s) {
                                        Semaforo.VERDE -> "Bien"
                                        Semaforo.AMARILLO -> "A medias"
                                        Semaforo.ROJO -> "Falta"
                                        Semaforo.INDETERMINADO -> "Revisar"
                                    },
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                    }
                }
            }
        }

        item(key = "filtro") {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(selected = !soloProblemas, onClick = { soloProblemas = false }, label = { Text("Todas") })
                FilterChip(selected = soloProblemas, onClick = { soloProblemas = true }, label = { Text("Solo las que faltan") })
            }
        }

        for ((pasillo, lista) in porPasillo) {
            item(key = "pasillo-$pasillo") {
                Column {
                    TituloSeccion("Pasillo $pasillo")
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        lista.sortedBy { it.posicion }.forEach { g ->
                            val estado = vm.estadoGondola(g)
                            RecuadroGondola(
                                g = g,
                                estado = estado,
                                stockMinimo = vm.stockMinimo(g),
                                semaforoDe = { vm.semaforo(it) },
                                onClick = { onAbrirGondola(g.id) },
                                modifier = Modifier
                                    .weight(1f)
                                    .alpha(if (soloProblemas && estado == Semaforo.VERDE) 0.3f else 1f)
                            )
                        }
                    }
                }
            }
        }

        item(key = "nota") {
            Text(
                "Gris = no se vio bien en la foto, no quiere decir que esté llena.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

@Composable
private fun RecuadroGondola(
    g: Gondola,
    estado: Semaforo,
    stockMinimo: Double?,
    semaforoDe: (cl.duoc.stockeye.data.Repisa) -> Semaforo,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    val c = colorDe(estado)
    Card(
        onClick = onClick,
        modifier = modifier,
        shape = MaterialTheme.shapes.small,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = BorderStroke(if (estado == Semaforo.VERDE) 1.dp else 2.dp, c)
    ) {
        Column(Modifier.padding(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    g.nombre,
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f)
                )
                Punto(c, 9)
            }
            Text(
                g.categoria,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            Spacer(Modifier.height(8.dp))
            MiniRepisas(g.repisas, semaforoDe)
            Spacer(Modifier.height(8.dp))
            Text(
                when {
                    estado == Semaforo.INDETERMINADO -> "Revisar"
                    stockMinimo != null -> "${pct(stockMinimo)}% stock"
                    else -> "Sin datos"
                },
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.SemiBold,
                color = colorTextoDe(estado)
            )
        }
    }
}
