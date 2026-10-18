"""
Sistema de gestión de usuarios para biblioteca.

Funciones:
  - Registrar usuarios
  - Buscar usuarios (por id o por nombre/apellido)
  - Mostrar información de usuarios
  - Validar que el usuario exista antes de realizar un préstamo

Estructura:
  Usuario
   ├── id
   ├── nombre
   ├── apellido
   └── contacto
"""


import unicodedata


def _sin_acentos(texto):
    normal = unicodedata.normalize("NFD", str(texto))
    return "".join(c for c in normal if unicodedata.category(c) != "Mn").lower()


class UsuarioError(Exception):
    """Error propio del sistema de usuarios (datos inválidos, no encontrado, etc.)."""


class Usuario:
    def __init__(self, id_usuario, nombre, apellido, contacto):
        self.id = self._validar_id(id_usuario)
        self.nombre = self._validar_texto(nombre, "nombre")
        self.apellido = self._validar_texto(apellido, "apellido")
        self.contacto = self._validar_contacto(contacto)

    @staticmethod
    def _validar_id(valor):
        try:
            if isinstance(valor, bool):
                raise ValueError
            numero = int(str(valor).strip())
        except (ValueError, TypeError):
            raise UsuarioError("El id debe ser un número entero.")
        if numero <= 0:
            raise UsuarioError("El id debe ser un número positivo.")
        return numero

    @staticmethod
    def _validar_texto(valor, campo):
        if valor is None or not str(valor).strip():
            raise UsuarioError(f"El {campo} no puede estar vacío.")
        texto = " ".join(str(valor).split())
        if any(c.isdigit() for c in texto):
            raise UsuarioError(f"El {campo} no puede contener números.")
        return texto.title()

    @staticmethod
    def _validar_contacto(valor):
        if valor is None or not str(valor).strip():
            raise UsuarioError("El contacto no puede estar vacío.")
        return str(valor).strip()

    def nombre_completo(self):
        return f"{self.nombre} {self.apellido}"

    def __str__(self):
        return (
            f"ID: {self.id} | Nombre: {self.nombre_completo()} | "
            f"Contacto: {self.contacto}"
        )


class GestorUsuarios:
    def __init__(self):
        self._usuarios = {}  # id -> Usuario

    # ---------- Registrar ----------
    def registrar(self, id_usuario, nombre, apellido, contacto):
        usuario = Usuario(id_usuario, nombre, apellido, contacto)
        if usuario.id in self._usuarios:
            raise UsuarioError(f"Ya existe un usuario con el id {usuario.id}.")
        self._usuarios[usuario.id] = usuario
        return usuario

    # ---------- Buscar ----------
    def existe(self, id_usuario):
        try:
            return int(str(id_usuario).strip()) in self._usuarios
        except (ValueError, TypeError):
            return False

    def buscar_por_id(self, id_usuario):
        try:
            clave = int(str(id_usuario).strip())
        except (ValueError, TypeError):
            raise UsuarioError("El id debe ser un número entero.")
        usuario = self._usuarios.get(clave)
        if usuario is None:
            raise UsuarioError(f"No existe un usuario con el id {clave}.")
        return usuario

    def buscar_por_nombre(self, texto):
        if texto is None or not str(texto).strip():
            raise UsuarioError("Escribe un texto para buscar.")
        texto = _sin_acentos(str(texto).strip())
        return [
            u for u in self._usuarios.values()
            if texto in _sin_acentos(u.nombre) or texto in _sin_acentos(u.apellido)
        ]

    # ---------- Mostrar ----------
    def listar(self):
        return sorted(self._usuarios.values(), key=lambda u: u.id)

    def mostrar_todos(self):
        usuarios = self.listar()
        if not usuarios:
            print("No hay usuarios registrados.")
            return
        for u in usuarios:
            print(u)

    # ---------- Validar para préstamo ----------
    def validar_para_prestamo(self, id_usuario):
        """Lanza UsuarioError si el usuario no existe; devuelve el Usuario si existe."""
        return self.buscar_por_id(id_usuario)


class Prestamo:
    """Ejemplo mínimo de préstamo que depende de que el usuario exista."""

    def __init__(self, usuario, item):
        self.usuario = usuario
        self.item = item

    def __str__(self):
        return f"Préstamo de '{self.item}' a {self.usuario.nombre_completo()} (ID {self.usuario.id})"


def realizar_prestamo(gestor, id_usuario, item):
    if item is None or not str(item).strip():
        raise UsuarioError("Debes indicar qué se va a prestar.")
    usuario = gestor.validar_para_prestamo(id_usuario)  # valida existencia
    return Prestamo(usuario, str(item).strip())


# ---------------------- Menú interactivo ----------------------
def pedir(mensaje):
    return input(mensaje).strip()


def menu():
    gestor = GestorUsuarios()
    opciones = """
===== SISTEMA DE USUARIOS =====
1. Registrar usuario
2. Buscar usuario por ID
3. Buscar usuario por nombre/apellido
4. Mostrar todos los usuarios
5. Realizar préstamo
0. Salir
"""
    while True:
        try:
            print(opciones)
            opcion = pedir("Elige una opción: ")

            if opcion == "1":
                u = gestor.registrar(
                    pedir("ID: "), pedir("Nombre: "),
                    pedir("Apellido: "), pedir("Contacto: "),
                )
                print(f"Usuario registrado: {u}")

            elif opcion == "2":
                print(gestor.buscar_por_id(pedir("ID a buscar: ")))

            elif opcion == "3":
                resultados = gestor.buscar_por_nombre(pedir("Texto a buscar: "))
                if resultados:
                    for u in resultados:
                        print(u)
                else:
                    print("No se encontraron coincidencias.")

            elif opcion == "4":
                gestor.mostrar_todos()

            elif opcion == "5":
                p = realizar_prestamo(
                    gestor, pedir("ID del usuario: "), pedir("Libro/artículo: ")
                )
                print(f"Préstamo realizado -> {p}")

            elif opcion == "0":
                print("¡Hasta luego!")
                break

            else:
                print("Opción no válida, intenta de nuevo.")

        except UsuarioError as e:
            print(f"Error: {e}")
        except (KeyboardInterrupt, EOFError):
            print("\nSaliendo del programa...")
            break
        except Exception as e:  # red de seguridad final
            print(f"Ocurrió un error inesperado: {e}")


if __name__ == "__main__":
    menu()
