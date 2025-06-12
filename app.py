import fitz  # PyMuPDF

pdf_path = "pdfs/P5PAD_AJIDP_P880000008155_1_New Purchase Order Printout.pdf"  # ganti dengan nama file PDF kamu
output_txt = "output1.txt"

doc = fitz.open(pdf_path)

with open(output_txt, "w", encoding="utf-8") as f:
    for page_number in range(len(doc)):
        page = doc[page_number]
        text_dict = page.get_text("dict")

        f.write(f"\n=== Halaman {page_number + 1} ===\n")
        
        for block in text_dict["blocks"]:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span['text'].strip()
                    bbox = span['bbox']  # [x0, y0, x1, y1]
                    if text:
                        f.write(f"Text: '{text}' | Posisi: x0={bbox[0]:.1f}, y0={bbox[1]:.1f}, x1={bbox[2]:.1f}, y1={bbox[3]:.1f}\n")

print(f"Selesai. Hasil disimpan di: {output_txt}")
