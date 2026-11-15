package cl.duoc.stockeye.data

import kotlinx.serialization.Serializable

// Contrato con la API de StockEye (/api/v1). Los nombres JSON vienen en
// snake_case y se convierten solos (JsonNamingStrategy.SnakeCase en ApiCliente).
// Las fechas llegan en ISO-8601 con zona horaria.

@Serializable
data class LoginPeticion(val email: String, val clave: String, val origen: String = "app")

@Serializable
data class RefrescoPeticion(val refresco: String)

@Serializable
data class Tokens(val acceso: String, val refresco: String)

@Serializable
data class LoginRespuesta(val acceso: String, val refresco: String, val usuario: Usuario)

@Serializable
data class Recinto(
    val id: Int,
    val codigo: String,
    val nombre: String,
    val carpetaImagenes: String = "",
    val umbralVacio: Double = 5.0
)

@Serializable
data class Usuario(
    val id: Int,
    val nombre: String,
    val apellido: String,
    val email: String,
    val rol: String,
    val debeCambiarClave: Boolean = false,
    val recintos: List<Recinto> = emptyList()
) {
    val nombreCompleto get() = "$nombre $apellido"
}

@Serializable
data class Conteos(
    val sinAsignar: Int = 0,
    val asignados: Int = 0,
    val enProgreso: Int = 0,
    val cerradosHoy: Int = 0,
    val activos: Int = 0
)

@Serializable
data class Bandeja(val total: Int = 0, val conteos: Conteos = Conteos(), val tickets: List<Ticket> = emptyList())

@Serializable
data class Ticket(
    val id: Long,
    val numero: String,
    val titulo: String,
    val estado: String,
    val prioridad: String,
    val origen: String,
    val porcentajeVacio: Double? = null,
    val productoFaltante: String? = null,
    val enriquecidoIa: Boolean = false,
    val recintoId: Int,
    val recintoCodigo: String = "",
    val gondolaId: Int? = null,
    val gondolaCodigo: String? = null,
    val pasillo: String? = null,
    val categoria: String? = null,
    val categoriaProducto: String? = null,
    val descripcion: String? = null,
    val asignadoA: Int? = null,
    val asignadoNombre: String? = null,
    val asignadoPorNombre: String? = null,
    val creadoPorNombre: String? = null,
    val creadoEn: String,
    val asignadoEn: String? = null,
    val cerradoEn: String? = null,
    val minutosAbierto: Int = 0,
    val numComentarios: Int = 0,
    val cierreVerificado: Boolean = false,
    val camaraCodigo: String? = null,
    val pctApertura: Double? = null,
    val pctCierre: Double? = null,
    val umbralVacio: Double = 5.0
)

@Serializable
data class Evidencia(
    val imagenId: Long,
    val tipo: String,
    val capturadaEn: String,
    val origen: String,
    val estadoImagen: String = "",
    val porcentajeVacio: Double? = null,
    val umbralAplicado: Double? = null,
    val superaUmbral: Boolean? = null,
    val numVacios: Int? = null,
    val url: String? = null,
    val urlAnotada: String? = null
)

@Serializable
data class Comentario(val id: Long, val usuarioId: Int, val nombre: String, val rol: String = "", val texto: String, val creadoEn: String)

@Serializable
data class EventoLinea(val en: String, val tipo: String, val texto: String)

@Serializable
data class ProductoIA(val producto: String, val categoria: String? = null, val confianza: Double? = null)

@Serializable
data class AnalisisIA(
    val proveedor: String = "",
    val modelo: String = "",
    val productosFaltantes: List<ProductoIA> = emptyList(),
    val resumen: String? = null,
    val exitoso: Boolean = true
)

@Serializable
data class Permisos(
    val asignar: Boolean = false,
    val editar: Boolean = false,
    val empezar: Boolean = false,
    val cerrar: Boolean = false,
    val cancelar: Boolean = false,
    val comentar: Boolean = false
)

@Serializable
data class DetalleTicket(
    val ticket: Ticket,
    val evidencias: List<Evidencia> = emptyList(),
    val comentarios: List<Comentario> = emptyList(),
    val lineaTiempo: List<EventoLinea> = emptyList(),
    val ia: AnalisisIA? = null,
    val iaPendiente: Boolean = false,
    val permisos: Permisos = Permisos()
)

@Serializable
data class Gondola(
    val id: Int,
    val codigo: String,
    val pasillo: String? = null,
    val categoria: String? = null,
    val descripcion: String? = null,
    val camaraCodigo: String? = null
) {
    val etiqueta get() = codigo + (categoria?.let { " · $it" } ?: "")
}

@Serializable
data class Prediccion(
    val porcentajeVacio: Double,
    val umbralAplicado: Double,
    val superaUmbral: Boolean,
    val numVacios: Int = 0,
    val tiempoInferenciaMs: Int? = null,
    val modelo: String? = null
)

/** Estado del análisis de IA de una foto: desactivada | pendiente | lista | error | no_aplica */
@Serializable
data class EstadoIA(val estado: String = "desactivada", val productos: List<ProductoIA> = emptyList())

@Serializable
data class TicketDeImagen(val numero: String, val tipo: String)

@Serializable
data class GondolaCorta(val id: Int, val codigo: String, val categoria: String? = null, val pasillo: String? = null)

@Serializable
data class Imagen(
    val id: Long,
    val recintoId: Int,
    val origen: String,
    val estado: String,
    val error: String? = null,
    val capturadaEn: String,
    val url: String? = null,
    val urlAnotada: String? = null,
    val gondola: GondolaCorta? = null,
    val prediccion: Prediccion? = null,
    val ia: EstadoIA = EstadoIA(),
    val ticket: TicketDeImagen? = null
) {
    val enAnalisis get() = estado == "PENDIENTE" || estado == "PROCESANDO"
}

@Serializable
data class ImagenSubida(val imagenId: Long)

@Serializable
data class NuevoTicket(
    val imagenId: Long,
    val titulo: String? = null,
    val productoFaltante: String? = null,
    val comentario: String? = null
)

@Serializable
data class CambioTicket(val estado: String? = null, val productoFaltante: String? = null)

@Serializable
data class Cierre(val comentario: String? = null)

@Serializable
data class NuevoComentario(val texto: String)

@Serializable
data class Dispositivo(val token: String, val plataforma: String = "ANDROID")

@Serializable
data class Notificacion(
    val id: Long,
    val tipo: String,
    val mensaje: String,
    val leida: Boolean,
    val creadaEn: String,
    val ticketNumero: String? = null
)

@Serializable
data class Notificaciones(val noLeidas: Int = 0, val notificaciones: List<Notificacion> = emptyList())

@Serializable
data class MarcaLeida(val leida: Boolean = true)

@Serializable
data class ErrorApi(val detail: String? = null)
