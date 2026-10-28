"""Las cuentas de la tienda: del carrito al pedido y del pedido a la factura.

La tienda no emite nada por su cuenta: deja el pedido con lo que se compró y con los
precios de ese momento. La factura sale después, desde la aplicación, revisando lo
que se va a emitir.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from django.core.exceptions import ValidationError
from django.db import transaction
from factec.catalogos import PORCENTAJE_IVA
from factec.django.documentos import (
    IVA_POR_OMISION,
    Cliente,
    Factura,
    FacturaDetalle,
)

from .models import LineaPedido, Pedido

__all__ = ["cliente_para", "crear_pedido", "factura_del_pedido"]


def cliente_para(datos: dict) -> Cliente:
    """El cliente al que se le factura: se busca por la identificación o se crea.

    Sin identificación se usa el consumidor final, que es lo que el SRI permite a
    quien no quiere dar sus datos; todas esas compras caen en la misma ficha.

    Dos compras a la vez del mismo cliente nuevo no pueden dejar dos fichas: la
    creación va con ``get_or_create``, que aguanta la carrera.
    """
    identificacion = (datos.get("identificacion") or "").strip()
    nombre = (datos.get("nombre") or "").strip() or "Consumidor Final"
    if not identificacion:
        cliente, _ = Cliente.objects.get_or_create(
            identificacion=Cliente.CONSUMIDOR_FINAL,
            defaults={
                "razon_social": "CONSUMIDOR FINAL",
                "tipo_identificacion": "07",
            },
        )
        return cliente

    try:
        cliente, creado = Cliente.objects.get_or_create(
            identificacion=identificacion,
            defaults={
                "razon_social": nombre,
                "tipo_identificacion": "04" if len(identificacion) == 13 else "05",
                "direccion": datos.get("direccion") or "",
                "email": datos.get("email") or "",
                "telefono": datos.get("telefono") or "",
            },
        )
    except Cliente.MultipleObjectsReturned:
        # El catálogo de antes puede tener la misma identificación dos veces.
        cliente = Cliente.objects.filter(identificacion=identificacion).order_by("pk").first()
        creado = False
    if creado:
        return cliente

    # Al que ya estaba se le completan los datos que falten, sin pisarle los suyos.
    cambios = []
    for campo in ("direccion", "email", "telefono"):
        if not getattr(cliente, campo) and datos.get(campo):
            setattr(cliente, campo, datos[campo])
            cambios.append(campo)
    if cambios:
        cambios.append("actualizado")
        cliente.save(update_fields=cambios)
    return cliente


def crear_pedido(carrito: Any, datos: dict) -> Pedido:
    """Copia el carrito a un pedido con los precios de ahora y lo deja vacío.

    El pedido guarda una copia de la descripción, el precio y el IVA de cada línea:
    lo que se cobró no cambia porque mañana cambie la ficha. No reserva stock: el
    inventario se mueve cuando la factura se emite, como siempre.

    Todo va en una transacción: un pedido a medias —sin sus líneas o sin totales—
    no puede quedarse en la base.
    """
    lineas = carrito.lineas()
    if not lineas:
        raise ValidationError("El carrito está vacío.")
    if any(not linea.producto.publicado_en_la_web for linea in lineas):
        raise ValidationError("Algún producto del carrito ya no está a la venta.")

    with transaction.atomic():
        pedido = Pedido.objects.create(
            nombre=datos.get("nombre") or "Consumidor Final",
            identificacion=datos.get("identificacion") or "",
            email=datos.get("email") or "",
            telefono=datos.get("telefono") or "",
            direccion=datos.get("direccion") or "",
            nota=datos.get("nota") or "",
            cliente=cliente_para(datos),
        )
        for linea in lineas:
            producto = linea.producto
            LineaPedido.objects.create(
                pedido=pedido,
                producto=producto,
                codigo=producto.codigo_principal,
                descripcion=producto.nombre,
                cantidad=linea.cantidad,
                precio_unitario=producto.precio_sin_iva,
                tarifa_iva=producto.tarifa_iva,
            )
        pedido.calcular_totales()
        pedido.save(update_fields=["subtotal", "iva", "total"])
    carrito.vaciar()
    return pedido


def factura_del_pedido(pedido: Pedido) -> Factura:
    """Arma la factura en borrador para revisarla y emitirla desde la aplicación.

    No emite: deja la factura con el cliente y las líneas del pedido, lista para
    abrirla en la pantalla de facturar. Si el pedido ya tenía factura, la devuelve.
    """
    if pedido.factura_id:
        return pedido.factura
    if pedido.anulado:
        raise ValidationError("Un pedido anulado no se factura.")

    cliente = pedido.cliente or cliente_para(
        {
            "nombre": pedido.nombre,
            "identificacion": pedido.identificacion,
            "direccion": pedido.direccion,
            "email": pedido.email,
            "telefono": pedido.telefono,
        }
    )
    factura = Factura.objects.create(
        receptor=cliente,
        observaciones=f"Pedido {pedido.numero} de la tienda",
    )
    for linea in pedido.lineas.select_related("producto"):
        producto = linea.producto
        FacturaDetalle.objects.create(
            factura=factura,
            producto=producto,
            descripcion=linea.descripcion,
            cantidad=linea.cantidad,
            precio_unitario=linea.precio_unitario,
            codigo_principal=linea.codigo,
            unidad_medida=producto.unidad_medida if producto else "UNIDAD",
            codigo_porcentaje_iva=(
                producto.codigo_porcentaje_iva
                if producto
                else _codigo_del_iva(linea.tarifa_iva)
            ),
        )
    pedido.factura = factura
    pedido.save(update_fields=["factura"])
    return factura


def _codigo_del_iva(porcentaje: Optional[Decimal]) -> str:
    """El código del SRI para una tarifa, para cuando el producto ya no existe."""
    if porcentaje is not None:
        for codigo, valor in PORCENTAJE_IVA.items():
            if valor == porcentaje:
                return codigo
    return IVA_POR_OMISION
