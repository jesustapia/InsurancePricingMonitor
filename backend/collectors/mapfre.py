"""
Collector de Mapfre — Sin cotizador online disponible.
El producto Ahorro Devolución solo se cotiza a través de asesor comercial.
"""
from core.models import Cotizacion, Perfil

COMPETIDOR = "Mapfre"
PRODUCTO   = "Ahorro Devolución"

async def cotizar_mapfre(perfil: Perfil) -> Cotizacion:
    return Cotizacion(
        competidor=COMPETIDOR, producto=PRODUCTO,
        perfil_id=perfil.id, perfil_nombre=perfil.nombre,
        edad=perfil.edad, sexo=perfil.sexo,
        suma_asegurada_pen=perfil.suma_asegurada_pen,
        vigencia_anios=perfil.vigencia_anios,
        frecuencia_pago=perfil.frecuencia_pago,
        prima_anual_pen=0, confianza="baja",
        fuente_url="https://www.mapfreseguros.com.pe",
        error="Mapfre no tiene cotizador online. Requiere contacto con asesor comercial.",
    )
