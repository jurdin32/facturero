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

    /* ---------------------------------------------------------- el historial
     *
     * Lo que el navegador deshace solo son las teclas; las filas, columnas y
     * uniones se tocan a mano y no entrarían. Así que el editor se guarda sus
     * propias instantáneas y Ctrl+Z / Ctrl+Mayúsculas+Z van por ahí.
     */
    var HISTORIAL_MAXIMO = 80;
    var historial = { estados: [], indice: -1, callado: false };
    var temporizador = null;

    function anotar() {
      if (historial.callado) {
        return;
      }
      var actual = area.innerHTML;
      if (historial.estados[historial.indice] === actual) {
        return;
      }
      historial.estados = historial.estados.slice(0, historial.indice + 1);
      historial.estados.push(actual);
      if (historial.estados.length > HISTORIAL_MAXIMO) {
        historial.estados.shift();
      }
      historial.indice = historial.estados.length - 1;
    }

    // Al teclear se espera un poco: una instantánea por palabra, no por letra.
    function anotarPronto() {
      window.clearTimeout(temporizador);
      temporizador = window.setTimeout(anotar, 400);
    }

    function anotarYa() {
      window.clearTimeout(temporizador);
      anotar();
    }

    function volverA(html) {
      historial.callado = true;
      area.innerHTML = html;
      historial.callado = false;
      guardar();
      ajustar();
      mirarTabla();
      area.focus();
    }

    function deshacer() {
      if (historial.indice <= 0) {
        return false;
      }
      historial.indice -= 1;
      volverA(historial.estados[historial.indice]);
      return true;
    }

    function rehacer() {
      if (historial.indice >= historial.estados.length - 1) {
        return false;
      }
      historial.indice += 1;
      volverA(historial.estados[historial.indice]);
      return true;
    }

    historial.estados = [area.innerHTML];
    historial.indice = 0;

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
      anotarYa();
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

    //: La celda en la que se estaba, para cuando el foco se va a los botones.
    var celdaRecordada = null;
    //: La celda desde la que se arrastra para marcar varias.
    var marcando = null;

    function celdaDeSeleccion() {
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
      var celda = nodo.closest("td, th");
      return celda && area.contains(celda) ? celda : null;
    }

    function tablaActual() {
      var celda = celdaDeSeleccion();
      return celda ? celda.closest("table") : null;
    }

    /** La celda que se está editando: la de la selección o la última que hubo. */
    function celdaActual(tabla) {
      var celda = celdaDeSeleccion();
      if (celda && (!tabla || celda.closest("table") === tabla)) {
        celdaRecordada = celda;
        return celda;
      }
      if (
        celdaRecordada &&
        area.contains(celdaRecordada) &&
        (!tabla || celdaRecordada.closest("table") === tabla)
      ) {
        return celdaRecordada;
      }
      return null;
    }

    /** La rejilla de la tabla: qué celda ocupa cada sitio, contando los spans. */
    function rejilla(tabla) {
      var mapa = {};
      filasDe(tabla).forEach(function (fila, f) {
        var columna = 0;
        Array.prototype.forEach.call(fila.children, function (celda) {
          while (mapa[f + ":" + columna]) {
            columna++;
          }
          var alto = Math.max(1, celda.rowSpan || 1);
          var ancho = Math.max(1, celda.colSpan || 1);
          for (var i = 0; i < alto; i++) {
            for (var j = 0; j < ancho; j++) {
              mapa[f + i + ":" + (columna + j)] = celda;
            }
          }
          columna += ancho;
        });
      });
      return mapa;
    }

    /** Dónde empieza una celda: su esquina de arriba a la izquierda. */
    function coordenadasDe(tabla, celda) {
      var mapa = rejilla(tabla);
      for (var clave in mapa) {
        if (mapa[clave] === celda) {
          var partes = clave.split(":");
          return { fila: parseInt(partes[0], 10), columna: parseInt(partes[1], 10) };
        }
      }
      return null;
    }

    /** Las celdas con su sitio, sin repetir las que ocupan varias. */
    function sitiosDe(tabla) {
      var mapa = rejilla(tabla);
      var salida = [];
      var vistos = [];
      for (var clave in mapa) {
        var celda = mapa[clave];
        if (vistos.indexOf(celda) !== -1) {
          continue;
        }
        vistos.push(celda);
        var partes = clave.split(":");
        salida.push({
          celda: celda,
          fila: parseInt(partes[0], 10),
          columna: parseInt(partes[1], 10),
        });
      }
      return salida;
    }

    /** El ancho de cada columna, en porcentaje de la tabla. */
    function anchosDe(tabla) {
      var total = tabla.getBoundingClientRect().width || 1;
      var mapa = rejilla(tabla);
      var ultima = 0;
      for (var clave in mapa) {
        var columna = parseInt(clave.split(":")[1], 10);
        if (columna > ultima) {
          ultima = columna;
        }
      }
      var anchos = [];
      for (var i = 0; i <= ultima; i++) {
        var celda = mapa["0:" + i];
        anchos.push(
          celda ? (celda.getBoundingClientRect().width / total) * 100 : 100 / (ultima + 1)
        );
      }
      return anchos;
    }

    /** El ancho se guarda en cada celda de la columna, en porcentaje. */
    function fijarAnchos(tabla, anchos) {
      sitiosDe(tabla).forEach(function (sitio) {
        var celda = sitio.celda;
        if ((celda.colSpan || 1) > 1) {
          celda.removeAttribute("width");
          return;
        }
        var ancho = anchos[sitio.columna];
        if (ancho) {
          celda.setAttribute("width", Math.round(ancho) + "%");
        }
      });
      ajustar();
    }

    function limpiarMarcas() {
      Array.prototype.forEach.call(
        area.querySelectorAll(".celda-elegida"),
        function (celda) {
          celda.classList.remove("celda-elegida");
          if (!celda.getAttribute("class")) {
            celda.removeAttribute("class");
          }
        }
      );
    }

    function marcarHasta(tabla, desde, hasta) {
      var mapa = rejilla(tabla);
      var a = coordenadasDe(tabla, desde);
      var b = coordenadasDe(tabla, hasta);
      if (!a || !b) {
        return;
      }
      limpiarMarcas();
      var f1 = Math.min(a.fila, b.fila);
      var f2 = Math.max(a.fila, b.fila);
      var c1 = Math.min(a.columna, b.columna);
      var c2 = Math.max(a.columna, b.columna);
      for (var f = f1; f <= f2; f++) {
        for (var c = c1; c <= c2; c++) {
          var celda = mapa[f + ":" + c];
          if (celda) {
            celda.classList.add("celda-elegida");
          }
        }
      }
      var seleccion = window.getSelection();
      if (seleccion && seleccion.removeAllRanges) {
        seleccion.removeAllRanges();
      }
      area.focus();
      actualizarBotones(tabla);
    }

    function tablaDeLasMarcas() {
      var marcada = area.querySelector(".celda-elegida");
      return marcada ? marcada.closest("table") : null;
    }

    /** Marca una lista de celdas; con `sumar` se añaden a lo ya marcado. */
    function marcarCeldas(tabla, celdas, sumar) {
      if (!sumar) {
        limpiarMarcas();
      }
      celdas.forEach(function (celda) {
        celda.classList.add("celda-elegida");
      });
      area.focus();
      actualizarBotones(tabla);
    }

    function celdasDeLaFila(tabla, fila) {
      var laFila = filasDe(tabla)[fila];
      return laFila ? Array.prototype.slice.call(laFila.children) : [];
    }

    function celdasDeLaColumna(tabla, columna) {
      var mapa = rejilla(tabla);
      var salida = [];
      filasDe(tabla).forEach(function (fila, f) {
        var celda = mapa[f + ":" + columna];
        if (celda && salida.indexOf(celda) === -1) {
          salida.push(celda);
        }
      });
      return salida;
    }

    /** La marca, si es un rectángulo completo: solo entonces se puede unir. */
    function esRectangulo(tabla) {
      var marcadas = Array.prototype.slice.call(
        tabla.querySelectorAll(".celda-elegida")
      );
      if (marcadas.length < 2) {
        return false;
      }
      var filas = [];
      var columnas = [];
      marcadas.forEach(function (celda) {
        var sitio = coordenadasDe(tabla, celda);
        if (sitio) {
          filas.push(sitio.fila);
          columnas.push(sitio.columna);
        }
      });
      if (!filas.length) {
        return false;
      }
      var f1 = Math.min.apply(null, filas);
      var f2 = Math.max.apply(null, filas);
      var c1 = Math.min.apply(null, columnas);
      var c2 = Math.max.apply(null, columnas);
      var mapa = rejilla(tabla);
      var dentro = [];
      for (var f = f1; f <= f2; f++) {
        for (var c = c1; c <= c2; c++) {
          var celda = mapa[f + ":" + c];
          if (celda && dentro.indexOf(celda) === -1) {
            dentro.push(celda);
          }
        }
      }
      if (dentro.length !== marcadas.length) {
        return false;
      }
      return marcadas.every(function (celda) {
        return dentro.indexOf(celda) !== -1;
      });
    }

    function actualizarBotones(tabla) {
      if (!barraTabla) {
        return;
      }
      if (!tabla) {
        tabla = tablaDeLasMarcas();
      }
      var unir = barraTabla.querySelector('[data-tabla="unir"]');
      var dividir = barraTabla.querySelector('[data-tabla="dividir"]');
      var campoAncho = barraTabla.querySelector("[data-ancho]");
      var cuantas = barraTabla.querySelector("[data-cuenta-celdas]");
      var marcadas = tabla ? tabla.querySelectorAll(".celda-elegida").length : 0;
      if (unir) {
        unir.disabled = !tabla || !esRectangulo(tabla);
      }
      if (cuantas) {
        cuantas.hidden = marcadas < 1;
        cuantas.textContent = marcadas === 1 ? "1 celda" : marcadas + " celdas";
      }
      var celda = tabla ? celdaActual(tabla) : null;
      if (dividir) {
        var partida =
          celda && ((celda.rowSpan || 1) > 1 || (celda.colSpan || 1) > 1);
        dividir.disabled = !partida;
      }
      if (campoAncho) {
        var sitio = tabla && celda ? coordenadasDe(tabla, celda) : null;
        campoAncho.disabled = !sitio;
        if (sitio) {
          campoAncho.value = Math.round(anchosDe(tabla)[sitio.columna]);
          campoAncho.setAttribute("data-columna", sitio.columna);
        } else {
          campoAncho.value = "";
        }
      }
    }

    function mirarTabla() {
      if (!barraTabla) {
        return;
      }
      var tabla = tablaActual() || tablaDeLasMarcas();
      barraTabla.hidden = !tabla;
      caja.classList.toggle("con-tabla", !!tabla);
      actualizarBotones(tabla);
    }

    function filasDe(tabla) {
      return Array.prototype.slice.call(tabla.querySelectorAll("tr"));
    }

    function celdaVacia(modelo) {
      var celda = document.createElement(modelo && modelo.tagName === "TH" ? "th" : "td");
      celda.innerHTML = "<br>";
      return celda;
    }

    /** Dónde está el cursor dentro de la tabla (o la esquina si no hay celda). */
    function sitioDelCursor(tabla) {
      var celda = celdaActual(tabla);
      var sitio = celda ? coordenadasDe(tabla, celda) : null;
      if (sitio) {
        return sitio;
      }
      var mapa = rejilla(tabla);
      var filas = 0;
      var columnas = 0;
      for (var clave in mapa) {
        var partes = clave.split(":");
        filas = Math.max(filas, parseInt(partes[0], 10));
        columnas = Math.max(columnas, parseInt(partes[1], 10));
      }
      return { fila: filas, columna: columnas };
    }

    /** La fila de abajo del cursor, con las mismas celdas que la suya. */
    function anadirFila(tabla) {
      var sitio = sitioDelCursor(tabla);
      var filas = filasDe(tabla);
      var modelo = filas[sitio.fila] || filas[filas.length - 1];
      var nueva = document.createElement("tr");
      var cuantas = modelo ? modelo.children.length : 1;
      for (var i = 0; i < cuantas; i++) {
        nueva.appendChild(celdaVacia(modelo ? modelo.children[i] : null));
      }
      if (modelo && modelo.parentNode) {
        modelo.parentNode.insertBefore(nueva, modelo.nextSibling);
      } else {
        var cuerpo = tabla.tBodies[tabla.tBodies.length - 1];
        if (!cuerpo) {
          cuerpo = document.createElement("tbody");
          tabla.appendChild(cuerpo);
        }
        cuerpo.appendChild(nueva);
      }
      var primera = nueva.querySelector("td, th");
      if (primera) {
        colocarEn(primera);
      }
    }

    /** Una columna nueva a la derecha de la del cursor. */
    function anadirColumna(tabla) {
      var sitio = sitioDelCursor(tabla);
      var mapa = rejilla(tabla);
      var vistas = [];
      filasDe(tabla).forEach(function (fila, f) {
        var celda = mapa[f + ":" + sitio.columna] || fila.children[fila.children.length - 1];
        if (!celda || vistas.indexOf(celda) !== -1) {
          return;
        }
        vistas.push(celda);
        celda.parentNode.insertBefore(celdaVacia(celda), celda.nextSibling);
      });
    }

    /** Se lleva la fila del cursor. */
    function quitarFila(tabla) {
      var sitio = sitioDelCursor(tabla);
      var filas = filasDe(tabla);
      var fila = filas[sitio.fila];
      if (!fila) {
        return;
      }
      fila.parentNode.removeChild(fila);
      if (!filasDe(tabla).length) {
        quitarTabla(tabla);
        return;
      }
      var donde = filasDe(tabla)[Math.min(sitio.fila, filasDe(tabla).length - 1)];
      var primera = donde ? donde.querySelector("td, th") : null;
      if (primera) {
        colocarEn(primera);
      }
      mirarTabla();
    }

    /** Se lleva la columna del cursor en todas las filas. */
    function quitarColumna(tabla) {
      var sitio = sitioDelCursor(tabla);
      var mapa = rejilla(tabla);
      var vistas = [];
      var columnas = 0;
      for (var clave in mapa) {
        columnas = Math.max(columnas, parseInt(clave.split(":")[1], 10) + 1);
      }
      if (columnas <= 1) {
        quitarTabla(tabla);
        return;
      }
      filasDe(tabla).forEach(function (fila, f) {
        var celda = mapa[f + ":" + sitio.columna];
        if (!celda || vistas.indexOf(celda) !== -1) {
          return;
        }
        vistas.push(celda);
        if ((celda.colSpan || 1) > 1) {
          // Una celda unida que abarca la columna: se encoge en vez de irse.
          celda.colSpan = celda.colSpan - 1;
        } else {
          celda.parentNode.removeChild(celda);
        }
      });
      // Una fila que se quedó sin celdas se va con la columna.
      filasDe(tabla).forEach(function (fila) {
        if (!fila.children.length) {
          fila.parentNode.removeChild(fila);
        }
      });
      if (!filasDe(tabla).length) {
        quitarTabla(tabla);
        return;
      }
      var despues = rejilla(tabla);
      var destino =
        despues[sitio.fila + ":" + Math.min(sitio.columna, columnas - 2)] ||
        despues["0:0"];
      if (destino) {
        colocarEn(destino);
      }
      mirarTabla();
    }

    /** Une en una sola las celdas marcadas con Mayúsculas y clic. */
    function unirCeldas(tabla) {
      var marcadas = Array.prototype.slice.call(
        tabla.querySelectorAll(".celda-elegida")
      );
      if (marcadas.length < 2) {
        return;
      }
      var mapa = rejilla(tabla);
      var filas = [];
      var columnas = [];
      marcadas.forEach(function (celda) {
        var sitio = coordenadasDe(tabla, celda);
        if (sitio) {
          filas.push(sitio.fila);
          columnas.push(sitio.columna);
        }
      });
      if (!filas.length) {
        return;
      }
      var f1 = Math.min.apply(null, filas);
      var f2 = Math.max.apply(null, filas);
      var c1 = Math.min.apply(null, columnas);
      var c2 = Math.max.apply(null, columnas);
      var dentro = [];
      for (var f = f1; f <= f2; f++) {
        for (var c = c1; c <= c2; c++) {
          var celda = mapa[f + ":" + c];
          if (celda && dentro.indexOf(celda) === -1) {
            dentro.push(celda);
          }
        }
      }
      if (dentro.length < 2) {
        return;
      }
      var destino = mapa[f1 + ":" + c1] || dentro[0];
      // Lo que había escrito en cada una se queda en la de arriba a la izquierda.
      var trozos = [];
      dentro.forEach(function (celda) {
        var texto = (celda.textContent || "").trim();
        if (texto) {
          trozos.push(texto);
        }
      });
      var unico = [];
      trozos.forEach(function (texto) {
        if (unico.indexOf(texto) === -1) {
          unico.push(texto);
        }
      });
      destino.innerHTML = unico.length ? unico.join("<br>") : "<br>";
      dentro.forEach(function (celda) {
        if (celda !== destino && celda.parentNode) {
          celda.parentNode.removeChild(celda);
        }
      });
      var ancho = c2 - c1 + 1;
      var alto = f2 - f1 + 1;
      if (ancho > 1) {
        destino.colSpan = ancho;
      } else {
        destino.removeAttribute("colspan");
      }
      if (alto > 1) {
        destino.rowSpan = alto;
      } else {
        destino.removeAttribute("rowspan");
      }
      limpiarMarcas();
      colocarEn(destino);
      guardar();
      ajustar();
      mirarTabla();
      anotarYa();
    }

    /** Parte una celda unida y devuelve el hueco que ocupaba. */
    function dividirCelda(tabla) {
      var celda = celdaActual(tabla);
      if (!celda) {
        return;
      }
      var alto = Math.max(1, celda.rowSpan || 1);
      var ancho = Math.max(1, celda.colSpan || 1);
      if (alto === 1 && ancho === 1) {
        return;
      }
      var sitio = coordenadasDe(tabla, celda);
      if (!sitio) {
        return;
      }
      var fila = celda.parentNode;
      celda.removeAttribute("rowspan");
      celda.removeAttribute("colspan");
      var siguiente = celda.nextSibling;
      for (var j = 1; j < ancho; j++) {
        fila.insertBefore(celdaVacia(celda), siguiente);
      }
      var filas = filasDe(tabla);
      for (var i = 1; i < alto; i++) {
        var otra = filas[sitio.fila + i];
        if (!otra) {
          continue;
        }
        var antes = otra.children[sitio.columna] || null;
        for (var k = 0; k < ancho; k++) {
          otra.insertBefore(celdaVacia(celda), antes);
        }
      }
      limpiarMarcas();
      colocarEn(celda);
      guardar();
      ajustar();
      mirarTabla();
      anotarYa();
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
      // Sin esto, pulsar un botón se lleva la selección y se pierde la celda.
      barraTabla.addEventListener("mousedown", function (evento) {
        if (evento.target.closest("[data-ancho]")) {
          return;
        }
        evento.preventDefault();
      });

      var campoAncho = barraTabla.querySelector("[data-ancho]");
      if (campoAncho) {
        campoAncho.addEventListener("change", function () {
          var tabla = tablaActual() || tablaDeLasMarcas();
          var celda = tabla ? celdaActual(tabla) : null;
          var sitio = tabla && celda ? coordenadasDe(tabla, celda) : null;
          var valor = parseFloat(campoAncho.value);
          if (!sitio || !valor) {
            return;
          }
          var anchos = anchosDe(tabla);
          var nuevos = anchos.slice();
          var deseado = Math.min(90, Math.max(5, valor));
          var delta = deseado - anchos[sitio.columna];
          nuevos[sitio.columna] = deseado;
          if (sitio.columna + 1 < nuevos.length) {
            nuevos[sitio.columna + 1] = Math.max(5, anchos[sitio.columna + 1] - delta);
          }
          fijarAnchos(tabla, nuevos);
          guardar();
          anotarYa();
        });
      }
      barraTabla.addEventListener("click", function (evento) {
        var boton = evento.target.closest("[data-tabla]");
        if (!boton) {
          return;
        }
        evento.preventDefault();
        var tabla = tablaActual() || tablaDeLasMarcas();
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
        } else if (que === "marcar-fila" || que === "marcar-columna") {
          var sitio = sitioDelCursor(tabla);
          var sumar = evento.ctrlKey || evento.metaKey;
          var celdas =
            que === "marcar-fila"
              ? celdasDeLaFila(tabla, sitio.fila)
              : celdasDeLaColumna(tabla, sitio.columna);
          marcarCeldas(tabla, celdas, sumar);
          return;
        } else if (que === "unir") {
          unirCeldas(tabla);
          return;
        } else if (que === "dividir") {
          dividirCelda(tabla);
          return;
        } else if (que === "quitar") {
          quitarTabla(tabla);
        }
        guardar();
        ajustar();
        mirarTabla();
        anotarYa();
      });
    }

    /* Escritura, pegado y salida: el campo oculto va siempre al día. */
    area.addEventListener("input", function () {
      guardar();
      ajustar();
      mirarTabla();
      anotarPronto();
    });
    area.addEventListener("blur", guardar);
    area.addEventListener("keyup", mirarTabla);
    area.addEventListener("click", mirarTabla);

    /* Marcar varias celdas para unirlas: con Mayúsculas y clic, o arrastrando
       por encima de ellas. */
    function celdaDelEvento(evento) {
      var nodo = evento.target;
      if (nodo && nodo.nodeType === 3) {
        nodo = nodo.parentNode;
      }
      var celda = nodo && nodo.closest ? nodo.closest("td, th") : null;
      return celda && area.contains(celda) ? celda : null;
    }

    //: Cuando se está estirando una columna, para no mirar el cursor.
    var estirando = false;

    function bordeDeColumna(evento) {
      var celda = celdaDelEvento(evento);
      if (!celda) {
        return null;
      }
      var caja = celda.getBoundingClientRect();
      if (evento.clientX < caja.right - 6) {
        return null;
      }
      var tabla = celda.closest("table");
      var sitio = coordenadasDe(tabla, celda);
      return sitio ? { tabla: tabla, columna: sitio.columna } : null;
    }

    function estirarColumna(borde, evento) {
      var base = anchosDe(borde.tabla);
      var anchoTabla = borde.tabla.getBoundingClientRect().width || 1;
      var inicioX = evento.clientX;
      var columna = borde.columna;
      var vecina = columna + 1 < base.length ? columna + 1 : -1;

      function mover(desplazamiento) {
        var delta = ((desplazamiento.clientX - inicioX) / anchoTabla) * 100;
        var deseado = Math.min(90, Math.max(5, base[columna] + delta));
        var nuevos = base.slice();
        if (vecina >= 0) {
          var resto = base[vecina] - (deseado - base[columna]);
          if (resto < 5) {
            deseado = base[columna] + (base[vecina] - 5);
            resto = 5;
          }
          nuevos[vecina] = resto;
        }
        nuevos[columna] = deseado;
        fijarAnchos(borde.tabla, nuevos);
      }

      function soltar() {
        document.removeEventListener("mousemove", mover);
        document.removeEventListener("mouseup", soltar);
        estirando = false;
        area.style.cursor = "";
        guardar();
        anotarYa();
      }

      estirando = true;
      area.style.cursor = "col-resize";
      document.addEventListener("mousemove", mover);
      document.addEventListener("mouseup", soltar);
    }

    area.addEventListener("mousemove", function (evento) {
      if (estirando) {
        return;
      }
      area.style.cursor = bordeDeColumna(evento) ? "col-resize" : "";
    });

    area.addEventListener("mousedown", function (evento) {
      var borde = bordeDeColumna(evento);
      if (borde) {
        evento.preventDefault();
        estirarColumna(borde, evento);
        return;
      }
      var celda = celdaDelEvento(evento);
      if (!celda) {
        marcando = null;
        limpiarMarcas();
        return;
      }
      if (evento.shiftKey) {
        evento.preventDefault();
        var tabla = celda.closest("table");
        marcarHasta(tabla, celdaRecordada || celda, celda);
        marcando = null;
        return;
      }
      if (evento.ctrlKey || evento.metaKey) {
        /* Selección libre: con Ctrl, una celda del cuerpo entra o sale de la
           marca, y una de la cabecera mete o saca su columna entera. */
        evento.preventDefault();
        var suya = celda.closest("table");
        var enCabecera =
          celda.tagName === "TH" && celda.parentNode.parentNode.tagName === "THEAD";
        var grupo = enCabecera
          ? celdasDeLaColumna(suya, (coordenadasDe(suya, celda) || {}).columna)
          : [celda];
        var todas = grupo.every(function (otra) {
          return otra.classList.contains("celda-elegida");
        });
        grupo.forEach(function (otra) {
          if (todas) {
            otra.classList.remove("celda-elegida");
          } else {
            otra.classList.add("celda-elegida");
          }
          if (!otra.getAttribute("class")) {
            otra.removeAttribute("class");
          }
        });
        celdaRecordada = celda;
        area.focus();
        actualizarBotones(suya);
        return;
      }
      marcando = celda;
      celdaRecordada = celda;
      limpiarMarcas();
    });

    area.addEventListener("mouseup", function () {
      marcando = null;
      mirarTabla();
    });

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

    /** Las celdas marcadas, como una tabla aparte lista para copiar. */
    function regionMarcada(tabla) {
      var marcadas = Array.prototype.slice.call(
        tabla.querySelectorAll(".celda-elegida")
      );
      if (!marcadas.length) {
        return null;
      }
      var mapa = rejilla(tabla);
      var filas = [];
      var columnas = [];
      marcadas.forEach(function (celda) {
        var sitio = coordenadasDe(tabla, celda);
        if (sitio) {
          filas.push(sitio.fila);
          columnas.push(sitio.columna);
        }
      });
      if (!filas.length) {
        return null;
      }
      var f1 = Math.min.apply(null, filas);
      var f2 = Math.max.apply(null, filas);
      // Solo las columnas marcadas, en su orden: así se llevan columnas sueltas.
      var elegidas = columnas
        .filter(function (valor, indice) {
          return columnas.indexOf(valor) === indice;
        })
        .sort(function (a, b) {
          return a - b;
        });
      var salida = document.createElement("table");
      var cuerpo = document.createElement("tbody");
      var plano = [];
      for (var f = f1; f <= f2; f++) {
        var fila = document.createElement("tr");
        var linea = [];
        for (var i = 0; i < elegidas.length; i++) {
          var celda = mapa[f + ":" + elegidas[i]];
          var vale = celda && marcadas.indexOf(celda) !== -1;
          var nueva = document.createElement("td");
          nueva.innerHTML = vale ? celda.innerHTML : "<br>";
          fila.appendChild(nueva);
          linea.push(
            (vale ? celda.textContent : "").replace(/\s+/g, " ").trim()
          );
        }
        cuerpo.appendChild(fila);
        plano.push(linea.join("\t"));
      }
      salida.appendChild(cuerpo);
      return { html: salida.outerHTML, texto: plano.join("\n"), celdas: marcadas };
    }

    function ponerEnElPortapapeles(region, cortar) {
      var alCopiar = function (evento) {
        if (!evento.clipboardData) {
          return;
        }
        evento.clipboardData.setData("text/html", region.html);
        evento.clipboardData.setData("text/plain", region.texto);
        evento.preventDefault();
      };
      document.addEventListener("copy", alCopiar, true);
      try {
        document.execCommand("copy");
      } catch (fallo) {
        // Un navegador que no deje copiar: el usuario siempre puede seleccionar
        // el texto y usar su menú.
      }
      document.removeEventListener("copy", alCopiar, true);
      if (cortar) {
        region.celdas.forEach(function (celda) {
          celda.innerHTML = "<br>";
        });
        limpiarMarcas();
        guardar();
        ajustar();
        mirarTabla();
        anotarYa();
      }
    }

    area.addEventListener("copy", function (evento) {
      var tabla = tablaDeLasMarcas();
      var region = tabla ? regionMarcada(tabla) : null;
      if (!region || !evento.clipboardData) {
        return;
      }
      evento.clipboardData.setData("text/html", region.html);
      evento.clipboardData.setData("text/plain", region.texto);
      evento.preventDefault();
    });

    area.addEventListener("cut", function (evento) {
      var tabla = tablaDeLasMarcas();
      var region = tabla ? regionMarcada(tabla) : null;
      if (!region || !evento.clipboardData) {
        return;
      }
      evento.clipboardData.setData("text/html", region.html);
      evento.clipboardData.setData("text/plain", region.texto);
      evento.preventDefault();
      // Lo cortado se va de la tabla, que es lo que se espera de un cortar.
      region.celdas.forEach(function (celda) {
        celda.innerHTML = "<br>";
      });
      limpiarMarcas();
      guardar();
      ajustar();
      mirarTabla();
    });

    /* Pegar una tabla —o una lista copiada de Excel— con el cursor en una celda
       la reparte por las celdas, como en una hoja de cálculo. Si lo pegado no
       cabe, la tabla crece. */
    function escaparHtml(texto) {
      var caja = document.createElement("div");
      caja.textContent = texto;
      return caja.innerHTML;
    }

    function matrizDePegado(html, texto) {
      var documento = null;
      if (html) {
        documento = new DOMParser().parseFromString(html, "text/html");
        var tabla = documento.querySelector("table");
        if (tabla) {
          return filasDe(tabla).map(function (fila) {
            return Array.prototype.map.call(fila.children, function (celda) {
              return (celda.textContent || "").replace(/\s+/g, " ").trim();
            });
          });
        }
      }
      var plano = (texto || "").replace(/\r\n?/g, "\n");
      var sinFinal = plano.replace(/\n+$/, "");
      if (!/[\t\n]/.test(sinFinal)) {
        return null;
      }
      return sinFinal.split("\n").map(function (linea) {
        return linea.split("\t");
      });
    }

    function fraseDePegado(html) {
      // Una tabla perdida en el HTML, que no venga de una celda.
      return /<\s*table\b/i.test(html || "");
    }

    function volcarMatriz(tabla, celda, matriz) {
      var sitio = coordenadasDe(tabla, celda);
      if (!sitio) {
        return;
      }
      var ancho = 0;
      matriz.forEach(function (fila) {
        ancho = Math.max(ancho, fila.length);
      });
      var cuerpo = tabla.tBodies[tabla.tBodies.length - 1];
      if (!cuerpo) {
        cuerpo = document.createElement("tbody");
        tabla.appendChild(cuerpo);
      }
      // Las filas que falten.
      var filas = filasDe(tabla);
      while (filas.length < sitio.fila + matriz.length) {
        var modelo = filas[filas.length - 1];
        var nueva = document.createElement("tr");
        var cuantas = Math.max(modelo ? modelo.children.length : 0, ancho);
        for (var i = 0; i < cuantas; i++) {
          nueva.appendChild(celdaVacia(modelo ? modelo.children[i] : null));
        }
        cuerpo.appendChild(nueva);
        filas.push(nueva);
      }
      // Las columnas que falten, en todas las filas.
      var mapa = rejilla(tabla);
      var ultima = 0;
      for (var clave in mapa) {
        ultima = Math.max(ultima, parseInt(clave.split(":")[1], 10));
      }
      var necesarias = sitio.columna + ancho - 1;
      if (necesarias > ultima) {
        filas.forEach(function (fila) {
          for (var c = ultima + 1; c <= necesarias; c++) {
            fila.appendChild(celdaVacia(fila.children[fila.children.length - 1]));
          }
        });
      }
      // Y los datos, cada uno en su celda.
      mapa = rejilla(tabla);
      matriz.forEach(function (datos, i) {
        datos.forEach(function (valor, j) {
          var destino = mapa[sitio.fila + i + ":" + (sitio.columna + j)];
          if (!destino) {
            return;
          }
          if (destino.querySelector("table")) {
            return;
          }
          destino.innerHTML = valor ? escaparHtml(valor) : "<br>";
        });
      });
      colocarEn(mapa[sitio.fila + ":" + sitio.columna] || celda);
      guardar();
      ajustar();
      mirarTabla();
      anotarYa();
    }

    // Pegar desde una web trae estilos y guiones: se queda el texto con su
    // formato básico y nada más. Dentro de una tabla, los datos se reparten.
    area.addEventListener("paste", function (evento) {
      var datos = evento.clipboardData || window.clipboardData;
      if (!datos) {
        return;
      }
      var html = datos.getData("text/html");
      var texto = datos.getData("text/plain");
      var tabla = tablaActual();
      if (tabla) {
        var celda = celdaActual(tabla);
        var matriz = matrizDePegado(html, texto);
        var esTabla = fraseDePegado(html);
        if (celda && matriz && (esTabla || matriz.length > 1 || matriz[0].length > 1)) {
          evento.preventDefault();
          volcarMatriz(tabla, celda, matriz);
          return;
        }
      }
      if (!html) {
        return;
      }
      evento.preventDefault();
      // Sin el texto plano de reserva, un HTML raro dejaría el área vacía.
      ejecutar("insertHTML", limpiarPegado(html) || texto);
    });

    // Con una tabla dentro, el tabulador pasa a la celda siguiente: escribir una
    // tabla deja de ser pelear con el ratón.
    area.addEventListener("keydown", function (evento) {
      // Los atajos de siempre: deshacer, rehacer y copiar o cortar lo marcado.
      if ((evento.ctrlKey || evento.metaKey) && !evento.altKey) {
        var tecla = (evento.key || "").toLowerCase();
        if (tecla === "z") {
          evento.preventDefault();
          if (evento.shiftKey) {
            rehacer();
          } else {
            deshacer();
          }
          return;
        }
        if (tecla === "y") {
          evento.preventDefault();
          rehacer();
          return;
        }
        if (tecla === "c" || tecla === "x") {
          var conMarcas = tablaDeLasMarcas();
          var region = conMarcas ? regionMarcada(conMarcas) : null;
          if (region) {
            evento.preventDefault();
            ponerEnElPortapapeles(region, tecla === "x");
            return;
          }
        }
      }
      if (evento.key === "Delete" || evento.key === "Backspace") {
        var conMarcas = tablaDeLasMarcas();
        if (conMarcas) {
          evento.preventDefault();
          Array.prototype.forEach.call(
            conMarcas.querySelectorAll(".celda-elegida"),
            function (celda) {
              celda.innerHTML = "<br>";
            }
          );
          limpiarMarcas();
          guardar();
          ajustar();
          mirarTabla();
          anotarYa();
          return;
        }
      }
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
