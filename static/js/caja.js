/* La caja: el desglose del efectivo y las ventanas del turno.
 *
 * El desglose: cada casilla dice cuántos billetes o monedas de ese valor se
 * contaron. Aquí se multiplica por su valor, se suma todo y se escribe el total
 * —y el campo del efectivo contado— para que el cajero vea el arqueo mientras
 * cuenta.
 *
 * Las ventanas: «registrar movimiento» y «cerrar caja» se abren en un panel
 * centrado en vez de ocupar el lateral. Se cierran con la ×, con «Cancelar», con
 * la tecla Esc o tocando fuera; al abrirse, el foco se va al primer campo.
 */
(function () {
  "use strict";

  // ------------------------------------------------------------- el desglose

  function aNumero(texto) {
    var limpio = String(texto || "").replace(/\s/g, "").replace(/\./g, "").replace(",", ".");
    var valor = parseFloat(limpio);
    return isNaN(valor) ? 0 : valor;
  }

  function aTexto(valor) {
    return valor.toLocaleString("es-EC", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function engancharDesglose(formulario) {
    var total = formulario.querySelector("[data-total-desglose]");
    var declarado = formulario.querySelector("[name='saldo_declarado']");
    var casillas = formulario.querySelectorAll(".desglose-cantidad");

    function pintar() {
      var suma = 0;
      Array.prototype.forEach.call(casillas, function (casilla) {
        var valor = aNumero(casilla.getAttribute("data-valor"));
        var cantidad = parseInt(casilla.value, 10) || 0;
        var subtotal = valor * cantidad;
        suma += subtotal;

        var fila = casilla.closest("tr");
        var celda = fila && fila.querySelector("[data-subtotal]");
        if (celda) {
          celda.textContent = aTexto(subtotal);
        }
      });

      if (total) {
        total.textContent = aTexto(suma);
      }
      // Si se contó por denominación, el efectivo contado es ese total; si no se
      // contó nada, el campo se deja como esté para escribirlo a mano.
      if (declarado && suma > 0) {
        declarado.value = suma.toFixed(2);
      }
    }

    formulario.addEventListener("input", pintar);
    formulario.addEventListener("change", pintar);
    pintar();
  }

  Array.prototype.forEach.call(document.querySelectorAll("[data-desglose]"), engancharDesglose);

  // -------------------------------------------------------------- las ventanas

  var abierta = null;
  var quienAbrio = null;

  function cerrar() {
    if (!abierta) {
      return;
    }
    abierta.hidden = true;
    document.body.classList.remove("con-modal");
    abierta = null;
    if (quienAbrio && typeof quienAbrio.focus === "function") {
      quienAbrio.focus();
    }
  }

  function abrir(ventana, boton) {
    if (!ventana) {
      return;
    }
    if (abierta) {
      cerrar();
    }
    ventana.hidden = false;
    document.body.classList.add("con-modal");
    abierta = ventana;
    quienAbrio = boton || null;

    var primero = ventana.querySelector("input:not([type=hidden]), select, textarea");
    if (primero && typeof primero.focus === "function") {
      primero.focus();
    }
  }

  document.addEventListener("click", function (evento) {
    var abrirBoton = evento.target.closest("[data-abrir-modal]");
    if (abrirBoton) {
      evento.preventDefault();
      abrir(document.getElementById(abrirBoton.getAttribute("data-abrir-modal")), abrirBoton);
      return;
    }

    if (evento.target.closest("[data-cerrar-modal]")) {
      evento.preventDefault();
      cerrar();
      return;
    }

    // Un clic en el fondo (fuera del panel) también cierra.
    if (abierta && evento.target === abierta) {
      cerrar();
    }
  });

  document.addEventListener("keydown", function (evento) {
    if (evento.key === "Escape" && abierta) {
      cerrar();
    }
  });
})();
