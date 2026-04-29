"""
Collector de Interseguro — Vida Cash Devolución.

Flujo real (3 pasos):
  1. GET token JWT  → token_generate_prod
  2. GET datos cliente → client_data_prod (valida DNI ficticio)
  3. POST cotización → data_gateway_prod/gateway

El token JWT expira y se renueva en cada ejecución.
DNI ficticio: 999999999 (registrado previamente en Interseguro).
"""
import httpx
import uuid
from datetime import datetime
from core.models import Cotizacion, Perfil

BASE_URL       = "https://us-east4-interseguro-vida.cloudfunctions.net"
TOKEN_URL      = f"{BASE_URL}/token_generate_prod?product=VIDACASH&channel=WE"
CLIENT_URL     = f"{BASE_URL}/client_data_prod/data/999999999?product=VIDACASH"
GATEWAY_URL    = f"{BASE_URL}/data_gateway_prod/gateway"

COMPETIDOR     = "Interseguro"
PRODUCTO       = "Vida Cash Devolución Plus"
TC             = 3.5
PCT_DEVOLUCION = 125
DNI_FICTICIO   = "999999999"

BROWSER_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "es-ES,es;q=0.9",
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


async def _get_token(client: httpx.AsyncClient) -> str:
    """Obtiene JWT token fresco."""
    resp = await client.get(TOKEN_URL, headers=BROWSER_HEADERS)
    resp.raise_for_status()
    token = resp.json()
    # El token viene como string JSON con comillas
    if isinstance(token, str):
        token = token.strip('"')
    return token


async def _get_client_data(client: httpx.AsyncClient, token: str) -> dict:
    """Valida el DNI ficticio y obtiene datos del cliente."""
    headers = {**BROWSER_HEADERS, "authorization": f"Bearer {token}"}
    resp = await client.get(CLIENT_URL, headers=headers)
    resp.raise_for_status()
    return resp.json()


async def cotizar_interseguro(perfil: Perfil) -> Cotizacion:
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            # Paso 1: obtener token JWT
            token = await _get_token(client)

            # Paso 2: validar cliente (necesario para que el gateway acepte)
            await _get_client_data(client, token)

            # Paso 3: cotizar
            headers = {
                **BROWSER_HEADERS,
                "content-type": "application/json",
                "authorization": f"Bearer {token}",
            }
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

            resp = await client.post(GATEWAY_URL, json=payload, headers=headers)
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
