package cl.duoc.stockeye.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import cl.duoc.stockeye.BuildConfig
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking

private val Context.almacen by preferencesDataStore(name = "sesion")

/**
 * Tokens y dirección del servidor. Se guardan en DataStore y se mantienen en
 * memoria para que el interceptor HTTP no tenga que leer disco en cada llamada.
 */
class Sesion(private val context: Context) {
    private object Claves {
        val acceso = stringPreferencesKey("acceso")
        val refresco = stringPreferencesKey("refresco")
        val servidor = stringPreferencesKey("servidor")
        val tokenPush = stringPreferencesKey("token_push")
    }

    @Volatile var acceso: String? = null
        private set
    @Volatile var refresco: String? = null
        private set
    @Volatile var servidor: String = BuildConfig.API_URL
        private set

    init {
        // Una sola lectura al iniciar la app (antes de la primera llamada a la API)
        runBlocking {
            val p = context.almacen.data.first()
            acceso = p[Claves.acceso]
            refresco = p[Claves.refresco]
            servidor = p[Claves.servidor] ?: BuildConfig.API_URL
        }
    }

    val iniciada get() = refresco != null

    suspend fun guardarTokens(nuevoAcceso: String, nuevoRefresco: String) {
        acceso = nuevoAcceso
        refresco = nuevoRefresco
        context.almacen.edit {
            it[Claves.acceso] = nuevoAcceso
            it[Claves.refresco] = nuevoRefresco
        }
    }

    fun guardarTokensBloqueante(nuevoAcceso: String, nuevoRefresco: String) =
        runBlocking { guardarTokens(nuevoAcceso, nuevoRefresco) }

    suspend fun cambiarServidor(url: String) {
        val limpia = url.trim().let { if (it.endsWith("/")) it else "$it/" }
        servidor = limpia
        context.almacen.edit { it[Claves.servidor] = limpia }
    }

    suspend fun tokenPush(): String? = context.almacen.data.first()[Claves.tokenPush]

    suspend fun guardarTokenPush(token: String) {
        context.almacen.edit { it[Claves.tokenPush] = token }
    }

    suspend fun cerrar() {
        acceso = null
        refresco = null
        context.almacen.edit {
            it.remove(Claves.acceso)
            it.remove(Claves.refresco)
        }
    }
}
