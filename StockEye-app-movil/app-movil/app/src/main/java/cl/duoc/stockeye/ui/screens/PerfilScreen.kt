package cl.duoc.stockeye.ui.screens

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import cl.duoc.stockeye.BuildConfig
import cl.duoc.stockeye.ui.SesionViewModel
import cl.duoc.stockeye.ui.components.Avatar
import cl.duoc.stockeye.ui.components.EspacioV
import cl.duoc.stockeye.ui.components.Tarjeta
import cl.duoc.stockeye.ui.theme.Marca
import com.google.firebase.FirebaseApp

@Composable
fun PerfilScreen(vm: SesionViewModel, alSalir: () -> Unit) {
    val usuario by vm.usuario.collectAsStateWithLifecycle()
    val contexto = LocalContext.current
    val pushConfigurado = FirebaseApp.getApps(contexto).isNotEmpty()
    val permisoNotif = Build.VERSION.SDK_INT < 33 ||
        ContextCompat.checkSelfPermission(contexto, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    Column(Modifier.fillMaxSize().background(Marca.Fondo)) {
        Column(Modifier.fillMaxWidth().background(Color.White).statusBarsPadding().padding(20.dp)) {
            Text("Perfil", style = MaterialTheme.typography.headlineSmall)
        }
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Tarjeta {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Avatar(usuario?.nombreCompleto ?: "?")
                    Column(Modifier.padding(start = 12.dp)) {
                        Text(usuario?.nombreCompleto ?: "", style = MaterialTheme.typography.titleMedium)
                        Text(usuario?.email ?: "", color = Marca.Gris)
                    }
                }
                EspacioV(12)
                Text("Recinto: ${usuario?.recintos?.joinToString { it.nombre } ?: "—"}")
            }
            Tarjeta {
                Text("Notificaciones", style = MaterialTheme.typography.titleMedium)
                EspacioV(6)
                Text(
                    when {
                        !pushConfigurado -> "Push no configurado en esta versión (falta google-services.json)."
                        !permisoNotif -> "Permiso de notificaciones denegado: actívalo en Ajustes > Apps > StockEye."
                        else -> "Activas: te avisamos cuando te asignen un ticket o comenten."
                    },
                    color = Marca.Gris
                )
            }
            Tarjeta {
                Text("Conexión", style = MaterialTheme.typography.titleMedium)
                EspacioV(6)
                Text("Servidor: ${vm.sesion.servidor}", color = Marca.Gris)
                Text("Versión ${BuildConfig.VERSION_NAME}", color = Marca.Gris)
            }
            OutlinedButton(onClick = { vm.salir(alSalir) }, modifier = Modifier.fillMaxWidth().height(52.dp), shape = MaterialTheme.shapes.small) {
                Text("Cerrar sesión", color = MaterialTheme.colorScheme.error)
            }
        }
    }
}
