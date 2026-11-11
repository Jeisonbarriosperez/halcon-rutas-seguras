"""
Lógica de Halcón: variables de cada comuna en un momento, predicción, rutas y explicaciones.
La usan el entrenamiento y la app, para que los dos calculen todo exactamente igual.
"""
import heapq
import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from ciudad import ARISTAS, BARRIOS, CENTRO, COMUNAS, en_confinamiento, es_festivo, es_puente, es_quincena

# ---------------------------------------------------------------- VARIABLES DEL MODELO
COLUMNAS = ['comuna_id', 'pct_subsidiado', 'franja', 'dia_semana', 'mes', 'anio', 'es_festivo', 'es_puente',
            'es_quincena', 'confinamiento', 'lluvia_mm', 'lluvia_previa_mm', 'temperatura']

NOMBRES_VARIABLES = {
    'comuna_id': 'La comuna',
    'pct_subsidiado': 'Nivel socioeconómico (% en régimen subsidiado)',
    'franja': 'Hora del día',
    'dia_semana': 'Día de la semana',
    'mes': 'Mes',
    'anio': 'Año',
    'es_festivo': 'Festivo',
    'es_puente': 'Puente festivo',
    'es_quincena': 'Quincena (día de pago)',
    'confinamiento': 'Confinamiento 2020',
    'lluvia_mm': 'Lluvia en esas 3 horas',
    'lluvia_previa_mm': 'Lluvia en las 3 horas anteriores',
    'temperatura': 'Temperatura',
}

NIVELES = ['Bajo', 'Medio', 'Alto']
TIPOS_INCIDENTE = ['hurto', 'violencia', 'accidente']
INCIDENTE_TEXTO = {'hurto': 'robos (celular, moto, bolso)', 'violencia': 'riñas y agresiones',
                   'accidente': 'accidentes con heridos'}

DIAS = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
         'septiembre', 'octubre', 'noviembre', 'diciembre']

MODOS = {'a_pie': 'A pie', 'bicicleta': 'Bicicleta', 'moto': 'Moto', 'carro': 'Carro o taxi'}
VELOCIDAD = {'a_pie': 4.5, 'bicicleta': 12, 'moto': 25, 'carro': 22}          # km/h promedio en la ciudad
PESO_MODO = {   # qué tanto le afecta cada tipo de incidente a quien va de cada forma
    'a_pie': {'hurto': 1.0, 'violencia': 0.9, 'accidente': 0.5},
    'bicicleta': {'hurto': 0.9, 'violencia': 0.6, 'accidente': 0.9},
    'moto': {'hurto': 0.8, 'violencia': 0.4, 'accidente': 1.0},
    'carro': {'hurto': 0.5, 'violencia': 0.3, 'accidente': 0.8},
}
PERFIL_OSRM = {'a_pie': 'foot', 'bicicleta': 'bike', 'moto': 'car', 'carro': 'car'}

UMBRALES = {'medio': 30.0, 'alto': 50.0}     # el entrenamiento los ajusta con los datos reales


def configurar_umbrales(medio, alto):
    UMBRALES['medio'], UMBRALES['alto'] = float(medio), float(alto)


def nivel_de(riesgo):
    if riesgo >= UMBRALES['alto']:
        return 'Alto'
    if riesgo >= UMBRALES['medio']:
        return 'Medio'
    return 'Bajo'


# ---------------------------------------------------------------- FRANJAS DE 3 HORAS
def franja_de(hora):
    return int(hora) // 3


def hora_texto(h, m=0):
    sufijo = 'a. m.' if h % 24 < 12 else 'p. m.'
    return f'{(h % 12) or 12}:{m:02d} {sufijo}'


def hora_corta(h):
    h %= 24
    if h == 0:
        return '12 a. m.'
    if h == 12:
        return '12 m.'
    return f'{h % 12} {"a. m." if h < 12 else "p. m."}'


def franja_texto(f):
    return f'de {hora_corta(f * 3)} a {hora_corta(f * 3 + 3)}'


def fecha_texto(momento):
    return f'{DIAS[momento.weekday()]} {momento.day} de {MESES[momento.month - 1]}'


def es_de_noche(franja):
    return franja in (0, 1, 6, 7)


def agregar_variables(df):
    """Variables derivadas que el modelo calcula por dentro (van dentro del pipeline)."""
    df = df.copy()
    centro = df['franja'].astype(float) * 3 + 1.5
    df['hora_sin'] = np.sin(2 * np.pi * centro / 24)
    df['hora_cos'] = np.cos(2 * np.pi * centro / 24)
    dia, f = df['dia_semana'].astype(int), df['franja'].astype(int)
    df['noche_de_fiesta'] = (((dia == 4) | (dia == 5)) & (f >= 6) | ((dia == 5) | (dia == 6)) & (f == 0)).astype(int)
    df['llueve'] = (df['lluvia_mm'].astype(float) >= 0.5).astype(int)
    df['comuna'] = df['comuna_id'].astype(int).astype(str)
    df['franja_txt'] = f.astype(str)
    df['dia_txt'] = dia.astype(str)
    return df


# ---------------------------------------------------------------- CLIMA
def clima_texto(lluvia_mm):
    if lluvia_mm >= 10:
        return 'Aguacero'
    if lluvia_mm >= 3:
        return 'Lluvia'
    if lluvia_mm >= 0.5:
        return 'Lluvia ligera'
    return 'Sin lluvia'


def icono_clima(lluvia_mm):
    if lluvia_mm >= 10:
        return 'thunderstorm'
    if lluvia_mm >= 0.5:
        return 'rainy'
    return 'partly_cloudy_day'


ESCENARIOS_LLUVIA = {'Sin lluvia': 0.0, 'Lluvia ligera': 1.5, 'Lluvia': 6.0, 'Aguacero': 15.0}


def pronostico_real(timeout=6):
    """Lluvia y temperatura de ayer, hoy y los próximos días en Bucaramanga (Open-Meteo). None si no hay internet."""
    import requests
    try:
        datos = requests.get('https://api.open-meteo.com/v1/forecast', timeout=timeout, params={
            'latitude': CENTRO[0], 'longitude': CENTRO[1], 'timezone': 'America/Bogota',
            'hourly': 'temperature_2m,precipitation', 'past_days': 1, 'forecast_days': 3,
            'current': 'temperature_2m,precipitation',
        }).json()
        horas = {datetime.fromisoformat(t): (mm or 0.0, temp)
                 for t, temp, mm in zip(datos['hourly']['time'], datos['hourly']['temperature_2m'],
                                        datos['hourly']['precipitation'])}
        return {'horas': horas, 'temperatura': datos['current']['temperature_2m'],
                'lluvia_mm': datos['current']['precipitation']}
    except Exception:
        return None


def clima_de_franja(pronostico, momento):
    """(lluvia en la franja, lluvia en la franja anterior, temperatura media) para el momento dado."""
    inicio = momento.replace(hour=franja_de(momento.hour) * 3, minute=0, second=0, microsecond=0)
    if not pronostico:
        return 0.0, 0.0, 22.0
    actual = [pronostico['horas'].get(inicio + timedelta(hours=i)) for i in range(3)]
    previa = [pronostico['horas'].get(inicio - timedelta(hours=i + 1)) for i in range(3)]
    actual = [a for a in actual if a]
    previa = [p for p in previa if p]
    if not actual:
        return 0.0, 0.0, 22.0
    return (round(sum(a[0] for a in actual), 1), round(sum(p[0] for p in previa), 1),
            round(sum(a[1] for a in actual) / len(actual), 1))


# ---------------------------------------------------------------- FILAS PARA EL MODELO
def fila(comuna_id, momento, lluvia_mm=0.0, lluvia_previa_mm=0.0, temperatura=22.0):
    d = momento.date()
    return {
        'comuna_id': int(comuna_id),
        'pct_subsidiado': float(COMUNAS[comuna_id]['pct_subsidiado']),
        'franja': franja_de(momento.hour),
        'dia_semana': d.weekday(),
        'mes': d.month,
        'anio': d.year,
        'es_festivo': es_festivo(d),
        'es_puente': es_puente(d),
        'es_quincena': es_quincena(d),
        'confinamiento': en_confinamiento(d),
        'lluvia_mm': float(lluvia_mm),
        'lluvia_previa_mm': float(lluvia_previa_mm),
        'temperatura': float(temperatura),
    }


def predecir(modelos, filas):
    """Agrega a cada fila: riesgo (% de que pase al menos un incidente en esas 3 horas), nivel y lo más probable."""
    filas = filas.copy()
    X = filas[COLUMNAS]
    m = modelos['nivel']
    p = m.predict_proba(X)
    clases = list(m.classes_)
    for nivel in NIVELES:
        filas['p_' + nivel.lower()] = p[:, clases.index(nivel)]
    filas['riesgo'] = ((1 - filas['p_bajo']) * 100).round(1)
    filas['nivel'] = filas['riesgo'].apply(nivel_de)
    # Qué tan común es cada tipo de incidente en esa comuna a esa hora (proporción real del historial)
    proporcion = modelos['tipo']
    claves = filas['comuna_id'].astype(int).astype(str) + '-' + filas['franja'].astype(int).astype(str)
    for tipo in TIPOS_INCIDENTE:
        filas['p_' + tipo] = claves.map(lambda k: proporcion.get(k, {}).get(tipo, 1 / 3))
    filas['incidente'] = filas[['p_' + x for x in TIPOS_INCIDENTE]].idxmax(axis=1).str[2:]
    return filas


def estado_ciudad(modelos, momento, lluvia_mm=0.0, lluvia_previa_mm=0.0, temperatura=22.0,
                  reportes=None, fallas=None):
    """Riesgo de las 17 comunas en un momento, más el ajuste por lo que reportan los vecinos."""
    filas = pd.DataFrame([fila(cid, momento, lluvia_mm, lluvia_previa_mm, temperatura) for cid in COMUNAS])
    est = predecir(modelos, filas)
    est['zona'] = est['comuna_id'].map(lambda c: COMUNAS[c]['nombre'])
    est['riesgo_modelo'] = est['riesgo']
    est['ajuste'] = 0.0
    reportes, fallas = reportes or {}, fallas or set()
    for i, cid in est['comuna_id'].items():
        extra = min(20.0, 6.0 * reportes.get(cid, 0))
        if cid in fallas and es_de_noche(franja_de(momento.hour)):
            extra += 8.0
        est.loc[i, 'ajuste'] = extra
    est['riesgo'] = (est['riesgo_modelo'] + est['ajuste']).clip(upper=99).round(1)
    est['nivel'] = est['riesgo'].apply(nivel_de)
    return est.set_index('comuna_id', drop=False)


def riesgo_para_modo(f, modo):
    peso = sum(f['p_' + t] * PESO_MODO[modo][t] for t in TIPOS_INCIDENTE)
    return float(f['riesgo']) * (0.75 + 0.25 * peso)


# ---------------------------------------------------------------- RUTAS (entre comunas vecinas)
def distancia_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, [a['lat'], a['lon'], b['lat'], b['lon']])
    d = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(d))


def _vecinos():
    vecinos = {c: [] for c in COMUNAS}
    for a, b in ARISTAS:
        km = distancia_km(COMUNAS[a], COMUNAS[b]) * 1.35          # calles en ladera: no son líneas rectas
        vecinos[a].append((b, km))
        vecinos[b].append((a, km))
    return vecinos


VECINOS = _vecinos()


def minutos_tramo(km, modo, franja):
    v = VELOCIDAD[modo]
    if modo in ('moto', 'carro', 'bicicleta') and franja in (2, 4, 6):    # horas pico: 6-9 a. m., 12-3 p. m., 6-9 p. m.
        v *= 0.75
    return km / v * 60


def _dijkstra(origen, destino, costo):
    cola, visto = [(0.0, origen, [origen])], set()
    while cola:
        c, nodo, camino = heapq.heappop(cola)
        if nodo == destino:
            return camino
        if nodo in visto:
            continue
        visto.add(nodo)
        for sig, km in VECINOS[nodo]:
            if sig not in visto:
                heapq.heappush(cola, (c + costo(nodo, sig, km), sig, camino + [sig]))
    return None


def _resumen(camino, modo, est, franja):
    riesgos = {c: riesgo_para_modo(est.loc[c], modo) for c in camino}
    km = sum(distancia_km(COMUNAS[a], COMUNAS[b]) * 1.35 for a, b in zip(camino, camino[1:]))
    if len(camino) == 1:
        km = 1.5
    peor = max(camino, key=lambda c: riesgos[c])
    de_paso = camino[1:-1]                                   # lo único que se puede esquivar
    peor_paso = max(de_paso, key=lambda c: riesgos[c]) if de_paso else None
    return {
        'zonas': camino,
        'minutos': max(3, round(minutos_tramo(km, modo, franja))),
        'km': round(km, 1),
        'riesgo': round(max(riesgos.values())),
        'riesgo_paso': round(riesgos[peor_paso]) if peor_paso else 0,
        'riesgos': riesgos,
        'peor_zona': peor,
        'peor_paso': peor_paso,
        'calles': [COMUNAS[c]['nombre'] for c in camino],
    }


def calcular_rutas(est, origen, destino, modo, franja):
    """La ruta habitual (la más corta) y la que sugiere Halcón (corta pero esquivando comunas calientes)."""
    def costo_corto(a, b, km):
        return km

    def costo_seguro(a, b, km):
        r = riesgo_para_modo(est.loc[b], modo)
        return km * (1 + 6 * (max(0.0, r - UMBRALES['medio'] * 0.6) / 70) ** 2)

    rapida = _resumen(_dijkstra(origen, destino, costo_corto), modo, est, franja)
    segura = _resumen(_dijkstra(origen, destino, costo_seguro), modo, est, franja)
    if segura['zonas'] == rapida['zonas'] or segura['riesgo_paso'] > rapida['riesgo_paso'] - 3:
        segura = rapida
    return rapida, segura


def geometria_osrm(zonas, modo, timeout=8):
    """Calles reales de OpenStreetMap que unen las comunas de la ruta. None si no hay internet."""
    import requests
    puntos = ';'.join(f'{COMUNAS[c]["lon"]:.6f},{COMUNAS[c]["lat"]:.6f}' for c in zonas)
    perfil = PERFIL_OSRM[modo]
    url = f'https://routing.openstreetmap.de/routed-{perfil}/route/v1/{"driving" if perfil == "car" else perfil}/{puntos}'
    try:
        r = requests.get(url, params={'overview': 'full', 'geometries': 'geojson'}, timeout=timeout,
                         headers={'User-Agent': 'Halcon-proyecto-academico'}).json()
        ruta = r['routes'][0]
        lon, lat = zip(*ruta['geometry']['coordinates'])
        return {'lat': list(lat), 'lon': list(lon), 'km': ruta['distance'] / 1000, 'min_osrm': ruta['duration'] / 60}
    except Exception:
        return None


# ---------------------------------------------------------------- EXPLICACIONES EN PALABRAS
def razones(modelos, f):
    """Qué está subiendo el riesgo: se cambia cada factor por uno 'tranquilo' y se mide cuánto baja."""
    base = {c: f[c] for c in COLUMNAS}
    variantes = []

    def agregar(cambios, texto):
        nueva = dict(base)
        nueva.update(cambios)
        variantes.append((texto, nueva))

    if base['lluvia_mm'] >= 0.5 or base['lluvia_previa_mm'] >= 0.5:
        agregar({'lluvia_mm': 0.0, 'lluvia_previa_mm': 0.0}, 'la lluvia')
    agregar({'franja': 4}, 'la hora (' + franja_texto(int(base['franja'])) + ')')
    if base['dia_semana'] >= 4:
        agregar({'dia_semana': 1}, 'que es ' + DIAS[int(base['dia_semana'])])
    if base['es_quincena']:
        agregar({'es_quincena': 0}, 'que es quincena')
    if base['es_festivo'] or base['es_puente']:
        agregar({'es_festivo': 0, 'es_puente': 0}, 'que es festivo')
    if base['temperatura'] >= 26:
        agregar({'temperatura': 22.0}, 'el calor')

    tabla = pd.DataFrame([v for _, v in variantes])
    nuevos = predecir(modelos, tabla)['riesgo'].values
    actual = float(f['riesgo_modelo']) if 'riesgo_modelo' in f else float(f['riesgo'])
    salida = [(t, round(actual - n, 1)) for (t, _), n in zip(variantes, nuevos)]
    if 'ajuste' in f and f['ajuste'] > 0:
        salida.append(('los reportes recientes de vecinos', float(f['ajuste'])))
    return sorted([s for s in salida if s[1] >= 1.5], key=lambda s: -s[1])


def unir(frases):
    frases = list(frases)
    if len(frases) <= 1:
        return ''.join(frases)
    return ', '.join(frases[:-1]) + ' y ' + frases[-1]


def riesgo_normal(modelos, momento, comuna_id):
    """Riesgo típico de esa comuna en esa franja: un martes cualquiera, sin lluvia."""
    m = momento
    while m.weekday() != 1:
        m -= timedelta(days=1)
    m = m.replace(hour=momento.hour)
    return float(predecir(modelos, pd.DataFrame([fila(comuna_id, m)]))['riesgo'].iloc[0])


def mensaje_principal(modelos, est, rapida, segura, momento, calientes=None):
    peor = rapida['peor_zona']
    nombre = COMUNAS[peor]['nombre']
    motivos = [t for t, _ in razones(modelos, est.loc[peor])[:2]]
    por = (' por ' + unir(motivos)) if motivos else ''
    normal = riesgo_normal(modelos, momento, peor)
    verbo = 'acaba de subir al' if rapida['riesgo'] >= normal + 6 else 'está en'
    barrios = ''
    if calientes:
        top = calientes.get(f'{peor}-{franja_de(momento.hour)}', [])[:2]
        if top:
            barrios = f' (sobre todo en {unir(top)})'

    if segura is not rapida:
        paso = rapida['peor_paso']
        motivos_paso = [t for t, _ in razones(modelos, est.loc[paso])[:2]]
        por_paso = (' por ' + unir(motivos_paso)) if motivos_paso else ''
        normal_paso = riesgo_normal(modelos, momento, paso)
        verbo_paso = 'acaba de subir al' if rapida['riesgo_paso'] >= normal_paso + 6 else 'está en'
        top = (calientes or {}).get(f'{paso}-{franja_de(momento.hour)}', [])[:2]
        barrios_paso = f' (sobre todo en {unir(top)})' if top else ''
        nuevas = [c for c in segura['zonas'] if c not in rapida['zonas']]
        via = COMUNAS[nuevas[0]]['nombre'] if nuevas else COMUNAS[segura['zonas'][1]]['nombre']
        extra = segura['minutos'] - rapida['minutos']
        tiempo = (f'Por {via} tardas {extra} minuto{"s" if extra != 1 else ""} más' if extra > 0
                  else f'Por {via} llegas casi en el mismo tiempo')
        return {'tipo': 'desvio', 'titulo': f'Te sugerimos desviar por {via}',
                'texto': f'En tu ruta habitual, el riesgo al pasar por {COMUNAS[paso]["nombre"]}{barrios_paso} '
                         f'{verbo_paso} {rapida["riesgo_paso"]:.0f}%{por_paso}. {tiempo} y esquivas esa zona.'}
    if rapida['riesgo'] >= UMBRALES['alto'] and peor in (rapida['zonas'][0], rapida['zonas'][-1]):
        donde = 'tu punto de salida' if peor == rapida['zonas'][0] else 'tu destino'
        return {'tipo': 'alerta', 'titulo': f'Lo más delicado es {donde}, {nombre}',
                'texto': f'Allí el riesgo {verbo} {rapida["riesgo"]:.0f}%{por}{barrios}, y no hay forma de rodearlo. '
                         'Mejor llega o sal en transporte puerta a puerta, o espera adentro y acompañado.'}
    if rapida['riesgo'] >= UMBRALES['alto']:
        return {'tipo': 'alerta', 'titulo': 'Hoy no hay una ruta realmente tranquila',
                'texto': f'El punto más complicado es {nombre} ({rapida["riesgo"]:.0f}%){por}{barrios}. '
                         'Si puedes, espera a una mejor hora, ve acompañado o pide un transporte puerta a puerta.'}
    if rapida['riesgo'] >= UMBRALES['medio']:
        return {'tipo': 'ok', 'titulo': 'Tu ruta de siempre es la mejor opción',
                'texto': f'No hay un desvío que baje el riesgo. Ve atento en {nombre}{barrios}, '
                         f'donde {verbo} {rapida["riesgo"]:.0f}%{por}.'}
    return {'tipo': 'ok', 'titulo': 'Tu ruta de siempre está bien',
            'texto': f'Es la más corta y también la más tranquila ahora mismo. '
                     f'El punto con más riesgo es {nombre} ({rapida["riesgo"]:.0f}%).'}


def consejos(est, ruta, modo, lluvia_mm, calientes=None, momento=None):
    lista = []
    f = est.loc[ruta['peor_zona']]
    lugar = f['zona']
    if calientes and momento is not None:
        top = calientes.get(f'{ruta["peor_zona"]}-{franja_de(momento.hour)}', [])[:1]
        if top:
            lugar = top[0] if top[0] == f['zona'] else f'{top[0]} ({f["zona"]})'
    if f['incidente'] == 'hurto':
        lista.append(f'Guarda el celular antes de llegar a {lugar} y no lo saques en los semáforos.'
                     if modo != 'carro' else f'En {lugar} sube los vidrios y deja el celular fuera de la vista.')
    elif f['incidente'] == 'violencia':
        lista.append(f'Cerca de {lugar} evita discusiones y zonas de bares a la salida; si ves una riña, aléjate.')
    else:
        lista.append(f'Baja la velocidad en {lugar}: es donde más accidentes con heridos se registran a esta hora.')
    if lluvia_mm >= 0.5:
        lista.append('Con lluvia, frena con más anticipación y evita las bajadas empinadas con el piso mojado.')
    if es_de_noche(int(f['franja'])):
        lista.append('Comparte tu trayecto con alguien de confianza y avisa cuando llegues.')
    else:
        lista.append('El riesgo cambia por franja horaria: si vas a salir más tarde, vuelve a mirar antes.')
    return lista[:3]


def proximas_franjas(momento, n):
    inicio = momento.replace(hour=franja_de(momento.hour) * 3, minute=0, second=0, microsecond=0)
    return [inicio + timedelta(hours=3 * i) for i in range(n)]
