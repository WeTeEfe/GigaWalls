"""Traduce al inglés lo que se escribe en el buscador: los sitios de wallpapers solo entienden inglés.

Usa un diccionario propio con el vocabulario típico de fondos: instantáneo, sin internet y sin
sorpresas. Las palabras que no están se dejan tal cual: casi siempre son nombres (Naruto, Goku,
Minecraft) o ya están en inglés. No se usa un traductor en línea a propósito: probado con MyMemory,
cambia "car" por "cart", "corazón" por "core", "jardín" por "front yard"... y lo devuelve con
confianza 0.99, así que no hay forma de filtrar los errores. Para ampliar, agregar entradas abajo.
"""
import unicodedata

# Palabras que no aportan a la búsqueda (conectores) o que todos los resultados ya cumplen.
STOP = {
    "de", "del", "la", "el", "lo", "los", "las", "en", "con", "y", "e", "o", "u", "un", "una", "unos",
    "unas", "por", "para", "a", "al", "sobre", "entre", "su", "sus", "mi", "que", "muy", "sin",
}
META = {"fondo", "fondos", "pantalla", "escritorio", "animado", "animados", "animada", "animadas",
        "vivo", "movimiento", "video", "videos", "wallpaper", "wallpapers", "hd", "4k"}

# Expresiones de varias palabras (sin tildes, en minúsculas). Se buscan antes que las palabras sueltas.
PHRASES = {
    "pixel art": "pixel art", "arte pixel": "pixel art", "ciencia ficcion": "sci-fi",
    "agujero negro": "black hole", "via lactea": "milky way", "fuegos artificiales": "fireworks",
    "flor de cerezo": "cherry blossom", "flores de cerezo": "cherry blossom", "cerezo en flor": "cherry blossom",
    "cerezos en flor": "cherry blossom", "estrella fugaz": "shooting star", "estrellas fugaces": "shooting stars",
    "aurora boreal": "aurora", "luna llena": "full moon", "luna roja": "red moon", "hora dorada": "golden hour",
    "puesta de sol": "sunset", "salida del sol": "sunrise", "cielo estrellado": "starry sky",
    "dia de muertos": "day of the dead", "noche estrellada": "starry night", "fondo marino": "underwater",
    "bajo el agua": "underwater", "bajo la lluvia": "rain", "rayo de luz": "light ray",
    "de noche": "night", "de dia": "day", "chica anime": "anime girl", "chico anime": "anime boy",
    "tormenta electrica": "thunderstorm", "caballeros del zodiaco": "saint seiya", "nave espacial": "spaceship", "lago helado": "frozen lake",
    "estacion de tren": "train station", "lluvia de estrellas": "meteor shower",
}

# Sustantivos y otras palabras sueltas (claves sin tildes, en singular).
WORDS = {
    # naturaleza y paisajes
    "paisaje": "landscape", "naturaleza": "nature", "montana": "mountain", "bosque": "forest",
    "selva": "jungle", "arbol": "tree", "flor": "flower", "hoja": "leaf", "rio": "river", "lago": "lake",
    "mar": "sea", "oceano": "ocean", "playa": "beach", "ola": "wave", "isla": "island", "desierto": "desert",
    "cascada": "waterfall", "cielo": "sky", "nube": "cloud", "sol": "sun", "luna": "moon", "estrella": "star",
    "planeta": "planet", "galaxia": "galaxy", "espacio": "space", "universo": "universe", "cometa": "comet",
    "nebulosa": "nebula", "tierra": "earth", "campo": "field", "pradera": "meadow", "jardin": "garden",
    "cueva": "cave", "volcan": "volcano", "valle": "valley", "colina": "hill", "acantilado": "cliff",
    "hierba": "grass", "pasto": "grass", "sakura": "sakura", "cerezo": "cherry blossom", "otono": "autumn",
    "invierno": "winter", "verano": "summer", "primavera": "spring", "estacion": "station",
    # clima y momentos del día
    "lluvia": "rain", "nieve": "snow", "tormenta": "storm", "rayo": "lightning",
    "relampago": "lightning", "niebla": "fog", "neblina": "mist", "viento": "wind", "arcoiris": "rainbow",
    "atardecer": "sunset", "amanecer": "sunrise", "anochecer": "dusk", "ocaso": "sunset", "noche": "night",
    "dia": "day", "tarde": "evening", "manana": "morning", "medianoche": "midnight", "crepusculo": "twilight",
    # ciudad y lugares
    "ciudad": "city", "calle": "street", "edificio": "building", "rascacielos": "skyscraper",
    "puente": "bridge", "tren": "train", "casa": "house",
    "habitacion": "room", "cuarto": "room", "cafeteria": "cafe", "cafe": "cafe", "tienda": "shop",
    "castillo": "castle", "templo": "temple", "pueblo": "village", "aldea": "village", "ventana": "window",
    "techo": "rooftop", "azotea": "rooftop", "carretera": "road", "camino": "road", "faro": "lighthouse",
    "biblioteca": "library", "escuela": "school", "neon": "neon", "luces": "lights", "luz": "light",
    "farola": "street lamp", "japon": "japan", "tokio": "tokyo",
    # vehículos
    "coche": "car", "carro": "car", "auto": "car", "automovil": "car", "moto": "motorcycle",
    "motocicleta": "motorcycle", "bicicleta": "bicycle", "avion": "plane", "barco": "ship", "nave": "ship",
    "camion": "truck", "cohete": "rocket", "tranvia": "tram", "carrera": "racing",
    # animales
    "gato": "cat", "gatito": "kitten", "perro": "dog", "cachorro": "puppy", "lobo": "wolf", "zorro": "fox",
    "tigre": "tiger", "leon": "lion", "oso": "bear", "pajaro": "bird", "ave": "bird", "aguila": "eagle",
    "buho": "owl", "cuervo": "crow", "pez": "fish", "peces": "fish", "ballena": "whale", "tiburon": "shark",
    "medusa": "jellyfish", "mariposa": "butterfly", "caballo": "horse", "conejo": "rabbit", "dragon": "dragon",
    "serpiente": "snake", "panda": "panda", "koi": "koi", "ciervo": "deer", "venado": "deer",
    "fenix": "phoenix", "unicornio": "unicorn",
    # personas y personajes
    "chica": "girl", "nina": "girl", "mujer": "woman", "chico": "boy", "nino": "boy", "hombre": "man",
    "guerrero": "warrior", "guerrera": "warrior", "samurai": "samurai", "ninja": "ninja", "caballero": "knight",
    "mago": "wizard", "bruja": "witch", "princesa": "princess", "rey": "king", "reina": "queen",
    "angel": "angel", "demonio": "demon", "diablo": "devil", "robot": "robot", "astronauta": "astronaut",
    "pareja": "couple", "heroe": "hero", "villano": "villain", "fantasma": "ghost", "calavera": "skull",
    "esqueleto": "skeleton", "monstruo": "monster", "zombi": "zombie", "vampiro": "vampire",
    "superheroe": "superhero", "soldado": "soldier", "piloto": "pilot", "personaje": "character",
    # temas y estilos
    "juego": "game", "videojuego": "game", "pelicula": "movie",
    "pinguino": "penguin", "murcielago": "bat", "piramide": "pyramid", "canon": "canyon",
    "senal": "sign", "jirafa": "giraffe", "elefante": "elephant", "mono": "monkey", "rana": "frog",
    "tortuga": "turtle", "pulpo": "octopus", "abeja": "bee", "arana": "spider", "hongo": "mushroom",
    "seta": "mushroom", "luciernaga": "firefly", "ruinas": "ruins", "torre": "tower", "molino": "windmill",
    "barrio": "neighborhood", "mercado": "market", "metro": "subway", "parque": "park", "piscina": "pool",
    "taller": "garage", "garaje": "garage", "escalera": "stairs", "balcon": "balcony", "vino": "wine",
    "cerveza": "beer", "glaciar": "glacier", "trigo": "wheat",
    "girasol": "sunflower", "rosas": "roses", "loto": "lotus", "bambu": "bamboo", "pino": "pine",
    "palmera": "palm tree", "cactus": "cactus", "eclipse": "eclipse", "meteorito": "meteor",
    "satelite": "satellite", "pirata": "pirate", "vaquero": "cowboy", "policia": "police", "detective": "detective",
    "mecha": "mecha", "tanque": "tank", "helicoptero": "helicopter", "peliculas": "movie", "serie": "series", "dibujo": "cartoon",
    "dibujos": "cartoon", "caricatura": "cartoon", "arte": "art", "abstracto": "abstract",
    "fantasia": "fantasy", "musica": "music", "guitarra": "guitar", "deporte": "sport", "futbol": "football",
    "espada": "sword", "fuego": "fire", "agua": "water", "hielo": "ice", "humo": "smoke", "sangre": "blood",
    "corazon": "heart", "amor": "love", "paz": "peace", "guerra": "war", "batalla": "battle",
    "magia": "magic", "tecnologia": "technology", "codigo": "code", "computadora": "computer",
    "ordenador": "computer", "minimalista": "minimalist", "minimalismo": "minimalist", "retro": "retro",
    "navidad": "christmas", "halloween": "halloween", "terror": "horror", "miedo": "horror",
    "geometrico": "geometric", "particulas": "particles", "particula": "particles", "cristal": "crystal",
    "ojos": "eyes", "ojo": "eye", "cara": "face", "mascara": "mask",
    "lampara": "lamp", "vela": "candle", "libro": "book", "comida": "food", "ramen": "ramen",
    "estudio": "study",
}

# Adjetivos: en inglés van delante del sustantivo ("coche rojo" -> "red car").
ADJECTIVES = {
    "rojo": "red", "azul": "blue", "verde": "green", "amarillo": "yellow", "negro": "black",
    "blanco": "white", "morado": "purple", "purpura": "purple", "violeta": "violet", "rosa": "pink",
    "rosado": "pink", "naranja": "orange", "gris": "gray", "dorado": "golden", "plateado": "silver",
    "oscuro": "dark", "claro": "light", "brillante": "bright", "colorido": "colorful", "nevado": "snowy",
    "lluvioso": "rainy", "nublado": "cloudy", "soleado": "sunny", "estrellado": "starry",
    "nocturno": "night", "antiguo": "ancient", "viejo": "old", "nuevo": "new", "grande": "big",
    "pequeno": "small", "gigante": "giant", "bonito": "beautiful", "hermoso": "beautiful",
    "lindo": "cute", "tierno": "cute", "triste": "sad", "solitario": "lonely", "solo": "alone",
    "epico": "epic", "misterioso": "mysterious", "magico": "magic", "mistico": "mystic",
    "futurista": "futuristic", "japones": "japanese", "chino": "chinese", "espacial": "space",
    "submarino": "underwater", "tropical": "tropical", "frio": "cold", "caliente": "hot",
    "salvaje": "wild", "sombrio": "dark", "deportivo": "sports", "electrico": "electric",
    "acogedor": "cozy", "relajante": "relaxing", "tranquilo": "calm", "montanoso": "mountain", "otonal": "autumn", "invernal": "winter",
    "helado": "frozen", "congelado": "frozen", "brumoso": "misty", "neblinoso": "foggy",
    "luminoso": "glowing", "radiante": "radiant", "silencioso": "quiet", "pacifico": "peaceful",
    "abandonado": "abandoned", "encantado": "haunted", "embrujado": "haunted", "celestial": "celestial",
    "cosmico": "cosmic", "urbano": "urban", "rural": "rural", "lejano": "distant", "infinito": "infinite",
}

_query_cache = {}  # búsqueda -> búsqueda en inglés (las páginas 2, 3... no vuelven a traducir)


def _plain(word):
    """minúsculas y sin tildes (la ñ pasa a n): así 'Montaña' y 'montana' encuentran la misma entrada."""
    word = unicodedata.normalize("NFD", word.lower())
    return "".join(c for c in word if unicodedata.category(c) != "Mn")


def _variants(key):
    """La palabra y sus formas en singular / masculino: 'gatos' -> 'gato', 'rojas' -> 'rojo'."""
    out = [key]
    if key.endswith("es") and len(key) > 4:
        out.append(key[:-2])
    if key.endswith("s") and len(key) > 3:
        out.append(key[:-1])
    for k in list(out):
        if k.endswith("ora") and len(k) > 4:  # acogedora -> acogedor
            out.append(k[:-1])
        elif k.endswith("a") and len(k) > 3:  # roja -> rojo
            out.append(k[:-1] + "o")
    return out


def _lookup(key):
    """(traducción, es_adjetivo) o (None, False) si no está en el diccionario."""
    for k in _variants(key):
        if k in WORDS:
            return WORDS[k], False
        if k in ADJECTIVES:
            return ADJECTIVES[k], True
    return None, False


def to_english(query):
    """Devuelve la búsqueda en inglés. Si no hay nada que traducir, devuelve `query` tal cual."""
    if query in _query_cache:
        return _query_cache[query]
    original = query.split()
    keys = [_plain(w) for w in original]
    out = []  # [(texto, es_sustantivo)]
    changed = False
    i = 0
    while i < len(keys):
        for n in (3, 2):  # expresiones de varias palabras primero
            phrase = " ".join(keys[i:i + n])
            if len(keys[i:i + n]) == n and phrase in PHRASES:
                out.append((PHRASES[phrase], True))
                changed = True
                i += n
                break
        else:
            word, key = original[i], keys[i]
            i += 1
            if key in STOP or key in META:
                changed = True
                continue
            text, is_adj = _lookup(key)
            if text is None or text == key:  # nombre propio, ya en inglés o igual en ambos (dragon, panda)
                out.append((word, True))
                continue
            changed = True
            if is_adj and out and out[-1][1]:
                out.insert(len(out) - 1, (text, False))  # "coche rojo" -> "red car"
            else:
                out.append((text, not is_adj))
    result = " ".join(t for t, _ in out) if changed else query
    _query_cache[query] = result
    return result
