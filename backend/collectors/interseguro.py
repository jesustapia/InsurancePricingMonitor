"""
Collector de Interseguro — Vida Cash Devolución.
Google Cloud Function — no requiere sesión, usa DNI ficticio.
"""
import httpx
from core.models import Cotizacion, Perfil

GATEWAY_URL    = "https://us-east4-interseguro-vida.cloudfunctions.net/data_gateway_prod/gateway"
API_ID         = "6902431292ec24791f84124b"
COMPETIDOR     = "Interseguro"
PRODUCTO       = "Vida Cash Devolución"
TC             = 3.5
PCT_DEVOLUCION = 145
HEADERS        = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Origin": "https://www.interseguro.pe",
    "Referer": "https://www.interseguro.pe/seguro-de-vida/vida-cash-plus/paso/cotiza",
}

async def cotizar_interseguro(perfil: Perfil) -> Cotizacion:
    payload = {
        "api_id": API_ID,
        "product": "VIDACASH",
        "body": {
            "producto": "VIDA_CASH_DEVOLUCION",
            "parametros": {
                "edad_actuarial": perfil.edad,
                "periodo_vigencia": perfil.vigencia_anios,
                "periodo_pago_primas": perfil.vigencia_anios,
                "suma_asegurada": int(perfil.suma_asegurada_pen),
                "sexo": "M" if perfil.sexo.upper() == "M" else "F",
                "porcentaje_devolucion": PCT_DEVOLUCION,
            },
            "document": "99999999",
        },
    }

    try:
        async with httpx.AsyncClient(timeout=20, headers=HEADERS) as client:
            resp = await client.post(GATEWAY_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()

        if data.get("code") != "01":
            raise ValueError(f"code={data.get('code')}: {data.get('message')}")

        params = data["data"]["data"]["parametros_almacenados"]
        plan   = params.get("no_plus") or list(params.values())[0]
        prima_mensual = float(plan["coberturas"]["fallecimiento"]["prima_asignada"])
        prima_anual   = round(prima_mensual * 12, 2)

        return Cotizacion(
            competidor=COMPETIDOR, producto=PRODUCTO,
            perfil_id=perfil.id, perfil_nombre=perfil.nombre,
            edad=perfil.edad, sexo=perfil.sexo,
            suma_asegurada_pen=perfil.suma_asegurada_pen,
            vigencia_anios=perfil.vigencia_anios, frecuencia_pago="mensual",
            prima_anual_pen=prima_anual,
            porcentaje_devolucion=float(PCT_DEVOLUCION),
            moneda_original="PEN", tc_usado=TC,
            fuente_url=GATEWAY_URL, confianza="alta",
            notas=f"prima mensual S/ {prima_mensual:.2f} · dev {PCT_DEVOLUCION}%",
        )
    except Exception as e:
        return Cotizacion(
            competidor=COMPETIDOR, producto=PRODUCTO,
            perfil_id=perfil.id, perfil_nombre=perfil.nombre,
            edad=perfil.edad, sexo=perfil.sexo,
            suma_asegurada_pen=perfil.suma_asegurada_pen,
            vigencia_anios=perfil.vigencia_anios, frecuencia_pago="mensual",
            prima_anual_pen=0, fuente_url=GATEWAY_URL, confianza="baja",
            error=f"Interseguro API: {str(e)[:200]}",
        )
