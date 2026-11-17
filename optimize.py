"""Procesado de video con ffmpeg: reducir a 1080p/30fps y reflejar."""
import os
import re
import subprocess
import time
import uuid

import cv2
import imageio_ffmpeg

# Perfiles: (alto máx., fps máx., Mbps máx., crf). El de ahorro gasta ~20 % menos GPU (medido).
NORMAL = (1080, 30, 10, 23)
ECO = (720, 24, 6, 24)
FLIPS = {"h": ("hflip", "-hflip"), "v": ("vflip", "-vflip")}  # modo: (filtro, sufijo del archivo)


def _tmp_name(path):
    """Nombre temporal unico: dos conversiones a la vez no se pisan el archivo."""
    return f"{path}.{uuid.uuid4().hex[:8]}.tmp.mp4"


def _replace(src, dest, retries=15):
    """os.replace con reintentos: Windows a veces tarda en soltar el archivo (antivirus, indexador,
    reproductor recien detenido)."""
    for attempt in range(retries):
        try:
            os.replace(src, dest)
            return
        except PermissionError:
            if attempt == retries - 1:
                os.remove(src)
                raise
            time.sleep(0.3)


def needs_optimizing(path, eco=False):
    """True si supera el perfil (resolución, fps o bitrate; un bitrate alto cuesta GPU aunque la
    resolución sea baja)."""
    max_h, max_fps, max_mbps, _ = ECO if eco else NORMAL
    cap = cv2.VideoCapture(path)
    height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    fps = cap.get(cv2.CAP_PROP_FPS)
    seconds = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps if fps else 0
    cap.release()
    mbps = os.path.getsize(path) * 8 / seconds / 1e6 if seconds else 0
    return height > max_h or fps > max_fps + 1 or mbps > max_mbps


def _encode(src, dest, vf, est_frames, progress, crf=23):
    """Recodifica src -> dest con el filtro vf. Borra dest si falla."""
    cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", src, "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", str(crf), "-pix_fmt", "yuv420p",
        "-an", "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", dest,
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    for line in proc.stdout:
        m = re.match(r"frame=(\d+)", line)
        if m and progress and est_frames:
            progress(min(int(m.group(1)), est_frames), est_frames)
    if proc.wait() != 0 or not os.path.exists(dest):
        if os.path.exists(dest):
            os.remove(dest)
        raise RuntimeError("ffmpeg no pudo convertir el video")


def _frame_count(path, fps=None):
    cap = cv2.VideoCapture(path)
    src_fps = max(cap.get(cv2.CAP_PROP_FPS), 1)
    n = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.release()
    return int(n / src_fps * fps) if fps else int(n)


def _profile_filter(eco):
    max_h, max_fps, _, crf = ECO if eco else NORMAL
    return f"scale=-2:'min({max_h},ih)',fps={max_fps}", max_fps, crf


def convert(path, progress=None, eco=False):
    """Convierte `path` al perfil en un archivo temporal, sin tocar el original (que puede seguir
    reproduciendose). Devuelve la ruta del temporal, o None si ya cumple el perfil."""
    if not needs_optimizing(path, eco):
        return None
    vf, max_fps, crf = _profile_filter(eco)
    tmp = _tmp_name(path)
    _encode(path, tmp, vf, _frame_count(path, max_fps), progress, crf=crf)
    return tmp


def replace(tmp, path):
    """Pone el resultado de convert() en lugar del original (con reintentos si Windows aun lo tiene
    abierto). Si no se puede, borra el temporal y lanza la excepcion."""
    _replace(tmp, path)


def optimize(path, progress=None, eco=False):
    """Recodifica `path` en el sitio. Devuelve True si lo convirtio."""
    tmp = convert(path, progress, eco)
    if not tmp:
        return False
    _replace(tmp, path)
    return True


def normalize(path, progress=None, eco=False):
    """Deja un video importado listo para usarse de fondo: .mp4 y dentro del perfil.

    Un archivo en otro formato (.webm, .mkv, .mov...) siempre se convierte a .mp4 y el original se
    borra. Devuelve la ruta final.
    """
    root, ext = os.path.splitext(path)
    if ext.lower() == ".mp4":
        optimize(path, progress, eco)
        return path
    out, n = root + ".mp4", 2
    while os.path.exists(out):
        out, n = f"{root} ({n}).mp4", n + 1
    vf, max_fps, crf = _profile_filter(eco)
    tmp = _tmp_name(out)
    _encode(path, tmp, vf, _frame_count(path, max_fps), progress, crf=crf)
    _replace(tmp, out)
    os.remove(path)
    return out


def flipped_name(path, modes):
    """Nombre del video reflejado con `modes` ('h', 'v' o 'hv'): nombre-hflip.mp4, nombre-hflip-vflip.mp4..."""
    root, ext = os.path.splitext(path)
    return root + "".join(FLIPS[m][1] for m in modes) + ext


def optimize_flipped(path, modes, progress=None, eco=False):
    """Deja un video recien descargado reflejado (y dentro del perfil) en una sola conversion.
    Crea el archivo con sufijo (-hflip / -vflip), borra el original y devuelve la ruta nueva."""
    filters = [FLIPS[m][0] for m in modes]
    if needs_optimizing(path, eco):
        vf, max_fps, crf = _profile_filter(eco)
        filters.insert(0, vf)
        frames = _frame_count(path, max_fps)
    else:
        crf, frames = 20, _frame_count(path)
    out = flipped_name(path, modes)
    tmp = _tmp_name(out)
    _encode(path, tmp, ",".join(filters), frames, progress, crf=crf)
    _replace(tmp, out)
    os.remove(path)
    return out


def flip(path, mode, progress=None):
    """Crea (o reutiliza) una copia reflejada de `path`. mode: 'h' (izq<->der) o 'v' (arriba<->abajo).

    Reflejar una copia ya reflejada con el mismo modo vuelve al original.
    Devuelve la ruta del video resultante.
    """
    filt, suffix = FLIPS[mode]
    root, ext = os.path.splitext(path)
    out = root[:-len(suffix)] + ext if root.endswith(suffix) else root + suffix + ext
    if os.path.exists(out):
        return out
    tmp = _tmp_name(out)
    _encode(path, tmp, filt, _frame_count(path), progress, crf=20)
    _replace(tmp, out)
    return out
