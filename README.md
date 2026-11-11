# Halcón · la ruta más tranquila, no solo la más rápida

El GPS te dice por dónde llegas antes. Halcón te dice por dónde llegas **mejor**.

Predice, para cada una de las 17 comunas de **Bucaramanga** y para cada franja de 3 horas, si el riesgo de que
se denuncie un robo, una riña o un accidente con heridos es **Bajo, Medio o Alto**. Con eso compara tu ruta de
siempre con una más tranquila y te avisa antes de que entres a una zona complicada.

**Todo con datos reales y abiertos.** No hay nada simulado.

## Fuentes

| Dato | Fuente |
|---|---|
| 80.000+ incidentes en la calle (2016 → junio 2026) con fecha, hora y barrio | Policía Nacional · Alcaldía de Bucaramanga, datos.gov.co `x46e-abhz` |
| Coordenadas de los barrios y relación barrio → comuna | datos.gov.co `75fz-q98y` (135.000 hechos georreferenciados) |
| Población por barrio y comuna | datos.gov.co `kn95-8dei` |
| Población en régimen subsidiado (en lugar del estrato, que no se publica) | datos.gov.co `vgwf-uvjx` |
| Lluvia y temperatura de cada hora desde 2016, y pronóstico | Open-Meteo |
| Festivos y quincenas | Calendario oficial de Colombia (Ley Emiliani), calculado en `ciudad.py` |
| Calles para dibujar las rutas | OpenStreetMap (OSRM) |

## Cómo ejecutarlo

1. Instala las librerías:
   ```
   python -m pip install -r requirements.txt
   ```
2. Copia `.streamlit/secrets.example.toml` como `.streamlit/secrets.toml` y pon tus datos de Azure SQL.
   Ese archivo nunca se sube a GitHub (está en `.gitignore`).
3. Corre el flujo de datos (solo la primera vez o cuando quieras actualizar):
   ```
   python 1_descargar_datos.py      # baja todo de datos.gov.co y Open-Meteo
   python 2_limpiar_y_cargar.py     # limpia y sube a Azure SQL (crea las tablas que falten)
   python 3_entrenar_modelo.py      # lee desde Azure, compara 3 modelos y guarda el ganador en modelo/
   ```
4. Abre la app:
   ```
   python -m streamlit run app.py
   ```

El modelo ya entrenado viene en la carpeta `modelo/`, así que la app funciona con solo el paso 4.

### Publicarla en Streamlit Cloud

Sube el repositorio, crea la app apuntando a `app.py` y, en **Settings > Secrets**, pega el contenido de tu
`.streamlit/secrets.toml`.

## La app

| Sección | Para qué sirve |
|---|---|
| **Inicio** | Buscas tu ruta en un paso y ves cómo está la ciudad ahora y en las próximas horas |
| **Mi ruta** | Veredicto claro, ruta habitual vs. sugerida sobre calles reales, mejor hora para salir, consejos y compartir por WhatsApp |
| **Mapa por horas** | Cómo cambia cada comuna según el día, la hora y la lluvia |
| **Reportar** | Los vecinos reportan robos, riñas o alumbrado dañado y el mapa cambia al instante |
| **¿Funciona?** | La prueba: lo que Halcón predijo para días reales de 2025-2026 (que nunca vio) contra lo que de verdad pasó |
| **Acerca** | Fuentes y tecnología |

## El modelo

- **Unidad:** una comuna en una franja de 3 horas de un día concreto (521.424 filas).
- **Objetivo (Target):** Bajo = 0 incidentes, Medio = 1, Alto = 2 o más.
- **Variables:** comuna, % en régimen subsidiado, franja horaria, día de la semana, mes, año, festivo, puente,
  quincena, confinamiento 2020, lluvia en la franja, lluvia en la franja anterior y temperatura.
- **Validación honesta:** entrena con 2016-2024 y se prueba con 2025-2026. Compara Regresión Logística, Random
  Forest y Gradient Boosting, y se queda con el de mejor AUC.

### Resultados en 2025-2026 (datos que el modelo nunca vio)

| Indicador | Resultado |
|---|---|
| Ganador | Gradient Boosting (AUC 76,6 %; Random Forest 76,3 %; Regresión Logística 74,9 %) |
| Incidentes atrapados por las franjas marcadas en rojo (12 % del tiempo) | **36 %**: 3 veces más que marcando al azar |
| La comuna que Halcón pone de primera tuvo incidentes | **29 %** de las veces (una comuna cualquiera: 11 %) |
- **Lo que ve la persona:** la probabilidad de que pase al menos un incidente en esas 3 horas. "Alto" es el 12 %
  de las franjas más complicadas de la ciudad.

## Decisiones de limpieza (y por qué)

- **La comuna se saca del barrio.** En `x46e-abhz` la columna de comuna viene revuelta: el barrio Centro aparece
  repartido casi por igual en 4 comunas. El barrio sí es confiable (coincide en fecha y barrio con el otro
  dataset en el 82 % de los casos, frente al 42 % que daría el azar).
- **Hora 00:00 = sin hora.** Hay casi el triple de casos a las 00:00 que a las 00:30.
- **Solo hechos en la calle.** Se quitan los ocurridos en casas, apartamentos, cárceles, etc., y la violencia
  intrafamiliar y los delitos sexuales contra menores, que no dependen de la ruta.
- **Un hecho con varias víctimas cuenta una vez.**
- **Subsidiado en el Centro topado en 100 %** (hay más afiliados registrados que habitantes).

## Lo que no existe como dato público

La iluminación, la cantidad de gente en la calle y el tráfico calle por calle, y un calendario de eventos.
Por eso los **reportes de los vecinos** (robo, alumbrado dañado, riña…) se suman como un ajuste aparte y visible.

## Archivos

| Archivo | Para qué sirve |
|---|---|
| `1_descargar_datos.py` | Descarga de las fuentes oficiales |
| `2_limpiar_y_cargar.py` | Limpieza y carga a Azure SQL |
| `3_entrenar_modelo.py` | Entrenamiento, validación y datos para las gráficas |
| `ciudad.py` | Comunas, barrios, conexiones y festivos |
| `halcon.py` | Lógica compartida: variables, predicción, rutas, explicaciones y clima en vivo |
| `almacen.py` | Guarda los reportes y las consultas en Azure SQL |
| `tarjeta.py` | Logo y tarjeta para compartir el trayecto |
| `app.py` | La aplicación web |
| `config.py` | Conexión a Azure SQL (lee las credenciales de `.streamlit/secrets.toml`) |
