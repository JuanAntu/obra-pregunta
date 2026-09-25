import re, sys, collections, urllib.request
from playwright.sync_api import sync_playwright

URL = "https://juanantu.github.io/obra-pregunta/"
js = urllib.request.urlopen(URL + "links.js").read().decode()
LINKS = re.findall(r'"(https?://[^"]+)"', js)
print("links.js tiene", len(LINKS), "links")
ok = True

def fail(msg):
    global ok
    ok = False
    print("FALLA:", msg)

with sync_playwright() as p:
    b = p.chromium.launch()
    dev = p.devices["Pixel 7"]

    def capture(ctx, url=URL):
        """Abre la página y devuelve el primer link de canva al que redirige."""
        hit = []
        def h(route):
            hit.append(route.request.url)
            route.fulfill(status=200, body="ok", content_type="text/html")
        ctx.route(re.compile(r"https://canva\.link/.*"), h)
        pg = ctx.new_page()
        try:
            pg.goto(url, timeout=20000)
            pg.wait_for_url(re.compile(r"canva\.link"), timeout=10000)
        except Exception as e:
            pass
        pg.close()
        return hit[0] if hit else None

    # A) 30 visitantes distintos
    cnt = collections.Counter()
    for i in range(30):
        ctx = b.new_context(**dev)
        r = capture(ctx); ctx.close()
        if r not in LINKS: fail(f"visita {i}: redirigió a {r}")
        cnt[r] += 1
    print("A) 30 celulares distintos:", dict(cnt))
    if set(cnt) != set(LINKS): fail("no salieron todos los links")

    # B) mismo celular 30 veces seguidas: nunca repite el anterior
    ctx = b.new_context(**dev)
    seq = [capture(ctx) for _ in range(30)]
    ctx.close()
    reps = sum(1 for a, c in zip(seq, seq[1:]) if a == c)
    print("B) mismo celular, repeticiones consecutivas:", reps, "| distintos:", len(set(seq)))
    if reps or None in seq: fail("repitió o no redirigió en el mismo celular")

    # C) JavaScript desactivado: botón visible con link válido
    ctx = b.new_context(java_script_enabled=False, **dev)
    pg = ctx.new_page(); pg.goto(URL)
    btn = pg.locator("#go"); alt = pg.locator("#alt")
    print("C) sin JS: botón visible =", btn.is_visible(), "| texto =", btn.inner_text(),
          "| href en links.js =", btn.get_attribute("href") in LINKS,
          "| respaldo visible =", alt.is_visible())
    pg.screenshot(path="sin_js.png")
    if not (btn.is_visible() and btn.get_attribute("href") in LINKS and alt.is_visible()): fail("fallback sin JS")
    ctx.close()

    # D) localStorage que tira error (Safari privado viejo, etc.)
    ctx = b.new_context(**dev)
    ctx.add_init_script("""Object.defineProperty(window,'localStorage',{get(){throw new Error('bloqueado')}});""")
    rs = [capture(ctx) for _ in range(5)]
    print("D) localStorage roto:", rs.count(None), "fallas de 5")
    if None in rs: fail("localStorage roto")
    ctx.close()

    # E) links.js no carga
    ctx = b.new_context(**dev)
    ctx.route("**/links.js", lambda r: r.abort())
    r = capture(ctx)
    print("E) links.js caído -> redirige a", r)
    if r not in LINKS: fail("fallback con links.js caído")
    ctx.close()

    # F) cada link de Canva abre de verdad (sin interceptar)
    for l in LINKS:
        ctx = b.new_context(**dev); pg = ctx.new_page()
        resp = pg.goto(l, timeout=45000, wait_until="domcontentloaded")
        pg.wait_for_timeout(6000)
        body = pg.inner_text("body")[:3000].lower()
        login = any(w in body for w in ["iniciar sesión", "log in", "sign up", "registrarte", "continue with google", "continuar con google"])
        print(f"F) {l} -> {resp.status} | {pg.url[:70]} | pide login: {login}")
        pg.screenshot(path="canva_" + l.rsplit('/', 1)[1] + ".png")
        if resp.status >= 400: fail(f"{l} status {resp.status}")
        ctx.close()
    b.close()

print("\nRESULTADO:", "TODO OK" if ok else "HAY FALLAS")
sys.exit(0 if ok else 1)
