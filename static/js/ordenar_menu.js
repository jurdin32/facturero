/* Ordena el menú arrastrando: primero los apartados y, dentro, sus opciones.
 *
 * No se usan números: el orden del DOM es el orden del menú. Al soltar se manda
 * una lista plana de opciones; el servidor le pone el orden correlativo y el
 * primer elemento de cada apartado decide también el orden de los apartados.
 */
(function () {
  "use strict";

  var caja = document.querySelector("[data-orden-menu]");
  if (!caja) return;

  var url = caja.dataset.url;
  var aviso = caja.querySelector("[data-orden-aviso]");
  var csrf = caja.querySelector("[name=csrfmiddlewaretoken]");
  var token = csrf ? csrf.value : "";
  var grupoArrastrado = null;
  var opcionArrastrada = null;
  var temporizador = null;

  function estado(texto, tipo) {
    if (!aviso) return;
    aviso.textContent = texto;
    aviso.className = "aviso aviso-" + (tipo || "info");
  }

  function limpiar() {
    caja.querySelectorAll(".arrastrando").forEach(function (nodo) {
      nodo.classList.remove("arrastrando");
    });
    grupoArrastrado = null;
    opcionArrastrada = null;
  }

  function opcionesEnOrden() {
    var ids = [];
    caja.querySelectorAll("[data-grupo]").forEach(function (grupo) {
      grupo.querySelectorAll("[data-opcion]").forEach(function (opcion) {
        ids.push(opcion.dataset.opcion);
      });
    });
    return ids;
  }

  function guardar() {
    var ids = opcionesEnOrden();
    if (!ids.length) return;

    var cuerpo = new URLSearchParams();
    ids.forEach(function (id) {
      cuerpo.append("opciones", id);
    });

    fetch(url, {
      method: "POST",
      headers: {
        "X-CSRFToken": token,
        "Content-Type": "application/x-www-form-urlencoded",
        Accept: "application/json",
      },
      body: cuerpo.toString(),
      credentials: "same-origin",
    })
      .then(function (respuesta) {
        if (!respuesta.ok) throw new Error("No se pudo guardar el orden.");
        return respuesta.json();
      })
      .then(function (datos) {
        if (!datos.ok) throw new Error(datos.error || "No se pudo guardar el orden.");
        estado("Orden guardado. Así queda en el menú.", "success");
      })
      .catch(function (error) {
        estado(error.message || "No se pudo guardar el orden.", "error");
      });
  }

  function programar() {
    estado("Guardando el orden…", "info");
    window.clearTimeout(temporizador);
    temporizador = window.setTimeout(guardar, 180);
  }

  // --------------------------------------------------------- los apartados
  caja.querySelectorAll("[data-arrastrar-grupo]").forEach(function (agarre) {
    agarre.addEventListener("dragstart", function (evento) {
      opcionArrastrada = null;
      grupoArrastrado = agarre.closest("[data-grupo]");
      if (!grupoArrastrado) return;
      grupoArrastrado.classList.add("arrastrando");
      evento.dataTransfer.effectAllowed = "move";
      evento.dataTransfer.setData("text/plain", "grupo");
    });
    agarre.addEventListener("dragend", limpiar);
  });

  caja.querySelectorAll("[data-grupo]").forEach(function (destino) {
    destino.addEventListener("dragover", function (evento) {
      if (!grupoArrastrado || grupoArrastrado === destino) return;
      evento.preventDefault();
      evento.dataTransfer.dropEffect = "move";
    });

    destino.addEventListener("drop", function (evento) {
      if (!grupoArrastrado || grupoArrastrado === destino) return;
      evento.preventDefault();
      evento.stopPropagation();

      var cajaDestino = destino.getBoundingClientRect();
      var despues = evento.clientY > cajaDestino.top + cajaDestino.height / 2;
      if (despues) {
        destino.parentNode.insertBefore(grupoArrastrado, destino.nextElementSibling);
      } else {
        destino.parentNode.insertBefore(grupoArrastrado, destino);
      }
      limpiar();
      programar();
    });
  });

  // ----------------------------------------------------------- las opciones
  caja.querySelectorAll("[data-opcion]").forEach(function (opcion) {
    opcion.addEventListener("dragstart", function (evento) {
      grupoArrastrado = null;
      opcionArrastrada = opcion;
      opcion.classList.add("arrastrando");
      evento.stopPropagation();
      evento.dataTransfer.effectAllowed = "move";
      evento.dataTransfer.setData("text/plain", "opcion");
    });

    opcion.addEventListener("dragend", limpiar);

    opcion.addEventListener("dragover", function (evento) {
      if (!opcionArrastrada || opcionArrastrada === opcion) return;
      if (opcionArrastrada.closest("[data-grupo]") !== opcion.closest("[data-grupo]")) {
        return;
      }
      evento.preventDefault();
      evento.stopPropagation();
      var cajaOpcion = opcion.getBoundingClientRect();
      var despues = evento.clientY > cajaOpcion.top + cajaOpcion.height / 2;
      opcion.parentNode.insertBefore(
        opcionArrastrada,
        despues ? opcion.nextElementSibling : opcion
      );
    });

    opcion.addEventListener("drop", function (evento) {
      if (!opcionArrastrada) return;
      evento.preventDefault();
      evento.stopPropagation();
      programar();
    });
  });

  caja.querySelectorAll("[data-opciones]").forEach(function (lista) {
    lista.addEventListener("dragover", function (evento) {
      if (!opcionArrastrada) return;
      if (opcionArrastrada.closest("[data-grupo]") !== lista.closest("[data-grupo]")) {
        return;
      }
      evento.preventDefault();
      evento.stopPropagation();
    });

    lista.addEventListener("drop", function (evento) {
      if (!opcionArrastrada) return;
      if (opcionArrastrada.closest("[data-grupo]") !== lista.closest("[data-grupo]")) {
        return;
      }
      evento.preventDefault();
      evento.stopPropagation();
      lista.appendChild(opcionArrastrada);
      programar();
    });
  });
})();
