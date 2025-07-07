import platform
import re
import cv2
import numpy as np
import pytesseract
from dateutil import parser
from datetime import datetime

# --- Konfigurasi PyTesseract (PENTING!) ---
if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
else: # Asumsi Linux di Streamlit Cloud
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

# --- 1. Fungsi Normalisasi Dasar ---
def normalize_price(price):
    """
    Normalisasi harga (price).
    - Hilangkan karakter non-digit kecuali koma/titik sebagai desimal.
    - Konversi ke integer setelah menghilangkan pemisah ribuan.
    - Handle 'Rp', '$', dll.
    """
    if price is None:
        return None
    price_str = str(price).strip()

    # Hapus semua karakter yang bukan digit, titik, atau koma.
    # Juga hapus spasi jika ada di tengah angka (misal "175, 000" -> "175,000")
    price_str = re.sub(r'[^\d.,]', '', price_str)
    price_str = re.sub(r'\s', '', price_str)

    # Menangani pemisah ribuan dan desimal (Asumsi: di Indo koma adalah desimal, titik adalah ribuan)
    # Ini adalah asumsi yang paling aman untuk format umum Indonesia
    if ',' in price_str:
        # Jika koma diikuti 1 atau 2 digit, asumsikan desimal (contoh: 123,45)
        if re.search(r',\d{1,2}$', price_str):
            price_str = price_str.replace('.', '')  # Hapus titik ribuan
            price_str = price_str.replace(',', '.')  # Ubah koma desimal ke titik
        else:
            # Jika koma tidak diikuti 1-2 digit, asumsikan pemisah ribuan (contoh: 1,000)
            price_str = price_str.replace(',', '')
    # Jika hanya ada titik, dan diikuti 1-2 digit, asumsikan desimal (contoh: 123.45)
    elif '.' in price_str and re.search(r'\.\d{1,2}$', price_str):
        pass  # Biarkan saja, sudah format float yang benar
    # Jika hanya ada titik, dan tidak diikuti 1-2 digit, asumsikan pemisah ribuan (contoh: 1.000)
    elif '.' in price_str:
        price_str = price_str.replace('.', '')

    # Akhirnya, coba konversi ke int. Jika gagal, None.
    try:
        if not price_str:  # Jika string kosong setelah pembersihan
            return None
        return int(float(price_str))  # Konversi ke float dulu untuk handle desimal, lalu int
    except ValueError:
        return None


def normalize_merchant_name(name: str) -> str | None:
    """
    Normalisasi nama merchant:
    - Buang angka/tanggal/waktu di belakang.
    - Buang karakter aneh di depan/belakang.
    - Hapus spasi ganda.
    - Kapitalisasi awal tiap kata.
    - Buang common receipt artifacts.
    - Tambahan: membersihkan sisa karakter non-nama yang sering muncul di raw text.
    """
    if not name:
        return None
    name = name.strip()
    # Buang tanggal/angka/waktu di akhir nama (biasa hasil OCR dari struk)
    name = re.sub(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{2}:\d{2})\b$', '', name).strip()
    # Tambahkan lebih banyak keyword yang sering muncul di header struk tapi bukan nama merchant.
    name = re.sub(
        r'\b(npwp|kasir|struk|no\.?|invoice|id|pos|cashier|check|bill|kassa|rcpt#|rept#|title|pax|op|gunawan|lippo|mall|kemang|j|pr|emang|vi|no|ind|cin|ctw|i|ster|cr[eÊ]perie|pt|cv|litle|rept|rpt|alun|gunungparang|kec|cikole|kota|sukabumi|jawa|barat|indonesia|karyawan)\b',
        '', name, flags=re.IGNORECASE).strip()

    # Hapus simbol di awal/akhir dan karakter yang tidak umum dalam nama merchant
    name = re.sub(r'^[^\w\s]+|[^\w\s]+$', '', name).strip()
    name = re.sub(r'[^A-Za-z0-9\s&\'\.]', '', name).strip()  # Hanya izinkan huruf, angka, spasi, &, ', .
    name = re.sub(r'\s+', ' ', name)  # Hapus spasi berlebih
    name = name.title()

    # Perbaiki specific OCR errors dari 'MOMI & TOY\'S' jika masih muncul
    name = name.replace("O Mall", "").replace("Momi Antoys", "Momi & Toy's").replace("O Momi Antoys",
                                                                                     "Momi & Toy's").strip()
    name = re.sub(r'cr[eÊ]perie', 'Crêperie', name, flags=re.IGNORECASE)

    # Final cleanup jika hanya tersisa kata-kata generik setelah normalisasi
    if name.lower() in ['mall', 'kemang', 'lippo', 'o', 'pr', 'j', 'vi', 'no', 'l', 'alun', 'gunungparang', 'kec',
                        'cikole', 'kota', 'sukabumi', 'jawa', 'barat', 'indonesia', 'karyawan', 'supercenter',
                        'wholesale', 'foods', 'family', 'mexican']:
        return None

    # Filter nama yang terlalu pendek atau hanya angka
    if len(name) < 3 or re.match(r'^\d+$', name):
        return None
    return name.strip()


def normalize_item_name(name: str) -> str | None:
    """
    Normalisasi nama item:
    - Buang angka (kuantitas) dan karakter aneh di awal/akhir
    - Hapus spasi ganda
    - Kapitalisasi awal tiap kata
    """
    if not name:
        return None
    name = name.strip()
    # Buang angka (kuantitas, dll) di awal atau akhir yang bisa salah terdeteksi
    name = re.sub(r'^\s*\d+(\s*[xX]\s*)?|\s+[xX]\s*\d+\s*$', '', name).strip()
    # Buang tanggal/angka yang tidak relevan di awal/akhir
    name = re.sub(r'^(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{2,})\b', '', name).strip()
    name = re.sub(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{2,})$', '', name).strip()
    # Hapus simbol aneh di depan/belakang
    name = re.sub(r'^[^\w\s]+|[^\w\s]+$', '', name).strip()
    # Hapus spasi berlebih
    name = re.sub(r'\s+', ' ', name)
    # Kapitalisasi awal tiap kata
    name = name.title()
    if len(name) < 2:  # Item name should be at least 2 chars
        return None
    return name.strip()


# --- 2. Fungsi Ekstraksi Entitas Individual ---
def extract_date(text):
    """
    Ekstrak tanggal dari teks dengan regex yang lebih fleksibel dan dateutil.parser.
    Mencoba beberapa format umum.
    """
    date_patterns = [
        r'(\d{2}/\d{2}/\d{4})\s+\d{2}:\d{2}',  # MM/DD/YYYY HH:MM (for 8.jpg, Costco)
        r'(\d{2}/\d{2}/\d{2})\s+\d{2}:\d{2}',  # MM/DD/YY HH:MM (for 0.jpg, Walmart)
        r'(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})',  # YYYY-MM-DD/MM/DD
        r'(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})',  # DD/MM/YYYY or MM/DD/YYYY
        r'(\d{1,2}\s+(?:Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember)[a-z]*\s+\d{2,4})',
        r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|Mei|Jun|Jul|Agu|Sep|Okt|Nov|Des)[a-z]*\s+\d{2,4})',
        r'(?:Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember)[a-z]*\s+\d{1,2},\s+\d{2,4}',
        r'(?:Jan|Feb|Mar|Apr|Mei|Jun|Jul|Agu|Sep|Okt|Nov|Des)[a-z]*\s+\d{1,2},\s+\d{2,4}',
        r'\b(\d{1,2}/\d{1,2}/\d{2})\b',  # For simpler MM/DD/YY (e.g. Primo 5/3/19)
    ]

    for pattern in date_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match_str in matches:
            try:
                # Try parsing with dayfirst=True
                dt = parser.parse(match_str, dayfirst=True)
                current_year = datetime.now().year
                if (current_year - 10) <= dt.year <= (current_year + 2):
                    return dt.strftime('%Y-%m-%d')
            except ValueError:
                # If dayfirst fails, try monthfirst if it looks like MM/DD/YY or MM/DD/YYYY
                # And if the first part is plausible month (<=12) and second part is plausible day (<=31)
                parts = re.split(r'[/.-]', match_str)
                if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                    m1 = int(parts[0])
                    m2 = int(parts[1])
                    if m1 <= 12 and m2 > 12:  # Looks like MM/DD where DD > 12
                        try:
                            dt = parser.parse(match_str, monthfirst=True)
                            current_year = datetime.now().year
                            if (current_year - 10) <= dt.year <= (current_year + 2):
                                return dt.strftime('%Y-%m-%d')
                        except ValueError:
                            pass
                continue  # Continue to next pattern/match if all parsing failed for this one

    # Fallback: search in lines containing date keywords
    date_keywords = r'(tanggal|date|tgl|tgl\.|waktu|time)'
    for line in text.split('\n'):
        if re.search(date_keywords, line, re.IGNORECASE):
            date_match = re.search(r"(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}[/.-]\d{1,2}[/.-]\d{1,2})", line)
            if date_match:
                try:
                    dt = parser.parse(date_match.group(1), dayfirst=True)
                    current_year = datetime.now().year
                    if (current_year - 10) <= dt.year <= (current_year + 2):
                        return dt.strftime('%Y-%m-%d')
                except ValueError:
                    pass
    return None


def extract_merchant_name(text: str) -> str | None:
    """
    Ambil nama merchant dari 1–7 baris teratas struk.
    Hindari kata kunci umum dan angka besar.
    Coba gunakan baris dengan jumlah karakter alfanumerik terbanyak di awal.
    Prioritaskan pencarian pola brand yang unik.
    """
    keywords_to_avoid = [
        'struk', 'kasir', 'tanggal', 'jam', 'npwp', 'invoice', 'no.', 'id',
        'transaksi', 'subtotal', 'ppn', 'pajak', 'terima kasih', 'selamat datang',
        'alamat', 'telepon', 'phone', 'telp', 'email', 'fax', 'admin', 'cashier',
        'check', 'bill', 'kassa', 'lippo', 'mall', 'kemang', 'pos', 'title',
        'recept', 'rcpt', 'pt', 'cv', 'pax', 'op', 'gunawan'
    ]
    lines = text.strip().split('\n')

    # Prioritaskan pencarian pola brand yang unik dari seluruh teks (paling efektif)
    brand_patterns = [
        r'MOMI\s*&\s*TOY\'S\s*CR[EÊ]PERIE',
        r'MOMI\s*&\s*TOY\'S',
        r'CR[EÊ]PERIE',
        r'YOMART\s*RAMBAY',
        r'UMMI\s*MART',
        r'INDOMARET',
        r'Pisang\s*Juara',
        r'TOSERBA\s*YOGYA\s*SUKABUMI',
        r'ALFAMART',
        r'WAL\s*\W?MART',  # Untuk Walmart
        r'COSTCO\s*WHOLESALE',  # Untuk Costco
        r'Primo(?:\s*Family\s*Restaurant)?',  # Untuk Primo
        r'WHOLE\s*FOODS\s*MARKET',  # Untuk Whole Foods
        r'MIGUELS\s*MEXICAN',  # Untuk Miguels
    ]

    for bp in brand_patterns:
        brand_match = re.search(bp, text, re.IGNORECASE)
        if brand_match:
            normalized = normalize_merchant_name(brand_match.group(0))
            if normalized:
                return normalized

    # Fallback to top lines processing
    best_merchant_name = None
    max_score = 0

    for line_num, line in enumerate(lines[:10]):
        clean_line = line.strip()

        if len(clean_line) < 5 or len(clean_line) > 50:
            continue
        if re.search(r'\d{3,}[.,]\d{2,}', clean_line):
            continue
        if any(kw in clean_line.lower() for kw in keywords_to_avoid):
            continue
        if re.search(r'^\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}$', clean_line):
            continue
        if re.search(r'^\s*$', clean_line):
            continue

        normalized = normalize_merchant_name(clean_line)
        if normalized:
            score = len(normalized) * (10 - line_num)

            if re.search(r'(jl\.|jalan|no\.|street|st\.|road|rd\.|kpm)', normalized.lower()):
                score *= 0.5

            if len(normalized.split()) <= 2 and len(normalized) <= 7:
                score *= 0.7

            if score > max_score:
                best_merchant_name = normalized
                max_score = score

    return best_merchant_name

def extract_total(text):
    """
    Cari baris yang mengandung 'total' lalu ambil angka di kanannya.
    Fallback: cari baris terakhir yang berupa angka besar.
    Prioritaskan 'GRAND TOTAL' atau 'TOTAL BAYAR'.
    """
    text_lower = text.lower()

    total_patterns = [
        r'(?:grand\s*total|total\s*bayar|total\s*amount|amount\s*due|jumlah\s*bayar|jml\s*bayar|total\s*jual|final\s*total)\s*[:\-\=\s]*([RrPp\$]?\s*[0-9.,\s]+)',
        r'(?:total|jumlah|jml)\s*[:\-\=\s]*([RrPp\$]?\s*[0-9.,\s]+)',
    ]

    for pattern_str in total_patterns:
        match = re.search(pattern_str, text_lower)
        if match:
            return normalize_price(match.group(1))

    # Fallback 1: Cari "Total" di satu baris dan angka di baris berikutnya (dekat)
    lines = text.strip().split('\n')
    for i, line in enumerate(lines):
        if re.search(r'(total|jumlah|jml)', line, re.IGNORECASE) and i + 1 < len(lines):
            next_line = lines[i + 1]
            number_match = re.search(
                r'[RrPp\$]?\s*([0-9]{1,3}(?:[.,\s][0-9]{3})*(?:[.,\s][0-9]{1,2})?|[0-9]{3,}(?:[.,\s][0-9]{1,2})?)$',
                next_line.strip())
            if number_match:
                price = normalize_price(number_match.group(1))
                if price is not None and price > 0:
                    return price

    # Fallback 2: Cari angka terbesar di 5 baris terakhir
    potential_totals = []
    for line in reversed(lines[-8:]):
        numbers = re.findall(
            r'[RrPp\$]?\s*([0-9]{1,3}(?:[.,\s][0-9]{3})*(?:[.,\s][0-9]{1,2})?|[0-9]{3,}(?:[.,\s][0-9]{1,2})?)$',
            line.strip())
        for num_str_tuple in numbers:
            num_str = num_str_tuple[0]
            price = normalize_price(num_str)
            if price is not None and price > 0:
                potential_totals.append(price)

    if potential_totals:
        return max(potential_totals)
    return None


def extract_subtotal(text):
    """
    Cari subtotal dengan beberapa variasi keyword dan typo.
    Fallback: angka besar sebelum baris 'tax' atau 'total'.
    """
    text_lower = text.lower()
    subtotal_patterns = [
        r'(?:sub[\s\-]?total|sub[\s\-]?amt|subtotalan)\s*[:\-\=\s]*([RrPp\$]?\s*[0-9.,\s]+)',
        r'(?:nett?[\s\-]?sales?|before[\s\-]?tax|jumlah\s*sebelum\s*pajak|jml\s*blm\s*pjk|total\s*jual)\s*[:\-\=\s]*([RrPp\$]?\s*[0-9.,\s]+)',
        # Tambah 'total jual'
    ]
    for pattern_str in subtotal_patterns:
        match = re.search(pattern_str, text_lower)
        if match:
            return normalize_price(match.group(1))

    # Fallback 1: Cari di baris sebelum 'tax' atau 'total'
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'(tax|ppn|pajak|total|grand\s*total)', line, re.IGNORECASE):
            for j in range(max(0, i - 3), i):
                prev_line = lines[j]
                number_match = re.search(r'[RrPp\$]?\s*([0-9]{2,}(?:[.,\s][0-9]{3})*(?:[.,\s][0-9]{1,2})?)$', prev_line)
                if number_match:
                    potential_subtotal = normalize_price(number_match.group(1))
                    if potential_subtotal is not None and potential_subtotal > 0:
                        return potential_subtotal
    return None

def extract_tax(text):
    """
    Cari tax/ppn/pajak/service charge/vat/gst/levy pada struk.
    """
    text_lower = text.lower()
    tax_patterns = [
        r'(?:tax|vat|ppn|pajak|service[\s\-]?charge|gst|pph|levy|service)\s*[:\-\=\s]*([RrPp\$]?\s*[0-9.,\s]+)',
        r'(\d{1,2}\s*%)?\s*(?:tax|vat|ppn|pajak)\s*[:\-\=\s]*([RrPp\$]?\s*[0-9.,\s]+)',
    ]
    for pattern_str in tax_patterns:
        match = re.search(pattern_str, text_lower)
        if match:
            return normalize_price(match.groups()[-1])

    lines = text.split('\n')
    for line in lines:
        if re.search(r'(tax|ppn|pajak|vat|service|gst|levy)', line, re.IGNORECASE):
            number_match = re.search(r'[RrPp\$]?\s*([0-9]{2,}(?:[.,\s][0-9]{3})*(?:[.,\s][0-9]{1,2})?)$', line)
            if number_match:
                potential_tax = normalize_price(number_match.group(1))
                if potential_tax is not None and potential_tax > 0:
                    return potential_tax
    return None

def extract_items(text):
    """
    Ekstrak item belanja.
    Pola: nama barang, (opsional kuantitas), dan harga di kanan.
    Abaikan baris yang mengandung entitas lain.
    Mencoba pola yang lebih toleran terhadap karakter acak di tengah.
    Prioritaskan mencari item di antara subtotal/total.
    """
    lines = text.strip().split('\n')
    items = []

    # Kata kunci yang menandakan batas atas/bawah dari daftar item
    start_keywords = ['item', 'produk', 'barang', 'desc', 'description', 'nama barang', 'qty', 'harga', 'price',
                      'quantity', 'menu']
    end_keywords = ['subtotal', 'total', 'tax', 'ppn', 'pajak', 'grand total', 'jumlah', 'pembayaran', 'terima kasih',
                    'kembalian', 'cash', 'diskon', 'charge', 'change', 'total jual', 'total item', 'total jenis',
                    'total jual',
                    'closed bill', 'amount due']

    item_section_lines = []
    in_item_section = False

    # Tahap 1: Identifikasi Blok Item yang Potensial
    for line in lines:
        line_lower = line.lower()
        if not in_item_section and (any(kw in line_lower for kw in start_keywords) or re.search(r'^\s*\d+\s*[a-z]',
                                                                                                line_lower)):  # Start if keyword or line starts with number then letter
            in_item_section = True
            # Don't continue, process this line if it's an item line

        if in_item_section:
            if any(kw in line_lower for kw in end_keywords):
                break

            # Filter baris yang jelas-jelas bukan item
            if len(line.strip()) < 3 or len(line.strip()) > 70 or \
                    re.match(r'^[\d\s.,Rp$]+$', line.strip()) or \
                    re.match(r'^\s*(no|check|date|time|pax|op|rcpt#|rept#)', line_lower) or \
                    any(kw in line_lower for kw in start_keywords):  # Ensure not to re-process header lines
                continue
            item_section_lines.append(line)

    # Tahap 2: Ekstraksi Item dari Blok yang Ditemukan (Mencoba beberapa pola)
    for line in item_section_lines:
        current_item = None

        # Pola A: Nama Item dengan dash/spasi lalu harga (contoh: "Mix Coklat - Rp18.000")
        # Atau nama item yang mengandung "x" lalu harga (contoh: "Tiramisu Kear 1x Rp18.000")
        # Menggunakan [ -—–] untuk berbagai jenis dash/hyphen
        item_match_A = re.search(
            r'(.+?)\s*(?:[-—–]|\s*1?[xX])\s*([RrPp\$]?\s*[0-9.,\s]{1,})$',
            line.strip(),
            re.IGNORECASE
        )

        # Pola B: Kuantitas di awal, Nama, Harga di akhir
        # Contoh: "1 Woman 0 74,000", "2 Ham Cheese 16,000", "1x Rp18.000" (ini harga total item, bukan harga satuan)
        item_match_B = re.search(
            r'^\s*(\d+)(?:\s*[xX])?\s*(.+?)([RrPp\$]?\s*[0-9.,\s]{1,})$',
            line.strip(),
            re.IGNORECASE
        )

        # Pola C: Nama (opsional 'x Qty'), Harga di akhir (jika tidak ada qty di awal dan tidak ada dash)
        # Contoh: "Ice Java Tea 16,000", "MAHI MAHI FILLETS 8.99 B" (dari Whole Foods)
        item_match_C = re.search(
            r'(.+?)\s+(?:(?:x\s*(\d+))|\s*(\d+)\s+)?([RrPp\$]?\s*[0-9.,\s]{1,})$',
            line.strip(),
            re.IGNORECASE
        )

        # Urutan prioritas pola
        if item_match_A:  # Cocok untuk Pisang Juara: "Mix Coklat - Rp18.000"
            name_part = item_match_A.group(1).strip()
            price_str = item_match_A.group(2)
            qty = 1  # Asumsi qty 1 jika pola ini cocok

            normalized_name = normalize_item_name(name_part)
            normalized_price = normalize_price(price_str)

            if normalized_name and normalized_price is not None and normalized_price >= 0:
                if not any(kw in normalized_name.lower() for kw in end_keywords):
                    current_item = {
                        'name': normalized_name,
                        'price': normalized_price,
                        'qty': qty
                    }
        elif item_match_B:
            qty_str = item_match_B.group(1).replace('x', '').strip()
            name_and_mid_num_part = item_match_B.group(2).strip()
            price_str = item_match_B.group(3)

            qty = int(qty_str) if qty_str.isdigit() else 1
            normalized_price = normalize_price(price_str)

            cleaned_name_part = re.sub(r'\s*\d+(?:\.\d+)?\s*$', '', name_and_mid_num_part).strip()
            cleaned_name_part = re.sub(r'[^A-Za-z0-9\s&\'\.]', '', cleaned_name_part).strip()

            normalized_name = normalize_item_name(cleaned_name_part)

            if normalized_name and normalized_price is not None and normalized_price >= 0:
                if not any(kw in normalized_name.lower() for kw in end_keywords):
                    current_item = {
                        'name': normalized_name,
                        'price': normalized_price,
                        'qty': qty
                    }
        elif item_match_C:
            name_part = item_match_C.group(1).strip()
            qty_part = item_match_C.group(2) or item_match_C.group(3)
            price_str = item_match_C.group(4)

            normalized_name = normalize_item_name(name_part)
            normalized_price = normalize_price(price_str)

            if normalized_name and normalized_price is not None and normalized_price >= 0:
                if not any(kw in normalized_name.lower() for kw in end_keywords):
                    current_item = {
                        'name': normalized_name,
                        'price': normalized_price,
                        'qty': int(qty_part) if (qty_part and qty_part.isdigit()) else 1
                    }

        if current_item:
            items.append(current_item)

    # Final processing for items, removing duplicates and very generic entries.
    final_items = []
    seen_names = set()
    for item in items:
        # Check for potential item price being too low to be real item price for most cases (e.g. 0 or 1)
        # unless it is specifically 'Change' or 'Discount' etc.
        if item['name'] and item['name'].lower() not in seen_names and \
                not re.match(r'^\d+$', item['name']) and \
                len(item['name']) >= 2 and \
                item['price'] is not None and item['price'] >= 0:  # Ensure price is not negative

            # Additional filter for very small prices, unless it's a known small item or discount
            if item['price'] < 500 and not re.search(r'(disc|off|diskon|change|kembali|tax|ppn|pajak|point)',
                                                     item['name'].lower()):
                continue  # Filter items that are too cheap to be valid unless they are discounts etc.

            final_items.append(item)
            seen_names.add(item['name'].lower())

    try:
        final_items.sort(key=lambda x: text.find(x['name']))
    except:
        pass  # Ignore sorting error if name not found in text

    return final_items


# --- 3. Fungsi Pipeline Utama Ekstraksi ---
def extract_entities_rule_based(text):
    """
    Pipeline ekstraksi entitas rule-based.
    Kali ini lebih fokus pada menampilkan raw_text, dengan sedikit usaha ekstraksi entitas kunci.
    """
    extracted_data = {}
    # 1. Coba ekstrak Merchant Name (dengan prioritas pola brand)
    merchant_name = extract_merchant_name(text)
    extracted_data['merchant_name'] = merchant_name

    # 2. Coba ekstrak Date
    date = extract_date(text)
    extracted_data['date'] = date

    # 3. Coba ekstrak Total
    total = extract_total(text)
    extracted_data['total'] = total

    # 4. Coba ekstrak Subtotal dan Tax (jika ada dan mudah)
    subtotal = extract_subtotal(text)
    extracted_data['subtotal'] = subtotal

    tax = extract_tax(text)
    extracted_data['tax'] = tax

    # 5. Untuk Items, karena ini yang paling sulit, kita akan lewati detailnya.
    # Atau, kita bisa mencoba ekstraksi item yang sangat dasar sebagai contoh saja.
    # Untuk deadline, mungkin lebih baik fokus pada raw text.
    # Jika ingin tetap ada upaya items, gunakan extract_items seperti biasa, tapi jangan terlalu berharap akurat.
    items = extract_items(text)  # Tetap panggil, siapa tahu ada yang berhasil
    extracted_data['items'] = items

    # Tambahkan raw_text yang sudah ada
    extracted_data['raw_text'] = text  # Ini adalah raw_text yang sudah di-clean_text

    return extracted_data


# --- 4. Fungsi Preprocessing Gambar ---
def preprocess_pipeline(image_path):
    """
    Pipeline preprocessing yang lebih kuat untuk gambar struk.
    Menambahkan langkah-langkah tambahan untuk kontras dan denoising.
    """
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Gagal membaca gambar dari {image_path}")
        return None

    height, width = img.shape[:2]

    # 1. Resize gambar (opsional, jika gambar terlalu besar/kecil)
    target_width = 1000
    if width > target_width or width < target_width * 0.5:
        scale = target_width / width
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        height, width = img.shape[:2]

    # 2. Konversi ke grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # --- Bagian yang akan kita eksperimenkan ---

    # 3. Denoise (Fast Nl Means Denoising - h: filter strength)
    # Coba berbagai nilai h: 10, 15, 20, 25.
    # Terkadang h yang terlalu tinggi bisa menghilangkan detail teks.
    denoised = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21) # <--- Coba h=10 (lebih halus)

    # 4. Adaptive Thresholding - Binarisasi gambar
    # blockSize: harus ganjil. C: konstanta yang dikurangi dari mean.
    # Coba kombinasi (blockSize, C) yang berbeda:
    # (15, 8), (17, 10), (21, 10), (25, 12), (29, 15)
    thresh = cv2.adaptiveThreshold(
        denoised, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        15,  # <--- Coba blockSize=15 (lebih kecil untuk detail)
        8    # <--- Coba C=8 (membuat teks lebih tebal)
    )

    # 5. Optional: Inverse (jika teks putih di latar belakang gelap)
    # Ini sangat penting! Jika gambar asli adalah teks gelap di latar terang,
    # dan Anda meng-invert-nya menjadi teks putih di latar gelap, Tesseract mungkin kesulitan.
    # KESALAHAN UMUM: Meng-invert gambar yang TIDAK perlu di-invert.
    # Coba komentar baris ini untuk gambar yang teksnya hitam di latar putih.
    # Jika gambar yang Anda uji memiliki teks hitam di latar belakang putih (seperti kebanyakan struk),
    # maka baris ini mungkin MERUSAK OCR.
    # thresh = cv2.bitwise_not(thresh) # <--- COBA KOMENTARI BARIS INI!

    # 6. Morphological Operations (untuk membersihkan teks)
    # Kernel (2,2) mungkin terlalu agresif atau terlalu halus.
    # Coba (1,1) untuk operasi paling halus, atau (3,3) jika teks sangat tebal.
    # Coba juga cv2.MORPH_CLOSE jika cv2.MORPH_OPEN menghilangkan terlalu banyak teks.
    kernel_morph = np.ones((1, 1), np.uint8) # <--- Coba kernel (1,1)
    # cleaned_morph = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel_morph) # Biarkan OPEN

    # Jika ingin mencoba CLOSING (menutup celah di teks)
    # cleaned_morph = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_morph)

    # Jika ingin mencoba hanya dilate (mempertebal teks)
    cleaned_morph = cv2.dilate(thresh, kernel_morph, iterations=1) # <--- Coba ini sebagai ganti morphEx

    # --- Akhir Bagian Eksperimen ---


    # 7. Deskew (perbaiki kemiringan)
    coords = np.column_stack(np.where(cleaned_morph > 0))
    if coords.shape[0] > 0:
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = 90 + angle
        (h, w) = cleaned_morph.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(cleaned_morph, M, (w, h),
                                 flags=cv2.INTER_CUBIC,
                                 borderMode=cv2.BORDER_REPLICATE)
    else:
        rotated = cleaned_morph

    cv2.imwrite("preprocessed_output_debug.png", rotated)
    return rotated


# --- 5. Fungsi Utama Pemrosesan Gambar (dipanggil dari app.py) ---
def process_receipt_image(image_path):
    """
    Fungsi utama dengan konfigurasi OCR yang dioptimalkan
    """
    print(f"Memproses gambar: {image_path}")
    # 1. Preprocessing
    preprocessed_img = preprocess_pipeline(image_path)
    if preprocessed_img is None:
        return {"error": "Gagal melakukan preprocessing gambar."}

    # 2. OCR dengan konfigurasi yang dioptimalkan
    try:
        psm_modes = [6, 3, 4, 11, 12]  # Try more PSM modes for better results
        best_text = ""
        max_confidence_score = -1

        for psm in psm_modes:
            config = f'--oem 3 --psm {psm} -l eng+ind --dpi 300'
            try:
                data = pytesseract.image_to_data(preprocessed_img, config=config, output_type=pytesseract.Output.DICT)
                current_text = " ".join([word for word in data['text'] if word.strip() != ''])

                if current_text:
                    total_conf = sum([float(conf) for conf in data['conf'] if float(conf) != -1])
                    num_words = sum([1 for conf in data['conf'] if float(conf) != -1])
                    avg_confidence = total_conf / num_words if num_words > 0 else 0

                    if avg_confidence > max_confidence_score:
                        max_confidence_score = avg_confidence
                        best_text = current_text
            except Exception as e_inner:
                print(f"Warning: OCR failed for PSM {psm} with error: {e_inner}")
                continue

        raw_text = best_text
        print(f"Raw text from OCR (best_psm): \n{raw_text[:500]}...")

        if not raw_text.strip():
            return {"error": "OCR did not detect any text on the image."}

    except pytesseract.TesseractNotFoundError:
        return {"error": "Tesseract OCR not found. Please ensure it's installed and in your PATH."}
    except Exception as e:
        return {"error": f"An error occurred during OCR: {str(e)}"}

    # 3. Post-processing text
    clean_text = raw_text.strip()
    clean_text = re.sub(r'\s+', ' ', clean_text)
    clean_text = re.sub(r'[^\w\s.,:/$\-Rp]', '', clean_text)

    print(f"Clean text before extraction: \n{clean_text[:500]}...")

    # 4. Extract entities
    extracted_data = extract_entities_rule_based(clean_text)
    extracted_data['raw_text'] = raw_text
    return extracted_data