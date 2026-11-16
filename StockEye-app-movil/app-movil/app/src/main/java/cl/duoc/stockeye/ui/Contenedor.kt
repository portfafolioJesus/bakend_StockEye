package cl.duoc.stockeye.ui

import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext
import cl.duoc.stockeye.StockEyeApp
import cl.duoc.stockeye.data.Repositorio

/** Acceso al repositorio desde las pantallas. */
@Composable
fun repositorio(): Repositorio = (LocalContext.current.applicationContext as StockEyeApp).repositorio
