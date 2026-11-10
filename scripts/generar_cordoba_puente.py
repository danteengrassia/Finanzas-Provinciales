"""Adapta los datos de Cordoba al consolidador web."""

from puente_provincial import build_hierarchical, write_bridge


if __name__ == "__main__":
    write_bridge("cordoba", lambda source, path: build_hierarchical(
        source, "cordoba", path.with_name("deuda_tesoro_flotante.csv"),
    ))
