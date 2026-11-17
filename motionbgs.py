"""Cliente mínimo de MotionBGS: búsqueda, miniaturas, vista previa y descarga del .mp4 en 1080p."""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import webdl

NAME = "MotionBGS"
PREVIEW_EXT = ".mp4"
BASE = "https://motionbgs.com"

_session = webdl.session(BASE)
# La búsqueda redirige a una etiqueta (/tag:sunset/) cuando el término coincide con una, y esas se
# paginan (/tag:sunset/2/); una búsqueda libre da una sola página. Se recuerda a dónde llevó cada
# término para pedir sus páginas siguientes.
_search_base = {}


def _search_landing(query):
    if query not in _search_base:
        r = _session.get(BASE + "/search", params={"q": query}, timeout=30)
        r.raise_for_status()
        _search_base[query] = (r.url, r.text)
    return _search_base[query]


def search(query="", page=1):
    """Devuelve una lista de dicts {title, url, thumb, category, source}. Vacía si no hay más."""
    if not query:
        r = _session.get(f"{BASE}/{page}/" if page > 1 else BASE + "/", timeout=30)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        html = r.text
    elif page == 1:
        _search_base.pop(query, None)  # búsqueda nueva: el catálogo pudo cambiar
        html = _search_landing(query)[1]
    else:
        landing = _search_landing(query)[0]
        if "/tag:" not in landing:
            return []
        r = _session.get(f"{landing.rstrip('/')}/{page}/", timeout=30)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        html = r.text
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for a in soup.select("div.tmb a[href]"):
        img = a.select_one("img")
        title = a.select_one(".ttl")
        if not img or not title:
            continue
        items.append({
            "title": title.get_text(strip=True),
            "url": urljoin(BASE, a["href"]),
            "thumb": urljoin(BASE, img.get("src", "")),
            "category": "",
            "source": NAME,
        })
    return items


def get_thumb(url):
    return _session.get(url, timeout=30).content


def _page(page_url):
    r = _session.get(page_url, timeout=30)
    r.raise_for_status()
    return r.text


def download_preview(page_url, dest):
    """Descarga el clip de vista previa (960x540, ~1 MB) a `dest`."""
    m = re.search(r'<source[^>]+src=["\']?([^"\' >]+\.mp4)', _page(page_url))
    if not m:
        raise RuntimeError("Este wallpaper no tiene vista previa")
    webdl.save(_session, urljoin(BASE, m.group(1)), dest, referer=page_url)


def get_download_url(page_url):
    """Enlace al video completo: el de 1080p (/dl/hd/ID); si no lo hay, el 4K."""
    text = _page(page_url)
    for quality in ("hd", "4k"):
        m = re.search(rf'href=["\']?(/dl/{quality}/\d+)', text)
        if m:
            return BASE + m.group(1) + "/"
    raise RuntimeError("No se encontró el enlace de descarga en MotionBGS")


def filename(page_url):
    return page_url.rstrip("/").rsplit("/", 1)[-1].lower() + ".mp4"


def download(page_url, dest, progress=None, cancelled=lambda: False):
    """Descarga el .mp4 a `dest`. progress(done, total) opcional."""
    return webdl.stream(_session, get_download_url(page_url), dest, progress, cancelled, referer=page_url)
