"""
PASO 3: entrenar Halcón con los datos reales de Bucaramanga.

Cada fila de entrenamiento es una comuna en una franja de 3 horas de un día concreto (2016 → 2026).
  Objetivo: nivel de riesgo
     Bajo  = no se reportó ningún incidente en la calle
     Medio = se reportó 1
     Alto  = se reportaron 2 o más
Validación honesta: se entrena con 2016-2024 y se prueba con 2025-2026, años que el modelo nunca vio.
Lee desde Azure SQL; si no hay conexión, usa los CSV de datos/.
"""
import json
import os
import sys
import time
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from scipy.spatial import Delaunay
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, recall_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

sys.stdout.reconfigure(encoding='utf-8')

print('=' * 64)
print(' PASO 3: ENTRENAMIENTO CON DATOS REALES DE BUCARAMANGA')
print('=' * 64)


# ---------------- 1. TRAER LOS DATOS ----------------
def leer(tabla, columnas):
    from config import conectar
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute(f'SELECT {", ".join(columnas)} FROM {tabla}')
    df = pd.DataFrame(cursor.fetchall(), columns=columnas)
    conn.close()
    if df.empty:
        raise ValueError(f'la tabla {tabla} está vacía')
    return df


COLS = {
    'incidentes': ['fecha_hora', 'hora_conocida', 'tipo', 'comuna_id', 'barrio', 'sitio', 'movil_victima'],
    'clima_horario': ['fecha_hora', 'temperatura', 'lluvia_mm'],
    'comunas': ['comuna_id', 'nombre', 'lat', 'lon', 'poblacion', 'pct_subsidiado'],
    'barrios': ['barrio', 'comuna_id', 'lat', 'lon', 'incidentes'],
}
try:
    if '--csv' in sys.argv:
        raise RuntimeError('se pidió usar los CSV locales')
    tablas = {t: leer(t, c) for t, c in COLS.items()}
    origen = 'Azure SQL'
except Exception as error:
    print('No se pudo leer Azure (' + str(error)[:90] + ') -> se usan los CSV de datos/')
    tablas = {t: pd.read_csv(f'datos/{t}.csv')[c] for t, c in COLS.items()}
    origen = 'CSV local'
inc, clima, comunas, barrios = tablas['incidentes'], tablas['clima_horario'], tablas['comunas'], tablas['barrios']
inc['fecha_hora'] = pd.to_datetime(inc['fecha_hora'])
clima['fecha_hora'] = pd.to_datetime(clima['fecha_hora'])
for df, cols in ((clima, ['temperatura', 'lluvia_mm']), (comunas, ['lat', 'lon', 'pct_subsidiado']),
                 (barrios, ['lat', 'lon'])):
    for c in cols:
        df[c] = df[c].astype(float)
print(f'Datos leídos desde {origen}: {len(inc):,} incidentes, {len(clima):,} horas de clima'.replace(',', '.'))

# El mapa de la ciudad sale de los datos: ahora se puede usar la lógica compartida
comunas = comunas.sort_values('comuna_id').reset_index(drop=True)
xy = np.c_[(comunas['lon'] - comunas['lon'].mean()) * 110.4, (comunas['lat'] - comunas['lat'].mean()) * 110.6]
aristas = set()
for tri in Delaunay(xy).simplices:
    for i in range(3):
        a, b = sorted((tri[i], tri[(i + 1) % 3]))
        if np.hypot(*(xy[a] - xy[b])) <= 3.2:              # comunas vecinas (máximo 3,2 km entre centros)
            aristas.add((int(comunas.comuna_id[a]), int(comunas.comuna_id[b])))
ciudad = {
    'comunas': comunas.to_dict('records'),
    'barrios': barrios.sort_values('incidentes', ascending=False).to_dict('records'),
    'aristas': sorted(aristas),
}
os.makedirs('modelo', exist_ok=True)
with open('modelo/ciudad.json', 'w', encoding='utf-8') as f:
    json.dump(ciudad, f, ensure_ascii=False, default=lambda o: o.item() if hasattr(o, 'item') else str(o))
print('Conexiones entre comunas vecinas:', len(aristas))

import importlib                       # noqa: E402
import ciudad as modulo_ciudad         # noqa: E402
importlib.reload(modulo_ciudad)
import halcon                          # noqa: E402
importlib.reload(halcon)
from ciudad import en_confinamiento, es_festivo, es_puente, es_quincena  # noqa: E402
from halcon import COLUMNAS, NIVELES, NOMBRES_VARIABLES, TIPOS_INCIDENTE, agregar_variables  # noqa: E402

# ---------------- 2. ARMAR LA TABLA COMUNA x DÍA x FRANJA ----------------
con_hora = inc[inc['hora_conocida'] == 1].copy()
con_hora['fecha'] = con_hora['fecha_hora'].dt.normalize()
con_hora['franja'] = con_hora['fecha_hora'].dt.hour // 3
inicio, fin = con_hora['fecha'].min(), con_hora['fecha'].max()
dias = pd.date_range(inicio, fin, freq='D')
print(f'Periodo: {inicio:%d/%m/%Y} a {fin:%d/%m/%Y} ({len(dias):,} días)'.replace(',', '.'))

panel = pd.MultiIndex.from_product([dias, range(8), comunas['comuna_id']], names=['fecha', 'franja', 'comuna_id'])
panel = pd.DataFrame(index=panel).reset_index()
conteo = con_hora.groupby(['fecha', 'franja', 'comuna_id']).size().rename('incidentes')
panel = panel.merge(conteo, on=['fecha', 'franja', 'comuna_id'], how='left').fillna({'incidentes': 0})
panel['incidentes'] = panel['incidentes'].astype(int)

clima['fecha'] = clima['fecha_hora'].dt.normalize()
clima['franja'] = clima['fecha_hora'].dt.hour // 3
cf = clima.groupby(['fecha', 'franja']).agg(lluvia_mm=('lluvia_mm', 'sum'), temperatura=('temperatura', 'mean'))
cf['lluvia_previa_mm'] = cf['lluvia_mm'].shift(1).fillna(0)
cf = cf.round(1).reset_index()
panel = panel.merge(cf, on=['fecha', 'franja'], how='left')
panel[['lluvia_mm', 'lluvia_previa_mm']] = panel[['lluvia_mm', 'lluvia_previa_mm']].fillna(0)
panel['temperatura'] = panel['temperatura'].fillna(panel['temperatura'].mean())

calendario = pd.DataFrame({'fecha': dias})
fechas = calendario['fecha'].dt.date
calendario['dia_semana'] = calendario['fecha'].dt.day_of_week
calendario['mes'] = calendario['fecha'].dt.month
calendario['anio'] = calendario['fecha'].dt.year
calendario['es_festivo'] = fechas.map(es_festivo)
calendario['es_puente'] = fechas.map(es_puente)
calendario['es_quincena'] = fechas.map(es_quincena)
calendario['confinamiento'] = fechas.map(en_confinamiento)
panel = panel.merge(calendario, on='fecha').merge(comunas[['comuna_id', 'pct_subsidiado']], on='comuna_id')
panel['nivel'] = np.select([panel['incidentes'] >= 2, panel['incidentes'] == 1], ['Alto', 'Medio'], 'Bajo')
print(f'Filas comuna-día-franja: {len(panel):,}'.replace(',', '.'))
print('Nivel real:', panel['nivel'].value_counts().to_dict())

prueba = panel['fecha'] >= '2025-01-01'
X_train, y_train = panel.loc[~prueba, COLUMNAS], panel.loc[~prueba, 'nivel']
X_test, y_test = panel.loc[prueba, COLUMNAS], panel.loc[prueba, 'nivel']
print(f'Entrenamiento (2016-2024): {len(X_train):,} | Prueba (2025-2026): {len(X_test):,}'.replace(',', '.'))

NUMERICAS = ['hora_sin', 'hora_cos', 'pct_subsidiado', 'anio', 'mes', 'es_festivo', 'es_puente', 'es_quincena',
             'confinamiento', 'lluvia_mm', 'lluvia_previa_mm', 'temperatura', 'noche_de_fiesta', 'llueve']
CATEGORICAS = ['comuna', 'franja_txt', 'dia_txt']


def armar(modelo):
    prep = ColumnTransformer([('numeros', StandardScaler(), NUMERICAS),
                              ('categorias', OneHotEncoder(handle_unknown='ignore', sparse_output=False), CATEGORICAS)])
    return make_pipeline(FunctionTransformer(agregar_variables), prep, modelo)


# ---------------- 3. TRES ALGORITMOS ----------------
modelos = {
    'Regresión Logística': armar(LogisticRegression(max_iter=3000)),
    'Random Forest': armar(RandomForestClassifier(n_estimators=150, max_depth=16, min_samples_leaf=40,
                                                  n_jobs=-1, random_state=42)),
    'Gradient Boosting': armar(HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05,
                                                              min_samples_leaf=80, random_state=42)),
}
resultados = {}
for nombre, modelo in modelos.items():
    t = time.time()
    modelo.fit(X_train, y_train)
    prob = modelo.predict_proba(X_test)
    clases = list(modelo.classes_)
    p_alguno = 1 - prob[:, clases.index('Bajo')]
    pred = np.array(clases)[prob.argmax(axis=1)]
    real_alguno = (y_test != 'Bajo').astype(int)
    resultados[nombre] = {
        'AUC': roc_auc_score(y_test, prob, multi_class='ovr', labels=clases) * 100,
        'AUC_alguno': roc_auc_score(real_alguno, p_alguno) * 100,
        'Exactitud': accuracy_score(y_test, pred) * 100,
        'F1': f1_score(y_test, pred, average='macro') * 100,
        'segundos': round(time.time() - t, 1),
    }
    r = resultados[nombre]
    print(f'{nombre:<22} AUC {r["AUC"]:.1f}%  (detectar si pasa algo: {r["AUC_alguno"]:.1f}%)  ({r["segundos"]} s)')

mejor = max(resultados, key=lambda n: resultados[n]['AUC'])
print('\nGANADOR:', mejor)
modelo_nivel = modelos[mejor]
prob = modelo_nivel.predict_proba(X_test)
clases = list(modelo_nivel.classes_)
riesgo = (1 - prob[:, clases.index('Bajo')]) * 100

# Umbrales: Alto = el 12 % de franjas más riesgosas de la ciudad; Medio = el siguiente 28 %
umbral_medio, umbral_alto = np.percentile(riesgo, [60, 88]).round(0)
nivel_pred = np.select([riesgo >= umbral_alto, riesgo >= umbral_medio], ['Alto', 'Medio'], 'Bajo')
print(f'Umbrales: medio desde {umbral_medio:.0f}%, alto desde {umbral_alto:.0f}%')
r = resultados[mejor]
r['matriz'] = confusion_matrix(y_test, nivel_pred, labels=NIVELES).tolist()
r['detecta_alto'] = recall_score(y_test, nivel_pred, labels=['Alto'], average='macro') * 100
r['siempre_bajo'] = (y_test == 'Bajo').mean() * 100

# ¿Cuando Halcón dice X %, pasa de verdad X %? (calibración por grupos)
grupos = pd.qcut(riesgo, 10, duplicates='drop')
calib = pd.DataFrame({'dijo': riesgo, 'paso': (y_test != 'Bajo').values * 100, 'g': grupos}) \
    .groupby('g', observed=True).mean().round(1)
r['calibracion'] = {'dijo': calib['dijo'].tolist(), 'paso': calib['paso'].tolist()}
print('Calibración (dijo -> pasó):', list(zip(calib['dijo'], calib['paso'])))

# Concentración: ¿qué % de los incidentes reales cayó en las franjas que Halcón marcó como Alto?
inc_test = panel.loc[prueba, 'incidentes'].values
r['incidentes_en_alto'] = inc_test[nivel_pred == 'Alto'].sum() / inc_test.sum() * 100
print(f'En 2025-2026, las franjas marcadas como Alto ({(nivel_pred == "Alto").mean():.0%} del tiempo) '
      f'concentraron el {r["incidentes_en_alto"]:.0f}% de los incidentes reales.')
r['tiempo_alto'] = (nivel_pred == 'Alto').mean() * 100
r['tiempo_medio_alto'] = (nivel_pred != 'Bajo').mean() * 100
r['incidentes_en_medio_alto'] = inc_test[nivel_pred != 'Bajo'].sum() / inc_test.sum() * 100

# ¿La comuna que Halcón ponía de primera era de verdad la más complicada?
val = panel.loc[prueba, ['fecha', 'franja', 'comuna_id', 'incidentes']].copy()
val['riesgo'] = riesgo.round(1)
primera = val.loc[val.groupby(['fecha', 'franja'])['riesgo'].idxmax()]
r['primera_con_incidente'] = (primera['incidentes'] > 0).mean() * 100
r['cualquiera_con_incidente'] = (val['incidentes'] > 0).mean() * 100
print(f'La comuna que Halcón ponía de primera tuvo incidentes el {r["primera_con_incidente"]:.0f}% de las veces '
      f'(una comuna cualquiera: {r["cualquiera_con_incidente"]:.0f}%).')

# Para la sección "¿Funciona?" de la app: lo que dijo (sin haber visto esos años) y lo que pasó
os.makedirs('modelo', exist_ok=True)
val.assign(fecha=val['fecha'].dt.strftime('%Y-%m-%d')).to_csv('modelo/validacion.csv.gz', index=False)
con_hora.loc[con_hora['fecha'] >= '2025-01-01', ['fecha', 'franja', 'comuna_id', 'barrio', 'tipo']] \
    .assign(fecha=lambda x: x['fecha'].dt.strftime('%Y-%m-%d')).to_csv('modelo/validacion_incidentes.csv.gz', index=False)

# ---------------- 4. QUÉ PESA MÁS ----------------
print('Midiendo cuánto pesa cada variable...')
muestra = X_test.sample(30000, random_state=42)
imp = permutation_importance(modelo_nivel, muestra, y_test.loc[muestra.index], scoring='roc_auc_ovr',
                             n_repeats=3, random_state=42, n_jobs=-1)
importancia = pd.Series(imp.importances_mean, index=COLUMNAS).clip(lower=0)
importancia = (importancia / importancia.sum() * 100).sort_values(ascending=False)
for col, v in importancia.head(6).items():
    print(f'   {NOMBRES_VARIABLES[col]:<45} {v:5.1f}%')

# ---------------- 5. MODELO DEFINITIVO CON TODOS LOS AÑOS ----------------
print('Reentrenando el ganador con todos los años (2016-2026)...')
modelo_nivel = armar(modelos[mejor].steps[-1][1])
modelo_nivel.fit(panel[COLUMNAS], panel['nivel'])

# ---------------- 6. ¿QUÉ TIPO DE INCIDENTE ES MÁS PROBABLE? ----------------
# Proporción real de cada tipo en cada comuna y franja (con un poco de suavizado hacia el promedio de la comuna)
print('Calculando qué tipo de incidente es más común en cada comuna y hora...')
filas_tipo = con_hora.merge(panel.drop(columns=['incidentes', 'nivel']), on=['fecha', 'franja', 'comuna_id'])
por_comuna = con_hora.groupby(['comuna_id', 'tipo']).size().unstack(fill_value=0)
por_comuna = por_comuna.div(por_comuna.sum(axis=1), axis=0)
por_franja = con_hora.groupby(['comuna_id', 'franja', 'tipo']).size().unstack(fill_value=0) \
    .reindex(columns=TIPOS_INCIDENTE, fill_value=0)
proporcion_tipo = {}
for (c, f), fila_t in por_franja.iterrows():
    suavizado = (fila_t + 20 * por_comuna.loc[c].reindex(TIPOS_INCIDENTE).fillna(0)) / (fila_t.sum() + 20)
    proporcion_tipo[f'{c}-{f}'] = suavizado.round(4).to_dict()
tipo_metricas = {'casos': con_hora['tipo'].value_counts().to_dict()}

# ---------------- 7. LO QUE MUESTRAN LOS DATOS (para la app) ----------------
inc['anio'] = inc['fecha_hora'].dt.year
reales = {
    'hora_dia': con_hora.assign(h=con_hora['fecha_hora'].dt.hour, d=con_hora['fecha_hora'].dt.day_of_week)
    .groupby(['d', 'h']).size().unstack(fill_value=0).reindex(index=range(7), columns=range(24), fill_value=0)
    .values.tolist(),
    'por_anio': inc.groupby(['anio', 'tipo']).size().unstack(fill_value=0).to_dict('index'),
    'tipo_hora': con_hora.assign(h=con_hora['fecha_hora'].dt.hour).groupby(['tipo', 'h']).size()
    .unstack(fill_value=0).reindex(columns=range(24), fill_value=0).to_dict('index'),
    'por_comuna': inc.groupby('comuna_id').size().to_dict(),
    'sitios': inc['sitio'].value_counts().head(8).to_dict(),
    'movil': inc[inc['tipo'] == 'hurto']['movil_victima'].value_counts().head(6).to_dict(),
}
lluvia = panel.assign(llueve=panel['lluvia_mm'] >= 0.5)
reales['lluvia'] = (lluvia.groupby(['franja', 'llueve'])['incidentes'].mean().unstack() * 100).round(2).to_dict()
llu_tipo = filas_tipo.assign(llueve=filas_tipo['lluvia_mm'] >= 0.5).groupby(['tipo', 'llueve']).size().unstack()
horas_lluvia = (lluvia.groupby('llueve').size() / 17)
reales['lluvia_tipo'] = (llu_tipo / horas_lluvia * 1000).round(2).to_dict('index')   # por cada 1000 franjas-ciudad
calientes = con_hora[~con_hora['barrio'].isin(['Bucaramanga', 'No Reportado', 'No Disponible'])] \
    .groupby(['comuna_id', 'franja', 'barrio']).size().rename('n').reset_index() \
    .sort_values('n', ascending=False).groupby(['comuna_id', 'franja']).head(3)
reales['calientes'] = {f'{c}-{f}': g['barrio'].tolist() for (c, f), g in calientes.groupby(['comuna_id', 'franja'])}

# ---------------- 8. GUARDAR ----------------
joblib.dump({'nivel': modelo_nivel, 'tipo': proporcion_tipo, 'nombre': mejor,
             'umbrales': (float(umbral_medio), float(umbral_alto))}, 'modelo/modelo_halcon.joblib', compress=3)
info = {
    'mejor': mejor, 'fecha': datetime.now().strftime('%d/%m/%Y %H:%M'), 'origen': origen,
    'incidentes': len(inc), 'incidentes_con_hora': len(con_hora), 'filas': len(panel),
    'entrenamiento': len(X_train), 'prueba': len(X_test),
    'periodo': [f'{inicio:%d/%m/%Y}', f'{fin:%d/%m/%Y}'],
    'distribucion': panel['nivel'].value_counts().to_dict(),
    'umbrales': [float(umbral_medio), float(umbral_alto)],
    'resultados': resultados, 'importancia': importancia.round(2).to_dict(), 'tipo': tipo_metricas,
    'reales': reales,
}
with open('modelo/metricas.json', 'w', encoding='utf-8') as f:
    json.dump(info, f, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, 'item') else str(o))
print('\nSe guardó modelo/modelo_halcon.joblib, modelo/metricas.json y modelo/ciudad.json')
print('Ahora abre la app:  python -m streamlit run app.py')
