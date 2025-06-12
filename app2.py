from flask import Flask, render_template, request, send_from_directory, send_file
import fitz  # PyMuPDF
import os
from collections import defaultdict
from flask import jsonify
from PIL import Image
import zipfile
import pikepdf
import pandas as pd
import win32com.client
import json
import pythoncom

app = Flask(__name__)

input_folder = "pdfs"
output_folder = "output_pdfs"
output_vendor_code = "vendor_code_name_temp/vendor_code.txt"
output_vendor_name = "vendor_code_name_temp/vendor_name.txt"

os.makedirs(output_folder, exist_ok=True)
os.makedirs(input_folder, exist_ok=True)
os.makedirs('vendor_code_name_temp', exist_ok=True)
os.makedirs('db_supplier', exist_ok=True)
os.makedirs('static/cons', exist_ok=True)
# Path ke file
file_path = 'static/cons/empty.png'

# Cek apakah file ada
if not os.path.exists(file_path):
    # Bikin folder kalau belum ada
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    # Bikin gambar transparan 304x451
    img = Image.new("RGBA", (304, 451), (0, 0, 0, 0))  # RGBA = transparan
    img.save(file_path, format="PNG")

    print(f"File '{file_path}' berhasil dibuat (kosong & transparan).")
else:
    print(f"File '{file_path}' sudah ada.")

os.makedirs('static/mtn', exist_ok=True)

def extract_supplier_name(page):
    """Ambil teks dari dua posisi di halaman dan gabungkan jadi title"""
    text_dict = page.get_text("dict")
    
    title = ""
    vendor_name = ""
    vendor_code = ""
    po_number = ""
    array_filter = []

    for block in text_dict["blocks"]:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                x, y = span["bbox"][0], span["bbox"][1]
                text = span["text"].strip()

                # Toleransi koordinat ±1.0
                if abs(x - 38.5) < 1.0 and len(text) > 2:
                    vendor_name = text.replace("/", "_")

                if abs(x - 61.3) < 1.0 and len(text) > 2:
                    textexplode = text.split(" / ")
                    po_number = textexplode[0].replace("/", "_")

                if abs(x - 126.7) < 1.0 and len(text) > 2:
                    vendor_code = text.replace("/", "_")

    if vendor_name or po_number or vendor_code:
        title = po_number + " " + vendor_name
        array_filter.append(title)
        array_filter.append(vendor_name)
        array_filter.append(vendor_code)
        return array_filter

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
        if tipe == "Maintenance":
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
            
        missing = []
        for path in ttd_files:
            if not os.path.exists(path):
                nama = os.path.splitext(os.path.basename(path))[0]
                if not nama == "empty":
                    missing.append(nama.upper())

        if missing:
            missing_str = ", ".join(missing)
            return f"TTD {missing_str} belum di setting", 200
        
        output_filenames = []
        vendor_names = set()
        vendor_codes = set()

        for file in files:
            filename = file.filename
            pdf_path = os.path.join(input_folder, filename)
            file.save(pdf_path)
            doc = fitz.open(pdf_path)

            supplier_pages = defaultdict(list)

            # Kelompokkan halaman berdasarkan supplier
            for page_num, page in enumerate(doc):
                supplier = extract_supplier_name(page)
                title = supplier[0]
                vendor_names.add(supplier[1])  # set akan otomatis hilangkan duplikat
                vendor_codes.add(supplier[2])  # set akan otomatis hilangkan duplikat
                supplier_pages[title].append(page_num)

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

                    # print(filename,page_width,reference_width,scale_ratio)
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

                # Simpan sementara tanpa enkripsi
                unencrypted_path = os.path.join(output_folder, "aes256" + supplier_name + ".pdf")
                new_doc.save(unencrypted_path)
                new_doc.close()

                # Enkripsi ulang menggunakan AES-128 dengan pikepdf
                encrypted_path = os.path.join(output_folder, supplier_name.upper() + ".pdf")
                with pikepdf.open(unencrypted_path) as pdf:
                    pdf.save(
                        encrypted_path,
                        encryption=pikepdf.Encryption(
                            user="adm",
                            owner="ownerpass",
                            R=4  # AES-128-bit encryption
                        )
                    )

                output_filenames.append(supplier_name.upper() + ".pdf")

                with open(output_vendor_code, 'w', encoding='utf-8') as f:
                    json.dump(list(vendor_codes), f)
                with open(output_vendor_name, 'w', encoding='utf-8') as f:
                    json.dump(list(vendor_names), f)

                try:
                    if os.path.isfile(unencrypted_path):
                        os.remove(unencrypted_path)
                except Exception as e:
                    print(f"Gagal menghapus file {unencrypted_path} : {e}")

        return render_template("index.html", message="LIST FILE PDF", files=output_filenames, vendor_code=list(vendor_codes), vendor_name=list(vendor_names))
    
    # Kalau file belum ada, buat file kosong dengan "[]"
    if not os.path.isfile(output_vendor_code):
        with open(output_vendor_code, 'w', encoding='utf-8') as f:
            f.write("[]")

    if not os.path.isfile(output_vendor_name):
        with open(output_vendor_name, 'w', encoding='utf-8') as f:
            f.write("[]")

    # Sekarang file udah pasti ada, tinggal baca isinya
    with open(output_vendor_code, 'r', encoding='utf-8') as f:
        vendor_codes = json.loads(f.read())

    with open(output_vendor_name, 'r', encoding='utf-8') as f:
        vendor_names = json.loads(f.read())
            
    output_filenames = []
    
    # buat load data file output
    for filename_pdfs in os.listdir(output_folder):
        file_path = os.path.join(output_folder, filename_pdfs)
        try:
            if os.path.isfile(file_path):
                output_filenames.append(filename_pdfs)
        except Exception as e:
            print(f"Gagal menghapus {file_path}: {e}")

    return render_template("index.html", message='LIST FILE PDF', files=output_filenames, vendor_code=vendor_codes, vendor_name=vendor_names)

@app.route("/send-email", methods=["POST"])
def send_email():
    pythoncom.CoInitialize()  # ⬅️ ini penting!
    data = request.get_json()
    file = data.get("file")
    nomor_po = data.get("nomor_po")
    vendor_name = data.get("vendor_name")
    title = data.get("title")
    email = data.get("email")
    cc = data.get("cc")
    
    # print("file:", file)
    # print("email:", email)
    # print("cc:", cc)
    # print("vendor_name:", vendor_name)
    # print("title:", title)
    # print("nomor_po:", nomor_po)

    # Nyalain Outlook-nya, kayak manggil anak magang
    outlook = win32com.client.Dispatch("Outlook.Application")

    # Bikin email baru
    mail = outlook.CreateItem(0)  # 0 artinya email item

    # Isi emailnya, gampang banget
    mail.To = email
    mail.CC = cc+"; Email.Log@Daihatsu.astra.co.id"
    mail.Subject = "PO "+title
    mail.HTMLBody = f"""
    <p>Kepada Yth.<br>{vendor_name}</p>

    <p>Dengan ini kami lampirkan Purchase Order (PO) nomor <b>{nomor_po}</b>.<br>
    Mohon dapat memeriksa file terlampir.<br>
    Password File: <b>adm</b></p>

    <p>Terima kasih atas perhatian dan kerjasamanya.</p>

    <p><i>PO Separating System (POSS)</i></p>
    """


    # Kalau mau nambahin file, tinggal tempelin aja
    lampiran = os.path.join(output_folder, file)
    lampiran = os.path.abspath(lampiran)  # ⬅️ Bikin path absolut
    # print("Path lampiran:", lampiran)
    # print("Absolut? ->", os.path.isabs(lampiran))
    # print("Ada file? ->", os.path.exists(lampiran))
    if not os.path.exists(lampiran):
        return jsonify({"message":"File lampiran tidak ditemukan"}), 500
    mail.Attachments.Add(lampiran)

    # Kalo mau ngeliat dulu sebelum kirim, pake ini:
    # mail.Display()

    # Tapi kalo lu udah pede langsung tancap gas:
    mail.Send()
    return jsonify({"message":"Email berhasil dikirim"}), 200


@app.route("/get_db_supplier")
def get_db_supplier():
    # Ambil kolom A sampai D (tanpa peduli nama header)
    data = pd.read_excel("db_supplier/db_supplier.xlsx", usecols="A:D", header=None, skiprows=1)

    # Tetapkan nama kolom tetap
    data.columns = ["vendor_code", "vendor_name", "email", "cc"]

    data = data.set_index('vendor_code')

    json_data = data.to_json(orient='index', indent=4)
    return json_data, 200

@app.route("/upload_db_supplier", methods=["POST"])
def upload_db_supplier():
    UPLOAD_FOLDER = "db_supplier"
    os.makedirs(UPLOAD_FOLDER,exist_ok=True)
    if 'file' not in request.files:
        return jsonify({'message':'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'message':'No file selected'}), 400
    
    filename = "db_supplier.xlsx"
    save_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(save_path)
    return jsonify({'message':'Sukses upload Database'}), 200

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
    app.run(debug=True) # For Development
    # app.run(debug=False, host='127.0.0.1', port=5000)
    # app.run(host='0.0.0.0', port=5000) # For Production
