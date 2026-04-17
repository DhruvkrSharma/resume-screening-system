"""
Main resume screening engine
Author: Gladiator2005
Date: 2025-11-09
"""

from pathlib import Path
import logging
from pdf_extractor import extract_text_from_pdf
from skill_extractor import SkillExtractor
from semantic_matcher import SemanticMatcher
from database import ResumeDatabase
from config import SKILLS_DB

logger = logging.getLogger(__name__)


class ResumeScreener:
    """Main resume screening engine"""
    
    def __init__(self):
        """Initialize components"""
        self.db = ResumeDatabase()
        self.skill_extractor = SkillExtractor(SKILLS_DB)
        self.semantic_matcher = SemanticMatcher()
    
    def add_role_from_text(self, name, job_text):
        """Add role by extracting skills from job description"""
        skills = self.skill_extractor.extract_skills(job_text)
        skills_text = "; ".join(skills)
        self.db.add_role(name, skills_text)
        logger.info("Role '%s' saved with %d extracted skill(s)", name, len(skills))
        return skills
    
    def add_role_manual(self, name, skills_list):
        """Add role with manually specified skills"""
        normalized = []
        seen = set()
        for skill in skills_list:
            value = skill.strip().lower()
            if value and value not in seen:
                seen.add(value)
                normalized.append(value)
        skills_text = "; ".join(normalized)
        self.db.add_role(name, skills_text)
        logger.info("Role '%s' saved with %d manual skill(s)", name, len(normalized))
        return normalized
    
    def screen_resumes(self, role_id, pdf_paths, semantic_threshold=0.45, skip_missing=True, use_fallback=False, fallbacks=None):
        """Screen multiple resumes for a role"""
        role = self.db.get_role(role_id)
        if not role:
            raise ValueError(f"Role id {role_id} not found")
        
        job_skills = role["skills"]
        role_text = " ".join(job_skills) if job_skills else role["name"]
        
        resumes_texts = []
        extraction_methods = []
        resume_ids = []
        valid_paths = []
        fallbacks = fallbacks or [None] * len(pdf_paths)
        
        for i, path in enumerate(pdf_paths):
            if not path or not Path(path).exists():
                msg = f"[WARN] PDF not found: {path}"
                if skip_missing:
                    logger.warning("%s -- skipping", msg)
                    continue
                else:
                    logger.warning("%s -- using fallback/empty", msg)
                    text = fallbacks[i] if (use_fallback and i < len(fallbacks) and fallbacks[i]) else ""
                    method = "fallback" if text else None
            else:
                logger.info("Extracting PDF: %s", path)
                text = extract_text_from_pdf(path)
                method = "extracted"
                logger.info("Extraction method=%s text_length=%d", method, len(text or ""))
                
                if (not text or len(text.strip()) == 0) and use_fallback and i < len(fallbacks) and fallbacks[i]:
                    text = fallbacks[i]
                    method = "fallback"
            
            resume_id = self.db.add_resume(path, text or "", method)
            resume_ids.append(resume_id)
            resumes_texts.append(text or "")
            extraction_methods.append(method)
            valid_paths.append(path)
        
        if not resumes_texts:
            logger.info("No resumes to screen")
            return []
        
        logger.info("Extracting skills from %d resume(s)", len(resumes_texts))
        resume_skills_exact = [self.skill_extractor.extract_skills(t) for t in resumes_texts]
        
        logger.info("Computing semantic matches (threshold=%s)", semantic_threshold)
        semantic_matches = self.semantic_matcher.compute_skill_matches(job_skills, resumes_texts, threshold=semantic_threshold)
        
        logger.info("Computing similarity scores")
        sim_scores = self.semantic_matcher.compute_similarity_scores(role_text, resumes_texts)
        
        results = []
        for rid, path, exact, sem, sim, method in zip(resume_ids, valid_paths, resume_skills_exact, semantic_matches, sim_scores, extraction_methods):
            union = sorted(set([s.lower() for s in exact]).union({s.lower() for s in sem}))
            matched_skills_text = "; ".join(union)
            num_matched = len(union)
            similarity_score = float(sim)
            
            self.db.add_result(role_id, rid, matched_skills_text, num_matched, similarity_score)
            
            results.append({
                "resume_id": rid,
                "pdf_path": path,
                "extraction_method": method,
                "matched_skills": matched_skills_text,
                "num_matched_skills": num_matched,
                "similarity_score": similarity_score
            })
        
        logger.info("Screening complete. Processed %d resume(s)", len(results))
        return results
