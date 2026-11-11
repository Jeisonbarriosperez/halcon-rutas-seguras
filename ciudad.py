"""
La ciudad que usa Halcón: Bucaramanga, con sus 17 comunas urbanas.

Las comunas, sus coordenadas, los barrios y las conexiones entre comunas salen de los datos reales
(las arma 3_entrenar_modelo.py y las guarda en modelo/ciudad.json). Aquí también se calculan los
festivos oficiales de Colombia para cualquier año.
"""
import json
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

CIUDAD = 'Bucaramanga'
CENTRO = (7.1193, -73.1227)
ARCHIVO = Path(__file__).parent / 'modelo' / 'ciudad.json'

CONFINAMIENTO = (date(2020, 3, 25), date(2020, 8, 31))   # aislamiento obligatorio por la pandemia


def cargar():
    """Devuelve (comunas, barrios, aristas) desde modelo/ciudad.json."""
    if not ARCHIVO.exists():
        return {}, [], []
    datos = json.loads(ARCHIVO.read_text(encoding='utf-8'))
    comunas = {c['comuna_id']: c for c in datos['comunas']}
    return comunas, datos['barrios'], datos['aristas']


COMUNAS, BARRIOS, ARISTAS = cargar()
NOMBRE_A_ID = {c['nombre']: cid for cid, c in COMUNAS.items()}


# ---------------------------------------------------------------- FESTIVOS DE COLOMBIA
def _pascua(anio):
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(anio, mes, dia)


def _lunes(d):
    return d + timedelta(days=(7 - d.weekday()) % 7)


@lru_cache(maxsize=None)
def festivos(anio):
    """Festivos oficiales (Ley 51 de 1983, ley Emiliani)."""
    fijos = [date(anio, 1, 1), date(anio, 5, 1), date(anio, 7, 20), date(anio, 8, 7), date(anio, 12, 8),
             date(anio, 12, 25)]
    trasladables = [date(anio, 1, 6), date(anio, 3, 19), date(anio, 6, 29), date(anio, 8, 15), date(anio, 10, 12),
                    date(anio, 11, 1), date(anio, 11, 11)]
    p = _pascua(anio)
    semana_santa = [p - timedelta(days=3), p - timedelta(days=2)]
    de_pascua = [_lunes(p + timedelta(days=39)), _lunes(p + timedelta(days=60)), _lunes(p + timedelta(days=68))]
    return frozenset(fijos + [_lunes(d) for d in trasladables] + semana_santa + de_pascua)


def es_festivo(d):
    return int(d in festivos(d.year))


def es_puente(d):
    """Fin de semana largo: sábado o domingo antes de un lunes festivo, o el lunes festivo."""
    lunes = d + timedelta(days=(7 - d.weekday()) % 7) if d.weekday() >= 5 else d
    return int(lunes.weekday() == 0 and es_festivo(lunes) and (d - lunes).days <= 0 and (lunes - d).days <= 2)


def es_quincena(d):
    return int(d.day in (14, 15, 16, 29, 30, 31, 1))


def en_confinamiento(d):
    return int(CONFINAMIENTO[0] <= d <= CONFINAMIENTO[1])
