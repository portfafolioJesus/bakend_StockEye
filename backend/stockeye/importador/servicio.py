"""Microservicio importador: fotos reales dejadas en una carpeta.

    entradas/
      R01/                              ← código del recinto
        Lácteos y huevos/               ← categoría (como los departamentos de Walmart)
          foto1.jpg                     ← reporte independiente: cada foto sobre el
          foto2.jpg                       umbral abre su propio ticket
          Yogures/                      ← (opcional) PUNTO FIJO dentro de la categoría:
            foto3.jpg                     la 2ª foto del mismo punto es SEGUIMIENTO
          _procesadas/  _rechazadas/    ← el importador mueve aquí lo que ya cargó / no pudo

Las carpetas de cada recinto y categoría se crean solas. Las de punto fijo las
creas tú y el punto aparece solo en el sistema. También se aceptan carpetas con
el código de una góndola existente (ej. R01/P04-G01/) por compatibilidad.
"""
from __future__ import annotations

import logging
import shutil
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

from ..core.config import Ajustes
from ..core.db import conectar, tx_sync
from ..core.fotos import (EXTENSIONES, SQL_IMAGEN_CARGA, SQL_IMAGEN_CARGA_CATEGORIA, FotoInvalida, guardar,
                          normalizar, normalizar_texto, slug)

log = logging.getLogger("stockeye.importador")
PROCESADAS, RECHAZADAS = "_procesadas", "_rechazadas"
LEEME = """Carpeta de entrada de StockEye
================================
Deja las fotos en  <RECINTO>/<CATEGORÍA>/   ej.:  R01/Lácteos y huevos/foto.jpg

  * Cada foto se analiza con el modelo. Si el % de vacío supera el umbral del recinto
    se abre un ticket de esa categoría (cada foto es un reporte independiente).
  * Si siempre fotografías el MISMO lugar (p. ej. una cámara fija), crea una subcarpeta
    para ese punto:  R01/Lácteos y huevos/Yogures/foto.jpg  → las fotos siguientes de ese
    punto se suman al ticket abierto como seguimiento, en vez de abrir uno nuevo.
  * Formatos: JPEG, PNG o WEBP (hasta 15 MB). Las fotos HEIC de iPhone: expórtalas a JPEG.
  * Las fotos cargadas pasan a _procesadas/ y las que fallan a _rechazadas/ (con el motivo).
  * La fecha de la foto es la de modificación del archivo.
  * Las carpetas de categorías se crean solas; las categorías se administran en el panel.
"""


class Importador:
    def __init__(self, a: Ajustes, carpeta: Path | None = None, espera_estable_s: float = 2.0):
        self.a = a
        self.raiz = Path(carpeta or a.entradas_dir)
        self.espera = espera_estable_s
        self.conn = conectar(a.database_url)
        self.detener = False
        self.importadas = 0
        self._avisadas: set[Path] = set()

    # ------------------------------------------------------------ catálogo
    def _catalogo(self) -> tuple[list[dict], list[dict], list[dict]]:
        with tx_sync(self.conn):
            recintos = self.conn.execute("""SELECT id, codigo, carpeta_imagenes FROM recinto
                                             WHERE activo ORDER BY codigo""").fetchall()
            categorias = self.conn.execute("""SELECT id, codigo, nombre FROM categoria
                                               WHERE activo ORDER BY orden, nombre""").fetchall()
            gondolas = self.conn.execute("""SELECT id, recinto_id, codigo FROM gondola WHERE activo""").fetchall()
        return recintos, categorias, gondolas

    @staticmethod
    def _categoria_de(nombre_carpeta: str, categorias: list[dict]) -> dict | None:
        n = normalizar_texto(nombre_carpeta)
        for c in categorias:
            if n in (normalizar_texto(c["nombre"]), normalizar_texto(c["codigo"])):
                return c
        return next((c for c in categorias if normalizar_texto(c["nombre"]).startswith(n + " ")), None)

    def preparar_carpetas(self, recintos: list[dict], categorias: list[dict]) -> None:
        self.raiz.mkdir(parents=True, exist_ok=True)
        leeme = self.raiz / "LEEME.txt"
        if not leeme.exists():
            leeme.write_text(LEEME, encoding="utf-8")
        for r in recintos:
            carpeta = self.raiz / r["codigo"]
            existentes = {normalizar_texto(p.name) for p in carpeta.iterdir()} if carpeta.is_dir() else set()
            for c in categorias:
                # no duplicar si el usuario ya creó la carpeta con otro nombre equivalente ("Lacteos")
                if normalizar_texto(c["nombre"]) not in existentes and normalizar_texto(c["codigo"]) not in existentes:
                    (carpeta / c["nombre"]).mkdir(parents=True, exist_ok=True)

    def _punto_fijo(self, recinto: dict, categoria: dict, nombre: str) -> int:
        """Crea (o reutiliza) el punto fijo de una subcarpeta: góndola con su categoría."""
        codigo = slug(f"{categoria['codigo']}-{nombre}", 20)
        with tx_sync(self.conn):
            return self.conn.execute("""
                INSERT INTO gondola (recinto_id, codigo, categoria_id, descripcion)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (recinto_id, codigo) DO UPDATE SET activo = TRUE
                RETURNING id""", [recinto["id"], codigo, categoria["id"], nombre[:200]]).fetchone()["id"]

    # ------------------------------------------------------------ carga
    def _estable(self, archivo: Path) -> bool:
        """Evita tomar una foto que todavía se está copiando."""
        try:
            info = archivo.stat()
        except FileNotFoundError:
            return False
        return info.st_size > 0 and time.time() - info.st_mtime >= self.espera

    @staticmethod
    def _mover(archivo: Path, subcarpeta: str, motivo: str | None = None) -> None:
        destino = archivo.parent / subcarpeta / datetime.now().strftime("%Y-%m-%d")
        destino.mkdir(parents=True, exist_ok=True)
        final = destino / archivo.name
        if final.exists():
            final = destino / f"{archivo.stem}_{int(time.time())}{archivo.suffix}"
        shutil.move(str(archivo), final)
        if motivo:
            final.with_suffix(final.suffix + ".txt").write_text(motivo + "\n", encoding="utf-8")

    def importar(self, archivo: Path, recinto: dict, *, gondola_id: int | None = None,
                 categoria: dict | None = None, prefijo: str = "carga") -> int | None:
        capturada = datetime.fromtimestamp(archivo.stat().st_mtime, tz=timezone.utc)
        try:
            foto = normalizar(archivo.read_bytes())
        except FotoInvalida as e:
            log.warning("%s rechazada: %s", archivo, e)
            self._mover(archivo, RECHAZADAS, str(e))
            return None
        ruta = guardar(foto, recinto["carpeta_imagenes"], prefijo, capturada)
        with tx_sync(self.conn):
            if gondola_id:
                fila = self.conn.execute(SQL_IMAGEN_CARGA, [ruta, foto.sha256, foto.ancho, foto.alto, capturada,
                                                            gondola_id]).fetchone()
            else:
                fila = self.conn.execute(SQL_IMAGEN_CARGA_CATEGORIA, [recinto["id"], recinto["id"], categoria["id"], ruta,
                                                                      foto.sha256, foto.ancho, foto.alto, capturada]).fetchone()
            self.conn.execute("UPDATE camara SET ultima_captura = now() WHERE id = %s", [fila["camara_id"]])
        self._mover(archivo, PROCESADAS)
        self.importadas += 1
        log.info("%s → imagen %s (%s)", archivo.relative_to(self.raiz), fila["id"], ruta)
        return fila["id"]

    def _fotos(self, carpeta: Path):
        for archivo in sorted(carpeta.iterdir(), key=lambda p: p.name):
            if not archivo.is_file() or archivo.name.startswith("."):
                continue
            if archivo.suffix.lower() in (".heic", ".heif"):
                self._mover(archivo, RECHAZADAS, "Formato HEIC no admitido: exporta la foto como JPEG")
            elif archivo.suffix.lower() in EXTENSIONES and self._estable(archivo):
                yield archivo

    def _cargar(self, carpeta: Path, recinto: dict, **destino) -> int:
        n = 0
        for archivo in self._fotos(carpeta):
            if self.detener:
                break
            try:
                if self.importar(archivo, recinto, **destino):
                    n += 1
            except Exception as e:     # BD caída, disco lleno…: se reintenta en la próxima vuelta
                log.error("No se pudo importar %s: %s", archivo, e)
                if self.conn.info.transaction_status != 0:
                    self.conn.rollback()
        return n

    def revisar(self) -> int:
        recintos, categorias, gondolas = self._catalogo()
        self.preparar_carpetas(recintos, categorias)
        n = 0
        for r in recintos:
            carpeta_r = self.raiz / r["codigo"]
            por_codigo = {g["codigo"].upper(): g for g in gondolas if g["recinto_id"] == r["id"]}
            for sub in sorted(p for p in carpeta_r.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))):
                cat = self._categoria_de(sub.name, categorias)
                if cat:
                    n += self._cargar(sub, r, categoria=cat, prefijo=cat["codigo"])
                    for punto in sorted(p for p in sub.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))):
                        if any(self._fotos(punto)):
                            gid = self._punto_fijo(r, cat, punto.name)
                            n += self._cargar(punto, r, gondola_id=gid, prefijo=slug(f"{cat['codigo']}-{punto.name}"))
                elif sub.name.upper() in por_codigo:          # compatibilidad: carpeta con código de góndola
                    g = por_codigo[sub.name.upper()]
                    n += self._cargar(sub, r, gondola_id=g["id"], prefijo=g["codigo"])
                elif sub not in self._avisadas:
                    self._avisadas.add(sub)
                    log.warning("Carpeta %s no corresponde a una categoría ni góndola de %s: se ignora",
                                sub.relative_to(self.raiz), r["codigo"])
        return n

    def correr(self) -> None:
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "detener", True))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "detener", True))
        log.info("Importador vigilando %s (cada %ss)", self.raiz, self.a.importador_intervalo_s)
        while not self.detener:
            try:
                self.revisar()
            except Exception:
                log.exception("Error revisando la carpeta de entrada")
                if self.conn.info.transaction_status != 0:
                    self.conn.rollback()
                time.sleep(5)
            for _ in range(int(self.a.importador_intervalo_s * 10)):
                if self.detener:
                    break
                time.sleep(0.1)
        log.info("Importador detenido (%s fotos importadas)", self.importadas)
        self.conn.close()
