"""El carrito de la tienda: lo que se va a pedir, guardado en la sesión.

No es una tabla: quien entra sin cuenta no tiene dónde guardar un carrito, así que
vive en su sesión hasta que confirma el pedido. Cuando confirma se copia a
:class:`tienda.models.LineaPedido`, con los precios de ese momento, y el carrito se
vacía.

Solo se enseña lo que está publicado y se puede pedir; si un producto se despublica
o se agota mientras el carrito está abierto, la línea se cae sola al leerlo.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional

from django.http import HttpRequest
from factec.modelos import cuantizar

from .models import ProductoTienda

__all__ = ["Carrito", "LineaDelCarrito", "CLAVE_DE_LA_SESION"]

#: Dónde queda el carrito dentro de la sesión.
CLAVE_DE_LA_SESION = "carrito_tienda"

#: Lo máximo de una misma cosa que se puede pedir de una vez.
MAXIMO_POR_LINEA = Decimal("999")


@dataclass
class LineaDelCarrito:
    """Una línea del carrito, ya con su producto y sus importes."""

    producto: ProductoTienda
    cantidad: Decimal

    @property
    def subtotal(self) -> Decimal:
        """Sin impuestos, como se guarda en la ficha."""
        return cuantizar(self.cantidad * self.producto.precio_sin_iva)

    @property
    def total(self) -> Decimal:
        """Con IVA, que es lo que paga el cliente."""
        return cuantizar(self.cantidad * self.producto.precio)


class Carrito:
    """Lo que lleva quien está comprando.

    Se construye con la petición porque el carrito vive en la sesión. Cada cambio se
    guarda en el acto: no hay que acordarse de llamar a nada.
    """

    def __init__(self, request: HttpRequest) -> None:
        self._sesion = request.session
        self._cantidades = self._leer()

    def _leer(self) -> Dict[int, Decimal]:
        guardado = self._sesion.get(CLAVE_DE_LA_SESION) or {}
        cantidades: Dict[int, Decimal] = {}
        for clave, valor in guardado.items():
            try:
                cantidad = Decimal(str(valor))
            except (InvalidOperation, TypeError, ValueError):
                continue
            if cantidad > 0:
                cantidades[int(clave)] = cantidad
        return cantidades

    def _guardar(self) -> None:
        # La cantidad se guarda sin ceros de más: «3» y no «3.000».
        self._sesion[CLAVE_DE_LA_SESION] = {
            str(producto): format(cantidad.normalize(), "f")
            for producto, cantidad in self._cantidades.items()
        }
        self._sesion.modified = True

    # -------------------------------------------------------------- lo que lleva

    @property
    def vacio(self) -> bool:
        return not self._cantidades

    @property
    def unidades(self) -> Decimal:
        """Cuántas cosas van en total, para el contador de la cabecera."""
        return sum(self._cantidades.values(), Decimal("0"))

    def cantidad_de(self, producto: ProductoTienda) -> Decimal:
        return self._cantidades.get(producto.pk, Decimal("0"))

    def lineas(self) -> List[LineaDelCarrito]:
        """Las líneas con su producto, en el orden en que se fueron agregando.

        Lo que ya no se puede vender —despublicado, retirado o sin stock— se quita
        del carrito: no se puede pedir lo que la tienda ya no ofrece.
        """
        if not self._cantidades:
            return []
        productos = (
            ProductoTienda.objects.publicadas()
            .filter(pk__in=self._cantidades)
            .prefetch_related("imagenes")
        )
        disponibles = {producto.pk: producto for producto in productos}
        lineas: List[LineaDelCarrito] = []
        cambiado = False
        for producto_id, cantidad in list(self._cantidades.items()):
            producto = disponibles.get(producto_id)
            if producto is None or not producto.con_stock:
                del self._cantidades[producto_id]
                cambiado = True
                continue
            lineas.append(LineaDelCarrito(producto=producto, cantidad=cantidad))
        if cambiado:
            self._guardar()
        return lineas

    # ------------------------------------------------------------------ cambios

    def agregar(self, producto: ProductoTienda, cantidad: Decimal = Decimal("1")) -> None:
        """Suma al carrito; si ya estaba, se acumula."""
        cantidad = self._limpiar(cantidad)
        if cantidad <= 0:
            return
        total = self._cantidades.get(producto.pk, Decimal("0")) + cantidad
        self._cantidades[producto.pk] = min(total, MAXIMO_POR_LINEA)
        self._guardar()

    def fijar(self, producto: ProductoTienda, cantidad: Decimal) -> None:
        """Deja la cantidad escrita; con cero o menos, quita la línea."""
        cantidad = self._limpiar(cantidad)
        if cantidad <= 0:
            self.quitar(producto.pk)
            return
        self._cantidades[producto.pk] = min(cantidad, MAXIMO_POR_LINEA)
        self._guardar()

    def quitar(self, producto: int) -> None:
        if self._cantidades.pop(int(producto), None) is not None:
            self._guardar()

    def vaciar(self) -> None:
        self._cantidades = {}
        self._guardar()

    # ---------------------------------------------------------------- los totales

    @property
    def subtotal(self) -> Decimal:
        return cuantizar(sum((linea.subtotal for linea in self.lineas()), Decimal("0")))

    @property
    def iva(self) -> Decimal:
        return cuantizar(
            sum((linea.total - linea.subtotal for linea in self.lineas()), Decimal("0"))
        )

    @property
    def total(self) -> Decimal:
        return cuantizar(sum((linea.total for linea in self.lineas()), Decimal("0")))

    @staticmethod
    def _limpiar(cantidad: Optional[Decimal]) -> Decimal:
        """Una cantidad que se pueda usar: sin negativos y con tres decimales."""
        if cantidad is None:
            return Decimal("0")
        try:
            return cuantizar(Decimal(cantidad), 3)
        except (InvalidOperation, TypeError, ValueError):
            return Decimal("0")
