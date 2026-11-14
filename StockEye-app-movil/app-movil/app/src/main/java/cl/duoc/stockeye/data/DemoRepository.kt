package cl.duoc.stockeye.data

import kotlinx.coroutines.delay
import kotlin.random.Random

// datos de prueba mientras no tengamos el backend (clave 1234 para todos)
class DemoRepository : StockEyeRepository {

    private val ahora = System.currentTimeMillis()
    private fun haceMin(min: Int): Long = ahora - min * 60_000L

    private val listaUsuarios = listOf(
        Usuario(1, "Claudio Galiano", "reponedor", Rol.REPONEDOR, zona = "Pasillos 1 y 2"),
        Usuario(2, "Ignacio Ruz", "reponedor2", Rol.REPONEDOR, zona = "Pasillos 3 y 4"),
        Usuario(3, "Jesús González", "supervisor", Rol.SUPERVISOR),
        Usuario(4, "Benito", "admin", Rol.ADMINISTRADOR)
    )

    private var umbralesActuales = Umbrales()

    private val listaGondolas = mutableListOf(
        gondola(1, "G-101", "Lácteos", "refrigerador", 1, 1, 12, 10.0, 22.0, 75.0, 15.0),
        gondola(2, "G-102", "Yogures", "refrigerador", 1, 2, 12, 5.0, 12.0, 8.0, 20.0),
        gondola(3, "G-103", "Quesos", "refrigerador", 1, 3, 15, 18.0, null, 25.0),
        gondola(4, "G-201", "Bebidas", "estanteria", 2, 1, 20, 40.0, 12.0, 9.0, 15.0, 30.0),
        gondola(5, "G-202", "Jugos", "estanteria", 2, 2, 40, 82.0, 78.0, 20.0, 10.0),
        gondola(6, "G-203", "Aguas", "estanteria", 2, 3, 20, 5.0, 7.0, 12.0, 4.0),
        gondola(7, "G-301", "Snacks", "estanteria", 3, 1, 25, 14.0, 35.0, 9.0, 11.0),
        gondola(8, "G-302", "Galletas", "estanteria", 3, 2, 5, 6.0, 10.0, 15.0, 72.0),
        gondola(9, "G-303", "Cereales", "estanteria", 3, 3, 25, 11.0, 9.0, 13.0, 8.0),
        gondola(10, "G-401", "Limpieza", "estanteria", 4, 1, 30, 20.0, null, null, 15.0),
        gondola(11, "G-402", "Higiene", "estanteria", 4, 2, 30, 45.0, 50.0, 12.0, 18.0),
        gondola(12, "G-403", "Mascotas", "estanteria", 4, 3, 30, 9.0, 14.0, 7.0, 12.0)
    )

    private val listaAlertas = mutableListOf(
        // abiertas
        Alerta(1, gondolaId = 1, nivel = 3, pctVacio = 75.0, creadaEn = haceMin(12)),
        Alerta(
            2, gondolaId = 5, nivel = 1, pctVacio = 82.0, creadaEn = haceMin(40),
            estado = EstadoAlerta.EN_ATENCION, asignadaA = 1, atendidaEn = haceMin(25)
        ),
        Alerta(3, gondolaId = 5, nivel = 2, pctVacio = 78.0, creadaEn = haceMin(35), asignadaA = 2),
        Alerta(4, gondolaId = 8, nivel = 4, pctVacio = 72.0, creadaEn = haceMin(5), prioridad = Prioridad.MEDIA),
        // resueltas, para el reporte
        Alerta(
            5, gondolaId = 4, nivel = 1, pctVacio = 74.0, creadaEn = haceMin(300),
            estado = EstadoAlerta.RESUELTA, asignadaA = 1, atendidaEn = haceMin(285), resueltaEn = haceMin(260)
        ),
        Alerta(
            6, gondolaId = 7, nivel = 2, pctVacio = 80.0, creadaEn = haceMin(180),
            estado = EstadoAlerta.RESUELTA, asignadaA = 2, atendidaEn = haceMin(170), resueltaEn = haceMin(155)
        ),
        Alerta(
            7, gondolaId = 10, nivel = 1, pctVacio = 71.0, creadaEn = haceMin(120),
            estado = EstadoAlerta.RESUELTA, asignadaA = 1, atendidaEn = haceMin(112), resueltaEn = haceMin(100)
        )
    )

    override suspend fun login(usuario: String, clave: String): Usuario? {
        delay(400)
        return listaUsuarios.firstOrNull { it.usuario == usuario } ?.takeIf { clave == "1234" }
    }

    override suspend fun usuarios(): List<Usuario> = listaUsuarios.toList()

    override suspend fun gondolas(): List<Gondola> {
        simularVentas()
        return listaGondolas.toList()
    }

    override suspend fun alertas(): List<Alerta> = listaAlertas.toList()

    override suspend fun actualizarAlerta(alerta: Alerta) {
        val i = listaAlertas.indexOfFirst { it.id == alerta.id }
        if (i >= 0) listaAlertas[i] = alerta
        // solo demo: al resolver dejamos la repisa casi llena
        if (alerta.estado == EstadoAlerta.RESUELTA) reponerRepisa(alerta.gondolaId, alerta.nivel)
    }

    override suspend fun umbrales(): Umbrales = umbralesActuales

    override suspend fun guardarUmbrales(umbrales: Umbrales) {
        umbralesActuales = umbrales
        generarAlertasAutomaticas()
    }

    // solo demo: cada ~30s se "vende" producto de una repisa, asi la app se va moviendo
    private var ultimaVenta = System.currentTimeMillis()

    private fun simularVentas() {
        val ahora = System.currentTimeMillis()
        if (ahora - ultimaVenta < 25_000L) return
        ultimaVenta = ahora
        val candidatas = listaGondolas.flatMap { g ->
            g.repisas.filter { (it.pctVacio ?: 100.0) < 70.0 }.map { g.id to it.nivel }
        }
        if (candidatas.isEmpty()) return
        val (gid, nivel) = candidatas.random()
        val i = listaGondolas.indexOfFirst { it.id == gid }
        val g = listaGondolas[i]
        listaGondolas[i] = g.copy(
            ultimaFoto = ahora,
            repisas = g.repisas.map {
                if (it.nivel == nivel) it.copy(pctVacio = ((it.pctVacio ?: 0.0) + Random.nextInt(15, 35)).coerceAtMost(95.0)) else it
            }
        )
        generarAlertasAutomaticas()
    }

    // crea alertas para las repisas en rojo que no tengan una abierta
    private fun generarAlertasAutomaticas() {
        for (g in listaGondolas) for (r in g.repisas) {
            val pct = r.pctVacio ?: continue
            if (umbralesActuales.semaforo(pct) != Semaforo.ROJO) continue
            val yaExiste = listaAlertas.any {
                it.gondolaId == g.id && it.nivel == r.nivel && it.estado != EstadoAlerta.RESUELTA
            }
            if (!yaExiste) {
                val id = (listaAlertas.maxOfOrNull { it.id } ?: 0) + 1
                listaAlertas += Alerta(id, g.id, r.nivel, pct, System.currentTimeMillis())
            }
        }
    }

    private fun reponerRepisa(gondolaId: Int, nivel: Int) {
        val i = listaGondolas.indexOfFirst { it.id == gondolaId }
        if (i < 0) return
        val g = listaGondolas[i]
        listaGondolas[i] = g.copy(
            ultimaFoto = System.currentTimeMillis(),
            repisas = g.repisas.map {
                if (it.nivel == nivel) it.copy(pctVacio = 5.0, evidencia = Evidencia.NORMAL, nVacios = 1) else it
            }
        )
    }

    private fun gondola(
        id: Int, nombre: String, categoria: String, tipo: String,
        pasillo: Int, posicion: Int, minutosFoto: Int, vararg pct: Double?
    ): Gondola = Gondola(
        id = id,
        nombre = nombre,
        categoria = categoria,
        tipo = tipo,
        pasillo = pasillo,
        posicion = posicion,
        repisas = pct.mapIndexed { i, p ->
            Repisa(
                nivel = i + 1,
                pctVacio = p,
                evidencia = if (p == null) Evidencia.NINGUNA else Evidencia.NORMAL,
                nVacios = if (p == null) 0 else (p / 15).toInt() + 1
            )
        },
        ultimaFoto = haceMin(minutosFoto),
        segundosAnalisis = 2.12,
        versionModelo = "YOLO26-seg v5 (maestro_v3)"
    )
}
