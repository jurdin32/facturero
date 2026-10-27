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
    { texto: "▦", titulo: "Tabla", clase: "",
      plantilla: "| Columna | Columna |\n| --- | --- |\n| Dato | Dato |\n| Dato | Dato |\n" },
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
    ["| a | b |", "tabla (la segunda línea son los guiones)"],
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

  function accion(campo, boton) {
    if (boton.plantilla) {
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
