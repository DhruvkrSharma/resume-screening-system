"""
Skill extraction module using NLP and pattern matching
Author: Gladiator2005
Date: 2025-11-09
"""

import re
import logging
from functools import lru_cache
import spacy
from spacy.matcher import PhraseMatcher

try:
    from config import SKILLS_DB, SPACY_MODEL
except ImportError:
    SPACY_MODEL = "en_core_web_sm"
    SKILLS_DB = [
        "python", "java", "sql", "react", "docker", "kubernetes"
    ]

logger = logging.getLogger(__name__)


@lru_cache(maxsize=2)
def _safe_load_spacy_model(model_name: str):
    """
    Try to load a spaCy model.
    If unavailable, fall back to blank('en') to keep runtime resilient.
    """
    try:
        return spacy.load(model_name)
    except OSError:
        logger.warning(
            "spaCy model '%s' not found. Falling back to blank English pipeline.",
            model_name
        )
        return spacy.blank("en")


class SkillExtractor:
    """Extract skills from text using multiple methods"""

    def __init__(self, skills_list=None, model_name: str = None):
        self.skills = [s.strip().lower() for s in (skills_list or SKILLS_DB) if s.strip()]
        chosen_model = model_name or SPACY_MODEL
        self.nlp = _safe_load_spacy_model(chosen_model)

        # Phrase matcher on lowercase for robust exact matching
        self.matcher = PhraseMatcher(self.nlp.vocab, attr="LOWER")
        patterns = [self.nlp.make_doc(skill) for skill in self.skills]
        if patterns:
            self.matcher.add("SKILLS", patterns)

    def extract_technical_skills_line(self, text):
        """Extract skills from an explicit 'Technical Skills:' line, if present."""
        if not text:
            return []

        m = re.search(r"technical skills\s*[:\-]\s*(.+)", text, flags=re.I)
        if not m:
            # Line-by-line fallback with tolerant matching
            for line in text.splitlines():
                if re.match(r"^\s*technical skills\s*[:\-]?", line, flags=re.I):
                    remainder = re.sub(r"^\s*technical skills\s*[:\-]?\s*", "", line, flags=re.I)
                    if remainder:
                        m = re.match(r"(.+)", remainder)
                        break

        if not m:
            return []

        skills_text = m.group(1)
        parts = re.split(r"[,;•\n]+", skills_text)
        parts = [p.strip() for p in parts if p.strip()]
        return parts

    def extract_skills(self, text):
        """
        Combined strategies:
        1) PhraseMatcher
        2) Regex-based well-known variants (e.g., DBs)
        3) 'Technical Skills:' line parsing
        4) Noun chunk fallback (best-effort)
        """
        if not text:
            return []

        doc = self.nlp(text)
        found = set()

        # 1) PhraseMatcher
        matches = self.matcher(doc)
        for _, start, end in matches:
            found.add(doc[start:end].text.lower().strip())

        # 2) Regex variants
        db_variants = ["postgresql", "postgres", "mysql", "mongodb", "oracle", "sql server"]
        for pat in db_variants:
            if re.search(r"\b" + re.escape(pat) + r"\b", text, flags=re.I):
                found.add(pat.lower())

        # 3) Technical Skills line
        for s in self.extract_technical_skills_line(text):
            found.add(s.lower())

        # 4) Noun-chunk best effort
        if not found and hasattr(doc, "noun_chunks"):
            for chunk in doc.noun_chunks:
                ctext = chunk.text.lower().strip()
                if len(ctext) >= 3 and any(tok.lemma_.lower() in self.skills for tok in chunk):
                    found.add(ctext)

        return sorted(found)


if __name__ == "__main__":
    sample_text = """
    Technical Skills: Python, React, Docker, Kubernetes; PostgreSQL
    Experienced building REST APIs with Flask and deploying via Docker and Kubernetes.
    """
    extractor = SkillExtractor()
    print(extractor.extract_skills(sample_text))
