/* Las filas de los comprobantes y las ventanas para elegir.
 *
 * Sirve para las tres formas que hay: la tabla de líneas (nota de crédito, liquidación
 * de compra), la de motivos (nota de débito) y las cabeceras repetibles —los
 * destinatarios de una guía, los documentos del proveedor de una retención— con sus
 * tablas dentro.
 *
 * Cada tabla dice de dónde clona una fila en data-plantilla, cómo se llama su prefijo
 * en data-formset y dónde lleva la cuenta en data-total. El prefijo de una tabla de
 * dentro de un grupo es ``hijo-3-bienes``: la marca de la plantilla se sustituye por
 * el número de la cabecera primero y por el de la fila después.
 *
 * Las ventanas (elegir cliente, productos o el comprobante que se modifica) llevan un
 * fondo que tapa la hoja mientras están abiertas: no se puede tocar nada de detrás, y
 * se cierran con su botón de cerrar.
 */
(function () {
  "use strict";

  var MARCA = "__prefix__";

  /** Un elemento por su id, con o sin el prefijo «id_» que pone Django. */
  function porId(nombre) {
    return document.getElementById(nombre) || document.getElementById("id_" + nombre);
  }

  /** El primer elemento del HTML que se le pase (una fila, un grupo).
   *
   * Se arma dentro de un ``<template>``, que es el único sitio donde el navegador no
   * desarma una fila de tabla: dentro de un ``<div>`` se perdería el ``<tr>`` y los
   * campos quedarían sueltos.
   */
  function nodo(html) {
    var molde = document.createElement("template");
    molde.innerHTML = String(html).trim();
    return molde.content.firstElementChild;
  }

  // ------------------------------------------------------------------- las filas

  /** La marca de la plantilla, puesta en su sitio: la cabecera y la fila que tocan. */
  function numerado(html, tabla) {
    var prefijo = tabla.dataset.formset || "";
    var ultimo = prefijo.split("-").pop();
    var cuenta = porId(tabla.dataset.total || "");
    var numero = cuenta ? parseInt(cuenta.value, 10) || 0 : 0;
    return html
      .split("hijo-" + MARCA + "-" + ultimo).join(prefijo)
      .split(MARCA).join(String(numero));
  }

  /** Una fila nueva de una tabla, con su número puesto. */
  function filaNueva(tabla) {
    var plantilla = document.getElementById(tabla.dataset.plantilla || "");
    var cuenta = porId(tabla.dataset.total || "");
    if (!plantilla || !cuenta) return null;

    var fila = nodo(numerado(plantilla.innerHTML, tabla));
    if (!fila) return null;
    cuenta.value = String((parseInt(cuenta.value, 10) || 0) + 1);
    return fila;
  }

  /** La tabla de una fila: la que dice el botón o la de su bloque. */
  function tablaDe(boton) {
    if (boton.dataset.para) {
      return document.querySelector('table[data-formset="' + boton.dataset.para + '"]');
    }
    return (boton.closest(".bloque") || document).querySelector("table[data-formset]");
  }

  /** Un número escrito a la española o a la inglesa (con coma o con punto). */
  function numero(valor) {
    var n = parseFloat(String(valor === null || valor === undefined ? "" : valor).replace(",", "."));
    return isNaN(n) ? 0 : n;
  }

  /** La tarifa que dice el código del impuesto: «IVA 15%» es 15. */
  function tarifaDelCodigo(select) {
    if (!select) return null;
    var opcion = select.options[select.selectedIndex];
    if (!opcion) return null;
    var texto = opcion.textContent || "";
    // Lo que no lleva IVA no se calcula: es cero y ya está.
    if (/no objeto|exento/i.test(texto)) return 0;
    var encontrado = texto.match(/(\d+(?:[.,]\d+)?)\s*%/);
    // «IVA diferenciado» no dice la tarifa: la escribe quien sabe cuál es.
    return encontrado ? parseFloat(encontrado[1].replace(",", ".")) : null;
  }

  /** Escribe una cifra calculada, sin disparar eventos que vuelvan a calcular. */
  function ponerCifra(campo, valor) {
    if (!campo || !isFinite(valor)) return;
    campo.value = valor.toFixed(2);
  }

  /* Lo que se calcula solo, a partir de la base imponible y del porcentaje:
   * la tarifa y el valor del IVA del documento, y lo que se retiene. */
  function recalcular(contenedor) {
    if (!contenedor) return;
    var base = contenedor.querySelector('[name$="-base_imponible"]');
    if (!base) return;

    var importe = numero(base.value);
    var tipo = tarifaDelCodigo(contenedor.querySelector('[name$="-codigo_porcentaje"]'));
    if (tipo !== null) {
      ponerCifra(contenedor.querySelector('[name$="-tarifa"]'), tipo);
      ponerCifra(contenedor.querySelector('[name$="-valor"]'), (importe * tipo) / 100);
    }

    var porcentaje = contenedor.querySelector('[name$="-porcentaje_retener"]');
    if (porcentaje) {
      ponerCifra(
        contenedor.querySelector('[name$="-valor_retenido"]'),
        (importe * numero(porcentaje.value)) / 100
      );
    }
    // Lo calculado también se lee en la tabla.
    pintarLinea(contenedor);
  }

  /** Añade una fila al final de su tabla (la que dice el botón). */
  function anadirFila(boton) {
    var tabla = tablaDe(boton);
    if (!tabla) return;
    var fila = filaNueva(tabla);
    if (!fila) return;
    tabla.querySelector("tbody").appendChild(fila);
    pintarLinea(fila);
    var primero = fila.querySelector("input:not([type=hidden]), select");
    if (primero) primero.focus();
  }

  /* La barra que abre la tabla de retenciones del SRI.
   *
   * El desplegable con los más de cien conceptos desarmaba la ventana de la fila,
   * así que el select se queda escondido —es el que lleva el valor— y en su lugar
   * va esta barra, que abre la tabla en su propia ventana.
   */
  function barraDeRetencion(select) {
    return (
      '<div class="buscador-barra" data-buscador-retencion data-url="' +
      (select.getAttribute("data-url") || "") + '">' +
      '<input type="text" class="buscador-barra-campo" readonly autocomplete="off" ' +
      'data-buscar-retencion placeholder="Busque el concepto y elíjalo">' +
      '<button type="button" class="button small square primary" data-buscar-retencion ' +
      'title="Buscar el código en la tabla del SRI" aria-label="Buscar el código">' +
      '<span class="mif-search" aria-hidden="true"></span>' +
      "</button></div>"
    );
  }

  /** Pone en la barra el nombre del código que tiene el select en ese momento. */
  function pintarBarrasDeRetencion(contenedor) {
    if (!contenedor) return;
    Array.prototype.forEach.call(
      contenedor.querySelectorAll("[data-buscador-retencion]"),
      function (barra) {
        var caja = barra.closest(".campo-caja");
        var select = caja ? caja.querySelector("select") : null;
        var campo = barra.querySelector(".buscador-barra-campo");
        if (!select || !campo) return;
        var opcion = select.options[select.selectedIndex];
        campo.value = select.value && opcion ? opcion.textContent.trim() : "";
        campo.title = campo.value;
      }
    );
  }

  /* Añadir o editar una fila: los datos se piden en una ventana.
   *
   * En la hoja la fila solo se lee; lo que se escribe va en la ventana, que es
   * donde caben las etiquetas y la ayuda. Con `fila` se edita esa; sin ella se
   * añade una nueva al final de la tabla.
   */
  function abrirVentanaFila(boton, fila) {
    // Al editar, la tabla es la de la fila: hay comprobantes con dos tablas dentro
    // (los impuestos del documento y lo que se retiene) y el botón no dice cuál.
    var tabla = (fila && fila.closest("table[data-formset]")) || tablaDe(boton);
    var molde = tabla ? document.getElementById(tabla.dataset.plantilla || "") : null;
    var ejemplo = molde ? nodo(molde.innerHTML) : null;
    if (!ejemplo || !window.Metro) {
      anadirFila(boton);
      return;
    }

    var cabeceras = Array.prototype.map.call(
      tabla.querySelectorAll("thead th"),
      function (cabecera) {
        return cabecera.textContent.trim();
      }
    );
    var rejilla = "";
    Array.prototype.forEach.call(ejemplo.children, function (celda, indice) {
      var control = celda.querySelector("input:not([type=hidden]), select, textarea");
      // La casilla de borrado no se pregunta: se quita con la × de la fila.
      if (!control || /-DELETE$/.test(control.name || "")) return;
      // El código de retención no se despliega aquí: se busca en su ventana.
      var barra = /-codigo_retencion$/.test(control.name || "")
        ? barraDeRetencion(control)
        : "";
      rejilla +=
        '<div class="cell-12 cell-md-6" data-campo="' + indice + '">' +
        '<div class="campo-caja">' +
        '<span class="etiqueta">' + (cabeceras[indice] || "") + "</span>" +
        control.outerHTML.split("__prefix__").join("nueva") +
        barra +
        "</div></div>";
    });
    if (!rejilla) {
      anadirFila(boton);
      return;
    }

    var rotulo = boton.closest("section");
    var titulo =
      (rotulo && rotulo.querySelector(".bloque-titulo, .grupo-titulo")
        ? rotulo.querySelector(".bloque-titulo, .grupo-titulo").textContent.trim()
        : "") || (fila ? "Editar la fila" : "Añadir fila");

    window.Metro.window.create({
      title: titulo,
      icon: fila ? "pencil" : "plus",
      content:
        '<div class="ventana-cuerpo">' +
        '<div class="grupo-campos"><div class="row">' + rejilla + "</div></div>" +
        '<div class="ventana-acciones">' +
        '<button type="button" class="button outline dark" data-cancelar-fila>Cancelar</button>' +
        '<button type="button" class="button success" data-aceptar-fila>' +
        (fila ? "Guardar" : "Añadir") +
        "</button>" +
        "</div>" +
        "</div>",
      width: 760,
      height: 420,
      btnClose: true,
      btnMin: false,
      btnMax: false,
      draggable: true,
      shadow: true,
      clsWindow: "ventana-modal-win ventana-fila",
      closeAction: window.Metro.actions.REMOVE,
    });

    var ventana = document.querySelector(".ventana-modal-win.ventana-fila");
    if (!ventana) return;
    // Encima de la ventana que la abrió: si no, nace detrás y no se ve.
    ventana.style.zIndex = String(zMayor() + 10);
    centrarVentana(ventana);

    // Y la que estaba abierta se aparta mientras se rellena esta: dos ventanas
    // una sobre otra no hay quien las lea.
    var padre = Array.prototype.find.call(
      document.querySelectorAll(".ventana-modal-win"),
      function (otra) {
        return otra !== ventana && otra.contains(boton);
      }
    );
    if (padre) {
      padre.style.visibility = "hidden";
      ventana.__padre = padre;
    }

    function cerrar() {
      cerrarModal(ventana);
    }

    // Si se está editando, la ventana nace con lo que ya tiene la fila.
    if (fila) {
      Array.prototype.forEach.call(ventana.querySelectorAll("[data-campo]"), function (caja) {
        var indice = parseInt(caja.dataset.campo, 10);
        var origen = caja.querySelector("input, select, textarea");
        var celda = fila.children[indice];
        var valor = celda
          ? celda.querySelector("input:not([type=hidden]), select, textarea")
          : null;
        if (!origen || !valor) return;
        if (origen.type === "checkbox" || origen.type === "radio") {
          origen.checked = valor.checked;
        } else if (origen.tagName === "SELECT") {
          ponerOpcion(origen, valor.value);
        } else {
          origen.value = valor.value;
        }
      });
      recalcular(ventana);
      pintarBarrasDeRetencion(ventana);
    }

    var aspa = ventana.querySelector(".btn-close");
    if (aspa) {
      aspa.addEventListener(
        "click",
        function (evento) {
          evento.preventDefault();
          evento.stopPropagation();
          cerrar();
        },
        true
      );
    }
    ventana.querySelector("[data-cancelar-fila]").addEventListener("click", cerrar);

    // Lo que se calcula solo se va poniendo según se escribe.
    ["input", "change"].forEach(function (cual) {
      ventana.addEventListener(cual, function (evento) {
        if (evento.target.closest(".grupo-campos")) recalcular(ventana);
      });
    });

    ventana.querySelector("[data-aceptar-fila]").addEventListener("click", function () {
      // Lo que el propio campo pide (obligatorio, número, fecha) se comprueba antes.
      var controles = ventana.querySelectorAll(
        ".grupo-campos input, .grupo-campos select, .grupo-campos textarea"
      );
      for (var i = 0; i < controles.length; i++) {
        if (!controles[i].checkValidity()) {
          controles[i].reportValidity();
          return;
        }
      }

      var destinoFila = fila || filaNueva(tabla);
      if (!destinoFila) {
        cerrar();
        return;
      }
      Array.prototype.forEach.call(ventana.querySelectorAll("[data-campo]"), function (caja) {
        var indice = parseInt(caja.dataset.campo, 10);
        var origen = caja.querySelector("input, select, textarea");
        var celda = destinoFila.children[indice];
        var destino = celda
          ? celda.querySelector("input:not([type=hidden]), select, textarea")
          : null;
        if (!origen || !destino) return;
        if (destino.type === "checkbox" || destino.type === "radio") {
          destino.checked = origen.checked;
        } else if (destino.tagName === "SELECT") {
          ponerOpcion(destino, origen.value);
        } else {
          destino.value = origen.value;
        }
        destino.dispatchEvent(new Event("change", { bubbles: true }));
      });
      if (!fila) tabla.querySelector("tbody").appendChild(destinoFila);
      pintarLinea(destinoFila);
      cerrar();
    });
  }

  /** Añade una cabecera: su fila en la tabla, su bloque y su ventana abierta. */
  function anadirGrupo(boton) {
    var tabla = document.querySelector("table[data-grupos]");
    var molde = document.getElementById(boton.dataset.plantilla || "");
    var cuenta = porId("hijo-TOTAL_FORMS");
    var cajon = document.querySelector(".grupos-detalles");
    if (!tabla || !molde || !cuenta || !cajon) return;

    var numero = parseInt(cuenta.value, 10) || 0;
    var detalle = nodo(molde.innerHTML.split(MARCA).join(String(numero)));
    if (!detalle) return;
    cuenta.value = String(numero + 1);

    var prefijo = detalle.dataset.detalle;
    tabla.querySelector("tbody").appendChild(filaDeGrupo(prefijo));
    cajon.appendChild(detalle);
    pintarFila(prefijo);
    refrescarVacio();
    abrirGrupo(prefijo);
  }

  /** Quita una fila: si ya estaba guardada, se marca para que la borre el servidor. */
  function quitarFila(boton) {
    var fila = boton.closest("tr");
    if (!fila) return;
    var guardada = fila.querySelector('input[name$="-id"]');

    if (guardada && guardada.value) {
      var borrar = fila.querySelector('input[name$="-DELETE"]');
      if (borrar) borrar.checked = true;
      fila.classList.add("tenue");
      return;
    }

    // La tabla puede quedarse vacía: las filas entran de nuevo desde el buscador.
    fila.remove();
  }

  /** Quita una cabecera: si ya estaba guardada se marca, y si no, se va con todo. */
  function quitarGrupo(boton) {
    var prefijo = prefijoDe(boton);
    var detalle = detalleDe(prefijo);
    var fila = filaDe(prefijo);
    if (!fila) return;

    // Si se está escribiendo en su ventana, se cierra antes de tocarla.
    if (detalle) {
      var abierta = detalle.closest(".ventana-modal-win");
      if (abierta) cerrarModal(abierta);
    }

    var guardada = detalle && detalle.querySelector('input[name="' + prefijo + '-id"]');
    if (guardada && guardada.value) {
      var borrar = detalle.querySelector('input[name="' + prefijo + '-DELETE"]');
      if (borrar) borrar.checked = true;
      fila.classList.add("tachada");
      return;
    }

    fila.remove();
    if (detalle) detalle.remove();
    // La que se va sin guardar deja su hueco: se baja la cuenta para no dejarlo.
    var cuenta = porId("hijo-TOTAL_FORMS");
    var numero = parseInt(prefijo.split("-").pop(), 10);
    if (cuenta && numero === (parseInt(cuenta.value, 10) || 0) - 1) {
      cuenta.value = String(numero);
    }
    refrescarVacio();
  }

  // ---------------------------------------------------------------- las ventanas
  //
  // Cada ventana lleva su fondo por debajo y las dos van por encima de la hoja y de la
  // barra de arriba: la última que se abre es la que manda. El z-index se reparte para
  // que una ventana abierta desde otra —el catálogo, desde el destinatario— quede
  // delante de ella y se cierre sin llevársela.

  /** La capa que se le da a cada ventana y a su fondo. Empiezan por encima de la barra. */
  var capa = 1000;
  var abiertas = 0;

  /** El fondo que tapa la hoja: mientras la ventana está abierta no se toca nada. */
  function abrirFondo() {
    var z = (capa += 4);
    var fondo = document.createElement("div");
    fondo.className = "fondo-buscador";
    fondo.style.cssText =
      "position:fixed;top:0;left:0;right:0;bottom:0;z-index:" + z + ";" +
      "background:rgba(16,24,40,.45)";
    document.body.appendChild(fondo);
    abiertas += 1;
    document.body.classList.add("con-ventana");
    return { fondo: fondo, z: z };
  }

  /** Quita un fondo y, si no queda ninguno, deja la hoja moverse otra vez. */
  function cerrarFondo(fondo) {
    if (fondo) fondo.remove();
    abiertas = Math.max(0, abiertas - 1);
    if (!abiertas) document.body.classList.remove("con-ventana");
  }

  /** La ventana, en el centro de la pantalla (el top/left se mide desde su contenedor). */
  function centrarVentana(marco) {
    if (!marco) return;
    var caja = marco.getBoundingClientRect();
    var desvioX = caja.left - (parseFloat(marco.style.left) || 0);
    var desvioY = caja.top - (parseFloat(marco.style.top) || 0);
    marco.style.left = Math.round((window.innerWidth - caja.width) / 2 - desvioX) + "px";
    marco.style.top = Math.round((window.innerHeight - caja.height) / 2 - desvioY) + "px";
  }

  /** Lo más alto que hay en pantalla: así lo que se abre después queda delante. */
  function zMayor() {
    var mayor = 0;
    document
      .querySelectorAll(".ventana-modal-win, .ventana-buscador-win, .dialog, .global-overlay")
      .forEach(function (caja) {
        var z = parseInt(window.getComputedStyle(caja).zIndex, 10);
        if (!isNaN(z) && z > mayor) mayor = z;
      });
    return mayor;
  }

  /** Cierra la última ventana del buscador (y su fondo), si hay alguna abierta. */
  function cerrarVentanaBusqueda() {
    var ventanas = document.querySelectorAll(".ventana-buscador-win");
    var vieja = ventanas[ventanas.length - 1];
    if (!vieja) return;
    cerrarCapa(vieja);
  }

  /** Cierra una ventana de las de encima y quita el fondo que le tocaba. */
  function cerrarCapa(caja) {
    if (!caja) return;
    var fondo = caja.__fondo;
    var ventana = window.Metro && window.Metro.getPlugin(caja, "window");
    if (ventana) ventana.close(); else caja.remove();
    cerrarFondo(fondo);
  }

  /** Arma la ventana del buscador y devuelve sus piezas.
   *
   * Sin cruz en el marco: se cierra con su botón de cerrar (ni pulsando fuera), y
   * mientras está abierta el fondo no deja tocar la hoja.
   */
  function abrirVentana(config) {
    if (!window.Metro) return null;
    cerrarVentanaBusqueda();
    var capa = abrirFondo();
    // Encima de lo que ya está abierto: desde la ventana de una fila también se busca.
    var encima = Math.max(1000, zMayor());
    capa.fondo.style.zIndex = String(encima + 2);

    window.Metro.window.create({
      title: config.titulo,
      icon: config.icono,
      content:
        '<div class="buscador">' +
        '<div class="buscador-campo"><input type="search" autocomplete="off" placeholder="' +
        config.pista + '"></div>' +
        (config.filtros || "") +
        '<div class="buscador-cuerpo"></div>' +
        '<div class="buscador-vacio">' + config.vacio + "</div>" +
        '<div class="buscador-pie"><span class="buscador-cuenta"></span>' +
        (config.anadir
          ? '<button type="button" class="button primary" data-anadir-las disabled>Elegir</button>'
          : "") +
        '<button type="button" class="button outline dark" data-cerrar>Cerrar</button>' +
        "</div>" +
        "</div>",
      width: config.ancho,
      height: config.alto,
      btnClose: false,
      btnMin: false,
      btnMax: false,
      draggable: true,
      resizable: true,
      shadow: true,
      clsWindow: "ventana-buscador-win " + (config.clase || ""),
      closeAction: window.Metro.actions.REMOVE,
    });

    var caja = document.querySelector(".ventana-buscador-win");
    if (!caja) {
      cerrarFondo(capa.fondo);
      return null;
    }
    caja.__fondo = capa.fondo;
    caja.style.zIndex = String(encima + 3);
    centrarVentana(caja);

    var cerrar = caja.querySelector("[data-cerrar]");
    if (cerrar) cerrar.addEventListener("click", cerrarVentanaBusqueda);

    return {
      caja: caja,
      texto: caja.querySelector(".buscador-campo input"),
      cuerpo: caja.querySelector(".buscador-cuerpo"),
      vacio: caja.querySelector(".buscador-vacio"),
      cuenta: caja.querySelector(".buscador-cuenta"),
      anadir: caja.querySelector("[data-anadir-las]"),
    };
  }

  /** La ventana donde se escribe una cabecera repetible (un destinatario, un documento
   *  del proveedor): sus campos y las tablas que lleva dentro.
   *
   * Va dentro del formulario —de ahí se envían sus campos— y con su fondo: mientras
   * esté abierta no se toca la hoja. Solo tiene el botón de cerrar.
   */
  function abrirModal(config) {
    if (!window.Metro) return null;
    var capa = abrirFondo();
    var encima = Math.max(1000, zMayor());
    capa.fondo.style.zIndex = String(encima + 2);

    window.Metro.window.create({
      title: config.titulo,
      icon: config.icono,
      content: '<div class="ventana-cuerpo"></div>',
      width: config.ancho,
      height: config.alto,
      // La cruz va en la barra de título, arriba a la derecha: es donde se busca.
      btnClose: true,
      btnMin: false,
      btnMax: false,
      draggable: true,
      resizable: true,
      shadow: true,
      clsWindow: "ventana-modal-win",
      closeAction: window.Metro.actions.REMOVE,
    });

    var caja = document.querySelector(".ventana-modal-win");
    if (!caja) {
      cerrarFondo(capa.fondo);
      return null;
    }
    // Los campos tienen que seguir dentro del formulario para que se envíen.
    if (config.formulario) config.formulario.appendChild(caja);
    caja.__fondo = capa.fondo;
    caja.style.zIndex = String(encima + 3);
    centrarVentana(caja);

    var cerrar = caja.querySelector("[data-cerrar]");
    if (cerrar) cerrar.addEventListener("click", function () { cerrarModal(caja); });

    // La cruz de la barra de título cierra igual que el botón de antes: primero se
    // devuelve lo escrito a su sitio y luego Metro quita la ventana.
    var aspa = caja.querySelector(".btn-close");
    if (aspa) {
      aspa.addEventListener(
        "click",
        function (evento) {
          evento.preventDefault();
          evento.stopPropagation();
          cerrarModal(caja);
        },
        true
      );
    }
    return caja;
  }

  /** Cierra la ventana de una cabecera: devuelve lo escrito a su sitio y pinta la fila. */
  function cerrarModal(caja) {
    if (!caja) return;
    var volver = caja.__volver;
    var fondo = caja.__fondo;
    var padre = caja.__padre;
    if (volver) volver();
    var ventana = window.Metro && window.Metro.getPlugin(caja, "window");
    if (ventana) ventana.close(); else caja.remove();
    // La ventana que se había apartado vuelve a su sitio.
    if (padre) padre.style.visibility = "";
    cerrarFondo(fondo);
  }

  // ------------------------------------------------------------------ los grupos
  //
  // Las cabeceras repetibles —los destinatarios de una guía, los documentos del
  // proveedor de una retención— se ven en una tabla, una fila por cabecera, y lo que se
  // escribe de cada una vive en su bloque escondido. Al abrirlo, el bloque se mete en la
  // ventana y vuelve a su sitio al cerrarla: los campos no salen del formulario.

  /** El bloque donde se escribe una cabecera, por su prefijo (``hijo-2``). */
  function detalleDe(prefijo) {
    return document.querySelector('[data-detalle="' + prefijo + '"]');
  }

  /** La fila de la tabla que le toca a una cabecera. */
  function filaDe(prefijo) {
    return document.querySelector('tr.grupo[data-grupo="' + prefijo + '"]');
  }

  /** El prefijo de la cabecera a la que pertenece lo que se pulsó. */
  function prefijoDe(objetivo) {
    var bloque = objetivo.closest("[data-detalle]");
    if (bloque) return bloque.dataset.detalle;
    var fila = objetivo.closest("tr[data-grupo]");
    return fila ? fila.dataset.grupo : "";
  }

  /** Qué número hace la fila entre las de su tabla. */
  function numeroDeLaFila(fila) {
    var filas = fila.parentElement.querySelectorAll("tr.grupo");
    return Array.prototype.indexOf.call(filas, fila) + 1;
  }

  /** Una fila nueva de la tabla de cabeceras, con los huecos de sus columnas. */
  function filaDeGrupo(prefijo) {
    var tabla = document.querySelector("table[data-grupos]");
    var fila = document.createElement("tr");
    fila.className = "grupo";
    fila.dataset.grupo = prefijo;

    tabla.querySelectorAll("thead th[data-campo]").forEach(function (cabecera) {
      var celda = document.createElement("td");
      celda.className = "grupo-dato";
      celda.dataset.campo = cabecera.dataset.campo;
      fila.appendChild(celda);
    });
    tabla.querySelectorAll("thead th[data-cuenta]").forEach(function (cabecera) {
      var celda = document.createElement("td");
      celda.className = "col-cuenta cifra";
      celda.dataset.cuenta = cabecera.dataset.cuenta;
      celda.title = cabecera.title;
      celda.textContent = "0";
      fila.appendChild(celda);
    });

    var acciones = document.createElement("td");
    acciones.className = "col-acciones";
    // Los mismos dos botones que la fila que pinta el servidor: solo el icono,
    // uno para editar y la × para quitar.
    acciones.innerHTML =
      '<button type="button" class="button small square outline primary" data-abrir-grupo ' +
      'title="Editar" aria-label="Editar">' +
      '<span class="mif-pencil" aria-hidden="true"></span></button>' +
      '<button type="button" class="quitar" data-quitar-grupo title="Quitar" ' +
      'aria-label="Quitar">&times;</button>';
    fila.appendChild(acciones);
    return fila;
  }

  /** Deja un `<select>` en la opción que se le dice, con Metro de por medio.
   *
   * El select de verdad y el que se ve no son el mismo: hay que avisar al
   * componente o se queda enseñando la opción de antes.
   */
  function ponerOpcion(select, valor) {
    if (!select || valor === undefined || valor === null || valor === "") return;
    if (select.value !== valor) select.value = valor;
    var plugin =
      window.Metro && window.Metro.getPlugin
        ? window.Metro.getPlugin(select, "select")
        : null;
    if (plugin && typeof plugin.val === "function") plugin.val(valor);
  }

  /* El código de retención es de la tabla del SRI y con él vienen el impuesto y el
   * porcentaje: no hay que escribirlos ni acordarse de ellos. */
  function retencionElegida(campo, contenedor) {
    if (!campo || !/-codigo_retencion$/.test(campo.name || "")) return;
    var opcion = campo.options[campo.selectedIndex];
    if (!opcion) return;

    var impuesto = opcion.getAttribute("data-impuesto");
    if (impuesto) ponerOpcion(contenedor.querySelector('[name$="-codigo"]'), impuesto);

    var porcentaje = opcion.getAttribute("data-porcentaje");
    if (porcentaje === null || porcentaje === "") return;
    ponerCifra(
      contenedor.querySelector('[name$="-porcentaje_retener"]'),
      numero(porcentaje)
    );
  }

  /** Lo que se lee de un campo en la fila: las listas, por su nombre. */
  function valorDe(campo) {
    if (!campo) return "";
    if (campo.tagName === "SELECT") {
      var opcion = campo.options[campo.selectedIndex];
      return opcion ? opcion.textContent.trim() : "";
    }
    if (campo.type === "date") return fechaCorta(campo.value);
    return campo.value.trim();
  }

  /** Cuántas filas quedan en una tabla de dentro, sin contar las que se quitan. */
  function cuantasFilas(detalle, nombre) {
    var tabla = detalle.querySelector('table[data-formset$="-' + nombre + '"]');
    if (!tabla) return 0;
    var cuantas = 0;
    tabla.querySelectorAll("tbody tr").forEach(function (fila) {
      var borrar = fila.querySelector('input[name$="-DELETE"]');
      if (!borrar || !borrar.checked) cuantas += 1;
    });
    return cuantas;
  }

  /** La fila de la tabla, puesta al día con lo que se escribió en la ventana. */
  function pintarFila(prefijo) {
    var fila = filaDe(prefijo);
    var detalle = detalleDe(prefijo);
    if (!fila || !detalle) return;

    fila.querySelectorAll("td[data-campo]").forEach(function (celda) {
      celda.textContent = valorDe(detalle.querySelector('[name$="-' + celda.dataset.campo + '"]'));
    });
    fila.querySelectorAll("td[data-cuenta]").forEach(function (celda) {
      celda.textContent = String(cuantasFilas(detalle, celda.dataset.cuenta));
    });
  }

  /** Deja el aviso de que no hay ninguno como toque. */
  function refrescarVacio() {
    var vacio = document.querySelector(".grupos-vacio");
    var cuantas = document.querySelectorAll("table[data-grupos] tr.grupo").length;
    if (vacio) vacio.hidden = cuantas > 0;
  }

  /** Abre la ventana de una cabecera: sus campos y sus tablas, para escribirla. */
  function abrirGrupo(prefijo) {
    var detalle = detalleDe(prefijo);
    var fila = filaDe(prefijo);
    var tabla = document.querySelector("table[data-grupos]");
    if (!detalle || !fila || !tabla) return;
    if (detalle.closest(".ventana-modal-win")) return;  // ya está abierta

    var caja = abrirModal({
      titulo: tabla.dataset.titulo + " " + numeroDeLaFila(fila),
      icono: '<span class="mif-file-text"></span>',
      ancho: Math.min(940, window.innerWidth - 40),
      alto: Math.min(620, window.innerHeight - 80),
      formulario: fila.closest("form"),
    });
    if (!caja) return;

    var cajon = document.querySelector(".grupos-detalles");
    detalle.classList.remove("oculto");
    caja.querySelector(".ventana-cuerpo").appendChild(detalle);
    caja.__volver = function () {
      detalle.classList.add("oculto");
      if (cajon) cajon.appendChild(detalle);
      pintarFila(prefijo);
    };

    var primero = detalle.querySelector("input:not([type=hidden]), select, textarea");
    if (primero) primero.focus();
  }

  /** Pinta un resultado en la tabla del buscador.
   *
   * Con ``varios`` cada fila lleva su casilla y no se cierra la ventana al elegir.
   * Con ``doble`` el clic solo marca el renglón y la elección se hace con doble
   * clic, que es como se eligen los códigos de la tabla del SRI.
   */
  function pintarResultados(ventana, datos, columnas, alElegir, varios, doble) {
    ventana.cuerpo.innerHTML = "";
    ventana.vacio.style.display = datos.length ? "none" : "";
    if (!datos.length) return;

    var tabla = document.createElement("table");
    tabla.className = "table small libro buscador-libro";
    var cabecera = document.createElement("thead");
    if (varios) {
      var suelta = document.createElement("th");
      suelta.className = "col-elegir";
      cabecera.appendChild(suelta);
    }
    columnas.forEach(function (titulo) {
      var celda = document.createElement("th");
      celda.textContent = titulo;
      cabecera.appendChild(celda);
    });
    tabla.appendChild(cabecera);

    var filas = document.createElement("tbody");
    datos.forEach(function (dato) {
      var fila = document.createElement("tr");
      var casilla = null;
      if (varios) {
        var celda = document.createElement("td");
        celda.className = "col-elegir";
        casilla = document.createElement("input");
        casilla.type = "checkbox";
        casilla.className = "buscador-elegir";
        celda.appendChild(casilla);
        fila.appendChild(celda);
        casilla.addEventListener("change", function () {
          alElegir(dato, casilla.checked);
        });
      }
      (dato.celdas || []).forEach(function (valor) {
        var celda = document.createElement("td");
        celda.textContent = valor === null || valor === undefined ? "" : valor;
        fila.appendChild(celda);
      });
      fila.addEventListener("click", function (evento) {
        if (evento.target.type === "checkbox") return;  // la casilla ya se encarga
        if (varios) {
          casilla.checked = !casilla.checked;
          alElegir(dato, casilla.checked);
          return;
        }
        if (doble) {
          Array.prototype.forEach.call(filas.children, function (otra) {
            otra.classList.remove("elegida");
          });
          fila.classList.add("elegida");
          return;
        }
        alElegir(dato, true);
      });
      if (doble) {
        fila.addEventListener("dblclick", function () {
          alElegir(dato, true);
        });
      }
      filas.appendChild(fila);
    });
    tabla.appendChild(filas);
    ventana.cuerpo.appendChild(tabla);
  }

  /** Deja el buscador listo: escribe, espera un poco y busca. */
  function buscarCon(ventana, url, extra, pintar) {
    var reloj = null;
    function buscar() {
      var direccion =
        url +
        (url.indexOf("?") < 0 ? "?" : "&") +
        "q=" +
        encodeURIComponent(ventana.texto.value.trim());
      (extra ? extra() : []).forEach(function (par) {
        direccion += "&" + par[0] + "=" + encodeURIComponent(par[1]);
      });
      window
        .fetch(direccion)
        .then(function (respuesta) { return respuesta.json(); })
        .then(function (datos) { pintar(datos); })
        .catch(function () {
          ventana.vacio.style.display = "";
          ventana.vacio.textContent = "No se pudo buscar. Revise la conexión.";
        });
    }
    ventana.texto.addEventListener("input", function () {
      window.clearTimeout(reloj);
      reloj = window.setTimeout(buscar, 250);
    });
    ventana.texto.addEventListener("keydown", function (evento) {
      if (evento.key !== "Enter") return;
      evento.preventDefault();
      window.clearTimeout(reloj);
      buscar();
    });
    ventana.buscar = buscar;
    return buscar;
  }

  /** El buscador de clientes: se elige uno y sus datos van a los campos de su barra.
   *
   * Cada barra dice en ``data-llena`` qué campos se llenan con lo que trae el cliente:
   * el de la otra parte de una nota (``receptor``, ``proveedor``…) o los cuatro del
   * destinatario de una guía. Dentro de una cabecera repetible se llena la suya, no
   * las de las demás.
   */
  function buscarParte(barra) {
    if (!barra) return;
    var url = barra.dataset.url;
    var nombre = barra.querySelector(".buscador-barra-campo");
    if (!url) return;
    var alcance = barra.closest("[data-detalle]") || document;

    function llenar(dato) {
      (barra.dataset.llena || "").split(",").forEach(function (sufijo) {
        sufijo = sufijo.trim();
        if (!sufijo) return;
        var valores = {
          razon_social: dato.razon_social,
          identificacion: dato.identificacion,
          tipo_identificacion: dato.tipo_identificacion,
          direccion: dato.direccion,
        };
        var valor = sufijo in valores ? valores[sufijo] : dato.pk;
        var campo =
          alcance.querySelector('[name$="-' + sufijo + '"]') ||
          alcance.querySelector('[name="' + sufijo + '"]');
        if (campo && valor) campo.value = valor;
      });
      if (nombre) nombre.value = dato.razon_social;
    }

    var ventana = abrirVentana({
      titulo: "Buscar cliente",
      icono: "<span class=\"mif-person\"></span>",
      pista: "Nombre, RUC o cédula del cliente…",
      vacio: "Escriba para buscar.",
      ancho: Math.min(640, window.innerWidth - 40),
      alto: Math.min(460, window.innerHeight - 80),
    });
    if (!ventana) return;

    function elegir(dato) {
      llenar(dato);
      cerrarVentanaBusqueda();
    }

    var buscar = buscarCon(ventana, url, null, function (datos) {
      pintarResultados(
        ventana,
        (datos.resultados || []).map(function (dato) {
          return { dato: dato, celdas: [dato.razon_social, dato.identificacion, dato.direccion] };
        }),
        ["Cliente", "Identificación", "Dirección"],
        function (fila) { elegir(fila.dato); },
        false
      );
      if (!datos.resultados || !datos.resultados.length) {
        ventana.vacio.textContent = "No hay clientes con eso. Pruebe con otro nombre o el RUC.";
      }
    });
    buscar();
  }

  /** El buscador de los códigos de retención del SRI.
   *
   * La tabla tiene más de cien conceptos con el texto completo: se buscan en su
   * ventana y se eligen con doble clic. Al elegir se ponen el código, el impuesto
   * y el porcentaje que fija el SRI para ese concepto.
   */
  function buscarCodigoDeRetencion(barra) {
    if (!barra) return;
    var url = barra.dataset.url;
    var caja = barra.closest(".campo-caja");
    var select = caja ? caja.querySelector("select") : null;
    var contenedor = barra.closest(".grupo-campos");
    if (!url || !select || !contenedor) return;

    var ventana = abrirVentana({
      titulo: "Códigos de retención del SRI",
      icono: "<span class=\"mif-list\"></span>",
      pista: "Código o concepto (303, honorarios, IVA…)",
      vacio: "Escriba el código o lo que se retiene. Elija con doble clic.",
      ancho: Math.min(760, window.innerWidth - 40),
      alto: Math.min(520, window.innerHeight - 80),
      clase: "ventana-codigos",
    });
    if (!ventana) return;

    function elegir(dato) {
      ponerOpcion(select, dato.codigo);
      ponerOpcion(
        contenedor.querySelector('[name$="-codigo"]'),
        dato.impuesto
      );
      if (dato.porcentaje) {
        ponerCifra(
          contenedor.querySelector('[name$="-porcentaje_retener"]'),
          numero(dato.porcentaje)
        );
      }
      cerrarVentanaBusqueda();
      pintarBarrasDeRetencion(contenedor);
      recalcular(contenedor);
    }

    var buscar = buscarCon(ventana, url, null, function (datos) {
      pintarResultados(
        ventana,
        (datos.resultados || []).map(function (dato) {
          return {
            dato: dato,
            celdas: [dato.codigo, dato.concepto, dato.impuesto_nombre, dato.como_porcentaje],
          };
        }),
        ["Código", "Concepto", "Impuesto", "%"],
        function (fila) { elegir(fila.dato); },
        false,
        true
      );
      if (!datos.resultados || !datos.resultados.length) {
        ventana.vacio.textContent = "No hay códigos con eso. Pruebe con otro código o concepto.";
      }
    });
    buscar();
  }

  /** La ventana del catálogo: se eligen varios y se añaden sus líneas.
   *
   * No se cierra al elegir: se van marcando y se añaden con «Añadir N líneas». Solo se
   * cierra con su botón de cerrar.
   */
  function buscarProducto(url, tabla, delDocumento) {
    if (!url || !tabla) return;
    var ventana = abrirVentana({
      titulo: delDocumento
        ? "Qué se devuelve del comprobante"
        : "Buscar producto o servicio",
      icono: delDocumento
        ? "<span class=\"mif-books\"></span>"
        : "<span class=\"mif-cube\"></span>",
      pista: "Descripción o código…",
      vacio: delDocumento
        ? "Estas son las líneas del comprobante: elija las que se devuelven."
        : "Escriba para buscar.",
      ancho: Math.min(780, window.innerWidth - 40),
      alto: Math.min(560, window.innerHeight - 80),
      anadir: true,
    });
    if (!ventana) return;

    var marcados = {};

    function refrescar() {
      var cuantos = Object.keys(marcados).length;
      ventana.cuenta.textContent = cuantos
        ? cuantos + (cuantos === 1 ? " elegido" : " elegidos")
        : "";
      ventana.anadir.disabled = !cuantos;
      ventana.anadir.textContent = cuantos
        ? "Añadir " + cuantos + (cuantos === 1 ? " línea" : " líneas")
        : "Elegir";
    }

    ventana.anadir.addEventListener("click", function () {
      // Lo que ya está en la nota no se vuelve a poner: repetir una línea da errores.
      var claves = yaEnLaTabla(tabla);
      var repetidos = 0;
      Object.keys(marcados).forEach(function (clave) {
        var dato = marcados[clave];
        var suya = claveDe(dato);
        if (suya && claves.indexOf(suya) >= 0) {
          repetidos += 1;
          return;
        }
        anadirConDatos(tabla, dato);
        claves.push(suya);
      });
      marcados = {};
      ventana.cuerpo.querySelectorAll(".buscador-elegir").forEach(function (casilla) {
        casilla.checked = false;
      });
      refrescar();
      if (repetidos) {
        avisar(
          repetidos === 1
            ? "Esa línea ya está en la nota: no se repite."
            : repetidos + " líneas ya estaban en la nota y no se repiten."
        );
      }
      ventana.buscar();
    });

    var buscar = buscarCon(ventana, url, null, function (datos) {
      pintarResultados(
        ventana,
        (datos.resultados || []).map(function (dato) {
          return {
            dato: dato,
            celdas: delDocumento
              ? [dato.codigo_principal, dato.descripcion, dato.cantidad, dato.precio_unitario]
              : [dato.codigo_principal, dato.descripcion, dato.precio_unitario],
          };
        }),
        delDocumento
          ? ["Código", "Producto o servicio", "Cantidad", "Precio"]
          : ["Código", "Producto o servicio", "Precio"],
        function (fila, marcada) {
          if (marcada) marcados[fila.dato.pk] = fila.dato;
          else delete marcados[fila.dato.pk];
          refrescar();
        },
        true
      );
      // Lo que ya está en la nota se ve apagado y sin casilla: no se puede repetir.
      var claves = yaEnLaTabla(tabla);
      Array.prototype.forEach.call(ventana.cuerpo.querySelectorAll("tbody tr"), function (fila) {
        var celda = fila.children[1];
        var codigo = celda ? celda.textContent.trim() : "";
        if (!codigo || claves.indexOf(codigo) < 0) return;
        fila.classList.add("tenue");
        fila.title = "Ya está en la nota";
        var casilla = fila.querySelector(".buscador-elegir");
        if (casilla) {
          casilla.disabled = true;
          casilla.checked = false;
        }
      });
      if (!datos.resultados || !datos.resultados.length) {
        ventana.vacio.textContent = "No hay productos con eso. Pruebe con otra palabra.";
      }
    });
    buscar();
    refrescar();
  }

  /** El buscador del comprobante que modifica una nota: por fecha, tipo, cliente o número. */
  function buscarDocumento(barra) {
    if (!barra) return;
    var url = barra.dataset.url;
    var nombre = document.querySelector("[data-documento] .buscador-barra-campo");
    if (!url) return;

    var ventana = abrirVentana({
      titulo: "Buscar el comprobante que modifica",
      icono: "<span class=\"mif-books\"></span>",
      pista: "Número, clave o cliente…",
      vacio: "Busque el comprobante que corrige o anula.",
      filtros:
        '<div class="buscador-filtros" style="display:flex;gap:10px;flex-wrap:wrap;' +
        'align-items:center;padding:0 16px 10px">' +
        '<label class="etiqueta" for="buscar-desde">Desde</label>' +
        '<input type="date" id="buscar-desde" class="campo-fecha filtro-desde">' +
        '<label class="etiqueta" for="buscar-hasta">Hasta</label>' +
        '<input type="date" id="buscar-hasta" class="campo-fecha filtro-hasta">' +
        '<label class="etiqueta" for="buscar-tipo">Tipo</label>' +
        '<select id="buscar-tipo" class="filtro-tipo" data-role="select">' +
        '<option value="">Todos</option></select>' +
        "</div>",
      ancho: Math.min(880, window.innerWidth - 40),
      alto: Math.min(600, window.innerHeight - 80),
    });
    if (!ventana) return;

    var desde = ventana.caja.querySelector(".filtro-desde");
    var hasta = ventana.caja.querySelector(".filtro-hasta");
    var tipo = ventana.caja.querySelector(".filtro-tipo");

    // Del mes en curso, que es lo que se busca casi siempre; se puede cambiar.
    var hoy = new Date();
    var dosDigitos = function (valor) { return ("0" + valor).slice(-2); };
    desde.value = hoy.getFullYear() + "-" + dosDigitos(hoy.getMonth() + 1) + "-01";
    hasta.value =
      hoy.getFullYear() + "-" + dosDigitos(hoy.getMonth() + 1) + "-" + dosDigitos(hoy.getDate());

    function filtros() {
      return [
        ["desde", desde.value],
        ["hasta", hasta.value],
        ["tipo", tipo.value],
      ];
    }

    [desde, hasta, tipo].forEach(function (control) {
      control.addEventListener("change", function () { ventana.buscar(); });
    });

    function elegir(dato) {
      ponerEnLaCabecera("cod_doc_modificado", dato.tipo);
      ponerEnLaCabecera("num_doc_modificado", dato.numero);
      ponerEnLaCabecera("fecha_emision_doc_sustento", dato.fecha);
      if (nombre) nombre.value = apuntado(dato);
      // El cliente (o el proveedor, o el sujeto retenido) viene con el comprobante, y se
      // escribe al final: es lo último que se mira.
      ponerEnLaCabecera(dato.contraparte_campo, dato.contraparte_pk);
      ponerLaOtraParte(dato.contraparte_campo, dato.contraparte);
      cerrarVentanaBusqueda();
    }

    var buscar = buscarCon(ventana, url, filtros, function (datos) {
      if (datos.tipos) {
        Object.keys(datos.tipos).forEach(function (codigo) {
          var existe = Array.prototype.some.call(tipo.options, function (opcion) {
            return opcion.value === codigo;
          });
          if (existe) return;
          var opcion = document.createElement("option");
          opcion.value = codigo;
          opcion.textContent = datos.tipos[codigo];
          tipo.appendChild(opcion);
        });
      }
      pintarResultados(
        ventana,
        (datos.resultados || []).map(function (dato) {
          return {
            dato: dato,
            celdas: [dato.tipo_nombre, dato.numero, dato.fecha, dato.contraparte, dato.total],
          };
        }),
        ["Tipo", "Número", "Fecha", "Cliente o proveedor", "Total"],
        function (fila) { elegir(fila.dato); },
        false
      );
      if (!datos.resultados || !datos.resultados.length) {
        ventana.vacio.textContent =
          "No hay comprobantes autorizados con esos filtros. Pruebe otro mes.";
      }
    });
    buscar();
  }

  /** La clave con la que se reconoce una línea: su código o, si no, su descripción. */
  function claveDe(dato) {
    return String(dato.codigo_principal || "").trim() || String(dato.descripcion || "").trim();
  }

  /** Las claves de las líneas que ya están puestas en la tabla: esas no se repiten. */
  function yaEnLaTabla(tabla) {
    var claves = [];
    tabla.querySelectorAll("tbody tr").forEach(function (fila) {
      var codigo = fila.querySelector('[name$="-codigo_principal"]');
      var descripcion = fila.querySelector('[name$="-descripcion"]');
      var clave = (codigo && codigo.value.trim()) || (descripcion && descripcion.value.trim());
      if (clave) claves.push(clave);
    });
    return claves;
  }

  /** Un aviso de los de la casa, si Metro está a mano. */
  function avisar(texto) {
    if (window.Metro && window.Metro.toast) {
      window.Metro.toast.create({ message: texto, timeout: 4000 });
    }
  }

  /** Añade la línea del producto o servicio que se acaba de elegir. */
  function anadirConDatos(tabla, dato) {
    var fila = filaNueva(tabla);
    if (!fila) return;
    tabla.querySelector("tbody").appendChild(fila);
    poner(fila, "producto", dato.pk);
    poner(fila, "codigo_principal", dato.codigo_principal);
    poner(fila, "descripcion", dato.descripcion);
    poner(fila, "cantidad", dato.cantidad);
    poner(fila, "precio_unitario", dato.precio_unitario);
    poner(fila, "descuento", dato.descuento);
    poner(fila, "unidad_medida", dato.unidad_medida);
    poner(fila, "codigo_porcentaje_iva", dato.codigo_porcentaje_iva);
    pintarLinea(fila);
    var primera = fila.querySelector("input:not([type=hidden]), select");
    if (primera) primera.focus();
  }

  /* La fila de una tabla solo se lee: cada celda enseña lo que dice su campo.
   *
   * Los campos de verdad siguen ahí, escondidos, porque son los que viajan con el
   * formulario. Al cambiar uno (a mano, desde la ventana o porque se calculó solo)
   * su celda se vuelve a escribir.
   */
  function pintarLinea(fila) {
    if (!fila) return;
    Array.prototype.forEach.call(fila.querySelectorAll("[data-valor]"), function (celda) {
      var campo = fila.querySelector('[name$="-' + celda.dataset.valor + '"]');
      if (!campo) return;
      var texto = campo.value;
      if (campo.tagName === "SELECT") {
        var opcion = campo.options[campo.selectedIndex];
        texto = opcion ? opcion.textContent.trim() : "";
      }
      // Las fechas se leen como se leen aquí: 26/10/2026.
      if (campo.type === "date") texto = fechaCorta(texto);
      celda.textContent = texto;
      // El concepto de una retención es largo: en la celda se corta y aquí se lee.
      if (texto) celda.title = texto;
      else celda.removeAttribute("title");
    });
  }

  /** Una fecha ISO, como se escribe en la hoja. */
  function fechaCorta(valor) {
    var partes = (valor || "").split("-");
    if (partes.length !== 3) return valor || "";
    return partes[2] + "/" + partes[1] + "/" + partes[0];
  }

  /** El campo de esa fila, buscándolo por su nombre (el prefijo cambia en cada una). */
  function poner(fila, nombre, valor) {
    var campo = fila.querySelector('[name$="-' + nombre + '"]');
    if (!campo || valor === undefined || valor === null || valor === "") return;
    if (campo.tagName === "SELECT") ponerOpcion(campo, valor);
    else campo.value = valor;
  }

  /** El comprobante apuntado, como se lee en la barra: «Factura 001-001-000000033 · 13/10/2026». */
  function apuntado(dato) {
    var fecha = (dato.fecha || "").split("-");
    var cuando = fecha.length === 3 ? fecha[2] + "/" + fecha[1] + "/" + fecha[0] : dato.fecha;
    return dato.tipo_nombre + " " + dato.numero + (cuando ? " · " + cuando : "");
  }

  /** Lo que dice un campo de la cabecera del comprobante, si está. */
  function valorCabecera(nombre) {
    var campo = document.querySelector('[name="' + nombre + '"]');
    return campo ? campo.value.trim() : "";
  }

  /** Un campo de la cabecera del comprobante, por su nombre. */
  function ponerEnLaCabecera(nombre, valor) {
    var campo = document.querySelector('[name="' + nombre + '"]');
    if (campo && valor) campo.value = valor;
  }

  /** Escribe el nombre de la otra parte en la barra de su campo (el resto va oculto). */
  function ponerLaOtraParte(campo, nombre) {
    if (!campo || !nombre) return;
    var barra = document.querySelector(".buscador-barra[data-buscador]");
    var visible = barra && barra.querySelector(".buscador-barra-campo");
    if (visible) visible.value = nombre;
  }

  /** El botón de añadir de la tarjeta: del comprobante, del catálogo o en blanco. */
  function anadirDesdeLaVentana(boton) {
    var tabla = document.querySelector('table[data-formset="' + (boton.dataset.para || "") + '"]');
    if (!tabla) return;
    if (!boton.hasAttribute("data-productos")) {
      abrirVentanaFila(boton, null);
      return;
    }
    // Si ya se eligió el comprobante que se modifica, se ofrecen sus propias líneas:
    // una nota de crédito devuelve lo que se vendió en ese comprobante, no el catálogo.
    var tipo = valorCabecera("cod_doc_modificado");
    var numero = valorCabecera("num_doc_modificado");
    if (boton.dataset.items && tipo && numero) {
      buscarProducto(
        boton.dataset.items +
          "?tipo=" + encodeURIComponent(tipo) +
          "&numero=" + encodeURIComponent(numero),
        tabla,
        true
      );
      return;
    }
    buscarProducto(boton.dataset.url, tabla);
  }

  document.addEventListener("click", function (evento) {
    var boton = evento.target.closest(
      "[data-buscar], [data-buscar-doc], [data-anadir-fila], [data-anadir], " +
        "[data-editar-fila], [data-abrir-grupo], [data-anadir-grupo], [data-quitar], " +
        "[data-quitar-grupo], [data-buscar-retencion]"
    );
    if (boton) {
      evento.preventDefault();
      if (boton.hasAttribute("data-buscar-doc")) buscarDocumento(boton.closest(".buscador-barra"));
      else if (boton.hasAttribute("data-buscar-retencion"))
        buscarCodigoDeRetencion(boton.closest("[data-buscador-retencion]"));
      else if (boton.hasAttribute("data-anadir-fila")) anadirDesdeLaVentana(boton);
      else if (boton.hasAttribute("data-buscar")) buscarParte(boton.closest(".buscador-barra"));
      else if (boton.hasAttribute("data-quitar-grupo")) quitarGrupo(boton);
      else if (boton.hasAttribute("data-abrir-grupo")) abrirGrupo(prefijoDe(boton));
      else if (boton.hasAttribute("data-anadir-grupo")) anadirGrupo(boton);
      else if (boton.hasAttribute("data-quitar")) quitarFila(boton);
      else if (boton.hasAttribute("data-editar-fila")) abrirVentanaFila(boton, boton.closest("tr"));
      else abrirVentanaFila(boton, null);
      return;
    }
    // Cualquier parte de la fila de una cabecera abre su ventana.
    var fila = evento.target.closest("tr.grupo[data-grupo]");
    if (fila) abrirGrupo(fila.dataset.grupo);
  });

  /* En la tabla, la tarifa y los valores se calculan solos: al escribir la base
   * imponible o al elegir el porcentaje, la cifra de al lado se pone al día. */
  ["input", "change"].forEach(function (cual) {
    document.addEventListener(cual, function (evento) {
      var fila = evento.target.closest("tr.linea, .grupo-campos");
      if (!fila) return;
      // El concepto de la retención trae su impuesto y su porcentaje.
      if (evento.type === "change") retencionElegida(evento.target, fila);
      recalcular(fila);
    });
  });

  // La hoja arranca con las filas de la tabla de cabeceras puestas al día, que es lo que
  // se ve de cada una.
  document.querySelectorAll("table[data-grupos] tr.grupo[data-grupo]").forEach(function (fila) {
    pintarFila(fila.dataset.grupo);
  });
  // Y con las de las tablas de líneas, que también se leen.
  document.querySelectorAll("tr.linea").forEach(pintarLinea);
  refrescarVacio();

  // Si al enviar quedó algo mal dentro de una cabecera, se abre su ventana: lo que
  // falta está ahí dentro y en la hoja no se vería.
  var conFallo = document.querySelector("table[data-grupos] tr.con-fallo");
  if (conFallo) abrirGrupo(conFallo.dataset.grupo);

  // Enter en un campo no envía la hoja: aquí se escribe y se busca, no se guarda.
  document.addEventListener("keydown", function (evento) {
    if (evento.key !== "Enter") return;
    var campo = evento.target;
    if (campo.tagName === "INPUT" && campo.form) evento.preventDefault();
  });
})();
