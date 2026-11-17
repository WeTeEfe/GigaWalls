"""Cliente mínimo de LiveWallpapers4Free: búsqueda, miniaturas, vista previa y descarga del .mp4 en HD."""
import re

from bs4 import BeautifulSoup

import webdl

NAME = "LiveWallpapers4Free"
PREVIEW_EXT = ".mp4"
BASE = "https://livewallpapers4free.com"

_session = webdl.session(BASE)


def _clean_title(text):
    return re.sub(r"\s*live wallpaper$", "", text.strip(), flags=re.I)


def search(query="", page=1):
    """Devuelve una lista de dicts {title, url, thumb, category, source}. Vacía si no hay más."""
    path = f"/page/{page}/" if page > 1 else "/"
    r = _session.get(BASE + path, params={"s": query} if query else None, timeout=30)
    if r.status_code == 404:  # pasada la última página
        return []
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for a in soup.select("#recent-content a.thumbnail-link"):
        img = a.select_one("img")
        if not img:
            continue
        items.append({
            "title": _clean_title(img.get("alt") or a["href"]),
            "url": a["href"],
            "thumb": img.get("src", ""),
            "category": "",
            "source": NAME,
        })
    return items


def get_thumb(url):
    return _session.get(url, timeout=30).content


def _page(page_url):
    r = _session.get(page_url, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def download_preview(page_url, dest):
    """Descarga el clip del reproductor de la página (480p, ~1 MB) a `dest`."""
    source = _page(page_url).select_one("video source[src]")
    if not source:
        raise RuntimeError("Este wallpaper no tiene vista previa")
    webdl.save(_session, source["src"], dest, referer=page_url)


def get_download_url(page_url):
    """De las versiones que ofrece (HD, 2K, 4K, 8K) se elige la HD: es la que se usa de fondo."""
    links = [(a["href"], a.get_text(" ", strip=True).lower())
             for a in _page(page_url).find_all("a", href=re.compile(r"/download/\d+/?$"))]
    if not links:
        raise RuntimeError("No se encontró el enlace de descarga en LiveWallpapers4Free")
    for href, text in links:
        if "-hd-" in text or "hd" in text.split(".")[0].split("-"):
            return href
    return links[0][0]


def filename(page_url):
    return page_url.rstrip("/").rsplit("/", 1)[-1].lower() + ".mp4"


def download(page_url, dest, progress=None, cancelled=lambda: False):
    """Descarga el .mp4 a `dest`. progress(done, total) opcional."""
    return webdl.stream(_session, get_download_url(page_url), dest, progress, cancelled, referer=page_url)
