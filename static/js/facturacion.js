/* La hoja de facturar: el buscador, las líneas y los totales.
 *
 * La tabla empieza vacía y se llena con lo que se elige en el buscador: cada
 * línea guarda, además de lo que se ve (descripción, cantidad y precio), lo que
 * el documento necesita y no se pregunta (el producto, su código, la unidad y la
 * tarifa de IVA). Eso viaja en campos ocultos del formset que ya venía pintado.
 *
 *   #lineas                  el cuerpo de la tabla de líneas
 *   #plantilla-linea         una línea vacía con __prefix__ en su sitio
 *   #plantilla-buscador      el modal, que sirve para clientes y para productos
 *   #totales                 el cuadro de totales
 *   #porcentajes-iva         las tarifas de IVA, tal como las conoce el paquete
 */
(function () {
  "use strict";

  // ------------------------------------------------------------------ números

  /* Una cifra puede venir escrita como se dice en Ecuador: 1.234,56 */
  function aNumero(texto) {
    if (texto === null || texto === undefined) return 0;
    var t = String(texto).replace(/\s|\u00a0/g, "");
    if (t === "") return 0;
    var coma = t.lastIndexOf(",");
    var punto = t.lastIndexOf(".");
    if (coma > -1 && punto > -1) {
      t = coma > punto ? t.replace(/\./g, "").replace(",", ".") : t.replace(/,/g, "");
    } else if (coma > -1) {
      t = t.replace(/\./g, "").replace(",", ".");
    }
    var n = parseFloat(t.replace(/[^0-9.eE+-]/g, ""));
    return isFinite(n) ? n : 0;
  }

  var IMPORTE = new Intl.NumberFormat("es-EC", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  function aImporte(n) {
    return IMPORTE.format(isFinite(n) ? n : 0);
  }

  /* Los precios llevan hasta seis decimales: se quitan los ceros que sobran. */
  function aPrecio(n) {
    var t = (Math.round(n * 1e6) / 1e6).toFixed(6).replace(/0+$/, "").replace(/\.$/, "");
    return t.replace(".", ",");
  }

  function aCantidad(n) {
    var t = (Math.round(n * 1e3) / 1e3).toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
    return t.replace(".", ",");
  }

  function porcentaje(codigo) {
    var tasa = tarifas[codigo];
    return tasa === undefined ? 0 : tasa;
  }

  function etiquetaIva(codigo) {
    var tasa = porcentaje(codigo);
    return "IVA " + aImporte(tasa * 100).replace(",00", "") + " %";
  }

  // ---------------------------------------------------------------- la tabla

  var cuerpo = document.getElementById("lineas");
  var tabla = document.getElementById("tabla-lineas");
  var molde = document.getElementById("plantilla-linea");
  var tarifas = leerTarifas();

  function leerTarifas() {
    var datos = document.getElementById("porcentajes-iva");
    var mapa = { "0": 0 };
    if (!datos) return mapa;
    try {
      var crudo = JSON.parse(datos.textContent);
      Object.keys(crudo).forEach(function (codigo) {
        mapa[codigo] = aNumero(crudo[codigo]) / 100;
      });
    } catch (e) {
      // Sin tarifas se factura con IVA cero, que es lo que hace el paquete.
    }
    return mapa;
  }

  function campo(fila, nombre) {
    return fila.querySelector('[name$="-' + nombre + '"]');
  }

  function valor(fila, nombre) {
    var entrada = campo(fila, nombre);
    return entrada ? entrada.value : "";
  }

  function poner(fila, nombre, dato) {
    var entrada = campo(fila, nombre);
    if (entrada) entrada.value = dato === undefined || dato === null ? "" : dato;
  }

  function filas() {
    return Array.prototype.slice.call(cuerpo.querySelectorAll("[data-linea]"));
  }

  function stockDisponible(producto, stockBase, excluir) {
    var total = aNumero(stockBase);
    filas().forEach(function (fila) {
      if (fila === excluir) return;
      var borrar = campo(fila, "DELETE");
      if (borrar && borrar.checked) return;
      if (String(valor(fila, "producto")) !== String(producto)) return;
      total -= aNumero(valor(fila, "cantidad"));
    });
    return total;
  }

  function notificarInventario(texto) {
    if (!texto || !window.Metro || !Metro.notify) return;
    Metro.notify.create(texto, "Inventario", {
      clsNotify: "notify-error",
      width: Math.min(380, window.innerWidth - 40),
      timeout: 5000,
    });
  }

  function limitarCantidad(fila) {
    if (!fila || fila.dataset.servicio === "1") return;
    var producto = valor(fila, "producto");
    if (!producto) return;
    var disponible = stockDisponible(producto, fila.dataset.stock || "0", fila);
    var cantidad = aNumero(valor(fila, "cantidad"));
    if (cantidad <= disponible) return;
    poner(fila, "cantidad", aCantidad(Math.max(disponible, 0)));
    notificarInventario(
      "Solo hay " + aCantidad(Math.max(disponible, 0)) + " de " +
      (valor(fila, "descripcion") || "ese producto") + "."
    );
  }

  /* El precio de una línea con producto es el del catálogo: se lee, no se toca. El
   * descuento sí se escribe, y es donde cae el foco. */
  function marcarPrecio(fila) {
    var entrada = campo(fila, "precio_unitario");
    if (!entrada) return;
    var catalogo = !!valor(fila, "producto");
    entrada.readOnly = catalogo;
    entrada.classList.toggle("solo-lectura", catalogo);
    entrada.title = catalogo ? "Es el precio del catálogo." : "";
  }

  /* El pie de la línea: lo que el documento lleva y no hace falta preguntar. */
  function refrescarPie(fila) {
    var pie = fila.querySelector("[data-pie]");
    if (!pie) return;
    var trozos = [valor(fila, "codigo_principal"), valor(fila, "unidad_medida")];
    var codigo = valor(fila, "codigo_porcentaje_iva") || "0";
    trozos.push(etiquetaIva(codigo));
    var texto = trozos.filter(Boolean).join(" · ");
    pie.textContent = texto;
    pie.hidden = !texto;
  }

  function sumarLinea(datos) {
    var disponible = null;
    if (datos && !datos.es_servicio) {
      disponible = stockDisponible(datos.pk, datos.existencia);
      if (disponible <= 0) {
        notificarInventario(
          "«" + (datos.descripcion || "Ese producto") + "» no tiene existencia."
        );
        return null;
      }
    }

    var fila = molde.content.firstElementChild.cloneNode(true);
    var cuenta = formulario.querySelector('input[name$="-TOTAL_FORMS"]');
    var indice = parseInt(cuenta.value, 10) || 0;

    // El prefijo del formset viaja en los name y en los id.
    Array.prototype.forEach.call(fila.querySelectorAll("[name],[id],[for]"), function (nodo) {
      ["name", "id", "for"].forEach(function (atributo) {
        var actual = nodo.getAttribute(atributo);
        if (actual && actual.indexOf("__prefix__") > -1) {
          nodo.setAttribute(atributo, actual.replace("__prefix__", indice));
        }
      });
    });
    cuenta.value = indice + 1;

    if (datos) {
      poner(fila, "producto", datos.pk);
      poner(fila, "codigo_principal", datos.codigo_principal);
      poner(fila, "codigo_auxiliar", datos.codigo_auxiliar);
      poner(fila, "unidad_medida", datos.unidad_medida);
      poner(fila, "descripcion", datos.descripcion);
      poner(fila, "precio_unitario", aPrecio(aNumero(datos.precio_unitario)));
      poner(fila, "codigo_porcentaje_iva", datos.codigo_porcentaje_iva || "0");
      poner(fila, "datos_adicionales", datos.datos_adicionales);
    }

    cuerpo.appendChild(fila);
    if (datos) {
      fila.dataset.stock = datos.existencia || "0";
      fila.dataset.servicio = datos.es_servicio ? "1" : "";
      if (disponible !== null && disponible < 1) {
        poner(fila, "cantidad", aCantidad(disponible));
      }
    }
    marcarPrecio(fila);
    refrescarPie(fila);
    calcular();

    // Con producto, el foco va a la cantidad: es lo siguiente que se escribe.
    var siguiente = campo(fila, datos ? "cantidad" : "descripcion");
    if (siguiente) siguiente.focus();
    return fila;
  }

  function quitarLinea(fila) {
    if (!fila) return;
    var borrar = campo(fila, "DELETE");
    if (borrar) {
      // Estaba guardada: se marca para borrar y se aparta a la vista.
      borrar.checked = true;
      fila.classList.add("tachada");
    } else {
      fila.parentNode.removeChild(fila);
    }
    calcular();
  }

  function calcular() {
    var bruto = 0;
    var descuentos = 0;
    var subtotal = 0;
    var porTarifa = {};
    var vivas = 0;

    filas().forEach(function (fila) {
      var borrar = campo(fila, "DELETE");
      var apartada = borrar && borrar.checked;
      if (!apartada) vivas += 1;

      var cantidad = aNumero(valor(fila, "cantidad"));
      var precio = aNumero(valor(fila, "precio_unitario"));
      var descuento = aNumero(valor(fila, "descuento"));
      var linea = cantidad * precio;
      if (linea < 0) linea = 0;
      var base = linea - descuento;
      if (base < 0) base = 0;

      var celda = fila.querySelector("[data-importe]");
      if (celda) celda.textContent = cantidad && precio ? aImporte(base) : "0,00";
      if (apartada) return;

      bruto += linea;
      descuentos += descuento;
      subtotal += base;
      var codigo = valor(fila, "codigo_porcentaje_iva") || "0";
      porTarifa[codigo] = (porTarifa[codigo] || 0) + base;
    });

    var iva = 0;
    Object.keys(porTarifa).forEach(function (codigo) {
      iva += porTarifa[codigo] * porcentaje(codigo);
    });

    pintarTotales(subtotal, iva, porTarifa, bruto, descuentos);
    marcarVacio(vivas === 0);
  }

  function marcarVacio(sinLineas) {
    var vacio = document.getElementById("lineas-vacio");
    if (vacio) vacio.hidden = !sinLineas;
    var caja = document.querySelector(".desliza");
    if (tabla && caja && caja.contains(tabla)) caja.hidden = sinLineas;
  }

  function pintarTotales(subtotal, iva, porTarifa, bruto, descuentos) {
    var caja = document.getElementById("totales");
    if (!caja) return;

    var html = [];
    // Con descuentos, el resumen los enseña: suma − descuento = subtotal, y así se
    // ve que todo cuadra sin sacar la cuenta a mano.
    if (descuentos > 0) {
      html.push(
        '<tr class="fila-suma"><th>Suma de líneas</th><td class="cifra" data-bruto>' +
          aImporte(bruto) +
          "</td></tr>"
      );
      html.push(
        '<tr class="fila-descuento"><th>Descuento</th><td class="cifra" data-descuento>−' +
          aImporte(descuentos) +
          "</td></tr>"
      );
    }
    html.push(
      '<tr><th>Subtotal</th><td class="cifra" data-subtotal>' + aImporte(subtotal) + "</td></tr>"
    );

    Object.keys(porTarifa)
      .sort(function (a, b) {
        return porcentaje(b) - porcentaje(a);
      })
      .forEach(function (codigo) {
        var base = porTarifa[codigo];
        if (base <= 0) return;
        html.push(
          '<tr class="fila-tarifa"><th>' +
            etiquetaIva(codigo) +
            ' <span class="tenue">sobre ' +
            aImporte(base) +
            "</span></th><td class=\"cifra\" data-iva>" +
            aImporte(base * porcentaje(codigo)) +
            "</td></tr>"
        );
      });

    html.push(
      '<tr class="total-final"><th>Total</th><td class="cifra" data-total>' +
        aImporte(subtotal + iva) +
        "</td></tr>"
    );
    caja.innerHTML = html.join("");
  }

  // --------------------------------------------------------------- el buscador

  // El aspecto de cada columna de la tabla del buscador. `mono` para los códigos
  // y las cifras, `num` para lo que se lee pegado a la derecha.
  var COLUMNAS = {
    producto: [
      { titulo: "Código", clase: "col-codigo", mono: true },
      { titulo: "Producto o servicio" },
      { titulo: "Precio", clase: "col-cifra", mono: true, num: true },
      { titulo: "IVA", clase: "col-iva", num: true },
      { titulo: "Stock", clase: "col-dato", mono: true, num: true },
    ],
  };

  var BUSQUEDAS = {
    producto: function () {
      return {
        tipo: "producto",
        titulo: "Buscar producto o servicio",
        icono: "<span class=\"mif-cube\"></span>",
        url: tabla ? tabla.dataset.urlProductos : "",
        pista: "Descripción o código…",
        vacio: "No hay productos con eso. Puede escribir la línea a mano.",
        // Los productos se eligen de varios en varios y no cierran la ventana.
        varios: true,
        columnas: COLUMNAS.producto,
        celda: function (dato) {
          return [
            dato.codigo_principal,
            dato.descripcion,
            aImporte(aNumero(dato.precio_unitario)),
            etiquetaIva(dato.codigo_porcentaje_iva || "0"),
            dato.es_servicio ? "—" : aCantidad(aNumero(dato.existencia)),
          ];
        },
        elegir: function (dato) {
          sumarLinea(dato);
        },
      };
    },
  };

  // La ventana se abre centrada y sin salirse de la pantalla. El `top`/`left` de
  // una ventana se mide desde su contenedor, no desde la ventana del navegador,
  // así que se corrige con el desvío que tenga en ese momento.
  function centrarVentana(marco) {
    if (!marco) return;
    var caja = marco.getBoundingClientRect();
    var desvioX = caja.left - (parseFloat(marco.style.left) || 0);
    var desvioY = caja.top - (parseFloat(marco.style.top) || 0);
    marco.style.left = Math.round((window.innerWidth - caja.width) / 2 - desvioX) + "px";
    marco.style.top = Math.round((window.innerHeight - caja.height) / 2 - desvioY) + "px";
  }

  // La ventana viva de Metro, si la hay.
  function ventanaAbierta(elemento) {
    return window.Metro.getPlugin(elemento, "window");
  }

  function cerrarVentanas() {
    Array.prototype.forEach.call(document.querySelectorAll(".ventana-buscador-win"), function (vieja) {
      var ventana = ventanaAbierta(vieja);
      if (ventana) ventana.close();
      else vieja.remove();
    });
  }

  function abrirBuscador(tipo, textoInicial) {
    var ajustes = BUSQUEDAS[tipo]();
    var plantilla = document.getElementById("plantilla-buscador");
    if (!ajustes.url || !plantilla || !window.Metro) return;

    cerrarVentanas();

    var varios = !!ajustes.varios;
    var ancho = Math.min(varios ? 780 : 620, window.innerWidth - 40);
    var alto = Math.min(varios ? 560 : 460, window.innerHeight - 80);

    // Una ventana de Metro: barra de título con su icono y sus botones, que se
    // arrastra y se estira. Dentro va el buscador de la plantilla.
    window.Metro.window.create({
      title: ajustes.titulo,
      icon: ajustes.icono,
      content: plantilla.innerHTML,
      width: ancho,
      height: alto,
      // La ventana lleva solo el botón de cerrar: se arrastra y se estira, pero
      // no se minimiza ni se maximiza.
      btnClose: true,
      btnMin: false,
      btnMax: false,
      draggable: true,
      resizable: true,
      shadow: true,
      clsWindow: "ventana-buscador-win",
      closeAction: window.Metro.actions.REMOVE,
    });

    var caja = document.querySelector(".ventana-buscador-win");
    if (!caja) return;

    // El buscador, dentro del componente de Metro si lo envolvió (su div se
    // queda con la clase y el input va dentro).
    var texto = caja.querySelector(".buscador-campo input");
    var cuerpo = caja.querySelector(".buscador-cuerpo");
    var vacio = caja.querySelector(".buscador-vacio");
    var pie = caja.querySelector(".buscador-pie");
    var cuenta = caja.querySelector(".buscador-cuenta");
    var botonAnadir = caja.querySelector("[data-anadir]");
    var botonCerrar = caja.querySelector("[data-cerrar]");
    var barra = document.getElementById("buscador-productos");
    var reloj = null;

    // Lo marcado, por producto: sigue marcado aunque cambie la búsqueda.
    var marcados = {};

    texto.placeholder = ajustes.pista;
    if (textoInicial) texto.value = textoInicial;
    if (pie) pie.hidden = !varios;

    // Al abrirla, Metro coloca el foco en la ventana y le da su propia posición:
    // se corrige un par de veces, salvo que el usuario ya la haya movido.
    var movida = false;
    var barraTitulo = caja.querySelector(".window-caption");
    if (barraTitulo) barraTitulo.addEventListener("pointerdown", function () { movida = true; });

    [0, 120, 300].forEach(function (retardo) {
      setTimeout(function () {
        if (movida || !document.contains(caja)) return;
        centrarVentana(caja);
        texto.focus({ preventScroll: true });
      }, retardo);
    });

    function cerrar() {
      document.removeEventListener("keydown", alEscape, true);
      // Lo buscado se queda en la barra de la hoja: así se sigue buscando sin
      // volver a escribirlo.
      if (ajustes.tipo === "producto" && barra) barra.value = texto.value;
      var ventana = ventanaAbierta(caja);
      if (ventana) ventana.close();
      else caja.remove();
    }

    // El Escape cierra la ventana mire donde mire el teclado.
    function alEscape(ev) {
      if (ev.key === "Escape") cerrar();
    }
    document.addEventListener("keydown", alEscape, true);

    if (botonCerrar) botonCerrar.addEventListener("click", cerrar);

    // ------------------------------------------------------------- lo elegido

    function elegidos() {
      return Object.keys(marcados).map(function (pk) {
        return marcados[pk];
      });
    }

    function refrescarCuenta() {
      var cuantos = elegidos().length;
      if (cuenta) {
        cuenta.textContent = cuantos
          ? cuantos + (cuantos === 1 ? " línea elegida" : " líneas elegidas")
          : "Ninguna línea elegida";
        cuenta.className = "buscador-cuenta" + (cuantos ? " fuerte" : "");
      }
      if (botonAnadir) {
        botonAnadir.disabled = cuantos === 0;
        botonAnadir.textContent = cuantos
          ? "Añadir " + cuantos + (cuantos === 1 ? " línea" : " líneas")
          : "Añadir al comprobante";
      }
      refrescarTodos();
    }

    /* La casilla de la cabecera: marcada si lo está todo lo que se ve, y a medias
     * si solo está marcada una parte. */
    function refrescarTodos() {
      var todos = cuerpo.querySelector(".buscador-todos");
      if (!todos) return;
      var casillas = Array.prototype.slice.call(cuerpo.querySelectorAll(".buscador-elegir"))
        .filter(function (casilla) {
          return !casilla.disabled;
        });
      var marcadas = casillas.filter(function (casilla) {
        return casilla.checked;
      }).length;
      todos.checked = casillas.length > 0 && marcadas === casillas.length;
      todos.indeterminate = marcadas > 0 && marcadas < casillas.length;
    }

    function anadirElegidos() {
      var primera = null;
      elegidos().forEach(function (dato) {
        var fila = sumarLinea(dato);
        if (!primera) primera = fila;
      });
      // El foco va a la cantidad de la primera: es lo siguiente que se escribe.
      if (primera) {
        var cantidad = campo(primera, "cantidad");
        if (cantidad) {
          cantidad.focus();
          cantidad.select();
        }
      }
      cerrar();
    }

    if (botonAnadir) botonAnadir.addEventListener("click", anadirElegidos);

    // ------------------------------------------------------------- la tabla

    function claseDe(columna, esCelda) {
      var clases = [];
      if (columna.clase) clases.push(columna.clase);
      if (esCelda && columna.mono) clases.push("cifra");
      if (columna.num) clases.push("num");
      return clases.join(" ");
    }

    function casillaTodos() {
      var casilla = document.createElement("input");
      casilla.type = "checkbox";
      casilla.className = "buscador-todos";
      casilla.title = "Elegir todo lo que se ve";
      casilla.addEventListener("change", function () {
        Array.prototype.forEach.call(cuerpo.querySelectorAll(".buscador-elegir"), function (otra) {
          if (otra.disabled) return;
          otra.checked = casilla.checked;
          if (casilla.checked) marcados[otra.dato.pk] = otra.dato;
          else delete marcados[otra.dato.pk];
        });
        refrescarCuenta();
      });
      return casilla;
    }

    function pintar(datos) {
      cuerpo.innerHTML = "";
      vacio.hidden = datos.length > 0;
      vacio.textContent = ajustes.vacio;
      cuerpo.hidden = datos.length === 0;
      if (!datos.length) {
        refrescarCuenta();
        return;
      }

      var tabla = document.createElement("table");
      tabla.className = "table small libro buscador-libro";

      var cabecera = document.createElement("tr");
      if (varios) {
        var thElegir = document.createElement("th");
        thElegir.className = "col-elegir";
        thElegir.appendChild(casillaTodos());
        cabecera.appendChild(thElegir);
      }
      ajustes.columnas.forEach(function (columna) {
        var th = document.createElement("th");
        th.textContent = columna.titulo;
        th.className = claseDe(columna, false);
        cabecera.appendChild(th);
      });
      var thead = document.createElement("thead");
      thead.appendChild(cabecera);
      tabla.appendChild(thead);

      var tbody = document.createElement("tbody");
      datos.forEach(function (dato) {
        var fila = document.createElement("tr");
        fila.dato = dato;

        if (varios) {
          var tdElegir = document.createElement("td");
          tdElegir.className = "col-elegir";
          var casilla = document.createElement("input");
          casilla.type = "checkbox";
          casilla.className = "buscador-elegir";
          casilla.dato = dato;
          casilla.checked = Object.prototype.hasOwnProperty.call(marcados, dato.pk);
          if (!dato.es_servicio && aNumero(dato.existencia) <= 0) {
            casilla.disabled = true;
            casilla.title = "Sin existencia";
            fila.classList.add("sin-stock");
          }
          tdElegir.appendChild(casilla);
          fila.appendChild(tdElegir);
        }

        ajustes.celda(dato).forEach(function (valor, indice) {
          var columna = ajustes.columnas[indice] || {};
          var td = document.createElement("td");
          td.className = claseDe(columna, true);
          td.textContent = valor === null || valor === undefined || valor === "" ? "—" : valor;
          fila.appendChild(td);
        });

        tbody.appendChild(fila);
      });
      tabla.appendChild(tbody);
      cuerpo.appendChild(tabla);
      refrescarCuenta();
    }

    /* Al hacer clic en una fila: al cliente se lo lleva y se cierra; el producto
     * se marca y la ventana sigue abierta, que es para elegir varios. */
    cuerpo.addEventListener("click", function (ev) {
      var fila = ev.target.closest("tr");
      if (!fila || !fila.dato) return;
      if (!varios) {
        cerrar();
        ajustes.elegir(fila.dato);
        return;
      }
      var casilla = fila.querySelector(".buscador-elegir");
      if (!casilla || casilla.disabled) return;
      if (ev.target !== casilla) casilla.checked = !casilla.checked;
      if (casilla.checked) marcados[fila.dato.pk] = fila.dato;
      else delete marcados[fila.dato.pk];
      refrescarCuenta();
    });

    function buscar() {
      var textoBuscado = texto.value.trim();
      fetch(ajustes.url + "?q=" + encodeURIComponent(textoBuscado), {
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" },
      })
        .then(function (respuesta) {
          return respuesta.ok ? respuesta.json() : { resultados: [] };
        })
        .then(function (datos) {
          pintar(datos.resultados || []);
        })
        .catch(function () {
          pintar([]);
        });
    }

    texto.addEventListener("input", function () {
      clearTimeout(reloj);
      reloj = setTimeout(buscar, 220);
    });

    texto.addEventListener("keydown", function (ev) {
      if (ev.key !== "Enter") return;
      ev.preventDefault();
      if (varios) {
        // Con algo marcado, Enter lo añade; si no, marca el primero de la lista.
        if (elegidos().length) anadirElegidos();
        else {
          var primera = cuerpo.querySelector(".buscador-elegir");
          if (primera) primera.click();
        }
        return;
      }
      var primero = cuerpo.querySelector("tbody tr");
      if (primero && primero.dato) {
        cerrar();
        ajustes.elegir(primero.dato);
      }
    });

    buscar();
  }

  // ------------------------------------------------------------------ el cliente

  var clienteCaja = null;
  var campoIdentificacion = null;
  var campoTipoCliente = null;
  var avisoCliente = null;
  var completarCliente = null;
  var clienteTurno = 0;
  var clienteTemporizador = null;
  var clienteEspera = null;
  var clienteConsultando = false;
  var ultimoNumero = "";
  // El documento que ya está cargado: no se vuelve a consultar ni se avisa otra
  // vez al salir del campo o al volver a él.
  var clienteCargado = "";
  // Mientras se pinta el cliente, los `change` que dispara Metro no son del
  // usuario: no deben borrarlo ni lanzar otra consulta.
  var poniendoCliente = false;

  function soloDigitos(texto) {
    return String(texto || "").replace(/\D/g, "");
  }

  function tipoDe(numero) {
    if (numero.length === 10) return "05";
    if (numero.length === 13) return "04";
    return "";
  }

  var NOMBRES_TIPO = {
    "04": "RUC",
    "05": "Cédula",
    "06": "Pasaporte",
    "07": "Consumidor final",
    "08": "Identificación del exterior",
  };

  function nombreTipo(tipo) {
    return NOMBRES_TIPO[tipo] || "";
  }

  function tipoManual() {
    return campoTipoCliente ? campoTipoCliente.value : "auto";
  }

  function normalizarDocumento(texto, tipo) {
    if (tipo === "auto" || tipo === "04" || tipo === "05" || tipo === "07") {
      return soloDigitos(texto);
    }
    return String(texto || "").trim().toUpperCase();
  }

  function tipoElegido(numero, manual) {
    return manual && manual !== "auto" ? manual : tipoDe(numero);
  }

  function avisoDeCliente(texto, clase) {
    if (!avisoCliente) return;
    avisoCliente.textContent = texto || "";
    avisoCliente.className = "ayuda" + (clase ? " aviso-cliente-" + clase : "");
  }

  function mostrarCompletar(visible) {
    if (completarCliente) completarCliente.hidden = !visible;
  }

  function notificarCliente(texto, tipo) {
    if (!texto || !window.Metro || !Metro.notify) return;
    Metro.notify.create(texto, "Cliente", {
      clsNotify: tipo === "ok" ? "notify-cliente-ok" : "",
      width: Math.min(380, window.innerWidth - 40),
      timeout: tipo === "ok" ? 6000 : 4000,
    });
  }

  function limpiarCliente(mensaje) {
    var select = document.getElementById("id_receptor");
    if (select) select.value = "";
    var nombre = document.getElementById("cliente-nombre");
    var datos = document.getElementById("cliente-datos");
    if (nombre) nombre.textContent = "— sin cliente —";
    if (datos) datos.textContent = "";
    if (mensaje) avisoDeCliente(mensaje, "error");
  }

  function ponerCliente(dato) {
    poniendoCliente = true;
    try {
      pintarCliente(dato);
    } finally {
      // El `change` del select de Metro llega después del propio manejador.
      window.setTimeout(function () {
        poniendoCliente = false;
      }, 0);
    }
  }

  function pintarCliente(dato) {
    var select = document.getElementById("id_receptor");
    if (select && dato.pk) {
      var existe = Array.prototype.some.call(select.options, function (opcion) {
        return String(opcion.value) === String(dato.pk);
      });
      if (!existe) {
        select.add(new Option(dato.razon_social || dato.identificacion, dato.pk, true, true));
      }
      select.value = dato.pk;
    }

    var nombre = document.getElementById("cliente-nombre");
    var datos = document.getElementById("cliente-datos");
    if (nombre) nombre.textContent = dato.razon_social || "— sin cliente —";
    if (datos) {
      var tipo = dato.tipo_identificacion || tipoDe(soloDigitos(dato.identificacion));
      datos.textContent = [dato.identificacion, dato.direccion, nombreTipo(tipo)]
        .filter(Boolean)
        .join(" · ");
    }
    // El tipo solo se cambia si el usuario lo eligió a mano. Con «detectar solo»
    // el select se queda así: si no, tras los 10 dígitos se quedaría en cédula y
    // ya no dejaría escribir el resto del RUC.
    var manual = campoTipoCliente ? campoTipoCliente.value : "auto";
    if (dato.tipo_identificacion && campoTipoCliente && manual !== "auto") {
      campoTipoCliente.value = dato.tipo_identificacion;
      var pluginTipo = window.Metro && Metro.getPlugin
        ? Metro.getPlugin(campoTipoCliente, "select")
        : null;
      if (pluginTipo && typeof pluginTipo.val === "function") {
        pluginTipo.val(dato.tipo_identificacion);
      }
    }
    // Si se está escribiendo el número, no se toca: pisarlo perdía los dígitos
    // que el usuario ya había tecleado.
    if (campoIdentificacion && dato.identificacion && !campoIdentificacion.value.trim()) {
      campoIdentificacion.value = dato.identificacion;
    }
  }

  function tokenCsrf() {
    var campo = document.querySelector("[name=csrfmiddlewaretoken]");
    return campo ? campo.value : "";
  }

  function cerrarEsperaCliente() {
    if (clienteEspera && window.Metro && Metro.activity) {
      Metro.activity.close(clienteEspera);
    }
    clienteEspera = null;
  }

  function identificarCliente(identificacion, tipo) {
    var url = clienteCaja ? clienteCaja.dataset.urlIdentificar : "";
    var manual = tipo || "auto";
    var numero = normalizarDocumento(identificacion, manual);
    if (!url || !numero) return;
    if (manual === "auto" && numero.length !== 10 && numero.length !== 13) return;
    if (manual === "04" && numero.length !== 13) return;
    if (manual === "05" && numero.length !== 10) return;
    if (manual === "06" || manual === "08") {
      if (numero.length < 3) return;
    }
    var marca = numero + "|" + manual;
    if (marca === clienteCargado) return;
    if (clienteConsultando && marca === ultimoNumero) return;

    clienteConsultando = true;
    ultimoNumero = marca;
    cerrarEsperaCliente();
    var esteTurno = ++clienteTurno;
    // Igual que al autorizar: el anillo tapa la pantalla mientras el SRI responde.
    if (window.Metro && Metro.activity) {
      clienteEspera = Metro.activity.open({
        text: "Obteniendo datos del SRI…",
        type: "metro",
        style: "color",
      });
    }
    fetch(url, {
      method: "POST",
      headers: {
        "X-CSRFToken": tokenCsrf(),
        "Content-Type": "application/x-www-form-urlencoded",
        Accept: "application/json",
      },
      body: new URLSearchParams({
        identificacion: numero,
        tipo_identificacion: manual,
      }).toString(),
      credentials: "same-origin",
    })
      .then(function (respuesta) {
        if (!respuesta.ok) throw new Error("No se pudo consultar la identificación.");
        return respuesta.json();
      })
      .then(function (datos) {
        if (esteTurno !== clienteTurno) return;
        clienteConsultando = false;
        cerrarEsperaCliente();
        if (!datos.encontrado) {
          limpiarCliente(datos.mensaje || "No se encontró la identificación.");
          mostrarCompletar(true);
          // Una cédula de 10 dígitos siempre puede registrarse a mano: si el SRI
          // está caído, no se puede dejar al usuario sin el formulario.
          if (
            (datos.pedir_datos || numero.length === 10)
            && window.abrirClienteNuevo
            && !document.querySelector(".dialogo-cliente")
          ) {
            // Se abre después de cerrar la espera, para que no quede detrás.
            window.setTimeout(function () {
              if (!document.querySelector(".dialogo-cliente")) {
                window.abrirClienteNuevo({
                  identificacion: numero,
                  tipo: manual !== "auto" ? manual : tipoDe(numero),
                });
              }
            }, 0);
          }
          return;
        }

        mostrarCompletar(false);
        ponerCliente(datos.cliente || {});
        clienteCargado = marca;
        avisoDeCliente("", "");
        // Si el cliente ya estaba guardado se cargan sus datos y nada más: el
        // aviso solo tiene sentido cuando se acaba de crear la ficha.
        if (!datos.nuevo) return;
        var mensaje = datos.mensaje || "Cliente agregado al catálogo.";
        if (datos.origen === "sri" && datos.sri) {
          var detalles = [datos.sri.estado, datos.sri.regimen, datos.sri.actividad_economica]
            .filter(Boolean);
          if (detalles.length) mensaje += " " + detalles.join(" · ");
        }
        notificarCliente(mensaje, "ok");
      })
      .catch(function () {
        if (esteTurno === clienteTurno) {
          clienteConsultando = false;
          cerrarEsperaCliente();
          limpiarCliente("No se pudo consultar la identificación. Inténtelo de nuevo.");
          mostrarCompletar(true);
        }
      });
  }

  /* Sin JavaScript queda el desplegable de siempre; con él, el campo de cédula o
   * RUC hace el trabajo. El desplegable se aparta, no se borra: es el que lleva
   * el cliente en el envío. */
  function montarCliente() {
    var caja = document.getElementById("cliente-caja");
    var desplegable = document.getElementById("cliente-desplegable");
    var select = document.getElementById("id_receptor");
    if (!caja || !desplegable || !select) return;

    clienteCaja = caja;
    campoIdentificacion = document.getElementById("cliente-identificacion");
    campoTipoCliente = document.getElementById("cliente-tipo-documento");
    avisoCliente = document.getElementById("cliente-aviso");
    completarCliente = document.getElementById("cliente-completar");
    caja.hidden = false;

    if (completarCliente) {
      completarCliente.addEventListener("click", function () {
        var manual = tipoManual();
        var numero = normalizarDocumento(campoIdentificacion.value, manual);
        var tipo = tipoElegido(numero, manual);
        if (
          window.abrirClienteNuevo
          && numero
          && tipo
          && !document.querySelector(".dialogo-cliente")
        ) {
          window.abrirClienteNuevo({ identificacion: numero, tipo: tipo });
        }
      });
    }

    // La fecha y la forma de pago se mudan a su fila: cada campo, una sola vez.
    var fila = document.getElementById("fecha-forma-pago");
    if (fila) {
      ["id_fecha_emision", "id_forma_pago"].forEach(function (id) {
        var entrada = document.getElementById(id);
        var campoCaja = entrada && entrada.closest(".campo-caja");
        if (campoCaja) fila.appendChild(campoCaja.closest("[class*='cell']") || campoCaja);
      });
      fila.hidden = false;
    }

    var columna = select.closest("[class*='cell']") || select.closest(".campo-caja");
    if (columna) columna.hidden = true;
    desplegable.hidden = true;

    function revisarIdentificacion() {
      // Lo que cambia el propio código al cargar el cliente no es una edición.
      if (poniendoCliente) return;
      window.clearTimeout(clienteTemporizador);
      mostrarCompletar(false);
      var manual = tipoManual();
      var crudo = campoIdentificacion.value;
      var numero = normalizarDocumento(crudo, manual);
      var tipo = tipoElegido(numero, manual);

      if (tipo) {
        avisoDeCliente("Tipo: " + nombreTipo(tipo) + ".", "info");
      } else if (String(crudo || "").trim()) {
        avisoDeCliente("Elija el tipo de documento si es pasaporte u otro.", "info");
      }

      // Si cambia el número o el tipo, el cliente que estaba elegido deja de valer.
      if (select.value) {
        select.value = "";
        clienteCargado = "";
        var nombre = document.getElementById("cliente-nombre");
        var datos = document.getElementById("cliente-datos");
        if (nombre) nombre.textContent = "— sin cliente —";
        if (datos) datos.textContent = "";
      }

      var retardo = null;
      if (manual === "auto") {
        if (numero.length === 10) retardo = 250;
        else if (numero.length === 13) retardo = 0;
      } else if (manual === "04" && numero.length === 13) {
        retardo = 0;
      } else if (manual === "05" && numero.length === 10) {
        retardo = 250;
      } else if ((manual === "06" || manual === "08") && numero.length >= 3) {
        retardo = 700;
      } else if (manual === "07" && numero.length >= 1) {
        retardo = 700;
      }
      if (retardo === null) return;

      clienteTemporizador = window.setTimeout(function () {
        identificarCliente(numero, manual);
      }, retardo);
    }

    // Una factura que ya trae cliente (borrador o ?cliente=) muestra su número.
    if (select.value) {
      var consultar = caja.dataset.urlConsultar;
      if (consultar) {
        fetch(consultar + "?cliente=" + encodeURIComponent(select.value), {
          headers: { Accept: "application/json" },
        })
          .then(function (respuesta) {
            return respuesta.ok ? respuesta.json() : null;
          })
          .then(function (datos) {
            if (datos && datos.encontrado) ponerCliente(datos.cliente || {});
          })
          .catch(function () {});
      }
    }

    if (!campoIdentificacion) return;
    campoIdentificacion.addEventListener("input", revisarIdentificacion);
    if (campoTipoCliente) {
      campoTipoCliente.addEventListener("change", revisarIdentificacion);
    }
    campoIdentificacion.addEventListener("blur", function () {
      // Al abrir el formulario manual el campo pierde el foco: no se consulta otra vez.
      if (document.querySelector(".dialogo-cliente")) return;
      var manual = tipoManual();
      var numero = normalizarDocumento(campoIdentificacion.value, manual);
      if (numero) identificarCliente(numero, manual);
    });
  }

  // ----------------------------------------------------------------- arranque

  if (!cuerpo || !molde) {
    montarCatalogo();
    return;
  }

  var formulario = cuerpo.closest("form");

  montarCliente();

  // La barra de la hoja: al hacer clic —o al pulsar Enter— se abre el buscador
  // con lo que haya escrito, y las coincidencias se ven en una tabla.
  function textoDeLaBarra() {
    var campo = document.getElementById("buscador-productos");
    return campo ? campo.value.trim() : "";
  }

  function buscarProductos() {
    abrirBuscador("producto", textoDeLaBarra());
  }

  /* Se escucha en el documento, no en el campo: Metro envuelve el input al
   * arrancar y puede rehacerlo, así que un oyente puesto en él se perdería. Y en
   * el Enter hay que adelantarse al envío del formulario, que es lo que hace el
   * navegador por su cuenta cuando el campo está dentro de un `form`. */
  function esDeLaBarra(nodo) {
    return !!(nodo && nodo.closest && nodo.closest(".buscador-barra"));
  }

  document.addEventListener("click", function (ev) {
    if (ev.target.closest(".input-clear-button")) return; // el aspa de borrar
    if (esDeLaBarra(ev.target)) buscarProductos();
  });

  document.addEventListener(
    "keydown",
    function (ev) {
      if (ev.key !== "Enter" || !esDeLaBarra(ev.target)) return;
      ev.preventDefault(); // que no se envíe la factura
      buscarProductos();
    },
    true
  );

  // El botón viejo de «Añadir producto o servicio» ya no está: se añade desde el
  // buscador de la barra. Si quedara en alguna página antigua, se sigue escuchando.
  var anadirLinea = document.getElementById("anadir-linea");
  if (anadirLinea) anadirLinea.addEventListener("click", buscarProductos);

  var suelta = document.getElementById("anadir-suelta");
  if (suelta) {
    suelta.addEventListener("click", function () {
      sumarLinea();
    });
  }

  cuerpo.addEventListener("input", function (ev) {
    var nombre = ev.target.name || "";
    if (/-cantidad$/.test(nombre)) {
      limitarCantidad(ev.target.closest("[data-linea]"));
    }
    if (/-cantidad$|-precio_unitario$|-descuento$|-descripcion$/.test(nombre)) calcular();
  });

  cuerpo.addEventListener("click", function (ev) {
    var botonQuitar = ev.target.closest("[data-quitar]");
    if (botonQuitar) {
      ev.preventDefault();
      quitarLinea(botonQuitar.closest("[data-linea]"));
    }
  });

  cuerpo.addEventListener("keydown", function (ev) {
    // Enter en una línea llama al buscador: se factura añadiendo, no tecleando.
    // Lo que haya escrito en la descripción viaja al buscador.
    if (ev.key === "Enter") {
      ev.preventDefault();
      var fila = ev.target.closest("[data-linea]");
      var escrito = fila ? (valor(fila, "descripcion") || "").trim() : "";
      abrirBuscador("producto", escrito || textoDeLaBarra());
    }
  });

  filas().forEach(refrescarPie);
  filas().forEach(marcarPrecio);
  calcular();
  montarCatalogo();

  // -------------------------------------------------- el formulario del catálogo

  function montarCatalogo() {
    var bloque = document.getElementById("bloque-inventario");
    var tipo = document.getElementById("id_tipo");
    if (!bloque || !tipo) return;
    function mirar() {
      // Un servicio no se agota: su bloque de inventario sólo estorba.
      bloque.hidden = tipo.value === "servicio";
    }
    tipo.addEventListener("change", mirar);
    mirar();
  }
})();
