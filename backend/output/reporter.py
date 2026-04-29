"""
Generador de reporte del agente de monitoreo.
Produce JSON estructurado + resumen de texto con señales.
"""
import json
from datetime import datetime
from typing import List
from core.models import ResultadoComparacion

SENAL_EMOJI = {
    "CARO":           "⚠️  CARO",
    "COMPETITIVO":    "✅  COMPETITIVO",
    "BARATO":         "🟢  BARATO",
    "SIN_REFERENCIA": "⬜  SIN REF",
}


def generar_reporte_json(
    resultados: List[ResultadoComparacion],
    config_meta: dict = None,
) -> dict:
    """
    Genera el JSON final estructurado del reporte.
    """
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")

    reporte = {
        "meta": {
            "fecha_ejecucion": fecha,
            "tc_usd_pen": 3.5,
            "umbral_caro": 1.05,
            "umbral_barato": 0.95,
            **(config_meta or {}),
        },
        "resumen": _calcular_resumen(resultados),
        "resultados": [r.to_dict() for r in resultados],
    }
    return reporte


def _calcular_resumen(resultados: List[ResultadoComparacion]) -> dict:
    total = len(resultados)
    exitosos = [r for r in resultados if not r.cotizacion.error]
    errores = total - len(exitosos)

    por_senal = {"CARO": 0, "COMPETITIVO": 0, "BARATO": 0, "SIN_REFERENCIA": 0}
    por_competidor = {}

    for r in exitosos:
        por_senal[r.senal] = por_senal.get(r.senal, 0) + 1
        comp = r.cotizacion.competidor
        if comp not in por_competidor:
            por_competidor[comp] = {"exitosos": 0, "errores": 0}
        por_competidor[comp]["exitosos"] += 1

    for r in resultados:
        if r.cotizacion.error:
            comp = r.cotizacion.competidor
            if comp not in por_competidor:
                por_competidor[comp] = {"exitosos": 0, "errores": 0}
            por_competidor[comp]["errores"] += 1

    return {
        "total_cotizaciones": total,
        "exitosas": len(exitosos),
        "errores": errores,
        "por_senal": por_senal,
        "por_competidor": por_competidor,
    }


def imprimir_reporte_tabla(resultados: List[ResultadoComparacion]):
    """
    Imprime un resumen tabular legible en consola.
    """
    print("\n" + "=" * 90)
    print(f"  REPORTE DE MONITOREO COMPETITIVO — VIDA INDIVIDUAL PERÚ")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 90)

    header = f"{'Perfil':<22} {'Competidor':<14} {'Producto':<26} {'Prima/año':<12} {'Tasa':<8} {'δ':<7} {'Señal'}"
    print(header)
    print("-" * 90)

    exitosos = [r for r in resultados if not r.cotizacion.error]
    errores  = [r for r in resultados if r.cotizacion.error]

    for r in exitosos:
        c = r.cotizacion
        prima_fmt = f"S/ {c.prima_anual_pen:,.0f}"
        tasa_fmt  = f"{r.tasa_competidor:.4f}"
        delta_fmt = f"{r.delta:.3f}" if r.delta else "  -  "
        senal_fmt = SENAL_EMOJI.get(r.senal, r.senal)
        print(
            f"{c.perfil_nombre:<22} {c.competidor:<14} {c.producto[:24]:<26} "
            f"{prima_fmt:<12} {tasa_fmt:<8} {delta_fmt:<7} {senal_fmt}"
        )

    if errores:
        print("\n⚠️  Cotizaciones con error:")
        for r in errores:
            c = r.cotizacion
            print(f"  · {c.competidor} / {c.perfil_nombre}: {c.error}")

    # Resumen
    resumen = _calcular_resumen(resultados)
    print("\n" + "-" * 90)
    print(f"  Exitosas: {resumen['exitosas']}/{resumen['total_cotizaciones']}  |  "
          f"Caro: {resumen['por_senal']['CARO']}  "
          f"Competitivo: {resumen['por_senal']['COMPETITIVO']}  "
          f"Barato: {resumen['por_senal']['BARATO']}  "
          f"Sin ref: {resumen['por_senal']['SIN_REFERENCIA']}")
    print("=" * 90 + "\n")
