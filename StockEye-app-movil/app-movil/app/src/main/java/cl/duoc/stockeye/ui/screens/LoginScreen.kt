package cl.duoc.stockeye.ui.screens

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import cl.duoc.stockeye.R
import cl.duoc.stockeye.ui.SesionViewModel
import cl.duoc.stockeye.ui.components.EspacioV
import cl.duoc.stockeye.ui.theme.Marca
import kotlinx.coroutines.launch

@Composable
fun LoginScreen(vm: SesionViewModel, alIngresar: () -> Unit) {
    var email by remember { mutableStateOf("") }
    var clave by remember { mutableStateOf("") }
    var servidor by remember { mutableStateOf(vm.sesion.servidor) }
    var verServidor by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var cargando by remember { mutableStateOf(false) }
    val alcance = rememberCoroutineScope()

    Column(
        Modifier.fillMaxSize().background(Marca.Tinta).systemBarsPadding().verticalScroll(rememberScrollState()).imePadding().padding(24.dp),
        verticalArrangement = Arrangement.Center
    ) {
        Column(
            Modifier.fillMaxWidth().background(Color.White, MaterialTheme.shapes.large).padding(24.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Image(painterResource(R.drawable.ic_launcher_foreground), null, Modifier.size(44.dp).background(Marca.Naranjo, MaterialTheme.shapes.small))
                Column(Modifier.padding(start = 12.dp)) {
                    Text("StockEye", style = MaterialTheme.typography.headlineSmall)
                    Text("App del reponedor", color = Marca.Gris)
                }
            }
            EspacioV(24)
            OutlinedTextField(
                value = email, onValueChange = { email = it }, label = { Text("Email") }, singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email), modifier = Modifier.fillMaxWidth()
            )
            EspacioV(12)
            OutlinedTextField(
                value = clave, onValueChange = { clave = it }, label = { Text("Clave") }, singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password), modifier = Modifier.fillMaxWidth()
            )
            if (verServidor) {
                EspacioV(12)
                OutlinedTextField(
                    value = servidor, onValueChange = { servidor = it }, label = { Text("Servidor") }, singleLine = true,
                    supportingText = { Text("Ej.: http://192.168.1.50:8080/ en la red del local") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri), modifier = Modifier.fillMaxWidth()
                )
            }
            error?.let {
                EspacioV(8)
                Text(it, color = MaterialTheme.colorScheme.error)
            }
            EspacioV(20)
            Button(
                onClick = {
                    cargando = true
                    error = null
                    alcance.launch {
                        vm.ingresar(email, clave, servidor)
                            .onSuccess { alIngresar() }
                            .onFailure { error = it.message }
                        cargando = false
                    }
                },
                enabled = !cargando && email.isNotBlank() && clave.isNotBlank(),
                modifier = Modifier.fillMaxWidth().height(52.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Marca.Azul)
            ) {
                if (cargando) CircularProgressIndicator(Modifier.size(20.dp), color = Color.White, strokeWidth = 2.dp)
                else Text("Ingresar", fontWeight = FontWeight.Bold)
            }
            TextButton(onClick = { verServidor = !verServidor }, modifier = Modifier.align(Alignment.CenterHorizontally)) {
                Text(if (verServidor) "Ocultar servidor" else "Configurar servidor", color = Marca.Gris)
            }
        }
    }
}
