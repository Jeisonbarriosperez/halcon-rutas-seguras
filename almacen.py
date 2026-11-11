"""
Dónde se guardan los reportes de la comunidad y las rutas consultadas.
Si hay conexión con Azure SQL se usa Azure; si no, un CSV en la carpeta datos/ (la app nunca se cae).
"""
from datetime import datetime
from pathlib import Path

import pandas as pd

CARPETA = Path(__file__).parent / 'datos'
REPORTES_CSV = CARPETA / 'reportes.csv'
CONSULTAS_CSV = CARPETA / 'consultas.csv'

COLS_REPORTES = ['fecha', 'zona', 'tipo', 'comentario']
COLS_CONSULTAS = ['fecha', 'origen', 'destino', 'modo', 'hora_salida', 'clima', 'riesgo_habitual',
                  'riesgo_sugerida', 'hubo_desvio', 'minutos_extra']

_estado = {'azure': None}


def _conectar():
    from config import conectar
    return conectar()


def azure_disponible():
    """Se revisa una sola vez: si las tablas de Halcón existen en Azure, se trabaja allá."""
    if _estado['azure'] is None:
        try:
            conn = _conectar()
            cursor = conn.cursor()
            cursor.execute('SELECT TOP 1 id FROM reportes_ciudadanos')
            cursor.fetchall()
            conn.close()
            _estado['azure'] = True
        except Exception:
            _estado['azure'] = False
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
        except Exception:
            pass
    _agregar_csv(archivo, columnas, valores)
    return 'archivo local'


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
        except Exception:
            pass
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
