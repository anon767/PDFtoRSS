import os
import re
import requests
from flask import Flask, request, jsonify, send_file, render_template_string
import pdfplumber
from feedgen.feed import FeedGenerator
from urllib.parse import urlparse
import hashlib
import fitz  # PyMuPDF
from transformers import pipeline

# Load Hugging Face summarization model
summarizer = pipeline("summarization", model="t5-small")

app = Flask(__name__)

# Directory to store downloaded PDFs
PDF_DIR = "static/pdfs"
if not os.path.exists(PDF_DIR):
    os.makedirs(PDF_DIR)

def get_pdf_filename(url):
    """Generate a unique filename based on the URL"""
    parsed_url = urlparse(url)
    filename = hashlib.md5(parsed_url.path.encode('utf-8')).hexdigest() + ".pdf"
    return os.path.join(PDF_DIR, filename)

def download_pdf(url):
    """Download the PDF from the URL if not already downloaded"""
    filename = get_pdf_filename(url)
    if not os.path.exists(filename):
        print(f"Downloading PDF from {url}")
        response = requests.get(url)
        with open(filename, 'wb') as f:
            f.write(response.content)
    else:
        print(f"PDF already downloaded: {filename}")
    return filename


def extract_chapters_from_pdf(pdf_path):
    """Extract chapters from a PDF file using get_toc() and identify both start and end pages, 
    backtracking when a chapter is repeated, and generating descriptions with a summarization model."""
    
    chapters = []
    chapter_title_positions = {}  # Dictionary to store positions of processed chapter titles
    current_description = []
    
    # Open the PDF using PyMuPDF to get TOC
    pdf_document = fitz.open(pdf_path)
    toc = pdf_document.get_toc()  # Returns [level, title, start_page]
    
    # Open the PDF using pdfplumber to extract text for summaries
    with pdfplumber.open(pdf_path) as pdf:
        for index, toc_entry in enumerate(toc):
            level, title, start_page = toc_entry
            start_page -= 1  # Adjust start_page to 0-indexed
            
            # Backtrack if the chapter title has already been processed
            if title in chapter_title_positions:
                previous_index = chapter_title_positions[title]
                # Remove all chapters added after this one
                chapters = chapters[:previous_index + 1]
                # Update the end_page of the previous chapter
                chapters[previous_index]['end_page'] = start_page - 1
            
            # Otherwise, mark this chapter title as processed
            else:
                chapter_title_positions[title] = len(chapters)
                
            # Set end_page as one page before the next chapter's start or the last page
            if index < len(toc) - 1:
                next_start_page = toc[index + 1][2] - 1  # Adjust to 0-indexed
            else:
                next_start_page = len(pdf.pages) - 1  # Last chapter ends at the last page
            
            # Extract text for this chapter
            chapter_text = ""
            for page_num in range(start_page, next_start_page + 1):
                page = pdf.pages[page_num]
                chapter_text += page.extract_text()
            
            # Summarize the chapter content
            better_description = summarizer(chapter_text[:800], max_length=150, min_length=30, do_sample=False)[0]['summary_text']
            #better_description = chapter_text
            # Add chapter details to the list
            chapter = {
                'title': title,
                'description': better_description,
                'start_page': start_page-1,
                'end_page': next_start_page
            }
            chapters.append(chapter)
    
    return chapters

def is_chapter_title(title, font_info=None):
    """
    Determine if a line of text is a chapter title using multiple heuristics.
    
    Parameters:
    - title: The line of text to analyze.
    - font_info: (Optional) Font information such as font size, if available.
    
    Returns:
    - bool: True if the line is determined to be a chapter title.
    """
    # Strip surrounding whitespace
    title = title.strip()
    
    # Basic checks for common chapter-related keywords or patterns
    chapter_patterns = [
        r"^chapter \d+",  # "Chapter 1", "Chapter 10"
        r"^section \d+",  # "Section 1", "Section 1.1"
        r"^part \d+",     # "Part 1", "Part II"
        r"^\d+(\.\d+)*",  # "1", "1.1", "1.1.1"
    ]
    
    # Check for matching patterns
    for pattern in chapter_patterns:
        if re.match(pattern, title, re.IGNORECASE):
            return True

    # If the title is in all uppercase, it could be a chapter title
    if title.isupper():
        return True

    # If the title has fewer than a certain number of words (e.g., 10), it may be a title
    if len(title.split()) <= 10:
        # Further refine by looking for special characters or patterns indicating a chapter
        if re.match(r'^\d+[\.]*\s*[A-Za-z]+', title):
            return True

    # Heuristic based on font size (if available)
    if font_info and 'size' in font_info:
        # Assume a larger font size indicates a title (you might need to fine-tune this threshold)
        if font_info['size'] > 12:  # Example threshold for larger titles
            return True

    # Add any additional specific checks you might need for the document structure
    return False

@app.route("/rss", methods=["GET"])
def generate_rss_feed():
    """Generate an RSS feed from the chapters in the PDF"""
    pdf_url = request.args.get('url')
    if not pdf_url:
        return jsonify({"error": "URL parameter is missing"}), 400

    pdf_path = download_pdf(pdf_url)
    chapters = extract_chapters_from_pdf(pdf_path)

    # Create RSS feed
    fg = FeedGenerator()
    fg.title("PDF Chapters Feed")
    fg.link(href=pdf_url, rel="alternate")
    fg.description("RSS feed of PDF chapters")

    for chapter in chapters:
        fe = fg.add_entry()
        fe.title(chapter['title'])
        fe.link(href=f"{request.host_url}pdf-chapter?file={os.path.basename(pdf_path)}&start_page={chapter['start_page']}&end_page={chapter['end_page']}")
        fe.description(chapter['description'])

    rss_feed = fg.rss_str(pretty=True)
    return rss_feed, {'Content-Type': 'application/rss+xml'}

@app.route("/pdf-chapter", methods=["GET"])
def view_pdf_chapter():
    """Serve a specific chapter as a new PDF (this would extract only the page/chapter requested)"""
    pdf_file = request.args.get('file')
    start_page = int(request.args.get('start_page'))
    end_page = int(request.args.get('end_page'))    
    pdf_path = os.path.join(PDF_DIR, pdf_file)

    if not os.path.exists(pdf_path):
        return jsonify({"error": "PDF not found"}), 404

    # Extract only the specific page
    output_pdf_path = os.path.join(PDF_DIR, f"chapter_{start_page + 1}_to_{end_page + 1}_{pdf_file}")

    if not os.path.exists(output_pdf_path):
        # Load the original PDF
        pdf_document = fitz.open(pdf_path)

        # Create a new PDF with just the selected page
        new_pdf = fitz.open()  # Create a new empty PDF
        new_pdf.insert_pdf(pdf_document, from_page=start_page-1, to_page=end_page)  # Add the range of pages
        new_pdf.save(output_pdf_path)
        new_pdf.close()

    # Serve the extracted page as a new PDF
    return send_file(output_pdf_path, as_attachment=False)


if __name__ == "__main__":
    app.run(debug=True)

