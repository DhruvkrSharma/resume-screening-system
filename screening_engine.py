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
from config import SKILLS_DB

logger = logging.getLogger(__name__)


class ResumeScreener:
    """Main resume screening engine"""
    
    def __init__(self):
        """Initialize components"""
        self.db = ResumeDatabase()
        self.skill_extractor = SkillExtractor(SKILLS_DB)
        self.semantic_matcher = SemanticMatcher()
        self.last_internship_resume_text = ""
    
    def add_role_from_text(self, name, job_text):
        """Add role by extracting skills from job description"""
        skills = self.skill_extractor.extract_skills(job_text)
        skills_text = "; ".join(skills)
        self.db.add_role(name, skills_text)
        logger.info("Role '%s' saved with %d extracted skills", name, len(skills))
        return skills
    
    def add_role_manual(self, name, skills_list):
        """Add role with manually specified skills"""
        skills_text = "; ".join(self.normalize_skills(skills_list))
        self.db.add_role(name, skills_text)
        logger.info("Role '%s' saved with %d manual skills", name, len(skills_text.split("; ")))
        return skills_text.split("; ")

    @staticmethod
    def normalize_skills(skills_list, min_count=1):
        """Normalize and deduplicate skill inputs while preserving order."""
        normalized = []
        seen = set()
        for raw_skill in skills_list or []:
            skill = str(raw_skill).strip().lower()
            if not skill or skill in seen:
                continue
            seen.add(skill)
            normalized.append(skill)
        if len(normalized) < min_count:
            raise ValueError(f"Please provide at least {min_count} valid, unique skill(s).")
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
                logger.info("Extracting resume text from %s", path)
                text = extract_text_from_pdf(path)
                method = "extracted"
                logger.info("Extraction method=%s, length=%d", method, len(text or ""))
                
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
        
        logger.info("Computing semantic matches with threshold=%s", semantic_threshold)
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
        
        logger.info("Screening complete: processed %d resume(s)", len(results))
        return sorted(
            results,
            key=lambda x: (-x["num_matched_skills"], -x["similarity_score"], x["resume_id"])
        )

    def find_resume_internship_matches(self, pdf_paths, semantic_threshold=0.45):
        """Resume-only internship matching flow against internship roles."""
        roles_df = self.db.list_roles()
        if roles_df.empty:
            return []

        internship_roles = roles_df[roles_df["name"].str.contains("intern", case=False, na=False)]
        if internship_roles.empty:
            internship_roles = roles_df

        path = next((p for p in (pdf_paths or []) if p and Path(p).exists()), None)
        if not path:
            raise ValueError("Please provide one valid resume PDF for internship matching.")

        resume_text = extract_text_from_pdf(path)
        if not resume_text or not resume_text.strip():
            raise ValueError("Could not extract text from the uploaded resume.")
        self.last_internship_resume_text = resume_text

        resume_skills = self.skill_extractor.extract_skills(resume_text)
        matches = []
        for _, role_row in internship_roles.iterrows():
            role = self.db.get_role(int(role_row["id"]))
            role_skills = role["skills"] if role else []
            role_text = " ".join(role_skills) if role_skills else role_row["name"]

            sem_matches = self.semantic_matcher.compute_skill_matches(
                role_skills,
                [resume_text],
                threshold=semantic_threshold
            )[0]
            similarity = float(self.semantic_matcher.compute_similarity_scores(role_text, [resume_text])[0])
            exact = {s for s in resume_skills if s in {rs.lower() for rs in role_skills}}
            matched = sorted(set(sem_matches).union(exact))
            matches.append({
                "role_id": int(role_row["id"]),
                "role_name": role_row["name"],
                "num_matched_skills": len(matched),
                "similarity_score": similarity,
                "matched_skills": "; ".join(matched)
            })

        return sorted(
            matches,
            key=lambda x: (-x["num_matched_skills"], -x["similarity_score"], x["role_id"])
        )

    def generate_tailored_resume_cv(self, resume_text, role_id):
        """Generate tailored resume and CV drafts for a selected position."""
        role = self.db.get_role(role_id)
        if not role:
            raise ValueError(f"Role id {role_id} not found")
        if not resume_text or not resume_text.strip():
            raise ValueError("Resume text is required to generate tailored drafts.")

        role_skills = [s.strip().lower() for s in role["skills"]]
        resume_skills = self.skill_extractor.extract_skills(resume_text)
        matched = [s for s in role_skills if s in set(resume_skills)]
        missing = [s for s in role_skills if s not in set(resume_skills)]

        resume_draft = (
            f"# Tailored Resume Draft – {role['name']}\n\n"
            "## Professional Summary\n"
            f"Candidate profile aligned for {role['name']} with focus on "
            f"{', '.join(matched[:5]) if matched else 'relevant transferable skills'}.\n\n"
            "## Core Skills\n"
            f"- Matched skills: {', '.join(matched) if matched else 'Add role-relevant skills from experience'}\n"
            f"- Priority skills to highlight next: {', '.join(missing[:8]) if missing else 'None'}\n\n"
            "## Experience Guidance\n"
            "- Quantify impact in internships/projects using metrics.\n"
            "- Use role-relevant keywords in bullet points.\n"
            "- Highlight tools/frameworks used in practical work.\n"
        )

        cv_draft = (
            f"# Tailored CV Draft – {role['name']}\n\n"
            "## Profile\n"
            f"Seeking {role['name']} opportunities with practical experience in "
            f"{', '.join(matched[:6]) if matched else 'software development and learning agility'}.\n\n"
            "## Skills Matrix\n"
            f"- Role skills covered: {len(matched)}/{len(role_skills)}\n"
            f"- Covered: {', '.join(matched) if matched else 'To be expanded'}\n"
            f"- Gap areas: {', '.join(missing[:10]) if missing else 'None'}\n\n"
            "## CV Focus Sections\n"
            "- Education and relevant coursework\n"
            "- Internship/project experience with measurable outcomes\n"
            "- Technical stack and certifications\n"
        )
        return {"resume_draft": resume_draft, "cv_draft": cv_draft}
