from datetime import date, timedelta


class Prestamo:
    def __init__(self, usuario, libro, dias_prestamo=7):
        self.usuario = usuario
        self.libro = libro
        self.fecha_prestamo = date.today()
        self.fecha_limite = date.today() + timedelta(days=dias_prestamo)
        self.fecha_devolucion = None
        self.estado = "activo"

    def devolver(self):
        self.fecha_devolucion = date.today()
        self.estado = "devuelto"

    def __str__(self):
        return (f"Préstamo → Usuario: {self.usuario} | Libro: {self.libro} | "
                f"Fecha: {self.fecha_prestamo} | Límite: {self.fecha_limite} | "
                f"Devolución: {self.fecha_devolucion} | Estado: {self.estado}")


prestamos_registrados = []


def registrar_prestamo(usuario, libro, usuarios, libros):
    if usuario not in usuarios:
        print("❌ El usuario no existe.")
        return None

    if libro not in libros:
        print("❌ El libro no existe.")
        return None

    if libros[libro]["disponibles"] <= 0:
        print("❌ No hay ejemplares disponibles.")
        return None

    libros[libro]["disponibles"] -= 1

    nuevo = Prestamo(usuario, libro)
    prestamos_registrados.append(nuevo)

    print(f"✅ Préstamo registrado para {usuario} con el libro '{libro}'.")
    print(f"   Fecha límite: {nuevo.fecha_limite}")
    return nuevo


def devolver_prestamo(usuario, libro, libros):
    for p in prestamos_registrados:
        if p.usuario == usuario and p.libro == libro and p.estado == "activo":
            p.devolver()
            libros[libro]["disponibles"] += 1
            print(f"✅ Devolución registrada: {usuario} devolvió '{libro}'.")
            return p
    print("❌ No se encontró un préstamo activo con esos datos.")
    return None


def mostrar_prestamos():
    if not prestamos_registrados:
        print("No hay préstamos registrados.")
        return
    for p in prestamos_registrados:
        print(p)


if __name__ == "__main__":
    usuarios = ["Dani", "Anderson", "Jeremy"]
    libros = { "Full Software": {"disponibles": 2},
        "Full Hardware": {"disponibles": 1},}

    registrar_prestamo("Dani", "Full Software", usuarios, libros)
    registrar_prestamo("Anderson", "Full Software", usuarios, libros)
    mostrar_prestamos()
    devolver_prestamo("Dani", "Full Software", libros)
    mostrar_prestamos()
