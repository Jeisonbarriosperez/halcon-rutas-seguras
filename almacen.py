"""
Dónde se guardan los reportes de la comunidad y las rutas consultadas: en Azure SQL.
Si Azure no responde (por ejemplo, mientras la base despierta), se guarda en datos/ para no perder el
reporte, se deja el motivo en el registro y se vuelve a intentar Azure al minuto.
"""
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

CARPETA = Path(__file__).parent / 'datos'
REPORTES_CSV = CARPETA / 'reportes.csv'
CONSULTAS_CSV = CARPETA / 'consultas.csv'

COLS_REPORTES = ['fecha', 'zona', 'tipo', 'comentario']
COLS_CONSULTAS = ['fecha', 'origen', 'destino', 'modo', 'hora_salida', 'clima', 'riesgo_habitual',
                  'riesgo_sugerida', 'hubo_desvio', 'minutos_extra']

REINTENTAR_CADA = 60          # segundos entre intentos cuando Azure no respondió
_estado = {'azure': None, 'revisado': 0.0}


def _registrar(texto):
    """Deja el motivo en el registro (en Streamlit Cloud: Manage app > logs)."""
    print(f'[Halcón · Azure SQL] {texto}', file=sys.stderr, flush=True)


def _conectar():
    from config import conectar
    return conectar()


def _marcar_caida(error):
    _estado['azure'], _estado['revisado'] = False, time.time()
    _registrar(f'sin conexión: {error!r}'[:400])


def azure_disponible():
    """Si la última revisión falló, vuelve a intentar pasado un minuto (nunca se rinde para siempre)."""
    if _estado['azure'] is True:
        return True
    if _estado['azure'] is False and time.time() - _estado['revisado'] < REINTENTAR_CADA:
        return False
    try:
        conn = _conectar()
        cursor = conn.cursor()
        cursor.execute('SELECT TOP 1 id FROM reportes_ciudadanos')
        cursor.fetchall()
        conn.close()
        if _estado['azure'] is not True:
            _registrar('conectado')
        _estado['azure'] = True
    except Exception as error:
        _marcar_caida(error)
    return _estado['azure']


def _insertar(tabla, columnas, valores):
    conn = _conectar()
    cursor = conn.cursor()
    cursor.execute(f'INSERT INTO {tabla} ({", ".join(columnas)}) VALUES ({", ".join(["%s"] * len(columnas))})',
                   tuple(valores))
    conn.commit()
    conn.close()


def _agregar_csv(archivo, columnas, valores):
    CARPETA.mkdir(exist_ok=True)
    fila = pd.DataFrame([dict(zip(columnas, valores))])
    fila.to_csv(archivo, mode='a', header=not archivo.exists(), index=False, encoding='utf-8')


def _guardar(tabla, archivo, columnas, valores):
    if azure_disponible():
        try:
            _insertar(tabla, columnas, valores)
            return 'Azure SQL'
        except Exception as error:
            _marcar_caida(error)
    _agregar_csv(archivo, columnas, valores)
    return 'respaldo'


def _leer(tabla, archivo, columnas, desde):
    if azure_disponible():
        try:
            conn = _conectar()
            cursor = conn.cursor()
            cursor.execute(f'SELECT {", ".join(columnas)} FROM {tabla} WHERE fecha >= %s ORDER BY fecha DESC',
                           (desde,))
            datos = pd.DataFrame(cursor.fetchall(), columns=columnas)
            conn.close()
            return datos
        except Exception as error:
            _marcar_caida(error)
    if not archivo.exists():
        return pd.DataFrame(columns=columnas)
    datos = pd.read_csv(archivo, parse_dates=['fecha'])
    return datos[datos['fecha'] >= desde].sort_values('fecha', ascending=False)


def guardar_reporte(fecha, zona, tipo, comentario=''):
    return _guardar('reportes_ciudadanos', REPORTES_CSV, COLS_REPORTES,
                    [fecha, zona, tipo, (comentario or '')[:200]])


def leer_reportes(desde):
    datos = _leer('reportes_ciudadanos', REPORTES_CSV, COLS_REPORTES, desde)
    datos['fecha'] = pd.to_datetime(datos['fecha'])
    datos['comentario'] = datos['comentario'].fillna('')
    return datos


def guardar_consulta(**campos):
    campos['fecha'] = campos.get('fecha') or datetime.now()
    return _guardar('consultas_rutas', CONSULTAS_CSV, COLS_CONSULTAS, [campos[c] for c in COLS_CONSULTAS])


def leer_consultas(desde):
    return _leer('consultas_rutas', CONSULTAS_CSV, COLS_CONSULTAS, desde)
