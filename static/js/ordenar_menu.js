/* Ordena el menú arrastrando: primero los apartados y, dentro, sus opciones.
 *
 * No se usan números: el orden del DOM es el orden del menú. Al soltar se manda
 * una lista plana de opciones; el servidor le pone el orden correlativo y el
 * primer elemento de cada apartado decide también el orden de los apartados.
 *
 * Mientras se arrastra **no se mueve nada**: aparece una línea —la guía— donde
 * va a caer, y el cambio se hace al soltar. Antes la tarjeta se movía sola al
 * pasar por encima, sin decir dónde quedaba, y al soltar en un hueco no pasaba
 * nada: no había forma de saber dónde soltar.
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

  //: Una guía para dentro de una lista (tiene que ser un <li>) y otra para
  //: entre apartados (un <div>).
  var guiaOpcion = crearGuia("li");
  var guiaGrupo = crearGuia("div");

  function crearGuia(etiqueta) {
    var nodo = document.createElement(etiqueta);
    nodo.className = "orden-guia";
    nodo.setAttribute("aria-hidden", "true");
    var texto = document.createElement("span");
    texto.textContent = "Suelte aquí";
    nodo.appendChild(texto);
    return nodo;
  }

  function estado(texto, tipo) {
    if (!aviso) return;
    aviso.textContent = texto;
    aviso.className = "aviso aviso-" + (tipo || "info");
  }

  function quitarGuias() {
    [guiaOpcion, guiaGrupo].forEach(function (guia) {
      if (guia.parentNode) guia.parentNode.removeChild(guia);
    });
  }

  function limpiar() {
    caja.querySelectorAll(".arrastrando").forEach(function (nodo) {
      nodo.classList.remove("arrastrando");
    });
    caja.querySelectorAll(".orden-destino-otro").forEach(function (nodo) {
      nodo.classList.remove("orden-destino-otro");
    });
    quitarGuias();
    document.body.classList.remove("orden-arrastrando");
    grupoArrastrado = null;
    opcionArrastrada = null;
    estado("Las flechas guardan al momento. Lo que se arrastra se guarda al soltar.", "info");
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

  // Al arrastrar cerca del borde, la página se mueve sola: en un apartado largo
  // no se podía llevar una tarjeta de abajo arriba sin soltarla.
  var MARGEN = 90;
  var PASO = 16;

  function autoScroll(evento) {
    var alto = window.innerHeight || document.documentElement.clientHeight;
    if (evento.clientY < MARGEN) {
      window.scrollBy(0, -PASO);
    } else if (evento.clientY > alto - MARGEN) {
      window.scrollBy(0, PASO);
    }
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
      document.body.classList.add("orden-arrastrando");
      evento.dataTransfer.effectAllowed = "move";
      evento.dataTransfer.setData("text/plain", "grupo");
      estado("Suelte el apartado donde esté la línea.", "info");
    });
    agarre.addEventListener("dragend", limpiar);
  });

  caja.addEventListener("dragover", function (evento) {
    if (!grupoArrastrado) return;
    autoScroll(evento);
    var destinos = Array.prototype.filter.call(caja.children, function (hijo) {
      return hijo.hasAttribute("data-grupo") && hijo !== grupoArrastrado;
    });
    if (!destinos.length) return;
    evento.preventDefault();
    evento.stopPropagation();
    evento.dataTransfer.dropEffect = "move";

    var referencia = null;
    var despues = false;
    for (var i = 0; i < destinos.length; i += 1) {
      var cajaDestino = destinos[i].getBoundingClientRect();
      if (evento.clientY < cajaDestino.top + cajaDestino.height / 2) {
        referencia = destinos[i];
        despues = false;
        break;
      }
      referencia = destinos[i];
      despues = true;
    }
    if (!referencia) return;
    if (despues) {
      referencia.parentNode.insertBefore(guiaGrupo, referencia.nextElementSibling);
    } else {
      referencia.parentNode.insertBefore(guiaGrupo, referencia);
    }
  });

  caja.addEventListener("drop", function (evento) {
    if (!grupoArrastrado || !guiaGrupo.parentNode) return;
    evento.preventDefault();
    guiaGrupo.parentNode.insertBefore(grupoArrastrado, guiaGrupo);
    limpiar();
    programar();
  });

  // ----------------------------------------------------------- las opciones
  caja.querySelectorAll("[data-opcion]").forEach(function (opcion) {
    opcion.addEventListener("dragstart", function (evento) {
      grupoArrastrado = null;
      opcionArrastrada = opcion;
      opcion.classList.add("arrastrando");
      document.body.classList.add("orden-arrastrando");
      evento.stopPropagation();
      evento.dataTransfer.effectAllowed = "move";
      evento.dataTransfer.setData("text/plain", "opcion");
      // Los demás apartados no aceptan la tarjeta: se ve dónde sí y dónde no.
      var suyo = opcion.closest("[data-grupo]");
      caja.querySelectorAll("[data-opciones]").forEach(function (lista) {
        if (lista.closest("[data-grupo]") !== suyo) {
          lista.classList.add("orden-destino-otro");
        }
      });
      estado("Suelte la opción donde esté la línea, dentro de su apartado.", "info");
    });

    opcion.addEventListener("dragend", limpiar);
  });

  // Todo el movimiento se decide con la posición del puntero dentro de la lista:
  // así vale soltar sobre otra tarjeta, en el hueco entre dos o al final, y la
  // guía enseña exactamente dónde va a quedar.
  caja.querySelectorAll("[data-opciones]").forEach(function (lista) {
    function puedeSoltar() {
      if (!opcionArrastrada) return false;
      return opcionArrastrada.closest("[data-grupo]") === lista.closest("[data-grupo]");
    }

    lista.addEventListener("dragover", function (evento) {
      if (!puedeSoltar()) return;
      autoScroll(evento);
      evento.preventDefault();
      evento.stopPropagation();
      evento.dataTransfer.dropEffect = "move";

      var hermanas = Array.prototype.filter.call(
        lista.querySelectorAll("[data-opcion]"),
        function (otra) {
          return otra !== opcionArrastrada;
        }
      );
      var puesta = false;
      for (var i = 0; i < hermanas.length; i += 1) {
        var cajaOtra = hermanas[i].getBoundingClientRect();
        if (evento.clientY < cajaOtra.top + cajaOtra.height / 2) {
          lista.insertBefore(guiaOpcion, hermanas[i]);
          puesta = true;
          break;
        }
      }
      if (!puesta) lista.appendChild(guiaOpcion);
    });

    lista.addEventListener("drop", function (evento) {
      if (!puedeSoltar() || !guiaOpcion.parentNode) return;
      evento.preventDefault();
      evento.stopPropagation();
      guiaOpcion.parentNode.insertBefore(opcionArrastrada, guiaOpcion);
      limpiar();
      programar();
    });
  });
})();
