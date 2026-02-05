"""
Simple test for read_pdf, read_docx, read_excel functions.
"""
import os
import sys

from kg.build_kg_deepseek import read_pdf, read_docx, read_excel


def test_read_pdf(pdf_path):
    """Test PDF reading"""
    print("Testing read_pdf...")
    if not os.path.exists(pdf_path):
        print(f"  ⚠️  Skipped: {pdf_path} not found")
        return False

    result = read_pdf(pdf_path)
    print(f"  Result length: {len(result)} chars")
    return bool(result.strip())


def test_read_docx():
    """Test DOCX reading"""
    print("Testing read_docx...")
    docx_path = "data/test.docx"
    if not os.path.exists(docx_path):
        print(f"  ⚠️  Skipped: {docx_path} not found")
        return False

    result = read_docx(docx_path)
    print(f"  Result length: {len(result)} chars")
    return bool(result.strip())


def test_read_excel():
    """Test Excel reading"""
    print("Testing read_excel...")
    xlsx_path = "data/test.xlsx"
    if not os.path.exists(xlsx_path):
        print(f"  ⚠️  Skipped: {xlsx_path} not found")
        return False

    result = read_excel(xlsx_path)
    print(f"  Result length: {len(result)} chars")
    return bool(result.strip())


def main():
    results = []
    pdf_path = "data\\A_quick_guide_to_govt_healthy_eating_update.pdf"

    pdf_content = None
    if os.path.exists(pdf_path):
        pdf_content = read_pdf(pdf_path)
        results.append(("read_pdf", pdf_content))
    else:
        print(f"  ⚠️  Skipped: {pdf_path} not found")
        results.append(("read_pdf", None))

    # results.append(("read_docx", test_read_docx()))
    # results.append(("read_excel", test_read_excel()))

    # Save to file
    output_text = ""
    for res in results:
        if res[1] is not None:
            output_text += res[1]
    output_file = os.path.join(os.path.dirname(__file__), "output.txt")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(output_text)
    print(f"\nResult saved to: {output_file}")


if __name__ == "__main__":
    main()
