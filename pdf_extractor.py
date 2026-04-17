import fitz  # PyMuPDF
import pdfplumber
import pytesseract
from PIL import Image
import io

def extract_text_with_pymupdf(pdf_path):
    text = ''
    try:
        with fitz.open(pdf_path) as doc:
            for page in doc:
                text += page.get_text()
    except Exception:
        return ''
    return text

def extract_text_with_pdfplumber(pdf_path):
    text = ''
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() or ''
    except Exception:
        return ''
    return text

def extract_text_with_ocr(pdf_path):
    text = ''
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                img = page.to_image().original
                text += pytesseract.image_to_string(img)  # OCR extraction
    except Exception:
        return ''
    return text


def extract_text_from_pdf(pdf_path):
    # Attempt extraction with PyMuPDF
    text = extract_text_with_pymupdf(pdf_path)
    if text.strip():
        return text
    # If PyMuPDF extraction fails, try pdfplumber
    text = extract_text_with_pdfplumber(pdf_path)
    if text.strip():
        return text
    # If both methods fail, fallback to OCR
    return extract_text_with_ocr(pdf_path)

if __name__ == '__main__':
    pdf_path = 'path_to_your_pdf.pdf'  # Specify your PDF path here
    text = extract_text_from_pdf(pdf_path)
    print(text)
