#!/usr/bin/env python3
# Sistema de biblioteca: usuarios, autores, libros, préstamos, devoluciones y multas.
# Python 3.10+. Usa SQLite para conservar datos entre ejecuciones.
# No modifica archivos fuente existentes: crea/usa su propia carpeta de datos.

from __future__ import annotations
import sqlite3
from datetime import date, datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "datos"
BACKUP_DIR = APP_DIR / "respaldos"
DB_PATH = DATA_DIR / "biblioteca.db"
MULTA_DIARIA = 5.00

DATA_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def conectar():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


def inicializar_bd():
    with conectar() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS autores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS libros (
            codigo TEXT PRIMARY KEY,
            titulo TEXT NOT NULL,
            autor_id INTEGER NOT NULL REFERENCES autores(id),
            categoria TEXT NOT NULL DEFAULT '',
            cantidad_total INTEGER NOT NULL CHECK(cantidad_total >= 0),
            cantidad_disponible INTEGER NOT NULL CHECK(cantidad_disponible >= 0)
        );
        CREATE TABLE IF NOT EXISTS usuarios (
            id TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            apellido TEXT NOT NULL,
            contacto TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS prestamos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id TEXT NOT NULL REFERENCES usuarios(id),
            libro_codigo TEXT NOT NULL REFERENCES libros(codigo),
            fecha_prestamo TEXT NOT NULL,
            fecha_limite TEXT NOT NULL,
            fecha_devolucion TEXT,
            estado TEXT NOT NULL DEFAULT 'Prestado'
                CHECK(estado IN ('Prestado','Devuelto')),
            multa REAL NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_prestamos_estado ON prestamos(estado);
        """)
        con.commit()


def crear_respaldo():
    """Crea una copia consistente de la base de datos, sin borrar la original."""
    if not DB_PATH.exists():
        return None
    destino = BACKUP_DIR / f"biblioteca_{datetime.now():%Y%m%d_%H%M%S}.db"
    origen = sqlite3.connect(DB_PATH)
    copia = sqlite3.connect(destino)
    try:
        origen.backup(copia)
    finally:
        copia.close()
        origen.close()
    return destino


def texto_fecha(valor):
    try:
        return date.fromisoformat(valor.strip())
    except (ValueError, AttributeError):
        raise ValueError("La fecha debe tener formato AAAA-MM-DD (por ejemplo, 2026-10-20).")


def registrar_autor(nombre):
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("Escriba el nombre del autor.")
    with conectar() as con:
        con.execute("INSERT INTO autores(nombre) VALUES (?)", (nombre,))


def registrar_libro(codigo, titulo, autor_nombre, categoria, cantidad):
    codigo, titulo, autor_nombre = codigo.strip(), titulo.strip(), autor_nombre.strip()
    if not codigo or not titulo or not autor_nombre:
        raise ValueError("Código, título y autor son obligatorios.")
    try:
        cantidad = int(cantidad)
    except ValueError:
        raise ValueError("La cantidad debe ser un número entero.")
    if cantidad < 0:
        raise ValueError("La cantidad no puede ser negativa.")
    with conectar() as con:
        autor = con.execute("SELECT id FROM autores WHERE nombre = ?", (autor_nombre,)).fetchone()
        if not autor:
            raise ValueError("Ese autor no existe. Registre primero al autor.")
        con.execute("""INSERT INTO libros
            (codigo,titulo,autor_id,categoria,cantidad_total,cantidad_disponible)
            VALUES (?,?,?,?,?,?)""",
            (codigo, titulo, autor["id"], categoria.strip(), cantidad, cantidad))


def registrar_usuario(id_usuario, nombre, apellido, contacto):
    valores = [id_usuario.strip(), nombre.strip(), apellido.strip(), contacto.strip()]
    if not valores[0] or not valores[1] or not valores[2]:
        raise ValueError("ID, nombre y apellido son obligatorios.")
    with conectar() as con:
        con.execute("INSERT INTO usuarios(id,nombre,apellido,contacto) VALUES (?,?,?,?)", valores)


def registrar_prestamo(id_usuario, codigo_libro, fecha_limite):
    limite = texto_fecha(fecha_limite)
    hoy = date.today()
    if limite < hoy:
        raise ValueError("La fecha límite no puede estar antes de hoy.")
    with conectar() as con:
        usuario = con.execute("SELECT id FROM usuarios WHERE id=?", (id_usuario.strip(),)).fetchone()
        if not usuario:
            raise ValueError("El usuario no existe. Regístrelo antes del préstamo.")
        libro = con.execute("SELECT cantidad_disponible FROM libros WHERE codigo=?",
                            (codigo_libro.strip(),)).fetchone()
        if not libro:
            raise ValueError("El libro no existe.")
        if libro["cantidad_disponible"] < 1:
            raise ValueError("No hay ejemplares disponibles; no se puede prestar.")
        con.execute("UPDATE libros SET cantidad_disponible=cantidad_disponible-1 WHERE codigo=?",
                    (codigo_libro.strip(),))
        con.execute("""INSERT INTO prestamos
            (usuario_id,libro_codigo,fecha_prestamo,fecha_limite,estado,multa)
            VALUES (?,?,?,?, 'Prestado',0)""",
            (id_usuario.strip(), codigo_libro.strip(), hoy.isoformat(), limite.isoformat()))


def devolver_prestamo(id_prestamo, fecha_devolucion=None):
    try:
        prestamo_id = int(id_prestamo)
    except ValueError:
        raise ValueError("El número de préstamo debe ser un entero.")
    fecha_real = texto_fecha(fecha_devolucion) if fecha_devolucion else date.today()
    with conectar() as con:
        p = con.execute("SELECT * FROM prestamos WHERE id=?", (prestamo_id,)).fetchone()
        if not p:
            raise ValueError("No se encontró ese préstamo.")
        if p["estado"] == "Devuelto":
            raise ValueError("Este préstamo ya fue devuelto; no se volverá a sumar disponibilidad.")
        dias_atraso = max(0, (fecha_real - date.fromisoformat(p["fecha_limite"])).days)
        multa = round(dias_atraso * MULTA_DIARIA, 2)
        con.execute("""UPDATE prestamos
            SET estado='Devuelto', fecha_devolucion=?, multa=? WHERE id=?""",
            (fecha_real.isoformat(), multa, prestamo_id))
        con.execute("UPDATE libros SET cantidad_disponible=cantidad_disponible+1 WHERE codigo=?",
                    (p["libro_codigo"],))
    return dias_atraso, multa


def filas_consulta(sql, params=()):
    with conectar() as con:
        return [dict(r) for r in con.execute(sql, params).fetchall()]


def exportar_respaldo_csv():
    """Respaldo legible en CSV separado por tabla; conserva también la BD original."""
    import csv
    carpeta = BACKUP_DIR / f"exportacion_{datetime.now():%Y%m%d_%H%M%S}"
    carpeta.mkdir(parents=True, exist_ok=False)
    tablas = ("autores", "libros", "usuarios", "prestamos")
    with conectar() as con:
        for tabla in tablas:
            registros = con.execute(f"SELECT * FROM {tabla}").fetchall()
            ruta = carpeta / f"{tabla}.csv"
            with ruta.open("w", newline="", encoding="utf-8-sig") as archivo:
                if registros:
                    escritor = csv.DictWriter(archivo, fieldnames=registros[0].keys())
                    escritor.writeheader()
                    escritor.writerows([dict(r) for r in registros])
                else:
                    archivo.write("")
    return carpeta


class BibliotecaApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Sistema de Biblioteca")
        self.geometry("1050x700")
        self.minsize(760, 560)
        self.configure(bg="#f3f6fb")
        self._estilos()
        self._interfaz()
        self.refrescar()

    def _estilos(self):
        estilo = ttk.Style(self)
        try:
            estilo.theme_use("clam")
        except tk.TclError:
            pass
        estilo.configure("TFrame", background="#f3f6fb")
        estilo.configure("TLabel", background="#f3f6fb", foreground="#182230", font=("Arial", 10))
        estilo.configure("Titulo.TLabel", font=("Arial", 19, "bold"), foreground="#153e75")
        estilo.configure("TButton", font=("Arial", 10), padding=7)
        estilo.configure("Treeview", font=("Arial", 9), rowheight=27)
        estilo.configure("Treeview.Heading", font=("Arial", 9, "bold"))

    def _interfaz(self):
        encabezado = ttk.Frame(self, padding=(18, 16))
        encabezado.pack(fill="x")
        ttk.Label(encabezado, text="Sistema de Biblioteca", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(encabezado, text=f"Multa diaria: Q {MULTA_DIARIA:.2f} · Los datos se guardan automáticamente").pack(anchor="w", pady=(4, 0))

        barra = ttk.Frame(self, padding=(12, 0, 12, 8))
        barra.pack(fill="x")
        self.pestanas = ttk.Notebook(self)
        self.pestanas.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.tab_libros = ttk.Frame(self.pestanas, padding=12)
        self.tab_usuarios = ttk.Frame(self.pestanas, padding=12)
        self.tab_prestamos = ttk.Frame(self.pestanas, padding=12)
        self.tab_devoluciones = ttk.Frame(self.pestanas, padding=12)
        self.tab_consultas = ttk.Frame(self.pestanas, padding=12)
        for tab, nombre in [(self.tab_libros, "Libros y autores"), (self.tab_usuarios, "Usuarios"),
                            (self.tab_prestamos, "Préstamos"), (self.tab_devoluciones, "Devoluciones y multas"),
                            (self.tab_consultas, "Consultas e historial")]:
            self.pestanas.add(tab, text=nombre)

        self._form_libros()
        self._form_usuarios()
        self._form_prestamos()
        self._form_devoluciones()
        self._form_consultas()

        ttk.Button(barra, text="Crear respaldo ahora", command=self.respaldar).pack(side="right")
        ttk.Button(barra, text="Actualizar tablas", command=self.refrescar).pack(side="right", padx=8)

    def _campo(self, padre, etiqueta, fila, columna, ancho=24):
        ttk.Label(padre, text=etiqueta).grid(row=fila, column=columna, sticky="w", padx=5, pady=5)
        entrada = ttk.Entry(padre, width=ancho)
        entrada.grid(row=fila, column=columna+1, sticky="ew", padx=5, pady=5)
        return entrada

    def _form_libros(self):
        f = self.tab_libros
        ttk.Label(f, text="Registrar autor", font=("Arial", 12, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.autor_nombre = self._campo(f, "Nombre del autor", 1, 0)
        ttk.Button(f, text="Guardar autor", command=self.guardar_autor).grid(row=1, column=2, padx=5)
        ttk.Separator(f).grid(row=2, column=0, columnspan=4, sticky="ew", pady=12)
        ttk.Label(f, text="Registrar libro (el autor debe existir)", font=("Arial", 12, "bold")).grid(row=3, column=0, sticky="w", pady=(0, 8))
        self.lib_codigo = self._campo(f, "Código", 4, 0)
        self.lib_titulo = self._campo(f, "Título", 4, 2)
        self.lib_autor = self._campo(f, "Autor exacto", 5, 0)
        self.lib_categoria = self._campo(f, "Categoría", 5, 2)
        self.lib_cantidad = self._campo(f, "Cantidad total", 6, 0)
        self.lib_cantidad.insert(0, "1")
        ttk.Button(f, text="Guardar libro", command=self.guardar_libro).grid(row=6, column=2, padx=5)
        self.tabla_libros = self._tabla(f, ("Código", "Título", "Autor", "Categoría", "Disponibles"), 7)
        for c in range(4):
            f.columnconfigure(c, weight=1)

    def _form_usuarios(self):
        f = self.tab_usuarios
        ttk.Label(f, text="Registrar usuario", font=("Arial", 12, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.usr_id = self._campo(f, "ID de usuario", 1, 0)
        self.usr_nombre = self._campo(f, "Nombre", 1, 2)
        self.usr_apellido = self._campo(f, "Apellido", 2, 0)
        self.usr_contacto = self._campo(f, "Contacto", 2, 2)
        ttk.Button(f, text="Guardar usuario", command=self.guardar_usuario).grid(row=3, column=0, sticky="w", padx=5, pady=8)
        self.tabla_usuarios = self._tabla(f, ("ID", "Nombre", "Apellido", "Contacto"), 4)
        for c in range(4):
            f.columnconfigure(c, weight=1)

    def _form_prestamos(self):
        f = self.tab_prestamos
        ttk.Label(f, text="Registrar préstamo", font=("Arial", 12, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.pres_usuario = self._campo(f, "ID de usuario", 1, 0)
        self.pres_libro = self._campo(f, "Código del libro", 1, 2)
        self.pres_limite = self._campo(f, "Fecha límite AAAA-MM-DD", 2, 0, 26)
        self.pres_limite.insert(0, date.today().replace(day=min(28, date.today().day)).isoformat())
        ttk.Button(f, text="Registrar préstamo", command=self.guardar_prestamo).grid(row=2, column=2, padx=5)
        ttk.Label(f, text="El sistema valida usuario, libro y ejemplares disponibles.").grid(row=3, column=0, columnspan=4, sticky="w", padx=5, pady=8)
        self.tabla_prestamos = self._tabla(f, ("N.º", "Usuario", "Libro", "Préstamo", "Fecha límite", "Estado"), 4)
        for c in range(4):
            f.columnconfigure(c, weight=1)

    def _form_devoluciones(self):
        f = self.tab_devoluciones
        ttk.Label(f, text="Devolver libro y calcular multa", font=("Arial", 12, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.dev_id = self._campo(f, "N.º de préstamo", 1, 0)
        self.dev_fecha = self._campo(f, "Fecha real AAAA-MM-DD (vacío = hoy)", 1, 2, 32)
        ttk.Button(f, text="Registrar devolución", command=self.guardar_devolucion).grid(row=2, column=0, sticky="w", padx=5, pady=8)
        self.tabla_devoluciones = self._tabla(f, ("N.º", "Usuario", "Libro", "Límite", "Devolución", "Días atraso", "Multa Q", "Estado"), 3)
        ttk.Label(f, text="Seleccione un préstamo en la tabla para copiar su número.", foreground="#475467").grid(row=4, column=0, columnspan=4, sticky="w", padx=5, pady=8)
        self.tabla_devoluciones.bind("<<TreeviewSelect>>", self.seleccionar_devolucion)
        for c in range(4):
            f.columnconfigure(c, weight=1)

    def _form_consultas(self):
        f = self.tab_consultas
        ttk.Label(f, text="Historial, préstamos vencidos y disponibilidad", font=("Arial", 12, "bold")).pack(anchor="w", pady=(0, 8))
        botones = ttk.Frame(f)
        botones.pack(fill="x", pady=(0, 8))
        ttk.Button(botones, text="Todos los préstamos", command=self.refrescar).pack(side="left", padx=(0, 6))
        ttk.Button(botones, text="Solo vencidos", command=self.mostrar_vencidos).pack(side="left", padx=6)
        ttk.Button(botones, text="Exportar respaldo CSV", command=self.exportar).pack(side="left", padx=6)
        self.tabla_consultas = self._tabla(f, ("N.º", "Usuario", "Libro", "Fecha préstamo", "Fecha límite", "Devolución", "Estado", "Multa Q"), 0, pack=True)

    def _tabla(self, padre, columnas, fila, pack=False):
        marco = ttk.Frame(padre)
        if pack:
            marco.pack(fill="both", expand=True)
        else:
            marco.grid(row=fila, column=0, columnspan=4, sticky="nsew", pady=(12, 0))
            padre.rowconfigure(fila, weight=1)
        tabla = ttk.Treeview(marco, columns=columnas, show="headings", height=10)
        barra_y = ttk.Scrollbar(marco, orient="vertical", command=tabla.yview)
        barra_x = ttk.Scrollbar(marco, orient="horizontal", command=tabla.xview)
        tabla.configure(yscrollcommand=barra_y.set, xscrollcommand=barra_x.set)
        tabla.grid(row=0, column=0, sticky="nsew")
        barra_y.grid(row=0, column=1, sticky="ns")
        barra_x.grid(row=1, column=0, sticky="ew")
        marco.rowconfigure(0, weight=1)
        marco.columnconfigure(0, weight=1)
        for col in columnas:
            tabla.heading(col, text=col)
            tabla.column(col, width=115, minwidth=75, anchor="w")
        return tabla

    def _accion(self, funcion):
        try:
            resultado = funcion()
            self.refrescar()
            if resultado is not None:
                return resultado
        except (ValueError, sqlite3.IntegrityError) as e:
            mensaje = str(e)
            if isinstance(e, sqlite3.IntegrityError):
                mensaje = "No se pudo guardar. Revise que el código/ID/nombre no esté duplicado y que los datos relacionados existan."
            messagebox.showerror("No se pudo completar", mensaje, parent=self)

    def guardar_autor(self):
        self._accion(lambda: (registrar_autor(self.autor_nombre.get()), messagebox.showinfo("Correcto", "Autor registrado.", parent=self)))

    def guardar_libro(self):
        self._accion(lambda: (registrar_libro(self.lib_codigo.get(), self.lib_titulo.get(), self.lib_autor.get(),
                                             self.lib_categoria.get(), self.lib_cantidad.get()),
                              messagebox.showinfo("Correcto", "Libro registrado.", parent=self)))

    def guardar_usuario(self):
        self._accion(lambda: (registrar_usuario(self.usr_id.get(), self.usr_nombre.get(), self.usr_apellido.get(), self.usr_contacto.get()),
                              messagebox.showinfo("Correcto", "Usuario registrado.", parent=self)))

    def guardar_prestamo(self):
        self._accion(lambda: (registrar_prestamo(self.pres_usuario.get(), self.pres_libro.get(), self.pres_limite.get()),
                              messagebox.showinfo("Correcto", "Préstamo registrado; disponibilidad actualizada.", parent=self)))

    def guardar_devolucion(self):
        def operacion():
            dias, multa = devolver_prestamo(self.dev_id.get(), self.dev_fecha.get() or None)
            messagebox.showinfo("Devolución registrada", f"Días de atraso: {dias}\\nMulta: Q {multa:.2f}\\nDisponibilidad del libro aumentada en 1.", parent=self)
        self._accion(operacion)

    def seleccionar_devolucion(self, _evento=None):
        seleccion = self.tabla_devoluciones.selection()
        if seleccion:
            valores = self.tabla_devoluciones.item(seleccion[0], "values")
            self.dev_id.delete(0, "end")
            self.dev_id.insert(0, valores[0])

    def _limpiar(self, tabla):
        for item in tabla.get_children():
            tabla.delete(item)

    def refrescar(self):
        if not hasattr(self, "tabla_libros"):
            return
        self._limpiar(self.tabla_libros)
        for r in filas_consulta("""SELECT l.codigo,l.titulo,a.nombre AS autor,l.categoria,l.cantidad_disponible
                                 FROM libros l JOIN autores a ON a.id=l.autor_id ORDER BY l.titulo"""):
            self.tabla_libros.insert("", "end", values=(r["codigo"], r["titulo"], r["autor"], r["categoria"], r["cantidad_disponible"]))
        self._limpiar(self.tabla_usuarios)
        for r in filas_consulta("SELECT * FROM usuarios ORDER BY apellido,nombre"):
            self.tabla_usuarios.insert("", "end", values=(r["id"], r["nombre"], r["apellido"], r["contacto"]))
        self._cargar_prestamos()
        self._cargar_devoluciones()
        self.mostrar_historial()

    def _cargar_prestamos(self):
        self._limpiar(self.tabla_prestamos)
        for r in filas_consulta("""SELECT p.id,p.usuario_id,l.titulo,p.fecha_prestamo,p.fecha_limite,p.estado
                                  FROM prestamos p JOIN libros l ON l.codigo=p.libro_codigo
                                  WHERE p.estado='Prestado' ORDER BY p.id DESC"""):
            self.tabla_prestamos.insert("", "end", values=(r["id"], r["usuario_id"], r["titulo"], r["fecha_prestamo"], r["fecha_limite"], r["estado"]))

    def _cargar_devoluciones(self):
        self._limpiar(self.tabla_devoluciones)
        hoy = date.today()
        for r in filas_consulta("""SELECT p.id,p.usuario_id,l.titulo,p.fecha_limite,p.fecha_devolucion,p.estado,p.multa
                                  FROM prestamos p JOIN libros l ON l.codigo=p.libro_codigo ORDER BY p.id DESC"""):
            referencia = date.fromisoformat(r["fecha_devolucion"]) if r["fecha_devolucion"] else hoy
            dias = max(0, (referencia - date.fromisoformat(r["fecha_limite"])).days) if (r["fecha_devolucion"] or r["estado"] == "Prestado") else 0
            multa_mostrada = r["multa"] if r["estado"] == "Devuelto" else dias * MULTA_DIARIA
            self.tabla_devoluciones.insert("", "end", values=(r["id"], r["usuario_id"], r["titulo"], r["fecha_limite"],
                r["fecha_devolucion"] or "Pendiente", dias, f"{multa_mostrada:.2f}", r["estado"]))

    def mostrar_historial(self):
        self._cargar_historial(False)

    def mostrar_vencidos(self):
        self._cargar_historial(True)
        self.pestanas.select(self.tab_consultas)

    def _cargar_historial(self, solo_vencidos):
        self._limpiar(self.tabla_consultas)
        sql = """SELECT p.id,p.usuario_id,l.titulo,p.fecha_prestamo,p.fecha_limite,
                 COALESCE(p.fecha_devolucion,'Pendiente') AS devolucion,p.estado,p.multa
                 FROM prestamos p JOIN libros l ON l.codigo=p.libro_codigo"""
        if solo_vencidos:
            sql += " WHERE p.estado='Prestado' AND p.fecha_limite < ?"
            params = (date.today().isoformat(),)
        else:
            params = ()
        sql += " ORDER BY p.id DESC"
        for r in filas_consulta(sql, params):
            multa = r["multa"]
            if r["estado"] == "Prestado":
                dias = max(0, (date.today() - date.fromisoformat(r["fecha_limite"])).days)
                multa = dias * MULTA_DIARIA
            self.tabla_consultas.insert("", "end", values=(r["id"], r["usuario_id"], r["titulo"], r["fecha_prestamo"],
                r["fecha_limite"], r["devolucion"], r["estado"], f"{multa:.2f}"))

    def respaldar(self):
        try:
            ruta = crear_respaldo()
            carpeta_csv = exportar_respaldo_csv()
            messagebox.showinfo("Respaldo completado", f"Base de datos: {ruta or 'Aún no hay datos'}\\nExportación legible: {carpeta_csv}", parent=self)
        except (OSError, sqlite3.Error) as e:
            messagebox.showerror("Error de respaldo", str(e), parent=self)

    def exportar(self):
        try:
            carpeta = exportar_respaldo_csv()
            messagebox.showinfo("Exportación completada", f"Archivos CSV guardados en:\\n{carpeta}", parent=self)
        except (OSError, sqlite3.Error) as e:
            messagebox.showerror("Error de exportación", str(e), parent=self)


def main():
    inicializar_bd()
    try:
        app = BibliotecaApp()
        app.mainloop()
    except tk.TclError as e:
        print("No se pudo abrir la ventana gráfica.")
        print("En Linux, instale Tkinter con: sudo apt install python3-tk")
        print(f"Detalle: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
