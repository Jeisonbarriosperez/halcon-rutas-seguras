-- 1. Las 17 comunas urbanas
IF OBJECT_ID('comunas', 'U') IS NULL
CREATE TABLE comunas (
    comuna_id INT PRIMARY KEY,
    nombre NVARCHAR(40),
    lat FLOAT,                         -- centro calculado con las coordenadas reales de los hechos
    lon FLOAT,
    poblacion INT,                     -- proyección Alcaldía (dataset kn95-8dei)
    pct_subsidiado DECIMAL(5,1)        -- % de población en régimen subsidiado (vgwf-uvjx)
);

-- 2. Barrios con coordenadas reales
IF OBJECT_ID('barrios', 'U') IS NULL
CREATE TABLE barrios (
    id INT IDENTITY(1,1) PRIMARY KEY,
    barrio NVARCHAR(80),
    comuna_id INT,
    lat FLOAT,
    lon FLOAT,
    incidentes INT
);

-- 3. Cada incidente en la calle (Policía Nacional - Alcaldía, dataset x46e-abhz)
IF OBJECT_ID('incidentes', 'U') IS NULL
CREATE TABLE incidentes (
    id INT IDENTITY(1,1) PRIMARY KEY,
    fecha_hora DATETIME2,
    hora_conocida INT,                 -- 0 cuando la hora venía como 00:00 (sin hora)
    tipo NVARCHAR(20),                 -- hurto, violencia, accidente
    delito NVARCHAR(80),
    comuna_id INT,                     -- sacada del barrio (la columna original viene revuelta)
    barrio NVARCHAR(80),
    sitio NVARCHAR(80),
    movil_victima NVARCHAR(60)
);

-- 4. Clima de cada hora desde 2016 (Open-Meteo)
IF OBJECT_ID('clima_horario', 'U') IS NULL
CREATE TABLE clima_horario (
    fecha_hora DATETIME2 PRIMARY KEY,
    temperatura DECIMAL(4,1),
    lluvia_mm DECIMAL(5,1),
    codigo_clima INT
);

-- 5. Lo que reporta la comunidad desde la app (zona = número de la comuna)
IF OBJECT_ID('reportes_ciudadanos', 'U') IS NULL
CREATE TABLE reportes_ciudadanos (
    id INT IDENTITY(1,1) PRIMARY KEY,
    fecha DATETIME2 NOT NULL,
    zona NVARCHAR(40) NOT NULL,
    tipo NVARCHAR(30) NOT NULL,
    comentario NVARCHAR(200)
);

-- 6. Cada ruta que alguien consulta
IF OBJECT_ID('consultas_rutas', 'U') IS NULL
CREATE TABLE consultas_rutas (
    id INT IDENTITY(1,1) PRIMARY KEY,
    fecha DATETIME2 NOT NULL,
    origen NVARCHAR(40),
    destino NVARCHAR(40),
    modo NVARCHAR(20),
    hora_salida DATETIME2,
    clima NVARCHAR(20),
    riesgo_habitual DECIMAL(5,1),
    riesgo_sugerida DECIMAL(5,1),
    hubo_desvio INT,
    minutos_extra INT
);
