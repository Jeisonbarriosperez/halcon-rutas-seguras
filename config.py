"""
Conexión a Azure SQL.
Las credenciales NO están aquí: se leen de .streamlit/secrets.toml (que no se sube a GitHub),
de los Secrets de Streamlit Cloud o de variables de entorno AZURE_SERVER, AZURE_DATABASE, AZURE_USER, AZURE_PASSWORD.
"""
import os
import tomllib
from pathlib import Path

import certifi
import pytds

SECRETOS = Path(__file__).parent / '.streamlit' / 'secrets.toml'


def credenciales():
    if SECRETOS.exists():
        with open(SECRETOS, 'rb') as archivo:
            azure = tomllib.load(archivo).get('azure', {})
        if azure:
            return azure['server'], azure['database'], azure['username'], azure['password']
    try:
        import streamlit as st
        azure = st.secrets['azure']
        return azure['server'], azure['database'], azure['username'], azure['password']
    except Exception:
        pass
    try:
        return (os.environ['AZURE_SERVER'], os.environ['AZURE_DATABASE'], os.environ['AZURE_USER'],
                os.environ['AZURE_PASSWORD'])
    except KeyError:
        raise RuntimeError('Faltan las credenciales de Azure: crea .streamlit/secrets.toml '
                           '(copia .streamlit/secrets.example.toml)') from None


def conectar():
    servidor, base, usuario, clave = credenciales()
    return pytds.connect(servidor, base, usuario, clave, cafile=certifi.where(), validate_host=False,
                         login_timeout=30)
