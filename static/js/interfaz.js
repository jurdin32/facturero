/* El comportamiento de la interfaz, encima de los componentes de Metro.
 *
 *   · el menú del móvil (el lateral de escritorio no necesita JavaScript)
 *   · los avisos del servidor, como avisos flotantes de Metro
 *   · los formularios que piden confirmación, con un diálogo de Metro
 *   · los formularios que tardan (emitir al SRI), con el anillo de espera
 *
 * Todo es mejora progresiva: si este archivo no carga, la pantalla sigue
 * funcionando y los avisos se leen en su sitio, dentro de la página.
 */
(function () {
  "use strict";

  var Metro = window.Metro;

  /* ------------------------------------------------------ el menú del móvil */

  var boton = document.getElementById("abrir-menu");
  var panel = document.getElementById("panel-menu");
  var velo = document.getElementById("velo");

  if (boton && panel && velo) {
    var menu = function (abierto) {
      document.body.classList.toggle("menu-abierto", abierto);
      boton.setAttribute("aria-expanded", abierto ? "true" : "false");
    };

    boton.addEventListener("click", function () {
      menu(!document.body.classList.contains("menu-abierto"));
    });
    velo.addEventListener("click", function () {
      menu(false);
    });
    panel.addEventListener("click", function (evento) {
      if (evento.target.closest("a")) {
        menu(false);
      }
    });
    document.addEventListener("keydown", function (evento) {
      if (evento.key === "Escape") {
        menu(false);
      }
    });
  }

  if (!Metro) {
    return;
  }

  /* -------------------------------------------------- los avisos del servidor */

  var ICONO = {
    success: "mif-checkmark",
    error: "mif-cross",
    warning: "mif-warning",
    info: "mif-info",
  };

  document.querySelectorAll(".avisos .aviso").forEach(function (aviso) {
    var tipo = aviso.dataset.aviso || "info";
    var icono = ICONO[tipo] || ICONO.info;
    var duracion = tipo === "error" ? 9000 : 5000;

    Metro.toast.create(
      '<span class="mif-' + icono + ' aviso-icono"></span><span>' + aviso.innerHTML + "</span>",
      { position: "top", timeout: duracion, clsToast: "aviso-flotante aviso-flotante-" + tipo }
    );

    aviso.remove();
    apilarAvisos();
  });

  /* Metro pone todos los avisos flotantes en el mismo sitio —arriba— y el segundo
   * tapa al primero. Aquí se les da su altura: cada uno debajo del anterior. */
  function apilarAvisos() {
    var alto = 20; // el mismo aire que Metro deja por arriba
    document.querySelectorAll(".toast.aviso-flotante").forEach(function (aviso) {
      aviso.style.top = alto + "px";
      alto += aviso.getBoundingClientRect().height + 8;
    });
  }

  document.querySelectorAll(".avisos").forEach(function (caja) {
    if (!caja.children.length) {
      caja.remove();
    }
  });

  /* -------------------------------------------- lo que hay que confirmar antes */

  document.querySelectorAll("form[data-confirmar]").forEach(function (formulario) {
    formulario.addEventListener("submit", function (evento) {
      evento.preventDefault();

      Metro.dialog.create({
        title: formulario.dataset.titulo || "¿Seguimos?",
        content: formulario.dataset.confirmar,
        closeButton: true,
        defaultActions: false,
        clsDialog: "dialogo-confirmar",
        customButtons: [
          {
            text: formulario.dataset.aceptar || "Sí, seguir",
            cls: "js-dialog-close primary",
            onclick: function () {
              formulario.submit();
            },
          },
          { text: "Cancelar", cls: "js-dialog-close" },
        ],
      });
    });
  });

  /* Un mismo formulario puede tener varias acciones —guardar, contabilizar,
   * cerrar—, así que la confirmación también se puede poner en el botón. Antes
   * solo se leía en el formulario y los botones con data-confirmar no hacían
   * nada: el proceso seguía sin avisar. */
  document.querySelectorAll("button[data-confirmar]").forEach(function (boton) {
    boton.addEventListener("click", function (evento) {
      var formulario = boton.form;
      if (!formulario) {
        return;
      }
      if (!formulario.noValidate && formulario.checkValidity && !formulario.checkValidity()) {
        return;
      }
      evento.preventDefault();

      Metro.dialog.create({
        title: boton.dataset.titulo || "¿Seguimos?",
        content: boton.dataset.confirmar,
        closeButton: true,
        defaultActions: false,
        clsDialog: "dialogo-confirmar",
        customButtons: [
          {
            text: boton.dataset.aceptar || "Sí, seguir",
            cls: "js-dialog-close primary",
            onclick: function () {
              // `form.submit()` no envía el botón que se pulsó; se guarda su
              // nombre y su valor para que el servidor sepa qué acción ejecutar.
              if (boton.name) {
                var oculto = document.createElement("input");
                oculto.type = "hidden";
                oculto.name = boton.name;
                oculto.value = boton.value;
                formulario.appendChild(oculto);
              }
              formulario.submit();
            },
          },
          { text: "Cancelar", cls: "js-dialog-close" },
        ],
      });
    });
  });

  /* ------------------------------------------------- lo que tarda en volver */

  var espera = null;

  document.querySelectorAll("form[data-espera]").forEach(function (formulario) {
    formulario.addEventListener("submit", function (evento) {
      if (formulario.checkValidity && !formulario.checkValidity()) {
        return;
      }
      // El botón que envía **no** se deshabilita: el navegador arma los datos del
      // formulario después de este aviso y, si queda deshabilitado, no viajan su
      // `name`/`value` (el servidor no sabría que era «emitir al SRI» y solo
      // guardaría el borrador). El anillo de espera ya tapa la pantalla.
      var enviador = evento.submitter || null;
      formulario.querySelectorAll("button[type=submit], button:not([type])").forEach(function (boton) {
        if (boton !== enviador) {
          boton.disabled = true;
        }
      });
      // Se guarda para poder quitarlo si el navegador vuelve a esta página.
      espera = Metro.activity.open({
        text: formulario.dataset.espera,
        type: "metro",
        style: "color",
      });
    });
  });

  /* Si el navegador vuelve atrás mientras el anillo está puesto, se quita: si no,
   * quedaría tapando la pantalla en una página que ya no está enviando nada. Los
   * botones vuelven a su sitio por el mismo motivo. */
  window.addEventListener("pageshow", function () {
    if (espera && document.querySelector(".global-overlay")) {
      Metro.activity.close(espera);
    }
    espera = null;
    document.querySelectorAll("form[data-espera] button[disabled]").forEach(function (boton) {
      boton.disabled = false;
    });
  });

  /* ------------------------------------- los controles sueltos de la interfaz */

  /* Un interruptor puede enviar su formulario: se marca con `data-enviar-al-cambiar`
   * (el interruptor de «solo lo que hay que reponer», por ejemplo). */
  document.querySelectorAll("[data-enviar-al-cambiar]").forEach(function (control) {
    control.addEventListener("change", function () {
      if (control.form) {
        control.form.submit();
      }
    });
  });

  /* -------------------------------------- los demás controles de Metro
   *
   * Metro monta sus componentes cuando se le pide (`Metro.makePlugin`). Los que
   * se piden desde las plantillas con `data-role` se montan aquí de una vez, y se
   * vuelven a montar los que aparezcan después: la tabla de datos repinta sus
   * filas al filtrar y al paginar, y trae controles nuevos con ellas.
   *
   * Metro marca lo que ya montó con `data-role-<nombre>="true"`, que es lo que se
   * mira para no montar dos veces lo mismo.
   */

  var COMPONENTES = [
    "input",
    "select",
    "textarea",
    "checkbox",
    "radio",
    "switch",
    "counter",
    "progress",
  ];

  function montar(raiz) {
    if (!raiz || raiz.nodeType !== 1) {
      return;
    }
    COMPONENTES.forEach(function (nombre) {
      var selector = '[data-role="' + nombre + '"]:not([data-role-' + nombre + "])";
      if (raiz.matches(selector)) {
        Metro.makePlugin(raiz, nombre, {});
      }
      raiz.querySelectorAll(selector).forEach(function (elemento) {
        Metro.makePlugin(elemento, nombre, {});
      });
    });
  }

  montar(document.body);

  if (window.MutationObserver) {
    var pendiente = null;
    new MutationObserver(function () {
      // Lo que llegue de golpe (una página entera de filas) se monta una vez.
      if (pendiente) {
        return;
      }
      pendiente = window.requestAnimationFrame(function () {
        pendiente = null;
        montar(document.body);
      });
    }).observe(document.body, { childList: true, subtree: true });
  }

  /* -------------------------------------- las listas, con la tabla de Metro
   *
   * Las listas las sigue sirviendo Django, ya filtradas, y aquí se les monta
   * encima la tabla de datos de Metro: buscador, orden por columna, cuántas
   * filas se ven y paginación, todo en el navegador.
   */

  Metro.locales[document.documentElement.lang || "es"] = Object.assign(
    {},
    Metro.locales.es,
    {
      label_search: "Buscar:",
      label_rows_count: "Mostrar:",
      label_table_info: "Mostrando $1 a $2 de $3",
      label_prev: "Anterior",
      label_next: "Siguiente",
      label_all: "Todos",
      label_empty: "No hay nada que mostrar",
      label_goto_page: "Ir a",
      label_enter_page: "Página…",
      label_clear_input: "Borrar",
      label_inspector: "Columnas",
    }
  );

  /* De la tabla que pintó Django a los datos que entiende el componente.
   * Las fechas y los importes no se reordenan: en texto «09/10/2026» o
   * «1.234,56» no se comparan bien, y ya vienen de la más nueva a la más vieja. */
  function datosDeLaTabla(tabla) {
    var cabeceras = [];
    var filas = [];

    tabla.querySelectorAll("thead th").forEach(function (celda, indice) {
      var clases = (celda.className.match(/col-[a-z-]+/g) || []).join(" ");
      var orden = celda.dataset.orden || "";
      cabeceras.push({
        name: "columna-" + indice,
        title: celda.innerHTML.trim(),
        // El componente pone `cls` en la cabecera y `clsColumn` también en las celdas.
        cls: clases,
        clsColumn: clases,
        sortable: celda.classList.contains("sortable-column") && !/numero|fecha/.test(orden),
      });
    });

    tabla.querySelectorAll("tbody tr").forEach(function (fila) {
      var celdas = [];
      fila.querySelectorAll("td").forEach(function (celda) {
        celdas.push(celda.innerHTML.trim());
      });
      filas.push(celdas);
    });

    return { header: cabeceras, data: filas };
  }

  document.querySelectorAll("table[data-tabla]").forEach(function (tabla) {
    var datos = datosDeLaTabla(tabla);
    if (!datos.data.length) {
      return;
    }
    // La tabla de Metro se pinta entera: se vacía lo que sirvió Django.
    tabla.querySelectorAll("thead, tbody, tfoot").forEach(function (parte) {
      parte.remove();
    });
    Metro.makePlugin(tabla, "table", {
      head: datos.header,
      body: datos.data,
      rows: 25,
      rowsSteps: "10,25,50,100,-1",
      showSearch: true,
      showRowsSteps: true,
      showTableInfo: true,
      showPagination: true,
      showSkip: false,
      cellWrapper: false,
      // La tabla se desplaza de lado si no caben las columnas (en una pantalla
      // justa). La barra sólo sale cuando de verdad sobra ancho: el desborde de
      // 4px que la dejaba puesta siempre lo quita el CSS (`pagination`).
      horizontalScroll: true,
      viewSaveMode: "client",
      viewSavePath: "tabla-$1",
    });
  });
})();
