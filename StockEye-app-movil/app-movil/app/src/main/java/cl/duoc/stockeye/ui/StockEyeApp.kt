package cl.duoc.stockeye.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Place
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import cl.duoc.stockeye.data.EstadoAlerta
import cl.duoc.stockeye.data.Rol
import cl.duoc.stockeye.data.Usuario
import cl.duoc.stockeye.ui.screens.AlertasScreen
import cl.duoc.stockeye.ui.screens.DetalleGondolaScreen
import cl.duoc.stockeye.ui.screens.LoginScreen
import cl.duoc.stockeye.ui.screens.MapaScreen
import cl.duoc.stockeye.ui.screens.PerfilScreen
import cl.duoc.stockeye.ui.screens.ResumenScreen
import cl.duoc.stockeye.ui.theme.Marca
import kotlinx.coroutines.delay

enum class Pestana(val titulo: String, val icono: ImageVector) {
    RESUMEN("Resumen", Icons.Filled.Home),
    PASILLOS("Pasillos", Icons.Filled.Place),
    ALERTAS("Alertas", Icons.Filled.Notifications),
    PERFIL("Perfil", Icons.Filled.Person)
}

private const val INTERVALO_ACTUALIZACION_MS = 30_000L

@Composable
fun StockEyeApp(vm: StockEyeViewModel) {
    val usuario = vm.usuario
    if (usuario == null) {
        LoginScreen(vm)
    } else {
        Principal(vm, usuario)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun Principal(vm: StockEyeViewModel, usuario: Usuario) {
    // el reponedor no ve el resumen
    val pestanas = if (usuario.rol == Rol.REPONEDOR) {
        listOf(Pestana.ALERTAS, Pestana.PASILLOS, Pestana.PERFIL)
    } else {
        listOf(Pestana.RESUMEN, Pestana.PASILLOS, Pestana.ALERTAS, Pestana.PERFIL)
    }
    var actual by rememberSaveable(usuario.id) { mutableStateOf(pestanas.first()) }
    var gondolaAbierta by rememberSaveable { mutableStateOf<Int?>(null) }
    val snackbar = remember { SnackbarHostState() }

    // refresca cada 30s
    LaunchedEffect(usuario.id) {
        while (true) {
            delay(INTERVALO_ACTUALIZACION_MS)
            vm.refrescarSilencioso()
        }
    }

    LaunchedEffect(vm.mensaje) {
        vm.mensaje?.let {
            snackbar.showSnackbar(it)
            vm.mensajeMostrado()
        }
    }

    val abierta = gondolaAbierta
    if (abierta != null) {
        BackHandler { gondolaAbierta = null }
        DetalleGondolaScreen(vm, abierta, onVolver = { gondolaAbierta = null })
    } else {
        val nuevas = vm.alertasPara(usuario).count { it.estado == EstadoAlerta.NUEVA }
        Scaffold(
            topBar = {
                TopAppBar(
                    title = {
                        Column {
                            Text(actual.titulo)
                            Text(
                                "Hola, ${usuario.nombre.substringBefore(" ")}",
                                style = MaterialTheme.typography.labelMedium,
                                color = Color.White.copy(alpha = 0.75f)
                            )
                        }
                    },
                    actions = {
                        IconButton(onClick = { vm.refrescar() }) {
                            Icon(Icons.Filled.Refresh, contentDescription = "Actualizar")
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(
                        containerColor = Marca.Azul,
                        titleContentColor = Color.White,
                        actionIconContentColor = Color.White
                    )
                )
            },
            bottomBar = {
                NavigationBar(containerColor = MaterialTheme.colorScheme.surface) {
                    pestanas.forEach { p ->
                        NavigationBarItem(
                            selected = p == actual,
                            onClick = { actual = p },
                            icon = {
                                if (p == Pestana.ALERTAS && nuevas > 0) {
                                    BadgedBox(badge = { Badge { Text("$nuevas") } }) {
                                        Icon(p.icono, contentDescription = p.titulo)
                                    }
                                } else {
                                    Icon(p.icono, contentDescription = p.titulo)
                                }
                            },
                            label = { Text(p.titulo) },
                            colors = NavigationBarItemDefaults.colors(
                                selectedIconColor = Marca.AzulClaro,
                                selectedTextColor = Marca.AzulClaro,
                                indicatorColor = MaterialTheme.colorScheme.primaryContainer
                            )
                        )
                    }
                }
            },
            snackbarHost = { SnackbarHost(snackbar) },
            containerColor = MaterialTheme.colorScheme.background
        ) { padding ->
            Box(
                Modifier
                    .padding(padding)
                    .fillMaxSize()
            ) {
                val abrir: (Int) -> Unit = { gondolaAbierta = it }
                when (actual) {
                    Pestana.RESUMEN -> ResumenScreen(vm, abrir)
                    Pestana.PASILLOS -> MapaScreen(vm, abrir)
                    Pestana.ALERTAS -> AlertasScreen(vm, usuario, abrir)
                    Pestana.PERFIL -> PerfilScreen(vm, usuario, abrir)
                }
            }
        }
    }
}
