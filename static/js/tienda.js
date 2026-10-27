/* Lo poco que necesita la tienda en el navegador: cambiar la foto de la galería y
 * compartir la ficha. Todo lo demás —el carrito, el pedido— se resuelve en el
 * servidor, para que funcione igual con el JavaScript apagado.
 */
(function () {
  "use strict";

  /* La foto grande cambia de `<img>` a `<video>` según lo que se pulse: un video
   * necesita sus controles y no se puede pintar con un `src` de imagen. */
  function ponerEnLaGaleria(caja, direccion, video) {
    var actual = caja.querySelector("img, video");
    var nuevo;
    if (video) {
      nuevo = document.createElement("video");
      nuevo.src = direccion;
      nuevo.controls = true;
      nuevo.autoplay = true;
      nuevo.playsInline = true;
    } else {
      nuevo = document.createElement("img");
      nuevo.src = direccion;
      nuevo.alt = actual ? actual.getAttribute("alt") || "" : "";
    }
    nuevo.id = "foto-principal";
    if (actual) {
      actual.parentNode.replaceChild(nuevo, actual);
    } else {
      caja.appendChild(nuevo);
    }
  }

  function galeria() {
    var miniaturas = document.querySelectorAll("[data-foto]");
    var caja = document.getElementById("foto-principal-caja");
    if (!caja) {
      return;
    }
    Array.prototype.forEach.call(miniaturas, function (miniatura) {
      miniatura.addEventListener("click", function () {
        ponerEnLaGaleria(
          caja,
          miniatura.getAttribute("data-foto"),
          miniatura.getAttribute("data-video") === "1"
        );
        Array.prototype.forEach.call(miniaturas, function (otra) {
          otra.classList.remove("activa");
        });
        miniatura.classList.add("activa");
      });
    });
  }

  function avisar(boton, texto) {
    var antes = boton.textContent;
    boton.textContent = texto;
    window.setTimeout(function () {
      boton.textContent = antes;
    }, 2000);
  }

  function compartir() {
    var botones = document.querySelectorAll("[data-compartir]");
    Array.prototype.forEach.call(botones, function (boton) {
      boton.addEventListener("click", function () {
        var direccion = boton.getAttribute("data-compartir");
        if (navigator.share) {
          navigator.share({ url: direccion }).catch(function () {});
          return;
        }
        if (navigator.clipboard) {
          navigator.clipboard.writeText(direccion).then(function () {
            avisar(boton, "Enlace copiado");
          });
        }
      });
    });
  }

  function estrellas() {
    var elige = document.querySelectorAll("[data-estrellas-texto]");
    Array.prototype.forEach.call(elige, function (texto) {
      var grupo = texto.parentNode.querySelector(".estrellas-elige");
      if (!grupo) {
        return;
      }
      grupo.addEventListener("change", function () {
        var elegida = grupo.querySelector("input:checked");
        var rotulo = elegida ? grupo.querySelector('label[for="' + elegida.id + '"]') : null;
        texto.textContent = rotulo ? rotulo.getAttribute("title") : "";
      });
    });
  }

  /* El carrito, sin botones: al cambiar la cantidad se manda sola y los importes se
   * repintan con lo que responde el servidor. Sin JavaScript queda el botón de
   * siempre, que envía el formulario completo.
   */
  function carrito() {
    var caja = document.querySelector("[data-carrito]");
    if (!caja || !window.fetch || !window.FormData) {
      return;
    }
    var direccion = caja.getAttribute("data-url");
    var formulario = caja.querySelector("form");
    var testigo = caja.querySelector("input[name=csrfmiddlewaretoken]");
    var contador = document.querySelector(".carrito-enlace .contador");

    var sobra = caja.querySelector(".solo-sin-js");
    if (sobra) {
      sobra.style.display = "none";
    }

    function filaDe(elemento) {
      return elemento.closest("tr");
    }

    function poner(selector, texto) {
      var sitio = caja.querySelector(selector);
      if (sitio) {
        sitio.textContent = texto;
      }
    }

    function pintar(datos, fila) {
      if (datos.quitada) {
        if (fila && fila.parentNode) {
          fila.parentNode.removeChild(fila);
        }
      } else if (fila) {
        var subtotal = fila.querySelector("[data-subtotal]");
        if (subtotal) {
          subtotal.textContent = "$ " + datos.linea;
        }
      }
      poner("[data-subtotal-resumen]", "$ " + datos.subtotal);
      poner("[data-iva]", "$ " + datos.iva);
      poner("[data-total]", "$ " + datos.total);
      if (contador) {
        contador.textContent = datos.unidades;
      }
      if (datos.vacia) {
        window.location.reload();
      }
    }

    function enviar(producto, cantidad, fila) {
      var cuerpo = new FormData();
      cuerpo.append("producto", producto);
      cuerpo.append("cantidad", cantidad);
      if (testigo) {
        cuerpo.append("csrfmiddlewaretoken", testigo.value);
      }
      if (fila) {
        fila.classList.add("guardando");
      }
      function terminar() {
        if (fila) {
          fila.classList.remove("guardando");
        }
      }
      fetch(direccion, {
        method: "POST",
        body: cuerpo,
        headers: { "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin"
      })
        .then(function (respuesta) { return respuesta.json(); })
        .then(function (datos) {
          terminar();
          if (datos && datos.ok) {
            pintar(datos, fila);
          }
        })
        .catch(terminar);
    }

    caja.addEventListener("input", function (evento) {
      var campo = evento.target.closest("[data-cantidad]");
      if (!campo || campo.value === "") {
        return;
      }
      window.clearTimeout(campo.espera);
      campo.espera = window.setTimeout(function () {
        enviar(campo.getAttribute("data-producto"), campo.value, filaDe(campo));
      }, 350);
    });

    caja.addEventListener("change", function (evento) {
      var campo = evento.target.closest("[data-cantidad]");
      if (!campo) {
        return;
      }
      window.clearTimeout(campo.espera);
      enviar(campo.getAttribute("data-producto"), campo.value, filaDe(campo));
    });

    caja.addEventListener("click", function (evento) {
      var boton = evento.target.closest("[data-quitar]");
      if (!boton) {
        return;
      }
      evento.preventDefault();
      enviar(boton.getAttribute("data-quitar"), "0", filaDe(boton));
    });

    if (formulario) {
      // Con el carrito al día no hay nada que enviar: Enter no recarga la página.
      formulario.addEventListener("submit", function (evento) {
        evento.preventDefault();
      });
    }
  }

  function arrancar() {
    galeria();
    compartir();
    estrellas();
    carrito();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", arrancar);
  } else {
    arrancar();
  }
})();
