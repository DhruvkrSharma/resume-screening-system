"""
Semantic matching using sentence transformers
Author: Gladiator2005
Date: 2025-11-09
"""

import logging
import re
from functools import lru_cache
from sentence_transformers import SentenceTransformer, util
from config import SENTENCE_TRANSFORMER_MODEL, DEFAULT_SEMANTIC_THRESHOLD

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_sentence_model(model_name):
    return SentenceTransformer(model_name)


class SemanticMatcher:
    def __init__(self):
        try:
            self.model = _load_sentence_model(SENTENCE_TRANSFORMER_MODEL)
            self._fallback_mode = False
        except (OSError, RuntimeError, ValueError):
            logger.exception(
                "Could not initialize sentence-transformer model '%s'. Falling back to token-overlap matcher.",
                SENTENCE_TRANSFORMER_MODEL
            )
            self.model = None
            self._fallback_mode = True

    @staticmethod
    def _tokenize(text):
        return set(re.findall(r"[a-zA-Z0-9+#.]+", (text or "").lower()))

    def _fallback_skill_matches(self, job_skills, resumes_texts):
        matched = []
        for resume_text in resumes_texts:
            resume_tokens = self._tokenize(resume_text)
            matched_skills = []
            for skill in job_skills:
                skill_tokens = self._tokenize(skill)
                if skill_tokens and skill_tokens.issubset(resume_tokens):
                    matched_skills.append(skill)
            matched.append(sorted(set(matched_skills)))
        return matched

    def _fallback_similarity_scores(self, role_text, resumes_texts):
        role_tokens = self._tokenize(role_text)
        scores = []
        for resume_text in resumes_texts:
            resume_tokens = self._tokenize(resume_text)
            union = role_tokens.union(resume_tokens)
            score = 0.0 if not union else len(role_tokens.intersection(resume_tokens)) / len(union)
            scores.append(float(score))
        return scores
    
    def compute_skill_matches(self, job_skills, resumes_texts, threshold=DEFAULT_SEMANTIC_THRESHOLD):
        if not job_skills or not resumes_texts:
            return [[] for _ in resumes_texts]
        if self._fallback_mode:
            return self._fallback_skill_matches(job_skills, resumes_texts)
        
        skill_emb = self.model.encode(job_skills, convert_to_tensor=True)
        resume_emb = self.model.encode(resumes_texts, convert_to_tensor=True)
        sim_matrix = util.pytorch_cos_sim(skill_emb, resume_emb).cpu().numpy()
        
        matched = []
        for j in range(sim_matrix.shape[1]):
            matched_skills = []
            for i, skill in enumerate(job_skills):
                if sim_matrix[i, j] >= threshold:
                    matched_skills.append(skill)
            matched.append(sorted(set(matched_skills)))
        
        return matched
    
    def compute_similarity_scores(self, role_text, resumes_texts):
        if not resumes_texts:
            return []
        if self._fallback_mode:
            return self._fallback_similarity_scores(role_text, resumes_texts)
        
        role_emb = self.model.encode([role_text], convert_to_tensor=True)
        resume_emb = self.model.encode(resumes_texts, convert_to_tensor=True)
        
        return util.pytorch_cos_sim(role_emb, resume_emb).cpu().numpy().flatten()
