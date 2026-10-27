/* El editor de la descripción larga de la tienda.
 *
 * Pone una barra de botones encima del campo y escribe la marca de Markdown
 * alrededor de lo que esté seleccionado. No trae ninguna librería: la descripción
 * se convierte a HTML en el servidor (`tienda/texto.py`), así que aquí solo hace
 * falta saber dónde va cada marca.
 *
 * Se engancha solo a los campos con `data-editor-markdown`.
 */
(function () {
  "use strict";

  var NEGRITA = { etiqueta: "B", titulo: "Negrita", estilo: "fuerte" };
  var CURSIVA = { etiqueta: "I", titulo: "Cursiva", estilo: "cursiva" };

  var BOTONES = [
    { texto: NEGRITA.etiqueta, titulo: NEGRITA.titulo, clase: NEGRITA.estilo,
      antes: "**", despues: "**", ejemplo: "texto" },
    { texto: CURSIVA.etiqueta, titulo: CURSIVA.titulo, clase: CURSIVA.estilo,
      antes: "*", despues: "*", ejemplo: "texto" },
    { texto: "H", titulo: "Título", clase: "titulo",
      linea: "## ", ejemplo: "Título de la sección" },
    { texto: "•", titulo: "Lista con viñetas", clase: "",
      linea: "- ", ejemplo: "Primer punto\n- Segundo punto" },
    { texto: "1.", titulo: "Lista numerada", clase: "",
      linea: "1. ", ejemplo: "Primer paso\n2. Segundo paso" },
    { texto: "▦ Tabla", titulo: "Tabla: se arma en una cuadrícula", clase: "tabla", tabla: true },
    { texto: "🔗", titulo: "Enlace", clase: "",
      antes: "[", despues: "](https://)", ejemplo: "el texto del enlace" },
    { texto: "❝", titulo: "Cita", clase: "", linea: "> ", ejemplo: "Una nota al margen" },
    { texto: "</>", titulo: "Código", clase: "", antes: "`", despues: "`", ejemplo: "código" },
    { texto: "―", titulo: "Separador", clase: "", plantilla: "\n---\n" }
  ];

  var GUIA = [
    ["**negrita**", "texto en negrita"],
    ["*cursiva*", "texto en cursiva"],
    ["## Título", "un título de sección"],
    ["- punto", "lista con viñetas"],
    ["1. paso", "lista numerada"],
    ["▦ Tabla", "una tabla, armada en una cuadrícula"],
    ["[texto](https://…)", "un enlace"],
    ["> nota", "una cita"],
    ["`código`", "código en línea"]
  ];

  function seleccion(campo) {
    return {
      inicio: campo.selectionStart,
      fin: campo.selectionEnd,
      texto: campo.value.slice(campo.selectionStart, campo.selectionEnd)
    };
  }

  function escribir(campo, texto, inicio, fin) {
    var valor = campo.value;
    campo.value = valor.slice(0, inicio) + texto + valor.slice(fin);
    campo.selectionStart = campo.selectionEnd = inicio + texto.length;
    campo.focus();
    campo.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function envolver(campo, boton) {
    var parte = seleccion(campo);
    var cuerpo = parte.texto || boton.ejemplo || "";
    var texto = boton.antes + cuerpo + boton.despues;
    escribir(campo, texto, parte.inicio, parte.fin);
    if (!parte.texto) {
      campo.selectionStart = parte.inicio + boton.antes.length;
      campo.selectionEnd = campo.selectionStart + cuerpo.length;
    }
  }

  function porLineas(campo, boton) {
    var parte = seleccion(campo);
    var valor = campo.value;
    var desde = valor.lastIndexOf("\n", parte.inicio - 1) + 1;
    var hasta = valor.indexOf("\n", parte.fin);
    if (hasta === -1) {
      hasta = valor.length;
    }
    var bloque = valor.slice(desde, hasta) || boton.ejemplo || "";
    var lineas = bloque.split("\n").map(function (linea, indice) {
      if (boton.linea === "1. ") {
        return indice + 1 + ". " + linea.replace(/^\s*\d+\.\s*/, "");
      }
      return boton.linea + linea;
    });
    escribir(campo, lineas.join("\n"), desde, hasta);
  }

  function insertarPlantilla(campo, boton) {
    var parte = seleccion(campo);
    var antes = campo.value.slice(0, parte.inicio);
    var salto = antes && !/\n$/.test(antes) ? "\n" : "";
    escribir(campo, salto + boton.plantilla, parte.inicio, parte.fin);
  }

  /* --------------------------------------------------------------- las tablas
   *
   * Una tabla en Markdown son barras y una segunda línea de guiones: pedirle eso
   * a quien factura no tiene sentido. El botón de la tabla abre una cuadrícula
   * donde se escribe como en una hoja de cálculo, y aquí se pasa a Markdown. Si
   * el cursor estaba dentro de una tabla, la carga para retocarla.
   */

  var TABLA_COLUMNAS = 8;   // la rejilla de tamaños que se ve al pasar el ratón
  var TABLA_FILAS = 6;
  var MAX_COLUMNAS = 12;    // lo que aguanta la tabla de verdad
  var MAX_FILAS = 100;
  var SEPARADORA = /^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$/;
  var HUECO = "\u0000";

  function celdasDe(linea) {
    var texto = linea.trim();
    if (texto.charAt(0) === "|") {
      texto = texto.slice(1);
    }
    if (texto.charAt(texto.length - 1) === "|") {
      texto = texto.slice(0, -1);
    }
    return texto.replace(/\\\|/g, HUECO).split("|").map(function (celda) {
      return celda.replace(new RegExp(HUECO, "g"), "|").trim();
    });
  }

  function aMarkdown(datos) {
    var columnas = 1;
    datos.forEach(function (fila) {
      columnas = Math.max(columnas, fila.length);
    });
    var normal = datos.map(function (fila) {
      var copia = fila.slice(0, columnas);
      while (copia.length < columnas) {
        copia.push("");
      }
      return copia.map(function (celda) {
        return String(celda).replace(/\|/g, "\\|").replace(/\n/g, " ").trim();
      });
    });
    if (!normal.length) {
      normal = [[""]];
    }
    var cuerpo = normal.slice(1);
    // Las filas de relleno que quedan vacías al final no se escriben.
    while (cuerpo.length && cuerpo[cuerpo.length - 1].every(function (celda) { return celda === ""; })) {
      cuerpo.pop();
    }
    var salida = ["| " + normal[0].join(" | ") + " |"];
    salida.push("| " + normal[0].map(function () { return "---"; }).join(" | ") + " |");
    cuerpo.forEach(function (fila) {
      salida.push("| " + fila.join(" | ") + " |");
    });
    return salida.join("\n") + "\n";
  }

  function tablaEnCursor(campo) {
    var valor = campo.value;
    var posicion = campo.selectionStart;
    var desde = valor.lastIndexOf("\n", posicion - 1) + 1;
    var hasta = valor.indexOf("\n", posicion);
    if (hasta === -1) {
      hasta = valor.length;
    }
    if (valor.slice(desde, hasta).indexOf("|") === -1) {
      return null;
    }

    while (desde > 0) {
      var anterior = valor.lastIndexOf("\n", desde - 2) + 1;
      if (valor.slice(anterior, desde - 1).indexOf("|") === -1) {
        break;
      }
      desde = anterior;
    }
    while (hasta < valor.length) {
      var siguiente = valor.indexOf("\n", hasta + 1);
      var fin = siguiente === -1 ? valor.length : siguiente;
      if (valor.slice(hasta + 1, fin).indexOf("|") === -1) {
        break;
      }
      hasta = fin;
    }

    var lineas = valor.slice(desde, hasta).split("\n").filter(function (linea) {
      return linea.trim() !== "";
    });
    if (lineas.length < 2 || !SEPARADORA.test(lineas[1])) {
      return null;
    }
    return {
      desde: desde,
      hasta: hasta,
      datos: [celdasDe(lineas[0])].concat(lineas.slice(2).map(celdasDe))
    };
  }

  function insertarTabla(campo, markdown, desde, hasta) {
    var valor = campo.value;
    var antes = valor.slice(0, desde);
    var despues = valor.slice(hasta);
    var previo = antes && !/\n$/.test(antes) ? "\n\n" : "";
    var posterior = despues && !/^\n/.test(despues) ? "\n" : "";
    escribir(campo, previo + markdown + posterior, desde, hasta);
  }

  /* Los datos que se pegan desde una hoja de cálculo: columnas separadas por
   * tabuladores (lo que copia Excel) o, si no, por punto y coma o coma. */
  function datosPegados(texto) {
    var lineas = texto.replace(/\r/g, "").split("\n").filter(function (linea) {
      return linea.trim() !== "";
    });
    if (!lineas.length) {
      return [];
    }
    if (lineas[0].indexOf("|") !== -1) {
      return lineas.filter(function (linea) {
        return !SEPARADORA.test(linea);
      }).map(celdasDe);
    }
    var separador = "\t";
    if (lineas[0].indexOf("\t") === -1) {
      separador = lineas[0].indexOf(";") !== -1 ? ";" : (lineas[0].indexOf(",") !== -1 ? "," : null);
    }
    return lineas.map(function (linea) {
      if (separador === null) {
        return [linea.trim()];
      }
      return linea.split(separador).map(function (celda) {
        return celda.trim();
      });
    });
  }

  function plural(cantidad, uno, varios) {
    return cantidad + " " + (cantidad === 1 ? uno : varios);
  }

  function crearDialogoTabla(doc, campo) {
    var dlg = doc.createElement("dialog");
    dlg.className = "editor-tabla";
    dlg.setAttribute("aria-label", "Tabla de la descripción");

    var caja = doc.createElement("div");
    caja.className = "editor-tabla-caja";
    dlg.appendChild(caja);

    var cabecera = doc.createElement("div");
    cabecera.className = "editor-tabla-cabecera";
    var titulo = doc.createElement("h2");
    titulo.className = "editor-tabla-titulo";
    cabecera.appendChild(titulo);
    var cerrar = doc.createElement("button");
    cerrar.type = "button";
    cerrar.className = "editor-tabla-cerrar";
    cerrar.textContent = "×";
    cerrar.setAttribute("aria-label", "Cerrar");
    cerrar.addEventListener("click", function () { dlg.close(); });
    cabecera.appendChild(cerrar);
    caja.appendChild(cabecera);

    var ayuda = doc.createElement("p");
    ayuda.className = "editor-tabla-ayuda";
    ayuda.textContent = "Elija el tamaño y escriba en las celdas. La primera fila es el encabezado.";
    caja.appendChild(ayuda);

    // Dos columnas: el tamaño a la izquierda, la tabla a la derecha. Si no, con
    // dos columnas de datos todo quedaba apilado a un lado del diálogo.
    var cuerpo = doc.createElement("div");
    cuerpo.className = "editor-tabla-cuerpo";
    caja.appendChild(cuerpo);

    var lateral = doc.createElement("div");
    lateral.className = "editor-tabla-lateral";
    cuerpo.appendChild(lateral);

    var principal = doc.createElement("div");
    principal.className = "editor-tabla-principal";
    cuerpo.appendChild(principal);

    var rapida = doc.createElement("div");
    rapida.className = "editor-tabla-rapida";
    rapida.setAttribute("role", "group");
    rapida.setAttribute("aria-label", "Tamaño de la tabla");
    var celdas = [];
    for (var f = 0; f < TABLA_FILAS; f++) {
      for (var c = 0; c < TABLA_COLUMNAS; c++) {
        var celda = doc.createElement("button");
        celda.type = "button";
        celda.className = "editor-tabla-rapida-celda";
        celda.dataset.fila = f + 1;
        celda.dataset.columna = c + 1;
        celda.setAttribute("aria-label", plural(c + 1, "columna", "columnas") + " × " + plural(f + 1, "fila", "filas"));
        rapida.appendChild(celda);
        celdas.push(celda);
      }
    }
    lateral.appendChild(rapida);

    var medida = doc.createElement("p");
    medida.className = "editor-tabla-medida";
    medida.setAttribute("aria-live", "polite");
    lateral.appendChild(medida);

    function marcarRapida(filas, columnas) {
      celdas.forEach(function (una) {
        var activa = +una.dataset.fila <= filas && +una.dataset.columna <= columnas;
        una.classList.toggle("activa", activa);
      });
    }

    function actualizarMedida() {
      medida.textContent = plural(dlg.estado.columnas, "columna", "columnas") + " × " + plural(dlg.estado.filas, "fila", "filas");
      marcarRapida(dlg.estado.filas, dlg.estado.columnas);
    }
    dlg.actualizarMedida = actualizarMedida;

    rapida.addEventListener("mouseover", function (evento) {
      var una = evento.target.closest(".editor-tabla-rapida-celda");
      if (!una) {
        return;
      }
      marcarRapida(+una.dataset.fila, +una.dataset.columna);
      medida.textContent = plural(+una.dataset.columna, "columna", "columnas") + " × " + plural(+una.dataset.fila, "fila", "filas");
    });
    rapida.addEventListener("mouseleave", actualizarMedida);
    rapida.addEventListener("click", function (evento) {
      var una = evento.target.closest(".editor-tabla-rapida-celda");
      if (!una) {
        return;
      }
      cambiarTamano(+una.dataset.fila, +una.dataset.columna);
      var primera = caja.querySelector(".editor-tabla-celda");
      if (primera) {
        primera.focus();
      }
    });

    var tamano = doc.createElement("div");
    tamano.className = "editor-tabla-tamano";

    function grupo(rotulo, singular, eje) {
      var grupoCaja = doc.createElement("div");
      grupoCaja.className = "editor-tabla-paso";
      var etiqueta = doc.createElement("span");
      etiqueta.textContent = rotulo;
      grupoCaja.appendChild(etiqueta);

      function paso(texto, delta, nombre) {
        var boton = doc.createElement("button");
        boton.type = "button";
        boton.className = "editor-tabla-paso-boton";
        boton.textContent = texto;
        boton.setAttribute("aria-label", nombre);
        boton.addEventListener("click", function () {
          if (eje === "filas") {
            cambiarTamano(dlg.estado.filas + delta, dlg.estado.columnas);
          } else {
            cambiarTamano(dlg.estado.filas, dlg.estado.columnas + delta);
          }
        });
        grupoCaja.appendChild(boton);
        return boton;
      }

      var menos = paso("−", -1, "Quitar una " + singular);
      var cuenta = doc.createElement("output");
      cuenta.className = "editor-tabla-cuenta";
      cuenta.textContent = "2";
      grupoCaja.appendChild(cuenta);
      var mas = paso("+", 1, "Añadir una " + singular);
      tamano.appendChild(grupoCaja);
      return { menos: menos, cuenta: cuenta, mas: mas };
    }

    var pasos = {
      columnas: grupo("Columnas", "columna", "columnas"),
      filas: grupo("Filas", "fila", "filas")
    };
    lateral.appendChild(tamano);

    var cuadricula = doc.createElement("div");
    cuadricula.className = "editor-tabla-cuadricula";
    cuadricula.setAttribute("role", "group");
    cuadricula.setAttribute("aria-label", "Celdas de la tabla");
    principal.appendChild(cuadricula);

    function cambiarTamano(filas, columnas) {
      filas = Math.min(MAX_FILAS, Math.max(1, filas));
      columnas = Math.min(MAX_COLUMNAS, Math.max(1, columnas));
      var estado = dlg.estado;
      var datos = [];
      for (var fila = 0; fila < filas; fila++) {
        var valores = [];
        for (var columna = 0; columna < columnas; columna++) {
          valores.push((estado.datos[fila] && estado.datos[fila][columna]) || "");
        }
        datos.push(valores);
      }
      estado.filas = filas;
      estado.columnas = columnas;
      estado.datos = datos;
      pintar();
    }
    dlg.cambiarTamano = cambiarTamano;

    function pintar() {
      var estado = dlg.estado;
      cuadricula.innerHTML = "";
      cuadricula.style.setProperty("--columnas", estado.columnas);
      for (var fila = 0; fila < estado.filas; fila++) {
        for (var columna = 0; columna < estado.columnas; columna++) {
          var entrada = doc.createElement("input");
          entrada.type = "text";
          entrada.className = "editor-tabla-celda" + (fila === 0 ? " editor-tabla-celda-cabecera" : "");
          entrada.value = estado.datos[fila][columna] || "";
          entrada.placeholder = fila === 0 ? "Encabezado " + (columna + 1) : "";
          entrada.dataset.fila = fila;
          entrada.dataset.columna = columna;
          entrada.setAttribute("aria-label", "Fila " + (fila + 1) + ", columna " + (columna + 1));
          cuadricula.appendChild(entrada);
        }
      }
      pasos.columnas.cuenta.textContent = estado.columnas;
      pasos.filas.cuenta.textContent = estado.filas;
      pasos.columnas.menos.disabled = estado.columnas <= 1;
      pasos.columnas.mas.disabled = estado.columnas >= MAX_COLUMNAS;
      pasos.filas.menos.disabled = estado.filas <= 1;
      pasos.filas.mas.disabled = estado.filas >= MAX_FILAS;
      dlg.anadir.filas.disabled = estado.filas >= MAX_FILAS;
      dlg.anadir.columnas.disabled = estado.columnas >= MAX_COLUMNAS;
      actualizarMedida();
    }
    dlg.pintar = pintar;

    // Los asteriscos de la negrita se ven tal cual dentro de la celda: se avisa
    // de que son formato, para que no parezcan un error.
    var formato = doc.createElement("p");
    formato.className = "editor-tabla-formato";
    formato.innerHTML = "Dentro de una celda valen <code>**negrita**</code>, <code>*cursiva*</code> y <code>[enlace](https://…)</code>.";
    principal.appendChild(formato);

    cuadricula.addEventListener("input", function (evento) {
      var entrada = evento.target;
      if (!entrada.dataset || entrada.dataset.fila === undefined) {
        return;
      }
      dlg.estado.datos[+entrada.dataset.fila][+entrada.dataset.columna] = entrada.value;
    });

    // Enter pasa a la celda siguiente, como en una hoja de cálculo.
    cuadricula.addEventListener("keydown", function (evento) {
      if (evento.key !== "Enter") {
        return;
      }
      evento.preventDefault();
      var entradas = Array.prototype.slice.call(cuadricula.querySelectorAll(".editor-tabla-celda"));
      var siguiente = entradas[entradas.indexOf(evento.target) + 1];
      if (siguiente) {
        siguiente.focus();
        return;
      }
      // En la última celda, Enter añade una fila más.
      if (evento.target.value.trim() !== "") {
        var filas = dlg.estado.filas;
        cambiarTamano(filas + 1, dlg.estado.columnas);
        var nuevas = cuadricula.querySelectorAll(".editor-tabla-celda");
        var destino = nuevas[filas * dlg.estado.columnas];
        if (destino) {
          destino.focus();
        }
      }
    });

    var pegar = doc.createElement("details");
    pegar.className = "editor-tabla-pegar";
    var resumen = doc.createElement("summary");
    resumen.textContent = "Ya la tengo en Excel o en una lista";
    pegar.appendChild(resumen);
    var nota = doc.createElement("p");
    nota.className = "editor-tabla-nota";
    nota.textContent = "Copie las celdas en Excel y péguelas aquí, o escriba una línea por fila separando con punto y coma.";
    pegar.appendChild(nota);
    var area = doc.createElement("textarea");
    area.rows = 4;
    area.placeholder = "Pegue aquí…";
    area.className = "editor-tabla-pegado";
    pegar.appendChild(area);

    var aviso = doc.createElement("p");
    aviso.className = "editor-tabla-aviso";
    aviso.setAttribute("aria-live", "polite");
    pegar.appendChild(aviso);

    // Lo pegado se carga solo en la cuadrícula: si hay que pulsar además un
    // botón, parece que no ha hecho nada.
    function aplicarPegado(opciones) {
      var datos = datosPegados(area.value);
      if (!datos.length) {
        aviso.textContent = "No se encontraron celdas: copie las celdas en la hoja de cálculo y péguelas aquí.";
        area.focus();
        return;
      }
      var columnas = 1;
      datos.forEach(function (fila) { columnas = Math.max(columnas, fila.length); });
      dlg.estado.datos = datos;
      cambiarTamano(Math.max(datos.length, 1), columnas);
      aviso.textContent = "";
      if (opciones && opciones.cerrar) {
        pegar.open = false;
      }
      cuadricula.scrollIntoView({ block: "nearest" });
      if (!opciones || opciones.enfocar) {
        var primera = cuadricula.querySelector(".editor-tabla-celda");
        if (primera) {
          primera.focus();
        }
      }
    }
    dlg.aplicarPegado = aplicarPegado;

    area.addEventListener("paste", function () {
      window.setTimeout(function () { aplicarPegado({ cerrar: false, enfocar: false }); }, 30);
    });
    area.addEventListener("change", function () { aplicarPegado({ cerrar: false, enfocar: false }); });

    var usar = doc.createElement("button");
    usar.type = "button";
    usar.className = "editor-tabla-usar";
    usar.textContent = "Usar estos datos";
    usar.addEventListener("click", function () { aplicarPegado({ cerrar: true, enfocar: true }); });
    pegar.appendChild(usar);
    lateral.appendChild(pegar);

    // Añadir filas y columnas, con un botón que se vea: los «+» pequeños
    // pasaban desapercibidos.
    var anadir = doc.createElement("div");
    anadir.className = "editor-tabla-anadir";

    function botonAnadir(texto) {
      var boton = doc.createElement("button");
      boton.type = "button";
      boton.className = "editor-tabla-anadir-boton";
      boton.textContent = texto;
      anadir.appendChild(boton);
      return boton;
    }

    var masFilas = botonAnadir("+ Añadir fila");
    masFilas.addEventListener("click", function () {
      cambiarTamano(dlg.estado.filas + 1, dlg.estado.columnas);
      var entradas = cuadricula.querySelectorAll(".editor-tabla-celda");
      var destino = entradas[(dlg.estado.filas - 1) * dlg.estado.columnas];
      if (destino) {
        destino.focus();
      }
    });

    var masColumnas = botonAnadir("+ Añadir columna");
    masColumnas.addEventListener("click", function () {
      cambiarTamano(dlg.estado.filas, dlg.estado.columnas + 1);
    });

    principal.appendChild(anadir);
    dlg.anadir = { filas: masFilas, columnas: masColumnas };

    var acciones = doc.createElement("div");
    acciones.className = "editor-tabla-acciones";
    var cancelar = doc.createElement("button");
    cancelar.type = "button";
    cancelar.className = "editor-tabla-cancelar";
    cancelar.textContent = "Cancelar";
    cancelar.addEventListener("click", function () { dlg.close(); });
    acciones.appendChild(cancelar);
    var aceptar = doc.createElement("button");
    aceptar.type = "button";
    aceptar.className = "editor-tabla-aceptar";
    acciones.appendChild(aceptar);
    aceptar.addEventListener("click", function () {
      var estado = dlg.estado;
      var markdown = aMarkdown(estado.datos);
      // Se cierra antes de escribir: con el diálogo modal abierto el foco no
      // puede irse al campo, y el texto se quedaba insertado sin que se viera.
      dlg.close();
      if (estado.editar) {
        escribir(campo, markdown, estado.desde, estado.hasta);
      } else {
        insertarTabla(campo, markdown, estado.desde, estado.hasta);
      }
    });
    caja.appendChild(acciones);

    dlg.aceptar = aceptar;
    dlg.titulo = titulo;
    dlg.area = area;
    dlg.cuadricula = cuadricula;
    dlg.estado = { editar: false, datos: [["", ""], ["", ""]], filas: 2, columnas: 2, desde: 0, hasta: 0 };
    return dlg;
  }

  function abrirTabla(campo) {
    var dlg = campo.editorTabla;
    if (!dlg) {
      return;
    }
    // Si el campo no se ha tocado nunca no hay cursor donde poner la tabla: se
    // añade al final, que es lo que se espera al pulsar el botón directamente.
    var parte = campo.ultimaSeleccion
      ? { inicio: campo.ultimaSeleccion[0], fin: campo.ultimaSeleccion[1] }
      : { inicio: campo.value.length, fin: campo.value.length };
    var hallada = campo.ultimaSeleccion ? tablaEnCursor(campo) : null;
    if (hallada) {
      dlg.estado = {
        editar: true,
        datos: hallada.datos,
        filas: hallada.datos.length,
        columnas: hallada.datos[0].length,
        desde: hallada.desde,
        hasta: hallada.hasta
      };
      dlg.titulo.textContent = "Editar la tabla";
      dlg.aceptar.textContent = "Aplicar los cambios";
    } else {
      dlg.estado = {
        editar: false,
        datos: [["", ""], ["", ""], ["", ""]],
        filas: 3,
        columnas: 2,
        desde: parte.inicio,
        hasta: parte.fin
      };
      dlg.titulo.textContent = "Nueva tabla";
      dlg.aceptar.textContent = "Insertar la tabla";
    }
    dlg.area.value = "";
    dlg.pintar();
    if (typeof dlg.showModal === "function") {
      dlg.showModal();
    } else {
      dlg.setAttribute("open", "open");
    }
    var primera = dlg.cuadricula.querySelector(".editor-tabla-celda");
    if (primera) {
      primera.focus();
    }
  }

  function accion(campo, boton) {
    if (boton.tabla) {
      abrirTabla(campo);
    } else if (boton.plantilla) {
      insertarPlantilla(campo, boton);
    } else if (boton.linea) {
      porLineas(campo, boton);
    } else {
      envolver(campo, boton);
    }
  }
  function crearBoton(doc, boton, campo) {
    var elemento = doc.createElement("button");
    elemento.type = "button";
    elemento.className = "editor-boton" + (boton.clase ? " " + boton.clase : "");
    elemento.title = boton.titulo;
    elemento.setAttribute("aria-label", boton.titulo);
    elemento.textContent = boton.texto;
    elemento.addEventListener("click", function (evento) {
      evento.preventDefault();
      accion(campo, boton);
    });
    return elemento;
  }

  function crearGuia(doc) {
    var caja = doc.createElement("details");
    caja.className = "editor-guia";

    var resumen = doc.createElement("summary");
    resumen.textContent = "Cómo se escribe";
    caja.appendChild(resumen);

    var lista = doc.createElement("dl");
    GUIA.forEach(function (par) {
      var marca = doc.createElement("dt");
      marca.textContent = par[0];
      var explica = doc.createElement("dd");
      explica.textContent = par[1];
      lista.appendChild(marca);
      lista.appendChild(explica);
    });
    caja.appendChild(lista);

    var nota = doc.createElement("p");
    nota.className = "editor-nota";
    nota.textContent = "Lo que se guarda es Markdown; la ficha del producto lo muestra ya formateado.";
    caja.appendChild(nota);

    return caja;
  }

  function montar(campo) {
    if (campo.dataset.editorListo === "si") {
      return;
    }
    campo.dataset.editorListo = "si";

    var doc = campo.ownerDocument;
    var caja = doc.createElement("div");
    caja.className = "editor-markdown";

    var barra = doc.createElement("div");
    barra.className = "editor-barra";
    barra.setAttribute("role", "toolbar");
    barra.setAttribute("aria-label", "Formato de la descripción");
    BOTONES.forEach(function (boton) {
      barra.appendChild(crearBoton(doc, boton, campo));
    });
    caja.appendChild(barra);

    // Metro envuelve los textarea con `data-role="textarea"`; se sube el envoltorio
    // entero para que la barra quede por fuera y no dentro del marco.
    var ancla = campo.closest(".textarea") || campo;
    ancla.parentNode.insertBefore(caja, ancla);
    caja.appendChild(ancla);
    caja.appendChild(crearGuia(doc));

    // La última posición del cursor, para saber dónde va una tabla cuando el
    // botón se pulsa sin haber vuelto a tocar el campo.
    ["keyup", "mouseup", "focus", "select"].forEach(function (evento) {
      campo.addEventListener(evento, function () {
        campo.ultimaSeleccion = [campo.selectionStart, campo.selectionEnd];
      });
    });

    // El constructor de tablas va al final del documento: dentro del formulario
    // estorbaría y cualquier contenedor con overflow lo recortaría.
    var dialogo = crearDialogoTabla(doc, campo);
    campo.editorTabla = dialogo;
    (doc.body || caja).appendChild(dialogo);
  }

  function arrancar() {
    var campos = document.querySelectorAll("[data-editor-markdown]");
    Array.prototype.forEach.call(campos, montar);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", arrancar);
  } else {
    arrancar();
  }

  window.EditorMarkdown = { arrancar: arrancar, montar: montar };
})();
