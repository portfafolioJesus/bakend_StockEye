package cl.duoc.stockeye.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import cl.duoc.stockeye.StockEyeApp
import cl.duoc.stockeye.data.ErrorStockEye
import cl.duoc.stockeye.data.Usuario
import cl.duoc.stockeye.push.StockEyeMessagingService
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** Sesión del reponedor: login, usuario actual, recinto y cierre de sesión. */
class SesionViewModel(app: Application) : AndroidViewModel(app) {
    private val contenedor = app as StockEyeApp
    val repo get() = contenedor.repositorio
    val sesion get() = contenedor.sesion

    private val _usuario = MutableStateFlow<Usuario?>(null)
    val usuario: StateFlow<Usuario?> = _usuario.asStateFlow()

    private val _expirada = MutableStateFlow(false)
    val expirada: StateFlow<Boolean> = _expirada.asStateFlow()

    val recinto get() = _usuario.value?.recintos?.firstOrNull()

    init {
        if (sesion.iniciada) cargarUsuario()
        viewModelScope.launch {
            repo.sesionExpirada.collect {
                sesion.cerrar()
                _usuario.value = null
                _expirada.value = true
            }
        }
    }

    private fun cargarUsuario() = viewModelScope.launch {
        runCatching { repo.yo() }.onSuccess {
            _usuario.value = it
            StockEyeMessagingService.registrarDispositivo(getApplication(), viewModelScope)
        }
    }

    suspend fun ingresar(email: String, clave: String, servidor: String): Result<Usuario> = runCatching {
        if (servidor.isNotBlank() && servidor != sesion.servidor) sesion.cambiarServidor(servidor)
        val u = repo.ingresar(email, clave)
        if (u.rol != "REPONEDOR") {
            // la app es del reponedor; supervisores y administradores usan el panel web
            repo.salir()
            throw ErrorStockEye("Esta app es para reponedores. Supervisores y administradores usan el panel web.")
        }
        _usuario.value = u
        _expirada.value = false
        StockEyeMessagingService.registrarDispositivo(getApplication(), viewModelScope)
        u
    }

    fun salir(alTerminar: () -> Unit) = viewModelScope.launch {
        runCatching { repo.salir() }
        _usuario.value = null
        alTerminar()
    }
}
