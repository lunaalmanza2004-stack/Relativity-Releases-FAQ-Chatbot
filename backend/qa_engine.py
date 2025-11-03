import os
from typing import List, Dict, Any, Tuple
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel
import joblib

from .scraper import build_index_for_version

INDEX_DIR = Path("data/index")
INDEX_DIR.mkdir(parents=True, exist_ok=True)

def _trim_complete(text: str, limit: int = 1200) -> str:
    """
    Recorta cerca del límite pero respetando el final de oración.
    No agrega '...' para que no parezca truncado.
    """
    if len(text) <= limit:
        return text
    cut = text[:limit]
    last_dot = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if last_dot > 200:  # asegura que no quede demasiado corto
        return cut[:last_dot+1].strip()
    return cut.strip()  # como fallback

class QAIndex:
    def __init__(self, version: str):
        self.version = version
        self.sections: List[Dict[str,Any]] = []
        self.vectorizer = None
        self.matrix = None

    def fit(self, sections: List[Dict[str,Any]]):
        self.sections = [s for s in sections if s.get("content")]
        corpus = [s["content"][:20000] for s in self.sections]  # corpus más grande
        self.vectorizer = TfidfVectorizer(ngram_range=(1,2), max_df=0.9, min_df=1, stop_words="english")
        self.matrix = self.vectorizer.fit_transform(corpus)

    def search(self, query: str, top_k: int = 5) -> List[Tuple[float, Dict[str,Any]]]:
        if not self.sections or self.matrix is None:
            return []
        qvec = self.vectorizer.transform([query])
        sims = linear_kernel(qvec, self.matrix).flatten()
        ranked_idx = sims.argsort()[::-1][:top_k]
        return [(float(sims[i]), self.sections[i]) for i in ranked_idx]

    def save(self):
        joblib.dump({
            "version": self.version,
            "sections": self.sections,
            "vectorizer": self.vectorizer,
            "matrix": self.matrix
        }, INDEX_DIR / f"{self.version}.joblib")

    @staticmethod
    def load(version: str):
        path = INDEX_DIR / f"{version}.joblib"
        if not path.exists():
            return None
        obj = joblib.load(path)
        qi = QAIndex(version=obj["version"])
        qi.sections = obj["sections"]
        qi.vectorizer = obj["vectorizer"]
        qi.matrix = obj["matrix"]
        return qi

def ensure_index(version: str, force: bool=False) -> QAIndex:
    qi = None if force else QAIndex.load(version)
    if qi is not None and not force:
        return qi
    data = build_index_for_version(version, force=force)
    qi = QAIndex(version)
    qi.fit(data["sections"])
    qi.save()
    return qi

def answer_question(query: str, version: str, top_k: int = 5) -> Dict[str, Any]:
    qi = ensure_index(version, force=False)
    matches = qi.search(query, top_k=top_k)
    if not matches:
        return {
            "answer": "I couldn’t find this in the official Relativity release notes. Please provide your contact information so our team can follow up.",
            "citations": [],
            "confidence": 0.0,
            "should_collect_contact": True
        }

    best_score = matches[0][0]
    snippets = []
    citations = []
    for score, sec in matches:
        if score < 0.08:
            continue
        short = _trim_complete(sec["content"], limit=1400)  # ✅ sin '...'
        # poner cada sección en viñeta
        snippets.append(f"— {short}")
        citations.append({"title": f'{sec.get("title","")}: {sec.get("heading","")}', "url": sec["url"], "score": score})

    if not snippets:
        return {
            "answer": "I couldn’t find this in the official Relativity release notes. Please provide your contact information so our team can follow up.",
            "citations": [],
            "confidence": float(best_score),
            "should_collect_contact": True
        }

    answer_text = "Here’s what the Relativity release notes say:\n\n" + "\n\n".join(snippets)
    should_collect = best_score < 0.18
    return {
        "answer": answer_text,
        "citations": citations[:3],
        "confidence": float(best_score),
        "should_collect_contact": should_collect
    }

def list_sections(version: str) -> List[Dict[str,Any]]:
    qi = ensure_index(version, force=False)
    seen = set()
    out = []
    for s in qi.sections:
        h = s.get("heading","").strip()
        if h and h not in seen:
            out.append({"heading": h, "url": s["url"]})
            seen.add(h)
    return out[:500]
