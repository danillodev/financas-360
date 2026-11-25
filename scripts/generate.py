#!/usr/bin/env python3
"""Finanças 360: gera o post diário (comando `post`) e o site estático (comando `build`)."""
import html, json, os, re, shutil, sys, time, unicodedata, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRT = timezone(timedelta(hours=-3))
SITE = json.loads((ROOT / "config/site.json").read_text("utf-8"))
CATS = SITE["categorias"]
POSTS_DIR = ROOT / "data/posts"
OUT = ROOT / "_site"
esc = lambda s: html.escape(str(s), quote=True)

def log(msg):
    line = f"{datetime.now(BRT):%Y-%m-%d %H:%M:%S} {msg}"
    print(line, file=sys.stderr)
    with open(ROOT / "logs/errors.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")

def slugify(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

STOP = set("para como mais com uma uns das dos pelo pela sobre entre apos ate sua seu nao sao foi ser tem pode vai por que".split())
def toks(s): return {w for w in slugify(s).split("-") if len(w) > 3 and w not in STOP}
def overlap(a, b):
    a, b = toks(a), toks(b)
    n = len(a & b)
    return n / max(1, min(len(a), len(b))) if n >= 3 else 0

KW = {
    "investimentos": ["investiment", "bolsa", "ibovespa", "acoes", "fii", "tesouro", "renda fixa", "cdb", "dividendo", "selic", "etf", "fundo"],
    "cartoes-e-bancos": ["cartao", "cartoes", "banco", "nubank", "c6", "pix", "credito", "limite", "conta digital", "inter "],
    "fintechs": ["fintech", "open finance", "drex", "cripto", "bitcoin", "inteligencia artificial", "tecnologia"],
    "financas-pessoais": ["fgts", "inss", "aposentad", "imposto de renda", "irpf", "salario", "divida", "endivid", "orcamento", "consumidor", "renegoci", "cpf"],
    "empreendedorismo": ["mei", "empreend", "startup", "pequenas empresas", "micro", "pme", "negocio"],
    "economize": ["desconto", "promocao", "black friday", "cashback", "economizar", "oferta"],
    "economia": ["pib", "inflacao", "ipca", "juros", "dolar", "fiscal", "copom", "banco central", "emprego", "desemprego"],
}
def classify(text):
    t = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    best = max(KW, key=lambda c: sum(t.count(k) for k in KW[c]))
    return best if sum(t.count(k) for k in KW[best]) else "economia"

EVERGREEN = [
    ("Como montar uma reserva de emergência passo a passo", "financas-pessoais"),
    ("Cartão de crédito: como funciona a fatura e os juros do rotativo", "cartoes-e-bancos"),
    ("Tesouro Direto para iniciantes: Selic, IPCA+ e prefixado", "investimentos"),
    ("O que é CDI e como ele afeta seus rendimentos", "investimentos"),
    ("Como sair das dívidas: método para priorizar o que pagar primeiro", "financas-pessoais"),
    ("MEI: direitos, limites de faturamento e obrigações mensais", "empreendedorismo"),
    ("Pix: como funciona e como se proteger de golpes", "fintechs"),
    ("Banco digital ou banco tradicional: o que comparar antes de escolher", "cartoes-e-bancos"),
    ("Regra 50-30-20: como organizar o orçamento mensal", "financas-pessoais"),
    ("Inflação e poder de compra: o que muda no seu bolso", "economia"),
    ("Como funciona o cashback e quando ele realmente compensa", "economize"),
    ("Open Finance: o que é e como compartilhar seus dados com segurança", "fintechs"),
    ("Fundos imobiliários (FIIs): como funcionam os rendimentos", "investimentos"),
    ("Como declarar investimentos no Imposto de Renda", "financas-pessoais"),
    ("Score de crédito: o que influencia e como melhorar", "financas-pessoais"),
    ("Fluxo de caixa para pequenos negócios: o básico que evita sustos", "empreendedorismo"),
    ("Como comparar ofertas e evitar armadilhas de promoções", "economize"),
    ("Diversificação: por que não colocar tudo no mesmo investimento", "investimentos"),
]

# ---------- coleta de notícias ----------
def http(url, data=None, headers=None, timeout=25):
    h = {"User-Agent": "Mozilla/5.0 (Financas360 bot)"}; h.update(headers or {})
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h), timeout=timeout) as r:
        return r.read()

def clean(s): return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()

def parse_feed(raw):
    root, out = ET.fromstring(raw), []
    for it in root.iter():
        tag = it.tag.split("}")[-1]
        if tag not in ("item", "entry"): continue
        g = lambda n: next((c for c in it if c.tag.split("}")[-1] == n), None)
        title, link = g("title"), g("link")
        href = (link.get("href") or link.text) if link is not None else ""
        summ = g("description") if g("description") is not None else g("summary")
        d = g("pubDate") if g("pubDate") is not None else (g("published") if g("published") is not None else g("updated"))
        try:
            dt = parsedate_to_datetime(d.text) if d is not None and "," in (d.text or "") else datetime.fromisoformat(d.text.replace("Z", "+00:00"))
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        except Exception: dt = datetime.now(timezone.utc)
        if title is not None and title.text and href:
            out.append({"title": clean(title.text), "link": href.strip(), "summary": clean(summ.text if summ is not None else "")[:700], "date": dt})
    return out

def collect():
    items = []
    for f in json.loads((ROOT / "config/feeds.json").read_text("utf-8")):
        try:
            for i in parse_feed(http(f["url"])):
                i["source"], i["official"] = f["nome"], f["oficial"]; items.append(i)
        except Exception as e:
            log(f"AVISO feed {f['nome']}: {e}")
    return items

# ---------- dados ----------
def load_posts():
    ps = [json.loads(p.read_text("utf-8")) for p in POSTS_DIR.glob("*.json")]
    return sorted(ps, key=lambda p: p["date"], reverse=True)

def seen_path(): return ROOT / "data/seen.json"
def load_seen():
    return json.loads(seen_path().read_text("utf-8")) if seen_path().exists() else {"urls": [], "topics": []}

def pick(items, posts, seen):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    recent = [i for i in items if i["date"] >= cutoff and i["link"] not in seen["urls"]]
    last_cats = [p["category"] for p in posts[:3]]
    best, best_score = None, 0
    for i in recent:
        if any(overlap(i["title"], p["title"]) >= 0.5 for p in posts[:60]): continue
        others = {o["source"] for o in recent if o["source"] != i["source"] and overlap(i["title"], o["title"]) >= 0.5}
        if not others and not i["official"]: continue   # exige confirmação: 2+ fontes ou fonte oficial
        i["cat"] = classify(i["title"] + " " + i["summary"])
        i["confirm"] = [o for o in recent if o["source"] in others and overlap(i["title"], o["title"]) >= 0.5]
        score = len(others) * 2 + (3 if i["official"] else 0) + (1 if i["summary"] else 0) - (2 if i["cat"] in last_cats else 0)
        if score > best_score: best, best_score = i, score
    return best

# ---------- IA (GitHub Models gratuito, ou qualquer API compatível com OpenAI) ----------
def ai_json(system, user):
    key = os.environ.get("AI_API_KEY") or os.environ.get("GITHUB_TOKEN")
    if not key: raise RuntimeError("Sem AI_API_KEY/GITHUB_TOKEN")
    url = os.environ.get("AI_ENDPOINT", "https://models.github.ai/inference/chat/completions")
    body = {"model": os.environ.get("AI_MODEL", SITE["ai_model"]), "temperature": 0.5,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    raw = http(url, json.dumps(body).encode(), {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, 90)
    return json.loads(json.loads(raw)["choices"][0]["message"]["content"])

SYSTEM = ("Você é editor de um portal brasileiro de finanças. Escreva em português do Brasil, linguagem simples e direta, "
          "texto 100% original (nunca copie frases das fontes). Use SOMENTE fatos presentes no material fornecido; "
          "não invente números, datas, nomes ou citações; se algo não estiver claro, não afirme. Não dê recomendação "
          "personalizada de investimento. Responda apenas JSON com as chaves: titulo (até 85 caracteres, atrativo e sem exagero), "
          "descricao (até 155 caracteres), palavras_chave (lista de 5 a 8), corpo_html (350 a 550 palavras, apenas tags "
          "<p>, <h2>, <ul>, <li>, <strong>; inclua uma seção 'O que muda para você' e uma seção 'Pontos de atenção').")

def write_news(item):
    mat = "\n".join(f"- {s['source']}: {s['title']}. {s['summary']}" for s in [item] + item["confirm"][:3])
    return ai_json(SYSTEM, f"Escreva um artigo sobre este fato noticiado hoje.\nMaterial das fontes:\n{mat}")

def write_evergreen(topic):
    return ai_json(SYSTEM, f"Escreva um guia educativo atemporal sobre: {topic}. Não cite notícias, datas recentes nem taxas atuais; explique conceitos e dê exemplos numéricos simples e claramente hipotéticos.")

SAFE = re.compile(r"</?(?!(?:p|h2|ul|li|strong)\b)[^>]*>", re.I)
def sanitize(h):
    h = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", h, flags=re.S | re.I)
    h = SAFE.sub("", h)
    return re.sub(r"<(p|h2|ul|li|strong)\b[^>]*>", r"<\1>", h, flags=re.I)

def make_post():
    posts, seen = load_posts(), load_seen()
    today = datetime.now(BRT).strftime("%Y-%m-%d")
    if posts and posts[0]["date"][:10] == today and not os.environ.get("FORCE"):
        print("Já existe post de hoje; nada a fazer."); return
    item = pick(collect(), posts, seen)
    if item: data, cat, sources = write_news(item), item["cat"], [{"name": s["source"], "url": s["link"]} for s in [item] + item["confirm"][:2]]
    else:
        log("AVISO sem notícia confirmada; publicando guia atemporal")
        topic, cat = next(((t, c) for t, c in EVERGREEN if t not in seen["topics"]), EVERGREEN[len(posts) % len(EVERGREEN)])
        data, sources = write_evergreen(topic), []
        seen["topics"].append(topic)
    body = sanitize(data["corpo_html"])
    if len(re.sub(r"<[^>]+>", " ", body).split()) < 150: raise RuntimeError("Texto gerado curto demais")
    title = clean(data["titulo"])[:95]
    slug = slugify(title)[:70]
    post = {"slug": slug, "title": title, "description": clean(data["descricao"])[:160], "category": cat,
            "keywords": [clean(k) for k in data.get("palavras_chave", [])][:8], "date": datetime.now(BRT).isoformat(timespec="seconds"),
            "body_html": body, "sources": sources}
    (POSTS_DIR / f"{today}-{slug}.json").write_text(json.dumps(post, ensure_ascii=False, indent=1), "utf-8")
    if item: seen["urls"] = (seen["urls"] + [s["link"] for s in [item] + item["confirm"]])[-800:]
    seen_path().write_text(json.dumps(seen, ensure_ascii=False, indent=1), "utf-8")
    print("Publicado:", title)

# ---------- afiliados ----------
PLAT = {"amazon": "Amazon", "mercadolivre": "Mercado Livre", "shopee": "Shopee"}
def offers():
    cfg, res = json.loads((ROOT / "config/affiliates.json").read_text("utf-8")), []
    for it in cfg["itens"]:
        url = it.get("url", "").strip()
        if not url and it["plataforma"] == "amazon" and cfg.get("amazon_tag") and it.get("busca"):
            url = "https://www.amazon.com.br/s?" + urllib.parse.urlencode({"k": it["busca"], "tag": cfg["amazon_tag"]})
        if url: res.append({**it, "url": url})
    return res

def offer_card(o):
    return (f'<a class="offer" href="{esc(o["url"])}" target="_blank" rel="sponsored nofollow noopener">'
            f'<span class="plat p-{o["plataforma"]}">{PLAT[o["plataforma"]]}</span><strong>{esc(o["titulo"])}</strong>'
            f'<span class="od">{esc(o["desc"])}</span><em>Ver oferta</em></a>')

def pick_offers(allo, cat, n=3):
    pool, out, used = [o for o in allo if cat in o["categorias"]] or allo, [], set()
    for o in pool:
        if o["plataforma"] not in used: out.append(o); used.add(o["plataforma"])
    return (out + [o for o in pool if o not in out])[:n]

# ---------- páginas ----------
BASE_URL = os.environ.get("BASE_URL", SITE["base_url"]).rstrip("/")
BP = urllib.parse.urlparse(BASE_URL).path.rstrip("/")
def u(p=""): return f"{BP}/{p}"
def abs_u(p=""): return f"{BASE_URL}/{p}"
def fdate(iso): return datetime.fromisoformat(iso).strftime("%d/%m/%Y")
MESES = None

LOGO = ('<svg class="logo-ring" viewBox="0 0 40 40" aria-hidden="true"><circle cx="20" cy="20" r="16" fill="none" stroke="#0B3C49" stroke-width="5"/>'
        '<path d="M20 4a16 16 0 0 1 16 16" fill="none" stroke="#E8A317" stroke-width="5" stroke-linecap="round"/></svg>')

def cover_svg(post):
    h = (sum(map(ord, post["category"])) * 37) % 360
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630"><rect width="1200" height="630" fill="hsl({h},45%,22%)"/>'
            f'<circle cx="980" cy="200" r="260" fill="none" stroke="hsl({(h+40)%360},70%,60%)" stroke-width="46" opacity=".5"/>'
            f'<path d="M980 -60A260 260 0 0 1 1240 200" fill="none" stroke="#E8A317" stroke-width="46" stroke-linecap="round"/>'
            f'<text x="70" y="540" font-family="Arial,sans-serif" font-weight="700" font-size="54" fill="#fff" opacity=".9">{esc(CATS[post["category"]]["nome"])}</text></svg>')

def layout(title, desc, path, body, og_type="website", jsonld="", img=None):
    cats = "".join(f'<a href="{u("categoria/"+s+"/")}">{esc(c["nome"])}</a>' for s, c in CATS.items())
    social = "".join(f'<a href="{esc(v)}" target="_blank" rel="noopener me">{k.replace("_"," ").title()}</a>' for k, v in SITE["redes"].items() if v)
    ga = SITE.get("google_analytics_id")
    gat = (f'<script async src="https://www.googletagmanager.com/gtag/js?id={esc(ga)}"></script><script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}gtag("js",new Date());gtag("config","{esc(ga)}")</script>' if ga else "")
    full = title if path == "" else f"{title} | {SITE['nome']}"
    image = abs_u(img or "assets/og.svg")
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(full)}</title><meta name="description" content="{esc(desc)}"><link rel="canonical" href="{abs_u(path)}">
<meta property="og:title" content="{esc(full)}"><meta property="og:description" content="{esc(desc)}"><meta property="og:type" content="{og_type}"><meta property="og:url" content="{abs_u(path)}"><meta property="og:image" content="{image}"><meta property="og:locale" content="pt_BR"><meta name="twitter:card" content="summary_large_image">
<link rel="alternate" type="application/rss+xml" title="{esc(SITE['nome'])}" href="{u('feed.xml')}"><link rel="icon" href="{u('assets/favicon.svg')}" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700;12..96,800&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{u('assets/style.css')}">{jsonld}{gat}</head><body>
<a class="skip" href="#main">Ir para o conteúdo</a>
<header class="top"><div class="wrap bar"><a class="brand" href="{u()}">{LOGO}<span>Finanças <b>360</b></span></a>
<form class="search" action="{u('busca/')}" role="search"><input type="search" name="q" placeholder="Buscar artigos" aria-label="Buscar artigos"><button>Buscar</button></form>
<button class="burger" aria-label="Menu" aria-expanded="false" data-menu>Menu</button></div>
<nav class="cats" id="nav"><div class="wrap">{cats}<a href="{u('ofertas/')}" class="hot">Ofertas</a></div></nav></header>
<main id="main">{body}</main>
<footer><div class="wrap fgrid"><div><strong>{esc(SITE['nome'])}</strong><p>{esc(SITE['slogan'])}.</p><div class="soc">{social}</div></div>
<div><strong>Institucional</strong><a href="{u('sobre/')}">Sobre o projeto</a><a href="{u('contato/')}">Contato</a><a href="{u('privacidade/')}">Política de privacidade</a><a href="{u('divulgacao-de-afiliados/')}">Divulgação de afiliados</a></div>
<div><strong>Aviso</strong><p>Conteúdo informativo, sem recomendação de investimento. Alguns links são de afiliados: podemos receber comissão sem custo extra para você.</p></div></div>
<div class="wrap copy">© {datetime.now(BRT).year} {esc(SITE['nome'])}</div></footer><script src="{u('assets/app.js')}" defer></script></body></html>'''

def write(path, content):
    p = OUT / path; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content, "utf-8")

def post_card(p, big=False):
    return (f'<article class="card{" big" if big else ""}"><a href="{u("artigos/"+p["slug"]+"/")}"><img src="{u("assets/img/"+p["slug"]+".svg")}" alt="" loading="lazy" width="1200" height="630">'
            f'<span class="tag">{esc(CATS[p["category"]]["nome"])}</span><h3>{esc(p["title"])}</h3><p>{esc(p["description"])}</p><time datetime="{p["date"][:10]}">{fdate(p["date"])}</time></a></article>')

def shares(p):
    url, t = urllib.parse.quote(abs_u(f"artigos/{p['slug']}/")), urllib.parse.quote(p["title"])
    L = [("WhatsApp", f"https://wa.me/?text={t}%20{url}"), ("Telegram", f"https://t.me/share/url?url={url}&text={t}"),
         ("X", f"https://twitter.com/intent/tweet?text={t}&url={url}"), ("Facebook", f"https://www.facebook.com/sharer/sharer.php?u={url}"),
         ("LinkedIn", f"https://www.linkedin.com/sharing/share-offsite/?url={url}")]
    return '<div class="share"><span>Compartilhar</span>' + "".join(f'<a href="{a}" target="_blank" rel="noopener">{n}</a>' for n, a in L) + "</div>"

def build():
    posts, allo = load_posts(), offers()
    if OUT.exists(): shutil.rmtree(OUT)
    shutil.copytree(ROOT / "assets", OUT / "assets")
    (OUT / ".nojekyll").write_text("")
    for p in posts: write(f"assets/img/{p['slug']}.svg", cover_svg(p))
    # artigos
    for i, p in enumerate(posts):
        rel = [q for q in posts if q["category"] == p["category"] and q is not p][:3] or [q for q in posts if q is not p][:3]
        src = ("<h2>Fontes consultadas</h2><ul>" + "".join(f'<li><a href="{esc(s["url"])}" rel="nofollow noopener" target="_blank">{esc(s["name"])}</a></li>' for s in p["sources"]) + "</ul>") if p["sources"] else ""
        oc = pick_offers(allo, p["category"])
        box = ('<aside class="offers-box"><h2>Para ir além</h2><div class="offers">' + "".join(map(offer_card, oc)) + '</div><p class="fine">Links de afiliados: podemos receber comissão se você comprar, sem custo extra.</p></aside>') if oc else ""
        warn = '<p class="fine">Este texto é informativo e não constitui recomendação de investimento.</p>' if p["category"] in ("investimentos", "economia", "fintechs") else ""
        ld = '<script type="application/ld+json">' + json.dumps({"@context": "https://schema.org", "@type": "NewsArticle", "headline": p["title"], "description": p["description"], "datePublished": p["date"], "image": [abs_u(f"assets/img/{p['slug']}.svg")], "author": {"@type": "Organization", "name": SITE["nome"]}, "publisher": {"@type": "Organization", "name": SITE["nome"]}, "mainEntityOfPage": abs_u(f"artigos/{p['slug']}/")}, ensure_ascii=False) + "</script>"
        body = (f'<div class="wrap art"><nav class="crumb"><a href="{u()}">Início</a> / <a href="{u("categoria/"+p["category"]+"/")}">{esc(CATS[p["category"]]["nome"])}</a></nav>'
                f'<h1>{esc(p["title"])}</h1><p class="lead">{esc(p["description"])}</p><p class="meta">Publicado em <time datetime="{p["date"]}">{fdate(p["date"])}</time> · {esc(SITE["nome"])}</p>'
                f'<img class="hero-img" src="{u("assets/img/"+p["slug"]+".svg")}" alt="" width="1200" height="630"><div class="prose">{p["body_html"]}{src}{warn}</div>{shares(p)}{box}'
                f'<section class="more"><h2>Leia também</h2><div class="grid">{"".join(post_card(q) for q in rel)}</div></section></div>')
        write(f"artigos/{p['slug']}/index.html", layout(p["title"], p["description"], f"artigos/{p['slug']}/", body, "article", ld, f"assets/img/{p['slug']}.svg"))
    # home
    if posts:
        top, side, rest = posts[0], posts[1:5], posts[5:17]
        hero = f'<section class="hero wrap"><div class="main-feature">{post_card(top, True)}</div><aside class="today"><h2>Mais recentes</h2>' + "".join(f'<a href="{u("artigos/"+p["slug"]+"/")}"><span>{esc(CATS[p["category"]]["nome"])}</span>{esc(p["title"])}</a>' for p in side) + "</aside></section>"
        grid = f'<section class="wrap"><h2 class="sec">Últimas notícias</h2><div class="grid">{"".join(post_card(p) for p in rest)}</div></section>' if rest else ""
    else:
        hero, grid = '<section class="wrap empty"><h1>Finanças 360</h1><p>O primeiro conteúdo será publicado hoje às 08h (Brasília).</p></section>', ""
    oh = (f'<section class="wrap"><h2 class="sec">Ofertas selecionadas</h2><div class="offers">{"".join(map(offer_card, allo[:6]))}</div><p class="fine">Links de afiliados. <a href="{u("divulgacao-de-afiliados/")}">Saiba mais</a>.</p></section>') if allo else ""
    chips = "".join(f'<a href="{u("categoria/"+s+"/")}"><strong>{esc(c["nome"])}</strong><span>{esc(c["desc"])}</span></a>' for s, c in CATS.items())
    write("index.html", layout(f"{SITE['nome']}: {SITE['slogan']}", SITE["descricao"], "", hero + grid + oh + f'<section class="wrap"><h2 class="sec">Explore por tema</h2><div class="chips">{chips}</div></section>'))
    # categorias
    for s, c in CATS.items():
        ps = [p for p in posts if p["category"] == s]
        body = f'<div class="wrap"><h1 class="ph">{esc(c["nome"])}</h1><p class="lead">{esc(c["desc"])}</p><div class="grid">{"".join(post_card(p) for p in ps) or "<p>Em breve, novos conteúdos nesta categoria.</p>"}</div></div>'
        write(f"categoria/{s}/index.html", layout(c["nome"], c["desc"], f"categoria/{s}/", body))
    # ofertas
    sec = "".join(f'<h2 class="sec">{PLAT[k]}</h2><div class="offers">{"".join(offer_card(o) for o in allo if o["plataforma"] == k)}</div>' for k in PLAT if any(o["plataforma"] == k for o in allo))
    write("ofertas/index.html", layout("Ofertas e produtos recomendados", "Livros, ferramentas e ofertas selecionadas na Amazon, Mercado Livre e Shopee.", "ofertas/",
          f'<div class="wrap"><h1 class="ph">Ofertas e produtos recomendados</h1><p class="lead">Seleção ligada aos temas do portal. Preços e disponibilidade mudam: confira na loja. Links de afiliados.</p>{sec or "<p>Em breve.</p>"}</div>'))
    # busca
    write("busca/index.html", layout("Buscar artigos", "Pesquise artigos do Finanças 360.", "busca/", '<div class="wrap"><h1 class="ph">Buscar artigos</h1><form class="search big" role="search"><input type="search" id="q" placeholder="Digite um assunto" autofocus><button>Buscar</button></form><div id="res" class="grid"></div></div>'))
    write("search.json", json.dumps([{"t": p["title"], "d": p["description"], "u": u(f"artigos/{p['slug']}/"), "c": CATS[p["category"]]["nome"], "k": " ".join(p["keywords"])} for p in posts], ensure_ascii=False))
    for slug, (t, d, h) in PAGES().items(): write(f"{slug}/index.html", layout(t, d, f"{slug}/", f'<div class="wrap art"><h1>{t}</h1><div class="prose">{h}</div></div>'))
    write("404.html", layout("Página não encontrada", "Página não encontrada.", "404.html", f'<div class="wrap empty"><h1>Página não encontrada</h1><p><a href="{u()}">Voltar ao início</a></p></div>'))
    now = datetime.now(BRT)
    urls = [("", now.isoformat())] + [(f"artigos/{p['slug']}/", p["date"]) for p in posts] + [(f"categoria/{s}/", now.isoformat()) for s in CATS] + [(f"{x}/", now.isoformat()) for x in ["ofertas", "sobre", "contato", "privacidade", "divulgacao-de-afiliados"]]
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(f"<url><loc>{abs_u(a)}</loc><lastmod>{b[:10]}</lastmod></url>" for a, b in urls) + "</urlset>")
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {abs_u('sitemap.xml')}\n")
    write("feed.xml", f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{esc(SITE["nome"])}</title><link>{abs_u()}</link><description>{esc(SITE["descricao"])}</description><language>pt-BR</language>' + "".join(f'<item><title>{esc(p["title"])}</title><link>{abs_u("artigos/"+p["slug"]+"/")}</link><guid>{abs_u("artigos/"+p["slug"]+"/")}</guid><pubDate>{datetime.fromisoformat(p["date"]).strftime("%a, %d %b %Y %H:%M:%S %z")}</pubDate><description>{esc(p["description"])}</description></item>' for p in posts[:30]) + "</channel></rss>")
    print(f"Site gerado: {len(posts)} artigos")

def PAGES():
    n, em = esc(SITE["nome"]), esc(SITE["email"])
    form = (f'<form action="https://formspree.io/f/{esc(SITE["formspree_id"])}" method="post" class="cform"><label>Nome <input name="nome" required></label><label>E-mail <input type="email" name="email" required></label><label>Mensagem <textarea name="mensagem" rows="5" required></textarea></label><button>Enviar mensagem</button></form>' if SITE.get("formspree_id") else "")
    return {
        "sobre": ("Sobre o projeto", f"Conheça o {SITE['nome']}.", f"<p>O {n} é um portal de notícias e educação financeira em português. Nosso objetivo é explicar economia, investimentos, cartões, bancos digitais, fintechs e empreendedorismo com clareza.</p><h2>Como produzimos o conteúdo</h2><p>Acompanhamos veículos de imprensa e fontes oficiais. Só publicamos fatos confirmados por mais de uma fonte ou por fonte oficial, e sempre listamos as fontes consultadas ao final do texto. Os textos são redigidos com apoio de inteligência artificial e passam por regras automáticas de verificação e de duplicidade.</p><h2>Como nos mantemos</h2><p>Parte dos links do site é de afiliados (Amazon, Mercado Livre e Shopee). Quando você compra por eles, podemos receber uma comissão, sem custo extra. Isso não altera o conteúdo editorial. Veja a <a href='{u('divulgacao-de-afiliados/')}'>divulgação de afiliados</a>.</p><h2>Aviso</h2><p>O conteúdo é informativo e não substitui orientação profissional nem constitui recomendação de investimento.</p>"),
        "contato": ("Contato", "Fale com o Finanças 360.", f"<p>Sugestões, correções ou parcerias: <a href='mailto:{em}'>{em}</a>.</p>{form}"),
        "privacidade": ("Política de privacidade", "Como tratamos dados no Finanças 360.", f"<p>Esta política segue a Lei Geral de Proteção de Dados (LGPD, Lei 13.709/2018).</p><h2>Dados coletados</h2><p>O {n} não exige cadastro. Podemos coletar dados de navegação anônimos (páginas visitadas, tipo de dispositivo) por ferramentas de estatística, quando ativadas pelo responsável. Se você nos escreve, usamos seu e-mail apenas para responder.</p><h2>Cookies e terceiros</h2><p>Fontes tipográficas são carregadas do Google Fonts. Ao clicar em links de afiliados, Amazon, Mercado Livre e Shopee podem gravar cookies para atribuir a venda ao nosso link; eles têm suas próprias políticas de privacidade. Você pode bloquear cookies nas configurações do navegador.</p><h2>Seus direitos</h2><p>Você pode solicitar acesso, correção ou exclusão de dados pessoais pelo e-mail <a href='mailto:{em}'>{em}</a>.</p><h2>Hospedagem</h2><p>O site é hospedado no GitHub Pages, que pode registrar dados técnicos de acesso conforme a política do GitHub.</p>"),
        "divulgacao-de-afiliados": ("Divulgação de afiliados", "Como funcionam os links de afiliados do Finanças 360.", f"<p>O {n} participa de programas de afiliados da Amazon, do Mercado Livre e da Shopee. Ao comprar por links marcados como oferta, podemos receber comissão, sem custo adicional para você.</p><p>Como Associado da Amazon, ganhamos com compras qualificadas.</p><p>Indicamos produtos relacionados aos temas do site. Preços, estoque e condições são definidos pelas lojas e podem mudar; confira sempre na página do vendedor. Links de afiliados usam o atributo <code>rel=\"sponsored\"</code>.</p>"),
    }

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    try:
        {"post": make_post, "build": build}[cmd]()
    except Exception as e:
        log(f"ERRO {cmd}: {type(e).__name__}: {e}"); sys.exit(1)
