from flask import Flask, render_template, request, send_from_directory, send_file
import fitz  # PyMuPDF
import os
from collections import defaultdict
from flask import jsonify
from PIL import Image
import zipfile

app = Flask(__name__)

input_folder = "pdfs"
output_folder = "output_pdfs"

os.makedirs(output_folder, exist_ok=True)
os.makedirs(input_folder, exist_ok=True)

def extract_supplier_name(page):
    """Ambil teks dari dua posisi di halaman dan gabungkan jadi title"""
    text_dict = page.get_text("dict")
    
    title = ""
    first_part = ""
    second_part = ""

    for block in text_dict["blocks"]:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                x, y = span["bbox"][0], span["bbox"][1]
                text = span["text"].strip()

                # Toleransi koordinat ±1.0
                if abs(x - 38.5) < 1.0 and len(text) > 2:
                    first_part = text.replace("/", "_")

                if abs(x - 61.3) < 1.0 and len(text) > 2:
                    textexplode = text.split(" / ")
                    second_part = textexplode[0].replace("/", "_")

    if first_part or second_part:
        title = second_part + " " + first_part
        return title

    return "UnknownSupplier"

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        for filename_pdfs in os.listdir(output_folder):
            file_path = os.path.join(output_folder, filename_pdfs)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"Gagal menghapus {file_path}: {e}")

        files = request.files.getlist("file")
        tipe = request.form.get("tipe")
        if(tipe == "Maintenance"):
            ttd_files = [
                "static/mtn/mng.png",
                "static/mtn/spv.png",
                "static/mtn/div1.png",
                "static/mtn/div2.png"
            ]
        else:
            ttd_files = [
                "static/cons/spv.png",
                "static/cons/empty.png",
                "static/cons/mng.png",
                "static/cons/div1.png"
            ]
        output_filenames = []

        for file in files:
            filename = file.filename
            pdf_path = os.path.join(input_folder, filename)
            file.save(pdf_path)
            doc = fitz.open(pdf_path)

            supplier_pages = defaultdict(list)

            # Kelompokkan halaman berdasarkan supplier
            for page_num, page in enumerate(doc):
                supplier = extract_supplier_name(page)
                supplier_pages[supplier].append(page_num)

            # Buat PDF per supplier
            for supplier_name, pages in supplier_pages.items():
                new_doc = fitz.open()

                # Insert halaman dari dokumen asli ke dokumen baru
                for page_num in pages:
                    new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)

                # Tambahkan tanda tangan ke setiap halaman
                for i, page in enumerate(new_doc):
                    # Ukuran lebar referensi (11.67 inchi dalam poin)
                    reference_width = 842

                    page_width = page.rect.width
                    scale_ratio = page_width / reference_width

                    print(filename,page_width,reference_width,scale_ratio)
                    if(scale_ratio == 1):
                        coords = [
                            (480, 720, 550, 800), #TTD 1 (x1,y1,x2,y2)
                            (510, 670, 530, 720), #TTD KECIL
                            (480, 460, 550, 540), #TTD MANAGER
                            (480, 220, 550, 300), #TTD DIVISION
                        ]
                    else:
                        coords = [
                            (480, 660, 550, 740), #TTD 1
                            (510, 610, 530, 660), #TTD KECIL
                            (480, 420, 550, 500), #TTD MANAGER
                            (480, 160, 550, 240), #TTD DIVISION
                        ]
                    for j, rect_coords in enumerate(coords):
                        if j < len(ttd_files):
                            rect = fitz.Rect(*rect_coords)
                            page.insert_image(rect, filename=ttd_files[j])

                output_file = f"{supplier_name}.pdf"
                new_doc.save(
                    os.path.join(output_folder, output_file),
                    encryption=fitz.PDF_ENCRYPT_AES_256,
                    user_pw="adm"
                )
                new_doc.close()
                output_filenames.append(output_file)

        return render_template("index.html", message="LIST FILE PDF", files=output_filenames)

    return render_template("index.html", message=None)

@app.route("/download/<filename>")
def download(filename):
    for filename_pdfs in os.listdir(input_folder):
        file_path = os.path.join(input_folder, filename_pdfs)
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Gagal menghapus {file_path}: {e}")

    return send_from_directory(output_folder, filename)

@app.route("/download_bundle")
def download_bundle():
    zip_filename = "po_separate.zip"
    # Membuat file zip
    with zipfile.ZipFile(zip_filename, 'w') as zipf:
        for filename in os.listdir(output_folder):
            if filename.endswith('.pdf'):
                filepath = os.path.join(output_folder, filename)
                zipf.write(filepath, arcname=filename)  # arcname = nama dalam zip
    print(f'Semua PDF dari folder "{output_folder}" telah dimasukkan ke dalam "{zip_filename}".')
    return send_file(zip_filename, as_attachment=True)

@app.route('/upload-ttd', methods=['POST'])
def upload_ttd():
    tipe = request.form.get("tipe")
    UPLOAD_FOLDER = "static/mtn" if tipe == "Maintenance" else "static/cons"
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    if 'file' not in request.files:
        return jsonify({"message": "No file part"}), 400

    file = request.files['file']
    filename = request.form.get('target', 'default.png')

    if file.filename == '':
        return jsonify({"message": "No selected file"}), 400

    # Open image and convert to RGBA
    img = Image.open(file).convert("RGBA")
    datas = img.getdata()

    new_data = []
    for item in datas:
        # Ganti warna putih (atau hampir putih) menjadi transparan
        if item[0] > 240 and item[1] > 240 and item[2] > 240:
            new_data.append((255, 255, 255, 0))  # Transparent
        else:
            new_data.append(item)

    img.putdata(new_data)
    # Rotate gambar 90 derajat searah jarum jam
    img = img.rotate(90, expand=True)
    save_path = os.path.join(UPLOAD_FOLDER, filename)
    img.save(save_path, "PNG")

    return jsonify({"message": f"Gambar berhasil diupload"}), 200


if __name__ == "__main__":
    app.run(debug=True)
