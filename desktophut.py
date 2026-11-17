"""Cliente minimo de DesktopHut: busqueda, miniaturas y descarga del .mp4 (misma interfaz que moewalls)."""
import os
import re
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

NAME = "DesktopHut"
PREVIEW_EXT = ".mp4"
BASE = "https://desktophut.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": BASE + "/",
}

_session = requests.Session()
_session.headers.update(HEADERS)

# El video completo vive en /files/; las vistas previas en /previews/ (no sirven como fondo)
_FILE_RE = re.compile(r"https?://(?:media|www)\.desktophut\.com/files/[^\"'\s<>\\]+\.mp4")
_PREVIEW_RE = re.compile(r"https?://media\.desktophut\.com/previews/[^\"'\s<>\\]+\.mp4")


def _clean_title(text):
    text = re.sub(r"^Wallpaper of the Day:\s*", "", text.strip())
    text = re.sub(r"^Download\s+", "", text)
    text = re.sub(r"\s*[—-]\s*animated wallpaper$", "", text, flags=re.I)
    text = re.sub(r"\s*live wallpaper(\s*\(4K/HD\))?$", "", text, flags=re.I)
    return text.strip()


def search(query="", page=1):
    """Devuelve una lista de dicts {title, url, thumb, category, source}. Vacia si no hay mas."""
    path = f"/search/{quote(query)}" if query else "/"
    params = {"page": page} if page > 1 else None
    r = _session.get(BASE + path, params=params, timeout=30)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    h1 = soup.find("h1")
    if h1 and "no matches" in h1.get_text().lower():
        return []  # sin mas resultados: el sitio rellena la pagina con recomendados que no coinciden
    items = []
    for a in soup.select("a.wallpaper-card"):
        img = a.select_one("img")
        if not img:
            continue
        href = a.get("href", "")
        items.append({
            "title": _clean_title(a.get("aria-label") or a.get("title") or href),
            "url": href if href.startswith("http") else BASE + href,
            "thumb": img.get("src") or img.get("data-src") or "",
            "category": "",
            "source": NAME,
        })
    return items


def get_thumb(url):
    return _session.get(url, timeout=30).content


def get_download_url(page_url):
    r = _session.get(page_url, timeout=30)
    r.raise_for_status()
    m = _FILE_RE.search(r.text)
    if not m:
        raise RuntimeError("No se encontro el video en la pagina de DesktopHut")
    return m.group(0)


def download_preview(page_url, dest):
    """Descarga el clip corto de vista previa (.mp4, <1 MB) a `dest`."""
    r = _session.get(page_url, timeout=30)
    r.raise_for_status()
    m = _PREVIEW_RE.search(r.text)
    if not m:
        raise RuntimeError("Este wallpaper no tiene vista previa")
    clip = _session.get(m.group(0), timeout=60)
    clip.raise_for_status()
    with open(dest, "wb") as f:
        f.write(clip.content)


def filename(page_url):
    return page_url.rstrip("/").rsplit("/", 1)[-1].lower() + ".mp4"


def download(page_url, dest, progress=None, cancelled=lambda: False):
    """Descarga el .mp4 a `dest`. progress(done, total) opcional."""
    url = get_download_url(page_url)
    tmp = dest + ".part"
    with _session.get(url, stream=True, timeout=30) as r:
        r.raise_for_status()
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
