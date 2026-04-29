"""
Motor de cálculo: convierte cotizaciones crudas en métricas comparativas.
"""
from core.models import Cotizacion, Perfil, ResultadoComparacion
from typing import List, Optional

TC_USD_PEN = 3.5

# Umbrales para la señal competitiva
UMBRAL_CARO        = 1.05   # Rímac > 5% más caro que el competidor
UMBRAL_BARATO      = 0.95   # Rímac > 5% más barato que el competidor


def normalizar_a_anual(prima: float, frecuencia: str) -> float:
    """Convierte prima en la frecuencia dada a prima anual equivalente."""
    factor = {"mensual": 12, "trimestral": 4, "semestral": 2, "anual": 1}
    return prima * factor.get(frecuencia, 1)


def calcular_tasa(prima_anual_pen: float, suma_asegurada_pen: float) -> float:
    return round(prima_anual_pen / suma_asegurada_pen, 6)


def calcular_senal(delta: Optional[float]) -> str:
    if delta is None:
        return "SIN_REFERENCIA"
    if delta > UMBRAL_CARO:
        return "CARO"
    if delta < UMBRAL_BARATO:
        return "BARATO"
    return "COMPETITIVO"


def procesar_cotizacion(
    cotizacion: Cotizacion,
    perfil: Perfil,
) -> ResultadoComparacion:
    """
    Toma una cotización cruda y produce el resultado comparativo.
    La prima en la cotización debe estar en PEN/año al llegar aquí.
    """
    tasa_comp = calcular_tasa(cotizacion.prima_anual_pen, cotizacion.suma_asegurada_pen)
    tasa_rimac = perfil.tasa_rimac
    delta = round(tasa_rimac / tasa_comp, 4) if tasa_rimac else None
    senal = calcular_senal(delta)

    return ResultadoComparacion(
        cotizacion=cotizacion,
        tasa_competidor=tasa_comp,
        tasa_rimac=tasa_rimac,
        delta=delta,
        senal=senal,
    )


def procesar_lote(
    cotizaciones: List[Cotizacion],
    perfiles: List[Perfil],
) -> List[ResultadoComparacion]:
    perfil_map = {p.id: p for p in perfiles}
    resultados = []
    for c in cotizaciones:
        perfil = perfil_map.get(c.perfil_id)
        if perfil:
            resultados.append(procesar_cotizacion(c, perfil))
    return resultados
