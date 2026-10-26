/* Lo poco que necesita la pantalla de entrar: el panel de opciones.
 *
 * Sin JavaScript no se pierde nada: el formulario se envía igual y el navegador
 * ofrece lo de siempre (recordar la clave, verla en el llavero del sistema).
 */
(function () {
  "use strict";

  var boton = document.getElementById("opciones-entrada");
  var panel = document.getElementById("panel-entrada");
  if (!boton || !panel) {
    return;
  }

  boton.addEventListener("click", function () {
    var abierto = panel.hidden;
    panel.hidden = !abierto;
    boton.setAttribute("aria-expanded", abierto ? "true" : "false");
  });

  var clave = document.getElementById("id_password");
  var usuario = document.getElementById("id_username");

  var ver = document.getElementById("ver-clave");
  if (ver && clave) {
    ver.addEventListener("click", function () {
      var oculta = clave.type === "password";
      clave.type = oculta ? "text" : "password";
      ver.innerHTML = oculta
        ? '<span class="mif-eye" aria-hidden="true"></span> Ocultar la clave'
        : '<span class="mif-eye" aria-hidden="true"></span> Ver la clave';
      clave.focus();
    });
  }

  var limpiar = document.getElementById("limpiar-campos");
  if (limpiar) {
    limpiar.addEventListener("click", function () {
      if (usuario) {
        usuario.value = "";
        usuario.focus();
      }
      if (clave) {
        clave.value = "";
      }
    });
  }
})();
