/* Las líneas del asiento: se escriben en una ventana y la tabla solo muestra lo
 * que ya está puesto. También suma el debe y el haber y avisa si no cuadra.
 *
 * Los importes se escriben como en Ecuador («1.234,56»), así que se limpian antes
 * de sumarlos. El servidor vuelve a comprobarlo todo: esto es solo para no tener
 * que hacer la cuenta a mano.
 */
(function () {
  "use strict";

  var MARCA = "__prefix__";
  var CAMPOS = ["cuenta", "descripcion", "debe", "haber", "tercero", "documento"];

  function porId(nombre) {
    return document.getElementById(nombre) || document.getElementById("id_" + nombre);
  }

  function numero(texto) {
    var limpio = String(texto || "").trim().replace(/\s/g, "").replace(/\$/g, "");
    if (!limpio) return 0;
    if (limpio.indexOf(",") !== -1) {
      limpio = limpio.replace(/\./g, "").replace(",", ".");
    }
    var valor = parseFloat(limpio);
    return isNaN(valor) ? 0 : valor;
  }

  function formato(valor) {
    return new Intl.NumberFormat("es-EC", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(valor);
  }

  /** El campo real de la fila, que va oculto pero es el que se envía. */
  function campo(fila, sufijo) {
    return fila ? fila.querySelector('[name$="-' + sufijo + '"]') : null;
  }

  function textoOpcion(select) {
    if (!select || !select.value) return "—";
    var opcion = select.options[select.selectedIndex];
    return opcion ? opcion.textContent.trim() : select.value;
  }

  /** Pone en las celdas visibles lo que hay en los campos ocultos. */
  function actualizarFila(fila) {
    var cuenta = campo(fila, "cuenta");
    var descripcion = campo(fila, "descripcion");
    var debe = campo(fila, "debe");
    var haber = campo(fila, "haber");
    var tercero = campo(fila, "tercero");
    var documento = campo(fila, "documento");

    var verCuenta = fila.querySelector("[data-ver-cuenta]");
    var verDescripcion = fila.querySelector("[data-ver-descripcion]");
    var verDebe = fila.querySelector("[data-ver-debe]");
    var verHaber = fila.querySelector("[data-ver-haber]");
    var verTercero = fila.querySelector("[data-ver-tercero]");
    var verDocumento = fila.querySelector("[data-ver-documento]");

    if (verCuenta) verCuenta.textContent = textoOpcion(cuenta);
    if (verDescripcion) {
      verDescripcion.textContent = descripcion && descripcion.value.trim()
        ? descripcion.value.trim()
        : "—";
    }
    if (verDebe) verDebe.textContent = debe && numero(debe.value) ? formato(numero(debe.value)) : "—";
    if (verHaber) verHaber.textContent = haber && numero(haber.value) ? formato(numero(haber.value)) : "—";
    if (verTercero) verTercero.textContent = textoOpcion(tercero);
    if (verDocumento) {
      verDocumento.textContent = documento && documento.value.trim()
        ? documento.value.trim()
        : "—";
    }
  }

  function tablaDe(boton) {
    var para = boton.dataset.para;
    if (para) return document.querySelector('table[data-lineas="' + para + '"]');
    return boton.closest("table[data-lineas]");
  }

  function refrescarVacio(tabla) {
    var cuerpo = tabla.querySelector("[data-cuerpo-lineas]");
    var aviso = document.querySelector("[data-vacio-lineas]");
    if (!cuerpo || !aviso) return;
    var hay = Array.prototype.some.call(
      cuerpo.querySelectorAll("tr[data-linea]"),
      function (fila) { return !fila.classList.contains("oculto"); }
    );
    aviso.classList.toggle("oculto", hay);
  }

  function sumar() {
    var tabla = document.querySelector("table[data-lineas]");
    var caja = document.querySelector("[data-totales-asiento]");
    if (!tabla || !caja) return;

    var debe = 0;
    var haber = 0;
    tabla.querySelectorAll("tbody tr[data-linea]").forEach(function (fila) {
      if (fila.classList.contains("oculto")) return;
      var borrar = campo(fila, "DELETE");
      if (borrar && borrar.checked) return;
      debe += numero(campo(fila, "debe") && campo(fila, "debe").value);
      haber += numero(campo(fila, "haber") && campo(fila, "haber").value);
    });

    var diferencia = debe - haber;
    var etiquetaDebe = caja.querySelector("[data-total-debe]");
    var etiquetaHaber = caja.querySelector("[data-total-haber]");
    var etiquetaDiferencia = caja.querySelector("[data-diferencia]");
    if (etiquetaDebe) etiquetaDebe.textContent = formato(debe);
    if (etiquetaHaber) etiquetaHaber.textContent = formato(haber);
    if (etiquetaDiferencia) {
      etiquetaDiferencia.textContent =
        Math.abs(diferencia) < 0.005
          ? "cuadra"
          : "diferencia " + formato(Math.abs(diferencia));
      etiquetaDiferencia.className =
        Math.abs(diferencia) < 0.005 ? "entra" : "sale";
    }
  }

  /** Una fila nueva, con sus nombres de formset ya numerados. */
  function filaNueva(tabla) {
    var plantilla = document.getElementById(tabla.dataset.plantilla || "");
    var cuenta = porId(tabla.dataset.total || "");
    if (!plantilla || !cuenta) return null;
    var numeroFila = parseInt(cuenta.value, 10) || 0;
    var molde = document.createElement("template");
    molde.innerHTML = plantilla.innerHTML.split(MARCA).join(String(numeroFila)).trim();
    var fila = molde.content.firstElementChild;
    if (!fila) return null;
    cuenta.value = String(numeroFila + 1);
    return fila;
  }

  function abrirModal(tabla, fila) {
    var plantilla = document.getElementById(tabla.dataset.modal || "");
    if (!plantilla) return;
    var modal = plantilla.content.firstElementChild.cloneNode(true);

    Metro.dialog.create({
      title: fila ? "Editar la línea" : "Añadir una línea",
      content: modal.outerHTML,
      closeButton: true,
      defaultActions: false,
      clsDialog: "dialogo-linea",
      customButtons: [
        {
          text: fila ? "Guardar línea" : "Añadir línea",
          cls: "primary",
          onclick: function () { guardarLinea(tabla, fila); },
        },
        { text: "Cancelar", cls: "js-dialog-close" },
      ],
    });

    var dialogo = document.querySelector(".dialogo-linea");
    // Los valores se copian ya dentro de la ventana: el HTML serializado no
    // conserva lo que se escribe en las propiedades `value`.
    if (dialogo && fila) {
      CAMPOS.forEach(function (nombre) {
        var origen = campo(fila, nombre);
        var destino = campo(dialogo, nombre);
        if (origen && destino) destino.value = origen.value;
      });
    }
    if (dialogo && Metro.initWidgets) {
      Metro.initWidgets(dialogo.querySelectorAll("[data-role]"));
    }
  }

  function guardarLinea(tabla, filaExistente) {
    var dialogo = document.querySelector(".dialogo-linea");
    if (!dialogo) return;
    var datos = {};
    CAMPOS.forEach(function (nombre) {
      var control = campo(dialogo, nombre);
      datos[nombre] = control ? control.value : "";
    });

    var error = dialogo.querySelector("[data-error-linea]");
    function fallo(mensaje) {
      if (!error) return;
      error.textContent = mensaje;
      error.classList.remove("oculto");
      error.scrollIntoView({ block: "nearest" });
    }

    var debe = numero(datos.debe);
    var haber = numero(datos.haber);
    var llevaDebe = debe > 0;
    var llevaHaber = haber > 0;
    if (!datos.cuenta) {
      fallo("Elija la cuenta de la línea.");
      return;
    }
    if (llevaDebe === llevaHaber) {
      fallo("Escriba un importe en el debe o en el haber, pero no en los dos.");
      return;
    }

    var fila = filaExistente || filaNueva(tabla);
    if (!fila) {
      fallo("No se pudo preparar la línea. Recargue la página.");
      return;
    }
    CAMPOS.forEach(function (nombre) {
      var control = campo(fila, nombre);
      if (control) control.value = datos[nombre];
    });
    fila.classList.remove("oculto", "linea-vacia");
    actualizarFila(fila);
    if (!filaExistente) {
      tabla.querySelector("[data-cuerpo-lineas]").appendChild(fila);
    }

    Metro.dialog.close(".dialogo-linea");
    refrescarVacio(tabla);
    sumar();
  }

  function quitarLinea(boton) {
    var fila = boton.closest("tr[data-linea]");
    var tabla = boton.closest("table[data-lineas]");
    if (!fila || !tabla) return;
    var identificador = campo(fila, "id");
    if (identificador && identificador.value) {
      // Ya está guardada: se marca para que el servidor la borre, no se quita del DOM.
      var borrar = campo(fila, "DELETE");
      if (borrar) borrar.checked = true;
      fila.classList.add("oculto");
    } else {
      fila.remove();
    }
    refrescarVacio(tabla);
    sumar();
  }

  document.addEventListener("click", function (evento) {
    var abrir = evento.target.closest("[data-abrir-linea]");
    if (abrir) {
      evento.preventDefault();
      var tabla = tablaDe(abrir);
      if (tabla) abrirModal(tabla, null);
      return;
    }
    var editar = evento.target.closest("[data-editar-linea]");
    if (editar) {
      evento.preventDefault();
      abrirModal(editar.closest("table[data-lineas]"), editar.closest("tr[data-linea]"));
      return;
    }
    var quitar = evento.target.closest("[data-quitar-linea]");
    if (quitar) {
      evento.preventDefault();
      quitarLinea(quitar);
    }
  });

  document.addEventListener("input", function (evento) {
    if (evento.target.closest("table[data-lineas]")) sumar();
  });

  function preparar() {
    document.querySelectorAll("table[data-lineas]").forEach(function (tabla) {
      tabla.querySelectorAll("tbody tr[data-linea]").forEach(function (fila) {
        if (fila.classList.contains("linea-vacia")) return;
        fila.classList.remove("oculto");
        actualizarFila(fila);
      });
      refrescarVacio(tabla);
    });
    sumar();
  }

  document.addEventListener("DOMContentLoaded", preparar);
  preparar();
})();
