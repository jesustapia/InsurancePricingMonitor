"""
Collector de Interseguro — Vida Cash Devolución.
Sin token — headers exactos del HAR exitoso.
"""
import httpx
from core.models import Cotizacion, Perfil

GATEWAY_URL    = "https://us-east4-interseguro-vida.cloudfunctions.net/data_gateway_prod/gateway"
COMPETIDOR     = "Interseguro"
PRODUCTO       = "Vida Cash Devolución Plus"
TC             = 3.5
PCT_DEVOLUCION = 125
DNI_FICTICIO   = "999999999"

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "es-ES,es;q=0.9",
    "content-type": "application/json",
    "origin": "https://www.interseguro.pe",
    "referer": "https://www.interseguro.pe/",
    "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "cross-site",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
}

async def cotizar_interseguro(perfil: Perfil) -> Cotizacion:
    payload = {
        "api_id": "6902431292ec24791f84124b",
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
            "document": DNI_FICTICIO,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=25, headers=HEADERS) as client:
            resp = await client.post(GATEWAY_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()

        if data.get("code") != "01":
            raise ValueError(f"code={data.get('code')}: {data.get('message')}")

        params        = data["data"]["data"]["parametros_almacenados"]
        plan          = params.get("no_plus") or list(params.values())[0]
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
