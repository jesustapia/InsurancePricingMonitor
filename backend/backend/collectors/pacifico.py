"""
Collector de Pacífico Seguros — Vida Devolución Total.
API REST abierta — requiere headers de browser para evitar 403.
"""
import httpx
from datetime import date
from core.models import Cotizacion, Perfil

API_BASE   = "https://web.pacificoseguros.com/canales/servicios/api/cotizadores/vida/table"
COMPETIDOR = "Pacifico"
PRODUCTO   = "Vida Devolución Total Soles"
TC         = 3.5
VIGENCIAS  = {10, 15, 20}
HEADERS    = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://web.pacificoseguros.com/canales/servicios/cotizadores/vida",
    "Origin": "https://web.pacificoseguros.com",
    "Accept": "application/json, text/plain, */*",
}

async def cotizar_pacifico(perfil: Perfil) -> Cotizacion:
    vigencia  = min(VIGENCIAS, key=lambda v: abs(v - perfil.vigencia_anios))
    anio_nac  = date.today().year - perfil.edad
    fecha_enc = f"15%2F01%2F{anio_nac}"
    sa_usd    = perfil.suma_asegurada_pen / TC
    url       = f"{API_BASE}?insurance_years={vigencia}&born_date={fecha_enc}"

    try:
        async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        if data.get("errors") or not data.get("data"):
            raise ValueError(f"API error: {data}")

        tabla    = data["data"]
        edad_key = list(tabla.keys())[0]
        precios  = tabla[edad_key]
        sa_key   = min(precios.keys(), key=lambda k: abs(float(k.replace(",", "")) - sa_usd))
        sa_cotizada_usd   = float(sa_key.replace(",", ""))
        prima_mensual_usd = float(precios[sa_key])
        prima_anual_pen   = round(prima_mensual_usd * 12 * TC, 2)

        return Cotizacion(
            competidor=COMPETIDOR, producto=PRODUCTO,
            perfil_id=perfil.id, perfil_nombre=perfil.nombre,
            edad=perfil.edad, sexo=perfil.sexo,
            suma_asegurada_pen=round(sa_cotizada_usd * TC, 2),
            vigencia_anios=vigencia, frecuencia_pago="mensual",
            prima_anual_pen=prima_anual_pen,
            porcentaje_devolucion=100.0, moneda_original="USD",
            tc_usado=TC, fuente_url=url, confianza="alta",
            notas=f"USD {sa_key} · prima mensual USD {prima_mensual_usd}",
        )
    except Exception as e:
        return Cotizacion(
            competidor=COMPETIDOR, producto=PRODUCTO,
            perfil_id=perfil.id, perfil_nombre=perfil.nombre,
            edad=perfil.edad, sexo=perfil.sexo,
            suma_asegurada_pen=perfil.suma_asegurada_pen,
            vigencia_anios=vigencia, frecuencia_pago="mensual",
            prima_anual_pen=0, fuente_url=API_BASE, confianza="baja",
            error=f"Pacífico API: {str(e)[:200]}",
        )
