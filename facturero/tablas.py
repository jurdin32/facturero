"""Las tablas de las listas: búsqueda, orden y paginación, en el servidor.

Las listas de la aplicación se comportan todas igual: una barra con el buscador y
cuántas filas por página, la tabla con las columnas que se pueden ordenar (se pulsa
en la cabecera y se ordena), y abajo el «mostrando de X a Y de Z» con los botones de
página. Como todo va por la barra de direcciones, el buscador y la paginación
funcionan sin JavaScript y el enlace de una página se puede copiar y mandar.

Se usa igual en todas las listas: se le da el ``queryset`` y las columnas, y la
plantilla pinta ``tabla.columnas`` y ``tabla.filas`` con las ayudas de abajo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlencode

from django.core.paginator import EmptyPage, Paginator
from django.db.models import Q

__all__ = ["Columna", "Tabla", "POR_PAGINA", "TAMANOS"]

#: Cuántas filas por página de serie, y los tamaños que se pueden elegir.
POR_PAGINA = 25
TAMANOS = (10, 25, 50, 100)

#: Cuántos números de página se enseñan a cada lado del actual.
AL_LADO = 2


@dataclass(frozen=True)
class Columna:
    """Una columna del encabezado.

    ``campo`` es por lo que se ordena (el campo del modelo o el nombre de un
    ``annotate``); sin él, la columna no se ordena y no lleva enlace.
    """

    titulo: str
    campo: Optional[str] = None
    clase: str = ""
    oculta: bool = False


class Tabla:
    """Los datos de una lista: buscados, ordenados y partidos en páginas."""

    def __init__(
        self,
        request: Any,
        queryset: Any,
        columnas: Sequence[Columna],
        *,
        buscar_en: Sequence[str] = (),
        orden_por_omision: Optional[str] = None,
        por_pagina: int = POR_PAGINA,
        parametro_pagina: str = "pagina",
    ) -> None:
        self.request = request
        self.q = (request.GET.get("q") or "").strip()
        self.por_pagina = self._tamano_pedido(request, por_pagina)
        self.orden, self.direccion = self._orden_pedido(request, columnas, orden_por_omision)
        self.columnas: List[Dict[str, Any]] = [
            {
                "titulo": columna.titulo,
                "campo": columna.campo,
                "clase": columna.clase,
                "oculta": columna.oculta,
                "enlace": self._enlace_orden(columna) if columna.campo else "",
                "sentido": self._sentido_de(columna),
            }
            for columna in columnas
        ]

        datos = self._buscar(queryset, buscar_en)
        if self.orden:
            signo = "-" if self.direccion == "desc" else ""
            datos = datos.order_by(f"{signo}{self.orden}")

        paginador = Paginator(datos, self.por_pagina)
        self.numero = self._numero_pedido(request, parametro_pagina)
        try:
            self.filas = paginador.page(self.numero)
        except EmptyPage:
            # Una página que ya no existe (porque al buscar quedan menos) devuelve la
            # última, en vez de un error.
            self.numero = paginador.num_pages
            self.filas = paginador.page(self.numero)
        self.total = paginador.count
        self.paginas = self._paginas()

    # -------------------------------------------------------------- lo de fuera

    @property
    def tamanos(self) -> Sequence[int]:
        """Los tamaños de página que se pueden elegir."""
        return TAMANOS

    @property
    def hay_filtros(self) -> bool:
        """¿Se está buscando algo? (para el «limpiar» y el mensaje del vacío)"""
        return bool(self.q)

    @property
    def desde(self) -> int:
        """El número de la primera fila que se está viendo (1 si no hay ninguna)."""
        return self.filas.start_index() if self.total else 0

    @property
    def hasta(self) -> int:
        """El número de la última fila que se está viendo."""
        return self.filas.end_index()

    @property
    def enlace_limpio(self) -> str:
        """Volver a la lista sin nada buscado ni ordenado."""
        return self._enlace()

    @property
    def enlace_anterior(self) -> str:
        return self._enlace(pagina=self.numero - 1) if self.filas.has_previous() else ""

    @property
    def enlace_siguiente(self) -> str:
        return self._enlace(pagina=self.numero + 1) if self.filas.has_next() else ""

    # -------------------------------------------------------------- por dentro

    def _tamano_pedido(self, request: Any, por_pagina: int) -> int:
        pedido = request.GET.get("por_pagina")
        if pedido and pedido.isdigit() and int(pedido) in TAMANOS:
            return int(pedido)
        return por_pagina

    def _orden_pedido(
        self, request: Any, columnas: Sequence[Columna], por_omision: Optional[str]
    ) -> Tuple[str, str]:
        ordenables = {columna.campo for columna in columnas if columna.campo}
        pedido = request.GET.get("orden")
        if pedido is None or pedido not in ordenables:
            return (por_omision, "asc") if por_omision else ("", "")
        direccion = "desc" if request.GET.get("dir") == "desc" else "asc"
        return pedido, direccion

    def _buscar(self, queryset: Any, buscar_en: Sequence[str]) -> Any:
        if not self.q or not buscar_en:
            return queryset
        condiciones = Q()
        for campo in buscar_en:
            condiciones |= Q(**{f"{campo}__icontains": self.q})
        return queryset.filter(condiciones).distinct()

    def _sentido_de(self, columna: Columna) -> str:
        """``"asc"``/``"desc"`` si la tabla está ordenada por esa columna."""
        return self.direccion if columna.campo and columna.campo == self.orden else ""

    def _enlace_orden(self, columna: Columna) -> str:
        """El enlace de la cabecera: ordena al revés si ya está ordenada así."""
        if columna.campo == self.orden:
            direccion = "desc" if self.direccion == "asc" else "asc"
        else:
            direccion = "asc"
        return self._enlace(orden=columna.campo, direccion=direccion)

    def _numero_pedido(self, request: Any, parametro: str) -> int:
        pedido = request.GET.get(parametro)
        return int(pedido) if pedido and pedido.isdigit() and int(pedido) > 0 else 1

    def _enlace(
        self,
        *,
        orden: Optional[str] = None,
        direccion: Optional[str] = None,
        pagina: Optional[int] = None,
        por_pagina: Optional[int] = None,
    ) -> str:
        """La misma dirección, cambiando solo lo que se pida (lo demás se mantiene)."""
        parametros: Dict[str, Any] = {}
        if self.q:
            parametros["q"] = self.q
        orden = self.orden if orden is None else orden
        direccion = self.direccion if direccion is None else direccion
        if orden:
            parametros["orden"] = orden
            parametros["dir"] = direccion or "asc"
        if por_pagina or self.por_pagina != POR_PAGINA:
            parametros["por_pagina"] = por_pagina or self.por_pagina
        if pagina and pagina > 1:
            parametros["pagina"] = pagina

        codificado = urlencode(parametros)
        return f"?{codificado}" if codificado else "?"

    def _paginas(self) -> List[Optional[Dict[str, Any]]]:
        """Los números de página que se enseñan, con puntos suspensivos (``None``)."""
        total = self.filas.paginator.num_pages
        if total <= 1:
            return []

        numeros: List[Optional[int]] = [1]
        principio = max(2, self.numero - AL_LADO)
        final = min(total - 1, self.numero + AL_LADO)
        if principio > 2:
            numeros.append(None)
        numeros += list(range(principio, final + 1))
        if final < total - 1:
            numeros.append(None)
        numeros.append(total)

        return [
            None
            if numero is None
            else {"numero": numero, "activa": numero == self.numero, "enlace": self._enlace(pagina=numero)}
            for numero in numeros
        ]
