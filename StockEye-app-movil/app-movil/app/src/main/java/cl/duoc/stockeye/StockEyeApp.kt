package cl.duoc.stockeye

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import cl.duoc.stockeye.data.Repositorio
import cl.duoc.stockeye.data.Sesion
import coil.ImageLoader
import coil.ImageLoaderFactory

/** Contenedor de dependencias de la app (sin framework de inyección). */
class StockEyeApp : Application(), ImageLoaderFactory {
    lateinit var sesion: Sesion
        private set
    lateinit var repositorio: Repositorio
        private set

    override fun onCreate() {
        super.onCreate()
        sesion = Sesion(this)
        repositorio = Repositorio(sesion)
        crearCanal()
    }

    // Coil usa el mismo cliente HTTP (las fotos vienen de URLs firmadas de la API)
    override fun newImageLoader(): ImageLoader =
        ImageLoader.Builder(this).okHttpClient { repositorio.clienteImagenes }.crossfade(true).build()

    private fun crearCanal() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val canal = NotificationChannel(CANAL_TICKETS, "Tickets", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "Tickets asignados, comentarios y alertas de vacío"
            }
            getSystemService(NotificationManager::class.java).createNotificationChannel(canal)
        }
    }

    companion object {
        const val CANAL_TICKETS = "tickets"
    }
}
