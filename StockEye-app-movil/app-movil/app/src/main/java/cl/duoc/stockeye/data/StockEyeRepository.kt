package cl.duoc.stockeye.data

// cuando este la API se hace un ApiRepository con esto mismo
interface StockEyeRepository {
    suspend fun login(usuario: String, clave: String): Usuario?
    suspend fun usuarios(): List<Usuario>
    suspend fun gondolas(): List<Gondola>
    suspend fun alertas(): List<Alerta>
    suspend fun actualizarAlerta(alerta: Alerta)
    suspend fun umbrales(): Umbrales
    suspend fun guardarUmbrales(umbrales: Umbrales)
}
