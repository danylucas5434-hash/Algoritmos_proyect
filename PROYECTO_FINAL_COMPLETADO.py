#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""SISTEMA DE BIBLIOTECA NEXO — un solo archivo Python.

Python 3.10 o posterior. Windows: py Sistema_Biblioteca_Corregido_Video.py
Linux: python3 Sistema_Biblioteca_Corregido_Video.py
Interfaz: tkinter/ttk (Linux Ubuntu/Debian: sudo apt install python3-tk).
Opciones: --cli, --diagnostico, --check, --backup, --csv, --pruebas.
Registros: carpeta datos/ junto al archivo. Para trasladarlos, envía también esa carpeta.

Los comentarios siguen el ejemplo del video: función, validaciones y resultado.
Responsables: Kiomy (libros/autores), Carlos (usuarios), Anderson (préstamos),
Jeremy (devoluciones/multas) y Dany (interfaz, menú e integración).
"""

# =================================================================
# modelos.py | Parte integrada (Python)
# =================================================================
# CLASES: representan los registros que comparten las cinco partes del sistema.
from dataclasses import dataclass


# ============================================================================
# BLOQUE 1 — KIOMY | Libros y autores
# Objetivo: representar autores y libros y conservar cantidadDisponible.
# ============================================================================
@dataclass(frozen=True)
class Autor:
    id_autor: str
    nombre: str
    apellido: str

    def mostrar_nombre(self) -> str:
        return f"{self.nombre} {self.apellido}".strip()


@dataclass(frozen=True)
class Libro:
    codigo: str
    titulo: str
    autor: Autor
    categoria: str
    cantidad_total: int
    cantidad_disponible: int

    @property
    def cantidadDisponible(self) -> int:
        """Compatibilidad con el atributo usado en el primer Word."""
        return self.cantidad_disponible

    def mostrar_informacion(self) -> str:
        return (f"Código: {self.codigo} | Título: {self.titulo} | "
                f"Autor: {self.autor.mostrar_nombre()} | Categoría: {self.categoria} | "
                f"Disponibles: {self.cantidad_disponible}/{self.cantidad_total}")


# ============================================================================
# BLOQUE 2 — CARLOS | Usuarios
# Objetivo: representar, identificar y mostrar usuarios.
# ============================================================================
@dataclass(frozen=True)
class Usuario:
    id_usuario: str
    nombre: str
    apellido: str
    contacto: str

    @property
    def id(self) -> str:
        return self.id_usuario

    def nombre_completo(self) -> str:
        return f"{self.nombre} {self.apellido}".strip()


# ============================================================================
# BLOQUE 3 — ANDERSON | Préstamos
# Objetivo: registrar libro, usuario, fechas y estado del préstamo.
# ============================================================================
@dataclass(frozen=True)
class Prestamo:
    id_prestamo: int
    usuario_id: str
    libro_codigo: str
    fecha_prestamo: str
    fecha_limite: str
    fecha_devolucion: str | None
    estado: str
    multa_centavos: int


# ============================================================================
# BLOQUE 4 — JEREMY | Devoluciones y multas
# Objetivo: representar el cálculo final sin errores de decimales.
# ============================================================================
@dataclass(frozen=True)
class ResultadoDevolucion:
    id_prestamo: int
    fecha_devolucion: str
    dias_atraso: int
    multa_centavos: int

    @property
    def multa(self) -> float:
        return self.multa_centavos / 100


# =================================================================
# biblioteca_core.py | Parte integrada (Python)
# =================================================================
# MOTOR: usa SQLite y transacciones. Ante un error revierte toda la operación.

import csv
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterator


MULTA_DIARIA_CENTAVOS = 500  # Q 5.00, referencia del documento de tareas
MULTA_DIARIA = MULTA_DIARIA_CENTAVOS / 100


class BibliotecaError(ValueError):
    """Error controlado para mostrar mensajes claros sin cerrar el programa."""


def obligatorio(valor: object, campo: str, maximo: int = 150) -> str:
    texto = " ".join(str(valor if valor is not None else "").split())
    if not texto:
        raise BibliotecaError(f"El campo '{campo}' es obligatorio.")
    if len(texto) > maximo:
        raise BibliotecaError(f"'{campo}' no puede exceder {maximo} caracteres.")
    if any(ord(c) < 32 for c in texto):
        raise BibliotecaError(f"'{campo}' contiene caracteres inválidos.")
    return texto


def no_vacio_opcional(valor: object, campo: str, maximo: int = 200) -> str:
    texto = " ".join(str(valor if valor is not None else "").split())
    if len(texto) > maximo:
        raise BibliotecaError(f"'{campo}' no puede exceder {maximo} caracteres.")
    return texto


def entero_positivo(valor: object, campo: str, permitir_cero: bool = False) -> int:
    texto = str(valor).strip()
    if not texto.isascii() or not texto.isdecimal():
        raise BibliotecaError(f"'{campo}' debe ser un número entero no negativo.")
    if len(texto) > 7:
        raise BibliotecaError(f"'{campo}' supera el valor máximo permitido (1000000).")
    numero = int(texto)
    if numero < (0 if permitir_cero else 1) or numero > 1000000:
        raise BibliotecaError(f"'{campo}' debe estar entre {0 if permitir_cero else 1} y 1000000.")
    return numero


def fecha_valida(valor: object, campo: str) -> date:
    try:
        texto = str(valor).strip()
        if len(texto) != 10:
            raise ValueError
        fecha = date.fromisoformat(texto)
        if fecha.isoformat() != texto:
            raise ValueError
        return fecha
    except (TypeError, ValueError):
        raise BibliotecaError(f"'{campo}' debe tener formato AAAA-MM-DD.") from None


def _error_integridad(ex: sqlite3.IntegrityError) -> BibliotecaError:
    mensaje = str(ex).lower()
    if "unique" in mensaje or "primary key" in mensaje:
        return BibliotecaError("Ya existe un registro con ese código o identificación.")
    if "foreign key" in mensaje:
        return BibliotecaError("No existe el registro relacionado con esta operación.")
    return BibliotecaError("La operación incumple una regla de integridad de datos.")


# ============================================================================
# BLOQUE 5 — DANY | Integración, persistencia y comprobaciones
# Objetivo: compartir los mismos datos entre los módulos y evitar corrupción.
# ============================================================================
class Biblioteca:
    # Crea carpetas portables y abre una única base de datos SQLite.
    def __init__(self, carpeta_datos: str | Path | None = None):
        if carpeta_datos is None:
            carpeta_datos = os.environ.get("BIBLIOTECA_DATOS") or (Path(__file__).resolve().parent / "datos")
        self.carpeta = Path(carpeta_datos).expanduser().resolve()
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self.respaldos = self.carpeta / "respaldos"
        self.respaldos.mkdir(parents=True, exist_ok=True)
        self.db_path = self.carpeta / "biblioteca.sqlite3"
        self._inicializar()

    # Activa las relaciones y configuración segura de SQLite en cada conexión.
    def _abrir(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.db_path), timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=15000")
        # SQLite valida relaciones y espera si otra operación está escribiendo.
        con.execute("PRAGMA synchronous=FULL")
        return con

    @contextmanager
    def _lectura(self) -> Iterator[sqlite3.Connection]:
        con = self._abrir()
        try:
            yield con
        finally:
            con.close()

    # SEGURIDAD: confirma todos los cambios o cancela todo si falla una operación.
    @contextmanager
    def _escritura(self) -> Iterator[sqlite3.Connection]:
        con = self._abrir()
        try:
            con.execute("BEGIN IMMEDIATE")  # impide préstamos simultáneos inconsistentes
            yield con
            con.commit()
        except sqlite3.IntegrityError as ex:
            con.rollback()
            raise _error_integridad(ex) from ex
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _inicializar(self) -> None:
        esquema = """
        CREATE TABLE IF NOT EXISTS autores (
          id_autor TEXT PRIMARY KEY,
          nombre TEXT NOT NULL, apellido TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS libros (
          codigo TEXT PRIMARY KEY, titulo TEXT NOT NULL,
          autor_id TEXT NOT NULL REFERENCES autores(id_autor),
          categoria TEXT NOT NULL,
          cantidad_total INTEGER NOT NULL CHECK(cantidad_total >= 0),
          cantidad_disponible INTEGER NOT NULL
             CHECK(cantidad_disponible >= 0 AND cantidad_disponible <= cantidad_total)
        );
        CREATE TABLE IF NOT EXISTS usuarios (
          id_usuario TEXT PRIMARY KEY,
          nombre TEXT NOT NULL, apellido TEXT NOT NULL, contacto TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS prestamos (
          id_prestamo INTEGER PRIMARY KEY AUTOINCREMENT,
          usuario_id TEXT NOT NULL REFERENCES usuarios(id_usuario),
          libro_codigo TEXT NOT NULL REFERENCES libros(codigo),
          fecha_prestamo TEXT NOT NULL, fecha_limite TEXT NOT NULL,
          fecha_devolucion TEXT,
          estado TEXT NOT NULL CHECK(estado IN ('Prestado', 'Devuelto')),
          multa_centavos INTEGER NOT NULL DEFAULT 0 CHECK(multa_centavos >= 0),
          CHECK ((estado='Prestado' AND fecha_devolucion IS NULL) OR
                 (estado='Devuelto' AND fecha_devolucion IS NOT NULL))
        );
        CREATE INDEX IF NOT EXISTS idx_prestamos_estado ON prestamos(estado);
        CREATE INDEX IF NOT EXISTS idx_prestamos_libro ON prestamos(libro_codigo);
        CREATE INDEX IF NOT EXISTS idx_prestamos_limite ON prestamos(fecha_limite);
        """
        with self._lectura() as con:
            # Diario DELETE: evita archivos WAL auxiliares al mover la base de datos.
            con.execute("PRAGMA journal_mode=DELETE")
            con.executescript(esquema)
            con.commit()
        comprobacion = self.verificar_integridad()
        if not comprobacion["correcto"]:
            raise BibliotecaError("Base de datos inconsistente: " + "; ".join(comprobacion["detalles"]))

    # ========================================================================
    # BLOQUE 1 — KIOMY | Libros y autores
    # Registro, búsqueda, consultas y control de ejemplares.
    # ========================================================================
    # Registra autor solo si su identificación no está repetida.
    def registrar_autor(self, id_autor: object, nombre: object, apellido: object) -> Autor:
        autor = Autor(obligatorio(id_autor, "ID del autor", 40),
                      obligatorio(nombre, "Nombre"), obligatorio(apellido, "Apellido"))
        # GUARDA: identificación única y nombre del autor en SQLite.
        with self._escritura() as con:
            con.execute("INSERT INTO autores VALUES (?,?,?)",
                        (autor.id_autor, autor.nombre, autor.apellido))
        return autor

    def listar_autores(self) -> list[Autor]:
        with self._lectura() as con:
            return [Autor(**dict(r)) for r in con.execute(
                "SELECT id_autor, nombre, apellido FROM autores ORDER BY apellido,nombre").fetchall()]

    # Valida libro y autor; guarda existencias iniciales.
    def registrar_libro(self, codigo: object, titulo: object, id_autor: object,
                        categoria: object, cantidad: object) -> Libro:
        codigo = obligatorio(codigo, "Código", 60)
        titulo = obligatorio(titulo, "Título")
        id_autor = obligatorio(id_autor, "Autor", 40)
        categoria = obligatorio(categoria, "Categoría")
        cantidad = entero_positivo(cantidad, "Cantidad total", permitir_cero=True)
        # VALIDA: un libro no puede registrarse sin un autor existente.
        with self._escritura() as con:
            autor = con.execute("SELECT 1 FROM autores WHERE id_autor=?", (id_autor,)).fetchone()
            if autor is None:
                raise BibliotecaError("El autor no existe: regístrelo primero.")
            con.execute("""INSERT INTO libros(codigo,titulo,autor_id,categoria,
                         cantidad_total,cantidad_disponible) VALUES(?,?,?,?,?,?)""",
                        (codigo, titulo, id_autor, categoria, cantidad, cantidad))
        libro = self.buscar_libro(codigo)
        assert libro is not None
        return libro

    @staticmethod
    def _libro_fila(fila: sqlite3.Row) -> Libro:
        return Libro(fila["codigo"], fila["titulo"],
                     Autor(fila["id_autor"], fila["nombre"], fila["apellido"]),
                     fila["categoria"], fila["cantidad_total"], fila["cantidad_disponible"])

    _SQL_LIBROS = """SELECT l.codigo,l.titulo,l.categoria,l.cantidad_total,
            l.cantidad_disponible,a.id_autor,a.nombre,a.apellido
            FROM libros AS l JOIN autores AS a ON a.id_autor=l.autor_id"""

    def buscar_libro(self, codigo: object) -> Libro | None:
        with self._lectura() as con:
            fila = con.execute(self._SQL_LIBROS + " WHERE l.codigo=?", (str(codigo).strip(),)).fetchone()
            return self._libro_fila(fila) if fila else None

    # Busca por código, título, categoría o autor sin modificar datos.
    def buscar_libros(self, texto: object = "", solo_disponibles: bool = False) -> list[Libro]:
        busqueda = f"%{str(texto or '').strip()}%"
        sql = self._SQL_LIBROS + " WHERE (l.codigo LIKE ? OR l.titulo LIKE ? OR " \
              "l.categoria LIKE ? OR a.nombre LIKE ? OR a.apellido LIKE ?)"
        parametros: list = [busqueda] * 5
        if solo_disponibles:
            sql += " AND l.cantidad_disponible>0"
        sql += " ORDER BY l.titulo COLLATE NOCASE,l.codigo"
        with self._lectura() as con:
            return [self._libro_fila(r) for r in con.execute(sql, parametros).fetchall()]

    def consultar_libros_disponibles(self) -> list[Libro]:
        return self.buscar_libros(solo_disponibles=True)

    # ========================================================================
    # BLOQUE 2 — CARLOS | Usuarios
    # Registros, búsquedas y verificación antes de permitir un préstamo.
    # ========================================================================
    # Valida y guarda los datos de cada usuario.
    # FUNCIÓN: Carlos registra la ficha y valida los campos obligatorios.
    def registrar_usuario(self, id_usuario: object, nombre: object,
                          apellido: object, contacto: object) -> Usuario:
        usuario = Usuario(obligatorio(id_usuario, "ID de usuario", 50),
                          obligatorio(nombre, "Nombre"), obligatorio(apellido, "Apellido"),
                          obligatorio(contacto, "Contacto"))
        # GUARDA: el ID es único; los datos permanecen entre ejecuciones.
        with self._escritura() as con:
            con.execute("INSERT INTO usuarios VALUES(?,?,?,?)",
                        (usuario.id_usuario, usuario.nombre, usuario.apellido, usuario.contacto))
        return usuario

    def buscar_usuario(self, id_usuario: object) -> Usuario | None:
        with self._lectura() as con:
            fila = con.execute("SELECT * FROM usuarios WHERE id_usuario=?",
                               (str(id_usuario).strip(),)).fetchone()
            return Usuario(**dict(fila)) if fila else None

    # BÚSQUEDA: acepta identificación, nombre, apellido o contacto.
    def buscar_usuarios(self, texto: object = "") -> list[Usuario]:
        busqueda = f"%{str(texto or '').strip()}%"
        with self._lectura() as con:
            return [Usuario(**dict(r)) for r in con.execute(
                """SELECT * FROM usuarios WHERE id_usuario LIKE ? OR nombre LIKE ?
                   OR apellido LIKE ? OR contacto LIKE ? ORDER BY apellido,nombre""",
                (busqueda,)*4).fetchall()]

    # Impide prestar si el usuario no existe.
    def validar_usuario_para_prestamo(self, id_usuario: object) -> Usuario:
        usuario = self.buscar_usuario(id_usuario)
        if usuario is None:
            raise BibliotecaError("El usuario no existe. Debe registrarlo antes del préstamo.")
        return usuario

    # ========================================================================
    # BLOQUE 3 — ANDERSON | Préstamos y disponibilidad
    # La creación del préstamo y la resta de existencias son UNA transacción.
    # ========================================================================
    # Verifica usuario, libro y stock; descuenta uno y registra el préstamo juntos.
    def registrar_prestamo(self, id_usuario: object, codigo_libro: object,
                           fecha_limite: object, fecha_prestamo: object | None = None) -> Prestamo:
        usuario_id = obligatorio(id_usuario, "ID de usuario", 50)
        codigo = obligatorio(codigo_libro, "Código del libro", 60)
        inicio = fecha_valida(fecha_prestamo, "Fecha de préstamo") if fecha_prestamo else date.today()
        limite = fecha_valida(fecha_limite, "Fecha límite")
        if inicio > date.today():
            raise BibliotecaError("No se puede registrar un préstamo con fecha futura.")
        if limite < inicio:
            raise BibliotecaError("La fecha límite no puede ser anterior a la del préstamo.")
        # PASO 1: verifica usuario y libro antes de tocar el inventario.
        with self._escritura() as con:
            if not con.execute("SELECT 1 FROM usuarios WHERE id_usuario=?", (usuario_id,)).fetchone():
                raise BibliotecaError("El usuario no existe. Debe registrarlo primero.")
            if not con.execute("SELECT 1 FROM libros WHERE codigo=?", (codigo,)).fetchone():
                raise BibliotecaError("El libro no existe. Debe registrarlo primero.")
            # PASO 2: solo descuenta si queda al menos un ejemplar.
            actualizacion = con.execute("""UPDATE libros SET cantidad_disponible=cantidad_disponible-1
                                          WHERE codigo=? AND cantidad_disponible>0""", (codigo,))
            if actualizacion.rowcount != 1:
                raise BibliotecaError("No hay ejemplares disponibles de este libro.")
            # PASO 3: préstamo y descuento se confirman juntos o se revierten.
            cursor = con.execute("""INSERT INTO prestamos
                (usuario_id,libro_codigo,fecha_prestamo,fecha_limite,fecha_devolucion,estado,multa_centavos)
                VALUES(?,?,?,?,NULL,'Prestado',0)""", (usuario_id,codigo,inicio.isoformat(),limite.isoformat()))
            prestamo_id = cursor.lastrowid
            fila = con.execute("SELECT * FROM prestamos WHERE id_prestamo=?", (prestamo_id,)).fetchone()
        return Prestamo(**dict(fila))

    # ========================================================================
    # BLOQUE 4 — JEREMY | Devoluciones y multas
    # Solo una devolución, multa en centavos y devolución de ejemplar atómica.
    # ========================================================================
    # Impide doble devolución, calcula atraso y repone una existencia.
    def devolver_prestamo(self, id_prestamo: object,
                          fecha_devolucion: object | None = None) -> ResultadoDevolucion:
        prestamo_id = entero_positivo(id_prestamo, "Número de préstamo")
        real = fecha_valida(fecha_devolucion, "Fecha de devolución") if fecha_devolucion else date.today()
        if real > date.today():
            raise BibliotecaError("No se puede registrar una devolución futura.")
        # PASO 1: busca el préstamo e impide devolverlo dos veces.
        with self._escritura() as con:
            prestamo = con.execute("SELECT * FROM prestamos WHERE id_prestamo=?", (prestamo_id,)).fetchone()
            if prestamo is None:
                raise BibliotecaError("Ese número de préstamo no existe.")
            if prestamo["estado"] != "Prestado":
                raise BibliotecaError("Este préstamo ya fue devuelto; no puede devolverse dos veces.")
            inicio = date.fromisoformat(prestamo["fecha_prestamo"])
            if real < inicio:
                raise BibliotecaError("La devolución no puede ser anterior al préstamo.")
            limite = date.fromisoformat(prestamo["fecha_limite"])
            # PASO 2: los días de atraso multiplican la multa diaria (Q 5.00).
            dias = max(0, (real-limite).days)
            multa = dias * MULTA_DIARIA_CENTAVOS
            actualizado = con.execute("""UPDATE prestamos SET fecha_devolucion=?,
                estado='Devuelto',multa_centavos=? WHERE id_prestamo=? AND estado='Prestado'""",
                (real.isoformat(),multa,prestamo_id))
            if actualizado.rowcount != 1:
                raise BibliotecaError("El préstamo cambió de estado; vuelva a consultar.")
            # PASO 3: al devolver, aumenta una unidad de existencia.
            devolver = con.execute("""UPDATE libros SET cantidad_disponible=cantidad_disponible+1
                WHERE codigo=? AND cantidad_disponible<cantidad_total""", (prestamo["libro_codigo"],))
            if devolver.rowcount != 1:
                raise BibliotecaError("No se pudo actualizar el inventario; operación revertida.")
        return ResultadoDevolucion(prestamo_id, real.isoformat(), dias, multa)

    # ========================================================================
    # BLOQUE 5 — DANY | Consultas, historial, control, pruebas y respaldos
    # ========================================================================
    # Filtra historial, préstamos activos, devueltos y vencidos.
    def listar_prestamos(self, filtro: str = "Todos") -> list[dict]:
        if filtro not in {"Todos", "Prestados", "Devueltos", "Vencidos"}:
            raise BibliotecaError("Filtro no válido.")
        sql = """SELECT p.*, l.titulo, u.nombre, u.apellido FROM prestamos p
                 JOIN libros l ON l.codigo=p.libro_codigo
                 JOIN usuarios u ON u.id_usuario=p.usuario_id"""
        if filtro == "Prestados":
            sql += " WHERE p.estado='Prestado'"
        elif filtro == "Devueltos":
            sql += " WHERE p.estado='Devuelto'"
        elif filtro == "Vencidos":
            sql += " WHERE p.estado='Prestado' AND p.fecha_limite<?"
        sql += " ORDER BY p.id_prestamo DESC"
        with self._lectura() as con:
            parametros = (date.today().isoformat(),) if filtro == "Vencidos" else ()
            resultado = [dict(r) for r in con.execute(sql, parametros).fetchall()]
        hoy = date.today()
        for r in resultado:
            referencia = (date.fromisoformat(r["fecha_devolucion"]) if r["fecha_devolucion"] else hoy)
            r["dias_atraso"] = max(0, (referencia - date.fromisoformat(r["fecha_limite"])).days)
            r["multa_visible_centavos"] = (r["multa_centavos"] if r["estado"] == "Devuelto"
                                           else r["dias_atraso"] * MULTA_DIARIA_CENTAVOS)
            r["usuario"] = f"{r['nombre']} {r['apellido']}"
            r["vencido"] = r["estado"] == "Prestado" and r["dias_atraso"] > 0
        return resultado

    def consultar_libros_prestados(self) -> list[dict]:
        return self.listar_prestamos("Prestados")

    def prestamos_vencidos(self) -> list[dict]:
        return self.listar_prestamos("Vencidos")

    # RESUMEN: Dany muestra títulos, usuarios, disponibles y vencimientos.
    def estadisticas(self) -> dict[str, int]:
        with self._lectura() as con:
            valores = {
                "titulos": con.execute("SELECT COUNT(*) FROM libros").fetchone()[0],
                "ejemplares_disponibles": con.execute("SELECT COALESCE(SUM(cantidad_disponible),0) FROM libros").fetchone()[0],
                "usuarios": con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0],
                "prestamos_activos": con.execute("SELECT COUNT(*) FROM prestamos WHERE estado='Prestado'").fetchone()[0],
                "vencidos": con.execute("SELECT COUNT(*) FROM prestamos WHERE estado='Prestado' AND fecha_limite<?",
                                         (date.today().isoformat(),)).fetchone()[0],
            }
        return valores

    # SEGURIDAD: compara inventario con los préstamos todavía activos.
    def verificar_integridad(self) -> dict:
        detalles = []
        with self._lectura() as con:
            resultado = con.execute("PRAGMA quick_check").fetchone()[0]
            if resultado != "ok":
                detalles.append(f"SQLite: {resultado}")
            if con.execute("PRAGMA foreign_key_check").fetchall():
                detalles.append("Hay relaciones entre tablas inválidas.")
            inconsistentes = con.execute("""SELECT l.codigo FROM libros l WHERE
                l.cantidad_total != l.cantidad_disponible +
                (SELECT COUNT(*) FROM prestamos p WHERE p.libro_codigo=l.codigo AND p.estado='Prestado')""").fetchall()
            if inconsistentes:
                detalles.append("Inventario y préstamos activos no coinciden: " +
                                 ", ".join(r[0] for r in inconsistentes[:10]))
        return {"correcto": not detalles, "detalles": detalles or ["Integridad e inventario correctos."]}

    # Usa la API backup de SQLite para guardar una copia consistente.
    def crear_respaldo(self) -> Path:
        destino = self.respaldos / f"biblioteca_{datetime.now():%Y%m%d_%H%M%S_%f}.sqlite3"
        try:
            with self._lectura() as origen:
                with sqlite3.connect(str(destino)) as copia:
                    origen.backup(copia)  # snapshot atómico, sin copiar .db abierta
                    verificacion = copia.execute("PRAGMA quick_check").fetchone()[0]
                    if verificacion != "ok":
                        raise BibliotecaError("El respaldo no superó la comprobación de integridad.")
            return destino
        except Exception:
            destino.unlink(missing_ok=True)
            raise

    # Exporta las cuatro tablas a CSV legible, sin alterar la base.
    def exportar_csv(self) -> Path:
        destino = self.respaldos / f"csv_{datetime.now():%Y%m%d_%H%M%S_%f}"
        destino.mkdir(parents=True, exist_ok=False)
        tablas = ("autores", "libros", "usuarios", "prestamos")  # lista controlada, sin SQL libre
        try:
            with self._lectura() as con:
                for tabla in tablas:
                    consulta = con.execute(f"SELECT * FROM {tabla}")
                    columnas = [c[0] for c in consulta.description]
                    with (destino / f"{tabla}.csv").open("w", newline="", encoding="utf-8-sig") as f:
                        escritor = csv.writer(f)
                        escritor.writerow(columnas)
                        escritor.writerows(consulta.fetchall())
            return destino
        except Exception:
            for archivo in destino.glob("*.csv"):
                archivo.unlink()
            destino.rmdir()
            raise


# =================================================================
# biblioteca_gui.py | Parte integrada (Python)
# =================================================================
# VENTANA: Dany conecta los formularios con las funciones de todos los integrantes.

import sqlite3
try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except ImportError:
    tk = None
    messagebox = None
    ttk = None
from datetime import date, timedelta


NAVY = "#10223C"
NAVY_LIGHT = "#1B3554"
BLUE = "#1769E0"
SKY = "#EAF2FF"
BG = "#F3F6FB"
WHITE = "#FFFFFF"
TEXT = "#172638"
MUTED = "#607084"
LINE = "#DBE4EE"
GREEN = "#16845F"
RED = "#BF3E50"


class BibliotecaApp(tk.Tk if tk is not None else object):
    """Sistema integrado con páginas y tablas adaptables a Windows/Linux."""

    def __init__(self, sistema: Biblioteca):
        super().__init__()
        self.sistema = sistema
        self.title("NEXO • Biblioteca | Gestión integral")
        self.geometry("1250x800")
        self.minsize(980, 650)
        self.configure(bg=BG)
        self._views = {}
        self._buttons = {}
        self._pagina = "Inicio"
        self._estilos()
        self._estructura()
        self._crear_paginas()
        self.mostrar("Inicio")
        self.bind("<F5>", lambda _e: self.actualizar())

    def _estilos(self):
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Nexo.Treeview", font=("DejaVu Sans", 10), rowheight=32,
                        background=WHITE, fieldbackground=WHITE, foreground=TEXT, borderwidth=0)
        style.configure("Nexo.Treeview.Heading", font=("DejaVu Sans", 10, "bold"),
                        background="#E9EFF7", foreground=NAVY, padding=(9, 10), borderwidth=0)
        style.map("Nexo.Treeview", background=[("selected", "#CADFFF")],
                  foreground=[("selected", NAVY)])
        style.configure("Nexo.TCombobox", padding=7)

    # DANY: crea la barra lateral, las secciones y los botones de navegación.
    def _estructura(self):
        lateral = tk.Frame(self, bg=NAVY, width=246)
        lateral.pack(side="left", fill="y")
        lateral.pack_propagate(False)
        tk.Label(lateral, text="▣", fg="#58A3FF", bg=NAVY,
                 font=("DejaVu Sans", 27, "bold")).pack(anchor="w", padx=26, pady=(26, 0))
        tk.Label(lateral, text="NEXO", fg=WHITE, bg=NAVY,
                 font=("DejaVu Sans", 26, "bold")).pack(anchor="w", padx=26)
        tk.Label(lateral, text="GESTIÓN DE BIBLIOTECA", fg="#A6BBD1", bg=NAVY,
                 font=("DejaVu Sans", 9, "bold")).pack(anchor="w", padx=27, pady=(0, 30))
        rutas = [
            ("Inicio", "⌂"), ("Libros y autores", "▤"), ("Usuarios", "♙"),
            ("Préstamos", "⇧"), ("Devoluciones", "⇩"), ("Historial", "▥")
        ]
        for nombre, icono in rutas:
            boton = tk.Button(lateral, text=f"  {icono}    {nombre}", bg=NAVY,
                              fg="#CBD8E8", activebackground=NAVY_LIGHT,
                              activeforeground=WHITE, borderwidth=0, relief="flat", anchor="w",
                              padx=15, pady=14, cursor="hand2", font=("DejaVu Sans", 11),
                              command=lambda p=nombre: self.mostrar(p))
            boton.pack(fill="x", padx=13, pady=2)
            self._buttons[nombre] = boton
        tk.Frame(lateral, bg=NAVY).pack(fill="both", expand=True)
        tk.Label(lateral, text="●  Datos guardados en SQLite", fg="#8DCAAC", bg=NAVY,
                 font=("DejaVu Sans", 9)).pack(anchor="w", padx=23, pady=(8, 6))
        tk.Label(lateral, text="Python 3.10+ · Windows / Linux", fg="#8DA5C0", bg=NAVY,
                 font=("DejaVu Sans", 9)).pack(anchor="w", padx=23, pady=(0, 24))

        derecha = tk.Frame(self, bg=BG)
        derecha.pack(side="left", fill="both", expand=True)
        top = tk.Frame(derecha, bg=WHITE, height=72, highlightbackground=LINE, highlightthickness=1)
        top.pack(fill="x")
        top.pack_propagate(False)
        self.titulo = tk.Label(top, text="Panel de control", bg=WHITE, fg=NAVY,
                               font=("DejaVu Sans", 18, "bold"))
        self.titulo.pack(side="left", padx=30)
        tk.Button(top, text="↻  Actualizar", command=self.actualizar, cursor="hand2",
                  bg=SKY, fg=BLUE, relief="flat", padx=14, pady=9,
                  font=("DejaVu Sans", 10, "bold")).pack(side="right", padx=(7, 28))
        tk.Button(top, text="▣  Respaldo", command=self.respaldar, cursor="hand2",
                  bg=BLUE, fg=WHITE, relief="flat", padx=14, pady=9,
                  font=("DejaVu Sans", 10, "bold")).pack(side="right", padx=7)
        self.cuerpo = tk.Frame(derecha, bg=BG)
        self.cuerpo.pack(fill="both", expand=True, padx=26, pady=22)
        barra = tk.Frame(derecha, bg=WHITE, height=31)
        barra.pack(fill="x", side="bottom")
        self.estado = tk.Label(barra, text="Listo • F5 para actualizar", bg=WHITE, fg=MUTED,
                               anchor="w", font=("DejaVu Sans", 9))
        self.estado.pack(fill="x", padx=25)

    # DANY: integra las pantallas de los cinco responsables.
    def _crear_paginas(self):
        for ruta in self._buttons:
            marco = tk.Frame(self.cuerpo, bg=BG)
            self._views[ruta] = marco
        self._inicio(self._views["Inicio"])
        self._libros(self._views["Libros y autores"])
        self._usuarios(self._views["Usuarios"])
        self._prestamos(self._views["Préstamos"])
        self._devoluciones(self._views["Devoluciones"])
        self._historial(self._views["Historial"])

    def _titulo_seccion(self, padre, titulo, detalle):
        tk.Label(padre, text=titulo, bg=BG, fg=NAVY,
                 font=("DejaVu Sans", 20, "bold")).pack(anchor="w")
        tk.Label(padre, text=detalle, bg=BG, fg=MUTED,
                 font=("DejaVu Sans", 10)).pack(anchor="w", pady=(4, 18))

    def _card(self, padre, padx=18, pady=16):
        exterior = tk.Frame(padre, bg=WHITE, highlightbackground=LINE, highlightthickness=1)
        exterior.pack(fill="x", pady=(0, 14))
        interior = tk.Frame(exterior, bg=WHITE)
        interior.pack(fill="x", padx=padx, pady=pady)
        return interior

    def _subtitulo(self, padre, texto):
        tk.Label(padre, text=texto, bg=WHITE, fg=NAVY,
                 font=("DejaVu Sans", 12, "bold")).pack(anchor="w", pady=(0, 10))

    def _form(self, padre, columnas):
        fila = tk.Frame(padre, bg=WHITE)
        fila.pack(fill="x")
        for n in range(columnas):
            fila.grid_columnconfigure(n, weight=1, uniform="fields")
        return fila

    def _campo(self, padre, columna, texto, defecto="", ancho=20):
        f = tk.Frame(padre, bg=WHITE)
        f.grid(row=0, column=columna, sticky="ew", padx=(0, 12), pady=(0, 6))
        tk.Label(f, text=texto, fg=MUTED, bg=WHITE, anchor="w",
                 font=("DejaVu Sans", 9, "bold")).pack(fill="x", pady=(0, 4))
        entrada = ttk.Entry(f, width=ancho, font=("DejaVu Sans", 10))
        entrada.pack(fill="x", ipady=6)
        if defecto:
            entrada.insert(0, defecto)
        return entrada

    def _boton(self, padre, texto, comando, color=BLUE):
        return tk.Button(padre, text=texto, command=comando, bg=color, fg=WHITE,
                         activebackground=NAVY, activeforeground=WHITE, relief="flat",
                         cursor="hand2", padx=17, pady=9,
                         font=("DejaVu Sans", 10, "bold"))

    def _tabla(self, padre, columnas, anchos=None, altura=9):
        marco = tk.Frame(padre, bg=WHITE)
        marco.pack(fill="both", expand=True)
        tabla = ttk.Treeview(marco, columns=columnas, show="headings", height=altura,
                             selectmode="browse", style="Nexo.Treeview")
        for idx, col in enumerate(columnas):
            tabla.heading(col, text=col)
            tabla.column(col, width=(anchos[idx] if anchos else 120),
                         minwidth=75, anchor="w", stretch=True)
        tabla.grid(row=0, column=0, sticky="nsew")
        barra_y = ttk.Scrollbar(marco, orient="vertical", command=tabla.yview)
        barra_y.grid(row=0, column=1, sticky="ns")
        barra_x = ttk.Scrollbar(marco, orient="horizontal", command=tabla.xview)
        barra_x.grid(row=1, column=0, sticky="ew")
        tabla.configure(yscrollcommand=barra_y.set, xscrollcommand=barra_x.set)
        marco.columnconfigure(0, weight=1)
        marco.rowconfigure(0, weight=1)
        return tabla

    @staticmethod
    def _insertar(tabla, filas):
        tabla.delete(*tabla.get_children())
        for fila in filas:
            tabla.insert("", "end", values=fila)

    # DANY: ejecuta funciones del motor, refresca y muestra errores controlados.
    # ERRORES: avisa al usuario sin cerrar la ventana ni guardar operaciones fallidas.
    def _accion(self, descripcion, funcion, limpiar=()):
        try:
            resultado = funcion()
            for campo in limpiar:
                campo.delete(0, "end")
            self.actualizar()
            self.estado.configure(text="✓ " + descripcion)
            messagebox.showinfo("Operación completada", descripcion +
                                (f"\n\n{resultado}" if resultado is not None else ""), parent=self)
        except (BibliotecaError, sqlite3.Error, OSError, OverflowError) as e:
            self.estado.configure(text="Error controlado: operación no aplicada")
            messagebox.showerror("No se pudo completar", str(e), parent=self)

    # NAVEGACIÓN: cambia la página sin crear otra base de datos.
    def mostrar(self, pagina):
        for nombre, vista in self._views.items():
            vista.pack_forget()
            self._buttons[nombre].configure(bg=(BLUE if pagina == nombre else NAVY),
                                           fg=WHITE if pagina == nombre else "#CBD8E8")
        self._views[pagina].pack(fill="both", expand=True)
        self._pagina = pagina
        self.titulo.configure(text=pagina if pagina != "Inicio" else "Panel de control")
        self.actualizar()

    # ------------------------------------------------------------------------
    # DANY: Inicio / indicadores de todos los módulos
    # ------------------------------------------------------------------------
    def _inicio(self, padre):
        self._titulo_seccion(padre, "Tu biblioteca, organizada.",
                             "Panel general · información actualizada del inventario y los préstamos")
        tarjetas = tk.Frame(padre, bg=BG)
        tarjetas.pack(fill="x", pady=(0, 18))
        self.indicadores = {}
        for i, (clave, titulo, tono) in enumerate([
            ("titulos", "Títulos registrados", BLUE),
            ("ejemplares_disponibles", "Ejemplares libres", GREEN),
            ("usuarios", "Usuarios", "#9662D0"),
            ("prestamos_activos", "Préstamos activos", "#D18D2C"),
            ("vencidos", "Préstamos vencidos", RED)
        ]):
            tarjeta = tk.Frame(tarjetas, bg=WHITE, highlightbackground=LINE, highlightthickness=1)
            tarjeta.grid(row=0, column=i, sticky="nsew", padx=(0, 9 if i < 4 else 0))
            tarjetas.columnconfigure(i, weight=1, uniform="kpi")
            tk.Frame(tarjeta, bg=tono, width=4).pack(side="left", fill="y")
            tk.Label(tarjeta, text=titulo, bg=WHITE, fg=MUTED,
                     font=("DejaVu Sans", 9), wraplength=125).pack(anchor="w", padx=12, pady=(15, 5))
            valor = tk.Label(tarjeta, text="0", bg=WHITE, fg=NAVY,
                             font=("DejaVu Sans", 26, "bold"))
            valor.pack(anchor="w", padx=12, pady=(0, 18))
            self.indicadores[clave] = valor
        caja = self._card(padre)
        self._subtitulo(caja, "Movimientos recientes")
        self.tabla_inicio = self._tabla(caja, ("N.º", "Usuario", "Libro", "Estado", "Límite"),
                                        (60, 175, 220, 100, 110), 10)

    # ------------------------------------------------------------------------
    # KIOMY: Autores y libros
    # ------------------------------------------------------------------------
    def _libros(self, padre):
        self._titulo_seccion(padre, "Libros y autores", "Registra autores, controla existencias y busca títulos.")
        notebook = ttk.Notebook(padre)
        notebook.pack(fill="both", expand=True)
        pag_libros = tk.Frame(notebook, bg=BG)
        pag_autores = tk.Frame(notebook, bg=BG)
        notebook.add(pag_libros, text="  Catálogo de libros  ")
        notebook.add(pag_autores, text="  Autores  ")
        form = self._card(pag_libros)
        self._subtitulo(form, "Nuevo libro")
        fila = self._form(form, 5)
        self.lib_codigo = self._campo(fila, 0, "Código")
        self.lib_titulo = self._campo(fila, 1, "Título")
        combo = tk.Frame(fila, bg=WHITE)
        combo.grid(row=0, column=2, sticky="ew", padx=(0, 12))
        tk.Label(combo, text="Autor registrado", bg=WHITE, fg=MUTED,
                 font=("DejaVu Sans", 9, "bold")).pack(anchor="w", pady=(0, 4))
        self.lib_autor = ttk.Combobox(combo, state="readonly", width=22, style="Nexo.TCombobox")
        self.lib_autor.pack(fill="x", ipady=4)
        self._autor_ids = {}
        self.lib_categoria = self._campo(fila, 3, "Categoría")
        self.lib_cantidad = self._campo(fila, 4, "Cantidad", "1", ancho=9)
        self._boton(form, "+  Guardar libro", self.guardar_libro).pack(anchor="e", pady=(8, 0))
        caja = self._card(pag_libros)
        busca = tk.Frame(caja, bg=WHITE)
        busca.pack(fill="x", pady=(0, 8))
        self.bus_libro = ttk.Entry(busca, font=("DejaVu Sans", 11))
        self.bus_libro.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 9))
        self.bus_libro.bind("<Return>", lambda _e: self.refrescar_libros())
        self.solo_disponibles = tk.BooleanVar(value=False)
        tk.Checkbutton(busca, text="Solo disponibles", bg=WHITE, fg=TEXT,
                       variable=self.solo_disponibles, command=self.refrescar_libros).pack(side="left")
        self._boton(busca, "Buscar", self.refrescar_libros).pack(side="right", padx=(10, 0))
        self.tabla_libros = self._tabla(caja, ("Código", "Título", "Autor", "Categoría", "Libres / Total"),
                                       (100, 210, 170, 110, 130), 7)
        form_autor = self._card(pag_autores)
        self._subtitulo(form_autor, "Registrar autor")
        fa = self._form(form_autor, 3)
        self.aut_id = self._campo(fa, 0, "ID de autor")
        self.aut_nombre = self._campo(fa, 1, "Nombre")
        self.aut_apellido = self._campo(fa, 2, "Apellido")
        self._boton(form_autor, "+  Guardar autor", self.guardar_autor).pack(anchor="e", pady=(8, 0))
        lista = self._card(pag_autores)
        self._subtitulo(lista, "Autores registrados")
        self.tabla_autores = self._tabla(lista, ("ID de autor", "Nombre", "Apellido"), (130, 210, 210), 11)

    # KIOMY: envía los datos del formulario al registro de autores.
    def guardar_autor(self):
        self._accion("Autor registrado correctamente.",
                     lambda: self.sistema.registrar_autor(self.aut_id.get(), self.aut_nombre.get(),
                                                          self.aut_apellido.get()).mostrar_nombre(),
                     (self.aut_id, self.aut_nombre, self.aut_apellido))

    # KIOMY: guarda libros seleccionando un autor previamente registrado.
    def guardar_libro(self):
        etiqueta = self.lib_autor.get()
        id_autor = self._autor_ids.get(etiqueta, "")
        self._accion("Libro registrado y existencias guardadas.",
                     lambda: self.sistema.registrar_libro(self.lib_codigo.get(), self.lib_titulo.get(),
                                                           id_autor, self.lib_categoria.get(),
                                                           self.lib_cantidad.get()).titulo,
                     (self.lib_codigo, self.lib_titulo, self.lib_categoria))

    def refrescar_libros(self):
        libros = self.sistema.buscar_libros(self.bus_libro.get(), self.solo_disponibles.get())
        self._insertar(self.tabla_libros, [(l.codigo, l.titulo, l.autor.mostrar_nombre(),
                                          l.categoria, f"{l.cantidad_disponible} / {l.cantidad_total}")
                                         for l in libros])

    # ------------------------------------------------------------------------
    # CARLOS: usuarios, validación y búsqueda
    # ------------------------------------------------------------------------
    def _usuarios(self, padre):
        self._titulo_seccion(padre, "Usuarios", "Información centralizada para gestionar lectores.")
        caja = self._card(padre)
        self._subtitulo(caja, "Registrar usuario")
        fila = self._form(caja, 4)
        self.usr_id = self._campo(fila, 0, "Identificación")
        self.usr_nombre = self._campo(fila, 1, "Nombre")
        self.usr_apellido = self._campo(fila, 2, "Apellido")
        self.usr_contacto = self._campo(fila, 3, "Contacto")
        self._boton(caja, "+  Guardar usuario", self.guardar_usuario).pack(anchor="e", pady=(8, 0))
        listado = self._card(padre)
        tk.Label(listado, text="Buscar por ID, nombre, apellido o contacto", fg=MUTED,
                 bg=WHITE, font=("DejaVu Sans", 9)).pack(anchor="w", pady=(0, 6))
        bus = tk.Frame(listado, bg=WHITE)
        bus.pack(fill="x", pady=(0, 10))
        self.bus_usuario = ttk.Entry(bus, font=("DejaVu Sans", 11))
        self.bus_usuario.pack(side="left", fill="x", expand=True, ipady=6)
        self.bus_usuario.bind("<Return>", lambda _e: self.refrescar_usuarios())
        self._boton(bus, "Buscar usuario", self.refrescar_usuarios).pack(side="right", padx=(12, 0))
        self.tabla_usuarios = self._tabla(listado, ("ID", "Nombre", "Apellido", "Contacto"),
                                         (140, 200, 210, 250), 11)

    # CARLOS: guarda usuarios mediante la validación del motor.
    def guardar_usuario(self):
        self._accion("Usuario registrado correctamente.",
                     lambda: self.sistema.registrar_usuario(self.usr_id.get(), self.usr_nombre.get(),
                                                             self.usr_apellido.get(), self.usr_contacto.get()).nombre_completo(),
                     (self.usr_id, self.usr_nombre, self.usr_apellido, self.usr_contacto))

    def refrescar_usuarios(self):
        self._insertar(self.tabla_usuarios, [(u.id_usuario,u.nombre,u.apellido,u.contacto)
                                          for u in self.sistema.buscar_usuarios(self.bus_usuario.get())])

    # ------------------------------------------------------------------------
    # ANDERSON: préstamos y control de disponibilidad
    # ------------------------------------------------------------------------
    def _prestamos(self, padre):
        self._titulo_seccion(padre, "Préstamos", "Se comprueba que existan usuario, libro y ejemplares disponibles.")
        caja = self._card(padre)
        self._subtitulo(caja, "Nuevo préstamo")
        fila = self._form(caja, 3)
        self.pres_usuario = self._campo(fila, 0, "ID de usuario")
        self.pres_libro = self._campo(fila, 1, "Código del libro")
        self.pres_limite = self._campo(fila, 2, "Fecha límite (AAAA-MM-DD)",
                                       (date.today()+timedelta(days=14)).isoformat())
        self._boton(caja, "+  Registrar préstamo", self.guardar_prestamo).pack(anchor="e", pady=(8, 0))
        listado = self._card(padre)
        self._subtitulo(listado, "Préstamos activos")
        self.tabla_prestamos = self._tabla(listado, ("N.º", "Usuario", "Libro", "Fecha", "Límite", "Estado"),
                                          (65, 170, 210, 115, 115, 115), 12)

    # ANDERSON: registra un préstamo y descuenta un ejemplar.
    def guardar_prestamo(self):
        self._accion("Préstamo registrado; un ejemplar fue descontado.",
                     lambda: f"Número de préstamo: {self.sistema.registrar_prestamo(self.pres_usuario.get(), self.pres_libro.get(), self.pres_limite.get()).id_prestamo}",
                     (self.pres_usuario, self.pres_libro))

    # ------------------------------------------------------------------------
    # JEREMY: devoluciones, fechas y multas
    # ------------------------------------------------------------------------
    def _devoluciones(self, padre):
        self._titulo_seccion(padre, "Devoluciones y multas",
                             f"Multa automática: Q {MULTA_DIARIA:.2f} por día de atraso.")
        caja = self._card(padre)
        self._subtitulo(caja, "Registrar devolución")
        fila = self._form(caja, 2)
        self.dev_id = self._campo(fila, 0, "Número de préstamo")
        self.dev_fecha = self._campo(fila, 1, "Fecha real (AAAA-MM-DD; en blanco = hoy)")
        self._boton(caja, "✓  Registrar devolución", self.guardar_devolucion, GREEN).pack(anchor="e", pady=(8, 0))
        listado = self._card(padre)
        self._subtitulo(listado, "Selecciona un préstamo pendiente para devolverlo")
        self.tabla_devoluciones = self._tabla(listado,
                    ("N.º", "Usuario", "Libro", "Fecha límite", "Días de atraso", "Multa acumulada"),
                    (60, 170, 220, 110, 110, 120), 12)
        self.tabla_devoluciones.bind("<<TreeviewSelect>>", self._seleccionar_devolucion)

    def _seleccionar_devolucion(self, _evento=None):
        seleccion = self.tabla_devoluciones.selection()
        if seleccion:
            numero = self.tabla_devoluciones.item(seleccion[0], "values")[0]
            self.dev_id.delete(0, "end")
            self.dev_id.insert(0, numero)

    # JEREMY: registra la devolución y presenta la multa calculada.
    def guardar_devolucion(self):
        def operacion():
            r = self.sistema.devolver_prestamo(self.dev_id.get(), self.dev_fecha.get().strip() or None)
            return f"Días de atraso: {r.dias_atraso} | Multa: Q {r.multa:.2f}\nInventario aumentado en 1."
        self._accion("Devolución registrada correctamente.", operacion, (self.dev_id, self.dev_fecha))

    # ------------------------------------------------------------------------
    # DANY: historial, consultas, vencidos, integridad y respaldos
    # ------------------------------------------------------------------------
    def _historial(self, padre):
        self._titulo_seccion(padre, "Consultas e historial", "Consulta préstamos activos, devueltos y vencidos.")
        caja = self._card(padre)
        controles = tk.Frame(caja, bg=WHITE)
        controles.pack(fill="x", pady=(0, 12))
        self.filtro_historial = tk.StringVar(value="Todos")
        for nombre in ("Todos", "Prestados", "Devueltos", "Vencidos"):
            tk.Radiobutton(controles, text=nombre, value=nombre, variable=self.filtro_historial,
                           command=self.refrescar_historial, bg=WHITE, fg=TEXT,
                           activebackground=WHITE, selectcolor=SKY,
                           font=("DejaVu Sans", 10)).pack(side="left", padx=(0, 12))
        self._boton(controles, "Exportar CSV", self.exportar, NAVY_LIGHT).pack(side="right")
        self.tabla_historial = self._tabla(caja,
            ("N.º", "Usuario", "Libro", "Préstamo", "Límite", "Devolución", "Estado", "Multa Q"),
            (60, 150, 170, 102, 102, 106, 92, 90), 15)
        tk.Label(caja, text="* Para préstamos abiertos, la multa es una estimación al día de hoy.",
                 bg=WHITE, fg=MUTED, font=("DejaVu Sans", 9)).pack(anchor="w", pady=(8, 0))

    def refrescar_historial(self):
        prestamos = self.sistema.listar_prestamos(self.filtro_historial.get())
        self._insertar(self.tabla_historial, [
            (p["id_prestamo"], p["usuario"], p["titulo"], p["fecha_prestamo"],
             p["fecha_limite"], p["fecha_devolucion"] or "Pendiente",
             "Vencido" if p["vencido"] else p["estado"],
             f"{p['multa_visible_centavos']/100:.2f}") for p in prestamos])

    # DANY: refresca indicadores, catálogos, devoluciones e historial.
    def actualizar(self):
        try:
            estad = self.sistema.estadisticas()
            for clave, widget in self.indicadores.items():
                widget.configure(text=str(estad[clave]))
            autores = self.sistema.listar_autores()
            self._autor_ids = {f"{a.id_autor} • {a.mostrar_nombre()}": a.id_autor for a in autores}
            valor_anterior = self.lib_autor.get()
            self.lib_autor["values"] = list(self._autor_ids)
            if valor_anterior in self._autor_ids:
                self.lib_autor.set(valor_anterior)
            elif self._autor_ids:
                self.lib_autor.current(0)
            else:
                self.lib_autor.set("")
            self._insertar(self.tabla_autores, [(a.id_autor,a.nombre,a.apellido) for a in autores])
            self.refrescar_libros()
            self.refrescar_usuarios()
            prestamos = self.sistema.listar_prestamos("Prestados")
            self._insertar(self.tabla_prestamos, [
                (p["id_prestamo"],p["usuario"],p["titulo"],p["fecha_prestamo"],p["fecha_limite"],
                 "Vencido" if p["vencido"] else p["estado"]) for p in prestamos])
            self._insertar(self.tabla_devoluciones, [
                (p["id_prestamo"],p["usuario"],p["titulo"],p["fecha_limite"],p["dias_atraso"],
                 f"Q {p['multa_visible_centavos']/100:.2f}") for p in prestamos])
            todos = self.sistema.listar_prestamos()
            self._insertar(self.tabla_inicio, [
                (p["id_prestamo"],p["usuario"],p["titulo"],
                 "Vencido" if p["vencido"] else p["estado"],p["fecha_limite"])
                for p in todos[:12]])
            self.refrescar_historial()
            self.estado.configure(text=f"✓ Actualizado • Base de datos: {self.sistema.db_path}")
        except (BibliotecaError, sqlite3.Error, OSError) as e:
            messagebox.showerror("Error al actualizar", str(e), parent=self)

    def respaldar(self):
        self._accion("Respaldo SQLite creado de forma segura.",
                     lambda: self.sistema.crear_respaldo())

    def exportar(self):
        self._accion("Exportación CSV realizada correctamente.",
                     lambda: self.sistema.exportar_csv())




# =================================================================
# biblioteca_cli.py | Parte integrada (Python)
# =================================================================
"""Menú alternativo para terminal (útil en Linux sin escritorio).

RESPONSABLE SEGÚN REPARTO: Dany (integración y menú principal).
Mantiene el mismo motor de datos utilizado por la interfaz de ventana.
"""


def menu(sistema: Biblioteca):
    opciones = """
=================== SISTEMA DE BIBLIOTECA ===================
 1. Registrar libro           7. Registrar devolución
 2. Registrar autor           8. Libros disponibles
 3. Registrar usuario         9. Libros prestados
 4. Buscar libro             10. Historial de préstamos
 5. Buscar usuario           11. Préstamos vencidos
 6. Registrar préstamo       12. Salir
 0. Comprobar integridad     13. Crear respaldo
=============================================================
"""
    while True:
        try:
            print(opciones)
            op = input("Seleccione una opción: ").strip()
            if op == "12":
                print("Hasta luego. Los datos permanecen guardados.")
                return
            if op == "1":
                libro = sistema.registrar_libro(input("Código: "), input("Título: "),
                    input("ID autor: "), input("Categoría: "), input("Cantidad: "))
                print(libro.mostrar_informacion())
            elif op == "2":
                print(sistema.registrar_autor(input("ID autor: "),input("Nombre: "),input("Apellido: ")))
            elif op == "3":
                print(sistema.registrar_usuario(input("ID usuario: "),input("Nombre: "),
                    input("Apellido: "),input("Contacto: ")))
            elif op == "4":
                for libro in sistema.buscar_libros(input("Buscar título/código/autor: ")):
                    print(libro.mostrar_informacion())
            elif op == "5":
                for usuario in sistema.buscar_usuarios(input("Buscar nombre/ID: ")):
                    print(usuario)
            elif op == "6":
                p = sistema.registrar_prestamo(input("ID usuario: "),input("Código libro: "),
                                               input("Fecha límite AAAA-MM-DD: "))
                print("Préstamo registrado #", p.id_prestamo)
            elif op == "7":
                d = sistema.devolver_prestamo(input("N.º préstamo: "),
                                             input("Fecha devolución AAAA-MM-DD (vacío = hoy): ") or None)
                print(f"Devuelto. Atraso: {d.dias_atraso} días; multa: Q {d.multa:.2f}")
            elif op == "8":
                for libro in sistema.consultar_libros_disponibles():
                    print(libro.mostrar_informacion())
            elif op in ("9", "10", "11"):
                filtro = {"9":"Prestados", "10":"Todos", "11":"Vencidos"}[op]
                for p in sistema.listar_prestamos(filtro):
                    print(f"#{p['id_prestamo']} | {p['usuario']} | {p['titulo']} | "
                          f"{p['estado']} | límite {p['fecha_limite']} | Q {p['multa_visible_centavos']/100:.2f}")
            elif op == "0":
                print(sistema.verificar_integridad())
            elif op == "13":
                print("Respaldo guardado:", sistema.crear_respaldo())
            else:
                print("Opción no válida.")
        except (BibliotecaError, OSError) as e:
            print("Operación no realizada:", e)
        except (EOFError, KeyboardInterrupt):
            print("\nSaliendo de forma segura.")
            return


# =================================================================
# COMPROBACIÓN DE INTEGRACIÓN — ejecuta: python archivo.py --pruebas
# No toca los datos personales: utiliza una base temporal desechable.
# =================================================================
def pruebas_integracion() -> int:
    from tempfile import TemporaryDirectory
    from datetime import timedelta

    comprobaciones = 0
    def probar(condicion: bool, detalle: str):
        nonlocal comprobaciones
        assert condicion, "Falló la prueba: " + detalle
        comprobaciones += 1

    def rechaza(accion, detalle: str):
        try:
            accion()
        except BibliotecaError:
            probar(True, detalle)
        else:
            probar(False, detalle)

    with TemporaryDirectory(prefix="biblioteca_pruebas_") as carpeta:
        sistema = Biblioteca(carpeta)
        probar(sistema.verificar_integridad()["correcto"], "BD inicial")
        probar(len(sistema.listar_autores()) == 0, "catálogo inicial")
        autor = sistema.registrar_autor("A1", "Ana", "López")
        probar(autor.mostrar_nombre() == "Ana López", "autor")
        rechaza(lambda: sistema.registrar_autor("A1", "Otro", "Autor"), "autor duplicado")
        rechaza(lambda: sistema.registrar_libro("L0", "X", "no-existe", "C", 1), "autor inexistente")
        libro = sistema.registrar_libro("L1", "Cálculo", "A1", "Ciencia", 1)
        probar(libro.cantidadDisponible == 1, "libro guardado")
        rechaza(lambda: sistema.registrar_libro("L1", "Otro", "A1", "C", 1), "libro duplicado")
        rechaza(lambda: sistema.registrar_libro("L2", "X", "A1", "C", -1), "cantidad negativa")
        usuario = sistema.registrar_usuario("U1", "Luis", "Pérez", "correo@ejemplo.com")
        probar(usuario.nombre_completo() == "Luis Pérez", "usuario")
        rechaza(lambda: sistema.registrar_usuario("U1", "Otro", "X", "contacto"), "usuario duplicado")
        rechaza(lambda: sistema.registrar_prestamo("U2", "L1", date.today().isoformat()), "usuario inexistente")
        rechaza(lambda: sistema.registrar_prestamo("U1", "LX", date.today().isoformat()), "libro inexistente")
        limite = (date.today()+timedelta(days=1)).isoformat()
        p = sistema.registrar_prestamo("U1", "L1", limite)
        probar(p.estado == "Prestado", "préstamo creado")
        probar(sistema.buscar_libro("L1").cantidadDisponible == 0, "descuento del inventario")
        rechaza(lambda: sistema.registrar_prestamo("U1", "L1", limite), "sin ejemplares disponibles")
        rechaza(lambda: sistema.devolver_prestamo(999), "préstamo inexistente")
        resultado = sistema.devolver_prestamo(p.id_prestamo)
        probar(resultado.multa_centavos == 0, "devolución sin atraso")
        probar(sistema.buscar_libro("L1").cantidadDisponible == 1, "reposición del inventario")
        rechaza(lambda: sistema.devolver_prestamo(p.id_prestamo), "segunda devolución")
        probar(len(sistema.listar_prestamos("Devueltos")) == 1, "historial")
        probar(sistema.verificar_integridad()["correcto"], "integridad de registros")
        copia = sistema.crear_respaldo()
        probar(copia.is_file(), "respaldo SQLite")
        csv = sistema.exportar_csv()
        probar((csv / "prestamos.csv").is_file(), "exportación CSV")
        reabierto = Biblioteca(carpeta)
        probar(reabierto.buscar_libro("L1") is not None, "persistencia entre aperturas")
        probar(reabierto.verificar_integridad()["correcto"], "integridad al abrir")
    print(f"PRUEBAS CORRECTAS: {comprobaciones}/{comprobaciones}")
    return 0


# =================================================================
# main.py | Parte integrada (Python)
# =================================================================
#!/usr/bin/env python3
# INICIO: Dany selecciona ventana, consola, diagnóstico o respaldo.
import argparse
import platform
import importlib.util
from pathlib import Path
import sqlite3
import sys



def main() -> int:
    parser = argparse.ArgumentParser(description="NEXO: sistema de biblioteca Python")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--gui", action="store_true", help="abrir ventana gráfica (predeterminado)")
    grupo.add_argument("--cli", action="store_true", help="abrir menú de terminal")
    grupo.add_argument("--check", action="store_true", help="comprobar SQLite e inventario")
    grupo.add_argument("--backup", action="store_true", help="crear respaldo SQLite seguro")
    grupo.add_argument("--csv", action="store_true", help="exportar las cuatro tablas a CSV")
    grupo.add_argument("--diagnostico", action="store_true", help="revisar Python, Tkinter y los datos")
    grupo.add_argument("--pruebas", action="store_true", help="probar módulos en una base de datos temporal")
    args = parser.parse_args()
    try:
        # PRUEBAS: usa solamente datos de ejemplo; nunca modifica la biblioteca real.
        if args.pruebas:
            return pruebas_integracion()
        sistema = Biblioteca()
        if args.diagnostico:
            print("Sistema operativo:", platform.system(), platform.release())
            print("Python:", platform.python_version())
            try:
                import tkinter
                print("Tkinter: instalado (versión Tk)", tkinter.TkVersion)
            except ImportError:
                print("Tkinter: NO instalado. Ubuntu/Debian: sudo apt install python3-tk")
            print("SQLite:", sqlite3.sqlite_version)
            print("Base:", sistema.db_path)
            print("Integridad:", sistema.verificar_integridad())
            print("Ventana: requiere escritorio gráfico; --cli no lo requiere.")
            return 0
        if args.check:
            resultado = sistema.verificar_integridad()
            print("CORRECTO" if resultado["correcto"] else "ERROR", "-", "; ".join(resultado["detalles"]))
            return 0 if resultado["correcto"] else 2
        if args.backup:
            print("Respaldo creado en:", sistema.crear_respaldo())
            return 0
        if args.csv:
            print("CSV exportados en:", sistema.exportar_csv())
            return 0
        if args.cli:
            menu(sistema)
            return 0
        try:
            if tk is None:
                print("Tkinter no está instalado. Ubuntu/Debian: sudo apt install python3-tk", file=sys.stderr)
                print("Opción sin ventana: python3 Sistema_Biblioteca_Corregido_Video.py --cli", file=sys.stderr)
                return 1
            app = BibliotecaApp(sistema)
            app.mainloop()
            return 0
        except (ImportError, ModuleNotFoundError) as e:
            print("No se encontró Tkinter. En Debian/Ubuntu: sudo apt install python3-tk", file=sys.stderr)
            print("Si no tienes entorno gráfico, usa: python3 Sistema_Biblioteca_Corregido_Video.py --cli", file=sys.stderr)
            print("Detalle:", e, file=sys.stderr)
            return 1
        except Exception as e:
            # Tk/TclError normalmente indica DISPLAY o Tk ausente. No esconder
            # errores reales del programa: presentar causa y dejar la CLI.
            if tk is not None and isinstance(e, tk.TclError):
                print("No se puede abrir la ventana. Comprueba que Linux tenga escritorio y DISPLAY.", file=sys.stderr)
                print("En Ubuntu/Debian: sudo apt install python3-tk", file=sys.stderr)
                print("Como alternativa: python3 Sistema_Biblioteca_Corregido_Video.py --cli", file=sys.stderr)
                print("Detalle:", e, file=sys.stderr)
                return 1
            raise
    except (BibliotecaError, sqlite3.Error, OSError) as e:
        print("Error controlado:", e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

