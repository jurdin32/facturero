#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Consulta de RUC en el SRI — 100% gratuita y SIN autenticación.

No usa Selenium ni Chrome. Llama directamente al webservice REST que consume la
página del SRI y devuelve JSON:

    GET https://srienlinea.sri.gob.ec/sri-catastro-sujeto-servicio-internet/
        rest/ConsultaRuc/obtenerPorNumerosRuc?ruc=<RUC>

Respuesta:
    {"contribuyentes": [{"numeroRuc": "...", "razonSocial": "...", ...}],
     "encuesta": {...}}

IMPORTANTE: el SRI bloquea clientes que no envían un User-Agent de navegador
(con `curl` por defecto la petición se queda colgada sin responder). Por eso el
script envía uno.

Uso:
    python sri_consultas.py 0703886697001
    python sri_consultas.py 0703886697001 --json
    python sri_consultas.py 0703886697001 --crudo
    python sri_consultas.py 0703886697001 --timeout 30

También es importable: devuelve un objeto ``ResultadoConsulta``, con acceso por
atributo y por clave, y convertible a diccionario/JSON con ``to_dict()``:

    from sri_consultas import consultar_ruc_sri

    resultado = consultar_ruc_sri("0703886697001")
    print(resultado.encontrado)   # True
    print(resultado["datos"])     # {"Razón social": ..., ...}
    print(resultado.to_dict())    # dict listo para json.dumps()
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
import time
from collections.abc import Iterator, Mapping
from typing import Any, Dict, List, Optional

import requests

_BASE = "https://srienlinea.sri.gob.ec/sri-catastro-sujeto-servicio-internet/rest"
URL_CONSULTA = _BASE + "/ConsultaRuc/obtenerPorNumerosRuc"
URL_CONSULTA_ALT = _BASE + "/ConsolidadoContribuyente/obtenerPorNumerosRuc"
URL_EXISTE = _BASE + "/ConsolidadoContribuyente/existePorNumeroRuc"

_REFERER = (
    "https://srienlinea.sri.gob.ec/sri-en-linea/SriRucWeb/ConsultaRuc/"
    "Consultas/consultaRuc"
)

_CABECERAS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-EC,es;q=0.9",
    "Referer": _REFERER,
}

# (clave del JSON del SRI, etiqueta legible)
_ETIQUETAS = (
    ("numeroRuc", "Número RUC"),
    ("razonSocial", "Razón social"),
    ("estadoContribuyenteRuc", "Estado del contribuyente"),
    ("tipoContribuyente", "Tipo de contribuyente"),
    ("regimen", "Régimen"),
    ("categoria", "Categoría"),
    ("obligadoLlevarContabilidad", "Obligado a llevar contabilidad"),
    ("agenteRetencion", "Agente de retención"),
    ("contribuyenteEspecial", "Contribuyente especial"),
    ("contribuyenteFantasma", "Contribuyente fantasma"),
    ("transaccionesInexistente", "Transacciones inexistentes"),
    ("motivoCancelacionSuspension", "Motivo cancelación/suspensión"),
    ("actividadEconomicaPrincipal", "Actividad económica principal"),
)

_FECHAS = (
    ("fechaInicioActividades", "Fecha de inicio de actividades"),
    ("fechaCese", "Fecha de cese"),
    ("fechaReinicioActividades", "Fecha de reinicio de actividades"),
    ("fechaActualizacion", "Fecha de actualización"),
)


def _a_json(valor: Any) -> Any:
    """Vuelve serializable con json.dumps() cualquier objeto de este módulo."""
    if isinstance(valor, Contribuyente):
        return valor.to_dict()
    if isinstance(valor, list):
        return [_a_json(elemento) for elemento in valor]
    if isinstance(valor, dict):
        return {clave: _a_json(elemento) for clave, elemento in valor.items()}
    return valor


@dataclasses.dataclass
class Contribuyente(Mapping[str, Any]):
    """Contribuyente del SRI.

    Se comporta como un diccionario (``c["razonSocial"]``, ``c.get(...)``) y
    expone además sus claves como atributos (``c.razonSocial``). ``to_dict()``
    devuelve el JSON original del SRI.
    """

    _datos: Dict[str, Any] = dataclasses.field(default_factory=dict, repr=False)

    @classmethod
    def desde_dict(cls, datos: Dict[str, Any]) -> "Contribuyente":
        """Construye un Contribuyente desde un diccionario (object_hook de json)."""
        return cls(datos)

    def __getitem__(self, clave: str) -> Any:
        return self._datos[clave]

    def __iter__(self) -> Iterator[str]:
        return iter(self._datos)

    def __len__(self) -> int:
        return len(self._datos)

    def __getattr__(self, nombre: str) -> Any:
        try:
            datos = object.__getattribute__(self, "_datos")
        except AttributeError:
            raise AttributeError(nombre) from None
        try:
            return datos[nombre]
        except KeyError:
            raise AttributeError(nombre) from None

    def to_dict(self) -> Dict[str, Any]:
        """Devuelve el contribuyente como diccionario (JSON original del SRI)."""
        return dict(self._datos)


def _objeto(pares: Dict[str, Any]) -> Any:
    """``object_hook`` de ``json.loads``: convierte cada contribuyente en objeto."""
    return Contribuyente.desde_dict(pares) if "numeroRuc" in pares else pares


@dataclasses.dataclass
class ResultadoConsulta(Mapping[str, Any]):
    """Resultado de consultar un RUC.

    Acceso por atributo (``resultado.datos``) y por clave
    (``resultado["datos"]``). ``to_dict()`` lo vuelve un diccionario listo para
    ``json.dumps()``.
    """

    ruc: str
    encontrado: bool
    datos: Dict[str, str] = dataclasses.field(default_factory=dict)
    crudo: Any = None

    _CAMPOS = ("ruc", "encontrado", "datos", "crudo")

    def __getitem__(self, clave: str) -> Any:
        if clave not in self._CAMPOS:
            raise KeyError(clave)
        return getattr(self, clave)

    def __iter__(self) -> Iterator[str]:
        return iter(self._CAMPOS)

    def __len__(self) -> int:
        return len(self._CAMPOS)

    def to_dict(self) -> Dict[str, Any]:
        """Devuelve el resultado como diccionario serializable con json.dumps()."""
        return {
            "ruc": self.ruc,
            "encontrado": self.encontrado,
            "datos": dict(self.datos),
            "crudo": _a_json(self.crudo),
        }


def normalizar_ruc(ruc: str) -> str:
    """Deja solo los dígitos del RUC."""
    return re.sub(r"\D", "", ruc or "")


def validar_ruc(ruc: str) -> bool:
    """Validación básica: 13 dígitos terminados en 001."""
    return bool(re.fullmatch(r"\d{13}", ruc)) and ruc.endswith("001")


def _limpiar_fecha(valor: Any) -> str:
    """'2015-04-15 00:00:00.0' -> '2015-04-15'."""
    if not valor:
        return ""
    texto = str(valor)
    return texto.split(" ")[0] if " " in texto else texto


def _normalizar(contribuyente: Mapping[str, Any]) -> Dict[str, str]:
    """Aplana el JSON del SRI a un diccionario de etiquetas legibles."""
    datos: Dict[str, str] = {}
    for clave, etiqueta in _ETIQUETAS:
        valor = contribuyente.get(clave)
        if valor is not None and valor != "":
            datos[etiqueta] = str(valor)
    fechas = contribuyente.get("informacionFechasContribuyente") or {}
    for clave, etiqueta in _FECHAS:
        valor = _limpiar_fecha(fechas.get(clave))
        if valor:
            datos[etiqueta] = valor
    return datos


def _sesion() -> requests.Session:
    sesion = requests.Session()
    sesion.headers.update(_CABECERAS)
    return sesion


def _pedir(sesion: requests.Session, url: str, params: Dict[str, str], timeout: float) -> Any:
    respuesta = sesion.get(url, params=params, timeout=timeout)
    respuesta.raise_for_status()
    try:
        return respuesta.json(object_hook=_objeto)
    except ValueError:
        return None


def existe_ruc(ruc: str, timeout: float = 20.0) -> bool:
    """Comprobación rápida (True/False) mediante el webservice del SRI."""
    ruc = normalizar_ruc(ruc)
    if not validar_ruc(ruc):
        return False
    respuesta = _sesion().get(URL_EXISTE, params={"numeroRuc": ruc}, timeout=timeout)
    respuesta.raise_for_status()
    return respuesta.text.strip().lower() == "true"


def consultar_ruc_sri(ruc: str, timeout: float = 20.0) -> ResultadoConsulta:
    """Consulta un RUC en el SRI (sin autenticación).

    Devuelve un ``ResultadoConsulta`` con ``ruc``, ``encontrado``, ``datos``
    (diccionario de etiquetas legibles) y ``crudo`` (el ``Contribuyente`` con el
    JSON original del SRI).

    El SRI corta la conexión cuando recibe muchas consultas seguidas. Se intenta
    primero el servicio normal y después el consolidado, cada vez con una sesión
    nueva; si ninguno responde, se lanza la última excepción para que la pantalla
    no confunda una caída con «no existe».
    """
    ruc = normalizar_ruc(ruc)
    if not validar_ruc(ruc):
        raise ValueError("RUC inválido: debe tener 13 dígitos y terminar en 001.")

    crudo: Any = None
    respondio = False
    errores: List[Exception] = []

    for url in (URL_CONSULTA, URL_CONSULTA_ALT):
        try:
            crudo = _pedir(_sesion(), url, {"ruc": ruc}, timeout)
            respondio = True
        except requests.RequestException as exc:
            errores.append(exc)
            crudo = None

        contribuyentes = crudo.get("contribuyentes") if isinstance(crudo, dict) else None
        if not contribuyentes and isinstance(crudo, list):
            contribuyentes = crudo
        if contribuyentes:
            break
        if not respondio:
            time.sleep(0.35)

    if not respondio and errores:
        raise errores[-1]

    if not contribuyentes:
        return ResultadoConsulta(ruc=ruc, encontrado=False, crudo=crudo)

    primero = contribuyentes[0]
    return ResultadoConsulta(
        ruc=ruc,
        encontrado=True,
        datos=_normalizar(primero),
        crudo=primero,
    )


def _main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Consulta un RUC en el SRI (webservice gratuito, sin autenticación)."
    )
    parser.add_argument("ruc", help="RUC de 13 dígitos (ej. 0703886697001)")
    parser.add_argument(
        "--json", dest="salida_json", action="store_true", help="Imprimir el resultado en JSON"
    )
    parser.add_argument(
        "--crudo", action="store_true", help="Incluir el JSON original del SRI"
    )
    parser.add_argument(
        "--timeout", type=float, default=20.0, help="Segundos de espera máxima (por defecto 20)"
    )
    args = parser.parse_args(argv)

    ruc = normalizar_ruc(args.ruc)
    if not validar_ruc(ruc):
        print(
            f"❌ RUC inválido: {args.ruc!r}. Debe tener 13 dígitos y terminar en 001.",
            file=sys.stderr,
        )
        return 2

    try:
        resultado = consultar_ruc_sri(ruc, timeout=args.timeout)
    except Exception as exc:
        print(f"❌ Error al consultar el RUC {ruc}: {exc}", file=sys.stderr)
        return 1

    if args.salida_json:
        salida = resultado.to_dict()
        if not args.crudo:
            salida.pop("crudo", None)
        print(json.dumps(salida, ensure_ascii=False, indent=2))
        return 0 if resultado.encontrado else 3

    print(f"\n🔍 RUC consultado: {ruc}")
    if not resultado.encontrado:
        print("⚠️  El SRI no encontró información para este RUC.")
        return 3

    print("✅ Datos encontrados:\n")
    for etiqueta, valor in resultado.datos.items():
        print(f"  {etiqueta}: {valor}")
    if args.crudo:
        print("\n--- JSON original ---")
        print(json.dumps(_a_json(resultado.crudo), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_main())

