/* El asistente de la ficha del producto.
 *
 * Los tres pasos viven en el mismo formulario y se envían juntos: aquí solo se
 * enseña uno cada vez, se marca el que se está viendo y se mueve la barra de
 * progreso. Sin JavaScript se ven los tres seguidos, que es como llega el HTML.
 *
 * Se engancha solo a los formularios con `data-asistente`.
 */
(function () {
  "use strict";

  var TOTAL = 3;

  function arrancar(caja) {
    var formulario = caja.closest("form") || document;
    var secciones = Array.prototype.slice.call(
      formulario.querySelectorAll("[data-seccion]")
    );
    var pasos = Array.prototype.slice.call(caja.querySelectorAll("[data-paso]"));
    if (!secciones.length || !pasos.length) {
      return;
    }

    var cuenta = caja.querySelector("[data-cuenta]");
    var barra = caja.querySelector(".progress-component .bar");
    var visitados = { 1: true };
    var actual = 1;

    function pintar() {
      secciones.forEach(function (seccion) {
        seccion.hidden = Number(seccion.dataset.seccion) !== actual;
      });
      pasos.forEach(function (paso) {
        var numero = Number(paso.dataset.paso);
        var enlace = paso.querySelector("a");
        paso.classList.toggle("paso-activo", numero === actual);
        paso.classList.toggle("paso-hecho", !!visitados[numero] && numero !== actual);
        if (numero === actual) {
          enlace.setAttribute("aria-current", "step");
        } else {
          enlace.removeAttribute("aria-current");
        }
      });
      if (cuenta) {
        cuenta.textContent = actual + " de " + TOTAL;
      }
      if (barra) {
        barra.style.width = Math.round((actual / TOTAL) * 100) + "%";
      }
    }

    function ir(numero, conFoco) {
      if (numero < 1 || numero > TOTAL || numero === actual) {
        return;
      }
      actual = numero;
      visitados[numero] = true;
      pintar();
      if (conFoco) {
        caja.scrollIntoView({ block: "start" });
      }
    }

    // Si al guardar hubo un error, se abre el paso donde está: si no, el aviso
    // saldría en un paso que no se ve.
    var conError = secciones.filter(function (seccion) {
      return seccion.querySelector(".error, .errorlist");
    })[0];
    if (conError) {
      actual = Number(conError.dataset.seccion) || 1;
      visitados[actual] = true;
    }

    caja.addEventListener("click", function (evento) {
      var ir_ = evento.target.closest("[data-ir]");
      if (ir_) {
        evento.preventDefault();
        ir(Number(ir_.dataset.ir), true);
      }
    });

    formulario.addEventListener("click", function (evento) {
      var seguir = evento.target.closest("[data-seguir]");
      if (seguir) {
        evento.preventDefault();
        ir(Number(seguir.dataset.seguir), true);
      }
    });

    pintar();
  }

  function arrancarTodo() {
    Array.prototype.forEach.call(
      document.querySelectorAll("[data-asistente]"),
      arrancar
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", arrancarTodo);
  } else {
    arrancarTodo();
  }
})();
