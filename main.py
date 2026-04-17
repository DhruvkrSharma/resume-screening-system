"""
Streamlit Frontend for Resume Screening System
Author: Gladiator2005
Date: 2025-11-09
Usage: streamlit run main.py
"""

import streamlit as st
import pandas as pd
import tempfile
import os
import logging
from screening_engine import ResumeScreener
from database import ResumeDatabase
import plotly.express as px
import sqlite3
from config import MAX_UPLOAD_SIZE_BYTES, MIN_MANUAL_SKILLS, REPO_URL, TOP_N_LIMIT_MAX

# Page configuration
st.set_page_config(
    page_title="AI Resume Screening System",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@st.cache_resource
def get_screener():
    """Cache heavy NLP/ML resources."""
    return ResumeScreener()


def normalize_skill_input(raw_text):
    """Normalize, trim, and deduplicate comma-separated skills."""
    normalized = []
    seen = set()
    for skill in raw_text.split(","):
        cleaned = skill.strip().lower()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            normalized.append(cleaned)
    return normalized


def validate_uploaded_pdfs(uploaded_files):
    """Validate uploaded PDFs by type/signature and file size."""
    valid_files = []
    errors = []
    for uploaded_file in uploaded_files:
        payload = uploaded_file.getvalue()
        is_pdf_signature = payload.startswith(b"%PDF-")
        is_pdf_type = uploaded_file.type in ("application/pdf", "")
        if not (is_pdf_signature and is_pdf_type):
            errors.append(f"{uploaded_file.name}: invalid PDF file")
            continue
        if len(payload) > MAX_UPLOAD_SIZE_BYTES:
            errors.append(
                f"{uploaded_file.name}: file too large ({len(payload)} bytes). "
                f"Max allowed is {MAX_UPLOAD_SIZE_BYTES} bytes"
            )
            continue
        valid_files.append(uploaded_file)
    return valid_files, errors

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        padding: 1rem 0;
    }
    .sub-header {
        font-size: 1.5rem;
        color: #555;
        text-align: center;
        margin-bottom: 2rem;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'screener' not in st.session_state:
    st.session_state.screener = get_screener()
if 'results' not in st.session_state:
    st.session_state.results = None

# Header
st.markdown('<div class="main-header">🎯 AI Resume Screening System</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Intelligent Resume Analysis with NLP & Semantic Matching</div>', unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.title("Navigation")
    page = st.radio(
        "Select Page",
        [
            "🏠 Home",
            "➕ Add Role",
            "📊 Screen Resumes",
            "🎯 Internship Matching",
            "📝 Tailored Resume/CV",
            "📈 View Results",
            "⚙️ Settings",
        ],
    )
    
    st.markdown("---")
    st.info("**Features:**\n- PDF Text Extraction\n- NLP Skill Matching\n- Semantic Analysis\n- Multi-Role Support")
    st.success("**Maintainer:** DhruvkrSharma\n**Date:** 2025-11-09")

# Home Page
if page == "🏠 Home":
    st.header("Welcome to AI Resume Screening System")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Roles", len(st.session_state.screener.db.list_roles()))
    
    with col2:
        db = ResumeDatabase()
        conn = db._connect()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM resumes")
        resume_count = cursor.fetchone()[0]
        conn.close()
        st.metric("Resumes Processed", resume_count)
    
    with col3:
        conn = db._connect()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM results")
        result_count = cursor.fetchone()[0]
        conn.close()
        st.metric("Screening Results", result_count)
    
    st.markdown("---")
    st.subheader("📋 Available Job Roles")
    roles_df = st.session_state.screener.db.list_roles()
    
    if not roles_df.empty:
        display_df = roles_df[['id', 'name', 'skills_text', 'created_at']].copy()
        display_df['created_at'] = pd.to_datetime(display_df['created_at']).dt.strftime('%Y-%m-%d %H:%M')
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("No roles added yet. Go to 'Add Role' to create your first job role.")

# Add Role Page
elif page == "➕ Add Role":
    st.header("Add New Job Role")
    
    tab1, tab2 = st.tabs(["📝 From Job Description", "✍️ Manual Entry"])
    
    with tab1:
        st.subheader("Extract Skills from Job Description")
        role_name = st.text_input("Job Role Name", placeholder="e.g., Senior Python Developer")
        job_description = st.text_area("Job Description", height=300, 
                                       placeholder="Paste the complete job description here...")
        
        if st.button("🚀 Add Role & Extract Skills", type="primary"):
            role_name_clean = (role_name or "").strip()
            job_description_clean = (job_description or "").strip()
            if role_name_clean and job_description_clean:
                with st.spinner("Extracting skills using NLP..."):
                    try:
                        skills = st.session_state.screener.add_role_from_text(role_name_clean, job_description_clean)
                        st.success(f"✅ Role '{role_name_clean}' added successfully!")
                        st.info(f"**Extracted {len(skills)} skills:** {', '.join(skills)}")
                    except (ValueError, sqlite3.Error, RuntimeError) as exc:
                        logger.exception("Failed to add role from job description")
                        st.error(f"Could not add role: {exc}")
            else:
                st.warning("Please fill in both role name and job description.")
    
    with tab2:
        st.subheader("Manually Enter Skills")
        manual_role_name = st.text_input("Job Role Name", key="manual_name")
        manual_skills = st.text_area("Skills (comma-separated)", height=150,
                                      placeholder="Python, Machine Learning, TensorFlow, SQL, AWS")
        
        if st.button("➕ Add Role", type="primary", key="manual_add"):
            manual_role_name_clean = (manual_role_name or "").strip()
            if manual_role_name_clean and manual_skills:
                with st.spinner("Adding role..."):
                    try:
                        skills_list = normalize_skill_input(manual_skills)
                        if len(skills_list) < MIN_MANUAL_SKILLS:
                            raise ValueError(
                                f"Please provide at least {MIN_MANUAL_SKILLS} valid skill(s)."
                            )
                        st.session_state.screener.add_role_manual(manual_role_name_clean, skills_list)
                        st.success(f"✅ Role '{manual_role_name_clean}' added with {len(skills_list)} skills!")
                    except (ValueError, sqlite3.Error, RuntimeError) as exc:
                        logger.exception("Failed to add role manually")
                        st.error(f"Could not add role: {exc}")
            else:
                st.warning("Please fill in both role name and skills.")

# Screen Resumes Page
elif page == "📊 Screen Resumes":
    st.header("Screen Resumes Against Job Roles")
    
    roles_df = st.session_state.screener.db.list_roles()
    
    if roles_df.empty:
        st.warning("⚠️ No roles available. Please add a role first.")
    else:
        role_options = {f"{row['name']} (ID: {row['id']})": row['id'] for _, row in roles_df.iterrows()}
        selected_role = st.selectbox("Select Job Role", options=list(role_options.keys()))
        role_id = role_options[selected_role]
        
        role = st.session_state.screener.db.get_role(role_id)
        with st.expander("📋 Role Details"):
            st.write(f"**Role Name:** {role['name']}")
            st.write(f"**Required Skills ({len(role['skills'])}):** {', '.join(role['skills'])}")
        
        st.markdown("---")
        st.subheader("📤 Upload Resumes")
        uploaded_files = st.file_uploader("Upload PDF resumes", type=['pdf'], 
                                          accept_multiple_files=True,
                                          help="Upload one or more PDF resume files")
        st.caption(
            "🔒 Privacy note: Uploaded resumes are used for screening within this app session."
        )
        
        col1, col2 = st.columns(2)
        with col1:
            semantic_threshold = st.slider("Semantic Matching Threshold", 0.0, 1.0, 0.45, 0.05,
                                          help="Lower = more matches, Higher = stricter")
        with col2:
            skip_missing = st.checkbox("Skip missing files", value=True)
        
        if st.button("🔍 Start Screening", type="primary", disabled=not uploaded_files):
            if uploaded_files:
                with st.spinner(f"Screening {len(uploaded_files)} resume(s)..."):
                    temp_paths = []
                    try:
                        valid_files, errors = validate_uploaded_pdfs(uploaded_files)
                        for error in errors:
                            st.warning(error)
                        if not valid_files:
                            raise ValueError("No valid PDF files available for screening.")

                        for uploaded_file in valid_files:
                            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                                tmp_file.write(uploaded_file.getvalue())
                                temp_paths.append(tmp_file.name)
                        
                        results = st.session_state.screener.screen_resumes(
                            role_id=role_id,
                            pdf_paths=temp_paths,
                            semantic_threshold=semantic_threshold,
                            skip_missing=skip_missing
                        )
                        
                        st.success(f"✅ Successfully screened {len(results)} resume(s)!")
                        
                        if results:
                            results_df = pd.DataFrame(results)
                            results_df = results_df.sort_values(
                                by=['num_matched_skills', 'similarity_score', 'resume_id'],
                                ascending=[False, False, True],
                                kind='mergesort',
                            )
                            
                            st.subheader("📊 Screening Results")
                            st.markdown("### 🏆 Top Candidates")
                            top_3 = results_df.head(3)
                            
                            cols = st.columns(min(3, len(top_3)))
                            for idx, (i, row) in enumerate(top_3.iterrows()):
                                with cols[idx]:
                                    st.metric(f"Rank {idx + 1}", 
                                             f"{row['num_matched_skills']} skills",
                                             f"{row['similarity_score']:.2%} match")
                                    st.caption(f"Resume ID: {row['resume_id']}")
                            
                            st.markdown("---")
                            st.markdown("### 📋 Detailed Results")
                            display_cols = ['resume_id', 'num_matched_skills', 'similarity_score', 
                                          'matched_skills', 'extraction_method']
                            st.dataframe(results_df[display_cols], use_container_width=True, hide_index=True)
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                fig = px.bar(results_df, x='resume_id', y='num_matched_skills',
                                           title='Skills Matched per Resume')
                                st.plotly_chart(fig, use_container_width=True)
                            
                            with col2:
                                fig = px.scatter(results_df, x='num_matched_skills', y='similarity_score',
                                               size='num_matched_skills', title='Skills vs Similarity Score')
                                st.plotly_chart(fig, use_container_width=True)
                    
                    except (ValueError, sqlite3.Error, RuntimeError, OSError) as exc:
                        logger.exception("Error during screening workflow")
                        st.error(f"Error during screening: {exc}")
                    finally:
                        for path in temp_paths:
                            try:
                                os.unlink(path)
                            except OSError:
                                logger.warning("Failed to delete temp file: %s", path)

# Internship Matching Page
elif page == "🎯 Internship Matching":
    st.header("Resume-Only Internship Matching")
    st.write("Upload resume(s) and get ranked internship matches with skill-gap insights.")
    st.caption("🔒 Privacy note: Uploaded resumes may contain sensitive information. Review outputs before sharing.")

    uploaded_files = st.file_uploader(
        "Upload PDF resume(s) for internship matching",
        type=["pdf"],
        accept_multiple_files=True,
        key="internship_upload",
    )
    top_n = st.slider("Top internship matches per resume", 1, 5, 3, key="internship_top_n")

    if st.button("🎯 Match Internship Roles", type="primary", disabled=not uploaded_files):
        temp_paths = []
        try:
            valid_files, errors = validate_uploaded_pdfs(uploaded_files)
            for error in errors:
                st.warning(error)
            if not valid_files:
                raise ValueError("No valid PDF files available for internship matching.")

            for uploaded_file in valid_files:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                    tmp_file.write(uploaded_file.getvalue())
                    temp_paths.append(tmp_file.name)

            match_results = st.session_state.screener.match_internships_for_resumes(temp_paths, top_n=top_n)
            st.session_state["internship_match_results"] = match_results

            if not match_results:
                st.info("No resumes were matched.")
            else:
                for idx, resume_result in enumerate(match_results, start=1):
                    st.markdown(f"### Resume {idx}")
                    profile = resume_result.get("profile", {})
                    st.write(f"**Extracted Skills ({len(profile.get('skills', []))}):** {', '.join(profile.get('skills', [])) or 'None'}")
                    table_rows = []
                    for rank, match in enumerate(resume_result.get("matches", []), start=1):
                        table_rows.append(
                            {
                                "rank": rank,
                                "role_name": match["role_name"],
                                "score": match["score"],
                                "missing_skills": ", ".join(match["missing_skills"]) or "None",
                            }
                        )
                    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)
        except (ValueError, RuntimeError, OSError) as exc:
            logger.exception("Internship matching failed")
            st.error(f"Internship matching failed: {exc}")
        finally:
            for path in temp_paths:
                try:
                    os.unlink(path)
                except OSError:
                    logger.warning("Failed to delete temp file: %s", path)

# Tailored Resume/CV Page
elif page == "📝 Tailored Resume/CV":
    st.header("Tailored Resume/CV Draft Generator")
    st.write("Generate deterministic draft text for a selected internship role based on your uploaded resume.")
    st.caption("🔒 Privacy note: Review generated text to remove sensitive details before external use.")

    uploaded_file = st.file_uploader(
        "Upload one PDF resume",
        type=["pdf"],
        accept_multiple_files=False,
        key="tailored_upload",
    )
    role_names = st.session_state.screener.list_internship_role_names()
    selected_role_name = st.selectbox("Select target internship role", role_names)

    if st.button("📝 Generate Tailored Drafts", type="primary", disabled=not uploaded_file):
        temp_paths = []
        try:
            valid_files, errors = validate_uploaded_pdfs([uploaded_file])
            for error in errors:
                st.warning(error)
            if not valid_files:
                raise ValueError("Uploaded resume is not a valid PDF.")

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                tmp_file.write(valid_files[0].getvalue())
                temp_paths.append(tmp_file.name)

            resume_text = st.session_state.screener.extract_resume_text(temp_paths[0])
            draft = st.session_state.screener.generate_tailored_documents(resume_text, selected_role_name)

            st.subheader("Extracted Profile")
            st.write(", ".join(draft["profile"]["skills"]) or "No skills extracted")

            st.subheader("Tailored Resume Draft")
            st.text_area("Generated Resume", value=draft["tailored_resume"], height=260)

            st.subheader("Tailored CV Draft")
            st.text_area("Generated CV", value=draft["tailored_cv"], height=220)
        except (ValueError, RuntimeError, OSError) as exc:
            logger.exception("Tailored document generation failed")
            st.error(f"Tailored document generation failed: {exc}")
        finally:
            for path in temp_paths:
                try:
                    os.unlink(path)
                except OSError:
                    logger.warning("Failed to delete temp file: %s", path)

# View Results Page
elif page == "📈 View Results":
    st.header("View Screening Results")
    
    roles_df = st.session_state.screener.db.list_roles()
    
    if roles_df.empty:
        st.warning("No roles available.")
    else:
        role_options = {f"{row['name']} (ID: {row['id']})": row['id'] for _, row in roles_df.iterrows()}
        selected_role = st.selectbox("Select Role to View Results", options=list(role_options.keys()))
        role_id = role_options[selected_role]
        
        top_n = st.slider("Number of top candidates to display", 5, TOP_N_LIMIT_MAX, 10)
        
        if st.button("📊 Load Results"):
            with st.spinner("Loading results..."):
                try:
                    results_df = st.session_state.screener.db.get_results_for_role(role_id, top_n=top_n)
                except (ValueError, sqlite3.Error) as exc:
                    logger.exception("Failed to load role results")
                    st.error(f"Could not load results: {exc}")
                    results_df = pd.DataFrame()
                
                if results_df.empty:
                    st.info("No screening results found for this role.")
                else:
                    st.success(f"Found {len(results_df)} result(s)")
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total Screened", len(results_df))
                    with col2:
                        st.metric("Avg Skills Matched", f"{results_df['num_matched_skills'].mean():.1f}")
                    with col3:
                        st.metric("Avg Similarity", f"{results_df['similarity_score'].mean():.2%}")
                    
                    st.markdown("---")
                    st.dataframe(results_df, use_container_width=True, hide_index=True)
                    
                    csv = results_df.to_csv(index=False)
                    st.download_button("📥 Download Results as CSV", data=csv,
                                      file_name=f"screening_results_{role_id}.csv", mime="text/csv")

# Settings Page
elif page == "⚙️ Settings":
    st.header("System Settings")
    
    tab1, tab2 = st.tabs(["🗑️ Manage Roles", "ℹ️ About"])
    
    with tab1:
        st.subheader("Delete Roles")
        roles_df = st.session_state.screener.db.list_roles()
        
        if not roles_df.empty:
            role_to_delete = st.selectbox("Select role to delete",
                options=[f"{row['name']} (ID: {row['id']})" for _, row in roles_df.iterrows()])
            
            if st.button("🗑️ Delete Role", type="secondary"):
                role_id = int(role_to_delete.split("ID: ")[1].rstrip(")"))
                st.session_state.screener.db.delete_role(role_id)
                st.success("Role deleted successfully!")
                st.rerun()
        else:
            st.info("No roles to delete.")
    
    with tab2:
        st.subheader("About This System")
        st.markdown(f"""
        ### AI Resume Screening System
        **Version:** 1.0  
        **Maintainer:** DhruvkrSharma  
        **Date:** 2025-11-09
        
        **Tech Stack:** Streamlit, spaCy, Sentence Transformers, PyMuPDF, SQLite, Plotly
        
        **GitHub:** [{REPO_URL}]({REPO_URL})
        """)

st.markdown("---")
st.markdown('<div style="text-align: center; color: #888;">Maintained by DhruvkrSharma | Powered by Streamlit</div>', 
           unsafe_allow_html=True)
