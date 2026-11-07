from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
import threading
import time
import uuid

from .archivos import Archivos
from .configuracion import Configuracion
from .instancia import InstanciaUnica
from .motor import MotorSegFormer
from .registro import Registro, ahora

log = logging.getLogger("stockeye")
EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


class EntradaInestable(Exception):
    pass


class Revisor:
    def __init__(self, cfg: Configuracion, registro: Registro):
        self.cfg, self.registro = cfg, registro
        self.ultima_revision = None
        self.ultimo_error = None

    def _copiar(self, origen: Path, destino: Path, esperado) -> str:
        h = hashlib.sha256()
        total = 0
        temporal = destino.with_suffix(destino.suffix + ".tmp")
        try:
            if origen.is_symlink(): raise EntradaInestable("Entrada simbólica omitida.")
            with origen.open("rb") as entrada, temporal.open("xb") as salida:
                while bloque := entrada.read(1024 * 1024):
                    total += len(bloque)
                    if total > self.cfg.limites.max_archivo_mb * 1024**2:
                        raise ValueError("La imagen supera max_archivo_mb.")
                    h.update(bloque); salida.write(bloque)
                salida.flush(); os.fsync(salida.fileno())
            final = origen.stat()
            if (final.st_size, final.st_mtime_ns) != (esperado.st_size, esperado.st_mtime_ns) or total != esperado.st_size:
                raise EntradaInestable("El archivo sigue cambiando; se revisará después.")
            temporal.replace(destino)
            return h.hexdigest()
        finally:
            temporal.unlink(missing_ok=True)

    def revisar(self, tiempo: float | None = None) -> int:
        momento = time.time() if tiempo is None else tiempo
        nuevos = 0
        errores = []
        candidatos = []
        for sucursal, raiz in self.cfg.carpetas.items():
            presentes = set()
            try:
                # Carpetas planas, una por sucursal: no se siguen subcarpetas ni enlaces.
                for archivo in raiz.iterdir():
                    if archivo.suffix.lower() not in EXTENSIONES or archivo.is_symlink() or not archivo.is_file(): continue
                    relativo = archivo.name; presentes.add(relativo)
                    st = archivo.stat()
                    if st.st_size == 0: continue
                    firma = f"{st.st_size}:{st.st_mtime_ns}"
                    if self.registro.estable(sucursal, relativo, firma, momento, self.cfg.estabilidad_segundos):
                        candidatos.append((st.st_mtime_ns, sucursal, relativo, archivo, st, firma))
                self.registro.olvidar_ausentes(sucursal, presentes)
            except OSError as error:
                errores.append(f"Sucursal {sucursal}: {type(error).__name__}")
                log.warning("No se pudo revisar Sucursal %s: %s", sucursal, error)
        for _, sucursal, relativo, archivo, st, firma in sorted(candidatos, key=lambda x: x[:3]):
            ident = uuid.uuid4().hex
            copia = self.cfg.temporales / (ident + archivo.suffix.lower())
            try:
                sha = self._copiar(archivo, copia, st)
                insertado = self.registro.encolar(ident=ident, sucursal=sucursal, relativo=relativo,
                    sha256=sha, copia=str(copia), firma=firma)
                if insertado:
                    nuevos += 1
                    log.info("Encolada Sucursal %s: %s", sucursal, relativo)
                else:
                    copia.unlink(missing_ok=True)
            except EntradaInestable:
                copia.unlink(missing_ok=True)
            except ValueError as error:
                # Un exceso de tamaño se registra sin copiar una entrada ilimitada.
                self.registro.encolar(ident=ident, sucursal=sucursal, relativo=relativo,
                    sha256="rechazado:" + firma, copia=None, firma=firma, error=str(error))
                copia.unlink(missing_ok=True)
            except OSError as error:
                copia.unlink(missing_ok=True)
                errores.append(f"{relativo}: {type(error).__name__}")
                log.warning("No se pudo copiar %s: %s", relativo, error)
        self.ultima_revision = ahora()
        self.ultimo_error = "; ".join(errores) or None
        return nuevos


class Servicio:
    def __init__(self, cfg: Configuracion, motor_factory=MotorSegFormer):
        self.cfg = cfg
        cfg.crear_carpetas()
        self.registro = Registro(cfg.datos / "cola.sqlite3")
        self.archivos = Archivos(cfg.resultados)
        self.revisor = Revisor(cfg, self.registro)
        self.motor_factory = motor_factory
        self.motor = None
        self.error_modelo = None
        self.cargando_modelo = False
        self.parar = threading.Event()
        self.hilos = []
        self.instancia = InstanciaUnica(cfg.datos / "backend.lock")

    def cargar_motor(self):
        self.cargando_modelo = True
        try:
            self.motor = self.motor_factory(self.cfg)
            self.error_modelo = None
            log.info("Modelo cargado: %s", self.motor.version)
        except Exception as error:
            self.motor = None
            self.error_modelo = f"{type(error).__name__}: {error}"
            log.error("No se iniciará inferencia: %s", self.error_modelo)
        finally:
            self.cargando_modelo = False

    def procesar_uno(self) -> bool:
        if self.motor is None: return False
        trabajo = self.registro.tomar()
        if trabajo is None: return False
        copia = Path(trabajo["copia"]) if trabajo["copia"] else None
        try:
            if not self.archivos.recuperar(trabajo):
                if copia is None or not copia.is_file(): raise FileNotFoundError("Falta la copia local de la imagen pendiente.")
                prediccion = self.motor.inferir(copia)
                self.archivos.guardar(trabajo, copia, prediccion)
            self.registro.terminar(trabajo["id"])
            log.info("Completada Sucursal %s: %s", trabajo["sucursal_id"], trabajo["nombre"])
        except Exception as error:
            self.registro.terminar(trabajo["id"], f"{type(error).__name__}: {error}")
            log.exception("Falló una imagen; se continúa con la siguiente: %s", trabajo["nombre"])
        else:
            if copia:
                try: copia.unlink(missing_ok=True)
                except OSError:
                    log.warning("El resultado se guardó, pero no se pudo retirar su copia temporal: %s", trabajo["id"])
        return True

    def _escuchar(self):
        while not self.parar.is_set():
            try: self.revisor.revisar()
            except Exception:
                self.revisor.ultimo_error = "Falló una revisión; consulta el registro del backend."
                log.exception("Falló una revisión de carpetas")
            self.parar.wait(self.cfg.revision_segundos)

    def _trabajar(self):
        self.cargar_motor()
        while not self.parar.is_set():
            try:
                if not self.procesar_uno(): self.parar.wait(.25)
            except Exception:
                log.exception("Falló el acceso a la cola; se intentará de nuevo.")
                self.parar.wait(2)

    def iniciar(self, ejecutar_hilos=True):
        self.instancia.adquirir()
        recuperados = self.registro.recuperar_interrumpidos()
        if recuperados: log.info("Recuperados %s análisis interrumpidos", recuperados)
        if ejecutar_hilos:
            self.hilos = [threading.Thread(target=self._escuchar, name="stockeye-revisor", daemon=True),
                          threading.Thread(target=self._trabajar, name="stockeye-inferencia", daemon=True)]
            for hilo in self.hilos: hilo.start()

    def detener(self):
        self.parar.set()
        # Se espera la fotografía en curso antes de liberar la cola.
        for hilo in self.hilos: hilo.join()
        self.instancia.liberar()
