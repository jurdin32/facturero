/* Completa los datos de un cliente nuevo con el catastro público del SRI.
 *
 * Primero pregunta a la aplicación: si el RUC ya está en el catálogo devuelve
 * los datos guardados y no sale a la red. Solo cuando es nuevo consulta el SRI.
 * Se dispara al salir del campo o al escribir los 13 dígitos, y también con el
 * botón, para que nadie tenga que adivinar que existe. Con 10 dígitos se espera
 * a salir del campo: puede ser una cédula completa o el comienzo de un RUC.
 */
(function () {
  "use strict";

  function soloDigitos(texto) {
    return String(texto || "").replace(/\D/g, "");
  }

  function preparar(raiz) {
    (raiz || document).querySelectorAll("[data-consultar-ruc]").forEach(function (campo) {
    if (campo.dataset.consultaRucLista === "1") return;
    campo.dataset.consultaRucLista = "1";
    var alcance = campo.closest("[data-consulta-ruc]") || campo.closest(".bloque") || document;
    var url = campo.getAttribute("data-consultar-ruc");
    var boton = alcance.querySelector("[data-boton-consultar-ruc]");
    var aviso = alcance.querySelector("[data-aviso-ruc]");
    var razon = alcance.querySelector('[name="razon_social"]');
    var direccion = alcance.querySelector('[name="direccion"]');
    var email = alcance.querySelector('[name="email"]');
    var telefono = alcance.querySelector('[name="telefono"]');
    var tipo = alcance.querySelector('[name="tipo_identificacion"]');
    var turno = 0;
    var temporizador = null;
    var espera = null;

    function cerrarEspera() {
      if (espera && window.Metro && Metro.activity) {
        Metro.activity.close(espera);
      }
      espera = null;
    }

    function abrirEspera(esteTurno) {
      if (esteTurno === turno && window.Metro && Metro.activity) {
        espera = Metro.activity.open({
          text: "Obteniendo datos del SRI…",
          type: "metro",
          style: "color",
        });
      }
    }

    function mostrar(texto, clase) {
      if (!aviso) return;
      aviso.textContent = texto || "";
      aviso.className = "ayuda" + (clase ? " aviso-ruc-" + clase : "");
    }

    function poner(destino, valor, forzar) {
      if (!destino || valor === undefined || valor === null || valor === "") return;
      if (forzar || !String(destino.value || "").trim()) destino.value = valor;
    }

    function ponerTipo(valor) {
      if (!tipo || !valor) return;
      tipo.value = valor;
      // Metro pinta el select con su propio componente: cambiar solo el
      // <select> deja el texto visible con el valor anterior.
      var plugin = window.Metro && window.Metro.getPlugin
        ? window.Metro.getPlugin(tipo, "select")
        : null;
      if (plugin && typeof plugin.val === "function") {
        plugin.val(valor);
      } else {
        tipo.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }

    function consultar() {
      var numero = soloDigitos(campo.value);
      if (numero.length !== 13 && numero.length !== 10) return;
      // Pasaporte, consumidor final e identificación del exterior no se consultan
      // en el catastro del SRI: se escriben a mano.
      if (tipo && ["06", "07", "08"].indexOf(tipo.value) > -1) return;
      // El tipo se deduce de la longitud: el RUC tiene 13 y la cédula 10.
      ponerTipo(numero.length === 13 ? "04" : "05");
      var esteTurno = ++turno;
      cerrarEspera();
      abrirEspera(esteTurno);
      if (boton) {
        boton.disabled = true;
        boton.classList.add("cargando");
      }
      mostrar("Consultando los datos del contribuyente…", "info");

      fetch(url + "?identificacion=" + encodeURIComponent(numero), {
        headers: { Accept: "application/json" },
      })
        .then(function (respuesta) {
          if (!respuesta.ok) throw new Error("No se pudo consultar el RUC.");
          return respuesta.json();
        })
        .then(function (datos) {
          if (esteTurno !== turno) return;
          cerrarEspera();
          if (!datos.encontrado) {
            mostrar(datos.mensaje || "No se encontraron datos para esa identificación.", "error");
            return;
          }
          var cliente = datos.cliente || {};
          campo.value = cliente.identificacion || numero;
          poner(razon, cliente.razon_social, true);
          poner(direccion, cliente.direccion);
          poner(email, cliente.email);
          poner(telefono, cliente.telefono);
          if (cliente.tipo_identificacion) {
            ponerTipo(cliente.tipo_identificacion);
          }

          var texto = datos.mensaje || "";
          if (datos.origen === "sri" && datos.sri) {
            var detalles = [datos.sri.estado, datos.sri.regimen, datos.sri.actividad_economica]
              .filter(Boolean);
            if (detalles.length) texto += " " + detalles.join(" · ");
          }
          mostrar(texto, datos.origen === "local" ? "info" : "ok");
        })
        .catch(function (error) {
          if (esteTurno === turno) {
            cerrarEspera();
            mostrar(error.message || "No se pudo consultar el RUC.", "error");
          }
        })
        .then(function () {
          if (boton) {
            boton.disabled = false;
            boton.classList.remove("cargando");
          }
        });
    }

    campo.addEventListener("blur", consultar);
    campo.addEventListener("input", function () {
      window.clearTimeout(temporizador);
      var largo = soloDigitos(campo.value).length;
      if (largo === 10) {
        // Una cédula completa: se consulta al salir del campo.
        ponerTipo("05");
      } else if (largo > 10) {
        // Ya son más de 10: va camino de un RUC.
        ponerTipo("04");
        if (largo === 13) {
          temporizador = window.setTimeout(consultar, 600);
        }
      }
    });
    if (boton) {
      boton.addEventListener("click", function (evento) {
        evento.preventDefault();
        consultar();
      });
    }
    });
  }

  window.prepararConsultaRuc = preparar;
  document.addEventListener("DOMContentLoaded", function () { preparar(document); });
  preparar(document);
})();
