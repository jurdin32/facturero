/* Lo poco que necesita la tienda en el navegador: cambiar la foto de la galería y
 * compartir la ficha. Todo lo demás —el carrito, el pedido— se resuelve en el
 * servidor, para que funcione igual con el JavaScript apagado.
 */
(function () {
  "use strict";

  function galeria() {
    var miniaturas = document.querySelectorAll("[data-foto]");
    var principal = document.getElementById("foto-principal");
    if (!principal) {
      return;
    }
    Array.prototype.forEach.call(miniaturas, function (miniatura) {
      miniatura.addEventListener("click", function () {
        principal.src = miniatura.getAttribute("data-foto");
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

  function arrancar() {
    galeria();
    compartir();
    estrellas();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", arrancar);
  } else {
    arrancar();
  }
})();
