"""Utilidades de la biblioteca de videos: listado, espacio usado, favoritos, duplicados y rotación."""
import hashlib
import os
import random

VIDEO_EXTS = (".mp4", ".webm", ".mkv", ".mov", ".avi", ".m4v")
FLIP_SUFFIXES = ("-hflip", "-vflip")


def videos(folder):
    """Rutas de los videos de la carpeta (sin los ocultos ni los temporales de conversión)."""
    if not os.path.isdir(folder):
        return []
    return sorted(
        os.path.join(folder, n) for n in os.listdir(folder)
        if n.lower().endswith(VIDEO_EXTS) and not n.startswith(".") and ".tmp." not in n)


def total_size(paths):
    return sum(os.path.getsize(p) for p in paths if os.path.exists(p))


def human(nbytes):
    if nbytes >= 1 << 30:
        return f"{nbytes / (1 << 30):.1f} GB"
    return f"{nbytes / (1 << 20):.0f} MB" if nbytes >= 1 << 20 else f"{nbytes / 1024:.0f} KB"


def display_name(path):
    return os.path.splitext(os.path.basename(path))[0].replace("-", " ").title()


def is_flipped(path):
    return os.path.splitext(path)[0].endswith(FLIP_SUFFIXES)


def _sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def duplicate_groups(paths):
    """Grupos de archivos con contenido idéntico. Solo se calcula el hash entre los del mismo tamaño."""
    by_size = {}
    for p in paths:
        by_size.setdefault(os.path.getsize(p), []).append(p)
    groups = []
    for same_size in by_size.values():
        if len(same_size) < 2:
            continue
        by_hash = {}
        for p in same_size:
            by_hash.setdefault(_sha1(p), []).append(p)
        groups.extend(g for g in by_hash.values() if len(g) > 1)
    return groups


def cleanup_candidates(paths, keep=()):
    """Archivos que se pueden borrar sin perder contenido propio: [(ruta, motivo)].

    - Reflejados (-hflip / -vflip): se pueden volver a generar desde el original.
    - Duplicados exactos: se conserva uno (prefiere los protegidos y el de nombre más corto).
    Nunca incluye los de `keep` (fondo actual y favoritos).
    """
    keep = set(keep)
    out, marked = [], set()
    for p in paths:
        if is_flipped(p) and p not in keep:
            out.append((p, "reflejado (se puede volver a generar)"))
            marked.add(p)
    for group in duplicate_groups([p for p in paths if p not in marked]):
        best = min(group, key=lambda p: (p not in keep, len(os.path.basename(p)), p))
        for p in group:
            if p != best and p not in keep:
                out.append((p, f"duplicado de {os.path.basename(best)}"))
    return sorted(out)


def rotation_pool(all_paths, favorites):
    """Entre qué videos rotar: tus favoritos si tienes 2 o más; si no, toda la biblioteca."""
    favs = [p for p in all_paths if os.path.basename(p) in set(favorites)]
    return favs if len(favs) >= 2 else list(all_paths)


def pick_next(all_paths, favorites, current=None):
    """Video al azar del conjunto de rotación, distinto del actual si hay más de uno."""
    pool = rotation_pool(all_paths, favorites)
    options = [p for p in pool if p != current] or pool
    return random.choice(options) if options else None


def unique_dest(folder, filename):
    """Ruta libre dentro de `folder`: agrega ' (2)', ' (3)'... si el nombre ya existe."""
    root, ext = os.path.splitext(filename)
    dest, n = os.path.join(folder, filename), 2
    while os.path.exists(dest):
        dest, n = os.path.join(folder, f"{root} ({n}){ext}"), n + 1
    return dest
