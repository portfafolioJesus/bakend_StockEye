"""Primera configuración local de PostgreSQL. No recibe secretos por argumentos."""
from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
import queue
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, messagebox

ROLE = "stockeye_app"
DATABASES = ("stockeye_dev", "stockeye_copia_dev", "stockeye_test")
HOST, PORT = "127.0.0.1", 5432
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class SetupRefused(RuntimeError):
    pass


def current_sid():
    output = subprocess.check_output(
        ["whoami.exe", "/user", "/fo", "csv", "/nh"],
        text=True, creationflags=NO_WINDOW,
    )
    rows = list(csv.reader(io.StringIO(output)))
    sid = rows[0][-1].strip() if rows else ""
    if not re.fullmatch(r"S-\d+(?:-\d+)+", sid):
        raise SetupRefused("No se pudo identificar al usuario de Windows.")
    return sid


def private_acl(path, sid, directory=False):
    access = "(OI)(CI)F" if directory else "(F)"
    subprocess.run(
        ["icacls.exe", str(path), "/inheritance:r", "/grant:r",
         f"*{sid}:{access}", f"*S-1-5-18:{access}"],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=NO_WINDOW,
    )


def target_passfile():
    if sys.platform != "win32" or not os.environ.get("APPDATA"):
        raise SetupRefused("Este asistente requiere Windows y APPDATA.")
    base = Path(os.environ["APPDATA"]).resolve()
    candidate = base / "postgresql" / "pgpass.conf"
    target = candidate.resolve()
    if not target.is_relative_to(base) or candidate.is_symlink():
        raise SetupRefused("La ruta de credenciales no es la esperada.")
    if target.exists():
        raise SetupRefused("Ya existe pgpass.conf: no se ha leído ni se modificará.")
    for key in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        value = os.environ.get(key)
        if value and target.is_relative_to(Path(value).resolve()):
            raise SetupRefused("La credencial no debe quedar dentro de OneDrive.")
    if any(part.casefold().startswith("onedrive") for part in target.parts):
        raise SetupRefused("La credencial no debe quedar dentro de OneDrive.")
    if any(key in os.environ for key in ("PGSERVICE", "PGSERVICEFILE", "PGPASSWORD", "PGPASSFILE")):
        raise SetupRefused("Existe configuración PG heredada; usar un proceso de configuración aislado.")
    return target


def write_private_passfile(target, password, sid):
    created = False
    try:
        target.parent.mkdir()
        created = True
    except FileExistsError:
        if not target.parent.is_dir():
            raise SetupRefused("La ruta de credenciales no es un directorio.")
    if created:
        private_acl(target.parent, sid, directory=True)
    fd, name = tempfile.mkstemp(prefix=".stockeye-pgpass-", dir=target.parent)
    os.close(fd)
    temp = Path(name)
    try:
        private_acl(temp, sid)
        escaped = password.replace("\\", "\\\\").replace(":", "\\:")
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            for database in DATABASES:
                handle.write(f"{HOST}:{PORT}:{database}:{ROLE}:{escaped}\n")
            handle.flush()
            os.fsync(handle.fileno())
        # Windows no reemplaza un destino existente con rename.
        os.rename(temp, target)
    finally:
        if temp.exists():
            temp.unlink()


def provision(admin_password):
    result = {"ok": False, "created_role": False, "created_databases": [],
              "passfile_created": False, "stage": "preflight"}
    app_password = verifier = None
    try:
        import psycopg
        from psycopg import sql
    except ImportError:
        result["message"] = "Falta instalar psycopg[binary] en este entorno Python."
        return result
    try:
        target = target_passfile()
        sid = current_sid()
        with psycopg.connect(
            host=HOST, port=PORT, dbname="postgres", user="postgres",
            password=admin_password, autocommit=True, connect_timeout=8,
            application_name="stockeye_local_setup",
            options="-c statement_timeout=20000 -c lock_timeout=5000",
        ) as admin:
            result["stage"] = "check_empty"
            if not admin.execute("SELECT pg_try_advisory_lock(%s,%s)", (1398036805, 12)).fetchone()[0]:
                raise SetupRefused("Ya hay otro asistente de configuración activo.")
            if admin.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (ROLE,)).fetchone():
                raise SetupRefused("stockeye_app ya existe: no se cambia su contraseña.")
            if admin.execute(
                "SELECT datname FROM pg_database WHERE datname IN (%s,%s,%s)", DATABASES
            ).fetchall():
                raise SetupRefused("Ya existe una base prevista: no se adopta ni modifica.")
            rights = admin.execute(
                "SELECT rolsuper,rolcreaterole,rolcreatedb FROM pg_roles WHERE rolname=current_user"
            ).fetchone()
            if not rights or not (rights[0] or (rights[1] and rights[2])):
                raise SetupRefused("La cuenta necesita permiso para crear roles y bases.")
            app_password = secrets.token_urlsafe(36)
            verifier = admin.pgconn.encrypt_password(
                app_password.encode("ascii"), ROLE.encode("ascii"), b"scram-sha-256"
            ).decode("ascii")
            result["stage"] = "private_passfile"
            write_private_passfile(target, app_password, sid)
            result["passfile_created"] = True
            result["stage"] = "create_role"
            admin.execute(sql.SQL(
                "CREATE ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                "NOREPLICATION NOBYPASSRLS PASSWORD {}"
            ).format(sql.Identifier(ROLE), sql.Literal(verifier)))
            result["created_role"] = True
            for database in DATABASES:
                result["stage"] = "create_database"
                admin.execute(sql.SQL(
                    "CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING 'UTF8'"
                ).format(sql.Identifier(database), sql.Identifier(ROLE)))
                result["created_databases"].append(database)
            result["stage"] = "verify"
            for database in DATABASES:
                with psycopg.connect(
                    host=HOST, port=PORT, dbname=database, user=ROLE,
                    passfile=str(target), connect_timeout=8,
                    application_name="stockeye_local_setup_check",
                ) as connection:
                    if connection.execute("SELECT current_user,current_database()").fetchone() != (ROLE, database):
                        raise SetupRefused("No coincide la identidad de la conexión.")
            result.update(ok=True, stage="complete", passfile=str(target))
    except SetupRefused as error:
        result["message"] = str(error)
    except psycopg.Error as error:
        result["sqlstate"] = error.sqlstate or "CONNECTION_ERROR"
        result["message"] = "PostgreSQL no completó la operación. No se borraron recursos."
    except Exception:
        result["message"] = "No se completó la configuración; revisar permisos o instalación."
    finally:
        admin_password = app_password = verifier = None
    return result


def main():
    messages = queue.Queue()
    app = tk.Tk()
    app.title("StockEye: preparar PostgreSQL local")
    app.attributes("-topmost", True)
    app.resizable(False, False)
    frame = ttk.Frame(app, padding=18)
    frame.grid()
    ttk.Label(frame, text=(
        "Servidor: 127.0.0.1:5432 · Administrador: postgres\n"
        "Creará stockeye_app y las bases dev, copia_dev y test.\n"
        "La contraseña administrativa no se guarda ni se imprime.\n"
        "La credencial del backend quedará en el perfil privado de Windows."
    ), justify="left").grid(sticky="w", pady=(0, 12))
    ttk.Label(frame, text="Contraseña elegida en el instalador:").grid(sticky="w")
    entry = ttk.Entry(frame, show="*", width=46)
    entry.grid(sticky="ew", pady=(5, 12))
    status = tk.StringVar(value="Escribe la contraseña solo aquí, no en el chat.")
    ttk.Label(frame, textvariable=status, wraplength=460).grid(sticky="w", pady=(0, 12))
    busy = False
    outcome = {"ok": False, "stage": "cancelled"}

    def worker(value):
        messages.put(provision(value))

    def submit():
        nonlocal busy
        if busy:
            return
        value = entry.get()
        entry.delete(0, "end")
        if not value:
            status.set("La contraseña no puede estar vacía.")
            entry.focus_set()
            return
        busy = True
        button.configure(state="disabled")
        entry.configure(state="disabled")
        status.set("Configurando; no se mostrará ninguna contraseña.")
        threading.Thread(target=worker, args=(value,), daemon=True).start()

    def poll():
        nonlocal busy, outcome
        try:
            result = messages.get_nowait()
        except queue.Empty:
            app.after(100, poll)
            return
        busy = False
        outcome = result
        if result["ok"]:
            messagebox.showinfo("StockEye", "Bases y rol creados. Credencial del backend protegida.", parent=app)
        else:
            detail = result.get("message", "No se completó la configuración.")
            if result.get("sqlstate"):
                detail += "\nSQLSTATE: " + result["sqlstate"]
            if result.get("created_role") or result.get("passfile_created"):
                detail += "\nLos recursos parciales se conservan para revisión; no se borran."
            messagebox.showerror("StockEye", detail, parent=app)
        app.destroy()

    def close():
        if busy:
            messagebox.showinfo("StockEye", "Espera a que termine la operación.", parent=app)
        else:
            app.destroy()

    button = ttk.Button(frame, text="Crear configuración nueva", command=submit)
    button.grid(sticky="ew")
    app.protocol("WM_DELETE_WINDOW", close)
    app.bind("<Return>", lambda event: submit())
    app.after(100, lambda: (app.lift(), entry.focus_force()))
    app.after(100, poll)
    app.mainloop()
    print(json.dumps(outcome, ensure_ascii=False), flush=True)
    return 0 if outcome["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
