package cl.duoc.stockeye

import android.graphics.Color
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.lifecycle.viewmodel.compose.viewModel
import cl.duoc.stockeye.ui.StockEyeApp
import cl.duoc.stockeye.ui.StockEyeViewModel
import cl.duoc.stockeye.ui.theme.StockEyeTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // iconos blancos en la status bar porque el header es azul
        enableEdgeToEdge(statusBarStyle = SystemBarStyle.dark(Color.TRANSPARENT))
        setContent {
            StockEyeTheme {
                val vm: StockEyeViewModel = viewModel()
                StockEyeApp(vm)
            }
        }
    }
}
