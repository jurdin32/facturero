"""El código de barras del RIDE: la clave de acceso en Code 128.

El SRI pide la clave también en barras, para poder leerla con un lector en vez de
teclearla. Se dibuja aquí, en SVG, desde el servidor: no hace falta ninguna
dependencia y al imprimir sale nítido, porque son barras y no una imagen.

Code 128 B es lo que usan los RIDE: cada carácter imprimible de ASCII es un
símbolo de seis anchos (barra, espacio, barra, espacio, barra, espacio) y al final
van la suma de control y el símbolo de parada.
"""

from __future__ import annotations

from typing import List, Tuple

__all__ = ["svg", "SIMBOLO_INICIO_B", "SIMBOLO_PARADA"]


#: Los anchos de cada símbolo, del 0 al 105. Cada dígito es el ancho de una barra
#: o de un espacio, alternando: empieza en barra.
PATRONES: Tuple[str, ...] = (
    "212222", "222122", "222221", "121223", "121322", "131222", "122213",
    "122312", "132212", "221213", "221312", "231212", "112232", "122132",
    "122231", "113222", "123122", "123221", "223211", "221132", "221231",
    "213212", "223112", "312131", "311222", "321122", "321221", "312212",
    "322112", "322211", "212123", "212321", "232121", "111323", "131123",
    "131321", "112313", "132113", "132311", "211313", "231113", "231311",
    "112133", "112331", "132131", "113123", "113321", "133121", "313121",
    "211331", "231131", "213113", "213311", "213131", "311123", "311321",
    "331121", "312113", "312311", "332111", "314111", "221411", "431111",
    "111224", "111422", "121124", "121421", "141122", "141221", "112214",
    "112412", "122114", "122411", "142112", "142211", "241211", "221114",
    "413111", "241112", "134111", "111242", "121142", "121241", "114212",
    "124112", "124211", "411212", "421112", "421211", "212141", "214121",
    "412121", "111143", "111341", "131141", "114113", "114311", "411113",
    "411311", "113141", "114131", "311141", "411131", "211412", "211214",
    "211232",
)

#: El inicio del juego B (letras y números) y la parada, que lleva siete anchos.
SIMBOLO_INICIO_B = 104
SIMBOLO_PARADA = "2331112"


def _simbolos(texto: str) -> List[int]:
    """Los símbolos del texto, con el inicio, la suma de control y la parada."""
    valores = [SIMBOLO_INICIO_B] + [ord(caracter) - 32 for caracter in texto]
    suma = valores[0] + sum(valor * posicion for posicion, valor in enumerate(valores[1:], start=1))
    valores.append(suma % 103)
    return valores


def _barras(texto: str) -> Tuple[List[Tuple[int, int]], int]:
    """Las barras del texto como ``(x, ancho)``, y el ancho total."""
    barras: List[Tuple[int, int]] = []
    x = 0
    for valor in _simbolos(texto):
        for indice, ancho in enumerate(PATRONES[valor]):
            ancho = int(ancho)
            if indice % 2 == 0:  # los pares son barra; los impares, espacio
                barras.append((x, ancho))
            x += ancho
    for indice, ancho in enumerate(SIMBOLO_PARADA):
        ancho = int(ancho)
        if indice % 2 == 0:
            barras.append((x, ancho))
        x += ancho
    return barras, x


def svg(texto: str, alto: int = 46, clase: str = "ride-barras") -> str:
    """El código de barras del texto, en SVG, o vacío si no hay texto.

    Las barras se estiran a lo ancho de su caja: el alto es fijo y el ancho lo pone
    la hoja, así el mismo dibujo sirve en A4 y en el tíquet.
    """
    texto = (texto or "").strip()
    if not texto or any(not (32 <= ord(caracter) <= 126) for caracter in texto):
        return ""
    barras, ancho_total = _barras(texto)
    trazos = "".join(
        f'<rect x="{x}" y="0" width="{ancho}" height="{alto}"/>' for x, ancho in barras
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" class="{clase}" role="img" '
        f'aria-label="Código de barras de la clave de acceso" '
        f'viewBox="0 0 {ancho_total} {alto}" preserveAspectRatio="none" '
        f'shape-rendering="crispEdges">{trazos}</svg>'
    )
