"""
Collector de Interseguro — Vida Free / Vida Cash Plus.

Estrategia:
  El cotizador Vida Free hace una llamada a un endpoint server-side.
  Interceptamos la respuesta JSON directamente con Playwright.
  Si falla, intentamos leer el DOM renderizado.
"""
import json
import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Page, Response

from core.models import Cotizacion, Perfil

COTIZADOR_URL = "https://www.interseguro.pe/vidafree/"
COMPETIDOR    = "Interseguro"
PRODUCTO      = "Vida Free (Devolución)"
TC            = 3.5


async def cotizar_interseguro(perfil: Perfil) -> Cotizacion:
    """
    Cotiza en Interseguro Vida Free para el perfil dado.
    """
    captured = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            locale="es-PE",
        )
        page = await context.new_page()

        async def on_response(response: Response):
            url = response.url.lower()
            # Interseguro: el endpoint de cotización suele tener keywords como
            # cotizacion, prima, tarifa, quote en la URL
            if any(kw in url for kw in ["cotiz", "prima", "tarif", "quot", "vidafree", "precio"]):
                try:
                    ct = response.headers.get("content-type", "")
                    if "json" in ct:
                        body = await response.json()
                        captured["response"] = body
                        captured["url"] = response.url
                except Exception:
                    pass

        page.on("response", on_response)

        try:
            await page.goto(COTIZADOR_URL, wait_until="networkidle", timeout=30000)

            # Esperar que el cotizador cargue — busca inputs de datos del perfil
            await page.wait_for_timeout(2000)

            # --- Intentar llenar fecha de nacimiento ---
            from datetime import date
            anio_nac = date.today().year - perfil.edad
            fecha_nac_str = f"{anio_nac}-01-15"

            # Interseguro puede usar input type=date o campos separados
            inputs_fecha = page.locator("input[type='date']")
            if await inputs_fecha.count() > 0:
                await inputs_fecha.first.fill(fecha_nac_str)
                await page.keyboard.press("Tab")
                await page.wait_for_timeout(500)

            # Buscar y llenar campo de sexo si existe
            sexo_map = {"M": ["masculino", "hombre", "male"], "F": ["femenino", "mujer", "female"]}
            for keyword in sexo_map.get(perfil.sexo, []):
                try:
                    opt = page.locator(f"option:has-text('{keyword}'), label:has-text('{keyword}'), button:has-text('{keyword}')").first
                    if await opt.count() > 0:
                        await opt.click()
                        break
                except Exception:
                    pass

            # Buscar botón de cotizar / calcular
            for btn_text in ["Cotizar", "Calcular", "Ver prima", "Simular"]:
                try:
                    btn = page.locator(f"button:has-text('{btn_text}')").first
                    if await btn.count() > 0:
                        await btn.click()
                        await page.wait_for_timeout(3000)
                        break
                except Exception:
                    pass

            await page.wait_for_timeout(2000)

            # --- Procesar respuesta interceptada ---
            prima_anual = None
            pct_devolucion = None
            frecuencia = perfil.frecuencia_pago

            if captured.get("response"):
                data = captured["response"]
                # Campos comunes en APIs de seguros peruanos
                for campo_prima in ["prima", "primaMensual", "primaAnual", "monto", "amount", "cuota"]:
                    if campo_prima in data:
                        val = float(data[campo_prima])
                        if "ensual" in campo_prima or "uota" in campo_prima:
                            prima_anual = val * 12
                            frecuencia = "mensual"
                        else:
                            prima_anual = val
                        break

                for campo_dev in ["devolucion", "porcentajeDevolucion", "pctDevolucion", "returnPct"]:
                    if campo_dev in data:
                        pct_devolucion = float(data[campo_dev])
                        break

            # --- Fallback DOM ---
            if not prima_anual:
                content = await page.content()
                import re
                # Buscar el monto de devolución total que muestra el cotizador
                matches = re.findall(r"S/\s*([\d,]+\.?\d*)", content)
                for m in matches:
                    try:
                        val = float(m.replace(",", ""))
                        if 50 <= val <= 10000:
                            prima_anual = val * 12
                            frecuencia = "mensual"
                            break
                    except ValueError:
                        pass

            await browser.close()

            if not prima_anual:
                return Cotizacion(
                    competidor=COMPETIDOR,
                    producto=PRODUCTO,
                    perfil_id=perfil.id,
                    perfil_nombre=perfil.nombre,
                    edad=perfil.edad,
                    sexo=perfil.sexo,
                    suma_asegurada_pen=perfil.suma_asegurada_pen,
                    vigencia_anios=perfil.vigencia_anios,
                    frecuencia_pago=frecuencia,
                    prima_anual_pen=0,
                    fuente_url=COTIZADOR_URL,
                    confianza="baja",
                    error="Interseguro: no se capturó prima. El cotizador puede requerir parámetros adicionales o captcha.",
                )

            return Cotizacion(
                competidor=COMPETIDOR,
                producto=PRODUCTO,
                perfil_id=perfil.id,
                perfil_nombre=perfil.nombre,
                edad=perfil.edad,
                sexo=perfil.sexo,
                suma_asegurada_pen=perfil.suma_asegurada_pen,
                vigencia_anios=perfil.vigencia_anios,
                frecuencia_pago=frecuencia,
                prima_anual_pen=round(prima_anual, 2),
                porcentaje_devolucion=pct_devolucion,
                moneda_original="PEN",
                tc_usado=TC,
                fuente_url=captured.get("url", COTIZADOR_URL),
                confianza="media" if captured.get("response") else "baja",
            )

        except Exception as e:
            await browser.close()
            return Cotizacion(
                competidor=COMPETIDOR,
                producto=PRODUCTO,
                perfil_id=perfil.id,
                perfil_nombre=perfil.nombre,
                edad=perfil.edad,
                sexo=perfil.sexo,
                suma_asegurada_pen=perfil.suma_asegurada_pen,
                vigencia_anios=perfil.vigencia_anios,
                frecuencia_pago=perfil.frecuencia_pago,
                prima_anual_pen=0,
                fuente_url=COTIZADOR_URL,
                confianza="baja",
                error=f"Error Playwright: {str(e)[:200]}",
            )
