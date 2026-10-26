# Metro UI — procedencia

| | |
|---|---|
| Versión | **5.1.20** (la última publicada) |
| Origen | paquete npm [`@olton/metroui`](https://www.npmjs.com/package/@olton/metroui) · <https://metroui.org.ua> |
| Licencia | MIT (`LICENSE`) |
| Qué se copió | `lib/metro.css`, `lib/metro.js`, `icons/core/style.css` y la fuente de los iconos |
| Fecha | ver el historial del proyecto |

## Huellas (sha256) de lo que sí se copió

```
50e237f90becdbae2f216e97d84c2d3e35ef2bde1bbd1b69d2b24ed9c762c1f1  css/metro/metro.css
712839ac530b14733d33ffbce1e9d5715871a915bf367295614c63794fd6b094  js/metro/metro.js
81153ffbf8d05183858529129fc59493f5556185db6a8fa7dc91b8421e9823e6  icons/core/style.css
2d75955848c16cad48a9adcc0f3dec3b71dd1322328ba488bb15f4b74c0d547e  icons/core/fonts/metro-ui-core.ttf   (el @font-face lo pide antes que el .woff)
```

## Qué se dejó fuera y por qué

- `lib/metro.all.css` / `lib/metro.all.js`: traen todo lo de arriba **más** los ejemplos y
  los componentes de terceros; con `metro.css` ya está el aspecto que usa la interfaz.
- `lib/icons.css`: el juego completo de iconos pesa 1,9 MB; con `icons/core` (el que usa
  Metro para sus propios controles) basta, y sus nombres verificados están en el CSS.

## Lo que Metro no trae y pone `interfaz.css`

El marco (barra de arriba + lateral en riel), los avisos, los sellos de estado, las
tarjetas, el comprobante y su versión impresa. Metro aporta la tipografía, la rejilla,
los botones, los campos y las tablas.

## Cómo se usa

Las plantillas cargan, en este orden:

```html
<link rel="stylesheet" href="{% static 'css/metro/metro.css' %}">
<link rel="stylesheet" href="{% static 'icons/core/style.css' %}">
<link rel="stylesheet" href="{% static 'css/interfaz.css' %}">   {# el tema, encima #}
...
<script src="{% static 'js/metro/metro.js' %}"></script>
<script src="{% static 'js/interfaz.js' %}"></script>
```

De Metro se usan también sus componentes con JavaScript: los avisos flotantes
(`Metro.toast`), los diálogos de confirmación (`Metro.dialog`) y el anillo de espera
(`Metro.activity`). El resto del comportamiento (el menú del móvil) es de `interfaz.js`.

`interfaz.css` va al final a propósito: redefine las variables de Metro
(`--sidenav-*`, `--input-*`, `--table-*`, `--button-*`…) y estiliza lo que Metro no trae.
