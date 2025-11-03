import re
import time
from pathlib import Path
from typing import Dict, List, Any
import requests
from bs4 import BeautifulSoup

# Ajusta si tu proyecto usa otra carpeta
CACHE_DIR = Path("data/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Relativity-Releases-FAQ/1.0 (+https://localhost)"
}

# ====== NUEVOS LINKS + base ======
_VERSION_URLS: Dict[str, List[str]] = {
    "Server2023": [
        # Links que enviaste
        "https://help.relativity.com/Server2023/Content/CoveoSearch.htm",
        "https://help.relativity.com/Server2023/Content/Installing_and_Upgrading/Relativity_Upgrade/Upgrading_or_installing_Relativity_Analytics.htm",
        "https://help.relativity.com/Server2023/Content/Installing_and_Upgrading/Relativity_Upgrade/Upgrading_workspaces.htm",
        "https://help.relativity.com/Server2023/Content/Installing_and_Upgrading/Relativity_Upgrade/Upgrading_Relativity_Service_Bus.htm",
        "https://help.relativity.com/Server2023/Content/Installing_and_Upgrading/Relativity_Upgrade/Upgrading_your_agent_server.htm",
        "https://help.relativity.com/Server2023/Content/Installing_and_Upgrading/Relativity_Upgrade/Upgrading_your_web_server.htm",
        "https://help.relativity.com/Server2023/Content/Site_Resources/Products.htm",
        "https://help.relativity.com/Server2023/Content/Relativity/Analytics/Analytics.htm",
        "https://help.relativity.com/Server2023/Content/Solutions/Solving_review_case_challenges_with_Analytics/Solving_review_case_challenges_with_Analytics.htm",
        "https://help.relativity.com/Server2023/Content/Solutions/Solving_review_case_challenges_with_Analytics/Implementing_clustering_with_batching.htm",
        "https://help.relativity.com/Server2023/Content/Solutions/Solving_review_case_challenges_with_Analytics/Implementing_categorization.htm",
        "https://help.relativity.com/Server2023/Content/Solutions/Solving_review_case_challenges_with_Analytics/Finding_similar_documents.htm",
        "https://help.relativity.com/Server2023/Content/Solutions/Solving_review_case_challenges_with_Analytics/Using_keyword_expansion.htm",
    ],
    "RelativityOne": [
        "https://help.relativity.com/RelativityOne/Content/Relativity/Staging_Area.htm",
        "https://help.relativity.com/RelativityOne/Content/Relativity/Integration_Points/Azure_AD_provider.htm",
        "https://help.relativity.com/RelativityOne/Content/Site_Resources/Data_transfer.htm",
        "https://help.relativity.com/RelativityOne/Content/Relativity/Workspaces/Workspaces.htm",
    ],
    # Mantén tus otras versiones aquí
    "Server2024": [
        # agrega aquí los que ya tenías si aplica
    ],
}

def _dedupe(seq: List[str]) -> List[str]:
    seen = set(); out = []
    for u in seq:
        if u and u not in seen:
            seen.add(u); out.append(u)
    return out

def get_version_urls(version: str) -> List[str]:
    urls = _VERSION_URLS.get(version, [])
    return _dedupe(urls)

# --------- Fetch helpers ----------
def _cache_path(url: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", url)[:180]
    return CACHE_DIR / f"{safe}.html"

def fetch_html(url: str, use_cache: bool = True) -> str:
    p = _cache_path(url)
    if use_cache and p.exists():
        return p.read_text(encoding="utf-8", errors="ignore")
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    html = r.text
    p.write_text(html, encoding="utf-8", errors="ignore")
    time.sleep(0.5)  # ser amable
    return html

# --------- Parse helpers ----------
def clean_text(t: str) -> str:
    t = re.sub(r"\s+", " ", t or "").strip()
    return t

def extract_sections(url: str) -> List[Dict[str, Any]]:
    html = fetch_html(url)
    soup = BeautifulSoup(html, "lxml")

    # Título de la página
    page_title = clean_text(
        (soup.find("h1").get_text() if soup.find("h1") else soup.title.get_text() if soup.title else "")
    )

    # Contenido principal
    main = soup.find("main") or soup.find("div", {"id": "main"}) or soup

    # Reglas: dividir por h2/h3
    sections: List[Dict[str, Any]] = []
    current_heading = None
    current_chunks: List[str] = []

    def flush_section():
        if not current_heading: return
        content = clean_text(" ".join(current_chunks))
        if not content: return
        sections.append({
            "title": page_title,
            "heading": current_heading,
            "url": url,
            "content": content
        })

    for el in main.descendants:
        if getattr(el, "name", None) in ("h2", "h3"):
            # cierro sección previa
            flush_section()
            current_heading = clean_text(el.get_text())
            current_chunks = []
        elif getattr(el, "name", None) in ("p", "li"):
            txt = clean_text(el.get_text())
            if txt:
                current_chunks.append(txt)

    # última sección
    flush_section()

    # Si no detectó secciones, crea una genérica con párrafos
    if not sections:
        body_txt = " ".join([clean_text(p.get_text()) for p in main.find_all("p")])
        if body_txt:
            sections.append({
                "title": page_title,
                "heading": page_title or "Full Page",
                "url": url,
                "content": body_txt
            })

    # filtro rápido de basura
    cleaned = []
    seen = set()
    for s in sections:
        h = (s.get("heading") or "").strip()
        if not h or h.lower() in {"full page", "error"}:
            continue
        key = (s["title"], h, s["url"])
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(s)

    return cleaned

# --------- Public API used by qa_engine ----------
def build_index_for_version(version: str, force: bool = False) -> Dict[str, Any]:
    urls = get_version_urls(version)
    sections: List[Dict[str, Any]] = []
    for u in urls:
        try:
            sections.extend(extract_sections(u))
        except Exception as e:
            print(f"[scraper] Failed: {u} -> {e}")
    # retorno en el formato esperado por qa_engine
    return {"sections": sections}

def ensure_all_indexes() -> Dict[str, int]:
    """Útil si quieres forzar todos."""
    stats = {}
    for v in _VERSION_URLS.keys():
        try:
            data = build_index_for_version(v, force=True)
            stats[v] = len(data.get("sections", []))
        except Exception as e:
            print(f"[scraper] ensure_all_indexes error on {v}: {e}")
            stats[v] = 0
    return stats
