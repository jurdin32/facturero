/* Imprimir un comprobante: un solo diálogo, y en la misma pestaña.
 *
 * El tamaño del papel no es lo mismo en el mostrador que en la oficina: en caja
 * hay una impresora de tíquets y en la oficina, una de hojas. Al pulsar «imprimir»
 * sale un diálogo que lo pregunta —el tíquet de 80 mm viene marcado, que es el de
 * todos los días— y, al elegir, el RIDE se abre en esta misma pestaña ya con la
 * orden de imprimir. No se abren ventanas nuevas: el diálogo del navegador, si no
 * hay impresora, deja guardarlo como PDF.
 *
 * Se usa con `data-imprimir="<dirección del RIDE>"` en cualquier enlace o botón.
 */
(function () {
  "use strict";

  //: Lo que se explica en el diálogo.
  function ayuda() {
    return (
      "Se va a imprimir el comprobante. Elija el formato: el tíquet de 80 mm es el de " +
      "la impresora de caja y el A4, el de la impresora normal. Si no tiene impresora, " +
      "en la ventana de imprimir elija «Guardar como PDF»."
    );
  }

  function conFormato(base, formato) {
    var union = base.indexOf("?") === -1 ? "?" : "&";
    return base + union + "formato=" + formato + "&imprimir=1";
  }

  function imprimir(base, formato) {
    // En la misma pestaña: no se abre ninguna ventana nueva.
    window.location.href = conFormato(base, formato);
  }

  function preguntar(boton) {
    var base = boton.dataset.imprimir;
    if (!base) {
      return;
    }
    var titulo = boton.dataset.titulo || "Imprimir el comprobante";

    // Sin Metro se va directo a lo de siempre: el tíquet.
    if (!window.Metro || !Metro.dialog) {
      imprimir(base, "t80");
      return;
    }

    Metro.dialog.create({
      title: titulo,
      content: '<p class="ayuda">' + ayuda() + "</p>",
      closeButton: true,
      defaultActions: false,
      clsDialog: "dialogo-imprimir",
      customButtons: [
        {
          text: "Tíquet 80 mm",
          cls: "js-dialog-close primary",
          onclick: function () {
            imprimir(base, "t80");
          },
        },
        {
          text: "Hoja A4",
          cls: "js-dialog-close",
          onclick: function () {
            imprimir(base, "a4");
          },
        },
        { text: "Cancelar", cls: "js-dialog-close" },
      ],
    });
  }

  document.addEventListener("click", function (evento) {
    var boton = evento.target.closest("[data-imprimir]");
    if (!boton) {
      return;
    }
    evento.preventDefault();
    preguntar(boton);
  });
})();
