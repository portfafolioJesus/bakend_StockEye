package cl.duoc.stockeye.data

import okhttp3.MultipartBody
import okhttp3.RequestBody
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query

/** Endpoints que usa la app del reponedor (ver docs/API.md del backend). */
interface StockEyeApi {
    @POST("api/v1/auth/login")
    suspend fun login(@Body datos: LoginPeticion): LoginRespuesta

    @GET("api/v1/auth/yo")
    suspend fun yo(): Usuario

    @GET("api/v1/tickets")
    suspend fun tickets(@Query("vista") vista: String, @Query("limite") limite: Int): Bandeja

    @GET("api/v1/tickets/{numero}")
    suspend fun ticket(@Path("numero") numero: String): DetalleTicket

    @POST("api/v1/tickets")
    suspend fun crearTicket(@Body datos: NuevoTicket): DetalleTicket

    @PATCH("api/v1/tickets/{numero}")
    suspend fun editarTicket(@Path("numero") numero: String, @Body datos: CambioTicket): DetalleTicket

    @POST("api/v1/tickets/{numero}/comentarios")
    suspend fun comentar(@Path("numero") numero: String, @Body datos: NuevoComentario): Comentario

    @Multipart
    @POST("api/v1/tickets/{numero}/cierre")
    suspend fun fotoCierre(@Path("numero") numero: String, @Part foto: MultipartBody.Part): ImagenSubida

    @POST("api/v1/tickets/{numero}/cerrar")
    suspend fun cerrar(@Path("numero") numero: String, @Body datos: Cierre): DetalleTicket

    @Multipart
    @POST("api/v1/imagenes")
    suspend fun subirFoto(@Part foto: MultipartBody.Part, @Part("gondola_id") gondolaId: RequestBody): ImagenSubida

    @GET("api/v1/imagenes/{id}")
    suspend fun imagen(@Path("id") id: Long): Imagen

    @GET("api/v1/recintos/{id}/gondolas")
    suspend fun gondolas(@Path("id") recintoId: Int): List<Gondola>

    @GET("api/v1/notificaciones")
    suspend fun notificaciones(@Query("limite") limite: Int): Notificaciones

    @PATCH("api/v1/notificaciones/{id}")
    suspend fun marcarLeida(@Path("id") id: Long, @Body datos: MarcaLeida): Unit

    @POST("api/v1/dispositivos")
    suspend fun registrarDispositivo(@Body datos: Dispositivo): Unit

    @DELETE("api/v1/dispositivos/{token}")
    suspend fun eliminarDispositivo(@Path("token") token: String): Unit
}
