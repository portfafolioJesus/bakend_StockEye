package cl.duoc.stockeye.push

import android.Manifest
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import cl.duoc.stockeye.MainActivity
import cl.duoc.stockeye.R
import cl.duoc.stockeye.StockEyeApp
import com.google.firebase.FirebaseApp
import com.google.firebase.messaging.FirebaseMessaging
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

/**
 * Recibe las notificaciones push que envía el microservicio "notificador"
 * (ticket asignado, comentario, alerta). Con la app en segundo plano Android
 * muestra la notificación solo; aquí se muestra cuando la app está abierta.
 */
class StockEyeMessagingService : FirebaseMessagingService() {
    private val alcance = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onNewToken(token: String) {
        val app = application as StockEyeApp
        alcance.launch { runCatching { app.repositorio.registrarPush(token) } }
    }

    override fun onMessageReceived(mensaje: RemoteMessage) {
        val titulo = mensaje.notification?.title ?: mensaje.data["titulo"] ?: "StockEye"
        val cuerpo = mensaje.notification?.body ?: mensaje.data["cuerpo"] ?: return
        mostrar(this, titulo, cuerpo, mensaje.data["numero"])
    }

    companion object {
        const val EXTRA_NUMERO = "numero"

        fun mostrar(context: Context, titulo: String, cuerpo: String, numero: String?) {
            if (Build.VERSION.SDK_INT >= 33 &&
                ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
            ) return
            val abrir = Intent(context, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
                numero?.let { putExtra(EXTRA_NUMERO, it) }
            }
            val pendiente = PendingIntent.getActivity(
                context, numero?.hashCode() ?: 0, abrir,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            val n = NotificationCompat.Builder(context, StockEyeApp.CANAL_TICKETS)
                .setSmallIcon(R.drawable.ic_launcher_foreground)
                .setContentTitle(titulo)
                .setContentText(cuerpo)
                .setStyle(NotificationCompat.BigTextStyle().bigText(cuerpo))
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setAutoCancel(true)
                .setContentIntent(pendiente)
                .build()
            NotificationManagerCompat.from(context).notify(numero?.hashCode() ?: System.currentTimeMillis().toInt(), n)
        }

        /** Registra el token FCM del celular en el backend (si Firebase está configurado). */
        fun registrarDispositivo(context: Context, alcance: CoroutineScope) {
            if (FirebaseApp.getApps(context).isEmpty()) return   // sin google-services.json
            val app = context.applicationContext as StockEyeApp
            FirebaseMessaging.getInstance().token.addOnSuccessListener { token ->
                alcance.launch(Dispatchers.IO) { runCatching { app.repositorio.registrarPush(token) } }
            }
        }
    }
}
