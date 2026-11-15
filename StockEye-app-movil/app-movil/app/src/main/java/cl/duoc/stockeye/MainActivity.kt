package cl.duoc.stockeye

import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.mutableStateOf
import cl.duoc.stockeye.push.StockEyeMessagingService
import cl.duoc.stockeye.ui.StockEyeNavegacion
import cl.duoc.stockeye.ui.theme.StockEyeTheme

class MainActivity : ComponentActivity() {
    // ticket que llegó en una notificación push (se abre al tocarla)
    private val ticketDesdePush = mutableStateOf<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(statusBarStyle = SystemBarStyle.light(Color.TRANSPARENT, Color.TRANSPARENT))
        ticketDesdePush.value = intent.numeroDeTicket()
        setContent {
            StockEyeTheme {
                StockEyeNavegacion(
                    ticketPendiente = ticketDesdePush.value,
                    alAbrirTicketPendiente = { ticketDesdePush.value = null }
                )
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        intent.numeroDeTicket()?.let { ticketDesdePush.value = it }
    }

    private fun Intent.numeroDeTicket(): String? = getStringExtra(StockEyeMessagingService.EXTRA_NUMERO)
}
