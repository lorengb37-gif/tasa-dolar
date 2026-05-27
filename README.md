# Tasa USD Banco Popular Dominicano

Dashboard automatizado que muestra la tasa del dólar (compra/venta) del Banco Popular Dominicano.

- **Fuente de datos:** [tasareal.com/institucion/popular](https://tasareal.com/institucion/popular)
- **Actualización:** Diaria a las 7:00 AM (hora RD) vía GitHub Actions
- **Hosting:** GitHub Pages

## Estructura

- `actualizar.py` — Script que extrae la tasa y genera el HTML
- `index.html` — Dashboard generado (se sobreescribe cada día)
- `historial.json` — Historial de los últimos 30 días
- `.github/workflows/actualizar.yml` — Automatización (cron diario)

## Ejecutar localmente

```bash
pip install requests
python actualizar.py
```

## Forzar actualización manual

Ir a la pestaña **Actions** del repo → seleccionar el workflow → **Run workflow**.
