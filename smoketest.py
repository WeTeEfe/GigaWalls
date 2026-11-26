"""Prueba completa de GigaWalls antes de publicar (main.py --smoketest informe.txt).

Abre la ventana de verdad (sin tocar el fondo de escritorio ni los ajustes guardados), hace búsquedas
reales, carga más páginas, espera miniaturas, baja una vista previa, abre la biblioteca y revisa que
el indicador de "Buscando" aparezca y desaparezca. Funciona igual desde el código y desde el .exe,
así también detecta lo que falte en el empaquetado. Devuelve 0 si todo pasó.
"""
import os
import time
import traceback

from PySide6.QtCore import QEventLoop, QTimer


def _esperar(cond, segundos):
    """Procesa eventos de Qt hasta que cond() sea verdadero o se acabe el tiempo."""
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        if cond():
            return True
        loop = QEventLoop()
        QTimer.singleShot(100, loop.quit)
        loop.exec()
    return cond()


def run(main, out_path):
    lineas, fallos = [], 0

    def check(nombre, fn, fatal=True):
        nonlocal fallos
        try:
            lineas.append(f"OK     {nombre}: {fn()}")
        except Exception as e:  # noqa: BLE001
            if fatal:
                fallos += 1
            marca = "FALLA " if fatal else "AVISO "
            lineas.append(f"{marca} {nombre}: {type(e).__name__}: {e}")
            if fatal:
                lineas.append("       " + traceback.format_exc().strip().replace("\n", "\n       "))

    # Nada de lo que haga la prueba se guarda en el settings.json del usuario
    main.save_settings = lambda _data: None

    # 1) Lo que ya revisaba --selftest (ffmpeg, opencv, certificados, iconos...)
    tmp = out_path + ".selftest"

    def selftest():
        code = main.selftest(tmp)
        with open(tmp, encoding="utf-8") as f:
            texto = f.read()
        os.remove(tmp)
        if code:
            raise RuntimeError(texto.replace("\n", " | "))
        return "todo presente"
    check("dependencias (selftest)", selftest)

    # 2) La ventana se construye y la primera búsqueda arranca sin errores
    state = {}

    def ventana():
        wallpaper = main.DesktopWallpaper()
        state["win"] = win = main.MainWindow(wallpaper, {})
        win.show()
        return "construida"
    check("abrir ventana", ventana)
    win = state.get("win")
    if win is None:
        return _guardar(out_path, lineas, fallos)

    def indicador_visible():
        if not win.busy_spin.isVisibleTo(win) or not win.busy_label.text():
            raise RuntimeError("no se ve el indicador de búsqueda mientras busca")
        return win.busy_label.text()

    def busqueda(texto, minimo=1):
        def fn():
            win.search_box.setText(texto)
            win.search(texto)
            estado = indicador_visible()
            if not _esperar(lambda: not win.loading, 60):
                raise TimeoutError("la búsqueda no terminó en 60 s")
            if win.results.count() < minimo:
                raise RuntimeError(f"solo {win.results.count()} resultados (status: {win.status.currentMessage()})")
            if not _esperar(lambda: not win.busy_spin.isVisibleTo(win) or win.loading, 5):
                raise RuntimeError("el indicador de búsqueda no se ocultó al terminar")
            return f"{win.results.count()} resultados  ·  mientras buscaba: «{estado}»"
        return fn

    check("catálogo inicial (lo más nuevo)", busqueda(""))
    check("búsqueda en español traducida", busqueda("atardecer en la playa"))
    check("búsqueda de anime", busqueda("naruto"))

    def mas_paginas():
        antes, pagina = win.results.count(), win.page
        win.exhausted = False
        win.load_more()
        if not _esperar(lambda: not win.loading, 60):
            raise TimeoutError("la página siguiente no llegó en 60 s")
        if win.page <= pagina and not win.exhausted:
            raise RuntimeError("no avanzó de página")
        return f"página {win.page}: {antes} → {win.results.count()} resultados"
    check("cargar más páginas", mas_paginas)

    def miniaturas():
        def con_imagen():
            return sum(1 for i in range(win.results.count()) if not win.results.item(i).icon().isNull())
        _esperar(lambda: con_imagen() >= min(6, win.results.count()), 40)
        n = con_imagen()
        if n == 0:
            raise RuntimeError("no llegó ninguna miniatura en 40 s")
        return f"{n} de {win.results.count()} con imagen"
    check("miniaturas", miniaturas)

    def vista_previa():
        from PySide6.QtCore import Qt
        info = win.results.item(0).data(Qt.UserRole)
        path = main.fetch_preview(info)
        size = os.path.getsize(path)
        if size < 10_000:
            raise RuntimeError(f"archivo de vista previa muy chico ({size} bytes)")
        return f"{info['source']}: {size // 1024} KB"
    check("descargar vista previa", vista_previa)

    # 3) Cada origen por separado: si uno se cae se avisa, pero no frena la publicación
    for nombre, modulo in main.SOURCES.items():
        def origen(modulo=modulo):
            items = modulo.search("nature", 1)
            if not items:
                raise RuntimeError("0 resultados")
            return f"{len(items)} resultados"
        check(f"origen {nombre}", origen, fatal=False)

    def sin_resultados():
        win.search("zzqxjvwk qqzzxx")
        _esperar(lambda: not win.loading, 60)
        if win.busy_spin.isVisibleTo(win):
            raise RuntimeError("el indicador sigue girando sin resultados")
        return f"{win.results.count()} resultados, indicador oculto"
    check("búsqueda sin resultados", sin_resultados, fatal=False)

    def biblioteca():
        win._goto_page(1)
        _esperar(lambda: False, 1)
        win._goto_page(0)
        return f"{win.library.count()} videos en la biblioteca"
    check("abrir biblioteca", biblioteca)

    def cola_de_tareas():
        # dos operaciones seguidas: la segunda espera en la cola y arranca sola al terminar la primera
        from PySide6.QtCore import QTimer as _T
        orden = []

        def falsa(nombre):
            def arrancar(t):
                orden.append(nombre)
                t.etapa(0, "probando")
                t.avance(1, 2)
                _T.singleShot(300, lambda: (win._end(), t.terminar("Listo")))
            return arrancar
        t1, t2 = main.Tarea("prueba 1", ["Paso"]), main.Tarea("prueba 2", ["Paso"])
        win._encolar(t1, falsa("1"))
        win._encolar(t2, falsa("2"))
        if t2.estado != main.Tarea.COLA or t2.posicion != 1 or not win.panel_tareas.isVisible():
            raise RuntimeError(f"la segunda no quedó en cola (estado {t2.estado}, #{t2.posicion})")
        if not _esperar(lambda: t1.estado == t2.estado == main.Tarea.LISTA, 10):
            raise RuntimeError(f"no terminaron: {t1.estado}, {t2.estado}")
        if orden != ["1", "2"] or win._busy:
            raise RuntimeError(f"orden {orden}, ocupado={win._busy}")
        win.panel_tareas.quitar(t1)
        win.panel_tareas.quitar(t2)
        return "una después de la otra, con sus tarjetas"
    check("cola de descargas", cola_de_tareas)

    def recuperacion():
        # el fondo se rearma solo si deja de recibir imagen o si Qt avisa que el decodificador perdió la GPU
        import time as _t
        import desktop as d
        from PySide6.QtCore import qCritical
        from PySide6.QtMultimedia import QMediaPlayer
        w = d.DesktopWallpaper()
        rearmados = []

        class Reproductor:
            def playbackState(self):
                return QMediaPlayer.PlaybackState.PlayingState
        w._path, w._videos, w._visible, w._player = "prueba.mp4", [object()], [object()], Reproductor()
        w._desktop_alive = lambda: True
        w._rebuild = lambda: rearmados.append(_t.monotonic())
        w.pause_when_covered = False
        viejo_full = d._fullscreen_app
        d._fullscreen_app = lambda: False
        try:
            w._ultimo_fotograma = _t.monotonic()
            w._check_fullscreen()
            if rearmados:
                raise RuntimeError("se rearmó con imagen llegando bien")
            w._ultimo_fotograma = _t.monotonic() - 30  # 30 s sin imagen
            w._check_fullscreen()
            if len(rearmados) != 1:
                raise RuntimeError("no se rearmó tras 30 s sin imagen")
            main._al_perder_gpu = lambda: setattr(w, "gpu_perdida", True)
            qCritical("Unable to copy frame from decoder pool")  # el mensaje real del 26/11
            if not w.gpu_perdida:
                raise RuntimeError("el aviso de Qt no levantó la bandera")
            w._ultimo_fotograma = _t.monotonic()
            w._check_fullscreen()
            if len(rearmados) != 2:
                raise RuntimeError("no se rearmó al perder la GPU")
            for _ in range(5):  # video roto: no insistir sin parar
                w._ultimo_fotograma = _t.monotonic() - 30
                w._check_fullscreen()
            if len(rearmados) != 3:
                raise RuntimeError(f"se rearmó {len(rearmados)} veces (máximo 3 cada 5 min)")
        finally:
            d._fullscreen_app = viejo_full
            main._al_perder_gpu = None
        return "sin imagen 8 s o GPU perdida → se rearma (máx. 3 cada 5 min)"
    check("recuperación del fondo", recuperacion)

    def actualizaciones():
        # lo mismo que hace la copia instalada: consulta GitHub en un hilo (prueba también el SSL del .exe)
        from instalacion import INSTALACION, _en_hilo
        r = {}
        _en_hilo(INSTALACION.ultima_version, lambda info, error: r.update(info=info, error=error))
        if not _esperar(lambda: r, 20):
            raise RuntimeError("GitHub no respondió en 20 s")
        if r["error"]:
            raise r["error"]
        info = r["info"]
        if not info["url"].endswith("/" + INSTALACION.exe_nombre) or info["tamano"] < 10_000_000:
            raise RuntimeError(f"instalador publicado raro: {info['url']} ({info['tamano']} bytes)")
        return f"última publicada {info['version']} ({info['tamano'] / 1e6:.0f} MB), esta {INSTALACION.version}"
    check("buscar actualizaciones en GitHub", actualizaciones)

    win.tray.hide()
    win.hide()
    win._gen += 1  # que las miniaturas que sigan llegando se descarten
    # Salir con hilos de descarga vivos hace que Windows corte el proceso con 0xC0000005
    win.pool.clear()
    win.pool.waitForDone(30000)
    win.wallpaper.stop()
    win.deleteLater()
    _esperar(lambda: False, 0.5)
    return _guardar(out_path, lineas, fallos)


def _guardar(out_path, lineas, fallos):
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + f"\nRESULTADO: {'TODO OK' if not fallos else f'{fallos} FALLO(S)'}\n")
    return 0 if not fallos else 1
