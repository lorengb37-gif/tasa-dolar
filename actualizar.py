"""
Extrae la tasa del USD del Banco Popular Dominicano desde tasareal.com
y genera/actualiza el archivo index.html que se publicará en GitHub Pages.

Diseñado para correr en GitHub Actions todos los días a las 7:00 AM (RD).
"""

import re
import sys
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

FUENTE_URL = "https://tasareal.com/institucion/popular"
ARCHIVO_HTML = "index.html"
ARCHIVO_HISTORIAL = "historial.json"
TZ_RD = timezone(timedelta(hours=-4))  # República Dominicana = UTC-4

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-DO,es;q=0.9,en;q=0.8",
}


def obtener_html(url: str, intentos: int = 3, timeout: int = 20) -> str:
    """Descarga el HTML con reintentos en caso de fallo de red."""
    ultimo_error = None
    for intento in range(1, intentos + 1):
        try:
            print(f"Intento {intento}/{intentos}: GET {url}")
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            ultimo_error = e
            print(f"  Falló: {e}")
    raise RuntimeError(f"No se pudo descargar la página tras {intentos} intentos: {ultimo_error}")


def extraer_tasa(html: str) -> tuple[float, float]:
    """
    Extrae compra y venta usando tres estrategias en cascada.
    Si una falla por cambio leve de estructura, las otras aguantan.
    """
    # Estrategia 1: el listado superior "Banco Popular 57.00 / 60.00"
    m = re.search(r"Banco Popular\s+(\d{2,3}\.\d{2})\s*/\s*(\d{2,3}\.\d{2})", html, re.IGNORECASE)
    if m:
        print("  Extraído por estrategia 1 (listado superior)")
        return float(m.group(1)), float(m.group(2))

    # Estrategia 2: metadescripción "Compra: RD$57.00 | Venta: RD$60.00"
    m = re.search(
        r"Compra:\s*RD\$?\s*(\d{2,3}\.\d{2})\s*\|\s*Venta:\s*RD\$?\s*(\d{2,3}\.\d{2})",
        html, re.IGNORECASE
    )
    if m:
        print("  Extraído por estrategia 2 (metadescripción)")
        return float(m.group(1)), float(m.group(2))

    # Estrategia 3: primera fila de la tabla histórica
    m = re.search(
        r"\|\s*\w{3}\.?,?\s+\d{1,2}\s+\w+\.?\s+\d{4}\s*\|\s*(\d{2,3}\.\d{2})\s*\|\s*(\d{2,3}\.\d{2})",
        html, re.IGNORECASE
    )
    if m:
        print("  Extraído por estrategia 3 (tabla histórica)")
        return float(m.group(1)), float(m.group(2))

    raise ValueError(
        "No se pudo extraer la tasa. La estructura de la página puede haber cambiado. "
        "Revisar manualmente https://tasareal.com/institucion/popular"
    )


def validar_tasa(compra: float, venta: float) -> None:
    """Sanity check: las tasas deben estar en un rango razonable."""
    if not (40 <= compra <= 80):
        raise ValueError(f"Compra fuera de rango razonable: {compra}")
    if not (40 <= venta <= 80):
        raise ValueError(f"Venta fuera de rango razonable: {venta}")
    if venta < compra:
        raise ValueError(f"Venta ({venta}) no puede ser menor que compra ({compra})")


def cargar_historial() -> list:
    """Carga el historial previo si existe; si no, devuelve lista vacía."""
    if Path(ARCHIVO_HISTORIAL).exists():
        try:
            with open(ARCHIVO_HISTORIAL, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
    return []


def guardar_historial(historial: list, max_dias: int = 30) -> None:
    """Guarda el historial limitado a los últimos N días."""
    historial = historial[-max_dias:]
    with open(ARCHIVO_HISTORIAL, "w", encoding="utf-8") as f:
        json.dump(historial, f, ensure_ascii=False, indent=2)


def actualizar_historial(historial: list, compra: float, venta: float, fecha_iso: str) -> list:
    """Agrega o actualiza la entrada del día actual."""
    fecha_solo_dia = fecha_iso[:10]
    # Si ya existe entrada para hoy, la reemplaza; si no, la agrega
    historial = [h for h in historial if h["fecha"][:10] != fecha_solo_dia]
    historial.append({
        "fecha": fecha_iso,
        "compra": compra,
        "venta": venta,
    })
    historial.sort(key=lambda h: h["fecha"])
    return historial


def generar_html(compra: float, venta: float, ahora: datetime, historial: list) -> str:
    """Genera el HTML del dashboard con la tasa actual y mini-gráfico de historial."""
    spread = venta - compra
    fecha_str = ahora.strftime("%d/%m/%Y")
    hora_str = ahora.strftime("%I:%M %p").lstrip("0")

    # Comparar con el día anterior si existe
    delta_compra = ""
    delta_venta = ""
    if len(historial) >= 2:
        anterior = historial[-2]
        diff_c = compra - anterior["compra"]
        diff_v = venta - anterior["venta"]
        if abs(diff_c) >= 0.01:
            signo = "+" if diff_c > 0 else ""
            color = "#ef4444" if diff_c > 0 else "#10b981"
            delta_compra = f'<span class="delta" style="color:{color}">{signo}{diff_c:.2f}</span>'
        if abs(diff_v) >= 0.01:
            signo = "+" if diff_v > 0 else ""
            color = "#ef4444" if diff_v > 0 else "#10b981"
            delta_venta = f'<span class="delta" style="color:{color}">{signo}{diff_v:.2f}</span>'

    # Mini-tabla con los últimos 7 días
    filas_tabla = ""
    for entrada in reversed(historial[-7:]):
        f_dt = datetime.fromisoformat(entrada["fecha"])
        filas_tabla += (
            f'<tr><td>{f_dt.strftime("%d/%m")}</td>'
            f'<td>{entrada["compra"]:.2f}</td>'
            f'<td>{entrada["venta"]:.2f}</td></tr>'
        )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="3600">
<title>Tasa USD — Banco Popular Dominicano</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
    color: #e2e8f0;
  }}
  .dashboard {{
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 16px;
    padding: 40px;
    max-width: 560px;
    width: 100%;
    box-shadow: 0 20px 60px rgba(0,0,0,0.4);
  }}
  .header {{
    border-bottom: 1px solid #334155;
    padding-bottom: 20px;
    margin-bottom: 30px;
  }}
  .badge {{
    display: inline-block;
    background: #1d4ed8;
    color: #dbeafe;
    font-size: 11px;
    font-weight: 600;
    padding: 4px 10px;
    border-radius: 6px;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    margin-bottom: 10px;
  }}
  h1 {{
    font-size: 22px;
    font-weight: 600;
    color: #f1f5f9;
    letter-spacing: -0.3px;
  }}
  .subtitle {{
    color: #94a3b8;
    font-size: 13px;
    margin-top: 4px;
  }}
  .grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-bottom: 24px;
  }}
  .card {{
    background: #0f172a;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 24px;
    position: relative;
  }}
  .card.compra {{ border-left: 3px solid #10b981; }}
  .card.venta  {{ border-left: 3px solid #ef4444; }}
  .card-label {{
    font-size: 11px;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin-bottom: 8px;
  }}
  .card-value {{
    font-size: 38px;
    font-weight: 700;
    color: #f8fafc;
    letter-spacing: -1px;
  }}
  .card-currency {{
    font-size: 14px;
    color: #64748b;
    font-weight: 500;
    margin-left: 4px;
  }}
  .delta {{
    display: inline-block;
    font-size: 12px;
    font-weight: 600;
    margin-left: 8px;
    vertical-align: middle;
  }}
  .spread {{
    background: #0f172a;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 16px 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
  }}
  .spread-label {{ font-size: 13px; color: #94a3b8; }}
  .spread-value {{ font-size: 16px; font-weight: 600; color: #fbbf24; }}
  .historial {{
    background: #0f172a;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 24px;
  }}
  .historial h3 {{
    font-size: 11px;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin-bottom: 12px;
    font-weight: 600;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }}
  th, td {{
    padding: 8px 4px;
    text-align: left;
    border-bottom: 1px solid #1e293b;
  }}
  th {{
    color: #64748b;
    font-weight: 500;
    font-size: 11px;
    text-transform: uppercase;
  }}
  td {{ color: #cbd5e1; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:first-child td {{ color: #f8fafc; font-weight: 600; }}
  .footer {{
    border-top: 1px solid #334155;
    padding-top: 16px;
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    color: #64748b;
    flex-wrap: wrap;
    gap: 8px;
  }}
  .pulse {{
    display: inline-block;
    width: 8px;
    height: 8px;
    background: #10b981;
    border-radius: 50%;
    margin-right: 6px;
    animation: pulse 2s infinite;
  }}
  @keyframes pulse {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0.4; }}
  }}
  @media (max-width: 480px) {{
    .dashboard {{ padding: 24px; }}
    .grid {{ grid-template-columns: 1fr; }}
    .card-value {{ font-size: 32px; }}
  }}
</style>
</head>
<body>
  <div class="dashboard">
    <div class="header">
      <span class="badge">USD / DOP</span>
      <h1>Banco Popular Dominicano</h1>
      <p class="subtitle">Tasa de cambio del dólar estadounidense</p>
    </div>

    <div class="grid">
      <div class="card compra">
        <div class="card-label">Compra</div>
        <div class="card-value">{compra:.2f}<span class="card-currency">RD$</span>{delta_compra}</div>
      </div>
      <div class="card venta">
        <div class="card-label">Venta</div>
        <div class="card-value">{venta:.2f}<span class="card-currency">RD$</span>{delta_venta}</div>
      </div>
    </div>

    <div class="spread">
      <span class="spread-label">Spread (diferencia)</span>
      <span class="spread-value">RD$ {spread:.2f}</span>
    </div>

    <div class="historial">
      <h3>Últimos 7 días</h3>
      <table>
        <thead>
          <tr><th>Fecha</th><th>Compra</th><th>Venta</th></tr>
        </thead>
        <tbody>
          {filas_tabla}
        </tbody>
      </table>
    </div>

    <div class="footer">
      <span><span class="pulse"></span>Actualizado: {fecha_str} · {hora_str}</span>
      <span>Fuente: tasareal.com</span>
    </div>
  </div>
</body>
</html>"""


def generar_html_error(mensaje: str, ahora: datetime) -> str:
    """HTML alterno que se muestra si la extracción falla totalmente."""
    fecha_str = ahora.strftime("%d/%m/%Y %I:%M %p")
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Error al actualizar tasa</title>
<style>
body{{font-family:-apple-system,sans-serif;background:#1e293b;color:#fca5a5;padding:40px;text-align:center;min-height:100vh;display:flex;align-items:center;justify-content:center}}
.box{{max-width:500px;background:#0f172a;padding:30px;border-radius:12px;border-left:4px solid #ef4444}}
h2{{color:#f87171;margin-bottom:15px}}
p{{margin:10px 0;color:#cbd5e1;line-height:1.5}}
.fecha{{font-size:12px;color:#64748b;margin-top:20px}}
</style></head><body><div class="box">
<h2>⚠️ No se pudo actualizar la tasa</h2>
<p>{mensaje}</p>
<p class="fecha">Último intento: {fecha_str}</p>
</div></body></html>"""


def main():
    ahora = datetime.now(TZ_RD)
    print(f"=== Inicio: {ahora.isoformat()} ===")

    try:
        html = obtener_html(FUENTE_URL)
        compra, venta = extraer_tasa(html)
        validar_tasa(compra, venta)
        print(f"✅ Compra: {compra} | Venta: {venta}")

        historial = cargar_historial()
        historial = actualizar_historial(historial, compra, venta, ahora.isoformat())
        guardar_historial(historial)

        salida = generar_html(compra, venta, ahora, historial)
        Path(ARCHIVO_HTML).write_text(salida, encoding="utf-8")
        print(f"✅ {ARCHIVO_HTML} generado correctamente.")
        return 0

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        # Aún en caso de error, generamos un HTML que avisa, en vez de dejar el viejo sin señalar
        try:
            salida_error = generar_html_error(str(e), ahora)
            # Solo sobreescribir si no existe un HTML previo, para no perder el dato del día anterior
            if not Path(ARCHIVO_HTML).exists():
                Path(ARCHIVO_HTML).write_text(salida_error, encoding="utf-8")
        except Exception as e2:
            print(f"❌ Error escribiendo HTML de error: {e2}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
