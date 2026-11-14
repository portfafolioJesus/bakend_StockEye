package cl.duoc.stockeye.data

// nombres parecidos al json que sale de la celda 8.2

enum class Rol(val etiqueta: String) {
    REPONEDOR("Reponedor"),
    SUPERVISOR("Supervisor"),
    ADMINISTRADOR("Administrador")
}

data class Usuario(
    val id: Int,
    val nombre: String,
    val usuario: String,
    val rol: Rol,
    val zona: String? = null
)

enum class Semaforo(val etiqueta: String) {
    VERDE("Bien surtido"),
    AMARILLO("A medias"),
    ROJO("Falta producto"),
    INDETERMINADO("Revisar")
}

// misma regla que el notebook: stock = 100 - % vacio
data class Umbrales(
    val stockVerde: Int = 70,
    val stockRojo: Int = 30
) {
    fun semaforo(pctVacio: Double?): Semaforo {
        if (pctVacio == null || pctVacio.isNaN()) return Semaforo.INDETERMINADO
        val stock = 100.0 - pctVacio
        return when {
            stock >= stockVerde -> Semaforo.VERDE
            stock < stockRojo -> Semaforo.ROJO
            else -> Semaforo.AMARILLO
        }
    }
}

enum class Evidencia { NORMAL, RESCATE, NORMAL_RESCATE, SOLO_DUDOSA, NINGUNA }

data class Repisa(
    val nivel: Int,              // 1 = arriba
    val pctVacio: Double?,       // null = sin deteccion
    val evidencia: Evidencia,
    val nVacios: Int,
    val nDudosos: Int = 0
) {
    val medida: Boolean get() = pctVacio != null
}

data class Gondola(
    val id: Int,
    val nombre: String,
    val categoria: String,
    val tipo: String,
    val pasillo: Int,
    val posicion: Int,
    val repisas: List<Repisa>,
    val ultimaFoto: Long,
    val segundosAnalisis: Double,
    val versionModelo: String
)

enum class EstadoAlerta(val etiqueta: String) {
    NUEVA("Nuevas"),
    EN_ATENCION("En curso"),
    RESUELTA("Listas")
}

enum class Prioridad(val etiqueta: String) {
    ALTA("Alta"),
    MEDIA("Media"),
    BAJA("Baja")
}

data class Alerta(
    val id: Int,
    val gondolaId: Int,
    val nivel: Int,
    val pctVacio: Double,
    val creadaEn: Long,
    val estado: EstadoAlerta = EstadoAlerta.NUEVA,
    val asignadaA: Int? = null,
    val prioridad: Prioridad = Prioridad.ALTA,
    val atendidaEn: Long? = null,
    val resueltaEn: Long? = null
)
