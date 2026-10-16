class Autor:
    def __init__(self, id_autor, nombre, apellido):
        self.id_autor = id_autor
        self.nombre = nombre
        self.apellido = apellido

    def mostrar_nombre(self):
        return self.nombre + " " + self.apellido

class Libro:
    def __init__(self, codigo, titulo, autor, categoria,
                 cantidad_disponible):
        self.codigo = codigo
        self.titulo = titulo
        self.autor = autor
        self.categoria = categoria
        self.cantidadDisponible = cantidad_disponible 

    def mostrar_informacion(self):
        print("Codigo:", self.codigo)
        print("Titulo:", self.titulo)
        print("Autor:", self.autor.mostrar_nombre())
        print("Categoria:", self.categoria)
        print("Disponibles:", self.cantidadDisponible)

# Listas para guardar los registros
autores = []
libros = []

def registrar_autor(id_autor, nombre, apellido):
    for autor in autores:
        if autor.id_autor == id_autor:
            print("Error: ese autor ya esta registrado.")
            return False

    autor = Autor(id_autor, nombre, apellido)
    autores.append(autor)
    print("Autor registrado correctamente.")
    return True

def registrar_libro(codigo, titulo, id_autor,
                    categoria, cantidad):
    if cantidad < 0:
        print("Error: la cantidad no puede ser negativa.")
        return False

    for libro in libros:
        if libro.codigo == codigo:
            print("Error: ese codigo ya existe.")
            return False

    autor_encontrado = None

    for autor in autores:
        if autor.id_autor == id_autor:
            autor_encontrado = autor
            break

    if autor_encontrado is None:
        print("Error: primero debes registrar al autor.")
        return False

    libro = Libro(
        codigo, titulo, autor_encontrado,
        categoria, cantidad
    )
    libros.append(libro)
    print("Libro registrado correctamente.")
    return True

def buscar_libro(codigo):
    for libro in libros:
        if libro.codigo == codigo:
            return libro

    return None

def consultar_libros_disponibles():
    encontrados = 0

    for libro in libros:
        if libro.cantidadDisponible > 0:
            libro.mostrar_informacion()
            print("--------------------")
            encontrados += 1

    if encontrados == 0:
        print("No hay libros disponibles.")


        