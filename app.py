import streamlit as st
import json  # Tidak lagi diperlukan jika hanya raw text, tapi tidak masalah jika ada
import io
import os
import sys

# Tambahkan path ke direktori saat ini agar modul extraction dapat ditemukan
sys.path.append(os.path.dirname(__file__))

# Import fungsi dari extraction.py
# Hanya perlu process_receipt_image, tidak perlu normalize_item_name
from extraction import process_receipt_image


# --- Fungsi untuk memuat dan menjalankan model OCR Anda ---
def run_ocr_and_extraction(image_file_streamlit):
    """
    Fungsi untuk menjalankan pipeline OCR dan ekstraksi dari extraction.py.

    Args:
        image_file_streamlit: Objek UploadedFile dari Streamlit (gambar yang diunggah).

    Returns:
        Dict JSON yang berisi hasil ekstraksi (akan diambil raw_text-nya saja).
    """
    original_filename = image_file_streamlit.name
    temp_image_path = os.path.join(os.getcwd(), f"temp_{original_filename}")

    try:
        with open(temp_image_path, "wb") as f:
            f.write(image_file_streamlit.getvalue())

        extracted_data = process_receipt_image(temp_image_path)
        return extracted_data
    finally:
        if os.path.exists(temp_image_path):
            os.remove(temp_image_path)


# --- Aplikasi Streamlit ---
st.set_page_config(page_title="OCR Struk Belanja", page_icon="🧾", layout="centered")
st.title("OCR Struk Belanja 🧾")
st.write("Unggah gambar struk belanja Anda untuk melihat teks mentah hasil OCR.")

st.info(
    "Penting: Pastikan Anda telah menginstal `tesseract-ocr` di sistem Anda dan PATH-nya terdaftar di lingkungan Anda.")
st.markdown("---")

# Opsi: Unggah Gambar atau Ambil dari Kamera
upload_option = st.radio(
    "Pilih metode unggah:",
    ("Unggah Gambar", "Ambil dari Kamera")
)

image_file = None
if upload_option == "Unggah Gambar":
    image_file = st.file_uploader("Pilih gambar struk belanja...", type=["jpg", "jpeg", "png"])
elif upload_option == "Ambil dari Kamera":
    st.warning(
        "Fungsionalitas 'Ambil dari Kamera' memerlukan pengaturan server yang spesifik (misalnya, HTTPS). 'Unggah Gambar' lebih stabil untuk demo.")
    image_file = st.camera_input("Ambil gambar struk belanja")

extracted_data_result = None
if image_file is not None:
    st.image(image_file, caption='Gambar Struk Belanja', use_container_width=True)
    st.write("Memproses gambar, mohon tunggu...")

    try:
        extracted_data_result = run_ocr_and_extraction(image_file)

        if "error" in extracted_data_result:
            st.error(f"OCR gagal: {extracted_data_result['error']}")
        else:
            st.success("OCR berhasil!")  # Hanya menampilkan status sukses

    except Exception as e:
        st.error(f"Terjadi kesalahan saat memproses data: {e}")
        extracted_data_result = None

st.markdown("---")

# --- Bagian Output: Hanya Menampilkan Raw Text ---
if extracted_data_result:  # Pastikan ada hasil dari proses
    raw_text = extracted_data_result.get('raw_text', 'Tidak ada teks yang terdeteksi dari OCR.')

    st.subheader("Hasil OCR:")
    st.text_area("Seluruh Teks yang Ditemukan:", raw_text, height=600,
                 help="Ini adalah teks mentah yang dikenali oleh Tesseract OCR dari gambar struk.")

# Tidak ada lagi opsi JSON atau tampilan terstruktur lainnya