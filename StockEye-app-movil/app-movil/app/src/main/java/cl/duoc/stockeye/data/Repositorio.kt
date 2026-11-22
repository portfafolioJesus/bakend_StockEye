package cl.duoc.stockeye.data

import cl.duoc.stockeye.BuildConfig
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNamingStrategy
import okhttp3.Authenticator
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.Route
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.HttpException
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.io.IOException
import java.util.concurrent.TimeUnit

@OptIn(ExperimentalSerializationApi::class)
val json = Json {
    ignoreUnknownKeys = true
    explicitNulls = false
    coerceInputValues = true
    namingStrategy = JsonNamingStrategy.SnakeCase
}

/** Error con un mensaje listo para mostrar al reponedor. */
class ErrorStockEye(mensaje: String, val codigo: Int = 0) : Exception(mensaje)

/**
 * Único punto de acceso al backend. Agrega el JWT, lo renueva solo cuando
 * vence (401 → /auth/refresco) y traduce los errores a mensajes en español.
 */
class Repositorio(private val sesion: Sesion) {
    private val _sesionExpirada = MutableSharedFlow<Unit>(extraBufferCapacity = 1)
    val sesionExpirada: SharedFlow<Unit> = _sesionExpirada

    private var urlActual: String = ""
    private var apiActual: StockEyeApi? = null
    private val tipoJson = "application/json".toMediaType()

    private val autenticacion = Interceptor { cadena ->
        val token = sesion.acceso
        val peticion = cadena.request().newBuilder().apply {
            if (token != null) header("Authorization", "Bearer $token")
        }.build()
        cadena.proceed(peticion)
    }

    /** Ante un 401 intenta una vez renovar el token con el refresco. */
    private val renovador = object : Authenticator {
        override fun authenticate(route: Route?, response: Response): Request? {
            if (response.request.url.encodedPath.contains("/auth/")) return null
            if (response.priorResponse != null) return null      // ya se intentó
            val refresco = sesion.refresco ?: return null
            synchronized(this) {
                // otro hilo pudo renovarlo mientras esperábamos
                val actual = sesion.acceso
                if (actual != null && response.request.header("Authorization") != "Bearer $actual") {
                    return response.request.newBuilder().header("Authorization", "Bearer $actual").build()
                }
                val cuerpo = json.encodeToString(RefrescoPeticion.serializer(), RefrescoPeticion(refresco))
                val pedido = Request.Builder().url(sesion.servidor + "api/v1/auth/refresco")
                    .post(cuerpo.toRequestBody(tipoJson)).build()
                val r = try { clienteBase.newCall(pedido).execute() } catch (e: IOException) { return null }
                r.use {
                    if (!it.isSuccessful) {
                        _sesionExpirada.tryEmit(Unit)
                        return null
                    }
                    val t = json.decodeFromString(Tokens.serializer(), it.body!!.string())
                    sesion.guardarTokensBloqueante(t.acceso, t.refresco)
                    return response.request.newBuilder().header("Authorization", "Bearer ${t.acceso}").build()
                }
            }
        }
    }

    private val clienteBase = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)            // fotos de varios MB por redes móviles
        .build()

    private val cliente = clienteBase.newBuilder()
        .addInterceptor(autenticacion)
        .authenticator(renovador)
        .apply {
            if (BuildConfig.DEBUG) addInterceptor(HttpLoggingInterceptor().apply { level = HttpLoggingInterceptor.Level.BASIC })
        }
        .build()

    val clienteImagenes: OkHttpClient get() = cliente

    private fun api(): StockEyeApi {
        val url = sesion.servidor
        if (apiActual == null || url != urlActual) {
            apiActual = Retrofit.Builder()
                .baseUrl(url)
                .client(cliente)
                .addConverterFactory(json.asConverterFactory(tipoJson))
                .build()
                .create(StockEyeApi::class.java)
            urlActual = url
        }
        return apiActual!!
    }

    /** URL absoluta para Coil a partir de las rutas firmadas que entrega la API. */
    fun urlAbsoluta(ruta: String?): String? = ruta?.let { sesion.servidor.trimEnd('/') + it }

    private suspend fun <T> llamar(bloque: suspend StockEyeApi.() -> T): T = try {
        api().bloque()
    } catch (e: HttpException) {
        val detalle = e.response()?.errorBody()?.string()?.let {
            runCatching { json.decodeFromString(ErrorApi.serializer(), it).detail }.getOrNull()
        }
        if (e.code() == 401) _sesionExpirada.tryEmit(Unit)
        throw ErrorStockEye(detalle ?: "Error ${e.code()} del servidor", e.code())
    } catch (e: IOException) {
        throw ErrorStockEye("Sin conexión con el servidor (${sesion.servidor}). Revisa el WiFi o los datos.")
    }

    // ---- sesión
    suspend fun ingresar(email: String, clave: String): Usuario {
        val r = llamar { login(LoginPeticion(email.trim(), clave)) }
        sesion.guardarTokens(r.acceso, r.refresco)
        return r.usuario
    }

    suspend fun yo(): Usuario = llamar { yo() }

    suspend fun salir() {
        sesion.tokenPush()?.let { token -> runCatching { llamar { eliminarDispositivo(token) } } }
        sesion.cerrar()
    }

    suspend fun registrarPush(token: String) {
        sesion.guardarTokenPush(token)
        if (sesion.iniciada) llamar { registrarDispositivo(Dispositivo(token)) }
    }

    // ---- tickets
    suspend fun misTickets(vista: String): Bandeja = llamar { tickets(vista, 100) }
    suspend fun ticket(numero: String): DetalleTicket = llamar { ticket(numero) }
    suspend fun empezar(numero: String): DetalleTicket = llamar { editarTicket(numero, CambioTicket(estado = "EN_PROGRESO")) }
    suspend fun comentar(numero: String, texto: String): Comentario = llamar { comentar(numero, NuevoComentario(texto)) }
    suspend fun cerrar(numero: String, comentario: String?): DetalleTicket =
        llamar { cerrar(numero, Cierre(comentario?.takeIf { it.isNotBlank() })) }

    suspend fun crearTicket(imagenId: Long, titulo: String, producto: String, comentario: String): DetalleTicket =
        llamar {
            crearTicket(NuevoTicket(imagenId, titulo.ifBlank { null }, producto.ifBlank { null }, comentario.ifBlank { null }))
        }

    // ---- fotos
    private fun parte(jpeg: ByteArray) =
        MultipartBody.Part.createFormData("foto", "foto.jpg", jpeg.toRequestBody("image/jpeg".toMediaType()))

    suspend fun subirFoto(gondolaId: Int, jpeg: ByteArray): Long =
        llamar { subirFoto(parte(jpeg), gondolaId.toString().toRequestBody("text/plain".toMediaType())) }.imagenId

    suspend fun subirFotoCierre(numero: String, jpeg: ByteArray): Long = llamar { fotoCierre(numero, parte(jpeg)) }.imagenId

    suspend fun imagen(id: Long): Imagen = llamar { imagen(id) }
    suspend fun gondolas(recintoId: Int): List<Gondola> = llamar { gondolas(recintoId) }

    // ---- notificaciones
    suspend fun notificaciones(): Notificaciones = llamar { notificaciones(50) }
    suspend fun marcarLeida(id: Long): Unit = llamar { marcarLeida(id, MarcaLeida()) }
}
