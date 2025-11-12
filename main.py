import os
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime, timezone

from database import db, create_document, get_documents

app = FastAPI(title="Hustle Network API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure uploads directory exists
UPLOAD_DIR = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


# ---------- Models (response/request) ----------
class CommentIn(BaseModel):
    user_id: Optional[str] = None
    text: str

class CommentOut(BaseModel):
    _id: str
    user_id: Optional[str] = None
    text: str
    created_at: datetime

class ReelOut(BaseModel):
    _id: str
    video_url: str
    caption: Optional[str] = None
    hashtags: List[str] = []
    likes: int = 0
    comments: List[CommentOut] = []
    user_id: Optional[str] = None
    created_at: datetime

class SearchResult(BaseModel):
    type: str
    id: str
    title: str
    subtitle: Optional[str] = None

class CategoryInfo(BaseModel):
    key: str
    name: str
    average_credits: int
    description: str


# ---------- Utility ----------

def oid_str(oid) -> str:
    return str(oid) if isinstance(oid, ObjectId) else oid


def build_reel_out(doc) -> ReelOut:
    return ReelOut(
        _id=oid_str(doc.get("_id")),
        video_url=doc.get("video_url"),
        caption=doc.get("caption"),
        hashtags=doc.get("hashtags", []),
        likes=len(doc.get("likes", [])),
        comments=[
            CommentOut(
                _id=oid_str(c.get("_id")),
                user_id=c.get("user_id"),
                text=c.get("text"),
                created_at=c.get("created_at"),
            )
            for c in doc.get("comments", [])
        ],
        user_id=doc.get("user_id"),
        created_at=doc.get("created_at", datetime.now(timezone.utc)),
    )


# ---------- Routes ----------
@app.get("/")
def read_root():
    return {"message": "Hustle Network Backend Running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": [],
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = os.getenv("DATABASE_NAME") or "❌ Not Set"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
                response["connection_status"] = "Connected"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response


# Categories & credit model
@app.get("/api/meta/categories", response_model=List[CategoryInfo])
def get_categories():
    return [
        CategoryInfo(key="entertainment", name="Entertainment", average_credits=10,
                     description="Fun skills: sports tricks, gaming coaching, creative hobbies."),
        CategoryInfo(key="trades", name="Trades", average_credits=45,
                     description="Blue-collar skills: plumbing, electrical, mechanic, etc."),
        CategoryInfo(key="regulation", name="Regulation", average_credits=20,
                     description="Wellness & health: fitness, nutrition, mental health."),
        CategoryInfo(key="network", name="NetWork", average_credits=40,
                     description="Internet careers: ecommerce, trading, coding, streaming."),
        CategoryInfo(key="education", name="Education", average_credits=20,
                     description="School and life skills from grade 7 to university, plus misc."),
    ]


# Upload a reel (video up to 60s) - store file and metadata
@app.post("/api/reels", response_model=ReelOut)
async def upload_reel(
    file: UploadFile = File(...),
    caption: Optional[str] = Form(None),
    hashtags: Optional[str] = Form(None),  # comma-separated
    user_id: Optional[str] = Form(None),
):
    # Validate file type (basic)
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="Only video uploads are allowed")

    # Save file
    filename = f"{datetime.now(timezone.utc).timestamp()}_{file.filename}"
    save_path = os.path.join(UPLOAD_DIR, filename)
    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    backend_url = os.getenv("BACKEND_URL")  # optional env
    public_url = f"/uploads/{filename}"
    if backend_url:
        # Provide absolute URL if env set
        public_url = f"{backend_url.rstrip('/')}{public_url}"

    # Prepare document
    doc = {
        "video_url": public_url,
        "caption": caption,
        "hashtags": [h.strip().lstrip('#') for h in (hashtags or "").split(',') if h.strip()],
        "likes": [],
        "comments": [],
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    new_id = db["reel"].insert_one(doc).inserted_id
    saved = db["reel"].find_one({"_id": new_id})
    return build_reel_out(saved)


# List reels (newest first)
@app.get("/api/reels", response_model=List[ReelOut])
def list_reels(limit: int = 20, skip: int = 0):
    cursor = db["reel"].find({}).sort("created_at", -1).skip(skip).limit(limit)
    return [build_reel_out(doc) for doc in cursor]


# Like a reel
@app.post("/api/reels/{reel_id}/like", response_model=ReelOut)
def like_reel(reel_id: str, user_id: Optional[str] = None):
    try:
        oid = ObjectId(reel_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid reel id")

    reel = db["reel"].find_one({"_id": oid})
    if not reel:
        raise HTTPException(status_code=404, detail="Reel not found")

    likes = set([str(u) for u in reel.get("likes", [])])
    if user_id:
        if user_id in likes:
            likes.remove(user_id)
        else:
            likes.add(user_id)
    else:
        # Anonymous like increments without user tracking
        likes.add("anon")

    db["reel"].update_one({"_id": oid}, {"$set": {"likes": list(likes), "updated_at": datetime.now(timezone.utc)}})
    updated = db["reel"].find_one({"_id": oid})
    return build_reel_out(updated)


# Comment on a reel
@app.post("/api/reels/{reel_id}/comment", response_model=ReelOut)
def comment_reel(reel_id: str, payload: CommentIn):
    try:
        oid = ObjectId(reel_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid reel id")

    comment = {
        "_id": ObjectId(),
        "user_id": payload.user_id,
        "text": payload.text,
        "created_at": datetime.now(timezone.utc),
    }
    res = db["reel"].update_one({"_id": oid}, {"$push": {"comments": comment}, "$set": {"updated_at": datetime.now(timezone.utc)}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Reel not found")
    updated = db["reel"].find_one({"_id": oid})
    return build_reel_out(updated)


# Search across users (name), reels (captions/hashtags)
@app.get("/api/search", response_model=List[SearchResult])
def search(q: str):
    query = {"$regex": q, "$options": "i"}

    results: List[SearchResult] = []

    # Users by name
    for u in db["user"].find({"name": query}).limit(10):
        results.append(SearchResult(type="user", id=oid_str(u["_id"]), title=u.get("name"), subtitle=u.get("bio") or u.get("email")))

    # Reels by caption
    for r in db["reel"].find({"$or": [{"caption": query}, {"hashtags": query}]}).limit(20):
        title = (r.get("caption") or "").strip() or "Reel"
        results.append(SearchResult(type="reel", id=oid_str(r["_id"]), title=title, subtitle="#" + ", #".join(r.get("hashtags", [])[:3]) if r.get("hashtags") else None))

    return results


# Content: pricing model and vendor options
@app.get("/api/meta/pricing")
def pricing_model():
    return {
        "credit_system": {
            "daily_credits": True,
            "note": "Users receive daily credits to learn or exchange skills. Exchanging costs fewer credits than pure learning.",
        },
        "vendor_pricing": {
            "options": [
                {"type": "one_time", "description": "Great for single sessions or compact courses."},
                {"type": "subscription", "description": "Best for ongoing programs like dropshipping or trading."},
            ]
        },
        "categories": [c.model_dump() for c in get_categories()],
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
