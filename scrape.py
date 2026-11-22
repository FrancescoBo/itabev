#!/usr/bin/env python3
"""Raccoglie tutti gli allestimenti BEV dal listino Quattroruote.

Uso:
  python scrape.py                       # tutto il listino (lento: ore)
  python scrape.py --models tesla/model-3 dacia/spring   # prova su pochi modelli
  python scrape.py --debug               # salva l'HTML grezzo in debug/
Output: data/ev_ita.csv, data/ev_ita.json, data/scartate.csv, index.html
"""
import argparse, csv, json, os, re, sys, threading, time
import concurrent.futures as cf
from datetime import date
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

BASE = "https://www.quattroruote.it"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
FIELDS = ["modello", "allestimento", "tipo", "posti", "cap", "h", "w", "l", "m", "pomol",
          "ppeak", "cons", "vmax", "prezzo", "anno", "autonomia", "autonomia_fonte", "stato", "url"]

ARGS = None
TL = threading.local()


def session():
    if not hasattr(TL, "s"):
        TL.s = requests.Session()
        TL.s.headers.update({"User-Agent": UA, "Accept-Language": "it-IT,it;q=0.9"})
    return TL.s


def fetch(url, tries=2):
    for i in range(tries):
        try:
            r = session().get(url, timeout=20)
            if r.status_code == 200:
                time.sleep(ARGS.delay)
                return r.text
            if r.status_code == 404:
                return None
            print(f"  HTTP {r.status_code} {url}", file=sys.stderr, flush=True)
            time.sleep(8 * (i + 1) if r.status_code in (403, 429) else 2)
        except requests.RequestException as e:
            print(f"  errore rete {type(e).__name__} {url}", file=sys.stderr, flush=True)
            time.sleep(3)
    return None


def dump(name, html):
    if ARGS.debug and html:
        os.makedirs("debug", exist_ok=True)
        with open(os.path.join("debug", re.sub(r"\W+", "_", name)[:120] + ".html"), "w", encoding="utf-8") as f:
            f.write(html)


# ---------- scoperta dei modelli (serve un browser: la lista si carica con JS) ----------
def discover_models():
    """Modelli con almeno un allestimento BEV, dal filtro 'elettrica' della ricerca Quattroruote."""
    from playwright.sync_api import sync_playwright
    found = set()
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_context(user_agent=UA, locale="it-IT", viewport={"width": 1366, "height": 900}).new_page()
        pg.goto(BASE + "/listino/ricerca.html?elettrica=elettrica", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(4000)
        for txt in ("Accetta", "Accetto", "Consenti"):  # banner cookie, se presente
            try:
                pg.get_by_role("button", name=re.compile(txt, re.I)).first.click(timeout=1500)
                break
            except Exception:
                pass
        rx = re.compile(r"/listino/([a-z0-9._-]+)/([a-z0-9._-]+)(?=[\"'/?#])", re.I)

        def models_now():
            return {f"{m.group(1)}/{m.group(2)}" for m in rx.finditer(pg.content())
                    if not re.match(r"(ricerca|offerte|marche|source)", m.group(1))
                    and "quattroruote" not in m.group(0).lower()}

        stale, prev = 0, 0
        for _ in range(80):
            btn = pg.locator("#loadMoreCarsBtn")
            if btn.count() == 0 or not btn.first.is_visible():
                break
            try:
                btn.first.scroll_into_view_if_needed(timeout=3000)
                btn.first.click(timeout=5000)
            except Exception:
                break
            pg.wait_for_timeout(2500)
            n = len(models_now())
            stale = stale + 1 if n == prev else 0
            prev = n
            print(f"  ricerca: {n} modelli caricati", flush=True)
            if stale >= 3:
                break
        dump("ricerca", pg.content())
        found = models_now()
        b.close()
    print(f"Ricerca con filtro elettrica: {len(found)} modelli", flush=True)
    return sorted(found)


# ---------- pagina modello: elenco allestimenti + stato ----------
def model_versions(model):
    html = fetch(f"{BASE}/listino/{model}")
    if not html:
        return {}, None
    dump("modello_" + model, html)
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    title = re.sub(r"\s+", " ", h1.get_text(" ", strip=True)) if h1 else None
    if title and ("quattroruote" in title.lower() or "/" in title):   # titolo spurio (es. Polestar)
        title = None
    out = {}
    pages = [soup]
    for a in soup.find_all("a", string=re.compile(r"Tutti gli allestimenti", re.I)):  # elenco completo
        h2 = fetch(urljoin(BASE, a["href"]))
        if h2:
            pages.append(BeautifulSoup(h2, "html.parser"))
    pat = re.compile(r"^(?:https://www\.quattroruote\.it)?/auto/" + re.escape(model.split("/")[0]) + r"/[^/?#]+/[^/?#]+$")
    for s in pages:
        links = [a for a in s.find_all("a", href=True) if pat.match(a["href"])]
        allh = {a["href"] for a in links}
        for a in links:
            node, best = a, a
            while node.parent is not None and node.parent.name not in ("body", "html"):
                inside = {x["href"] for x in node.parent.find_all("a", href=True) if pat.match(x["href"])}
                if len(inside) > 1:
                    break
                node = node.parent
                best = node
            txt = best.get_text(" ", strip=True)
            url = urljoin(BASE, a["href"])
            stato = "esaurimento scorte" if re.search(r"esaurimento\s+scorte", txt, re.I) else "disponibile"
            if url not in out or stato != "disponibile":
                out[url] = stato
    return out, title


# ---------- pagina allestimento ----------
def to_num(s, thousands=False):
    s = s.strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif thousands:
        s = s.replace(".", "")
    try:
        v = float(s)
        return int(v) if v == int(v) else v
    except ValueError:
        return None


def grab(text, pattern, thousands=False, group=1):
    m = re.search(pattern, text, re.I)
    return to_num(m.group(group), thousands) if m else None


N = r"(\d[\d.,]*)"


def parse_version(url, html):
    soup = BeautifulSoup(html, "html.parser")
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    d = {"url": url}
    h1 = soup.find("h1")                       # es. "DACIA <strong>Spring 2ª serie</strong>"
    h2 = soup.select_one("h2.c-subtitles1")    # es. "Spring Electric 80 Expression"
    d["modello"] = re.sub(r"\s+", " ", h1.get_text(" ", strip=True)) if h1 else None
    d["allestimento"] = re.sub(r"\s+", " ", h2.get_text(" ", strip=True)) if h2 else None
    m = re.search(r"/auto/[^/]+/[^/]+/[^/]+-(\d+)(\d{4})(\d{2})$", url)
    d["anno"] = int(m.group(2)) if m else None
    m = re.search(r"Modello\s*:?\s*([a-zA-Zàèéìòù/ 0-9|]+?)\s+(?:Posti|Alimentazione|Motore)", text)
    d["tipo"] = m.group(1).strip() if m else None
    d["posti"] = grab(text, r"Posti\s*:?\s*(\d+)")
    d["cap"] = grab(text, r"Capacit[àa] batteria\s*:?\s*" + N)
    d["h"] = grab(text, r"Altezza\s*:?\s*" + N + r"\s*cm")
    d["w"] = grab(text, r"Larghezza\s*:?\s*" + N + r"\s*cm")
    d["l"] = grab(text, r"Lunghezza\s*:?\s*" + N + r"\s*cm")
    d["m"] = grab(text, r"Massa\s*:?\s*" + N + r"\s*kg", thousands=True)
    for key, lab in (("pomol", r"Potenza Omologata"), ("ppeak", r"Potenza di picco/boost")):
        cv = grab(text, lab + r"\s*:?\s*[\d.,]+\s*kW\s*\(\s*" + N + r"\s*CV")
        if cv is None:
            kw = grab(text, lab + r"\s*:?\s*" + N + r"\s*kW")
            cv = round(kw * 1.36) if kw else None
        d[key] = cv
    d["cons"] = grab(text, r"Consumo medio\s*:?\s*" + N)
    d["vmax"] = grab(text, r"Velocit[àa] max\s*:?\s*" + N)
    d["prezzo"] = grab(text, r"Prezzo allestimento\s*:?\s*€?\s*" + N, thousands=True)
    aut = grab(text, r"Autonomia\s*:?\s*" + N + r"\s*km")
    if aut:
        d["autonomia"], d["autonomia_fonte"] = aut, "sito"
    elif d["cap"] and d["cons"]:
        d["autonomia"], d["autonomia_fonte"] = round(d["cap"] / d["cons"] * 100), "calcolata"
    else:
        d["autonomia"], d["autonomia_fonte"] = None, ""
    # BEV: serve batteria, nessuna cilindrata e nessun riferimento a ibrido/termico nella sezione Motore
    mot = re.search(r"Motore(.{0,500})", text)
    mot = mot.group(1) if mot else ""
    ice = re.search(r"cilindrata\s*:?\s*\d{3,}|ibrid|hybrid|plug-in|benzina|gasolio|diesel|gpl|metano", mot, re.I)
    d["_bev"] = bool(d["cap"]) and not ice and re.search(r"elettric", text[:20000], re.I) is not None
    return d


# ---------- scoperta via sitemap (senza browser) ----------
HINT = re.compile(r"kwh|electric|elettric|-ev-|-ev$|bev|e-tech|e-tron|e-\d|\d+e-|-e-", re.I)
# segnali di motore termico/ibrido nello slug dell'allestimento: queste schede non si scaricano
ICE = re.compile(r"tfsi|tsi|tdi|hdi|puretech|multijet|mjt|ecoboost|ecoblue|crdi|t-gdi|\bgdi|mhev|48v|hybrid|ibrid|phev"
                 r"|plug-in|gpl|metano|dci|tce|vtec|skyactiv|diesel|benzina|s&s|-v6-|-v8-|-v12-"
                 r"|(?:^|-)\d{2,3}[di](?:-|$)", re.I)


def slug(u):
    return u.rsplit("/", 1)[-1]


def discover_from_sitemap(since):
    """{marca/modello: [(aaaamm, url), ...]} per i modelli con almeno una versione >= since."""
    import html as H
    urls = []
    for n in (1, 2, 3):
        t = fetch(f"{BASE}/Sitemap-listino-{n}.xml")
        if t:
            urls += re.findall(r"<loc>\s*(https://www\.quattroruote\.it/auto/[^<\s]+)\s*</loc>", t)
    models = {}
    for u in urls:
        u = H.unescape(u)
        m = re.match(r"https://www\.quattroruote\.it/auto/([^/]+)/([^/]+)/[^/]+?(\d{6})$", u)
        if m:
            models.setdefault(f"{m.group(1)}/{m.group(2)}", []).append((int(m.group(3)), u))
    models = {k: v for k, v in models.items() if max(x[0] for x in v) >= since}
    print(f"Sitemap: {len(urls)} URL totali, {len(models)} modelli con versioni dal {since}", flush=True)
    return models


def sample_urls(vers, full):
    cands = sorted([x for x in vers if not ICE.search(slug(x[1]))], reverse=True)
    if not cands:
        return []
    if full:
        return [u for _, u in cands]
    pick = [u for _, u in cands if HINT.search(slug(u))][:2] + [u for _, u in cands[:2]] + [cands[len(cands) // 2][1]]
    return list(dict.fromkeys(pick))


CACHE = {}
CACHE_FILE = "cache/versions.json"


def get_version(url):
    if url in CACHE:
        return CACHE[url]
    html = fetch(url)
    if html is None:
        return None            # non in cache: si puo' ritentare
    dump("allest_" + slug(url), html)
    CACHE[url] = parse_version(url, html)
    return CACHE[url]


def save_cache():
    os.makedirs("cache", exist_ok=True)
    json.dump(CACHE, open(CACHE_FILE, "w", encoding="utf-8"), ensure_ascii=False)


def pmap(fn, items, label, workers, deadline):
    out, done, t0 = {}, 0, time.time()
    with cf.ThreadPoolExecutor(workers) as ex:
        futs = {}
        for it in items:
            futs[ex.submit(lambda x=it: None if time.time() > deadline else fn(x))] = it
        for f in cf.as_completed(futs):
            out[futs[f]] = f.result()
            done += 1
            if done % 25 == 0 or done == len(items):
                el = time.time() - t0
                print(f"[{label}] {done}/{len(items)}  trascorsi {el/60:.1f} min, stima rimanente {el/done*(len(items)-done)/60:.1f} min", flush=True)
    return out


def process_model(mod):
    """Tutti gli allestimenti BEV di un modello (+ stato esaurimento)."""
    rows, scart = [], []
    marca, nome = mod.split("/", 1)
    vers, title = model_versions(mod)
    if title and title.lower().startswith(marca.replace("-", " ").lower()):
        etichetta = marca.replace("-", " ").upper() + title[len(marca):]
    elif title:
        etichetta = f"{marca.replace('-', ' ').upper()} {title}"
    else:
        etichetta = f"{marca.replace('-', ' ').upper()} {nome}"
    for url, stato in vers.items():
        if ICE.search(slug(url)):
            continue
        d = get_version(url)
        if d is None:
            scart.append({"url": url, "motivo": "pagina non scaricata"})
        elif not d.get("_bev"):
            scart.append({"url": url, "motivo": "non BEV (o scheda non riconosciuta)"})
        else:
            d = dict(d)
            mod_v = d.get("modello") or ""
            if not mod_v or "quattroruote" in mod_v.lower() or "/" in mod_v:   # titolo spurio (es. Polestar)
                mod_v = etichetta
            all_v = d.get("allestimento") or ""
            if not all_v or "quattroruote" in all_v.lower() or "/" in all_v:
                nome_all = re.sub(r"-\d{9,}$", "", slug(url)).replace("-", " ")
                all_v = nome_all[:1].upper() + nome_all[1:]
            d["modello"], d["allestimento"] = mod_v, all_v
            d["stato"] = stato
            rows.append({k: d.get(k) for k in FIELDS})
    return rows, scart


def main():
    global ARGS
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", help="es. tesla/model-3 dacia/spring (prova su pochi modelli)")
    ap.add_argument("--limit", type=int, help="max modelli (per prove)")
    ap.add_argument("--delay", type=float, default=0.5, help="pausa per richiesta, per ogni thread")
    ap.add_argument("--workers", type=int, default=4, help="richieste in parallelo")
    ap.add_argument("--since", type=int, default=202301, help="considera modelli con versioni da aaaamm")
    ap.add_argument("--max-minutes", type=float, default=180, help="tempo massimo; poi salva il parziale")
    ap.add_argument("--full", action="store_true", help="controlla ogni versione non termica di ogni modello")
    ap.add_argument("--resume", action="store_true", help="riusa cache/versions.json di una corsa interrotta")
    ap.add_argument("--sitemap", action="store_true", help="scoperta da sitemap invece che dal filtro elettrica")
    ap.add_argument("--debug", action="store_true")
    ARGS = ap.parse_args()
    deadline = time.time() + ARGS.max_minutes * 60
    if ARGS.resume and os.path.exists(CACHE_FILE):
        CACHE.update(json.load(open(CACHE_FILE, encoding="utf-8")))
        print(f"Cache: {len(CACHE)} schede riusate", flush=True)
    smap = {}
    try:
        if ARGS.models:
            bev_models = ARGS.models
        else:
            bev_models = [] if ARGS.sitemap else discover_models()
            if len(bev_models) < 50:
                print("Ricerca con filtro non utilizzabile (o --sitemap): scoperta da sitemap", flush=True)
                smap = discover_from_sitemap(ARGS.since)
                if not smap:
                    sys.exit("ERRORE: nessun modello trovato. File esistenti NON modificati.")
                models = sorted(smap)[:ARGS.limit] if ARGS.limit else sorted(smap)
                samples = {m: sample_urls(smap[m], ARGS.full) for m in models}
                todo = sorted({u for v in samples.values() for u in v})
                print(f"Fase 1: {len(todo)} schede campione su {len(models)} modelli", flush=True)
                pmap(get_version, todo, "fase1", ARGS.workers, deadline)
                bev_models = [m for m in models if any((CACHE.get(u) or {}).get("_bev") for u in samples[m])]
                print(f"Modelli con almeno un BEV: {len(bev_models)}", flush=True)
        if ARGS.limit:
            bev_models = bev_models[:ARGS.limit]
        # fase 2: tutti gli allestimenti dei modelli BEV
        res = pmap(process_model, bev_models, "fase2", ARGS.workers, deadline)
    finally:
        save_cache()
    rows, scartate = [], []
    for r in res.values():
        if r:
            rows += r[0]; scartate += r[1]
    partial = time.time() > deadline
    if not rows:
        sys.exit("ERRORE: 0 allestimenti BEV trovati. File esistenti NON modificati (controlla debug/).")
    rows = list({r["url"]: r for r in rows}.values())  # niente doppioni
    rows.sort(key=lambda r: (r["modello"], r["prezzo"] or 0))
    os.makedirs("data", exist_ok=True)
    with open("data/ev_ita.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, FIELDS, delimiter=";")
        w.writeheader(); w.writerows(rows)
    with open("data/ev_ita.json", "w", encoding="utf-8") as f:
        json.dump({"aggiornato": date.today().isoformat() + (" (PARZIALE: tempo scaduto)" if partial else ""),
                   "righe": rows}, f, ensure_ascii=False, indent=1)
    with open("data/scartate.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, ["url", "motivo"], delimiter=";")
        w.writeheader(); w.writerows(scartate)
    import build_html
    build_html.build()
    print(f"Fatto{' (PARZIALE)' if partial else ''}: {len(rows)} allestimenti BEV, {len(scartate)} scartati", flush=True)


if __name__ == "__main__":
    main()
