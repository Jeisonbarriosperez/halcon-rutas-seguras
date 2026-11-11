"""
PASO 1: descargar los datos reales de Bucaramanga.

  - Delitos de la Policía Nacional (Alcaldía de Bucaramanga) ...... datos.gov.co  x46e-abhz
  - Delitos con coordenadas (para ubicar barrios y comunas) ...... datos.gov.co  75fz-q98y
  - Población por barrio ......................................... datos.gov.co  kn95-8dei
  - Población en régimen subsidiado por comuna ................... datos.gov.co  vgwf-uvjx
  - Clima hora por hora desde 2016 ............................... Open-Meteo (archivo histórico)

Todo queda en la carpeta datos/crudos/ tal como lo entrega cada fuente.
"""
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

sys.stdout.reconfigure(encoding='utf-8')

CRUDOS = Path('datos/crudos')
CRUDOS.mkdir(parents=True, exist_ok=True)
SOCRATA = 'https://www.datos.gov.co/resource/{}.json'
BUCARAMANGA = (7.1193, -73.1227)

# Delitos que pasan en la calle y que una ruta puede esquivar
DELITOS_CALLE = [
    'HURTO PERSONAS', 'HURTO MOTOCICLETAS', 'HURTO AUTOMOTORES',
    'LESIONES PERSONALES', 'HOMICIDIO',
    'LESIONES CULPOSAS ( EN ACCIDENTE DE TRANSITO )', 'HOMICIDIO CULPOSO ( EN ACCIDENTE DE TRÁNSITO)',
]

print('=' * 64)
print(' PASO 1: DESCARGA DE DATOS REALES DE BUCARAMANGA')
print('=' * 64)


def descargar(recurso, select=None, where=None, group=None, lote=50000):
    """Descarga un dataset de datos.gov.co por partes (la API entrega máximo 50.000 filas por consulta)."""
    filas, offset = [], 0
    while True:
        params = {'$limit': lote, '$offset': offset}
        if select:
            params['$select'] = select
        if where:
            params['$where'] = where
        if group:
            params['$group'] = group
        else:
            params['$order'] = ':id'
        for intento in range(4):
            try:
                r = requests.get(SOCRATA.format(recurso), params=params, timeout=180)
                r.raise_for_status()
                parte = r.json()
                break
            except Exception as error:
                if intento == 3:
                    raise
                print(f'   reintentando ({error.__class__.__name__})...')
                time.sleep(5 * (intento + 1))
        filas += parte
        print(f'   {recurso}: {len(filas):,} filas'.replace(',', '.'))
        if len(parte) < lote:
            return pd.DataFrame(filas)
        offset += lote


# ---------------- 1. DELITOS EN LA CALLE ----------------
print('\n1. Delitos (Policía Nacional - Alcaldía de Bucaramanga)')
lista = ', '.join("'" + d + "'" for d in DELITOS_CALLE)
delitos = descargar('x46e-abhz',
                    select='fecha_hecho, hora_hecho, delito_solo, barrios_hecho, num_com, nom_com, clase_sitio, '
                           'movil_victima, movil_agresor, armas_medios',
                    where=f'delito_solo in ({lista})')
delitos.to_csv(CRUDOS / 'delitos.csv', index=False)

# ---------------- 2. COORDENADAS ----------------
print('\n2. Coordenadas de los hechos (para ubicar barrios y comunas)')
coords = descargar('75fz-q98y', select='barrios_hecho, nom_comuna, latitud, longitud',
                   where='latitud is not null')
coords.to_csv(CRUDOS / 'coordenadas.csv', index=False)

# ---------------- 3. POBLACIÓN ----------------
print('\n3. Población por barrio')
descargar('kn95-8dei').to_csv(CRUDOS / 'poblacion_barrios.csv', index=False)

print('\n4. Población en régimen subsidiado por comuna')
descargar('vgwf-uvjx', select='comuna, count(*) as personas', group='comuna').to_csv(
    CRUDOS / 'subsidiado_comunas.csv', index=False)

# ---------------- 4. CLIMA HORA POR HORA ----------------
print('\n5. Clima hora por hora (Open-Meteo, archivo histórico)')
fin = date.today() - timedelta(days=6)          # el archivo histórico tarda unos días en actualizarse
r = requests.get('https://archive-api.open-meteo.com/v1/archive', timeout=300, params={
    'latitude': BUCARAMANGA[0], 'longitude': BUCARAMANGA[1],
    'start_date': '2016-01-01', 'end_date': fin.isoformat(),
    'hourly': 'temperature_2m,precipitation,weather_code', 'timezone': 'America/Bogota',
})
r.raise_for_status()
h = r.json()['hourly']
clima = pd.DataFrame({'fecha_hora': h['time'], 'temperatura': h['temperature_2m'],
                      'lluvia_mm': h['precipitation'], 'codigo_clima': h['weather_code']})
clima.to_csv(CRUDOS / 'clima_horario.csv', index=False)
print(f'   {len(clima):,} horas, del {clima.fecha_hora.iloc[0][:10]} al {clima.fecha_hora.iloc[-1][:10]}'
      .replace(',', '.'))

print('\nListo. Siguiente paso:  python 2_limpiar_y_cargar.py')
