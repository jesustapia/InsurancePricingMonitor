"""
Collector de Mapfre Perú — Ahorro Devolución / Vida Devolución.

Estrategia:
  Mapfre tiene cotizadores online reales con lógica actuarial server-side.
  Llenamos el formulario con Playwright, esperamos el resultado y lo extraemos
  del DOM o de la respuesta de red interceptada.

Productos:
  - Ahorro Devolución  → más parecido a VidAhorroGarantizado de Rímac
  - Vida Devolución    → alternativa si Ahorro Dev. requiere asesor
"""
import json
import re
import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Page, Response

from core.models import Cotizacion, Perfil

COTIZADOR_URL  = "https://www.mapfreseguros.com.pe/ahorro-devolucion/"
COTIZADOR_URL2 = "https://www.mapfre.com.pe/ahorro-devolucion/"
COMPETIDOR     = "Mapfre"
PRODUCTO       = "Ahorro Devolución"
TC             = 3.5

VIGENCIAS_SOPORTADAS = {5, 7, 10, 15, 20, 25}


async def cotizar_mapfre(perfil: Perfil) -> Cotizacion:
    """
    Cotiza en Mapfre Ahorro Devolución para el perfil dado.
    """
    vigencia = min(VIGENCIAS_SOPORTADAS, key=lambda v: abs(v - perfil.vigencia_anios))
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
            if any(kw in url for kw in ["cotiz", "prima", "tarif", "quot", "calcul", "precio"]):
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
            # Intentar primero el dominio mapfreseguros.com.pe
            try:
                await page.goto(COTIZADOR_URL, wait_until="networkidle", timeout=25000)
            except Exception:
                await page.goto(COTIZADOR_URL2, wait_until="networkidle", timeout=25000)

            await page.wait_for_timeout(2000)

            from datetime import date
            anio_nac = date.today().year - perfil.edad

            # --- Fecha de nacimiento ---
            for selector in [
                "input[type='date']",
                "input[placeholder*='nacimiento']",
                "input[placeholder*='fecha']",
                "input[name*='fecha']",
                "input[id*='fecha']",
            ]:
                try:
                    inp = page.locator(selector).first
                    if await inp.count() > 0:
                        await inp.fill(f"{anio_nac}-01-15")
                        await page.keyboard.press("Tab")
                        await page.wait_for_timeout(400)
                        break
                except Exception:
                    pass

            # --- Suma asegurada ---
            sa_str = str(int(perfil.suma_asegurada_pen))
            for selector in [
                "input[placeholder*='suma']",
                "input[placeholder*='capital']",
                "input[name*='suma']",
                "input[name*='capital']",
                "input[id*='suma']",
            ]:
                try:
                    inp = page.locator(selector).first
                    if await inp.count() > 0:
                        await inp.fill(sa_str)
                        await page.keyboard.press("Tab")
                        await page.wait_for_timeout(400)
                        break
                except Exception:
                    pass

            # --- Plazo / vigencia ---
            for sel in [
                f"option[value='{vigencia}']",
                f"button:has-text('{vigencia}')",
                f"text={vigencia} años",
                f"[data-value='{vigencia}']",
            ]:
                try:
                    el = page.locator(sel).first
                    if await el.count() > 0:
                        await el.click()
                        await page.wait_for_timeout(400)
                        break
                except Exception:
                    pass

            # --- Sexo ---
            sexo_keywords = {"M": ["masculino", "hombre"], "F": ["femenino", "mujer"]}
            for kw in sexo_keywords.get(perfil.sexo, []):
                try:
                    el = page.locator(
                        f"option:has-text('{kw}'), label:has-text('{kw}'), input[value='{kw[0].upper()}']"
                    ).first
                    if await el.count() > 0:
                        await el.click()
                        break
                except Exception:
                    pass

            # --- Fumador ---
            fumador_kw = "fumador" if perfil.fumador else "no fumador"
            try:
                el = page.locator(f"text={fumador_kw}").first
                if await el.count() > 0:
                    await el.click()
            except Exception:
                pass

            # --- Disparar cotización ---
            for btn_text in ["Cotizar", "Calcular", "Ver prima", "Simular", "Consultar"]:
                try:
                    btn = page.locator(f"button:has-text('{btn_text}'), input[value='{btn_text}']").first
                    if await btn.count() > 0:
                        await btn.click()
                        await page.wait_for_timeout(4000)
                        break
                except Exception:
                    pass

            await page.wait_for_timeout(2000)

            # --- Extraer prima ---
            prima_anual = None
            pct_devolucion = None
            frecuencia = perfil.frecuencia_pago

            if captured.get("response"):
                data = captured["response"]
                for campo in ["prima", "primaMensual", "primaAnual", "monto", "amount", "cuota", "price"]:
                    if campo in data:
                        val = float(str(data[campo]).replace(",", "").replace("S/", "").strip())
                        if "ensual" in campo or "uota" in campo:
                            prima_anual = val * 12
                            frecuencia = "mensual"
                        else:
                            prima_anual = val
                        break
                for campo_dev in ["devolucion", "porcentajeDevolucion", "pctDevolucion"]:
                    if campo_dev in data:
                        pct_devolucion = float(data[campo_dev])
                        break

            # Fallback DOM
            if not prima_anual:
                content = await page.content()
                matches = re.findall(r"S/\.?\s*([\d,]+\.?\d*)", content)
                for m in matches:
                    try:
                        val = float(m.replace(",", ""))
                        if 50 <= val <= 15000:
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
                    vigencia_anios=vigencia,
                    frecuencia_pago=frecuencia,
                    prima_anual_pen=0,
                    fuente_url=COTIZADOR_URL,
                    confianza="baja",
                    error="Mapfre: formulario no completado o prima no visible. Inspección manual requerida.",
                )

            return Cotizacion(
                competidor=COMPETIDOR,
                producto=PRODUCTO,
                perfil_id=perfil.id,
                perfil_nombre=perfil.nombre,
                edad=perfil.edad,
                sexo=perfil.sexo,
                suma_asegurada_pen=perfil.suma_asegurada_pen,
                vigencia_anios=vigencia,
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
                vigencia_anios=vigencia,
                frecuencia_pago=perfil.frecuencia_pago,
                prima_anual_pen=0,
                fuente_url=COTIZADOR_URL,
                confianza="baja",
                error=f"Error Playwright: {str(e)[:200]}",
            )
