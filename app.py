import json
import os
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
from groq import Groq
from dotenv import load_dotenv

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

# 💡 設定 SQLite 資料庫
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"sqlite:///{os.path.join(BASE_DIR, 'travel.db')}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# 💡 初始化 Groq Client
load_dotenv()

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))


# --- 資料庫模型定義 (符合 2 張表與外鍵關聯條件) ---
class Category(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    attractions = db.relationship(
        "Attraction", backref="category_rel", lazy=True, cascade=""
    )


class Attraction(db.Model):
    __tablename__ = "attractions"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    town = db.Column(db.String(50))
    address = db.Column(db.Text)
    image = db.Column(db.Text)
    description = db.Column(db.Text)
    phone = db.Column(db.String(50), default="暫無聯絡電話")
    created_at = db.Column(
        db.String(20), default=lambda: datetime.now().strftime("%Y-%m-%d")
    )

    # 外鍵關聯到 categories 表
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)


# 💡 台灣觀光官方常見代碼與文字對照表
CATEGORY_MAP = {
    "1": "文化歷史 / 古蹟",
    "2": "自然生態 / 風景",
    "3": "遊憩休閒",
    "4": "體育健身 / 戶外",
    "5": "宗教信仰 / 廟宇",
    "6": "藝術展演 / 美術館",
    "7": "產業觀光 / 觀光工廠",
    "8": "國家公園 / 森林遊樂區",
    "9": "溫泉泉質",
    "10": "夜市 / 在地商圈",
    "11": "地質奇觀",
    "12": "小吃美食",
    "13": "古蹟建築",
    "14": "老街風情",
    "15": "民俗節慶",
    "16": "自然風景區",
    "17": "國家風景區",
    "18": "森林遊樂區",
    "26": "人文歷史區",
    "27": "主題樂園",
    "30": "都會觀光",
}

def clean_category_name(raw_cat):
    if not raw_cat:
        return "其他 / 一般景net"
    cat_str = str(raw_cat).strip()
    if cat_str in CATEGORY_MAP:
        return CATEGORY_MAP[cat_str]
    if not cat_str.isdigit() and len(cat_str) > 1:
        return cat_str
    return "其他 / 一般景點"

# 啟動時自動初始化資料庫與匯入初始 JSON 資料
def init_db_data():
    with app.app_context():
        db.create_all()

        # 如果資料庫已經有景點，就不重複匯入
        if Attraction.query.first():
            return

        attraction_file = os.path.join(BASE_DIR, "js", "AttractionList.json")
        if not os.path.exists(attraction_file):
            return

        try:
            with open(attraction_file, "r", encoding="utf-8-sig") as f:
                data = json.load(f)

            items = []
            if isinstance(data, dict):
                if "Infos" in data and "Info" in data["Infos"]:
                    items = data["Infos"]["Info"]
                else:
                    for val in data.values():
                        if isinstance(val, list):
                            items = val
                            break
            elif isinstance(data, list):
                items = data

            for idx, item in enumerate(items[:30]):  # 預設匯入前 30 筆
                raw_postal = item.get("PostalAddress")
                if not isinstance(raw_postal, dict) or not raw_postal.get(
                    "StreetAddress"
                ):
                    continue

                name = item.get("AttractionName") or "未命名景點"
                city = raw_postal.get("City") or ""
                town = raw_postal.get("Town") or ""
                street = raw_postal.get("StreetAddress") or ""
                full_address = f"{city}{town}{street}"

                # 處理分類
                classes = item.get("AttractionClasses")
                raw_cat = (
                    classes[0]
                    if isinstance(classes, list) and len(classes) > 0
                    else (classes if isinstance(classes, str) else "")
                )
                cat_name = clean_category_name(raw_cat)

                # 取得或建立分類
                category = Category.query.filter_by(name=cat_name).first()
                if not category:
                    category = Category(name=cat_name)
                    db.session.add(category)
                    db.session.commit()

                # 圖片
                images = item.get("Images")
                image_url = ""
                if isinstance(images, list) and len(images) > 0:
                    first_img = images[0]
                    image_url = (
                        first_img.get("MediaURL") or first_img.get("URL") or ""
                        if isinstance(first_img, dict)
                        else str(first_img)
                    )
                elif isinstance(images, dict):
                    image_url = images.get("MediaURL") or images.get("URL") or ""

                # 電話
                phone = "暫無聯絡電話"
                telephones = item.get("Telephones")
                if isinstance(telephones, list) and len(telephones) > 0:
                    phone = (
                        telephones[0].get("Tel") or "暫無聯絡電話"
                        if isinstance(telephones[0], dict)
                        else str(telephones[0])
                    )

                desc = item.get("Description") or "暫無詳細介紹"
                update_time = item.get(
                    "UpdateTime", datetime.now().strftime("%Y-%m-%d")
                )

                new_spot = Attraction(
                    name=name,
                    city=city,
                    town=town,
                    address=street,
                    image=image_url,
                    description=desc,
                    phone=phone,
                    created_at=update_time,
                    category_id=category.id,
                )
                db.session.add(new_spot)
            db.session.commit()
            print("📦 成功從 JSON 匯入初始資料至 SQLite 資料庫！")
        except Exception as e:
            print(f"初始化資料庫失敗: {e}")


# ===== API 路由 =====

# API：健康檢查
@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "ok",
        "message": "API is running"
    }), 200

# API：取得所有景點
@app.route("/api/attractions", methods=["GET"])
def get_attractions():
    spots = Attraction.query.all()
    result = []
    for s in spots:
        result.append(
            {
                "id": s.id,
                "name": s.name,
                "city": s.city[:3],
                "town": s.town,
                "address": s.address,
                "category": s.category_rel.name if s.category_rel else "一般",
                "phone": s.phone,
                "image": s.image,
                "description": s.description,
                "createdAt": s.created_at,
            }
        )
    return (
        jsonify(
            {"message": "資料讀取成功", "count": len(result), "attractions": result}
        ),
        200,
    )

# API：取得單一景點
@app.route("/api/attractions/<int:spot_id>", methods=["GET"])
def get_attraction_by_id(spot_id):
    s = Attraction.query.get(spot_id)
    if s:
        spot_data = {
            "id": s.id,
            "name": s.name,
            "city": s.city[:3],
            "town": s.town,
            "address": s.address,
            "category": s.category_rel.name if s.category_rel else "一般",
            "phone": s.phone,
            "image": s.image,
            "description": s.description,
            "createdAt": s.created_at,
        }
        return jsonify({"message": "讀取成功", "attraction": spot_data}), 200
    return jsonify({"error": "找不到該景點"}), 404

# API：新增景點
@app.route("/api/attractions", methods=["POST"])
def add_attraction():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "請傳送正確的 JSON 格式資料"}), 400

    name = data.get("name")
    city = data.get("city")
    category_name = data.get("category", "其他 / 一般景點")
    phone = data.get("phone", "暫無聯絡電話")
    image = data.get("image", "")
    description = data.get("description", "")

    if not name or not city:
        return jsonify({"error": "請提供完整的景點名稱與城市"}), 400

    # 確保分類存在
    category = Category.query.filter_by(name=category_name).first()
    if not category:
        category = Category(name=category_name)
        db.session.add(category)
        db.session.commit()

    new_spot = Attraction(
        name=name,
        city=city,
        image=image,
        description=description,
        phone=phone,
        created_at=datetime.now().strftime("%Y-%m-%d"),
        category_id=category.id,
    )
    db.session.add(new_spot)
    db.session.commit()

    return (
        jsonify(
            {
                "message": "新增景點成功！",
                "attraction": {
                    "id": new_spot.id,
                    "name": new_spot.name,
                    "city": new_spot.city,
                    "category": category.name,
                    "image": new_spot.image,
                    "description": new_spot.description,
                    "createdAt": new_spot.created_at,
                },
            }
        ),
        201,
    )

# API：修改景點
@app.route("/api/attractions/<int:spot_id>", methods=["PUT"])
def update_attraction(spot_id):
    s = Attraction.query.get(spot_id)
    if not s:
        return jsonify({"error": "找不到該景點"}), 404

    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "請傳送正確的 JSON 格式資料"}), 400

    s.name = data.get("name", s.name)
    s.city = data.get("city", s.city)
    s.description = data.get("description", s.description)
    s.phone = data.get("phone", s.phone)
    s.image = data.get("image", s.image)

    category_name = data.get("category")
    if category_name:
        category = Category.query.filter_by(name=category_name).first()
        if not category:
            category = Category(name=category_name)
            db.session.add(category)
            db.session.commit()
        s.category_id = category.id

    db.session.commit()
    return jsonify({"message": "更新景點成功！"}), 200

# API：刪除景點
@app.route("/api/attractions/<int:spot_id>", methods=["DELETE"])
def delete_attraction(spot_id):
    s = Attraction.query.get(spot_id)
    if not s:
        return jsonify({"error": "找不到該景點"}), 404

    db.session.delete(s)
    db.session.commit()
    return jsonify({"message": "刪除景點成功！"}), 200

# API：統計分析 Dashboard
@app.route("/api/dashboard/statistics", methods=["GET"])
def get_statistics():
    try:
        spots = Attraction.query.all()
        category_count = {}
        city_count = {}

        for s in spots:
            cat_name = s.category_rel.name if s.category_rel else "其他"
            address = s.city or ""
            short_city = "台灣"
            if len(address) >= 3 and ("市" in address[:3] or "縣" in address[:3]):
                short_city = address[:3]
            elif address:
                short_city = address[:2]

            category_count[cat_name] = category_count.get(cat_name, 0) + 1
            city_count[short_city] = city_count.get(short_city, 0) + 1

        total_items = len(spots) or 1

        category_stats = [
            {"category": k, "count": v, "percent": round((v / total_items) * 100, 1)}
            for k, v in sorted(category_count.items(), key=lambda x: x[1], reverse=True)
        ]

        city_stats = [
            {"city": k, "count": v, "percent": round((v / total_items) * 100, 1)}
            for k, v in sorted(city_count.items(), key=lambda x: x[1], reverse=True)
        ]

        return (
            jsonify(
                {
                    "message": "統計資料讀取成功",
                    "statistics": {
                        "total": total_items,
                        "categoryStats": category_stats,
                        "cityStats": city_stats,
                    },
                }
            ),
            200,
        )
    except Exception as e:
        return jsonify({"error": f"統計資料處理失敗: {str(e)}"}), 500

# API：AI 旅遊行程推薦
@app.route("/api/ai/recommend", methods=["POST"])
def generate_trip():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "請傳送正確的 JSON 格式資料"}), 400

    destination = data.get("destination")
    days = data.get("days", 1)
    preference = data.get("preference", "一般觀光")

    if not destination:
        return jsonify({"error": "請提供旅遊目的地"}), 400

    prompt = f"""
請幫我規劃一份詳細的台灣旅遊行程。

旅遊目的地：{destination}
旅遊天數：{days} 天
旅遊偏好主題：{preference}

請根據以上條件，設計一份適合旅客實際執行的完整行程。
行程安排請盡量詳細，包含：

1. 每一天的完整時間安排（例如上午、下午、晚上）。
2. 景點推薦與景點特色介紹。
3. 建議的景點遊覽順序，避免不必要的往返。
4. 景點之間的交通方式與大約移動時間。
5. 當地特色美食或推薦餐廳。
6. 適合安排的休息、購物或自由活動時間。
7. 每日行程的小提醒（例如天氣、穿著、預約需求、熱門時段避開方式）。
8. 根據旅遊天數提供合理的節奏，不要安排過度密集。

重要限制：

- 每一天至少安排 4 個旅遊活動。
- 每個活動 description 至少 80 字。
- 必須包含上午、下午、晚上安排。
- 不可使用摘要形式。
- 不可只列景點名稱。
- 請輸出完整可執行旅遊計畫。

請嚴格依照以下 JSON 格式回傳，絕對不要包含任何 Markdown 程式碼標記，只輸出純 JSON 文字：

{{
    "destination": "{destination}",
    "days": {days},
    "preference": "{preference}",
    "itinerary": [
        {{
            "day": "第 1 天",
            "activities": [
                {{
                    "time": "09:00-11:30",
                    "location": "",
                    "description": "",
                    "transportation": "",
                    "food": "",
                    "tip": ""
                }},
                {{
                    "time": "12:00-14:00",
                    "location": "",
                    "description": "",
                    "transportation": "",
                    "food": "",
                    "tip": ""
                }},
                {{
                    "time": "14:30-17:30",
                    "location": "",
                    "description": "",
                    "transportation": "",
                    "food": "",
                    "tip": ""
                }},
                {{
                    "time": "18:00-21:00",
                    "location": "",
                    "description": "",
                    "transportation": "",
                    "food": "",
                    "tip": ""
                }}
            ]
        }}
    ],
    "tip": "給旅客的一句實用貼心小建議"
}}
"""

    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "你是一個專業的台灣旅遊規劃 AI 助手，請務必只回傳合法的 JSON 格式內容。",
                },
                {"role": "user", "content": prompt},
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            max_tokens=4000,
        )

        raw_text = chat_completion.choices[0].message.content.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        raw_text = raw_text.strip()

        trip_json = json.loads(raw_text)
        return jsonify(trip_json), 200

    except Exception as e:
        return jsonify({"error": f"AI 引擎產生行程失敗: {str(e)}"}), 500


if __name__ == "__main__":
    init_db_data()
    print("🚀 SQLite 資料庫與 Groq AI 旅遊 API 伺服器已啟動 (Port 5000)...")
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
