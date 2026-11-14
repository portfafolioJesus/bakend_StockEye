"""Persistencia PostgreSQL real; no inicia API ni carga pesos entrenados."""
from pathlib import Path
import hashlib
import sqlite3

import pytest

from migrar_postgres import (ErrorMigracion, crear_snapshot, importar, leer_sqlite,
                             preparar_esquema, reubicar_copias, verificar)
from stockeye.procesador import Servicio
from stockeye.registro import Registro, InstanciaPerdida
from .conftest import MotorPrueba, foto, encolar


def registro_de(cfg):
    return Registro(cfg.base_datos.conexion_dsn())


def origen_sqlite(ruta):
    with sqlite3.connect(ruta) as db:
        db.executescript("""
        CREATE TABLE trabajos (
            secuencia INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT NOT NULL UNIQUE, sucursal_id INTEGER NOT NULL,
            relativo TEXT NOT NULL, nombre TEXT NOT NULL, sha256 TEXT NOT NULL,
            copia TEXT, estado TEXT NOT NULL, creado_en TEXT NOT NULL,
            iniciado_en TEXT, terminado_en TEXT, intentos INTEGER NOT NULL DEFAULT 0,
            error TEXT
        );
        CREATE TABLE observaciones (
            sucursal_id INTEGER, relativo TEXT, firma TEXT,
            visto_desde REAL, registrado INTEGER, PRIMARY KEY(sucursal_id,relativo)
        );
        """)
        for i, estado in enumerate(("pendiente", "procesando", "completada", "error"), 1):
            db.execute(
                "INSERT INTO trabajos(id,sucursal_id,relativo,nombre,sha256,copia,estado,"
                "creado_en,iniciado_en,terminado_en,intentos,error) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (f"{i:032x}", 1 if i < 3 else 2, f"foto{i}.jpg", f"foto{i}.jpg",
                 "rechazado:firma" if estado == "error" else "a" * 64,
                 None if estado == "error" else str(ruta.parent / f"copia{i}.jpg"),
                 estado, "2026-11-14T00:00:00+00:00",
                 "2026-11-14T00:01:00+00:00" if i > 1 else None,
                 "2026-11-14T00:02:00+00:00" if i > 2 else None,
                 i, "Error controlado" if estado == "error" else None),
            )
        db.executemany("INSERT INTO observaciones VALUES(?,?,?,?,?)",
                       [(1, "foto1.jpg", "10:20", 100.123456789, 1),
                        (2, "otra.png", "30:40", 999.987654321, 0)])
        db.execute("UPDATE sqlite_sequence SET seq=50 WHERE name='trabajos'")
    return ruta


def test_importacion_conserva_columnas_nulos_estados_y_secuencia(cfg, tmp_path):
    datos = leer_sqlite(origen_sqlite(tmp_path / "origen.sqlite3"))
    registro = registro_de(cfg)
    registro.adquirir_instancia()
    try:
        importar(registro, datos)
        verificar(registro, datos)
        assert registro.conteos() == {"pendiente": 1, "procesando": 1, "completada": 1, "error": 1}
        assert registro.obtener(f"{4:032x}")["error"] == "Error controlado"
        assert registro.encolar(ident="f"*32, sucursal=1, relativo="nueva.png",
                                sha256="b"*64, copia=None, firma="nueva")
        assert registro.obtener("f"*32)["secuencia"] == 51
    finally:
        registro.liberar_instancia()


def test_importador_no_sobrescribe_destino_y_revierte(cfg, tmp_path):
    datos = leer_sqlite(origen_sqlite(tmp_path / "origen.sqlite3"))
    registro = registro_de(cfg)
    registro.adquirir_instancia()
    try:
        importar(registro, datos)
        with pytest.raises(ErrorMigracion, match="no está vacío"):
            importar(registro, datos)
        verificar(registro, datos)
    finally:
        registro.liberar_instancia()


def test_snapshot_conserva_origen_y_rechaza_reemplazo(cfg, tmp_path):
    origen = origen_sqlite(tmp_path / "origen.sqlite3")
    antes = origen.read_bytes()
    destino = crear_snapshot(origen, tmp_path / "respaldo.sqlite3")
    assert leer_sqlite(destino) == leer_sqlite(origen)
    assert origen.read_bytes() == antes
    with pytest.raises(ErrorMigracion):
        crear_snapshot(origen, destino)
    assert origen.read_bytes() == antes


def test_migracion_aplicada_modificada_se_rechaza(cfg, tmp_path):
    registro = registro_de(cfg)
    carpeta = tmp_path / "migraciones"
    carpeta.mkdir()
    original = Path(__file__).resolve().parents[1] / "migraciones" / "001_cola.sql"
    (carpeta / original.name).write_bytes(original.read_bytes() + b"\n-- cambio no permitido\n")
    registro.adquirir_instancia()
    try:
        with pytest.raises(ErrorMigracion, match="fue modificada"):
            preparar_esquema(registro, carpeta)
        registro.comprobar_version_esquema()
    finally:
        registro.liberar_instancia()


def test_bloqueo_postgres_impide_segunda_sesion(cfg):
    a, b = registro_de(cfg), registro_de(cfg)
    a.adquirir_instancia()
    try:
        a.verificar_instancia()
        with pytest.raises(RuntimeError, match="Otro backend"):
            b.adquirir_instancia()
    finally:
        a.liberar_instancia()
    b.adquirir_instancia()
    try:
        b.verificar_instancia()
    finally:
        b.liberar_instancia()


def test_dos_carpetas_no_pueden_recuperar_la_misma_cola(cfg, tmp_path):
    otra = cfg.model_copy(deep=True)
    otra.datos = tmp_path / "datos-otra-carpeta"
    otra.crear_carpetas()
    a, b = Servicio(cfg, MotorPrueba), Servicio(otra, MotorPrueba)
    a.iniciar(ejecutar_hilos=False)
    try:
        with pytest.raises(RuntimeError, match="Otro backend"):
            b.iniciar(ejecutar_hilos=False)
    finally:
        a.detener()
        b.detener()


def test_perdida_de_exclusion_no_guarda_ni_confirma_trabajo(cfg, monkeypatch):
    foto(cfg.carpetas[1] / "foto.png")
    servicio = Servicio(cfg, MotorPrueba)
    encolar(servicio)
    servicio.cargar_motor()
    servicio.iniciar(ejecutar_hilos=False)
    perdida = [False]
    verificar_original = servicio.registro.verificar_instancia
    inferir_original = servicio.motor.inferir
    def inferir_y_perder(ruta):
        prediccion = inferir_original(ruta)
        perdida[0] = True
        return prediccion
    def perder_tras_inferencia():
        if perdida[0]:
            raise InstanciaPerdida("Simulación")
        verificar_original()
    monkeypatch.setattr(servicio.motor, "inferir", inferir_y_perder)
    monkeypatch.setattr(servicio.registro, "verificar_instancia", perder_tras_inferencia)
    try:
        assert servicio.procesar_uno() is False
        # Sesión independiente de lectura: la simulación dejó inválido el guard de la otra.
        trabajo = registro_de(cfg).listar()[0][0]
        assert trabajo["estado"] == "procesando"
        assert servicio.parar.is_set()
        assert not servicio.archivos.carpeta(trabajo["id"]).exists()
    finally:
        servicio.detener()


def test_reubicar_copias_conserva_origen_y_verifica_bytes(cfg, tmp_path):
    origen = origen_sqlite(tmp_path / "origen.sqlite3")
    for i in (1, 2):
        contenido = f"foto-controlada-{i}".encode()
        (cfg.temporales / f"copia{i}.jpg").write_bytes(contenido)
        with sqlite3.connect(origen) as db:
            db.execute("UPDATE trabajos SET sha256=? WHERE id=?",
                       (hashlib.sha256(contenido).hexdigest(), f"{i:032x}"))
    antes = origen.read_bytes()
    datos = leer_sqlite(origen)
    cambios = reubicar_copias(datos, cfg)
    assert len(cambios) == 2
    assert all(Path(f["copia"]).parent == cfg.temporales for f in datos["trabajos"][:2])
    assert origen.read_bytes() == antes
    registro = registro_de(cfg)
    registro.adquirir_instancia()
    try:
        importar(registro, datos)
        verificar(registro, datos)
    finally:
        registro.liberar_instancia()


def test_reubicar_rechaza_archivo_ausente_o_sha_distinto(cfg, tmp_path):
    origen = origen_sqlite(tmp_path / "origen.sqlite3")
    datos = leer_sqlite(origen)
    with pytest.raises(ErrorMigracion, match="Falta una copia"):
        reubicar_copias(datos, cfg)
    (cfg.temporales / "copia1.jpg").write_bytes(b"contenido-diferente")
    with pytest.raises(ErrorMigracion, match="SHA-256"):
        reubicar_copias(leer_sqlite(origen), cfg)
