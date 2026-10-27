/* El editor de la descripción larga de la tienda: texto enriquecido.
 *
 * Lo que se escribe es HTML y así se guarda; el área es `contenteditable`, como
 * en cualquier editor visual. Los botones de arriba dan formato a lo que esté
 * seleccionado y las tablas se editan en el sitio: al entrar en una celda sale
 * su barra para añadir o quitar filas y columnas.
 *
 * Se engancha solo a las cajas con `data-editor-rico`.
 */
(function () {
  "use strict";

  var ALTO_MINIMO = 180;
  var ALTO_MAXIMO = 620;

  /* La tabla de partida: dos columnas con su cabecera y una fila vacía, que es lo
   * que deja TinyMCE al insertar una tabla. */
  var TABLA_NUEVA =
    "<table><thead><tr><th><br></th><th><br></th></tr></thead>" +
    "<tbody><tr><td><br></td><td><br></td></tr></tbody></table><p><br></p>";

  function montar(caja) {
    var area = caja.querySelector("[data-area]");
    var campo = caja.querySelector("[data-campo]");
    var barraTabla = caja.querySelector("[data-tabla-barra]");
    if (!area || !campo) {
      return;
    }

    // Lo guardado viene escapado en el campo oculto; al meterlo en el área se
    // interpreta como HTML, que es lo que el editor dejó escrito.
    area.innerHTML = (campo.value || "").trim() || "<p><br></p>";

    function guardar() {
      var html = area.innerHTML;
      campo.value = html === "<p><br></p>" ? "" : html;
    }

    function ajustar() {
      if (area.offsetParent === null) {
        return;
      }
      area.style.height = "0px";
      var alto = Math.min(Math.max(area.scrollHeight, ALTO_MINIMO), ALTO_MAXIMO);
      area.style.height = alto + "px";
      area.style.overflowY = area.scrollHeight > ALTO_MAXIMO ? "auto" : "hidden";
    }

    function enfocar() {
      area.focus();
    }

    function ejecutar(orden, valor) {
      enfocar();
      try {
        document.execCommand(orden, false, valor || null);
      } catch (fallo) {
        // Un navegador que no conozca el comando no debe romper el editor.
      }
      guardar();
      ajustar();
    }

    /* ------------------------------------------------------------- la barra */

    caja.addEventListener("click", function (evento) {
      var boton = evento.target.closest("[data-formato]");
      if (!boton) {
        return;
      }
      evento.preventDefault();
      var que = boton.getAttribute("data-formato");
      if (que === "negrita") {
        ejecutar("bold");
      } else if (que === "cursiva") {
        ejecutar("italic");
      } else if (que === "titulo") {
        ejecutar("formatBlock", "<h2>");
      } else if (que === "vinetas") {
        ejecutar("insertUnorderedList");
      } else if (que === "numerada") {
        ejecutar("insertOrderedList");
      } else if (que === "cita") {
        ejecutar("formatBlock", "<blockquote>");
      } else if (que === "codigo") {
        ejecutar("insertHTML", "<code>código</code>");
      } else if (que === "separador") {
        ejecutar("insertHorizontalRule");
      } else if (que === "enlace") {
        var direccion = window.prompt("¿A dónde lleva el enlace?", "https://");
        if (direccion) {
          ejecutar("createLink", direccion);
        }
      } else if (que === "tabla") {
        if (tablaActual()) {
          colocarAlFinal();
        }
        ejecutar("insertHTML", TABLA_NUEVA + "<p><br></p>");
        // El cursor se queda en la primera celda: escribir empieza por ahí.
        var tablas = area.querySelectorAll("table");
        var primera = tablas.length
          ? tablas[tablas.length - 1].querySelector("td, th")
          : null;
        if (primera) {
          colocarEn(primera);
        }
        mirarTabla();
      }
    });

    /* ------------------------------------------------------------ las tablas */

    function tablaActual() {
      var seleccion = window.getSelection();
      if (!seleccion || !seleccion.rangeCount) {
        return null;
      }
      var nodo = seleccion.getRangeAt(0).startContainer;
      if (nodo.nodeType === 3) {
        nodo = nodo.parentNode;
      }
      if (!nodo || !nodo.closest) {
        return null;
      }
      var tabla = nodo.closest("table");
      return tabla && area.contains(tabla) ? tabla : null;
    }

    function mirarTabla() {
      if (!barraTabla) {
        return;
      }
      var dentro = !!tablaActual();
      barraTabla.hidden = !dentro;
      caja.classList.toggle("con-tabla", dentro);
    }

    function filasDe(tabla) {
      return Array.prototype.slice.call(tabla.querySelectorAll("tr"));
    }

    function celdaVacia(modelo) {
      var celda = document.createElement(modelo && modelo.tagName === "TH" ? "th" : "td");
      celda.innerHTML = "<br>";
      return celda;
    }

    function anadirFila(tabla) {
      var cuerpo = tabla.tBodies[tabla.tBodies.length - 1];
      var filas = filasDe(tabla);
      var modelo = filas[filas.length - 1];
      if (!cuerpo) {
        cuerpo = document.createElement("tbody");
        tabla.appendChild(cuerpo);
      }
      var nueva = document.createElement("tr");
      var cuantas = modelo ? modelo.children.length : 1;
      for (var i = 0; i < cuantas; i++) {
        nueva.appendChild(celdaVacia(modelo ? modelo.children[i] : null));
      }
      cuerpo.appendChild(nueva);
      var primera = nueva.querySelector("td, th");
      if (primera) {
        colocarEn(primera);
      }
    }

    function anadirColumna(tabla) {
      filasDe(tabla).forEach(function (fila) {
        var modelo = fila.children[fila.children.length - 1];
        fila.appendChild(celdaVacia(modelo));
      });
    }

    function quitarFila(tabla) {
      var filas = filasDe(tabla);
      if (filas.length <= 2) {
        quitarTabla(tabla);
        return;
      }
      var ultima = filas[filas.length - 1];
      if (ultima.parentNode.tagName === "THEAD") {
        return;
      }
      ultima.parentNode.removeChild(ultima);
    }

    function quitarColumna(tabla) {
      var filas = filasDe(tabla);
      if (!filas.length || filas[0].children.length <= 1) {
        quitarTabla(tabla);
        return;
      }
      filas.forEach(function (fila) {
        fila.removeChild(fila.children[fila.children.length - 1]);
      });
    }

    function quitarTabla(tabla) {
      tabla.parentNode.removeChild(tabla);
      if (barraTabla) {
        barraTabla.hidden = true;
      }
      caja.classList.remove("con-tabla");
      guardar();
      ajustar();
    }

    function colocarAlFinal() {
      var rango = document.createRange();
      rango.selectNodeContents(area);
      rango.collapse(false);
      var seleccion = window.getSelection();
      seleccion.removeAllRanges();
      seleccion.addRange(rango);
      area.focus();
    }

    function colocarEn(celda) {
      var rango = document.createRange();
      rango.selectNodeContents(celda);
      rango.collapse(true);
      var seleccion = window.getSelection();
      seleccion.removeAllRanges();
      seleccion.addRange(rango);
      area.focus();
    }

    if (barraTabla) {
      barraTabla.addEventListener("click", function (evento) {
        var boton = evento.target.closest("[data-tabla]");
        if (!boton) {
          return;
        }
        evento.preventDefault();
        var tabla = tablaActual();
        if (!tabla) {
          return;
        }
        var que = boton.getAttribute("data-tabla");
        if (que === "fila-mas") {
          anadirFila(tabla);
        } else if (que === "fila-menos") {
          quitarFila(tabla);
        } else if (que === "columna-mas") {
          anadirColumna(tabla);
        } else if (que === "columna-menos") {
          quitarColumna(tabla);
        } else if (que === "quitar") {
          quitarTabla(tabla);
        }
        guardar();
        ajustar();
        mirarTabla();
      });
    }

    /* Escritura, pegado y salida: el campo oculto va siempre al día. */
    area.addEventListener("input", function () {
      guardar();
      ajustar();
      mirarTabla();
    });
    area.addEventListener("blur", guardar);
    area.addEventListener("keyup", mirarTabla);
    area.addEventListener("mouseup", mirarTabla);
    area.addEventListener("click", mirarTabla);

    /* Lo que llega de una web trae estilos, clases y hasta guiones. Se queda el
       texto con su formato básico: negritas, listas, enlaces http y tablas. */
    var TIRAR = "script, style, meta, link, iframe, object, embed, form, input, button";
    function limpiarPegado(html) {
      var documento = new DOMParser().parseFromString(html, "text/html");
      Array.prototype.forEach.call(documento.querySelectorAll(TIRAR), function (nodo) {
        nodo.parentNode.removeChild(nodo);
      });
      Array.prototype.forEach.call(documento.body.querySelectorAll("*"), function (nodo) {
        Array.prototype.slice.call(nodo.attributes).forEach(function (atributo) {
          var nombre = atributo.name.toLowerCase();
          if (nombre === "href") {
            if (!/^(https?:|mailto:)/i.test(atributo.value.trim())) {
              nodo.removeAttribute("href");
            }
          } else if (nombre === "src") {
            if (!/^(https?:|data:image\/)/i.test(atributo.value.trim())) {
              nodo.removeAttribute("src");
            }
          } else {
            nodo.removeAttribute(atributo.name);
          }
        });
      });
      return documento.body.innerHTML;
    }

    // Pegar desde una web trae estilos y guiones: se queda el texto con su
    // formato básico y nada más.
    area.addEventListener("paste", function (evento) {
      var datos = evento.clipboardData || window.clipboardData;
      if (!datos) {
        return;
      }
      var html = datos.getData("text/html");
      var texto = datos.getData("text/plain");
      if (!html) {
        return;
      }
      evento.preventDefault();
      // Dentro de una celda se pega el texto: una tabla ahí dentro quedaría
      // metida en otra y no hay quien la edite.
      if (tablaActual()) {
        ejecutar("insertText", texto);
        return;
      }
      // Sin el texto plano de reserva, un HTML raro dejaría el área vacía.
      ejecutar("insertHTML", limpiarPegado(html) || texto);
    });

    // Con una tabla dentro, el tabulador pasa a la celda siguiente: escribir una
    // tabla deja de ser pelear con el ratón.
    area.addEventListener("keydown", function (evento) {
      if (evento.key !== "Tab") {
        return;
      }
      var tabla = tablaActual();
      if (!tabla) {
        return;
      }
      var celdas = Array.prototype.slice.call(tabla.querySelectorAll("td, th"));
      var seleccion = window.getSelection();
      if (!seleccion.rangeCount) {
        return;
      }
      var nodo = seleccion.getRangeAt(0).startContainer;
      if (nodo.nodeType === 3) {
        nodo = nodo.parentNode;
      }
      var celda = nodo.closest ? nodo.closest("td, th") : null;
      var indice = celdas.indexOf(celda);
      if (indice === -1) {
        return;
      }
      evento.preventDefault();
      if (evento.shiftKey) {
        if (indice > 0) {
          colocarEn(celdas[indice - 1]);
        }
        return;
      }
      if (indice === celdas.length - 1) {
        anadirFila(tabla);
        var ultima = tabla.querySelector("tr:last-child td, tr:last-child th");
        if (ultima) {
          colocarEn(ultima);
        }
        guardar();
        ajustar();
        return;
      }
      colocarEn(celdas[indice + 1]);
    });

    // El formulario se envía con lo que hay en el área, aunque el foco no esté.
    var formulario = area.closest("form");
    if (formulario) {
      formulario.addEventListener("submit", guardar);
    }

    // El editor vive dentro de un paso que se enseña y se esconde.
    if (typeof MutationObserver === "function") {
      var mirar = new MutationObserver(function () {
        if (area.offsetParent !== null) {
          ajustar();
        }
      });
      for (var padre = caja.parentNode; padre && padre !== document.body; padre = padre.parentNode) {
        mirar.observe(padre, { attributes: true, attributeFilter: ["hidden"] });
      }
    }

    ajustar();
  }

  function arrancar() {
    Array.prototype.forEach.call(
      document.querySelectorAll("[data-editor-rico]"),
      montar
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", arrancar);
  } else {
    arrancar();
  }

  window.EditorRico = { arrancar: arrancar, montar: montar };
})();
