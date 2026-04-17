"""
Semantic matching using sentence transformers
Author: Gladiator2005
Date: 2025-11-09
"""

import logging
import re
from sentence_transformers import SentenceTransformer, util
from config import SENTENCE_TRANSFORMER_MODEL, DEFAULT_SEMANTIC_THRESHOLD

class SemanticMatcher:
    def __init__(self):
        self.model = None
        try:
            self.model = SentenceTransformer(SENTENCE_TRANSFORMER_MODEL)
        except Exception:
            logging.getLogger(__name__).warning(
                "SentenceTransformer model '%s' could not be loaded. Falling back to lexical matching.",
                SENTENCE_TRANSFORMER_MODEL
            )

    def _tokenize(self, text):
        """Tokenize text for lexical fallback scoring when transformer model is unavailable."""
        return set(re.findall(r"\b[a-z0-9+\-#\.]{2,}\b", (text or "").lower()))
    
    def compute_skill_matches(self, job_skills, resumes_texts, threshold=DEFAULT_SEMANTIC_THRESHOLD):
        if not job_skills or not resumes_texts:
            return [[] for _ in resumes_texts]
        if self.model is None:
            matched = []
            for resume_text in resumes_texts:
                text_l = (resume_text or "").lower()
                matched_skills = [skill for skill in job_skills if skill.lower() in text_l]
                matched.append(sorted(set(matched_skills)))
            return matched
        
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
        if self.model is None:
            role_tokens = self._tokenize(role_text)
            scores = []
            for resume_text in resumes_texts:
                resume_tokens = self._tokenize(resume_text)
                union = role_tokens.union(resume_tokens)
                scores.append(len(role_tokens.intersection(resume_tokens)) / len(union) if union else 0.0)
            return scores
        
        role_emb = self.model.encode([role_text], convert_to_tensor=True)
        resume_emb = self.model.encode(resumes_texts, convert_to_tensor=True)
        
        return util.pytorch_cos_sim(role_emb, resume_emb).cpu().numpy().flatten()
