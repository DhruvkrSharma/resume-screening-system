"""
Database operations for resume screening system
Author: Gladiator2005
Date: 2025-11-09
"""

import sqlite3
from datetime import datetime, timezone
import pandas as pd
from config import DB_PATH


class ResumeDatabase:
    """Handle all database operations"""
    
    def __init__(self, db_path=DB_PATH):
        """Initialize database connection and create tables"""
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Create database tables if they don't exist"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                skills_text TEXT,
                created_at TEXT
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS resumes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pdf_path TEXT,
                text_snippet TEXT,
                extraction_method TEXT,
                extracted_at TEXT
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_id INTEGER,
                resume_id INTEGER,
                matched_skills TEXT,
                num_matched_skills INTEGER,
                similarity_score REAL,
                created_at TEXT,
                FOREIGN KEY(role_id) REFERENCES roles(id),
                FOREIGN KEY(resume_id) REFERENCES resumes(id)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def add_role(self, name, skills_text):
        """Add or update a role"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO roles (name, skills_text, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                skills_text=excluded.skills_text
            """
            , (name, skills_text, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        conn.close()
    
    def get_role(self, role_id):
        """Get role by ID"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT id, name, skills_text FROM roles WHERE id=?", (role_id,))
        row = cur.fetchone()
        conn.close()
        
        if not row:
            return None
        
        skills = [s.strip() for s in row[2].split(";") if s.strip()]
        return {"id": row[0], "name": row[1], "skills": skills}
    
    def list_roles(self):
        """Get all roles as DataFrame"""
        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql("SELECT * FROM roles ORDER BY id", conn)
        conn.close()
        return df
    
    def delete_role(self, role_id):
        """Delete role and associated results"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("DELETE FROM results WHERE role_id=?", (role_id,))
        cur.execute("DELETE FROM roles WHERE id=?", (role_id,))
        conn.commit()
        conn.close()
    
    def add_resume(self, pdf_path, text_snippet, extraction_method):
        """Add resume to database"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO resumes (pdf_path, text_snippet, extraction_method, extracted_at) VALUES (?, ?, ?, ?)"
            , (pdf_path, text_snippet[:1000], extraction_method, datetime.now(timezone.utc).isoformat())
        )
        resume_id = cur.lastrowid
        conn.commit()
        conn.close()
        return resume_id
    
    def get_resume(self, resume_id):
        """Get resume by ID"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT pdf_path, text_snippet FROM resumes WHERE id=?", (resume_id,))
        row = cur.fetchone()
        conn.close()
        return row if row else None
    
    def add_result(self, role_id, resume_id, matched_skills, num_matched, similarity_score):
        """Add screening result"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO results (role_id, resume_id, matched_skills, num_matched_skills, similarity_score, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (role_id, resume_id, matched_skills, num_matched, similarity_score, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        conn.close()
    
    def get_results_for_role(self, role_id, top_n=None):
        """Get screening results for a role"""
        conn = sqlite3.connect(self.db_path)
        query = """
            SELECT 
                r.id as result_id,
                ro.name as role_name,
                re.pdf_path,
                r.matched_skills,
                r.num_matched_skills,
                r.similarity_score,
                re.extraction_method,
                r.created_at
            FROM results r
            JOIN roles ro ON r.role_id = ro.id
            JOIN resumes re ON r.resume_id = re.id
            WHERE r.role_id = ?
            ORDER BY r.num_matched_skills DESC, r.similarity_score DESC
        """
        params = [role_id]
        if top_n is not None:
            try:
                limit = int(top_n)
            except (TypeError, ValueError) as exc:
                raise ValueError("top_n must be an integer") from exc
            if limit <= 0:
                raise ValueError("top_n must be positive")
            query += " LIMIT ?"
            params.append(limit)
        
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        return df
