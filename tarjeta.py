"""
El logo de Halcón y la tarjeta para compartir el trayecto (imagen lista para WhatsApp o historias).
"""
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ciudad import ARISTAS, COMUNAS

TINTA = (28, 27, 25)
PAPEL = (245, 241, 232)
LINEA = (221, 212, 194)
TENUE = (107, 101, 90)
MARCA = (31, 78, 95)
OCRE = (196, 127, 44)
COLOR_NIVEL = {'Bajo': (76, 139, 90), 'Medio': (204, 145, 40), 'Alto': (184, 58, 46)}

# Silueta del halcón en vuelo (caja de 100 x 100). La mitad derecha; la izquierda es el espejo.
_DERECHA = [(50, 26), (54, 30), (56, 37), (66, 36), (80, 32), (97, 27), (85, 38), (71, 46), (60, 50),
            (57, 63), (61, 74), (50, 71)]
SILUETA = _DERECHA + [(100 - x, y) for x, y in reversed(_DERECHA[1:-1])]


def svg_logo(tamano=34, color='#1F4E5F'):
    puntos = ' '.join(f'{x},{y - 12}' for x, y in SILUETA)
    return (f'<svg width="{tamano}" height="{tamano * 0.7:.0f}" viewBox="0 0 100 70" xmlns="http://www.w3.org/2000/svg">'
            f'<polygon points="{puntos}" fill="{color}"/></svg>')


def _fuente(nombres, tamano):
    carpetas = [Path('C:/Windows/Fonts'), Path('/usr/share/fonts/truetype/dejavu'), Path('/Library/Fonts')]
    for nombre in nombres:
        for carpeta in carpetas:
            ruta = carpeta / nombre
            if ruta.exists():
                return ImageFont.truetype(str(ruta), tamano)
    return ImageFont.load_default(tamano)


def serif(t):
    return _fuente(['georgiab.ttf', 'DejaVuSerif-Bold.ttf', 'Georgia Bold.ttf'], t)


def sans(t, negrita=False):
    if negrita:
        return _fuente(['segoeuib.ttf', 'arialbd.ttf', 'DejaVuSans-Bold.ttf'], t)
    return _fuente(['segoeui.ttf', 'arial.ttf', 'DejaVuSans.ttf'], t)


def logo_png(ruta, tamano=256, color=MARCA, fondo=PAPEL):
    img = Image.new('RGB', (tamano, tamano), fondo)
    d = ImageDraw.Draw(img)
    esc = tamano / 100
    d.polygon([(x * esc, (y + 6) * esc) for x, y in SILUETA], fill=color)
    img.save(ruta)


def _envolver(draw, texto, fuente, ancho):
    lineas, actual = [], ''
    for palabra in texto.split():
        prueba = (actual + ' ' + palabra).strip()
        if draw.textlength(prueba, font=fuente) <= ancho:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


def tarjeta_trayecto(origen, destino, hora, modo, minutos, riesgo, nivel, calles, zonas_ruta, geometria=None):
    """Imagen 1080 x 1350 con el trayecto, para mandar a la familia o subir a historias."""
    W, H = 1080, 1350
    img = Image.new('RGB', (W, H), PAPEL)
    d = ImageDraw.Draw(img)
    m = 80

    # encabezado
    esc = 0.9
    d.polygon([(m + x * esc, 70 + y * esc) for x, y in SILUETA], fill=MARCA)
    d.text((m + 100, 88), 'HALCÓN', font=serif(46), fill=TINTA)
    d.text((W - m, 104), hora, font=sans(30), fill=TENUE, anchor='ra')
    d.line([(m, 170), (W - m, 170)], fill=LINEA, width=3)

    # título
    y = 210
    d.text((m, y), 'Voy en camino', font=sans(34, True), fill=OCRE)
    y += 60
    for linea in _envolver(d, f'De {origen} a {destino}', serif(72), W - 2 * m)[:3]:
        d.text((m, y), linea, font=serif(72), fill=TINTA)
        y += 88
    y += 10
    d.text((m, y), f'{modo} · llego en unos {minutos} minutos', font=sans(36), fill=TENUE)
    y += 80

    # mapa del trayecto
    caja = (m, y, W - m, y + 470)
    d.rounded_rectangle(caja, radius=28, fill=(255, 253, 248), outline=LINEA, width=3)
    lats = [z['lat'] for z in COMUNAS.values()] + (geometria['lat'] if geometria else [])
    lons = [z['lon'] for z in COMUNAS.values()] + (geometria['lon'] if geometria else [])
    pad = 50
    ancho_c, alto_c = caja[2] - caja[0] - 2 * pad, caja[3] - caja[1] - 2 * pad
    esc_m = min(ancho_c / ((max(lons) - min(lons)) * 0.992), alto_c / (max(lats) - min(lats)))   # sin deformar
    off_x = caja[0] + pad + (ancho_c - (max(lons) - min(lons)) * 0.992 * esc_m) / 2
    off_y = caja[3] - pad - (alto_c - (max(lats) - min(lats)) * esc_m) / 2

    def punto(lat, lon):
        return off_x + (lon - min(lons)) * 0.992 * esc_m, off_y - (lat - min(lats)) * esc_m

    def xy(cid):
        return punto(COMUNAS[cid]['lat'], COMUNAS[cid]['lon'])

    for a, b in ARISTAS:
        d.line([xy(a), xy(b)], fill=LINEA, width=5)
    for cid in COMUNAS:
        p = xy(cid)
        d.ellipse([p[0] - 7, p[1] - 7, p[0] + 7, p[1] + 7], fill=LINEA)
    if geometria:
        trazo = [punto(la, lo) for la, lo in zip(geometria['lat'], geometria['lon'])]
    else:
        trazo = [xy(z) for z in zonas_ruta]
    d.line(trazo, fill=MARCA, width=12, joint='curve')
    for p, color in ((trazo[0], TINTA), (trazo[-1], OCRE)):
        d.ellipse([p[0] - 20, p[1] - 20, p[0] + 20, p[1] + 20], fill=color, outline=(255, 253, 248), width=6)
    y = caja[3] + 40

    # riesgo y calles
    color = COLOR_NIVEL[nivel]
    etiqueta = f'Riesgo {nivel.lower()} · {riesgo:.0f}%'
    ancho = d.textlength(etiqueta, font=sans(36, True)) + 60
    d.rounded_rectangle((m, y, m + ancho, y + 70), radius=35, fill=color)
    d.text((m + 30, y + 35), etiqueta, font=sans(36, True), fill=(255, 255, 255), anchor='lm')
    y += 100
    for linea in _envolver(d, 'Por ' + ' → '.join(calles), sans(34), W - 2 * m)[:2]:
        d.text((m, y), linea, font=sans(34), fill=TINTA)
        y += 46

    # pie
    d.line([(m, H - 150), (W - m, H - 150)], fill=LINEA, width=3)
    d.text((m, H - 118), 'Si no te escribo al llegar, llámame.', font=serif(36), fill=TINTA)
    d.text((m, H - 66), 'Calcula tu ruta tranquila con Halcón', font=sans(28), fill=TENUE)

    salida = io.BytesIO()
    img.save(salida, format='PNG')
    return salida.getvalue()


def logo_marca_png(ruta, alto=120):
    """Logotipo horizontal (halcón + palabra) con fondo transparente, para la barra superior."""
    fuente = serif(int(alto * 0.62))
    ancho_texto = ImageDraw.Draw(Image.new('RGBA', (1, 1))).textlength('Halcón', font=fuente)
    esc = alto * 0.72 / 48                                  # el halcón ocupa el 72 % de la altura
    ancho_ave = 94 * esc
    ancho = int(ancho_ave + alto * 0.22 + ancho_texto + alto * 0.08)
    img = Image.new('RGBA', (ancho, alto), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([((x - 3) * esc, (y - 26) * esc + alto * 0.14) for x, y in SILUETA], fill=MARCA + (255,))
    d.text((ancho_ave + alto * 0.22, alto * 0.54), 'Halcón', font=fuente, fill=TINTA + (255,), anchor='lm')
    img.save(ruta)
