"""
PASO 2: limpiar los datos reales y subirlos a Azure SQL.

Tablas que llena:
  comunas        17 comunas urbanas con su ubicación, población y % en régimen subsidiado
  barrios        barrios con coordenadas reales y cuántos incidentes tuvieron
  incidentes     cada hecho ocurrido en la calle (hurto, riña o lesión, accidente con heridos)
  clima_horario  temperatura y lluvia de cada hora desde 2016
Si alguna tabla no existe, la crea.
"""
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

CRUDOS = Path('datos/crudos')
LIMPIOS = Path('datos')

NOMBRES_COMUNA = {
    1: 'Norte', 2: 'Nororiental', 3: 'San Francisco', 4: 'Occidental', 5: 'García Rovira',
    6: 'La Concordia', 7: 'La Ciudadela', 8: 'Suroccidente', 9: 'La Pedregosa', 10: 'Provenza',
    11: 'Sur', 12: 'Cabecera del Llano', 13: 'Oriental', 14: 'Morrorico', 15: 'Centro',
    16: 'Lagos del Cacique', 17: 'Mutis',
}
TIPO_DELITO = {
    'HURTO PERSONAS': 'hurto', 'HURTO MOTOCICLETAS': 'hurto', 'HURTO AUTOMOTORES': 'hurto',
    'LESIONES PERSONALES': 'violencia', 'HOMICIDIO': 'violencia',
    'LESIONES CULPOSAS ( EN ACCIDENTE DE TRANSITO )': 'accidente',
    'HOMICIDIO CULPOSO ( EN ACCIDENTE DE TRÁNSITO)': 'accidente',
}
# Sitios cerrados: lo que pasa adentro no depende de por dónde camines
BAJO_TECHO = r'^CASAS DE HABITACION$|APARTAMENTO|CARCEL|INTERIOR DE VIVIENDA|CONJUNTO RESIDENCIAL|INQUILINATO|' \
             r'HOTEL|MOTEL|^RESIDENCIAS$|^EDIFICIO$|FINCA'

print('=' * 64)
print(' PASO 2: LIMPIEZA Y CARGA A AZURE SQL')
print('=' * 64)


def numero_comuna(texto):
    m = re.match(r'\s*(\d+)', str(texto))
    return int(m.group(1)) if m else None


def bonito(texto):
    texto = re.sub(r'\s+', ' ', str(texto)).strip()
    return texto.title().replace(' De ', ' de ').replace(' Del ', ' del ').replace(' La ', ' la ') \
        .replace(' Las ', ' las ').replace(' Los ', ' los ').replace(' Y ', ' y ')


def clave(texto):
    t = unicodedata.normalize('NFKD', str(texto)).encode('ascii', 'ignore').decode().upper()
    return re.sub(r'[^A-Z0-9]', '', t)


# ---------------- 1. COORDENADAS: DÓNDE QUEDA CADA BARRIO ----------------
c = pd.read_csv(CRUDOS / 'coordenadas.csv', dtype=str)


def a_grados(texto, es_longitud):
    """Las coordenadas vienen en varios formatos (7.12 / 7,123,456 / -731,234,567...)."""
    texto = str(texto).strip()
    if ',' not in texto:
        try:
            return float(texto)
        except ValueError:
            return np.nan
    negativo = texto.startswith('-')
    digitos = re.sub(r'\D', '', texto)
    if not digitos:
        return np.nan
    enteros = 2 if es_longitud else 1
    valor = float(digitos[:enteros] + '.' + digitos[enteros:])
    return -valor if negativo else valor


c['lat'] = c['latitud'].map(lambda t: a_grados(t, False))
c['lon'] = c['longitud'].map(lambda t: a_grados(t, True))
c = c[c['lat'].between(7.03, 7.20) & c['lon'].between(-73.20, -73.05)]
c['comuna_id'] = c['nom_comuna'].map(numero_comuna)
c = c[c['comuna_id'].between(1, 17)]
c['clave'] = c['barrios_hecho'].map(clave)
print('Coordenadas válidas dentro de Bucaramanga:', len(c))

barrios_xy = c.groupby('clave').agg(lat=('lat', 'median'), lon=('lon', 'median'), puntos=('lat', 'size'),
                                    comuna_coord=('comuna_id', lambda s: s.mode().iloc[0])).reset_index()

# A qué comuna pertenece cada barrio. OJO: en el dataset de delitos (x46e) la columna de comuna está
# revuelta (el barrio Centro aparece repartido por igual en 4 comunas), así que NO se usa. La comuna se
# saca del barrio: primero con el listado oficial de barrios de la Alcaldía, y si no está, con el
# dataset de coordenadas, donde barrio y comuna coinciden en el 99,9 % de los casos.
pob = pd.read_csv(CRUDOS / 'poblacion_barrios.csv', dtype=str)
pob['comuna_id'] = pob['comunas_poligonos'].map(numero_comuna)
oficial = pob[pob['comuna_id'].between(1, 17)].assign(clave=pob['barrio_poligono'].map(clave))     .groupby('clave')['comuna_id'].first()
por_coordenadas = barrios_xy[barrios_xy['puntos'] >= 3].set_index('clave')['comuna_coord']
comuna_de_barrio = por_coordenadas.combine_first(oficial)
comuna_de_barrio.update(oficial)

# ---------------- 2. INCIDENTES ----------------
d = pd.read_csv(CRUDOS / 'delitos.csv', dtype=str)
print('Delitos descargados:', len(d))
d = d[~d['clase_sitio'].fillna('').str.contains(BAJO_TECHO, regex=True)]
print('  quitando los que pasaron bajo techo:', len(d))
d['barrio'] = d['barrios_hecho'].fillna('NO REPORTADO').map(bonito)
d['comuna_id'] = d['barrios_hecho'].map(clave).map(comuna_de_barrio)
sin_comuna = d['comuna_id'].isna().mean()
d = d.dropna(subset=['comuna_id'])
print(f'  con barrio ubicado en una de las 17 comunas urbanas: {len(d)} '
      f'(se descarta el {sin_comuna:.0%}: barrio no reportado, rural o desconocido)')
d['fecha'] = pd.to_datetime(d['fecha_hecho'], errors='coerce')
d = d.dropna(subset=['fecha'])
d['hora_texto'] = d['hora_hecho'].fillna('')
d['hora'] = pd.to_numeric(d['hora_texto'].str[:2], errors='coerce')
d['hora_conocida'] = ((d['hora_texto'] != '00:00:00') & d['hora'].notna()).astype(int)   # 00:00 = sin hora
d['tipo'] = d['delito_solo'].map(TIPO_DELITO)
antes = len(d)
d = d.drop_duplicates(['fecha', 'hora_texto', 'delito_solo', 'barrio'])
print('  hechos con varias víctimas contados una sola vez:', antes - len(d), 'filas unidas')

incidentes = pd.DataFrame({
    'fecha_hora': d['fecha'] + pd.to_timedelta(d['hora'].fillna(0), unit='h') +
                  pd.to_timedelta(pd.to_numeric(d['hora_texto'].str[3:5], errors='coerce').fillna(0), unit='m'),
    'hora_conocida': d['hora_conocida'],
    'tipo': d['tipo'],
    'delito': d['delito_solo'].str.title().str.replace(r'\s*\(\s*', ' (', regex=True).str.replace(r'\s*\)', ')', regex=True),
    'comuna_id': d['comuna_id'].astype(int),
    'barrio': d['barrio'],
    'sitio': d['clase_sitio'].fillna('NO REPORTADO').map(bonito),
    'movil_victima': d['movil_victima'].fillna('NO REPORTADO').map(bonito),
}).sort_values('fecha_hora').reset_index(drop=True)
print('Incidentes limpios:', len(incidentes), '| con hora conocida:', int(incidentes['hora_conocida'].sum()))
print('  por tipo:', incidentes['tipo'].value_counts().to_dict())
print('  por comuna:', incidentes['comuna_id'].value_counts().sort_index().to_dict())

conteo = incidentes.groupby('barrio').agg(incidentes=('tipo', 'size'),
                                          comuna_id=('comuna_id', 'first')).reset_index()
conteo['clave'] = conteo['barrio'].map(clave)
barrios = conteo.merge(barrios_xy[barrios_xy['puntos'] >= 5], on='clave', how='inner')
barrios = barrios[['barrio', 'comuna_id', 'lat', 'lon', 'incidentes']].sort_values('incidentes', ascending=False)
print('Barrios ubicados en el mapa:', len(barrios), f'(concentran el {barrios.incidentes.sum() / len(incidentes):.0%} '
      'de los incidentes)')

# Población (proyección 2024) y régimen subsidiado por comuna
p = pd.read_csv(CRUDOS / 'poblacion_barrios.csv', dtype=str)
p = p[p['a_o'] == p['a_o'].max()]
p['personas'] = pd.to_numeric(p['personas'].str.replace(',', ''), errors='coerce')
p['comuna_id'] = p['comunas_poligonos'].map(numero_comuna)
poblacion = p[p['comuna_id'].between(1, 17)].groupby('comuna_id')['personas'].sum()
s = pd.read_csv(CRUDOS / 'subsidiado_comunas.csv')
s['comuna_id'] = s['comuna'].map(numero_comuna)
subsidiado = s[s['comuna_id'].between(1, 17)].groupby('comuna_id')['personas'].sum()

xy = c.groupby('comuna_id').agg(lat=('lat', 'median'), lon=('lon', 'median'))
comunas = pd.DataFrame({'comuna_id': range(1, 18)})
comunas['nombre'] = comunas['comuna_id'].map(NOMBRES_COMUNA)
comunas['lat'] = comunas['comuna_id'].map(xy['lat']).round(6)
comunas['lon'] = comunas['comuna_id'].map(xy['lon']).round(6)
comunas['poblacion'] = comunas['comuna_id'].map(poblacion).astype(int)
# En el Centro hay más afiliados registrados que habitantes (muchos dan esa dirección y viven en otra parte): tope 100
comunas['pct_subsidiado'] = (comunas['comuna_id'].map(subsidiado) / comunas['poblacion'] * 100).clip(upper=100).round(1)
print(comunas.to_string(index=False))

# ---------------- 3. CLIMA ----------------
clima = pd.read_csv(CRUDOS / 'clima_horario.csv', parse_dates=['fecha_hora'])
clima = clima.dropna().drop_duplicates('fecha_hora')
print('Horas de clima:', len(clima), f'| llovió en el {(clima.lluvia_mm >= 0.2).mean():.0%} de las horas')

# ---------------- 4. GUARDAR ----------------
incidentes.to_csv(LIMPIOS / 'incidentes.csv', index=False)
barrios.to_csv(LIMPIOS / 'barrios.csv', index=False)
comunas.to_csv(LIMPIOS / 'comunas.csv', index=False)
clima.to_csv(LIMPIOS / 'clima_horario.csv', index=False)
print('Se guardaron los CSV limpios en datos/')

# ---------------- 5. SUBIR A AZURE ----------------
TABLAS = {
    'comunas': ('comuna_id INT PRIMARY KEY, nombre NVARCHAR(40), lat FLOAT, lon FLOAT, poblacion INT, '
                'pct_subsidiado DECIMAL(5,1)', comunas),
    'barrios': ('id INT IDENTITY(1,1) PRIMARY KEY, barrio NVARCHAR(80), comuna_id INT, lat FLOAT, lon FLOAT, '
                'incidentes INT', barrios),
    'incidentes': ('id INT IDENTITY(1,1) PRIMARY KEY, fecha_hora DATETIME2, hora_conocida INT, tipo NVARCHAR(20), '
                   'delito NVARCHAR(80), comuna_id INT, barrio NVARCHAR(80), sitio NVARCHAR(80), '
                   'movil_victima NVARCHAR(60)', incidentes),
    'clima_horario': ('fecha_hora DATETIME2 PRIMARY KEY, temperatura DECIMAL(4,1), lluvia_mm DECIMAL(5,1), '
                      'codigo_clima INT', clima),
}

if '--sin-azure' in sys.argv:
    sys.exit(0)
try:
    from config import conectar
    conn = conectar()
except Exception as error:
    print('\nNo hay conexión con Azure (' + str(error)[:80] + '). Los datos quedaron en CSV; '
          'puedes entrenar igual con:  python 3_entrenar_modelo.py')
    sys.exit(0)

cursor = conn.cursor()


def valor(v):
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    return v


for tabla, (definicion, df) in TABLAS.items():
    cursor.execute(f"IF OBJECT_ID('{tabla}', 'U') IS NULL CREATE TABLE {tabla} ({definicion})")
    cursor.execute(f'DELETE FROM {tabla}')
    conn.commit()
    columnas = list(df.columns)
    lote = max(1, 2000 // len(columnas))
    marca = '(' + ', '.join(['%s'] * len(columnas)) + ')'
    sql = f'INSERT INTO {tabla} ({", ".join(columnas)}) VALUES '
    for inicio in range(0, len(df), lote):
        parte = df.iloc[inicio:inicio + lote]
        valores = [valor(v) for fila in parte.itertuples(index=False) for v in fila]
        cursor.execute(sql + ', '.join([marca] * len(parte)), tuple(valores))
        conn.commit()
        hechas = inicio + len(parte)
        if hechas == len(df) or (hechas // lote) % 100 == 0:
            print(f'   {tabla}: {hechas:,} de {len(df):,}'.replace(',', '.'))
    cursor.execute(f'SELECT COUNT(*) FROM {tabla}')
    print(f'{tabla}: {cursor.fetchone()[0]:,} filas en Azure'.replace(',', '.'))

conn.close()
print('\nListo. Siguiente paso:  python 3_entrenar_modelo.py')
