package cl.duoc.stockeye.ui

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import cl.duoc.stockeye.ui.screens.AlertasScreen
import cl.duoc.stockeye.ui.screens.CamaraScreen
import cl.duoc.stockeye.ui.screens.DetalleTicketScreen
import cl.duoc.stockeye.ui.screens.LoginScreen
import cl.duoc.stockeye.ui.screens.MisTicketsScreen
import cl.duoc.stockeye.ui.screens.PerfilScreen
import cl.duoc.stockeye.ui.screens.ResultadoScreen
import cl.duoc.stockeye.ui.theme.Marca

object Rutas {
    const val LOGIN = "login"
    const val TICKETS = "tickets"
    const val ALERTAS = "alertas"
    const val PERFIL = "perfil"
    const val CAMARA = "camara/{modo}?numero={numero}"
    const val RESULTADO = "resultado/{imagenId}"
    const val TICKET = "ticket/{numero}"

    fun camaraNueva() = "camara/nueva"
    fun camaraCierre(numero: String) = "camara/cierre?numero=$numero"
    fun resultado(imagenId: Long) = "resultado/$imagenId"
    fun ticket(numero: String) = "ticket/$numero"
}

private data class Pestana(val ruta: String, val nombre: String, val icono: ImageVector)

private val pestanas = listOf(
    Pestana(Rutas.TICKETS, "Tickets", Icons.AutoMirrored.Filled.List),
    Pestana(Rutas.ALERTAS, "Alertas", Icons.Filled.Notifications),
    Pestana(Rutas.PERFIL, "Perfil", Icons.Filled.Person)
)

@Composable
fun StockEyeNavegacion(ticketPendiente: String?, alAbrirTicketPendiente: () -> Unit) {
    val nav = rememberNavController()
    val sesionVm: SesionViewModel = viewModel()
    val usuario by sesionVm.usuario.collectAsStateWithLifecycle()
    val expirada by sesionVm.expirada.collectAsStateWithLifecycle()
    // el destino inicial se decide una vez: si cambiara, NavHost rearmaría el grafo
    val inicio = remember { if (sesionVm.sesion.iniciada) Rutas.TICKETS else Rutas.LOGIN }
    val actual by nav.currentBackStackEntryAsState()
    val ruta = actual?.destination?.route

    // Android 13+: pedir permiso de notificaciones al entrar
    val permisoNotif = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }
    LaunchedEffect(usuario?.id) {
        if (usuario != null && Build.VERSION.SDK_INT >= 33) permisoNotif.launch(Manifest.permission.POST_NOTIFICATIONS)
    }
    LaunchedEffect(expirada) {
        if (expirada) nav.navigate(Rutas.LOGIN) { popUpTo(0) }
    }
    // Tocar una notificación push abre el ticket
    LaunchedEffect(ticketPendiente, usuario?.id) {
        if (ticketPendiente != null && sesionVm.sesion.iniciada) {
            nav.navigate(Rutas.ticket(ticketPendiente))
            alAbrirTicketPendiente()
        }
    }

    Scaffold(
        containerColor = Marca.Fondo,
        // cada pantalla maneja sus márgenes de sistema (la cámara usa pantalla completa)
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        bottomBar = {
            if (ruta in pestanas.map { it.ruta }) {
                NavigationBar(containerColor = Color.White) {
                    pestanas.forEach { p ->
                        NavigationBarItem(
                            selected = ruta == p.ruta,
                            onClick = { nav.irAPestana(p.ruta) },
                            icon = { Icon(p.icono, contentDescription = null) },
                            label = { Text(p.nombre) },
                            colors = NavigationBarItemDefaults.colors(
                                selectedIconColor = Marca.Azul,
                                selectedTextColor = Marca.Azul,
                                indicatorColor = Color(0xFFEEF2FF)
                            )
                        )
                    }
                }
            }
        }
    ) { relleno ->
        NavHost(
            navController = nav,
            startDestination = inicio,
            modifier = Modifier.padding(relleno)
        ) {
            composable(Rutas.LOGIN) {
                LoginScreen(sesionVm) { nav.navigate(Rutas.TICKETS) { popUpTo(Rutas.LOGIN) { inclusive = true } } }
            }
            composable(Rutas.TICKETS) {
                MisTicketsScreen(
                    usuario = usuario,
                    abrirTicket = { nav.navigate(Rutas.ticket(it)) },
                    tomarFoto = { nav.navigate(Rutas.camaraNueva()) },
                    abrirAlertas = { nav.irAPestana(Rutas.ALERTAS) }
                )
            }
            composable(Rutas.ALERTAS) { AlertasScreen(abrirTicket = { nav.navigate(Rutas.ticket(it)) }) }
            composable(Rutas.PERFIL) {
                PerfilScreen(sesionVm) { nav.navigate(Rutas.LOGIN) { popUpTo(0) } }
            }
            composable(
                Rutas.CAMARA,
                arguments = listOf(
                    navArgument("modo") { type = NavType.StringType },
                    navArgument("numero") { type = NavType.StringType; nullable = true; defaultValue = null }
                )
            ) { entrada ->
                val modo = entrada.arguments?.getString("modo") ?: "nueva"
                val numero = entrada.arguments?.getString("numero")
                CamaraScreen(
                    recinto = sesionVm.recinto,
                    numeroCierre = if (modo == "cierre") numero else null,
                    cerrar = { nav.popBackStack() },
                    alSubir = { imagenId ->
                        if (modo == "cierre") nav.popBackStack()
                        else nav.navigate(Rutas.resultado(imagenId)) { popUpTo(Rutas.TICKETS) }
                    }
                )
            }
            composable(Rutas.RESULTADO, arguments = listOf(navArgument("imagenId") { type = NavType.LongType })) { entrada ->
                ResultadoScreen(
                    imagenId = entrada.arguments?.getLong("imagenId") ?: 0L,
                    umbralRecinto = sesionVm.recinto?.umbralVacio ?: 5.0,
                    volver = { nav.popBackStack() },
                    alCrear = { numero -> nav.navigate(Rutas.ticket(numero)) { popUpTo(Rutas.TICKETS) } }
                )
            }
            composable(Rutas.TICKET, arguments = listOf(navArgument("numero") { type = NavType.StringType })) { entrada ->
                val numero = entrada.arguments?.getString("numero") ?: ""
                DetalleTicketScreen(
                    numero = numero,
                    volver = { nav.popBackStack() },
                    fotoCierre = { nav.navigate(Rutas.camaraCierre(numero)) }
                )
            }
        }
    }
}

private fun NavHostController.irAPestana(ruta: String) = navigate(ruta) {
    popUpTo(graph.findStartDestination().id) { saveState = true }
    launchSingleTop = true
    restoreState = true
}
