
import docx
import sys
import os

def read_docx(file_path):
    try:
        doc = docx.Document(file_path)
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
        return '\n'.join(full_text)
    except Exception as e:
        return f"Error reading file: {e}"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python read_docx.py <path_to_docx>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    output_path = "requirements_extracted.txt"
    content = read_docx(file_path)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    print(f"Successfully wrote content to {output_path}")
