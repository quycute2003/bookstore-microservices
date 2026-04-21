"""
Seed Data — Đồng bộ với Knowledge Base của AI RAG (module2_knowledge)
Chạy: docker-compose exec product-service python seeds/products_seed.py
"""
import os, sys, django, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from modules.catalog.infrastructure.models.product_model import ProductModel

ProductModel.objects.all().delete()

KB_DIR = os.path.dirname(os.path.abspath(__file__))

# ─────────────────────────────────────────────
# ẢNH SÁCH — ISBN URL (ổn định hơn cover ID)
# ─────────────────────────────────────────────
BOOK_IMAGES = {
    1:  "https://covers.openlibrary.org/b/isbn/9780199232765-L.jpg",
    2:  "https://covers.openlibrary.org/b/isbn/9780143058144-L.jpg",
    3:  "https://covers.openlibrary.org/b/isbn/9780374528379-L.jpg",
    4:  "https://covers.openlibrary.org/b/isbn/9780143035008-L.jpg",
    5:  "https://covers.openlibrary.org/b/isbn/9780061122415-L.jpg",
    6:  "https://covers.openlibrary.org/b/isbn/9780439708180-L.jpg",
    7:  "https://covers.openlibrary.org/b/isbn/9780141439518-L.jpg",
    8:  "https://covers.openlibrary.org/b/isbn/9780451167712-L.jpg",
    9:  "https://covers.openlibrary.org/b/isbn/9780451525260-L.jpg",
    10: "https://covers.openlibrary.org/b/isbn/9780451524935-L.jpg",
    11: "https://covers.openlibrary.org/b/isbn/9780132350884-L.jpg",
    12: "https://covers.openlibrary.org/b/isbn/9780201633610-L.jpg",
    13: "https://covers.openlibrary.org/b/isbn/9781593276034-L.jpg",
    14: "https://covers.openlibrary.org/b/isbn/9780358105589-L.jpg",
    15: "https://covers.openlibrary.org/b/isbn/9780135957059-L.jpg",
    16: "https://covers.openlibrary.org/b/isbn/9780374533557-L.jpg",
    17: "https://covers.openlibrary.org/b/isbn/9780804139021-L.jpg",
    18: "https://covers.openlibrary.org/b/isbn/9781612680194-L.jpg",
    19: "https://covers.openlibrary.org/b/isbn/9780671027032-L.jpg",
    20: "https://covers.openlibrary.org/b/isbn/9780743269513-L.jpg",
    21: "https://covers.openlibrary.org/b/isbn/9781585424337-L.jpg",
    22: "https://covers.openlibrary.org/b/isbn/9780735211292-L.jpg",
    23: "https://covers.openlibrary.org/b/isbn/9780807014295-L.jpg",
    24: "https://covers.openlibrary.org/b/isbn/9781501197277-L.jpg",
    25: "https://covers.openlibrary.org/b/isbn/9780062316097-L.jpg",
    26: "https://covers.openlibrary.org/b/isbn/9780062464316-L.jpg",
    27: "https://covers.openlibrary.org/b/isbn/9780156012195-L.jpg",
    28: "https://covers.openlibrary.org/b/isbn/9780486117232-L.jpg",
}

# ─────────────────────────────────────────────
# ẢNH THỜI TRANG — Unsplash CDN
# ─────────────────────────────────────────────
CLOTH_IMAGES = {
    1:  "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?auto=format&fit=crop&w=500",
    2:  "https://images.unsplash.com/photo-1591047139829-d91aecb6caea?auto=format&fit=crop&w=500",
    3:  "https://images.unsplash.com/photo-1542272454315-4c01d7abdf4a?auto=format&fit=crop&w=500",
    4:  "https://images.unsplash.com/photo-1539533113208-f6df8cc8b543?auto=format&fit=crop&w=500",
    5:  "https://images.unsplash.com/photo-1556821840-3a63f95609a7?auto=format&fit=crop&w=500",
    6:  "https://images.unsplash.com/photo-1596755094514-f87e32f6b864?auto=format&fit=crop&w=500",
    7:  "https://images.unsplash.com/photo-1583743814966-8936f5b7be1a?auto=format&fit=crop&w=500",
    8:  "https://images.unsplash.com/photo-1620799140408-edc6dcb6d633?auto=format&fit=crop&w=500",
    9:  "https://images.unsplash.com/photo-1552374151-60a631623f95?auto=format&fit=crop&w=500",
    10: "https://images.unsplash.com/photo-1520975954732-57dd22299614?auto=format&fit=crop&w=500",
}

FALLBACK_BOOK  = "https://covers.openlibrary.org/b/isbn/9780062316097-L.jpg"
FALLBACK_CLOTH = "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=500"

# ─────────────────────────────────────────────
# 8 LOẠI MỚI — mỗi loại 5 sản phẩm
# ─────────────────────────────────────────────
NEW_PRODUCTS = [
    # ── VĂN PHÒNG PHẨM (category_id=12) ──
    {"product_type":"stationery","name":"Bút Máy Montblanc Meisterstück","price":1800000,"stock":20,"category_id":12,
     "image_url":"https://images.unsplash.com/photo-1585386959984-a4155224a1ad?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Montblanc","material":"Resin & Gold Nib","type":"fountain_pen"}},
    {"product_type":"stationery","name":"Sổ Tay Moleskine Classic Hardcover A5","price":350000,"stock":60,"category_id":12,
     "image_url":"https://images.unsplash.com/photo-1531346680769-a1d79b57de5c?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Moleskine","material":"Hardcover","type":"notebook"}},
    {"product_type":"stationery","name":"Bút Bi Parker Jotter","price":280000,"stock":80,"category_id":12,
     "image_url":"https://images.unsplash.com/photo-1455390582262-044cdead277a?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Parker","material":"Stainless Steel","type":"ballpoint"}},
    {"product_type":"stationery","name":"Bộ Màu Faber-Castell 48 Màu","price":450000,"stock":45,"category_id":12,
     "image_url":"https://images.unsplash.com/photo-1452860606245-08befc0ff44b?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Faber-Castell","material":"Colored pencil","type":"art_supplies"}},
    {"product_type":"stationery","name":"Tập Vẽ Canson XL Mix Media A4","price":180000,"stock":50,"category_id":12,
     "image_url":"https://images.unsplash.com/photo-1503676260728-1c00da094a0b?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Canson","material":"300gsm paper","type":"sketchbook"}},

    # ── ĐIỆN TỬ (category_id=13) ──
    {"product_type":"electronics","name":"Tai Nghe Sony WH-1000XM5","price":8500000,"stock":15,"category_id":13,
     "image_url":"https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Sony","warranty_months":12,"type":"headphone","color":"Black"}},
    {"product_type":"electronics","name":"Máy Đọc Sách Kindle Paperwhite 11th Gen","price":4200000,"stock":25,"category_id":13,
     "image_url":"https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Amazon","warranty_months":12,"type":"ereader","storage":"8GB"}},
    {"product_type":"electronics","name":"Đèn Đọc Sách Thông Minh BenQ e-Reading","price":2800000,"stock":18,"category_id":13,
     "image_url":"https://images.unsplash.com/photo-1534073828943-f801091bb18c?auto=format&fit=crop&w=500",
     "attributes":{"brand":"BenQ","warranty_months":24,"type":"desk_lamp","power":"13W"}},
    {"product_type":"electronics","name":"Loa Bluetooth JBL Flip 6","price":2500000,"stock":30,"category_id":13,
     "image_url":"https://images.unsplash.com/photo-1608043152269-423dbba4e7e1?auto=format&fit=crop&w=500",
     "attributes":{"brand":"JBL","warranty_months":12,"type":"speaker","battery_hours":12}},
    {"product_type":"electronics","name":"Sạc Dự Phòng Anker 20000mAh PowerCore","price":850000,"stock":40,"category_id":13,
     "image_url":"https://images.unsplash.com/photo-1609091839311-d5365f9ff1c5?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Anker","warranty_months":18,"type":"power_bank","capacity":"20000mAh"}},

    # ── ĐỒ CHƠI (category_id=14) ──
    {"product_type":"toy","name":"LEGO Classic 11021 — 90 Years of Play","price":1200000,"stock":20,"category_id":14,
     "image_url":"https://images.unsplash.com/photo-1587654780291-39c9404d746b?auto=format&fit=crop&w=500",
     "attributes":{"brand":"LEGO","age_range":"5+","material":"ABS Plastic","pieces":1100}},
    {"product_type":"toy","name":"Rubik GAN 356 RS Speed Cube 3x3","price":680000,"stock":35,"category_id":14,
     "image_url":"https://images.unsplash.com/photo-1585515320310-259814833e62?auto=format&fit=crop&w=500",
     "attributes":{"brand":"GAN","age_range":"8+","material":"ABS Plastic","type":"speed_cube"}},
    {"product_type":"toy","name":"Bộ Puzzle Gỗ 1000 Mảnh Phong Cảnh","price":380000,"stock":40,"category_id":14,
     "image_url":"https://images.unsplash.com/photo-1611532736597-de2d4265fba3?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Melissa & Doug","age_range":"12+","material":"Wood","pieces":1000}},
    {"product_type":"toy","name":"Drone Mini DJI Tello Edu","price":3500000,"stock":8,"category_id":14,
     "image_url":"https://images.unsplash.com/photo-1508614589041-895b88991e3e?auto=format&fit=crop&w=500",
     "attributes":{"brand":"DJI","age_range":"14+","material":"Plastic","flight_time":"13min"}},
    {"product_type":"toy","name":"Bộ Khoa Học Thí Nghiệm 4M Science Kit","price":450000,"stock":25,"category_id":14,
     "image_url":"https://images.unsplash.com/photo-1581092921461-eab62e97a780?auto=format&fit=crop&w=500",
     "attributes":{"brand":"4M","age_range":"8+","material":"Mixed","type":"science_kit"}},

    # ── MỸ PHẨM (category_id=15) ──
    {"product_type":"cosmetic","name":"Nước Hoa Chanel N°5 EDP 50ml","price":4500000,"stock":10,"category_id":15,
     "image_url":"https://images.unsplash.com/photo-1541643600914-78b084683702?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Chanel","volume_ml":50,"skin_type":"All","type":"perfume"}},
    {"product_type":"cosmetic","name":"Kem Dưỡng Da Lancôme Rénergie H.C.F. Triple Serum","price":1800000,"stock":15,"category_id":15,
     "image_url":"https://images.unsplash.com/photo-1556228578-0d85b1a4d571?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Lancôme","volume_ml":50,"skin_type":"All","type":"serum"}},
    {"product_type":"cosmetic","name":"Son Môi MAC Retro Matte Ruby Woo","price":680000,"stock":30,"category_id":15,
     "image_url":"https://images.unsplash.com/photo-1512496015851-a90fb38ba796?auto=format&fit=crop&w=500",
     "attributes":{"brand":"MAC","volume_ml":3,"skin_type":"All","color":"Ruby Woo","type":"lipstick"}},
    {"product_type":"cosmetic","name":"Sữa Rửa Mặt Cetaphil Gentle Skin Cleanser 500ml","price":285000,"stock":50,"category_id":15,
     "image_url":"https://images.unsplash.com/photo-1571781926291-c477ebfd024b?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Cetaphil","volume_ml":500,"skin_type":"Sensitive","type":"cleanser"}},
    {"product_type":"cosmetic","name":"Toner SK-II Facial Treatment Essence 230ml","price":3200000,"stock":12,"category_id":15,
     "image_url":"https://images.unsplash.com/photo-1620916566398-39f1143ab7be?auto=format&fit=crop&w=500",
     "attributes":{"brand":"SK-II","volume_ml":230,"skin_type":"All","type":"toner"}},

    # ── TÚI XÁCH (category_id=16) ──
    {"product_type":"bag","name":"Túi Da Michael Kors Selma Medium Satchel","price":8500000,"stock":8,"category_id":16,
     "image_url":"https://images.unsplash.com/photo-1548036328-c9fa89d128fa?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Michael Kors","material":"Leather","color":"Black","type":"satchel"}},
    {"product_type":"bag","name":"Balo Samsonite Cityvibe 2.0 15.6\" Laptop","price":2800000,"stock":15,"category_id":16,
     "image_url":"https://images.unsplash.com/photo-1553062407-98eeb64c6a62?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Samsonite","material":"Polyester","color":"Jet Black","type":"backpack"}},
    {"product_type":"bag","name":"Túi Tote Coach Cargo Tote","price":5500000,"stock":10,"category_id":16,
     "image_url":"https://images.unsplash.com/photo-1544816155-12df9643f363?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Coach","material":"Canvas & Leather","color":"Natural","type":"tote"}},
    {"product_type":"bag","name":"Túi Đeo Vai Kate Spade Knott Medium","price":4200000,"stock":7,"category_id":16,
     "image_url":"https://images.unsplash.com/photo-1575032617751-6ddec2089882?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Kate Spade","material":"Leather","color":"Warm Beige","type":"shoulder_bag"}},
    {"product_type":"bag","name":"Ví Da Nam Guess Vezzola Smart","price":1500000,"stock":20,"category_id":16,
     "image_url":"https://images.unsplash.com/photo-1627123424574-724758594785?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Guess","material":"Leather","color":"Brown","type":"wallet"}},

    # ── GIÀY DÉP (category_id=17) ──
    {"product_type":"shoe","name":"Nike Air Force 1 '07 Low White","price":2800000,"stock":30,"category_id":17,
     "image_url":"https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Nike","size":"38-44","color":"White","type":"sneaker"}},
    {"product_type":"shoe","name":"Adidas Stan Smith Cloud White Green","price":2500000,"stock":25,"category_id":17,
     "image_url":"https://images.unsplash.com/photo-1518002054494-3a6f94352e9d?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Adidas","size":"36-45","color":"White/Green","type":"sneaker"}},
    {"product_type":"shoe","name":"Converse Chuck Taylor All Star Hi Black","price":1800000,"stock":40,"category_id":17,
     "image_url":"https://images.unsplash.com/photo-1606107557195-0e29a4b5b4aa?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Converse","size":"36-44","color":"Black","type":"high_top"}},
    {"product_type":"shoe","name":"New Balance 574 Core Grey","price":2200000,"stock":20,"category_id":17,
     "image_url":"https://images.unsplash.com/photo-1539185441755-769473a23570?auto=format&fit=crop&w=500",
     "attributes":{"brand":"New Balance","size":"36-45","color":"Grey","type":"sneaker"}},
    {"product_type":"shoe","name":"Puma Suede Classic XXI Navy","price":1600000,"stock":22,"category_id":17,
     "image_url":"https://images.unsplash.com/photo-1608231387042-66d1773070a5?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Puma","size":"36-44","color":"Navy","type":"sneaker"}},

    # ── ĐỒNG HỒ (category_id=18) ──
    {"product_type":"watch","name":"Casio G-Shock GA-2100 Carbon Core Guard","price":2800000,"stock":18,"category_id":18,
     "image_url":"https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Casio","movement":"Quartz","water_resistance":"200m","color":"Black"}},
    {"product_type":"watch","name":"Daniel Wellington Classic Sheffield 40mm","price":3500000,"stock":12,"category_id":18,
     "image_url":"https://images.unsplash.com/photo-1524592094714-0f0654e359e8?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Daniel Wellington","movement":"Quartz","water_resistance":"30m","color":"Silver/Black"}},
    {"product_type":"watch","name":"Fossil Gen 6 Smartwatch 44mm","price":7500000,"stock":8,"category_id":18,
     "image_url":"https://images.unsplash.com/photo-1544117519-31a4b719223d?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Fossil","movement":"Wear OS","water_resistance":"30m","color":"Smoke Stainless Steel"}},
    {"product_type":"watch","name":"Seiko 5 Sports SRPD Automatic 43mm","price":4800000,"stock":10,"category_id":18,
     "image_url":"https://images.unsplash.com/photo-1533139502658-0198f920d8e8?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Seiko","movement":"Automatic","water_resistance":"100m","color":"Black Dial"}},
    {"product_type":"watch","name":"Orient Mako III Diver Automatic","price":5200000,"stock":9,"category_id":18,
     "image_url":"https://images.unsplash.com/photo-1522312346375-d1a52e2b99b3?auto=format&fit=crop&w=500",
     "attributes":{"brand":"Orient","movement":"Automatic","water_resistance":"200m","color":"Navy Blue"}},

    # ── QUÀ TẶNG (category_id=19) ──
    {"product_type":"gift","name":"Hộp Quà Valentine LUMIÈRE Premium","price":450000,"stock":50,"category_id":19,
     "image_url":"https://images.unsplash.com/photo-1549465220-1a8b9238cd48?auto=format&fit=crop&w=500",
     "attributes":{"occasion":"Valentine","includes":"Card + Ribbon + Box","brand":"LUMIÈRE"}},
    {"product_type":"gift","name":"Combo Sách + Nến Thơm + Bookmarks","price":650000,"stock":30,"category_id":19,
     "image_url":"https://images.unsplash.com/photo-1512689975003-1b22a40d374b?auto=format&fit=crop&w=500",
     "attributes":{"occasion":"Birthday / Any","includes":"1 book + candle + 5 bookmarks","brand":"LUMIÈRE"}},
    {"product_type":"gift","name":"Bộ Trà Cao Cấp TWG Tea Selection","price":850000,"stock":20,"category_id":19,
     "image_url":"https://images.unsplash.com/photo-1544787219-7f47ccb76574?auto=format&fit=crop&w=500",
     "attributes":{"occasion":"Any","includes":"10 sachets × 5 flavors","brand":"TWG Tea"}},
    {"product_type":"gift","name":"Hộp Socola Godiva Belgian Chocolates 24pc","price":680000,"stock":25,"category_id":19,
     "image_url":"https://images.unsplash.com/photo-1548155782-1b2c0dde3e83?auto=format&fit=crop&w=500",
     "attributes":{"occasion":"Any","includes":"24 pieces assorted","brand":"Godiva"}},
    {"product_type":"gift","name":"Voucher Spa & Wellness LUMIÈRE 2 Giờ","price":1200000,"stock":15,"category_id":19,
     "image_url":"https://images.unsplash.com/photo-1540555700478-4be289fbecef?auto=format&fit=crop&w=500",
     "attributes":{"occasion":"Anniversary / Birthday","includes":"2h massage + tea","brand":"LUMIÈRE"}},
]

# ─────────────────────────────────────────────
# SEED
# ─────────────────────────────────────────────
book_count = cloth_count = 0

# 1. Books (28 cuốn)
docs_book = os.path.join(KB_DIR, 'books_catalog.json')
if os.path.exists(docs_book):
    with open(docs_book, 'r', encoding='utf-8') as f:
        books = json.load(f)
    for b in books:
        ProductModel.objects.create(
            product_type='book', name=b['title'],
            price=b['price'], stock=b['stock'], category_id=2,
            image_url=BOOK_IMAGES.get(b['id'], FALLBACK_BOOK),
            attributes={"author": b['author'], "isbn": b.get('id')},
        )
        book_count += 1

# 2. Clothes (10 sản phẩm)
docs_cloth = os.path.join(KB_DIR, 'clothes_catalog.json')
if os.path.exists(docs_cloth):
    with open(docs_cloth, 'r', encoding='utf-8') as f:
        clothes = json.load(f)
    for c in clothes:
        ProductModel.objects.create(
            product_type='cloth', name=c['name'],
            price=c['price'], stock=c['stock'], category_id=11,
            image_url=CLOTH_IMAGES.get(c['id'], FALLBACK_CLOTH),
            attributes={"brand": c['brand'], "size": c['size'], "color": c['color']},
        )
        cloth_count += 1

# 3. 8 loại mới (40 sản phẩm)
for p in NEW_PRODUCTS:
    ProductModel.objects.create(**p)

total = ProductModel.objects.count()
new_count = len(NEW_PRODUCTS)
print(f"✅ Seed xong: {book_count} sách | {cloth_count} thời trang | {new_count} sản phẩm mới = {total} tổng")
