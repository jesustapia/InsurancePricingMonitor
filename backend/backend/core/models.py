"""
Modelos de datos compartidos del agente de monitoreo.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import date


@dataclass
class Perfil:
    """Perfil de cotización configurado por el usuario."""
    id: int
    nombre: str
    edad: int
    sexo: str                    # "M" | "F"
    suma_asegurada_pen: float
    vigencia_anios: int
    frecuencia_pago: str         # mensual | trimestral | semestral | anual
    fumador: bool
    prima_rimac_ref_pen: Optional[float] = None  # referencia interna Rímac

    @property
    def tasa_rimac(self) -> Optional[float]:
        if self.prima_rimac_ref_pen:
            return self.prima_rimac_ref_pen / self.suma_asegurada_pen
        return None


@dataclass
class Cotizacion:
    """Resultado de una cotización extraída de un competidor."""
    competidor: str              # "Pacifico" | "Interseguro" | "Mapfre"
    producto: str
    perfil_id: int
    perfil_nombre: str
    edad: int
    sexo: str
    suma_asegurada_pen: float
    vigencia_anios: int
    frecuencia_pago: str
    prima_anual_pen: float
    porcentaje_devolucion: Optional[float] = None
    moneda_original: str = "PEN"
    tc_usado: float = 3.5
    fuente_url: str = ""
    confianza: str = "alta"      # alta | media | baja
    notas: str = ""
    error: Optional[str] = None  # si hubo problema al cotizar


@dataclass
class ResultadoComparacion:
    """Cotización + métricas comparativas vs Rímac."""
    cotizacion: Cotizacion
    tasa_competidor: float       # prima_anual / suma_asegurada
    tasa_rimac: Optional[float]  # None si no hay referencia
    delta: Optional[float]       # tasa_rimac / tasa_competidor
    senal: str                   # CARO | COMPETITIVO | BARATO | SIN_REFERENCIA
    fecha_ejecucion: str = field(default_factory=lambda: date.today().isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["cotizacion"] = asdict(self.cotizacion)
        return d
