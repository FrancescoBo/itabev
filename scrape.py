#!/usr/bin/env python3
"""Raccoglie tutti gli allestimenti BEV dal listino Quattroruote.

Uso:
  python scrape.py                       # tutto il listino (lento: ore)
  python scrape.py --models tesla/model-3 dacia/spring   # prova su pochi modelli
  python scrape.py --debug               # salva l'HTML grezzo in debug/
Output: data/ev_ita.csv, data/ev_ita.json, data/scartate.csv, index.html
"""
import argparse, csv, json, os, re, sys, time
from datetime import date
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

BASE = "https://www.quattroruote.it"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
FIELDS = ["modello", "allestimento", "tipo", "posti", "cap", "h", "w", "l", "m", "pomol",
          "ppeak", "cons", "vmax", "prezzo", "anno", "autonomia", "autonomia_fonte", "stato", "url"]

sess = requests.Session()
sess.headers.update({"User-Agent": UA, "Accept-Language": "it-IT,it;q=0.9"})
ARGS = None


def fetch(url, tries=4):
    for i in range(tries):
        try:
            r = sess.get(url, timeout=30)
            if r.status_code == 200:
                time.sleep(ARGS.delay)
                return r.text
            print(f"  HTTP {r.status_code} per {url}", file=sys.stderr)
            if r.status_code in (403, 429):
                time.sleep(10 * (i + 1))
        except requests.RequestException as e:
            print(f"  errore rete {e}", file=sys.stderr)
            time.sleep(5 * (i + 1))
    return None


def dump(name, html):
    if ARGS.debug and html:
        os.makedirs("debug", exist_ok=True)
        with open(os.path.join("debug", re.sub(r"\W+", "_", name)[:120] + ".html"), "w", encoding="utf-8") as f:
            f.write(html)


# ---------- scoperta dei modelli (serve un browser: la lista si carica con JS) ----------
def discover_models():
    from playwright.sync_api import sync_playwright
    found = set()
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_context(user_agent=UA, locale="it-IT").new_page()
        pg.goto(BASE + "/listino/ricerca.html", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(3000)
        for txt in ("Accetta", "Accetta tutto", "Accetto"):  # cookie banner
            try:
                pg.get_by_role("button", name=re.compile(txt, re.I)).first.click(timeout=2000)
                break
            except Exception:
                pass
        # tenta di filtrare su "elettrica"; se non riesce si scansiona tutto il listino
        try:
            pg.get_by_text(re.compile(r"^\s*elettrica\s*$", re.I)).first.click(timeout=4000)
            pg.wait_for_timeout(3000)
            print("Filtro 'elettrica' applicato")
        except Exception:
            print("ATTENZIONE: filtro 'elettrica' non applicato, scansiono tutti i modelli (molto piu' lento)")
        for _ in range(400):
            try:
                btn = pg.get_by_text(re.compile(r"Carica altri modelli", re.I)).first
                if not btn.is_visible():
                    break
                btn.click(timeout=5000)
                pg.wait_for_timeout(1200)
            except Exception:
                break
        dump("ricerca", pg.content())
        for a in pg.query_selector_all("a[href]"):
            h = a.get_attribute("href") or ""
            m = re.match(r"^(?:https://www\.quattroruote\.it)?/listino/([^/?#]+)/([^/?#]+)/?$", h)
            if m:
                found.add(f"{m.group(1)}/{m.group(2)}")
        b.close()
    return sorted(found)


# ---------- pagina modello: elenco allestimenti + stato ----------
def model_versions(model):
    html = fetch(f"{BASE}/listino/{model}")
    if not html:
        return {}
    dump("modello_" + model, html)
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    pages = [soup]
    for a in soup.find_all("a", string=re.compile(r"Tutti gli allestimenti", re.I)):  # elenco completo
        h2 = fetch(urljoin(BASE, a["href"]))
        if h2:
            pages.append(BeautifulSoup(h2, "html.parser"))
    pat = re.compile(r"^(?:https://www\.quattroruote\.it)?/auto/" + re.escape(model) + r"/[^/?#]+$")
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
    return out


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
    title = soup.find("h1")
    d["allestimento"] = title.get_text(" ", strip=True) if title else None
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


def discover_from_sitemap(since):
    """Ritorna {marca/modello: [(aaaamm, url), ...]} per i modelli con almeno una versione >= since."""
    import html as H
    urls = []
    for n in (1, 2, 3, 4, 5):
        t = fetch(f"{BASE}/Sitemap-listino-{n}.xml")
        if not t:
            if n > 3:
                break
            continue
        urls += re.findall(r"<loc>\s*(https://www\.quattroruote\.it/auto/[^<\s]+)\s*</loc>", t)
    models = {}
    for u in urls:
        u = H.unescape(u)
        m = re.match(r"https://www\.quattroruote\.it/auto/([^/]+)/([^/]+)/[^/]+?(\d{6})$", u)
        if m:
            models.setdefault(f"{m.group(1)}/{m.group(2)}", []).append((int(m.group(3)), u))
    models = {k: v for k, v in models.items() if max(x[0] for x in v) >= since}
    print(f"Sitemap: {len(urls)} URL totali, {len(models)} modelli con versioni dal {since}")
    return models


def sample_urls(vers, full):
    vers = sorted(vers, reverse=True)
    if full:
        return [u for _, u in vers]
    pick = [u for _, u in vers[:2]] + [u for _, u in vers if HINT.search(u.rsplit("/", 1)[-1])][:3]
    pick.append(vers[len(vers) // 2][1])
    return list(dict.fromkeys(pick))


CACHE = {}


def get_version(url):
    if url not in CACHE:
        html = fetch(url)
        if html is None:
            CACHE[url] = None
        else:
            dump("allest_" + url.rsplit("/", 1)[-1], html)
            CACHE[url] = parse_version(url, html)
    return CACHE[url]


def main():
    global ARGS
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", help="es. tesla/model-3 dacia/spring (prova su pochi modelli)")
    ap.add_argument("--limit", type=int, help="max modelli (per prove)")
    ap.add_argument("--delay", type=float, default=1.0, help="secondi tra richieste")
    ap.add_argument("--since", type=int, default=202301, help="considera modelli con versioni da aaaamm")
    ap.add_argument("--full", action="store_true", help="controlla ogni versione di ogni modello (molto lento)")
    ap.add_argument("--browser", action="store_true", help="scoperta con Playwright invece della sitemap")
    ap.add_argument("--debug", action="store_true")
    ARGS = ap.parse_args()
    smap = {}
    if ARGS.models:
        models = ARGS.models
    elif ARGS.browser:
        models = discover_models()
    else:
        smap = discover_from_sitemap(ARGS.since)
        models = sorted(smap)
        if not models:
            sys.exit("ERRORE: nessun modello trovato dalla sitemap. File esistenti NON modificati.")
    if ARGS.limit:
        models = models[:ARGS.limit]
    print(f"{len(models)} modelli da controllare")
    rows, scartate = [], []
    for i, mod in enumerate(models, 1):
        # 1) il modello ha almeno un allestimento BEV? (campione di versioni, o tutte con --full)
        if mod in smap:
            sample = sample_urls(smap[mod], ARGS.full)
            if not any((CACHE.get(u) or get_version(u) or {}).get("_bev") for u in sample):
                print(f"[{i}/{len(models)}] {mod}: nessun BEV nel campione")
                continue
        print(f"[{i}/{len(models)}] {mod}")
        # 2) tutti gli allestimenti dalla pagina modello (+ quelli in sitemap), con lo stato
        vers = model_versions(mod)
        for _, u in smap.get(mod, []):
            vers.setdefault(u, "disponibile")
        marca, nome = mod.split("/", 1)
        for url, stato in vers.items():
            d = get_version(url)
            if d is None:
                scartate.append({"url": url, "motivo": "pagina non scaricata"})
                continue
            if not d.get("_bev"):
                scartate.append({"url": url, "motivo": "non BEV (o scheda non riconosciuta)"})
                continue
            d = dict(d)
            d["allestimento"] = re.sub(r"^" + re.escape(marca) + r"\s+", "", d["allestimento"] or "", flags=re.I)
            d["modello"] = f"{marca.upper()} {nome}"
            d["stato"] = stato
            rows.append({k: d.get(k) for k in FIELDS})
    if not rows:
        sys.exit("ERRORE: 0 allestimenti BEV trovati. File esistenti NON modificati (controlla debug/).")
    os.makedirs("data", exist_ok=True)
    with open("data/ev_ita.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, FIELDS, delimiter=";")
        w.writeheader(); w.writerows(rows)
    with open("data/ev_ita.json", "w", encoding="utf-8") as f:
        json.dump({"aggiornato": date.today().isoformat(), "righe": rows}, f, ensure_ascii=False, indent=1)
    with open("data/scartate.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, ["url", "motivo"], delimiter=";")
        w.writeheader(); w.writerows(scartate)
    import build_html
    build_html.build()
    print(f"Fatto: {len(rows)} allestimenti BEV, {len(scartate)} scartati (vedi data/scartate.csv)")


if __name__ == "__main__":
    main()
