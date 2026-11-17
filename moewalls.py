"""Cliente minimo de MoeWalls: busqueda, miniaturas y descarga del .mp4."""
import re
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

NAME = "MoeWalls"
PREVIEW_EXT = ".webm"
BASE = "https://moewalls.com"
DOWNLOAD = "https://go.moewalls.com/download.php?video="
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": BASE + "/",
}

_session = requests.Session()
_session.headers.update(HEADERS)


def search(query="", page=1):
    """Devuelve una lista de dicts {title, url, thumb, category}. Vacia si no hay mas paginas."""
    path = f"/page/{page}/" if page > 1 else "/"
    params = {"s": query} if query else None
    try:
        r = _session.get(BASE + path, params=params, timeout=30)
    except requests.exceptions.Timeout:  # el sitio a veces tarda; un reintento
        r = _session.get(BASE + path, params=params, timeout=45)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for art in soup.select("article.entry-tpl-grid"):
        link = art.select_one("a.g1-frame")
        img = art.select_one("img")
        if not link or not img:
            continue
        cat = art.select_one(".entry-category")
        items.append({
            "title": re.sub(r"\s*Live Wallpaper$", "", link.get("title", "")).strip(),
            "url": link["href"],
            "thumb": img.get("src", ""),
            "category": cat.get_text(strip=True) if cat else "",
            "source": NAME,
        })
    return items


def download_preview(page_url, dest):
    """Descarga el clip corto de vista previa (.webm, 1-3 MB) a `dest`."""
    r = _session.get(page_url, timeout=30)
    r.raise_for_status()
    m = re.search(r'<source[^>]+src="([^"]*/preview/[^"]+)"', r.text)
    if not m:
        raise RuntimeError("Este wallpaper no tiene vista previa")
    clip = _session.get(urljoin(BASE, m.group(1)), timeout=60)
    clip.raise_for_status()
    with open(dest, "wb") as f:
        f.write(clip.content)


def filename(page_url):
    slug = page_url.rstrip("/").rsplit("/", 1)[-1].replace("-live-wallpaper", "")
    return slug + ".mp4"


def get_thumb(url):
    return _session.get(url, timeout=20).content


def get_download_url(page_url):
    r = _session.get(page_url, timeout=20)
    r.raise_for_status()
    m = re.search(r'id="moe-download"[^>]*data-url\s*=\s*"([^"]+)"', r.text)
    if not m:
        raise RuntimeError("No se encontro el enlace de descarga en la pagina")
    return DOWNLOAD + m.group(1)


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
        import os
        os.remove(tmp)
        return False
    import os
    os.replace(tmp, dest)
    return True
