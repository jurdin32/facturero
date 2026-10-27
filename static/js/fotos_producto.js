/* Las fotos del producto: se sueltan en el recuadro, se ven en pequeño y se
 * reducen antes de salir.
 *
 * El formulario sigue siendo el formset de Django —los campos de cada foto están
 * ahí, escondidos—, así que sin JavaScript se puede subir igual, con el campo de
 * archivo de siempre. Lo que hace esto es ponerle encima una zona de arrastre,
 * reordenar por posición y achicar la imagen en el navegador para no mandar cinco
 * megas por una foto que se va a ver a 600 px.
 */
(function () {
  "use strict";

  //: El lado mayor al que se reduce la foto. Con 1600 px sobra para la ficha,
  //: que enseña la imagen a 600 y a pantalla completa en el móvil.
  var LADO_MAXIMO = 1600;
  var CALIDAD = 0.82;
  var PESO_MINIMO_PARA_COMPRIMIR = 300 * 1024;
  var PESO_MAXIMO = 5 * 1024 * 1024;

  var soportaWebp = (function () {
    try {
      var lienzo = document.createElement("canvas");
      return lienzo.toDataURL("image/webp").indexOf("data:image/webp") === 0;
    } catch (error) {
      return false;
    }
  })();

  function cargarImagen(archivo) {
    return new Promise(function (listo, falla) {
      var direccion = URL.createObjectURL(archivo);
      var imagen = new Image();
      imagen.onload = function () {
        URL.revokeObjectURL(direccion);
        listo(imagen);
      };
      imagen.onerror = function () {
        URL.revokeObjectURL(direccion);
        falla(new Error("no se pudo leer"));
      };
      imagen.src = direccion;
    });
  }

  function nombreNuevo(archivo, tipo) {
    var base = archivo.name.replace(/\.[^.]+$/, "") || "foto";
    return base + (tipo === "image/webp" ? ".webp" : ".jpg");
  }

  /** Deja la foto en algo que se pueda subir: 1600 px de lado y poco peso. */
  function comprimir(archivo) {
    return cargarImagen(archivo).then(function (imagen) {
      var lado = Math.max(imagen.width, imagen.height);
      var escala = lado > LADO_MAXIMO ? LADO_MAXIMO / lado : 1;
      if (escala === 1 && archivo.size <= PESO_MINIMO_PARA_COMPRIMIR) {
        return archivo;
      }
      var ancho = Math.max(1, Math.round(imagen.width * escala));
      var alto = Math.max(1, Math.round(imagen.height * escala));
      var lienzo = document.createElement("canvas");
      lienzo.width = ancho;
      lienzo.height = alto;
      var pincel = lienzo.getContext("2d");
      // Un fondo blanco: las fotos con transparencia no quedan con manchas negras.
      pincel.fillStyle = "#fff";
      pincel.fillRect(0, 0, ancho, alto);
      pincel.drawImage(imagen, 0, 0, ancho, alto);
      var tipo = soportaWebp ? "image/webp" : "image/jpeg";
      return new Promise(function (listo) {
        lienzo.toBlob(
          function (blob) {
            if (!blob || blob.size >= archivo.size) {
              listo(archivo);
              return;
            }
            listo(
              new File([blob], nombreNuevo(archivo, blob.type), {
                type: blob.type,
                lastModified: Date.now()
              })
            );
          },
          tipo,
          CALIDAD
        );
      });
    });
  }

  function pesoLegible(bytes) {
    if (bytes >= 1024 * 1024) {
      return (bytes / (1024 * 1024)).toFixed(1).replace(".", ",") + " MB";
    }
    return Math.max(1, Math.round(bytes / 1024)) + " KB";
  }

  function montar(caja) {
    var rejilla = caja.querySelector("[data-rejilla]");
    var zona = caja.querySelector("[data-soltar]");
    var entrada = caja.querySelector("[data-archivo]");
    var aviso = caja.querySelector("[data-aviso]");
    var plantilla = document.querySelector("[data-plantilla-foto]");
    // El formulario de control del formset puede estar fuera del recuadro.
    var formulario = caja.closest("form");
    var totales =
      caja.querySelector("input[name$='-TOTAL_FORMS']") ||
      (formulario && formulario.querySelector("input[name$='-TOTAL_FORMS']"));
    if (!rejilla || !zona || !entrada || !plantilla || !totales) {
      return;
    }
    // Sin `DataTransfer` no se puede dejar el archivo dentro del formulario: en ese
    // caso se queda el campo de archivo de siempre, que funciona igual.
    if (typeof DataTransfer === "undefined" || !window.URL || !URL.createObjectURL) {
      return;
    }
    caja.classList.add("con-arrastre");

    function decir(texto, esError) {
      aviso.textContent = texto || "";
      aviso.classList.toggle("error", Boolean(esError));
    }

    function tarjetas() {
      return Array.prototype.slice.call(rejilla.querySelectorAll("[data-foto-tarjeta]"));
    }

    /** Numera el orden por la posición y marca cuál es la principal. */
    function reordenar() {
      var puestas = 0;
      tarjetas().forEach(function (tarjeta) {
        if (tarjeta.hidden) {
          return;
        }
        var orden = tarjeta.querySelector("input[name$='-orden']");
        if (orden) {
          orden.value = puestas;
        }
        var etiqueta = tarjeta.querySelector(".foto-principal");
        if (etiqueta) {
          etiqueta.classList.toggle("visible", puestas === 0);
        }
        puestas += 1;
      });
    }

    /** Una tarjeta nueva, tomando el formulario vacío del formset. */
    function nuevaTarjeta() {
      var indice = parseInt(totales.value, 10) || 0;
      totales.value = indice + 1;

      var trozo = document.createElement("div");
      trozo.innerHTML = plantilla.innerHTML.replace(/__prefix__/g, indice);
      var tarjeta = trozo.querySelector("[data-foto-tarjeta]");
      rejilla.appendChild(tarjeta);
      return tarjeta;
    }

    /** Una casilla libre: la que trae el formset de más, o una nueva. */
    function tarjetaLibre() {
      var libres = tarjetas().filter(function (tarjeta) {
        var archivo = tarjeta.querySelector("input[type=file]");
        var identificador = tarjeta.querySelector("input[name$='-id']");
        var tiene = archivo && archivo.files && archivo.files.length;
        return !tiene && !(identificador && identificador.value);
      });
      if (!libres.length) {
        return nuevaTarjeta();
      }
      var libre = libres[libres.length - 1];
      libre.hidden = false;
      return libre;
    }

    function ponerArchivo(tarjeta, archivo) {
      var campo = tarjeta.querySelector("input[type=file]");
      if (!campo) {
        return;
      }
      var cesto = new DataTransfer();
      cesto.items.add(archivo);
      campo.files = cesto.files;
      var vista = tarjeta.querySelector("[data-vista]");
      if (vista) {
        vista.src = URL.createObjectURL(archivo);
        vista.hidden = false;
      }
      var vacia = tarjeta.querySelector("[data-vacia]");
      if (vacia) {
        vacia.hidden = true;
      }
      var alt = tarjeta.querySelector("input[name$='-alt']");
      if (alt && !alt.value) {
        alt.placeholder = archivo.name.replace(/\.[^.]+$/, "").slice(0, 60);
      }
    }

    function recibir(lista) {
      var archivos = Array.prototype.slice.call(lista || []);
      if (!archivos.length) {
        return;
      }
      decir("Preparando las fotos…");
      var hechas = 0;

      archivos.reduce(function (cadena, archivo) {
        return cadena.then(function () {
          if (archivo.type && archivo.type.indexOf("image/") !== 0) {
            decir("«" + archivo.name + "» no es una imagen.", true);
            return null;
          }
          return comprimir(archivo)
            .then(function (final) {
              if (final.size > PESO_MAXIMO) {
                decir("«" + archivo.name + "» sigue pasando de 5 MB.", true);
                return null;
              }
              ponerArchivo(tarjetaLibre(), final);
              hechas += 1;
              return null;
            })
            .catch(function () {
              decir(
                "No se pudo leer «" + archivo.name + "». Si viene de un iPhone, " +
                  "expórtela como JPG.",
                true
              );
              return null;
            });
        });
      }, Promise.resolve()).then(function () {
        reordenar();
        if (hechas) {
          decir(
            hechas === 1 ? "Foto lista para guardar." : hechas + " fotos listas para guardar."
          );
        }
      });
    }

    // --- el arrastre -------------------------------------------------------
    ["dragenter", "dragover"].forEach(function (evento) {
      zona.addEventListener(evento, function (e) {
        e.preventDefault();
        zona.classList.add("encima");
      });
    });
    ["dragleave", "dragend", "drop"].forEach(function (evento) {
      zona.addEventListener(evento, function () {
        zona.classList.remove("encima");
      });
    });
    zona.addEventListener("drop", function (e) {
      e.preventDefault();
      recibir(e.dataTransfer && e.dataTransfer.files);
    });
    // Soltar fuera del recuadro no debe abrir la foto en otra pestaña.
    window.addEventListener("dragover", function (e) { e.preventDefault(); });
    window.addEventListener("drop", function (e) {
      if (!zona.contains(e.target)) {
        e.preventDefault();
      }
    });

    zona.querySelector("[data-elegir]").addEventListener("click", function () {
      entrada.click();
    });
    entrada.addEventListener("change", function () {
      recibir(entrada.files);
      entrada.value = "";
    });

    // --- quitar y mover ----------------------------------------------------
    rejilla.addEventListener("click", function (evento) {
      var tarjeta = evento.target.closest("[data-foto-tarjeta]");
      if (!tarjeta) {
        return;
      }
      if (evento.target.closest("[data-quitar]")) {
        var identificador = tarjeta.querySelector("input[name$='-id']");
        if (identificador && identificador.value) {
          var borrar = tarjeta.querySelector("input[name$='-DELETE']");
          if (borrar) {
            borrar.checked = true;
          }
          tarjeta.hidden = true;
        } else {
          tarjeta.parentNode.removeChild(tarjeta);
        }
        reordenar();
        decir("");
        return;
      }
      if (evento.target.closest("[data-izquierda]")) {
        var previa = tarjeta.previousElementSibling;
        if (previa) {
          rejilla.insertBefore(tarjeta, previa);
          reordenar();
        }
        return;
      }
      if (evento.target.closest("[data-derecha]")) {
        var siguiente = tarjeta.nextElementSibling;
        if (siguiente) {
          rejilla.insertBefore(siguiente, tarjeta);
          reordenar();
        }
      }
    });

    // Al enviar: que no queden tarjetas vacías contando y que el orden esté al día.
    if (formulario) {
      formulario.addEventListener("submit", function () {
        tarjetas().forEach(function (tarjeta) {
          var archivo = tarjeta.querySelector("input[type=file]");
          var identificador = tarjeta.querySelector("input[name$='-id']");
          var tiene = archivo && archivo.files && archivo.files.length;
          if (!tiene && !(identificador && identificador.value)) {
            tarjeta.parentNode.removeChild(tarjeta);
          }
        });
        reordenar();
      });
    }

    // Las tarjetas vacías que trae el formset no se enseñan hasta que hay foto.
    tarjetas().forEach(function (tarjeta) {
      var archivo = tarjeta.querySelector("input[type=file]");
      var identificador = tarjeta.querySelector("input[name$='-id']");
      if (!(identificador && identificador.value) && !(archivo && archivo.files.length)) {
        tarjeta.hidden = true;
      }
    });
    reordenar();
  }

  function arrancar() {
    var cajas = document.querySelectorAll("[data-fotos]");
    Array.prototype.forEach.call(cajas, montar);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", arrancar);
  } else {
    arrancar();
  }
})();
