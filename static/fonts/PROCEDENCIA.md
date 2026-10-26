# Manrope — procedencia

| | |
|---|---|
| Fuente | **Manrope** (variable, ejes `wght` 200–800) |
| Versión | 5.2.5 del paquete npm [`@fontsource-variable/manrope`](https://www.npmjs.com/package/@fontsource-variable/manrope) · <https://fonts.google.com/specimen/Manrope> |
| Autor | Mikhail Sharanda |
| Licencia | SIL Open Font License 1.1 (`LICENSE`, en esta misma carpeta) |
| Qué se copió | `files/manrope-latin-wght-normal.woff2` (subconjunto latino) |

## Huella (sha256) de lo que sí se copió

```
14be4114dcfde74652f19f9ffae8c9bb50707e9e88bd2b1fcd86fb50224109e7  manrope-latin.woff2
```

## Por qué el subconjunto latino

La aplicación se escribe en español: el subconjunto latino trae los acentos, la eñe y
las comillas angulares («»). Son 24 KB, así que carga como una imagen pequeña y se
queda en la caché del navegador. La fuente se sirve desde `static/`, sin depender de
ningún CDN: la aplicación funciona igual sin internet.
