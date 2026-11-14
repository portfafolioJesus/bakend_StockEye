package cl.duoc.stockeye.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import cl.duoc.stockeye.data.Alerta
import cl.duoc.stockeye.data.DemoRepository
import cl.duoc.stockeye.data.EstadoAlerta
import cl.duoc.stockeye.data.Gondola
import cl.duoc.stockeye.data.Prioridad
import cl.duoc.stockeye.data.Repisa
import cl.duoc.stockeye.data.Rol
import cl.duoc.stockeye.data.Semaforo
import cl.duoc.stockeye.data.StockEyeRepository
import cl.duoc.stockeye.data.Umbrales
import cl.duoc.stockeye.data.Usuario
import kotlinx.coroutines.launch

class StockEyeViewModel(
    private val repo: StockEyeRepository = DemoRepository()
) : ViewModel() {

    var usuario by mutableStateOf<Usuario?>(null)
        private set
    var usuarios by mutableStateOf<List<Usuario>>(emptyList())
        private set
    var gondolas by mutableStateOf<List<Gondola>>(emptyList())
        private set
    var alertas by mutableStateOf<List<Alerta>>(emptyList())
        private set
    var umbrales by mutableStateOf(Umbrales())
        private set
    var cargando by mutableStateOf(false)
        private set
    var errorLogin by mutableStateOf<String?>(null)
        private set
    var mensaje by mutableStateOf<String?>(null)
        private set
    var ultimaActualizacion by mutableStateOf(0L)
        private set

    // todavia no se usa
    var direccionBackend by mutableStateOf("http://10.0.2.2:8000/")

    // login

    fun login(nombreUsuario: String, clave: String) {
        viewModelScope.launch {
            cargando = true
            errorLogin = null
            val u = repo.login(nombreUsuario.trim(), clave)
            if (u == null) {
                errorLogin = "Usuario o contraseña incorrectos"
            } else {
                cargarDatos()
                usuario = u
            }
            cargando = false
        }
    }

    fun cerrarSesion() {
        usuario = null
    }

    fun refrescar() {
        viewModelScope.launch {
            cargarDatos()
            mensaje = "Actualizado"
        }
    }

    fun refrescarSilencioso() {
        viewModelScope.launch { cargarDatos() }
    }

    fun mensajeMostrado() {
        mensaje = null
    }

    private suspend fun cargarDatos() {
        usuarios = repo.usuarios()
        gondolas = repo.gondolas()
        alertas = repo.alertas()
        umbrales = repo.umbrales()
        ultimaActualizacion = System.currentTimeMillis()
    }

    fun gondola(id: Int): Gondola? = gondolas.firstOrNull { it.id == id }

    fun reponedores(): List<Usuario> = usuarios.filter { it.rol == Rol.REPONEDOR }

    fun nombreUsuario(id: Int?): String? = usuarios.firstOrNull { it.id == id }?.nombre

    fun semaforo(repisa: Repisa): Semaforo = umbrales.semaforo(repisa.pctVacio)

    // la gondola toma el color de su peor repisa
    fun estadoGondola(g: Gondola): Semaforo {
        val estados = g.repisas.map { semaforo(it) }
        return when {
            Semaforo.ROJO in estados -> Semaforo.ROJO
            Semaforo.INDETERMINADO in estados -> Semaforo.INDETERMINADO
            Semaforo.AMARILLO in estados -> Semaforo.AMARILLO
            else -> Semaforo.VERDE
        }
    }

    fun stockMinimo(g: Gondola): Double? =
        g.repisas.mapNotNull { it.pctVacio }.maxOrNull()?.let { 100.0 - it }

    // reponedor: las suyas + las sin asignar
    fun alertasPara(u: Usuario): List<Alerta> =
        if (u.rol == Rol.REPONEDOR) alertas.filter { it.asignadaA == null || it.asignadaA == u.id }
        else alertas

    fun alertasAbiertas(): List<Alerta> = alertas.filter { it.estado != EstadoAlerta.RESUELTA }

    // % de repisas en verde
    fun saludSala(): Float {
        val medidas = gondolas.flatMap { it.repisas }.filter { it.medida }
        if (medidas.isEmpty()) return 0f
        return medidas.count { semaforo(it) == Semaforo.VERDE }.toFloat() / medidas.size
    }

    // alertas

    fun marcarEnAtencion(a: Alerta) = actualizar(
        a.copy(
            estado = EstadoAlerta.EN_ATENCION,
            asignadaA = a.asignadaA ?: usuario?.id,
            atendidaEn = System.currentTimeMillis()
        )
    )

    fun marcarResuelta(a: Alerta) = actualizar(
        a.copy(
            estado = EstadoAlerta.RESUELTA,
            asignadaA = a.asignadaA ?: usuario?.id,
            resueltaEn = System.currentTimeMillis()
        )
    )

    fun asignar(a: Alerta, reponedorId: Int) = actualizar(a.copy(asignadaA = reponedorId))

    fun cambiarPrioridad(a: Alerta) {
        val todas = Prioridad.entries
        actualizar(a.copy(prioridad = todas[(a.prioridad.ordinal + 1) % todas.size]))
    }

    private fun actualizar(a: Alerta) {
        viewModelScope.launch {
            repo.actualizarAlerta(a)
            cargarDatos()
        }
    }

    fun guardarUmbrales(nuevos: Umbrales) {
        viewModelScope.launch {
            repo.guardarUmbrales(nuevos)
            cargarDatos()
            mensaje = "Guardado"
        }
    }
}
