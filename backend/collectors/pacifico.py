"""
Collector de Pacífico Seguros — Vida Devolución Total.

Estrategia:
  El cotizador es una SPA React en web.pacificoseguros.com.
  Usamos Playwright para navegar, seleccionar parámetros y capturar
  la respuesta del servidor (intercepción de red) o leer el DOM final.

Producto equivalente a VidAhorroGarantizado de Rímac:
  → Vida Devolución Total Soles (plazo 10/15/20a, SA desde S/100k)
"""
import json
import re
import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Page, Response

from core.models import Cotizacion, Perfil

COTIZADOR_URL  = "https://web.pacificoseguros.com/canales/servicios/cotizadores/vida"
COTIZADOR_URL2 = "https://www.pacifico.com.pe/seguros/vida/vida-devolucion"  # fallback
COMPETIDOR    = "Pacifico"
PRODUCTO      = "Vida Devolución Total Soles"

# Mapeo de vigencias soportadas por Pacífico
VIGENCIAS_SOPORTADAS = {10, 15, 20}


async def _interceptar_cotizacion(page: Page) -> Optional[dict]:
    """
    Espera y captura la respuesta JSON del servidor al cotizar.
    Devuelve el dict crudo del response, o None si no llegó.
    """
    resultado = {}

    async def on_response(response: Response):
        url = response.url.lower()
        if any(kw in url for kw in ["cotiz", "prima", "quot", "price", "tarif"]):
            try:
                body = await response.text()
                if body.strip().startswith("{") or body.strip().startswith("["):
                    resultado["data"] = json.loads(body)
            except Exception:
                pass

    page.on("response", on_response)
    return resultado


async def _leer_prima_del_dom(page: Page) -> Optional[float]:
    """
    Intenta leer la prima directamente del DOM después del render.
    Busca patrones numéricos asociados a 'S/' o 'prima'.
    """
    await page.wait_for_timeout(2000)
    content = await page.content()

    # Buscar montos tipo S/ 1,234 o 1234.56
    patrones = [
        r"S/\s*([\d,]+\.?\d*)",
        r"prima[^0-9]*([\d,]+\.?\d*)",
        r"([\d,]+\.?\d*)\s*(?:soles|mensual|anual)",
    ]
    for pat in patrones:
        matches = re.findall(pat, content, re.IGNORECASE)
        if matches:
            # Tomar el primero razonable (entre 50 y 50000 soles)
            for m in matches:
                try:
                    valor = float(m.replace(",", ""))
                    if 50 <= valor <= 50000:
                        return valor
                except ValueError:
                    continue
    return None


async def cotizar_pacifico(perfil: Perfil) -> Cotizacion:
    """
    Cotiza en Pacífico para el perfil dado.
    Retorna Cotizacion con prima_anual_pen o con error si no pudo.
    """
    # Verificar vigencia soportada
    if perfil.vigencia_anios not in VIGENCIAS_SOPORTADAS:
        vigencia_ajustada = min(VIGENCIAS_SOPORTADAS, key=lambda v: abs(v - perfil.vigencia_anios))
    else:
        vigencia_ajustada = perfil.vigencia_anios

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            locale="es-PE",
        )
        page = await context.new_page()

        try:
            # Activar intercepción antes de navegar
            intercept = await _interceptar_cotizacion(page)

            await page.goto(COTIZADOR_URL, wait_until="networkidle", timeout=30000)

            # --- Llenar fecha de nacimiento (calcula la edad internamente) ---
            from datetime import date
            anio_nac = date.today().year - perfil.edad
            fecha_nac = f"{anio_nac}-01-15"  # 15 enero, evita edge cases de cumpleaños

            dob_input = page.locator("input[type='date'], input[placeholder*='nacimiento'], input[placeholder*='fecha']").first
            if await dob_input.count() > 0:
                await dob_input.fill(fecha_nac)
                await page.keyboard.press("Tab")
                await page.wait_for_timeout(800)

            # --- Seleccionar vigencia / plazo ---
            # Pacífico muestra los plazos como botones o select
            plazo_selectores = [
                f"text={vigencia_ajustada} años",
                f"text={vigencia_ajustada}",
                f"[data-plazo='{vigencia_ajustada}']",
                f"button:has-text('{vigencia_ajustada}')",
            ]
            for sel in plazo_selectores:
                try:
                    btn = page.locator(sel).first
                    if await btn.count() > 0:
                        await btn.click()
                        await page.wait_for_timeout(600)
                        break
                except Exception:
                    pass

            # --- Esperar render de precios ---
            await page.wait_for_timeout(3000)

            # --- Intentar leer prima de intercepción de red primero ---
            prima_anual = None
            frecuencia_detectada = perfil.frecuencia_pago

            if intercept.get("data"):
                data = intercept["data"]
                # Los campos pueden variar — intentamos varios nombres comunes
                for campo in ["prima", "primaMensual", "primaAnual", "amount", "price", "monto"]:
                    if campo in data:
                        val = float(data[campo])
                        if "ensual" in campo or "monthly" in campo.lower():
                            prima_anual = val * 12
                            frecuencia_detectada = "mensual"
                        else:
                            prima_anual = val
                        break

            # --- Fallback: leer del DOM ---
            if not prima_anual:
                prima_dom = await _leer_prima_del_dom(page)
                if prima_dom:
                    # Pacífico muestra prima mensual por defecto
                    prima_anual = prima_dom * 12
                    frecuencia_detectada = "mensual"

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
                    vigencia_anios=vigencia_ajustada,
                    frecuencia_pago=frecuencia_detectada,
                    prima_anual_pen=0,
                    confianza="baja",
                    fuente_url=COTIZADOR_URL,
                    error="No se pudo extraer la prima del cotizador. Requiere inspección manual del DOM.",
                )

            return Cotizacion(
                competidor=COMPETIDOR,
                producto=PRODUCTO,
                perfil_id=perfil.id,
                perfil_nombre=perfil.nombre,
                edad=perfil.edad,
                sexo=perfil.sexo,
                suma_asegurada_pen=perfil.suma_asegurada_pen,
                vigencia_anios=vigencia_ajustada,
                frecuencia_pago=frecuencia_detectada,
                prima_anual_pen=round(prima_anual, 2),
                porcentaje_devolucion=100.0,  # Pacífico VDT = 100% devolución
                moneda_original="PEN",
                tc_usado=3.5,
                fuente_url=COTIZADOR_URL,
                confianza="media",
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
                vigencia_anios=vigencia_ajustada,
                frecuencia_pago=perfil.frecuencia_pago,
                prima_anual_pen=0,
                fuente_url=COTIZADOR_URL,
                confianza="baja",
                error=f"Error Playwright: {str(e)[:200]}",
            )
