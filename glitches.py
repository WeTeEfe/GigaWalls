"""Detecta fotogramas defectuosos que hacen parpadear el fondo al reproducirlo en bucle.

Muchos wallpapers se recortan mal en su origen: traen un fotograma «quemado» (blanco o de otra
escena) justo donde la animación original vuelve a empezar, o un fundido a negro al principio y al
final. Repetidos en bucle se ven como un destello cada vuelta. Aquí se localizan una sola vez por
video (ffmpeg a 32x18 en gris, es rápido) y el reproductor simplemente no los muestra: deja el
fotograma bueno anterior en pantalla. Los archivos no se modifican.
"""
import json
import os
import subprocess

import imageio_ffmpeg
import numpy as np

W, H = 32, 18
MAX_RUN = 12        # una racha defectuosa dura como mucho ~0,5 s
DARK = 4            # luminancia media por debajo de la cual un fotograma es «negro»


def _frames(path):
    """Fotogramas en gris a 32x18 (float32) y su duración en microsegundos."""
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", path, "-an", "-fps_mode", "passthrough",
           "-vf", f"scale={W}:{H}:flags=area,format=gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, timeout=300,
                         creationflags=subprocess.CREATE_NO_WINDOW).stdout
    n = len(raw) // (W * H)
    frames = np.frombuffer(raw[:n * W * H], np.uint8).reshape(n, H, W).astype(np.float32)
    return frames


def _fps(path):
    import cv2
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    cap.release()
    return fps


def bad_frames(frames):
    """Índices de los fotogramas a no mostrar (el video se considera circular, como en el bucle)."""
    n = len(frames)
    if n < 30:
        return []

    def diff(a, b):
        return float(np.abs(frames[a % n] - frames[b % n]).mean())

    steps = np.array([diff(i, i + 1) for i in range(n)])  # incluye el salto del final al principio
    typical = float(np.median(steps))
    jump = max(12.0, 8 * typical)  # cambio brusco: muy por encima del movimiento normal del video
    close = max(4.0, 3 * typical)  # «es la misma imagen»
    bad = set()
    # 1) Rachas cortas que saltan y vuelven: el fotograma de antes y el de después de la racha
    #    son casi iguales entre sí, y la racha no se parece a ninguno. Un corte de escena real no
    #    vuelve atrás, así que no se toca.
    i = 0
    while i < n + 1:
        prev = i - 1
        if steps[prev % n] > jump:
            for run in range(1, MAX_RUN + 1):
                # En la costura del bucle (donde el video se recortó) se tolera más diferencia
                seam = i % n == 0 or (i % n) + run >= n
                if diff(prev, i + run) < (close * 2 if seam else close):
                    bad.update((i + k) % n for k in range(run))
                    i += run
                    break
        i += 1
    # 2) Fundido a negro en los extremos de un video que no es oscuro.
    lum = frames.reshape(n, -1).mean(axis=1)
    if np.median(lum) > 20:
        for order in (range(n), range(n - 1, -1, -1)):
            for k in order:
                if lum[k] >= DARK:
                    break
                bad.add(k)
    return sorted(bad) if len(bad) < n // 4 else []  # algo raro: mejor no tocar nada


def analyze(path):
    """[(inicio_us, fin_us), ...] de los tramos que no se deben mostrar."""
    frames = _frames(path)
    fps = _fps(path)
    out = []
    for k in bad_frames(frames):
        t0, t1 = int(k * 1e6 / fps), int((k + 1) * 1e6 / fps)
        if out and out[-1][1] >= t0 - 1:
            out[-1][1] = t1
        else:
            out.append([t0, t1])
    return out


class Cache:
    """Resultados guardados en un JSON junto a la biblioteca (por ruta, tamaño y fecha)."""

    def __init__(self, file):
        self.file = file
        try:
            with open(file, encoding="utf-8") as f:
                self.data = json.load(f)
        except (OSError, ValueError):
            self.data = {}

    @staticmethod
    def _key(path):
        st = os.stat(path)
        return f"{os.path.normcase(os.path.abspath(path))}|{st.st_size}|{int(st.st_mtime)}"

    def get(self, path):
        try:
            return self.data.get(self._key(path))
        except OSError:
            return None

    def put(self, path, spans):
        try:
            self.data[self._key(path)] = spans
            os.makedirs(os.path.dirname(self.file), exist_ok=True)
            with open(self.file, "w", encoding="utf-8") as f:
                json.dump(self.data, f)
        except OSError:
            pass
