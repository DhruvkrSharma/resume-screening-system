"""
Main resume screening engine
Author: Gladiator2005
Date: 2025-11-09
"""

import logging
from pathlib import Path
from pdf_extractor import extract_text_from_pdf
from skill_extractor import SkillExtractor
from semantic_matcher import SemanticMatcher
from database import ResumeDatabase
from config import SKILLS_DB, INTERNSHIP_ROLE_TEMPLATES

logger = logging.getLogger(__name__)

class ResumeScreener:
    """Main resume screening engine"""
    
    def __init__(self):
        """Initialize components"""
        self.db = ResumeDatabase()
        self.skill_extractor = None
        self.semantic_matcher = None

    def _get_skill_extractor(self):
        if self.skill_extractor is None:
            self.skill_extractor = SkillExtractor(SKILLS_DB)
        return self.skill_extractor

    def _get_semantic_matcher(self):
        if self.semantic_matcher is None:
            self.semantic_matcher = SemanticMatcher()
        return self.semantic_matcher
    
    def add_role_from_text(self, name, job_text):
        """Add role by extracting skills from job description"""
        skills = self._get_skill_extractor().extract_skills(job_text)
        skills_text = "; ".join(skills)
        self.db.add_role(name, skills_text)
        logger.info("Role '%s' saved with %d extracted skills", name, len(skills))
        return skills
    
    def add_role_manual(self, name, skills_list):
        """Add role with manually specified skills"""
        skills_text = "; ".join([s.strip().lower() for s in skills_list if s.strip()])
        self.db.add_role(name, skills_text)
        logger.info("Role '%s' saved with %d manual skills", name, len(skills_text.split("; ")))
        return skills_text.split("; ")
    
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
                logger.info("Extracting resume from: %s", path)
                text = extract_text_from_pdf(path)
                method = "extracted"
                logger.info("Extraction method=%s length=%d", method, len(text or ""))
                
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
        skill_extractor = self._get_skill_extractor()
        semantic_matcher = self._get_semantic_matcher()
        resume_skills_exact = [skill_extractor.extract_skills(t) for t in resumes_texts]
        
        logger.info("Computing semantic matches (threshold=%s)", semantic_threshold)
        semantic_matches = semantic_matcher.compute_skill_matches(job_skills, resumes_texts, threshold=semantic_threshold)
        
        logger.info("Computing similarity scores")
        sim_scores = semantic_matcher.compute_similarity_scores(role_text, resumes_texts)
        
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

    def _normalize_skills(self, skills):
        return sorted({s.strip().lower() for s in skills if s and s.strip()})

    def extract_resume_text(self, pdf_path):
        """Extract text from a PDF path."""
        return extract_text_from_pdf(pdf_path) or ""

    def list_internship_role_names(self):
        """Return available built-in internship role names."""
        return [item["name"] for item in INTERNSHIP_ROLE_TEMPLATES]

    def build_resume_profile(self, resume_text):
        """Extract a normalized profile from resume text."""
        skills = self._normalize_skills(self._get_skill_extractor().extract_skills(resume_text or ""))
        return {
            "skills": skills,
            "summary_seed": " ".join((resume_text or "").strip().split())[:450],
        }

    def match_internship_roles(self, resume_text, top_n=3):
        """Match one resume text against built-in internship templates."""
        profile = self.build_resume_profile(resume_text)
        top_n = max(1, int(top_n))
        resume_text = resume_text or ""
        matches = []

        for template in INTERNSHIP_ROLE_TEMPLATES:
            required = self._normalize_skills(template.get("required_skills", []))
            matched = sorted(set(required).intersection(profile["skills"]))
            missing = sorted(set(required).difference(profile["skills"]))
            skill_score = (len(matched) / len(required)) if required else 0.0
            semantic_score = float(
                self._get_semantic_matcher().compute_similarity_scores(
                    f"{template['name']} {template['description']} {' '.join(required)}",
                    [resume_text],
                )[0]
            )
            combined_score = round((0.7 * skill_score) + (0.3 * max(0.0, semantic_score)), 4)
            matches.append(
                {
                    "role_name": template["name"],
                    "score": combined_score,
                    "matched_skills": matched,
                    "missing_skills": missing,
                    "description": template["description"],
                }
            )

        matches.sort(key=lambda item: (-item["score"], len(item["missing_skills"]), item["role_name"]))
        return {"profile": profile, "matches": matches[:top_n]}

    def match_internships_for_resumes(self, pdf_paths, top_n=3):
        """Run resume-only internship matching directly from uploaded PDFs."""
        output = []
        for path in pdf_paths:
            if not path or not Path(path).exists():
                logger.warning("Skipping missing PDF for internship matching: %s", path)
                continue
            text = self.extract_resume_text(path)
            match_data = self.match_internship_roles(text, top_n=top_n)
            output.append(
                {
                    "pdf_path": path,
                    "resume_text": text,
                    "profile": match_data["profile"],
                    "matches": match_data["matches"],
                }
            )
        return output

    def generate_tailored_documents(self, resume_text, internship_role_name):
        """Generate deterministic tailored resume and CV drafts."""
        role = next(
            (item for item in INTERNSHIP_ROLE_TEMPLATES if item["name"] == internship_role_name),
            None,
        )
        if role is None:
            raise ValueError(f"Internship role '{internship_role_name}' not found")

        profile = self.build_resume_profile(resume_text)
        required = self._normalize_skills(role.get("required_skills", []))
        matched = sorted(set(required).intersection(profile["skills"]))
        missing = sorted(set(required).difference(profile["skills"]))
        strengths = ", ".join(matched[:8]) if matched else "Foundational software and analytical skills"
        focus_areas = ", ".join(missing[:6]) if missing else "role-specific project outcomes"

        tailored_resume = (
            f"Generated Draft Resume (for {role['name']})\n"
            "NOTE: This is AI-generated content and should be reviewed before use.\n\n"
            "Professional Summary:\n"
            f"Candidate aligned to {role['name']} with demonstrated strengths in {strengths}.\n\n"
            "Targeted Skills:\n"
            f"- Matched: {', '.join(matched) if matched else 'No direct matches found'}\n"
            f"- Suggested to strengthen: {focus_areas}\n\n"
            "Project Highlights (Draft bullets):\n"
            "- Built practical solutions using modern engineering practices and collaborative workflows.\n"
            "- Applied data-driven decision making to improve product or model quality.\n"
            "- Communicated technical outcomes clearly with stakeholders and mentors.\n"
        )

        tailored_cv = (
            f"Generated Draft CV (for {role['name']})\n"
            "NOTE: This is AI-generated content and should be reviewed before use.\n\n"
            "Profile:\n"
            f"Applying for {role['name']}. Relevant capability areas include {strengths}.\n\n"
            "Core Competencies:\n"
            f"{', '.join(matched) if matched else 'General internship readiness'}\n\n"
            "Development Plan:\n"
            f"Prioritize upskilling in: {focus_areas}.\n"
        )

        return {
            "profile": profile,
            "matched_skills": matched,
            "missing_skills": missing,
            "tailored_resume": tailored_resume,
            "tailored_cv": tailored_cv,
        }
