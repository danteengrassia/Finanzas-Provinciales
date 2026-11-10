"""Adapta los datos de Entre Rios al consolidador web."""

from puente_provincial import build_hierarchical, write_bridge


if __name__ == "__main__":
    write_bridge("entre_rios", lambda source, _: build_hierarchical(source, "entre_rios", None))
