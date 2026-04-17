"""
Streamlit Frontend for Resume Screening System
Author: DhruvkrSharma
Date: 2025-11-09
Usage: streamlit run main.py
"""

import streamlit as st
import pandas as pd
from pathlib import Path
import tempfile
import os
import logging
from screening_engine import ResumeScreener
from database import ResumeDatabase
import plotly.express as px
import sqlite3

logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE_MB = 5
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024


def normalize_manual_skills(skills_text):
    """Normalize, validate, and deduplicate manual skills."""
    normalized = []
    seen = set()
    for raw in skills_text.replace("\n", ",").replace(";", ",").split(","):
        skill = raw.strip().lower()
        if skill and skill not in seen:
            seen.add(skill)
            normalized.append(skill)
    return normalized


def validate_uploaded_pdfs(uploaded_files):
    """Validate uploaded files for type and size limits."""
    valid_files = []
    errors = []
    for uploaded_file in uploaded_files:
        file_name = uploaded_file.name or "unnamed-file"
        mime_type = (uploaded_file.type or "").lower()
        ext = Path(file_name).suffix.lower()

        is_pdf_extension = ext == ".pdf"
        is_pdf_mime = mime_type in {"application/pdf", "application/x-pdf"}

        if not is_pdf_extension and not is_pdf_mime:
            errors.append(f"{file_name}: only PDF files are supported.")
            continue

        if uploaded_file.size and uploaded_file.size > MAX_UPLOAD_SIZE_BYTES:
            errors.append(f"{file_name}: exceeds {MAX_UPLOAD_SIZE_MB} MB limit.")
            continue

        valid_files.append(uploaded_file)
    return valid_files, errors

# Page configuration
st.set_page_config(
    page_title="AI Resume Screening System",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
    st.session_state.screener = ResumeScreener()
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
        ["🏠 Home", "➕ Add Role", "📊 Screen Resumes", "📈 View Results", "⚙️ Settings"]
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
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM resumes")
        resume_count = cursor.fetchone()[0]
        conn.close()
        st.metric("Resumes Processed", resume_count)
    
    with col3:
        conn = sqlite3.connect(db.db_path)
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
            if role_name and job_description:
                with st.spinner("Extracting skills using NLP..."):
                    try:
                        skills = st.session_state.screener.add_role_from_text(role_name, job_description)
                        st.success(f"✅ Role '{role_name}' added successfully!")
                        st.info(f"**Extracted {len(skills)} skills:** {', '.join(skills)}")
                    except (ValueError, sqlite3.Error, RuntimeError) as error:
                        logger.exception("Failed to add role from job description: role_name=%s", role_name)
                        st.error(f"Error: {error}")
            else:
                st.warning("Please fill in both role name and job description.")
    
    with tab2:
        st.subheader("Manually Enter Skills")
        manual_role_name = st.text_input("Job Role Name", key="manual_name")
        manual_skills = st.text_area("Skills (comma-separated)", height=150,
                                      placeholder="Python, Machine Learning, TensorFlow, SQL, AWS")
        
        if st.button("➕ Add Role", type="primary", key="manual_add"):
            if manual_role_name and manual_skills:
                with st.spinner("Adding role..."):
                    try:
                        skills_list = normalize_manual_skills(manual_skills)
                        if not skills_list:
                            raise ValueError("Please provide at least one non-empty skill.")
                        st.session_state.screener.add_role_manual(manual_role_name, skills_list)
                        st.success(f"✅ Role '{manual_role_name}' added with {len(skills_list)} skills!")
                    except (ValueError, sqlite3.Error) as error:
                        logger.exception("Failed to add manual role: role_name=%s", manual_role_name)
                        st.error(f"Error: {error}")
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
            "🔒 Privacy notice: Uploaded resumes are processed locally during screening. "
            "Temporary upload files are deleted after processing. Extracted snippets/results "
            "are stored in the local SQLite database for analysis."
        )

        valid_uploaded_files = []
        if uploaded_files:
            valid_uploaded_files, upload_errors = validate_uploaded_pdfs(uploaded_files)
            for error in upload_errors:
                st.warning(error)
        
        col1, col2 = st.columns(2)
        with col1:
            semantic_threshold = st.slider("Semantic Matching Threshold", 0.0, 1.0, 0.45, 0.05,
                                          help="Lower = more matches, Higher = stricter")
        with col2:
            skip_missing = st.checkbox("Skip missing files", value=True)
        
        if st.button("🔍 Start Screening", type="primary", disabled=not uploaded_files):
            if uploaded_files:
                if not valid_uploaded_files:
                    st.error("No valid PDF files to process. Please upload valid PDFs within size limits.")
                else:
                    with st.spinner(f"Screening {len(valid_uploaded_files)} resume(s)..."):
                        temp_paths = []
                        try:
                            for uploaded_file in valid_uploaded_files:
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
                                    by=['num_matched_skills', 'similarity_score'],
                                    ascending=False
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
                        
                        except (ValueError, sqlite3.Error, OSError, RuntimeError) as error:
                            logger.exception("Error during resume screening for role_id=%s", role_id)
                            st.error(f"Error during screening: {error}")
                        finally:
                            for path in temp_paths:
                                try:
                                    os.unlink(path)
                                except OSError as cleanup_error:
                                    logger.warning("Failed to delete temp file %s: %s", path, cleanup_error)

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
        
        top_n = st.slider("Number of top candidates to display", 5, 50, 10)
        
        if st.button("📊 Load Results"):
            with st.spinner("Loading results..."):
                results_df = st.session_state.screener.db.get_results_for_role(role_id, top_n=top_n)
                
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
        st.markdown("""
        ### AI Resume Screening System
        **Version:** 1.0  
        **Maintainer:** DhruvkrSharma  
        **Date:** 2025-11-09
        
        **Tech Stack:** Streamlit, spaCy, Sentence Transformers, PyMuPDF, SQLite, Plotly
        
        **GitHub:** [https://github.com/DhruvkrSharma/resume-screening-system](https://github.com/DhruvkrSharma/resume-screening-system)
        """)

st.markdown("---")
st.markdown('<div style="text-align: center; color: #888;">Maintained by DhruvkrSharma | Powered by Streamlit</div>', 
           unsafe_allow_html=True)
