"""
Utility functions for resume screening system
Author: Gladiator2005
Date: 2025-11-09
"""

import logging

logger = logging.getLogger(__name__)

try:
    from google.colab import files as colab_files
except ImportError:
    colab_files = None
    logger.info("google.colab.files is unavailable; Colab upload/download helpers are disabled.")


def upload_pdfs_colab():
    """
    Helper to upload PDF files in Google Colab.
    
    Returns:
        List of uploaded file paths
    """
    if colab_files is None:
        raise RuntimeError("google.colab.files not available. Are you in Colab?")
    
    print("Please select PDF file(s) to upload...")
    uploaded = colab_files.upload()
    paths = [f"/content/{fname}" for fname in uploaded.keys()]
    print(f"Uploaded {len(paths)} file(s): {paths}")
    return paths


def export_results_csv(results_df, filename="screening_results.csv"):
    """
    Export results DataFrame to CSV.
    
    Args:
        results_df: Pandas DataFrame with results
        filename: Output filename
    """
    results_df.to_csv(filename, index=False)
    print(f"Results exported to {filename}")
    
    # Download in Colab
    if colab_files:
        colab_files.download(filename)
