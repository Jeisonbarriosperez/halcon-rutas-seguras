"""
HALCÓN · la ruta más tranquila, no solo la más rápida.
Bucaramanga, con datos reales de la Policía Nacional, la Alcaldía y Open-Meteo.
Ejecutar:  python -m streamlit run app.py
"""
import json
import random
import urllib.parse
from datetime import date, datetime, timedelta, time as hora_dia
from pathlib import Path
from zoneinfo import ZoneInfo

import joblib
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import almacen
from ciudad import ARISTAS, BARRIOS, CENTRO, CIUDAD, COMUNAS
from halcon import (DIAS, ESCENARIOS_LLUVIA, INCIDENTE_TEXTO, MODOS, NIVELES, NOMBRES_VARIABLES, TIPOS_INCIDENTE,
                    UMBRALES, calcular_rutas, clima_de_franja, clima_texto, configurar_umbrales, consejos,
                    es_de_noche, estado_ciudad, fecha_texto, fila, franja_de, franja_texto, geometria_osrm,
                    hora_corta, hora_texto, icono_clima, mensaje_principal, nivel_de, predecir, pronostico_real,
                    proximas_franjas, razones, unir)
from tarjeta import tarjeta_trayecto

CARPETA = Path(__file__).parent
ZONA_HORARIA = ZoneInfo('America/Bogota')

st.set_page_config(page_title='Halcón · rutas tranquilas en Bucaramanga',
                   page_icon=str(CARPETA / 'recursos' / 'halcon.png'), layout='wide')
st.logo(str(CARPETA / 'recursos' / 'marca.png'), size='large')

TINTA, PAPEL, CARTA, LINEA, TENUE = '#1C1B19', '#F5F1E8', '#FFFDF8', '#E3DCCB', '#6B655A'
MARCA, OCRE = '#1F4E5F', '#C47F2C'
COLOR_NIVEL = {'Bajo': '#4C8B5A', 'Medio': '#CC9128', 'Alto': '#B83A2E'}
FONDO_NIVEL = {'Bajo': '#E9F2E7', 'Medio': '#FAF0DA', 'Alto': '#F8E3DF'}
PALABRA_NIVEL = {'Bajo': 'Tranquilo', 'Medio': 'Precaución', 'Alto': 'Complicado'}
COLOR_TIPO = {'hurto': MARCA, 'violencia': '#B83A2E', 'accidente': OCRE}
NOMBRE_TIPO = {'hurto': 'Robos', 'violencia': 'Riñas y agresiones', 'accidente': 'Accidentes con heridos'}
UNO_TIPO = {'hurto': 'Robo', 'violencia': 'Riña o agresión', 'accidente': 'Accidente con heridos'}

TIPOS_REPORTE = {
    'robo': 'Robo o intento de robo', 'alumbrado': 'Alumbrado dañado', 'rina': 'Riña o pelea',
    'accidente': 'Accidente', 'bloqueo': 'Vía bloqueada', 'sospechoso': 'Actitud sospechosa',
}
ICONO_REPORTE = {'alumbrado': 'lightbulb', 'robo': 'front_hand', 'accidente': 'car_crash', 'bloqueo': 'block',
                 'rina': 'groups', 'sospechoso': 'visibility'}

def _etiqueta_lugar(b):
    comuna = COMUNAS[b['comuna_id']]['nombre']
    return b['barrio'] if b['barrio'] == comuna else f'{b["barrio"]} · {comuna}'


LUGARES = {_etiqueta_lugar(b): b for b in sorted(BARRIOS, key=lambda b: b['barrio'])} if COMUNAS else {}
NOMBRES_LUGARES = list(LUGARES)
COORD_BARRIO = {b['barrio']: (b['lat'], b['lon']) for b in BARRIOS}

# ---------------------------------------------------------------- ESTILO
CSS = """@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,300..500,0..1,0');
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,800&family=Public+Sans:wght@400;500;600;700&display=swap');
html, body, .stApp, .stMarkdown, p, li, label, input, textarea, button { font-family:'Public Sans', sans-serif !important; }
h1, h2, h3, .serif { font-family:'Fraunces', Georgia, serif !important; letter-spacing:-0.01em; }
.block-container { max-width:1180px; padding-top:4.2rem; padding-bottom:3rem; }
.material-symbols-outlined { font-size:1.15em; vertical-align:-0.2em; }
[data-testid="stHeader"] { background:rgba(245,241,232,0.96); border-bottom:1px solid #E3DCCB; }

.estado { text-align:right; color:#6B655A; font-size:0.88rem; margin:-6px 0 14px 0; }
.antetitulo { color:#C47F2C; font-weight:700; text-transform:uppercase; letter-spacing:0.12em; font-size:0.76rem; margin-bottom:6px; }
.titular { font-family:'Fraunces',serif; font-size:2.6rem; line-height:1.08; font-weight:800; color:#1C1B19; margin:0 0 10px 0; }
.titular.chico { font-size:2rem; }
.bajada { font-size:1.08rem; color:#3E3A33; max-width:720px; line-height:1.55; margin-bottom:16px; }
.seccion { font-family:'Fraunces',serif; font-size:1.35rem; font-weight:600; color:#1C1B19; margin:28px 0 6px 0; }
.nota { color:#6B655A; font-size:0.88rem; margin:4px 0 10px 0; line-height:1.5; }
.carta { background:#FFFDF8; border:1px solid #E3DCCB; border-radius:14px; padding:16px 18px; }

.dato { background:#FFFDF8; border:1px solid #E3DCCB; border-radius:14px; padding:14px 18px; height:100%; }
.dato .valor { font-family:'Fraunces',serif; font-size:1.9rem; font-weight:800; line-height:1.15; }
.dato .etiqueta { color:#6B655A; font-size:0.87rem; margin-top:2px; }

.veredicto { display:flex; gap:22px; align-items:center; border-radius:16px; padding:20px 24px; border:2px solid; margin:8px 0 16px 0; }
.veredicto .medidor { min-width:130px; text-align:center; }
.veredicto .pct { font-family:'Fraunces',serif; font-size:3.2rem; font-weight:800; line-height:1; }
.veredicto .niv { font-weight:700; font-size:0.95rem; margin-top:4px; }
.veredicto h3 { margin:0 0 6px 0; font-size:1.5rem; font-weight:800; color:#1C1B19; }
.veredicto p { margin:0; font-size:1.04rem; line-height:1.55; color:#2B2823; }
@media (max-width: 700px) { .veredicto { flex-direction:column; text-align:center; } .titular { font-size:2rem; } }

.ruta { background:#FFFDF8; border:1px solid #E3DCCB; border-radius:14px; padding:14px 18px; height:100%; }
.ruta.sugerida { border:2px solid #1F4E5F; }
.ruta .tipo { font-weight:700; font-size:0.76rem; text-transform:uppercase; letter-spacing:0.1em; color:#6B655A; }
.ruta.sugerida .tipo { color:#1F4E5F; }
.ruta .cifras { display:flex; gap:20px; align-items:baseline; margin:6px 0; flex-wrap:wrap; }
.ruta .cifras b { font-family:'Fraunces',serif; font-size:1.8rem; }
.ruta .por { color:#3E3A33; font-size:0.92rem; }
.pastilla { display:inline-block; padding:3px 12px; border-radius:999px; color:white; font-weight:700; font-size:0.86rem; }

.franjas { display:grid; grid-template-columns:repeat(8, 1fr); gap:8px; margin:6px 0 8px 0; }
@media (max-width: 760px) { .franjas { grid-template-columns:repeat(4, 1fr); } }
.franja { background:#FFFDF8; border:1px solid #E3DCCB; border-top:6px solid; border-radius:10px; padding:8px 6px; text-align:center; }
.franja.actual { outline:2px solid #1C1B19; }
.franja .h { font-size:0.78rem; color:#6B655A; }
.franja .v { font-family:'Fraunces',serif; font-weight:800; font-size:1.25rem; }
.franja .n { font-size:0.74rem; font-weight:600; }

.fila-zona { display:flex; align-items:center; gap:10px; padding:9px 0; border-bottom:1px dashed #E3DCCB; }
.fila-zona:last-child { border-bottom:none; }
.punto { width:12px; height:12px; border-radius:50%; flex:none; display:inline-block; }
.fila-zona .nombre { font-weight:600; color:#1C1B19; }
.fila-zona .detalle { color:#6B655A; font-size:0.84rem; }
.fila-zona .pct { margin-left:auto; font-family:'Fraunces',serif; font-weight:800; font-size:1.1rem; }

.aviso { background:#FFFDF8; border:1px solid #E3DCCB; border-left:5px solid #C47F2C; border-radius:10px; padding:10px 14px; margin-bottom:8px; font-size:0.95rem; }
.consejo { display:flex; gap:12px; padding:10px 0; border-bottom:1px dashed #E3DCCB; font-size:0.98rem; line-height:1.45; }
.consejo:last-child { border-bottom:none; }
.consejo .material-symbols-outlined { color:#1F4E5F; font-size:1.4em; }
.paso { background:#FFFDF8; border:1px solid #E3DCCB; border-radius:14px; padding:16px; height:100%; }
.paso .num { font-family:'Fraunces',serif; font-size:2rem; font-weight:800; color:#C47F2C; line-height:1; }
.paso b { display:block; margin:6px 0 4px 0; }
.paso span { color:#3E3A33; font-size:0.92rem; }
.chip { display:inline-block; border:1px solid #D9CFBA; background:#FFFDF8; border-radius:999px; padding:4px 12px; margin:0 6px 6px 0; font-size:0.86rem; }

.barra { margin:10px 0 14px 0; }
.barra .fila { display:flex; align-items:center; gap:12px; margin:8px 0; }
.barra .quien { width:150px; font-weight:600; font-size:0.95rem; }
.barra .riel { flex:1; background:#EEE7D8; border-radius:999px; height:26px; overflow:hidden; }
.barra .lleno { height:100%; border-radius:999px; display:flex; align-items:center; justify-content:flex-end; padding-right:10px; color:white; font-weight:700; font-size:0.88rem; }

.pie { margin-top:40px; padding-top:14px; border-top:1px solid #E3DCCB; color:#8A8378; font-size:0.8rem; line-height:1.5; }
div[data-testid="stVerticalBlockBorderWrapper"] { border-radius:14px; }
.stButton button, .stDownloadButton button, .stLinkButton a, .stFormSubmitButton button { border-radius:10px; font-weight:600; }
"""
# Los estilos van en un solo bloque <style> sin líneas en blanco: en Markdown, una línea en blanco
# cortaría el bloque y el resto del CSS aparecería como texto en la página.
st.markdown('<style>' + ' '.join(linea.strip() for linea in CSS.splitlines() if linea.strip()) + '</style>',
            unsafe_allow_html=True)


# ---------------------------------------------------------------- PIEZAS DE INTERFAZ
def html(texto):
    st.markdown('\n'.join(linea.strip() for linea in texto.splitlines()), unsafe_allow_html=True)


def icono(nombre):
    return f'<span class="material-symbols-outlined">{nombre}</span>'


def pastilla(nivel, texto=None):
    return f'<span class="pastilla" style="background:{COLOR_NIVEL[nivel]}">{texto or nivel}</span>'


def seccion(titulo, nota=None):
    html(f'<div class="seccion">{titulo}</div>' + (f'<div class="nota">{nota}</div>' if nota else ''))


def dato(col, valor, etiqueta, color=TINTA):
    col.markdown(f'<div class="dato"><div class="valor" style="color:{color}">{valor}</div>'
                 f'<div class="etiqueta">{etiqueta}</div></div>', unsafe_allow_html=True)


def franjas_html(items, marcada=None):
    """Tira de franjas horarias: cada una con su hora, su % y su color."""
    celdas = []
    for i, (etiqueta, riesgo) in enumerate(items):
        n = nivel_de(riesgo)
        celdas.append(f'<div class="franja{" actual" if i == marcada else ""}" style="border-top-color:{COLOR_NIVEL[n]}">'
                      f'<div class="h">{etiqueta}</div><div class="v" style="color:{COLOR_NIVEL[n]}">{riesgo:.0f}%</div>'
                      f'<div class="n" style="color:{COLOR_NIVEL[n]}">{PALABRA_NIVEL[n]}</div></div>')
    return '<div class="franjas">' + ''.join(celdas) + '</div>'


def estado_barra(momento):
    pron = pronostico()
    clima = f' · {pron["temperatura"]:.0f} °C, {clima_texto(pron["lluvia_mm"]).lower()}' if pron else ''
    html(f'<div class="estado">{icono("location_on")} {CIUDAD} · {fecha_texto(momento)} · '
         f'{hora_texto(momento.hour, momento.minute)}{clima}</div>')


def estilo(fig, alto=320):
    fig.update_layout(template='plotly_white', height=alto, margin=dict(l=10, r=10, t=30, b=10),
                      font=dict(family='Public Sans, sans-serif', size=13, color=TINTA),
                      paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False)
    fig.update_xaxes(gridcolor='#EAE3D3', zeroline=False)
    fig.update_yaxes(gridcolor='#EAE3D3', zeroline=False)
    return fig


def grafica(fig):
    st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})


def pie_de_pagina():
    html('<div class="pie">Halcón · datos reales y abiertos de la Policía Nacional y la Alcaldía de Bucaramanga '
         '(datos.gov.co), clima de Open-Meteo y calles de OpenStreetMap. El riesgo es una estimación basada en '
         'incidentes denunciados: te ayuda a decidir, pero no reemplaza tu criterio ni a las autoridades. '
         'Emergencias: 123.</div>')


def ahora():
    return datetime.now(ZONA_HORARIA).replace(tzinfo=None, second=0, microsecond=0)


def inicio_franja(momento):
    return momento.replace(hour=franja_de(momento.hour) * 3, minute=0, second=0, microsecond=0)


def hace(fecha, momento):
    minutos = int((momento - fecha).total_seconds() // 60)
    if minutos < 1:
        return 'justo ahora'
    return f'hace {minutos} min' if minutos < 60 else f'hace {minutos // 60} h'


def etiqueta_franja(m, primera=False):
    return 'Ahora' if primera else f'{DIAS[m.weekday()][:3].capitalize()} {hora_corta(m.hour)}'


# ---------------------------------------------------------------- DATOS Y MODELO
@st.cache_resource
def cargar_modelos():
    ruta = CARPETA / 'modelo' / 'modelo_halcon.joblib'
    if not ruta.exists():
        return None
    modelos = joblib.load(ruta)
    configurar_umbrales(*modelos['umbrales'])
    return modelos


@st.cache_data
def cargar_metricas():
    ruta = CARPETA / 'modelo' / 'metricas.json'
    return json.loads(ruta.read_text(encoding='utf-8')) if ruta.exists() else None


@st.cache_data
def cargar_validacion():
    val = pd.read_csv(CARPETA / 'modelo' / 'validacion.csv.gz')
    inc = pd.read_csv(CARPETA / 'modelo' / 'validacion_incidentes.csv.gz')
    return val, inc


def calientes():
    info = cargar_metricas()
    return info['reales']['calientes'] if info else {}


@st.cache_data(ttl=900, show_spinner=False)
def pronostico():
    return pronostico_real()


@st.cache_data(ttl=30, show_spinner=False)
def reportes_desde(desde):
    return almacen.leer_reportes(desde)


def comunidad(momento):
    """Reportes de las últimas 2 horas por comuna y comunas con alumbrado reportado como dañado (12 h)."""
    rep = reportes_desde(ahora() - timedelta(hours=24))
    if rep.empty:
        return (), (), rep
    rep = rep.copy()
    rep['comuna_id'] = pd.to_numeric(rep['zona'], errors='coerce')
    recientes = rep[(rep['fecha'] <= momento) & (rep['fecha'] >= momento - timedelta(hours=2))]
    conteo = tuple(sorted((int(c), int(n)) for c, n in recientes.groupby('comuna_id').size().items()))
    fallas = rep[(rep['tipo'] == 'alumbrado') & (rep['fecha'] <= momento) & (rep['fecha'] >= momento - timedelta(hours=12))]
    return conteo, tuple(sorted(int(c) for c in set(fallas['comuna_id'].dropna()))), rep


@st.cache_data(ttl=300, show_spinner=False)
def estado(momento, lluvia=0.0, previa=0.0, temperatura=22.0, reportes=(), fallas=()):
    return estado_ciudad(cargar_modelos(), inicio_franja(momento), lluvia, previa, temperatura,
                         dict(reportes), set(fallas))


@st.cache_data(ttl=3600, show_spinner=False)
def riesgo_del_dia(fecha, lluvia):
    filas = pd.DataFrame([fila(cid, datetime.combine(fecha, hora_dia(f * 3)), lluvia, lluvia * 0.5)
                          for f in range(8) for cid in COMUNAS])
    salida = predecir(cargar_modelos(), filas)
    salida['zona'] = salida['comuna_id'].map(lambda c: COMUNAS[c]['nombre'])
    return salida


@st.cache_data(ttl=86400, show_spinner=False)
def _calles_guardadas(zonas, modo):
    geo = geometria_osrm(list(zonas), modo) or geometria_osrm(list(zonas), modo)
    if geo is None:
        raise ConnectionError('OpenStreetMap no respondió')       # así el fallo no se guarda en caché
    return geo


def calles_reales(zonas, modo):
    try:
        return _calles_guardadas(tuple(int(z) for z in zonas), modo)
    except ConnectionError:
        return None


def requiere_modelo():
    modelos = cargar_modelos()
    if modelos is None or not COMUNAS:
        st.error('Halcón todavía no tiene un modelo entrenado. Ejecuta en orden `1_descargar_datos.py`, '
                 '`2_limpiar_y_cargar.py` y `3_entrenar_modelo.py`.')
        st.stop()
    return modelos


def clima_en(momento, escenario='auto'):
    if escenario != 'auto':
        mm = ESCENARIOS_LLUVIA[escenario]
        return mm, mm * 0.5, 22.0 if mm else 24.0
    return clima_de_franja(pronostico(), momento)


# ---------------------------------------------------------------- MAPA
def mapa(est, rutas=None, marcas=None, alto=520, zoom=12.6):
    fig = go.Figure()
    for nivel in NIVELES:
        lat, lon = [], []
        for a, b in ARISTAS:
            if nivel_de((est.loc[a, 'riesgo'] + est.loc[b, 'riesgo']) / 2) == nivel:
                lat += [COMUNAS[a]['lat'], COMUNAS[b]['lat'], None]
                lon += [COMUNAS[a]['lon'], COMUNAS[b]['lon'], None]
        fig.add_trace(go.Scattermap(lat=lat, lon=lon, mode='lines', hoverinfo='skip', showlegend=False,
                                    line=dict(width=3, color=COLOR_NIVEL[nivel]), opacity=0.3))
    fig.add_trace(go.Scattermap(
        lat=[b['lat'] for b in BARRIOS], lon=[b['lon'] for b in BARRIOS], mode='markers', showlegend=False,
        marker=dict(size=[5 + min(b['incidentes'], 3000) ** 0.5 / 6 for b in BARRIOS],
                    color=[COLOR_NIVEL[est.loc[b['comuna_id'], 'nivel']] for b in BARRIOS], opacity=0.4),
        text=[b['barrio'] for b in BARRIOS], customdata=[COMUNAS[b['comuna_id']]['nombre'] for b in BARRIOS],
        hovertemplate='<b>%{text}</b> · %{customdata}<extra></extra>'))
    for ruta, color, nombre, ancho, geo in (rutas or []):
        lat = geo['lat'] if geo else [COMUNAS[z]['lat'] for z in ruta['zonas']]
        lon = geo['lon'] if geo else [COMUNAS[z]['lon'] for z in ruta['zonas']]
        fig.add_trace(go.Scattermap(lat=lat, lon=lon, mode='lines', name=nombre, hoverinfo='skip',
                                    line=dict(width=ancho, color=color)))
    cal = calientes()
    detalle = [[f['riesgo'], PALABRA_NIVEL[f['nivel']], INCIDENTE_TEXTO[f['incidente']],
                ', '.join(cal.get(f'{cid}-{int(f["franja"])}', [])[:3]) or '—'] for cid, f in est.iterrows()]
    fig.add_trace(go.Scattermap(
        lat=[COMUNAS[c]['lat'] for c in est.index], lon=[COMUNAS[c]['lon'] for c in est.index],
        mode='markers+text', showlegend=False, text=est['zona'], textposition='top center',
        textfont=dict(size=12, color=TINTA),
        marker=dict(size=14 + est['riesgo'] / 2.2, color=[COLOR_NIVEL[n] for n in est['nivel']], opacity=0.9),
        customdata=detalle,
        hovertemplate='<b>%{text}</b> · %{customdata[1]} (%{customdata[0]:.0f}%)<br>Lo más común: %{customdata[2]}'
                      '<br>Barrios más afectados a esta hora: %{customdata[3]}<extra></extra>'))
    if marcas:
        fig.add_trace(go.Scattermap(lat=[m[0] for m in marcas], lon=[m[1] for m in marcas], mode='markers',
                                    name='Incidente real', marker=dict(size=13, color=TINTA, opacity=0.9),
                                    text=[m[2] for m in marcas], hovertemplate='%{text}<extra></extra>'))
    if rutas:
        r0, geo = rutas[0][0], rutas[0][4]
        puntos = [((geo['lat'][0], geo['lon'][0]) if geo else (COMUNAS[r0['zonas'][0]]['lat'], COMUNAS[r0['zonas'][0]]['lon']), 'Salida', TINTA),
                  ((geo['lat'][-1], geo['lon'][-1]) if geo else (COMUNAS[r0['zonas'][-1]]['lat'], COMUNAS[r0['zonas'][-1]]['lon']), 'Llegada', OCRE)]
        for (la, lo), texto, color in puntos:
            fig.add_trace(go.Scattermap(lat=[la], lon=[lo], mode='markers+text', text=[texto], showlegend=False,
                                        marker=dict(size=18, color=color), textposition='bottom center',
                                        textfont=dict(size=12, color=TINTA), hoverinfo='skip'))
    fig.update_layout(map=dict(style='carto-positron', center=dict(lat=CENTRO[0] - 0.003, lon=CENTRO[1]), zoom=zoom),
                      margin=dict(l=0, r=0, t=0, b=0), height=alto, paper_bgcolor=PAPEL,
                      legend=dict(x=0.01, y=0.99, bgcolor='rgba(255,253,248,0.92)', bordercolor=LINEA, borderwidth=1))
    st.plotly_chart(fig, width='stretch', config={'displayModeBar': False, 'scrollZoom': True})


def leyenda():
    html('<div class="nota">' + ' &nbsp; '.join(
        f'<span class="punto" style="background:{COLOR_NIVEL[n]}"></span> {PALABRA_NIVEL[n]}' for n in NIVELES) +
        ' &nbsp;·&nbsp; Círculos grandes: comunas. Pequeños: barrios. Toca uno para ver el detalle.</div>')


def filas_zonas(est, ids):
    cal = calientes()
    partes = []
    for cid in ids:
        f = est.loc[cid]
        top = cal.get(f'{cid}-{int(f["franja"])}', [])[:2]
        detalle = INCIDENTE_TEXTO[f['incidente']].capitalize() + (' · sobre todo en ' + unir(top) if top else '')
        partes.append(f'<div class="fila-zona"><span class="punto" style="background:{COLOR_NIVEL[f["nivel"]]}"></span>'
                      f'<div><div class="nombre">{f["zona"]}</div><div class="detalle">{detalle}</div></div>'
                      f'<div class="pct" style="color:{COLOR_NIVEL[f["nivel"]]}">{f["riesgo"]:.0f}%</div></div>')
    return '<div class="carta">' + ''.join(partes) + '</div>'


def que_significa():
    with st.expander('¿Qué significa el porcentaje?'):
        st.markdown(f'Es la probabilidad de que se denuncie al menos un robo, una riña o un accidente con heridos en '
                    f'esa comuna durante esa franja de 3 horas, calculada con 10 años de datos reales de la Policía. '
                    f'**Tranquilo** por debajo de {UMBRALES["medio"]:.0f}%, **precaución** desde '
                    f'{UMBRALES["medio"]:.0f}% y **complicado** desde {UMBRALES["alto"]:.0f}% (el 12 % de los '
                    f'momentos más difíciles de la ciudad).')


# ================================================================ INICIO
def pagina_inicio():
    requiere_modelo()
    momento = ahora()
    lluvia, previa, temp = clima_en(momento)
    reportes, fallas, _ = comunidad(momento)
    est = estado(momento, lluvia, previa, temp, reportes, fallas)
    estado_barra(momento)

    izq, der = st.columns([1.15, 1], gap='large')
    with izq:
        html('<div class="antetitulo">Rutas tranquilas en Bucaramanga</div>'
             '<div class="titular">Llega bien,<br>no solo rápido.</div>'
             '<div class="bajada">Halcón aprendió de más de 80.000 robos, riñas y accidentes reales denunciados '
             'desde 2016. Dile para dónde vas y te dice por dónde ir, a qué hora salir y qué evitar.</div>')
    with der:
        with st.form('buscar', border=True):
            st.markdown('**¿Para dónde vas?**')
            origen = st.selectbox('Salgo de', NOMBRES_LUGARES, index=None, placeholder='Escribe tu barrio')
            destino = st.selectbox('Voy a', NOMBRES_LUGARES, index=None, placeholder='Escribe el barrio de destino')
            modo = st.segmented_control('Me muevo', list(MODOS), format_func=MODOS.get, default='moto')
            if st.form_submit_button('Ver mi ruta', type='primary', icon=':material/route:', width='stretch'):
                if origen and destino:
                    st.session_state['viaje'] = {'origen': origen, 'destino': destino, 'modo': modo or 'moto'}
                    st.switch_page(PAGINA_RUTA)
                else:
                    st.warning('Elige de dónde sales y a dónde vas.')

    promedio = est['riesgo'].mean()
    n_alto = int((est['nivel'] == 'Alto').sum())
    seccion('Así está la ciudad ahora', franja_texto(franja_de(momento.hour)).capitalize())
    k1, k2, k3 = st.columns(3)
    dato(k1, PALABRA_NIVEL[nivel_de(promedio)], f'Nivel general de la ciudad ({promedio:.0f}% en promedio)',
         COLOR_NIVEL[nivel_de(promedio)])
    dato(k2, f'{n_alto} de 17', 'comunas complicadas en este momento', COLOR_NIVEL['Alto'] if n_alto else COLOR_NIVEL['Bajo'])
    dato(k3, f'{icono(icono_clima(lluvia))} {clima_texto(lluvia)}', f'{temp:.0f} °C · clima en vivo')

    st.write('')
    izq, der = st.columns([1.7, 1], gap='medium')
    with izq:
        mapa(est, alto=500)
        leyenda()
    with der:
        orden = est.sort_values('riesgo', ascending=False)
        html('<div class="antetitulo">Mejor evita ahora</div>')
        html(filas_zonas(est, orden.index[:4]))
        html('<div class="antetitulo" style="margin-top:16px">Más tranquilas</div>')
        html(filas_zonas(est, orden.index[-3:][::-1]))
    que_significa()

    seccion('Hoy, franja por franja', 'Cómo va a estar la ciudad en las próximas 24 horas, con la lluvia pronosticada.')
    items = []
    for i, m in enumerate(proximas_franjas(momento, 8)):
        mm, pv, t = clima_en(m)
        items.append((etiqueta_franja(m, i == 0), estado(m, mm, pv, t)['riesgo'].mean()))
    html(franjas_html(items, marcada=0))
    mejor = min(range(1, 8), key=lambda i: items[i][1])
    html(f'<div class="aviso">{icono("schedule")} El momento más tranquilo que viene: <b>{items[mejor][0]}</b> '
         f'({items[mejor][1]:.0f}%). Si tienes vueltas que hacer, ese es buen momento.</div>')
    pie_de_pagina()


# ================================================================ MI RUTA
def pagina_ruta():
    modelos = requiere_modelo()
    momento_actual = ahora()
    estado_barra(momento_actual)
    viaje = st.session_state.get('viaje', {})

    def indice(nombre, respaldo):
        if nombre in NOMBRES_LUGARES:
            return NOMBRES_LUGARES.index(nombre)
        return next((i for i, n in enumerate(NOMBRES_LUGARES) if n == respaldo or n.startswith(respaldo + ' ·')), 0)

    html('<div class="titular chico">¿Para dónde vas?</div>')
    with st.container(border=True):
        c1, c2, c3 = st.columns([1, 1, 1.1])
        origen = c1.selectbox('Salgo de', NOMBRES_LUGARES, index=indice(viaje.get('origen'), 'Lagos del Cacique'))
        destino = c2.selectbox('Voy a', NOMBRES_LUGARES, index=indice(viaje.get('destino'), 'Comuneros'))
        modo = c3.segmented_control('Me muevo', list(MODOS), format_func=MODOS.get,
                                    default=viaje.get('modo', 'moto')) or 'moto'
        c4, c5, c6 = st.columns([1, 1, 1.1])
        cuando = c4.segmented_control('¿Cuándo sales?', ['Ahora', 'Más tarde'], default='Ahora') or 'Ahora'
        if cuando == 'Ahora':
            salida = momento_actual
        else:
            sugerida = (momento_actual + timedelta(hours=2)).replace(minute=0)
            dia = c5.date_input('Día', value=sugerida.date(), format='DD/MM/YYYY')
            salida = datetime.combine(dia, c6.time_input('Hora', value=sugerida.time(), step=1800))
        with st.expander('Cambiar el clima (por defecto usa el pronóstico real)'):
            escenario = st.segmented_control('Clima', ['auto'] + list(ESCENARIOS_LLUVIA), default='auto',
                                             format_func=lambda c: 'Pronóstico real' if c == 'auto' else c) or 'auto'
    st.session_state['viaje'] = {'origen': origen, 'destino': destino, 'modo': modo}

    o_b, d_b = LUGARES[origen], LUGARES[destino]
    o, d = o_b['comuna_id'], d_b['comuna_id']
    with st.spinner('Calculando tu ruta…'):
        lluvia, previa, temp = clima_en(salida, escenario)
        reportes, fallas, _ = comunidad(salida)
        est = estado(salida, lluvia, previa, temp, reportes, fallas)
        rapida, segura = calcular_rutas(est, o, d, modo, franja_de(salida.hour))
        msg = mensaje_principal(modelos, est, rapida, segura, salida, calientes())
        hay_desvio = segura is not rapida
        geo_r = calles_reales(rapida['zonas'], modo) if len(rapida['zonas']) > 1 else None
        geo_s = calles_reales(segura['zonas'], modo) if hay_desvio else geo_r

    # ---- el veredicto
    final = segura if hay_desvio else rapida
    nivel = nivel_de(final['riesgo'])
    html(f'<div class="veredicto" style="border-color:{COLOR_NIVEL[nivel]};background:{FONDO_NIVEL[nivel]}">'
         f'<div class="medidor" style="color:{COLOR_NIVEL[nivel]}"><div class="pct">{final["riesgo"]:.0f}%</div>'
         f'<div class="niv">{PALABRA_NIVEL[nivel]}</div></div>'
         f'<div><h3>{msg["titulo"]}</h3><p>{msg["texto"]}</p></div></div>')

    tarjetas = [(rapida, geo_r, 'Ruta habitual · la más corta' if hay_desvio else 'Tu ruta', '')]
    if hay_desvio:
        tarjetas.append((segura, geo_s, 'Ruta sugerida por Halcón', 'sugerida'))
    for col, (ruta, geo, titulo, clase) in zip(st.columns(len(tarjetas)), tarjetas):
        if geo:
            ruta['km'] = round(geo['km'], 1)
        n = nivel_de(ruta['riesgo'])
        col.markdown(f'<div class="ruta {clase}"><div class="tipo">{titulo}</div>'
                     f'<div class="cifras"><span><b>{ruta["minutos"]}</b> min</span><span><b>{ruta["km"]}</b> km</span>'
                     f'{pastilla(n, f"{PALABRA_NIVEL[n]} · {ruta['riesgo']:.0f}%")}</div>'
                     f'<div class="por">Pasa por {" → ".join(ruta["calles"])}</div></div>', unsafe_allow_html=True)

    st.write('')
    capas = [(rapida, '#8A8378' if hay_desvio else MARCA, 'Ruta habitual', 6 if hay_desvio else 7, geo_r)]
    if hay_desvio:
        capas.append((segura, MARCA, 'Ruta sugerida', 7, geo_s))
    mapa(est, capas, alto=460, zoom=12.8)
    html('<div class="nota">Los minutos son aproximados y no incluyen el tráfico en vivo.</div>')

    # ---- a qué hora salir
    seccion('¿A qué hora te conviene salir?')
    items = []
    for i, m in enumerate([salida] + proximas_franjas(salida, 8)[1:]):
        mm, pv, t = clima_en(m, escenario)
        rep_m, fal_m, _ = comunidad(m)
        _, s = calcular_rutas(estado(m, mm, pv, t, rep_m, fal_m), o, d, modo, franja_de(m.hour))
        items.append(('Tu hora' if i == 0 else etiqueta_franja(m), s['riesgo']))
    html(franjas_html(items, marcada=0))
    mejor = min(range(len(items)), key=lambda i: (items[i][1], i))
    if items[mejor][1] <= items[0][1] - 5:
        html(f'<div class="aviso">{icono("schedule")} Si puedes, sal <b>{items[mejor][0]}</b>: el riesgo baja de '
             f'{items[0][1]:.0f}% a {items[mejor][1]:.0f}%.</div>')
    else:
        html(f'<div class="aviso">{icono("check_circle")} Salir a tu hora está bien: las próximas horas no mejoran mucho.</div>')

    # ---- consejos y compartir
    izq, der = st.columns([1.1, 1], gap='large')
    with izq:
        seccion('Ten en cuenta')
        iconos = ['shield', 'umbrella' if lluvia >= 0.5 else 'directions', 'share_location']
        html('<div class="carta">' + ''.join(f'<div class="consejo">{icono(i)}<div>{c}</div></div>' for i, c in
                                              zip(iconos, consejos(est, final, modo, lluvia, calientes(), salida))) + '</div>')
    with der:
        seccion('Avisa a tu gente')
        o_txt, d_txt = o_b['barrio'], d_b['barrio']
        texto = (f'Voy de {o_txt} a {d_txt} ({MODOS[modo].lower()}). Salgo {hora_texto(salida.hour, salida.minute)} y '
                 f'llego en unos {final["minutos"]} min, pasando por {" → ".join(final["calles"])}. '
                 f'Halcón dice: {PALABRA_NIVEL[nivel].lower()} ({final["riesgo"]:.0f}%). Si no te escribo al llegar, llámame.')
        st.link_button('Enviar por WhatsApp', 'https://wa.me/?text=' + urllib.parse.quote(texto),
                       icon=':material/send:', width='stretch', type='primary')
        imagen = tarjeta_trayecto(o_txt, d_txt, f'{fecha_texto(salida)} · {hora_texto(salida.hour, salida.minute)}',
                                  MODOS[modo], final['minutos'], final['riesgo'], nivel, final['calles'],
                                  final['zonas'], geo_s)
        st.download_button('Descargar tarjeta para historias', imagen, file_name='mi_trayecto_halcon.png',
                           mime='image/png', icon=':material/download:', width='stretch')
        with st.expander('Ver la tarjeta'):
            st.image(imagen, width='stretch')

    with st.expander('Ver la ruta comuna por comuna'):
        html(filas_zonas(est, final['zonas']))
    que_significa()

    clave = (o_b['barrio'], d_b['barrio'], modo, salida.isoformat(), escenario)
    if st.session_state.get('ultima_consulta') != clave:
        st.session_state['ultima_consulta'] = clave
        try:
            almacen.guardar_consulta(fecha=momento_actual, origen=o_b['barrio'][:40], destino=d_b['barrio'][:40],
                                     modo=modo, hora_salida=salida, clima=clima_texto(lluvia),
                                     riesgo_habitual=float(rapida['riesgo']), riesgo_sugerida=float(segura['riesgo']),
                                     hubo_desvio=int(hay_desvio), minutos_extra=int(segura['minutos'] - rapida['minutos']))
        except Exception:
            pass
    pie_de_pagina()


# ================================================================ MAPA POR HORAS
def pagina_mapa():
    requiere_modelo()
    momento = ahora()
    estado_barra(momento)
    html('<div class="titular chico">La ciudad, hora por hora</div>'
         '<div class="bajada">Una misma comuna no es igual a las 2 de la tarde que un viernes a las 9 de la noche. '
         'Elige el día y la hora.</div>')
    with st.container(border=True):
        c1, c2, c3 = st.columns([1, 2.2, 1.4])
        fecha = c1.date_input('Día', value=momento.date(), format='DD/MM/YYYY')
        franja = c2.select_slider('Hora', options=list(range(8)), value=franja_de(momento.hour),
                                  format_func=franja_texto)
        escenario = c3.segmented_control('Clima', ['Sin lluvia', 'Lluvia', 'Aguacero'],
                                         default='Sin lluvia') or 'Sin lluvia'
    mm = ESCENARIOS_LLUVIA[escenario]
    elegido = datetime.combine(fecha, hora_dia(franja * 3))
    est = estado(elegido, mm, mm * 0.5)

    izq, der = st.columns([1.7, 1], gap='medium')
    with izq:
        mapa(est, alto=480)
        leyenda()
    with der:
        n_alto = int((est['nivel'] == 'Alto').sum())
        html(f'<div class="antetitulo">{fecha_texto(elegido).capitalize()}, {franja_texto(franja)}</div>')
        dato(st, f'{n_alto} de 17', 'comunas complicadas', COLOR_NIVEL['Alto'] if n_alto else COLOR_NIVEL['Bajo'])
        st.write('')
        html(filas_zonas(est, est.sort_values('riesgo', ascending=False).index[:5]))

    otro = 'Sin lluvia' if mm >= 0.5 else 'Lluvia'
    alterno = estado(elegido, ESCENARIOS_LLUVIA[otro], ESCENARIOS_LLUVIA[otro] * 0.5)
    actual_p, otro_p = est['riesgo'].mean(), alterno['riesgo'].mean()
    si = 'Si no lloviera' if otro == 'Sin lluvia' else 'Si llueve'
    cambio = (f'el riesgo promedio pasaría de {actual_p:.0f}% a {otro_p:.0f}%' if abs(otro_p - actual_p) >= 1
              else 'el riesgo casi no cambiaría a esta hora')
    html(f'<div class="aviso">{icono("rainy")} {si}, {cambio}. En los datos reales, con lluvia hay menos gente en la '
         f'calle: bajan algunos robos, pero suben los accidentes.</div>')

    with st.expander('Ver el día completo (todas las comunas, todas las horas)'):
        dia = riesgo_del_dia(fecha, mm)
        tabla = dia.pivot_table(index='zona', columns='franja', values='riesgo')
        tabla = tabla.loc[tabla.mean(axis=1).sort_values().index]
        fig = go.Figure(go.Heatmap(
            z=tabla.values, x=[franja_texto(f).replace('de ', '') for f in tabla.columns], y=tabla.index,
            colorscale=[[0, '#E9F2E7'], [0.3, '#A9C8A2'], [0.5, '#E8C46F'], [0.75, '#D27A45'], [1, '#9E2F25']],
            zmin=0, zmax=max(50, float(tabla.values.max())), xgap=2, ygap=2, showscale=False,
            text=tabla.values.round(0), texttemplate='%{text:.0f}%', hovertemplate='%{y}<br>%{x}: %{z:.0f}%<extra></extra>'))
        grafica(estilo(fig, 540))
    que_significa()
    pie_de_pagina()


# ================================================================ REPORTAR
def pagina_reportar():
    requiere_modelo()
    momento = ahora()
    lluvia, previa, temp = clima_en(momento)
    estado_barra(momento)
    html('<div class="titular chico">¿Viste algo? Avísale a la ciudad.</div>'
         '<div class="bajada">Tu reporte sube el riesgo de esa comuna durante las próximas 2 horas para todos los que '
         'planeen una ruta por ahí. El alumbrado dañado cuenta 12 horas en la noche.</div>')
    izq, der = st.columns(2, gap='large')
    with izq:
        with st.form('reporte', clear_on_submit=True, border=True):
            lugar = st.selectbox('¿En qué barrio?', NOMBRES_LUGARES, index=None, placeholder='Escribe el barrio')
            tipo = st.radio('¿Qué pasó?', list(TIPOS_REPORTE), format_func=TIPOS_REPORTE.get, horizontal=True)
            comentario = st.text_input('Detalle (opcional)', max_chars=120,
                                       placeholder='Ej: el poste de la esquina del parque está apagado')
            enviado = st.form_submit_button('Enviar reporte', type='primary', icon=':material/campaign:', width='stretch')
        if enviado and not lugar:
            st.warning('Elige el barrio donde pasó.')
        elif enviado:
            b = LUGARES[lugar]
            cid = b['comuna_id']
            reportes, fallas, _ = comunidad(momento)
            antes = float(estado(momento, lluvia, previa, temp, reportes, fallas).loc[cid, 'riesgo'])
            almacen.guardar_reporte(momento, str(cid), tipo, f'{b["barrio"]}: {comentario}'.strip(': '))
            reportes_desde.clear()
            reportes, fallas, _ = comunidad(momento)
            despues = float(estado(momento, lluvia, previa, temp, reportes, fallas).loc[cid, 'riesgo'])
            st.success(f'Gracias. El riesgo en {COMUNAS[cid]["nombre"]} pasó de {antes:.0f}% a {despues:.0f}%. '
                       'Quien planee una ruta por ahí ya lo va a ver.', icon=':material/check_circle:')
    with der:
        _, _, rep = comunidad(momento)
        seccion('Reportes de las últimas 24 horas')
        if rep.empty:
            html('<div class="carta">Todavía no hay reportes hoy.</div>')
        else:
            filas = []
            for _, r in rep.head(12).iterrows():
                cid = int(r['comuna_id']) if pd.notna(r['comuna_id']) else None
                filas.append(f'<div class="fila-zona">{icono(ICONO_REPORTE.get(r["tipo"], "flag"))}'
                             f'<div><div class="nombre">{TIPOS_REPORTE.get(r["tipo"], r["tipo"])} · '
                             f'{COMUNAS[cid]["nombre"] if cid in COMUNAS else ""}</div>'
                             f'<div class="detalle">{hace(r["fecha"], momento)} · {r["comentario"]}</div></div></div>')
            html('<div class="carta">' + ''.join(filas) + '</div>')
    pie_de_pagina()


# ================================================================ ¿FUNCIONA?
def elegir_dia_al_azar(semilla=None):
    val, _ = cargar_validacion()
    por_franja = val.groupby(['fecha', 'franja'])['incidentes'].sum()
    candidatos = por_franja[por_franja >= 4].index.tolist()
    fecha, franja = random.Random(semilla).choice(candidatos)
    st.session_state['v_fecha'] = date.fromisoformat(fecha)
    st.session_state['v_franja'] = int(franja)


def pagina_funciona():
    modelos = requiere_modelo()
    info = cargar_metricas()
    r = info['resultados'][info['mejor']]
    estado_barra(ahora())
    html('<div class="antetitulo">¿Funciona?</div>'
         '<div class="titular chico">No nos creas: compruébalo con días reales.</div>'
         '<div class="bajada">Halcón aprendió solo con datos hasta diciembre de 2024. Después lo pusimos a predecir '
         '2025 y 2026, sin mostrarle lo que pasó, y comparamos con los incidentes que de verdad se denunciaron.</div>')

    veces = r['incidentes_en_alto'] / r['tiempo_alto']
    k1, k2, k3 = st.columns(3)
    dato(k1, f'{veces:.0f} veces', 'mejor que adivinar: en los momentos que marcó como complicados ocurrieron '
                                   f'{veces:.0f} veces más incidentes de los que tocarían al azar', MARCA)
    dato(k2, f'{r["incidentes_en_medio_alto"]:.0f}%', f'de los incidentes reales pasaron donde Halcón había dicho '
                                                       f'"precaución" o "complicado"', COLOR_NIVEL['Medio'])
    dato(k3, f'{r["primera_con_incidente"]:.0f}%', 'de las veces, la comuna que Halcón ponía de primera tuvo '
                                                    f'incidentes (una comuna cualquiera: {r["cualquiera_con_incidente"]:.0f}%)',
         COLOR_NIVEL['Alto'])

    seccion('El 12 % del tiempo que Halcón marcó en rojo, ¿cuántos incidentes atrapó?')
    html(f'<div class="carta barra">'
         f'<div class="fila"><div class="quien">Con Halcón</div><div class="riel"><div class="lleno" '
         f'style="width:{r["incidentes_en_alto"]:.0f}%;background:{MARCA}">{r["incidentes_en_alto"]:.0f}%</div></div></div>'
         f'<div class="fila"><div class="quien">Marcando al azar</div><div class="riel"><div class="lleno" '
         f'style="width:{r["tiempo_alto"]:.0f}%;background:#8A8378">{r["tiempo_alto"]:.0f}%</div></div></div>'
         f'<div class="nota">Porcentaje de todos los incidentes de 2025-2026 que cayeron dentro de las franjas '
         f'marcadas en rojo.</div></div>')

    # ---- pruébalo con un día real
    seccion('Pruébalo tú con un día real')
    val, inc = cargar_validacion()
    if 'v_fecha' not in st.session_state:
        elegir_dia_al_azar(semilla=ahora().date().isoformat())
    c1, c2, c3 = st.columns([1, 2, 1])
    c1.date_input('Día', key='v_fecha', min_value=date(2025, 1, 1), max_value=date.fromisoformat(val['fecha'].max()),
                  format='DD/MM/YYYY')
    c2.select_slider('Hora', options=list(range(8)), key='v_franja', format_func=franja_texto)
    c3.button('Otro día al azar', icon=':material/casino:', on_click=elegir_dia_al_azar, width='stretch')
    f_txt, fr = st.session_state['v_fecha'].isoformat(), st.session_state['v_franja']

    sub = val[(val['fecha'] == f_txt) & (val['franja'] == fr)].set_index('comuna_id')
    reales = inc[(inc['fecha'] == f_txt) & (inc['franja'] == fr)]
    if sub.empty:
        st.info('No hay datos para ese día.')
        pie_de_pagina()
        return
    est = sub[['riesgo']].copy()
    est['nivel'] = est['riesgo'].apply(nivel_de)
    est['zona'] = [COMUNAS[c]['nombre'] for c in est.index]
    est['franja'] = fr
    est['incidente'] = [max(TIPOS_INCIDENTE, key=lambda t: modelos['tipo'].get(f'{c}-{fr}', {}).get(t, 0)) for c in est.index]
    marcas = []
    for i, x in enumerate(reales.itertuples()):
        lat, lon = COORD_BARRIO.get(x.barrio, (COMUNAS[x.comuna_id]['lat'] + 0.002 * ((i % 3) - 1),
                                                COMUNAS[x.comuna_id]['lon'] + 0.002 * ((i % 2) * 2 - 1)))
        marcas.append((lat, lon, f'{UNO_TIPO[x.tipo]} · {x.barrio}'))
    n = len(reales)
    acertados = int(reales['comuna_id'].map(est['nivel']).isin(['Medio', 'Alto']).sum())
    marcadas = int((est['nivel'] != 'Bajo').sum())
    dia_txt = fecha_texto(datetime.fromisoformat(f_txt))
    if n:
        frase = (f'El {dia_txt}, {franja_texto(fr)}, se denunciaron <b>{n} incidentes</b>. '
                 f'<b>{acertados} de {n}</b> pasaron en comunas que Halcón había marcado en naranja o rojo '
                 f'(y solo había marcado {marcadas} de las 17).')
    else:
        frase = f'El {dia_txt}, {franja_texto(fr)}, no se denunció ningún incidente en la calle.'
    nivel_frase = 'Bajo' if n == 0 or acertados / n >= 0.6 else ('Medio' if acertados / n >= 0.35 else 'Alto')
    html(f'<div class="veredicto" style="border-color:{COLOR_NIVEL[nivel_frase]};background:{FONDO_NIVEL[nivel_frase]}">'
         f'<div class="medidor" style="color:{COLOR_NIVEL[nivel_frase]}"><div class="pct">{acertados}/{n}</div>'
         f'<div class="niv">en zonas marcadas</div></div><div><h3>Lo que Halcón dijo vs. lo que pasó</h3>'
         f'<p>{frase}</p></div></div>')
    mapa(est, marcas=marcas, alto=470)
    html('<div class="nota">Colores: lo que Halcón predijo para esa hora sin conocer el resultado. '
         'Puntos negros: los incidentes reales denunciados.</div>')

    seccion('Cómo lo hace')
    pasos = [('1', 'Aprende', f'{info["incidentes"]:,} incidentes reales de la Policía (2016-2026), cruzados con la '
                              'lluvia real de cada hora.'.replace(',', '.')),
             ('2', 'Mira el momento', 'Comuna, hora, día, festivo, quincena, lluvia y temperatura en vivo.'),
             ('3', 'Califica', 'Cada una de las 17 comunas queda tranquila, en precaución o complicada.'),
             ('4', 'Te guía', 'Compara la ruta más corta con una que esquiva lo complicado.')]
    for col, (num, titulo, texto) in zip(st.columns(4), pasos):
        col.markdown(f'<div class="paso"><div class="num">{num}</div><b>{titulo}</b><span>{texto}</span></div>',
                     unsafe_allow_html=True)

    st.write('')
    with st.expander('Detalles técnicos (para curiosos y profesores)'):
        detalles_tecnicos(info, r)
    pie_de_pagina()


def detalles_tecnicos(info, r):
    reales = info['reales']
    st.markdown(f'**Modelo ganador:** {info["mejor"]} · **Objetivo:** nivel de riesgo por comuna y franja de 3 horas '
                f'(Bajo = 0 incidentes, Medio = 1, Alto = 2 o más) · **Filas:** {info["filas"]:,} · '
                f'**Entrenamiento:** 2016-2024 · **Prueba:** 2025-2026 · **Datos leídos desde:** {info["origen"]}'
                .replace(',', '.'))
    izq, der = st.columns(2)
    with izq:
        tabla = pd.DataFrame(info['resultados']).T[['AUC', 'AUC_alguno']].astype(float)
        fig = go.Figure([go.Bar(name='AUC 3 niveles', x=tabla.index, y=tabla['AUC'], marker_color=MARCA,
                                text=[f'{v:.1f}' for v in tabla['AUC']], textposition='outside'),
                         go.Bar(name='AUC ¿pasa algo?', x=tabla.index, y=tabla['AUC_alguno'], marker_color=OCRE,
                                text=[f'{v:.1f}' for v in tabla['AUC_alguno']], textposition='outside')])
        estilo(fig, 300).update_layout(barmode='group', showlegend=True, legend=dict(orientation='h', y=1.15),
                                       title=dict(text='Comparación de algoritmos (AUC %, 50 = azar)', font=dict(size=14)))
        fig.update_yaxes(range=[50, 82])
        grafica(fig)
    with der:
        cal = r['calibracion']
        tope = max(cal['dijo']) * 1.1
        fig = go.Figure([go.Scatter(x=[0, tope], y=[0, tope], mode='lines', line=dict(color=LINEA, dash='dash'), name='Perfecto'),
                         go.Scatter(x=cal['dijo'], y=cal['paso'], mode='lines+markers', name='Halcón',
                                    line=dict(color=MARCA, width=3))])
        estilo(fig, 300).update_layout(showlegend=True, legend=dict(orientation='h', y=1.15),
                                       title=dict(text='Calibración: dijo % vs. pasó %', font=dict(size=14)))
        grafica(fig)
    izq, der = st.columns(2)
    with izq:
        m = r['matriz']
        fig = go.Figure(go.Heatmap(z=m, x=[f'Dijo {n.lower()}' for n in NIVELES], y=[f'Fue {n.lower()}' for n in NIVELES],
                                   text=m, texttemplate='%{text:,}', colorscale=[[0, CARTA], [1, MARCA]], showscale=False,
                                   xgap=3, ygap=3))
        fig.update_yaxes(autorange='reversed')
        estilo(fig, 300).update_layout(title=dict(text='Matriz de confusión (2025-2026)', font=dict(size=14)))
        grafica(fig)
    with der:
        imp = pd.Series(info['importancia']).sort_values()
        imp = imp[imp > 0.05]
        fig = go.Figure(go.Bar(x=imp.values, y=[NOMBRES_VARIABLES[c] for c in imp.index], orientation='h',
                               marker_color=MARCA, text=[f'{v:.1f}%' for v in imp.values], textposition='outside'))
        fig.update_xaxes(range=[0, imp.max() * 1.3])
        estilo(fig, 300).update_layout(title=dict(text='Importancia por permutación', font=dict(size=14)))
        grafica(fig)
    izq, der = st.columns(2)
    with izq:
        fig = go.Figure(go.Heatmap(z=reales['hora_dia'], x=[hora_corta(h) for h in range(24)],
                                   y=[d.capitalize() for d in DIAS], colorscale=[[0, CARTA], [0.5, '#E8C46F'], [1, '#9E2F25']],
                                   xgap=1, ygap=1, showscale=False))
        fig.update_yaxes(autorange='reversed')
        estilo(fig, 300).update_layout(title=dict(text='Incidentes reales por día y hora', font=dict(size=14)))
        grafica(fig)
    with der:
        anios = sorted(reales['por_anio'], key=int)
        fig = go.Figure([go.Bar(x=anios, y=[reales['por_anio'][a].get(t, 0) for a in anios], name=NOMBRE_TIPO[t],
                                marker_color=COLOR_TIPO[t]) for t in TIPOS_INCIDENTE])
        estilo(fig, 300).update_layout(barmode='stack', showlegend=True, legend=dict(orientation='h', y=1.15),
                                       title=dict(text='Incidentes por año (2026 hasta junio)', font=dict(size=14)))
        grafica(fig)
    st.markdown(
        '**Decisiones de limpieza.** En el dataset de delitos de la Policía la columna de comuna viene revuelta (el barrio '
        'Centro aparece repartido en cuatro comunas), así que cada hecho se ubica por su barrio usando el listado '
        'oficial de barrios y el dataset de coordenadas. Se excluyen los hechos ocurridos dentro de viviendas o '
        'cárceles, los registros sin barrio o rurales y las horas reportadas como 00:00 (casi siempre significan '
        '"sin hora"). Un hecho con varias víctimas cuenta una vez.\n\n'
        '**Limitaciones.** Se predice lo denunciado, no todo lo que pasa. No existen datos públicos de iluminación, '
        'cantidad de gente o tráfico calle por calle, ni de eventos; por eso los reportes de los vecinos se suman como '
        'un ajuste aparte. Bucaramanga no publica el estrato por barrio: se usa el porcentaje de población en régimen '
        'subsidiado de cada comuna.')


# ================================================================ ACERCA
def pagina_acerca():
    estado_barra(ahora())
    html('<div class="titular chico">Porque llegar rápido no sirve de nada si no llegas bien.</div>'
         '<div class="bajada">Todos usamos el GPS para ir a la universidad o al trabajo, pero ninguno nos dice que la '
         'zona tranquila de las 2 de la tarde puede ser otra un viernes a las 9 de la noche. Halcón cubre ese punto '
         'ciego con datos reales y abiertos.</div>')
    izq, der = st.columns(2, gap='large')
    with izq:
        seccion('De dónde salen los datos')
        fuentes = [('Información delictiva de Bucaramanga', 'Policía Nacional · Alcaldía', 'x46e-abhz'),
                   ('Delitos con coordenadas', 'Alcaldía de Bucaramanga', '75fz-q98y'),
                   ('Población por barrio', 'Alcaldía de Bucaramanga', 'kn95-8dei'),
                   ('Población en régimen subsidiado', 'Alcaldía de Bucaramanga', 'vgwf-uvjx')]
        html('<div class="carta">' + ''.join(
            f'<div class="consejo">{icono("dataset")}<div><b>{n}</b><br><span class="nota">{q} · '
            f'<a href="https://www.datos.gov.co/d/{i}" target="_blank">datos.gov.co</a></span></div></div>'
            for n, q, i in fuentes) +
            f'<div class="consejo">{icono("rainy")}<div><b>Clima hora por hora y pronóstico</b><br>'
            f'<span class="nota">Open-Meteo</span></div></div>'
            f'<div class="consejo">{icono("map")}<div><b>Calles para dibujar las rutas</b><br>'
            f'<span class="nota">OpenStreetMap</span></div></div></div>')
    with der:
        seccion('Cómo está hecho')
        html('<div class="carta">' + ''.join(f'<span class="chip">{t}</span>' for t in [
            'Python', 'pandas', 'scikit-learn', 'Gradient Boosting', 'Random Forest', 'Regresión logística',
            'Azure SQL', 'Streamlit', 'Plotly', 'API de datos.gov.co', 'Open-Meteo', 'OpenStreetMap']) + '</div>')
        seccion('Lo que viene')
        html('<div class="carta">Accidentes de la Secretaría de Movilidad, calendario de partidos del estadio, '
             'alertas cuando sube el riesgo de tu ruta diaria y más ciudades que publiquen sus datos por barrio y hora.</div>')
    pie_de_pagina()


# ================================================================ NAVEGACIÓN
PAGINA_INICIO = st.Page(pagina_inicio, title='Inicio', icon=':material/home:', default=True)
PAGINA_RUTA = st.Page(pagina_ruta, title='Mi ruta', icon=':material/route:', url_path='mi-ruta')
PAGINA_MAPA = st.Page(pagina_mapa, title='Mapa por horas', icon=':material/map:', url_path='mapa')
PAGINA_REPORTAR = st.Page(pagina_reportar, title='Reportar', icon=':material/campaign:', url_path='reportar')
PAGINA_FUNCIONA = st.Page(pagina_funciona, title='¿Funciona?', icon=':material/verified:', url_path='funciona')
PAGINA_ACERCA = st.Page(pagina_acerca, title='Acerca', icon=':material/info:', url_path='acerca')

st.navigation([PAGINA_INICIO, PAGINA_RUTA, PAGINA_MAPA, PAGINA_REPORTAR, PAGINA_FUNCIONA, PAGINA_ACERCA],
              position='top').run()
