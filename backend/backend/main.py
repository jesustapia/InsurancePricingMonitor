"""
Backend FastAPI del agente de monitoreo de mercado.
Deploy en Railway · Autenticación por X-API-Key header.
"""
import asyncio
import os
import json
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Security, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel

from core.models import Perfil, Cotizacion
from core.calculator import procesar_lote
from output.reporter import generar_reporte_json
from collectors.pacifico import cotizar_pacifico
from collectors.interseguro import cotizar_interseguro
from collectors.mapfre import cotizar_mapfre

# ── Configuración ──────────────────────────────────────────────────────────────
API_KEY        = os.environ.get("API_KEY", "cambia-esta-clave-secreta")
ALLOWED_ORIGIN = os.environ.get("FRONTEND_URL", "*")   # URL de tu Netlify

app = FastAPI(title="Agente Monitoreo Vida Individual", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN, "http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

def verificar_key(key: str = Security(api_key_header)):
    if key != API_KEY:
        raise HTTPException(status_code=403, detail="API key inválida")
    return key

# ── Colectores disponibles ──────────────────────────────────────────────────────
COLLECTORS = {
    "pacifico":    cotizar_pacifico,
    "interseguro": cotizar_interseguro,
    "mapfre":      cotizar_mapfre,
}

# Cache en memoria del último reporte (persiste mientras el container esté vivo)
ultimo_reporte: Optional[dict] = None
estado_ejecucion: dict = {"estado": "idle", "inicio": None, "progreso": 0}

# ── Modelos Pydantic ────────────────────────────────────────────────────────────
class PerfilInput(BaseModel):
    id: int
    nombre: str
    edad: int
    sexo: str
    suma_asegurada_pen: float
    vigencia_anios: int
    frecuencia_pago: str = "mensual"
    fumador: bool = False
    prima_rimac_ref_pen: Optional[float] = None

class CotizarRequest(BaseModel):
    perfiles: List[PerfilInput]
    competidores: List[str] = ["pacifico", "interseguro", "mapfre"]

# ── Endpoints ──────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/estado")
def get_estado(key: str = Security(verificar_key)):
    return estado_ejecucion


@app.get("/ultimo-reporte")
def get_ultimo_reporte(key: str = Security(verificar_key)):
    if not ultimo_reporte:
        return {"reporte": None, "mensaje": "Aún no se ha ejecutado ninguna cotización"}
    return {"reporte": ultimo_reporte}


@app.post("/cotizar")
async def cotizar(
    request: CotizarRequest,
    background_tasks: BackgroundTasks,
    key: str = Security(verificar_key),
):
    if estado_ejecucion["estado"] == "running":
        raise HTTPException(status_code=409, detail="Ya hay una cotización en progreso")

    # Validar competidores
    invalidos = [c for c in request.competidores if c not in COLLECTORS]
    if invalidos:
        raise HTTPException(status_code=400, detail=f"Competidores inválidos: {invalidos}")

    # Convertir a modelos internos
    perfiles = [
        Perfil(
            id=p.id, nombre=p.nombre, edad=p.edad, sexo=p.sexo,
            suma_asegurada_pen=p.suma_asegurada_pen, vigencia_anios=p.vigencia_anios,
            frecuencia_pago=p.frecuencia_pago, fumador=p.fumador,
            prima_rimac_ref_pen=p.prima_rimac_ref_pen,
        )
        for p in request.perfiles
    ]

    background_tasks.add_task(_ejecutar_cotizaciones, perfiles, request.competidores)
    return {"mensaje": "Cotización iniciada", "total_tareas": len(perfiles) * len(request.competidores)}


async def _ejecutar_cotizaciones(perfiles: List[Perfil], competidores: List[str]):
    global ultimo_reporte, estado_ejecucion

    total = len(perfiles) * len(competidores)
    estado_ejecucion = {"estado": "running", "inicio": datetime.now().isoformat(), "progreso": 0, "total": total}

    tareas = []
    for perfil in perfiles:
        for nombre_comp in competidores:
            tareas.append(COLLECTORS[nombre_comp](perfil))

    cotizaciones: List[Cotizacion] = []
    completadas = 0
    for coro in asyncio.as_completed(tareas):
        resultado = await coro
        cotizaciones.append(resultado)
        completadas += 1
        estado_ejecucion["progreso"] = round(completadas / total * 100)

    resultados = procesar_lote(cotizaciones, perfiles)
    ultimo_reporte = generar_reporte_json(resultados)
    estado_ejecucion = {"estado": "done", "inicio": estado_ejecucion["inicio"],
                        "fin": datetime.now().isoformat(), "progreso": 100, "total": total}
