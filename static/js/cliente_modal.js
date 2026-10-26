/* Alta rápida de un cliente desde la factura, en una ventana aparte.
 *
 * El formulario vive en una plantilla para no llenar la hoja de campos que casi
 * nunca se usan. Al abrirlo se arma la ventana, se inicializan los controles de
 * Metro y se conecta la consulta del RUC.
 */
(function () {
  "use strict";

  var abrir = document.getElementById("abrir-cliente-nuevo");
  var plantilla = document.getElementById("plantilla-cliente-nuevo");
  if (!plantilla) return;

  function abrirClienteNuevo(datos) {
    var formulario = plantilla.content.firstElementChild.cloneNode(true);

    Metro.dialog.create({
      title: "Facturar a alguien nuevo",
      content: formulario.outerHTML,
      closeButton: true,
      defaultActions: false,
      clsDialog: "dialogo-cliente",
      customButtons: [
        {
          text: "Guardar cliente",
          cls: "primary",
          onclick: function () {
            var dialogo = document.querySelector(".dialogo-cliente");
            var form = dialogo ? dialogo.querySelector("form") : null;
            if (!form) return;
            if (form.reportValidity()) form.requestSubmit();
          },
        },
        { text: "Cancelar", cls: "js-dialog-close" },
      ],
    });

    var dialogo = document.querySelector(".dialogo-cliente");
    if (!dialogo) return;
    if (Metro.initWidgets) {
      Metro.initWidgets(dialogo.querySelectorAll("[data-role]"));
    }
    if (window.prepararConsultaRuc) {
      window.prepararConsultaRuc(dialogo);
    }

    // Si venimos de una identificación que no existe, se deja escrita y con su
    // tipo ya elegido; solo falta completar razón social, dirección, etc.
    if (datos && datos.identificacion) {
      var identificacion = dialogo.querySelector('[name="identificacion"]');
      if (identificacion) identificacion.value = datos.identificacion;
      var tipo = dialogo.querySelector('[name="tipo_identificacion"]');
      var valor = datos.tipo || (datos.identificacion.length === 10 ? "05" : "04");
      if (tipo) {
        tipo.value = valor;
        var plugin = window.Metro && Metro.getPlugin
          ? Metro.getPlugin(tipo, "select")
          : null;
        if (plugin && typeof plugin.val === "function") plugin.val(valor);
      }
    }

    var primero = dialogo.querySelector('[name="razon_social"]')
      || dialogo.querySelector("input:not([type=hidden])");
    if (primero) primero.focus();
  }

  window.abrirClienteNuevo = abrirClienteNuevo;
  if (abrir) abrir.addEventListener("click", function () { abrirClienteNuevo(); });
})();
