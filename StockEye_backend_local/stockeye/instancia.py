"""Evita dos procesadores sobre la misma cola; el SO libera el bloqueo al cerrar."""
from pathlib import Path
import os


class InstanciaUnica:
    def __init__(self, archivo: Path):
        self.archivo = archivo
        self.fd = None

    def adquirir(self):
        self.archivo.parent.mkdir(parents=True, exist_ok=True)
        self.fd = self.archivo.open("a+b")
        self.fd.seek(0, 2)
        if self.fd.tell() == 0:
            self.fd.write(b"0"); self.fd.flush()
        self.fd.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.fd.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.fd.close(); self.fd = None
            raise RuntimeError("Ya hay otro backend usando esta carpeta de datos. Cierra el anterior.") from error

    def liberar(self):
        if self.fd is not None:
            if os.name == "nt":
                import msvcrt
                self.fd.seek(0); msvcrt.locking(self.fd.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            self.fd.close(); self.fd = None
