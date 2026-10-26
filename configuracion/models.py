"""La marca del emisor: el logo que sale en el RIDE.

El paquete factec se queda con los datos fiscales del emisor —RUC, razón social,
serie, certificado—. La imagen no es un dato fiscal: es la marca de la casa, así
que vive aquí, colgada de la configuración a la que pertenece.
"""

from __future__ import annotations

from typing import Any, Optional

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models

__all__ = ["LogoEmisor", "EXTENSIONES_LOGO", "TAMANO_MAXIMO_LOGO"]

#: Lo que se acepta subir. El SVG se imprime nítido y el PNG con transparencia
#: queda bien sobre el papel blanco del RIDE.
EXTENSIONES_LOGO = ("png", "jpg", "jpeg", "svg", "webp")

#: 2 MB: un logo de impresión cabe de sobra y no hincha la copia de seguridad.
TAMANO_MAXIMO_LOGO = 2 * 1024 * 1024


def validar_tamano(archivo: Any) -> None:
    """Un logo de más de dos megas no es un logo: es una foto sin recortar."""
    if archivo and getattr(archivo, "size", 0) > TAMANO_MAXIMO_LOGO:
        raise ValidationError("El logo no puede pasar de 2 MB. Redúzcalo un poco.")


class LogoEmisor(models.Model):
    """El logo de una configuración del emisor.

    Va uno a uno con la configuración: la de pruebas y la de producción pueden
    llevar el mismo, pero cada una guarda el suyo.
    """

    emisor = models.OneToOneField(
        "sri_fe.ConfiguracionEmisor",
        on_delete=models.CASCADE,
        related_name="logo_emisor",
        verbose_name="Emisor",
    )
    imagen = models.FileField(
        "Logo",
        upload_to="logos/",
        validators=[
            FileExtensionValidator(EXTENSIONES_LOGO, "El logo tiene que ser PNG, JPG, SVG o WEBP."),
            validar_tamano,
        ],
        help_text="PNG, JPG, SVG o WEBP, hasta 2 MB. Sale en el RIDE y en la factura impresa.",
    )
    actualizado = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "logo del emisor"
        verbose_name_plural = "logos del emisor"

    def __str__(self) -> str:
        return f"Logo de {self.emisor.razon_social or self.emisor.ruc}"

    @classmethod
    def de(cls, emisor: Optional[Any]) -> Optional["LogoEmisor"]:
        """El logo de esa configuración, si ya subió uno."""
        if emisor is None or not getattr(emisor, "pk", None):
            return None
        return cls.objects.filter(emisor_id=emisor.pk).first()

    @property
    def url(self) -> str:
        """La dirección del archivo, o vacío si no hay ninguno."""
        try:
            return self.imagen.url
        except ValueError:
            return ""
