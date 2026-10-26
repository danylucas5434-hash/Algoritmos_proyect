#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sistema de Biblioteca: lógica compartida entre consola y ventana.

Python 3.10+, únicamente biblioteca estándar. Los cinco bloques están
señalados para que cada integrante pueda comprender su responsabilidad.
Los originales entregados por el grupo se conservan en originales/.

RESPONSABLES SEGÚN EL SEGUNDO DOCUMENTO (no acreditación de autoría original):
    Kiomy    = Bloque 1: autores y libros
    Carlos   = Bloque 2: usuarios
    Anderson = Bloque 3: préstamos y disponibilidad
    Jeremy   = Bloque 4: devoluciones y multas
    Dany     = Bloque 5: integración, menú, consultas y pruebas.
Todos los comentarios son descriptivos; no cambian la ejecución.
"""
from __future__ import annotations

import argparse
import csv
import os
import sqlite3
import sys
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterator

RAIZ = Path(__file__).resolve().parent
CARPETA_DATOS = RAIZ / "datos"
CARPETA_RESPALDOS = RAIZ / "respaldos"
MULTA_DIARIA = Decimal("5.00")  # Quetzales por cada día de atraso.
MULTA_DIARIA_CENTAVOS = int(MULTA_DIARIA * 100)


class BibliotecaError(ValueError):
    """Error de negocio que se puede mostrar al usuario sin terminar el programa."""


def _texto(valor: object, campo: str, *, requerido: bool = True) -> str:
    texto = " ".join(str(valor if valor is not None else "").split())
    if requerido and not texto:
        raise BibliotecaError(f"El campo '{campo}' es obligatorio.")
    if len(texto) > 250:
        raise BibliotecaError(f"El campo '{campo}' no puede superar 250 caracteres.")
    return texto


def _entero(valor: object, campo: str, *, minimo: int = 0) -> int:
    if isinstance(valor, bool):
        raise BibliotecaError(f"{campo}: ingrese un número entero.")
    cadena = str(valor).strip()
    if not cadena or not cadena.isdecimal():
        raise BibliotecaError(f"{campo}: ingrese un número entero no negativo.")
    numero = int(cadena)
    if numero < minimo or numero > 2_147_483_647:
        raise BibliotecaError(f"{campo}: debe estar entre {minimo} y 2147483647.")
    return numero


def _fecha(valor: date | str, campo: str) -> date:
    if isinstance(valor, datetime):
        raise BibliotecaError(f"{campo}: indique solamente la fecha AAAA-MM-DD.")
    if isinstance(valor, date):
        return valor
    try:
        cadena = str(valor).strip()
        if len(cadena) != 10:
            raise ValueError
        return date.fromisoformat(cadena)
    except (ValueError, TypeError):
        raise BibliotecaError(f"{campo}: use el formato AAAA-MM-DD.") from None


def _normalizar(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in descompuesto if not unicodedata.combining(c)).casefold()


# ---------------------------------------------------------------------------
# BLOQUE 1 · KIOMY · LIBROS Y AUTORES (integrante 1)
# Modelo Autor y Libro; registrar, buscar y conocer disponibilidad.
# ---------------------------------------------------------------------------
# RESPONSABLE DEL MODELO: KIOMY — Clase Autor del proyecto.
@dataclass(frozen=True)
class Autor:
    id_autor: int
    nombre: str
    apellido: str

    def mostrar_nombre(self) -> str:
        return f"{self.nombre} {self.apellido}".strip()


# RESPONSABLE DEL MODELO: KIOMY — Clase Libro del proyecto.
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
        """Nombre de atributo usado en el documento original."""
        return self.cantidad_disponible

    def mostrar_informacion(self) -> str:
        return (f"{self.codigo} | {self.titulo} | {self.autor.mostrar_nombre()} | "
                f"{self.categoria} | disponibles {self.cantidadDisponible}/{self.cantidad_total}")


# ---------------------------------------------------------------------------
# BLOQUE 2 · CARLOS · USUARIOS (integrante 2)
# Usuario identificado por ID positivo; búsqueda y verificación de existencia.
# ---------------------------------------------------------------------------
# RESPONSABLE DEL MODELO: CARLOS — Clase Usuario del proyecto.
@dataclass(frozen=True)
class Usuario:
    id: int
    nombre: str
    apellido: str
    contacto: str

    def nombre_completo(self) -> str:
        return f"{self.nombre} {self.apellido}"

    def __str__(self) -> str:
        return f"ID {self.id} | {self.nombre_completo()} | {self.contacto}"


# ---------------------------------------------------------------------------
# BLOQUE 3 · ANDERSON · PRÉSTAMOS (integrante 3)
# Guardar usuario, libro, fechas y estado; controlar existencias con transacción.
# ---------------------------------------------------------------------------
# RESPONSABLE DEL MODELO: ANDERSON — Clase Prestamo del proyecto.
@dataclass(frozen=True)
class Prestamo:
    id_prestamo: int
    usuario_id: int
    libro_codigo: str
    fecha_prestamo: date
    fecha_limite: date
    fecha_devolucion: date | None
    estado: str
    multa_centavos: int
    nombre_usuario: str = ""
    titulo_libro: str = ""

    # RESPONSABLE: JEREMY — cálculo/estado derivado de los préstamos.
    @property
    def multa(self) -> Decimal:
        return Decimal(self.multa_centavos) / 100

    # RESPONSABLE: JEREMY — cálculo/estado derivado de los préstamos.
    @property
    def dias_atraso(self) -> int:
        final = self.fecha_devolucion or date.today()
        return max(0, (final - self.fecha_limite).days)

    # RESPONSABLE: DANY — cálculo/estado derivado de los préstamos.
    @property
    def esta_vencido(self) -> bool:
        return self.estado == "Prestado" and self.fecha_limite < date.today()

    # RESPONSABLE: JEREMY — cálculo/estado derivado de los préstamos.
    @property
    def multa_estimacion(self) -> Decimal:
        if self.estado == "Devuelto":
            return self.multa
        return MULTA_DIARIA * self.dias_atraso


# ---------------------------------------------------------------------------
# BLOQUE 5 · DANY · INTEGRACIÓN Y ALMACENAMIENTO (integrante 5)
# Base común a consola/ventana. SQLite con WAL, claves foráneas, transacciones,
# protección contra cantidades inválidas y respaldos consistentes.
# ---------------------------------------------------------------------------
class Biblioteca:
    def __init__(self, carpeta_datos: Path | str | None = None,
                 carpeta_respaldos: Path | str | None = None):
        self.carpeta_datos = Path(carpeta_datos) if carpeta_datos else CARPETA_DATOS
        self.carpeta_respaldos = (Path(carpeta_respaldos) if carpeta_respaldos
                                 else CARPETA_RESPALDOS)
        self.carpeta_datos.mkdir(parents=True, exist_ok=True)
        self.carpeta_respaldos.mkdir(parents=True, exist_ok=True)
        # Nombre nuevo: nunca modifica una base antigua biblioteca.db del Word.
        self.archivo_db = self.carpeta_datos / "biblioteca_integrada.sqlite3"
        self._crear_tablas()

    @contextmanager
    def _conexion(self, *, escritura: bool = False) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(str(self.archivo_db), timeout=15)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA foreign_keys=ON")
            con.execute("PRAGMA busy_timeout=15000")
            con.execute("PRAGMA synchronous=FULL")
            if escritura:
                con.execute("BEGIN IMMEDIATE")
            yield con
            if escritura:
                con.commit()
        except BaseException:
            if escritura:
                con.rollback()
            raise
        finally:
            con.close()

    def _crear_tablas(self) -> None:
        # No usa executescript dentro de una transacción explícita, que puede
        # romper sus límites de transacción en sqlite3.
        sentencias = (
            """CREATE TABLE IF NOT EXISTS autores (
                id_autor INTEGER PRIMARY KEY CHECK(id_autor > 0),
                nombre TEXT NOT NULL CHECK(length(trim(nombre)) > 0),
                apellido TEXT NOT NULL CHECK(length(trim(apellido)) > 0),
                UNIQUE(nombre, apellido)
            )""",
            """CREATE TABLE IF NOT EXISTS libros (
                codigo TEXT PRIMARY KEY CHECK(length(trim(codigo)) > 0),
                titulo TEXT NOT NULL CHECK(length(trim(titulo)) > 0),
                autor_id INTEGER NOT NULL REFERENCES autores(id_autor),
                categoria TEXT NOT NULL,
                cantidad_total INTEGER NOT NULL CHECK(cantidad_total >= 0),
                cantidad_disponible INTEGER NOT NULL,
                CHECK(cantidad_disponible BETWEEN 0 AND cantidad_total)
            )""",
            """CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY CHECK(id > 0),
                nombre TEXT NOT NULL CHECK(length(trim(nombre)) > 0),
                apellido TEXT NOT NULL CHECK(length(trim(apellido)) > 0),
                contacto TEXT NOT NULL CHECK(length(trim(contacto)) > 0)
            )""",
            """CREATE TABLE IF NOT EXISTS prestamos (
                id_prestamo INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
                libro_codigo TEXT NOT NULL REFERENCES libros(codigo),
                fecha_prestamo TEXT NOT NULL,
                fecha_limite TEXT NOT NULL,
                fecha_devolucion TEXT,
                estado TEXT NOT NULL CHECK(estado IN ('Prestado','Devuelto')),
                multa_centavos INTEGER NOT NULL DEFAULT 0 CHECK(multa_centavos >= 0),
                CHECK((estado='Prestado' AND fecha_devolucion IS NULL) OR
                      (estado='Devuelto' AND fecha_devolucion IS NOT NULL))
            )""",
            "CREATE INDEX IF NOT EXISTS idx_prestamos_estado ON prestamos(estado)",
            "CREATE INDEX IF NOT EXISTS idx_prestamos_libro ON prestamos(libro_codigo)",
            "CREATE INDEX IF NOT EXISTS idx_prestamos_limite ON prestamos(fecha_limite)",
        )
        with self._conexion(escritura=True) as con:
            con.execute("PRAGMA user_version")
            for sql in sentencias:
                con.execute(sql)
            con.execute("PRAGMA user_version=1")
        # WAL funciona con varios lectores y escritores serializados.
        with self._conexion() as con:
            con.execute("PRAGMA journal_mode=WAL")

    # BLOQUE 1 · KIOMY · FUNCIONES DE AUTORES Y LIBROS ------------------------------
    # RESPONSABLE: KIOMY — Registrar autor y validar unicidad.
    def registrar_autor(self, id_autor: object, nombre: object, apellido: object) -> Autor:
        autor = Autor(_entero(id_autor, "ID de autor", minimo=1),
                      _texto(nombre, "Nombre"), _texto(apellido, "Apellido"))
        try:
            with self._conexion(escritura=True) as con:
                con.execute("INSERT INTO autores(id_autor,nombre,apellido) VALUES(?,?,?)",
                            (autor.id_autor, autor.nombre, autor.apellido))
        except sqlite3.IntegrityError as exc:
            raise BibliotecaError("Ese ID de autor o ese nombre completo ya existe.") from exc
        return autor

    # RESPONSABLE: KIOMY — Consultar autores.
    def listar_autores(self) -> list[Autor]:
        with self._conexion() as con:
            return [Autor(r["id_autor"], r["nombre"], r["apellido"])
                    for r in con.execute("SELECT * FROM autores ORDER BY apellido,nombre")]

    # RESPONSABLE: KIOMY — Localizar autor por ID.
    def buscar_autor(self, id_autor: object) -> Autor | None:
        clave = _entero(id_autor, "ID de autor", minimo=1)
        with self._conexion() as con:
            r = con.execute("SELECT * FROM autores WHERE id_autor=?", (clave,)).fetchone()
        return Autor(r["id_autor"], r["nombre"], r["apellido"]) if r else None

    # RESPONSABLE: KIOMY — Registrar libro vinculado con un autor.
    def registrar_libro(self, codigo: object, titulo: object, id_autor: object,
                       categoria: object, cantidad: object) -> Libro:
        codigo = _texto(codigo, "Código")
        titulo = _texto(titulo, "Título")
        categoria = _texto(categoria, "Categoría")
        id_autor = _entero(id_autor, "ID de autor", minimo=1)
        cantidad = _entero(cantidad, "Cantidad", minimo=0)
        try:
            with self._conexion(escritura=True) as con:
                autor = con.execute("SELECT * FROM autores WHERE id_autor=?", (id_autor,)).fetchone()
                if autor is None:
                    raise BibliotecaError("Primero debe registrar al autor indicado.")
                con.execute("""INSERT INTO libros
                             (codigo,titulo,autor_id,categoria,cantidad_total,cantidad_disponible)
                             VALUES(?,?,?,?,?,?)""",
                            (codigo, titulo, id_autor, categoria, cantidad, cantidad))
        except sqlite3.IntegrityError as exc:
            raise BibliotecaError("El código de libro ya existe o contiene datos inválidos.") from exc
        return self.buscar_libro(codigo)  # type: ignore[return-value]

    # RESPONSABLE: KIOMY — Construir modelo Libro con autor.
    @staticmethod
    def _a_libro(r: sqlite3.Row) -> Libro:
        autor = Autor(r["autor_id"], r["autor_nombre"], r["autor_apellido"])
        return Libro(r["codigo"], r["titulo"], autor, r["categoria"],
                     r["cantidad_total"], r["cantidad_disponible"])

    # RESPONSABLE: KIOMY — Mostrar catálogo completo/disponible.
    def listar_libros(self, solo_disponibles: bool = False) -> list[Libro]:
        sql = """SELECT l.*, a.nombre AS autor_nombre, a.apellido AS autor_apellido
                 FROM libros l JOIN autores a ON a.id_autor=l.autor_id"""
        if solo_disponibles:
            sql += " WHERE l.cantidad_disponible > 0"
        sql += " ORDER BY l.titulo COLLATE NOCASE, l.codigo"
        with self._conexion() as con:
            return [self._a_libro(r) for r in con.execute(sql)]

    # RESPONSABLE: KIOMY — Filtrar stock mayor a cero.
    def consultar_libros_disponibles(self) -> list[Libro]:
        return self.listar_libros(solo_disponibles=True)

    # RESPONSABLE: KIOMY — Buscar libro por código.
    def buscar_libro(self, codigo: object) -> Libro | None:
        codigo = _texto(codigo, "Código")
        with self._conexion() as con:
            r = con.execute("""SELECT l.*, a.nombre autor_nombre, a.apellido autor_apellido
                               FROM libros l JOIN autores a ON a.id_autor=l.autor_id
                               WHERE l.codigo=?""", (codigo,)).fetchone()
        return self._a_libro(r) if r else None

    # RESPONSABLE: KIOMY — Búsqueda flexible de libros.
    def buscar_libros(self, texto: object) -> list[Libro]:
        termino = _normalizar(_texto(texto, "Búsqueda"))
        return [l for l in self.listar_libros()
                if termino in _normalizar(" ".join((l.codigo, l.titulo,
                      l.autor.mostrar_nombre(), l.categoria)))]

    # BLOQUE 2 · CARLOS · FUNCIONES DE USUARIOS --------------------------------------
    # RESPONSABLE: CARLOS — Registrar usuario y validar datos.
    def registrar_usuario(self, id_usuario: object, nombre: object,
                         apellido: object, contacto: object) -> Usuario:
        usuario = Usuario(_entero(id_usuario, "ID de usuario", minimo=1),
                          _texto(nombre, "Nombre"), _texto(apellido, "Apellido"),
                          _texto(contacto, "Contacto"))
        try:
            with self._conexion(escritura=True) as con:
                con.execute("INSERT INTO usuarios(id,nombre,apellido,contacto) VALUES(?,?,?,?)",
                            (usuario.id, usuario.nombre, usuario.apellido, usuario.contacto))
        except sqlite3.IntegrityError as exc:
            raise BibliotecaError("Ya existe un usuario con ese ID.") from exc
        return usuario

    # RESPONSABLE: CARLOS — Consultar usuario por ID.
    def buscar_usuario(self, id_usuario: object) -> Usuario | None:
        clave = _entero(id_usuario, "ID de usuario", minimo=1)
        with self._conexion() as con:
            r = con.execute("SELECT * FROM usuarios WHERE id=?", (clave,)).fetchone()
        return Usuario(r["id"], r["nombre"], r["apellido"], r["contacto"]) if r else None

    # RESPONSABLE: CARLOS — Mostrar todos los usuarios.
    def listar_usuarios(self) -> list[Usuario]:
        with self._conexion() as con:
            return [Usuario(r["id"], r["nombre"], r["apellido"], r["contacto"])
                    for r in con.execute("SELECT * FROM usuarios ORDER BY apellido,nombre")]

    # RESPONSABLE: CARLOS — Buscar por nombre, apellido, ID o contacto.
    def buscar_usuarios(self, texto: object) -> list[Usuario]:
        termino = _normalizar(_texto(texto, "Búsqueda"))
        return [u for u in self.listar_usuarios()
                if termino in _normalizar(f"{u.id} {u.nombre} {u.apellido} {u.contacto}")]

    # RESPONSABLE: CARLOS — Asegurar que exista el usuario.
    def validar_usuario_para_prestamo(self, id_usuario: object) -> Usuario:
        usuario = self.buscar_usuario(id_usuario)
        if usuario is None:
            raise BibliotecaError("El usuario no existe: regístrelo antes de prestar.")
        return usuario

    # BLOQUE 3 · ANDERSON · REGISTRO DE PRÉSTAMOS Y DESCUENTO DE EXISTENCIAS -----------
    # RESPONSABLE: ANDERSON — Comprobar usuario/libro, descontar copia y registrar préstamo.
    def registrar_prestamo(self, id_usuario: object, codigo_libro: object,
                          fecha_limite: str | date,
                          fecha_prestamo: str | date | None = None) -> Prestamo:
        usuario_id = _entero(id_usuario, "ID de usuario", minimo=1)
        codigo = _texto(codigo_libro, "Código de libro")
        inicio = _fecha(fecha_prestamo, "Fecha de préstamo") if fecha_prestamo else date.today()
        limite = _fecha(fecha_limite, "Fecha límite")
        if inicio > date.today():
            raise BibliotecaError("La fecha del préstamo no puede estar en el futuro.")
        if limite < inicio:
            raise BibliotecaError("La fecha límite no puede preceder a la del préstamo.")
        with self._conexion(escritura=True) as con:
            if not con.execute("SELECT 1 FROM usuarios WHERE id=?", (usuario_id,)).fetchone():
                raise BibliotecaError("El usuario no existe: regístrelo primero.")
            if not con.execute("SELECT 1 FROM libros WHERE codigo=?", (codigo,)).fetchone():
                raise BibliotecaError("El libro no existe: regístrelo primero.")
            # Una sola transacción y condición atómica: jamás baja de cero.
            actualizado = con.execute("""UPDATE libros SET cantidad_disponible=cantidad_disponible-1
                                          WHERE codigo=? AND cantidad_disponible>0""", (codigo,))
            if actualizado.rowcount != 1:
                raise BibliotecaError("No hay ejemplares disponibles para prestar.")
            cur = con.execute("""INSERT INTO prestamos
                     (usuario_id,libro_codigo,fecha_prestamo,fecha_limite,
                      fecha_devolucion,estado,multa_centavos)
                     VALUES(?,?,?,?,NULL,'Prestado',0)""",
                              (usuario_id, codigo, inicio.isoformat(), limite.isoformat()))
            prestamo_id = cur.lastrowid
        return self.buscar_prestamo(prestamo_id)  # type: ignore[return-value]

    # RESPONSABLE: ANDERSON — Construir modelo de préstamo.
    @staticmethod
    def _a_prestamo(r: sqlite3.Row) -> Prestamo:
        return Prestamo(r["id_prestamo"], r["usuario_id"], r["libro_codigo"],
                        date.fromisoformat(r["fecha_prestamo"]),
                        date.fromisoformat(r["fecha_limite"]),
                        date.fromisoformat(r["fecha_devolucion"]) if r["fecha_devolucion"] else None,
                        r["estado"], r["multa_centavos"],
                        r["nombre_usuario"], r["titulo_libro"])

    # RESPONSABLE: DANY — Consulta central de préstamos, historial y vencimientos.
    def listar_prestamos(self, *, estado: str | None = None,
                         solo_vencidos: bool = False) -> list[Prestamo]:
        sql = """SELECT p.*, u.nombre || ' ' || u.apellido AS nombre_usuario,
                        l.titulo AS titulo_libro
                 FROM prestamos p JOIN usuarios u ON u.id=p.usuario_id
                 JOIN libros l ON l.codigo=p.libro_codigo WHERE 1=1"""
        parametros: list[object] = []
        if estado is not None:
            if estado not in ("Prestado", "Devuelto"):
                raise BibliotecaError("Estado de préstamo no válido.")
            sql += " AND p.estado=?"
            parametros.append(estado)
        if solo_vencidos:
            sql += " AND p.estado='Prestado' AND p.fecha_limite < ?"
            parametros.append(date.today().isoformat())
        sql += " ORDER BY p.id_prestamo DESC"
        with self._conexion() as con:
            return [self._a_prestamo(r) for r in con.execute(sql, parametros)]

    # RESPONSABLE: DANY — Consultar préstamo por número.
    def buscar_prestamo(self, id_prestamo: object) -> Prestamo | None:
        clave = _entero(id_prestamo, "Número de préstamo", minimo=1)
        with self._conexion() as con:
            r = con.execute("""SELECT p.*,u.nombre || ' ' || u.apellido nombre_usuario,
                               l.titulo titulo_libro
                               FROM prestamos p JOIN usuarios u ON u.id=p.usuario_id
                               JOIN libros l ON l.codigo=p.libro_codigo
                               WHERE p.id_prestamo=?""", (clave,)).fetchone()
        return self._a_prestamo(r) if r else None

    # RESPONSABLE: DANY — Mostrar préstamos activos.
    def consultar_libros_prestados(self) -> list[Prestamo]:
        return self.listar_prestamos(estado="Prestado")

    # RESPONSABLE: DANY — Mostrar historial completo.
    def historial_prestamos(self) -> list[Prestamo]:
        return self.listar_prestamos()

    # RESPONSABLE: DANY — Listar préstamos vencidos.
    def prestamos_vencidos(self) -> list[Prestamo]:
        return self.listar_prestamos(solo_vencidos=True)

    # BLOQUE 4 · JEREMY · DEVOLUCIONES Y MULTAS (integrante 4) -----------------------
    # RESPONSABLE: JEREMY — Devolver una sola vez, reintegrar copia y calcular multa.
    def registrar_devolucion(self, id_prestamo: object,
                            fecha_devolucion: date | str | None = None) -> Prestamo:
        clave = _entero(id_prestamo, "Número de préstamo", minimo=1)
        devolucion = _fecha(fecha_devolucion, "Fecha de devolución") if fecha_devolucion else date.today()
        if devolucion > date.today():
            raise BibliotecaError("No se puede registrar una devolución futura.")
        with self._conexion(escritura=True) as con:
            p = con.execute("SELECT * FROM prestamos WHERE id_prestamo=?", (clave,)).fetchone()
            if p is None:
                raise BibliotecaError("El préstamo indicado no existe.")
            if p["estado"] != "Prestado":
                raise BibliotecaError("Este préstamo ya fue devuelto: no se suma otra copia.")
            inicio = date.fromisoformat(p["fecha_prestamo"])
            if devolucion < inicio:
                raise BibliotecaError("La devolución no puede preceder al préstamo.")
            dias = max(0, (devolucion - date.fromisoformat(p["fecha_limite"])).days)
            multa_centavos = dias * MULTA_DIARIA_CENTAVOS
            resultado = con.execute("""UPDATE prestamos
                    SET estado='Devuelto', fecha_devolucion=?, multa_centavos=?
                    WHERE id_prestamo=? AND estado='Prestado'""",
                                    (devolucion.isoformat(), multa_centavos, clave))
            if resultado.rowcount != 1:
                raise BibliotecaError("La devolución ya se había realizado.")
            stock = con.execute("""UPDATE libros
                    SET cantidad_disponible=cantidad_disponible+1
                    WHERE codigo=? AND cantidad_disponible<cantidad_total""",
                                (p["libro_codigo"],))
            if stock.rowcount != 1:
                raise BibliotecaError("Inconsistencia de inventario; operación cancelada sin cambios.")
        return self.buscar_prestamo(clave)  # type: ignore[return-value]

    # BLOQUE 5 · DANY · CONSULTAS, RESPALDOS Y CONTROL DE INTEGRIDAD ---------------
    # RESPONSABLE: DANY — Calcular contadores de tablero.
    def estadisticas(self) -> dict[str, int]:
        with self._conexion() as con:
            return {
                "titulos": con.execute("SELECT COUNT(*) FROM libros").fetchone()[0],
                "ejemplares": con.execute("SELECT COALESCE(SUM(cantidad_total),0) FROM libros").fetchone()[0],
                "disponibles": con.execute("SELECT COALESCE(SUM(cantidad_disponible),0) FROM libros").fetchone()[0],
                "usuarios": con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0],
                "prestados": con.execute("SELECT COUNT(*) FROM prestamos WHERE estado='Prestado'").fetchone()[0],
                "vencidos": con.execute("SELECT COUNT(*) FROM prestamos WHERE estado='Prestado' AND fecha_limite<?",
                                        (date.today().isoformat(),)).fetchone()[0],
            }

    # RESPONSABLE: DANY — Auditar SQLite, relaciones y cantidades.
    def verificar_integridad(self) -> list[str]:
        """Devuelve errores. Lista vacía = verificaciones superadas."""
        fallos: list[str] = []
        with self._conexion() as con:
            for r in con.execute("PRAGMA integrity_check"):
                if r[0] != "ok":
                    fallos.append(f"SQLite: {r[0]}")
            for r in con.execute("PRAGMA foreign_key_check"):
                fallos.append(f"Referencia inválida: {tuple(r)}")
            sql = """SELECT l.codigo,l.cantidad_total,l.cantidad_disponible,
                         (SELECT COUNT(*) FROM prestamos p
                           WHERE p.libro_codigo=l.codigo AND p.estado='Prestado') activos
                     FROM libros l"""
            for r in con.execute(sql):
                if r["cantidad_total"] - r["cantidad_disponible"] != r["activos"]:
                    fallos.append(f"Inventario inconsistente para libro {r['codigo']}.")
        return fallos

    # RESPONSABLE: DANY — Crear copia SQLite consistente.
    def crear_respaldo(self) -> Path:
        """SQLite online backup; escribir temporal y renombrar atómicamente."""
        fallos = self.verificar_integridad()
        if fallos:
            raise BibliotecaError("No se creó el respaldo: " + "; ".join(fallos))
        sufijo = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        destino = self.carpeta_respaldos / f"biblioteca_{sufijo}.sqlite3"
        temporal = destino.with_suffix(".temporal")
        try:
            with sqlite3.connect(str(self.archivo_db)) as origen:
                with sqlite3.connect(str(temporal)) as copia:
                    origen.backup(copia)
            # RESPONSABLE: DANY — verificar copia antes de ofrecer el respaldo.
            with sqlite3.connect(str(temporal)) as copia_verificada:
                if copia_verificada.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise BibliotecaError("La copia SQLite no superó integrity_check.")
            os.replace(temporal, destino)
        finally:
            if temporal.exists():
                temporal.unlink()
        return destino

    # RESPONSABLE: DANY — Exportar registros con cabeceras.
    def exportar_csv(self) -> Path:
        """Exporta las 4 tablas sin reemplazar ni modificar la BD."""
        sufijo = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        carpeta = self.carpeta_respaldos / f"csv_{sufijo}"
        carpeta.mkdir(parents=True, exist_ok=False)
        with self._conexion() as con:
            for tabla in ("autores", "libros", "usuarios", "prestamos"):
                columnas = [r[1] for r in con.execute(f"PRAGMA table_info({tabla})")]
                registros = con.execute(f"SELECT * FROM {tabla}").fetchall()
                with (carpeta / f"{tabla}.csv").open("w", encoding="utf-8-sig", newline="") as f:
                    escritor = csv.writer(f)
                    escritor.writerow(columnas)
                    escritor.writerows([list(r) for r in registros])
        return carpeta


# BLOQUE 5 · DANY · MENÚ DE CONSOLA: 11 OPERACIONES + SALIR -----------------------
def _mostrar_libros(libros: list[Libro]) -> None:
    if not libros:
        print("No se encontraron libros.")
    for libro in libros:
        print(" -", libro.mostrar_informacion())


def _mostrar_prestamos(prestamos: list[Prestamo]) -> None:
    if not prestamos:
        print("No hay préstamos para esta consulta.")
    for p in prestamos:
        devolucion = p.fecha_devolucion or "Pendiente"
        print(f" - #{p.id_prestamo} | {p.nombre_usuario} | {p.titulo_libro} "
              f"| {p.fecha_prestamo} → {p.fecha_limite} | Devolución: {devolucion} "
              f"| {p.estado} | Multa {'final' if p.estado == 'Devuelto' else 'estimada'} "
              f"Q{p.multa_estimacion:.2f}")


def menu_consola(b: Biblioteca) -> None:
    opciones = """
╔══════════════════════════════════════════════╗
║            SISTEMA DE BIBLIOTECA             ║
╚══════════════════════════════════════════════╝
 1. Registrar libro             7. Registrar devolución
 2. Registrar autor             8. Libros disponibles
 3. Registrar usuario           9. Libros prestados
 4. Buscar libro               10. Historial de préstamos
 5. Buscar usuario             11. Préstamos vencidos
 6. Registrar préstamo         12. Salir
13. Crear respaldo             14. Verificar integridad
15. Exportar CSV
"""
    def pedir(campo: str) -> str:
        return input(f"{campo}: ").strip()

    while True:
        try:
            print(opciones)
            opcion = pedir("Seleccione una opción")
            if opcion == "1":
                libro = b.registrar_libro(pedir("Código"), pedir("Título"),
                          pedir("ID del autor registrado"), pedir("Categoría"), pedir("Cantidad total"))
                print("Libro registrado:", libro.mostrar_informacion())
            elif opcion == "2":
                autor = b.registrar_autor(pedir("ID autor"), pedir("Nombre"), pedir("Apellido"))
                print("Autor registrado:", autor.mostrar_nombre())
            elif opcion == "3":
                usuario = b.registrar_usuario(pedir("ID usuario"), pedir("Nombre"),
                                             pedir("Apellido"), pedir("Contacto"))
                print("Usuario registrado:", usuario)
            elif opcion == "4":
                _mostrar_libros(b.buscar_libros(pedir("Código, título, autor o categoría")))
            elif opcion == "5":
                resultado = b.buscar_usuarios(pedir("ID, nombre, apellido o contacto"))
                print("\n".join(map(str, resultado)) if resultado else "No hay coincidencias.")
            elif opcion == "6":
                p = b.registrar_prestamo(pedir("ID usuario"), pedir("Código libro"),
                                        pedir("Fecha límite AAAA-MM-DD"))
                print(f"Préstamo #{p.id_prestamo} guardado. Se descontó un ejemplar.")
            elif opcion == "7":
                p = b.registrar_devolucion(pedir("Número de préstamo"),
                                           pedir("Fecha devolución AAAA-MM-DD (vacío=hoy)") or None)
                print(f"Devolución registrada. Atraso: {p.dias_atraso} días; "
                      f"multa: Q{p.multa:.2f}. Se restauró un ejemplar.")
            elif opcion == "8":
                _mostrar_libros(b.consultar_libros_disponibles())
            elif opcion == "9":
                _mostrar_prestamos(b.consultar_libros_prestados())
            elif opcion == "10":
                _mostrar_prestamos(b.historial_prestamos())
            elif opcion == "11":
                _mostrar_prestamos(b.prestamos_vencidos())
            elif opcion == "12":
                print("Datos guardados. ¡Hasta luego!")
                return
            elif opcion == "13":
                print("Respaldo creado:", b.crear_respaldo())
            elif opcion == "14":
                fallos = b.verificar_integridad()
                print("Integridad correcta: sin errores." if not fallos else "\n".join(fallos))
            elif opcion == "15":
                print("Archivos CSV:", b.exportar_csv())
            else:
                print("Seleccione una opción válida.")
        except (BibliotecaError, sqlite3.Error, OSError) as exc:
            print("Error:", exc)
        except (KeyboardInterrupt, EOFError):
            print("\nSaliendo sin descartar los datos guardados.")
            return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sistema de Biblioteca, solo Python")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--verificar", action="store_true", help="Comprueba SQLite, referencias e inventario")
    grupo.add_argument("--respaldar", action="store_true", help="Crea copia consistente en respaldos/")
    grupo.add_argument("--exportar-csv", action="store_true", help="Exporta todas las tablas")
    args = parser.parse_args(argv)
    try:
        b = Biblioteca()
        if args.verificar:
            fallos = b.verificar_integridad()
            if fallos:
                for falla in fallos:
                    print("ERROR:", falla, file=sys.stderr)
                return 1
            print("Integridad correcta: SQLite, relaciones e inventario.")
        elif args.respaldar:
            print("Respaldo seguro:", b.crear_respaldo())
        elif args.exportar_csv:
            print("CSV exportado en:", b.exportar_csv())
        else:
            menu_consola(b)
        return 0
    except (BibliotecaError, sqlite3.Error, OSError) as exc:
        print(f"No se pudo iniciar/ejecutar el sistema: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
