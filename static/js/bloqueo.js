/* El bloqueo de la pantalla por inactividad, del lado del navegador.
 *
 * El que decide de verdad es el servidor (facturero/sesion.py): si la sesión está
 * bloqueada, cualquier página que se pida devuelve la pantalla de bloqueo. Aquí
 * solo se adelanta el aviso para no tener que recargar: pasados los minutos que
 * diga el servidor sin tocar nada, se enseña la misma pantalla encima y se espera
 * la clave. Al escribirla se la manda al servidor y, si es la buena, se sigue
 * donde se estaba.
 */
(function () {
  "use strict";

  var capa = document.querySelector("[data-bloqueo]");
  if (!capa) {
    return;
  }

  var minutos = Number.parseFloat(capa.dataset.minutos) || 0;
  if (minutos <= 0) {
    return;
  }

  var formulario = capa.querySelector("[data-bloqueo-form]");
  var clave = capa.querySelector("input[name=password]");
  var aviso = capa.querySelector("[data-bloqueo-error]");
  var reloj = null;
  var bloqueada = !capa.hidden;
  // ¿Es el aviso que se pone encima de la aplicación, o la pantalla entera que
  // manda el servidor? Cambia lo que se hace al desbloquear.
  var esCapa = capa.classList.contains("bloqueo-capa");

  if (bloqueada) {
    clave.focus();
  }

  function tapar() {
    if (bloqueada) {
      return;
    }
    bloqueada = true;
    capa.hidden = false;
    document.body.classList.add("pantalla-bloqueada");
    clave.focus();
  }

  function destapar() {
    bloqueada = false;
    capa.hidden = true;
    document.body.classList.remove("pantalla-bloqueada");
  }

  function reiniciar() {
    clearTimeout(reloj);
    if (bloqueada) {
      return;
    }
    // Un poco antes del límite del servidor, para que el aviso llegue a tiempo.
    reloj = setTimeout(tapar, Math.max(1000, minutos * 60 * 1000 - 5000));
  }

  ["mousemove", "mousedown", "keydown", "scroll", "touchstart", "focus"].forEach(function (evento) {
    window.addEventListener(evento, reiniciar, { passive: true });
  });

  // Volver a la pestaña después de un rato largo también cuenta como inactividad.
  document.addEventListener("visibilitychange", function () {
    reiniciar();
    if (document.visibilityState !== "visible" || bloqueada) {
      return;
    }
    fetch(window.location.pathname, {
      method: "HEAD",
      headers: { "X-Requested-With": "XMLHttpRequest" },
      credentials: "same-origin",
    })
      .then(function (respuesta) {
        if (respuesta.status === 423) {
          tapar();
        }
      })
      .catch(function () {});
  });

  formulario.addEventListener("submit", function (evento) {
    evento.preventDefault();
    aviso.hidden = true;

    var datos = new FormData(formulario);
    fetch(formulario.action, {
      method: "POST",
      body: datos,
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" },
    })
      .then(function (respuesta) {
        return respuesta.json().then(function (cuerpo) {
          return { ok: respuesta.ok, cuerpo: cuerpo };
        });
      })
      .then(function (resultado) {
        if (!resultado.ok) {
          aviso.textContent = resultado.cuerpo.error || "No se pudo desbloquear.";
          aviso.hidden = false;
          clave.value = "";
          clave.focus();
          return;
        }

        var destino = resultado.cuerpo.siguiente || "/";
        clave.value = "";

        if (!esCapa) {
          // La pantalla la mandó el servidor: no hay aplicación debajo que
          // enseñar, así que se va a la página en la que se estaba.
          window.location.href = destino;
          return;
        }

        destapar();
        reiniciar();
        if (destino !== window.location.pathname) {
          window.location.href = destino;
        }
      })
      .catch(function () {
        // Sin servidor a mano, que lo intente el navegador como siempre.
        formulario.submit();
      });
  });

  reiniciar();
})();
