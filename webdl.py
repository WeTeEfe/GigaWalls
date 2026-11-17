"""Piezas comunes de los clientes de sitios de wallpapers: sesión HTTP y descarga con progreso."""
import os

import requests

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def session(base):
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Referer": base + "/"})
    return s


def save(s, url, dest, referer=None):
    """Descarga un archivo pequeño (vista previa) entero a `dest`."""
    r = s.get(url, headers={"Referer": referer} if referer else None, timeout=60)
    r.raise_for_status()
    with open(dest, "wb") as f:
        f.write(r.content)


def stream(s, url, dest, progress=None, cancelled=lambda: False, referer=None):
    """Descarga `url` a `dest` por partes (vía un .part). progress(done, total) opcional.
    Devuelve False si se canceló."""
    tmp = dest + ".part"
    with s.get(url, stream=True, timeout=30, headers={"Referer": referer} if referer else None) as r:
        r.raise_for_status()
        if "text/html" in r.headers.get("Content-Type", ""):
            raise RuntimeError("El sitio devolvió una página en vez del video")
        total = int(r.headers.get("Content-Length", 0))
        done = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                if cancelled():
                    break
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    if cancelled():
        os.remove(tmp)
        return False
    os.replace(tmp, dest)
    return True
