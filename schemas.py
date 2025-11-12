from pydantic import BaseModel, Field
from typing import Optional, List

# Users
class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    bio: Optional[str] = Field(None, description="Short bio")
    avatar_url: Optional[str] = Field(None, description="Avatar image URL")

# Reels
class Reel(BaseModel):
    video_url: str
    caption: Optional[str] = None
    hashtags: List[str] = []
    user_id: Optional[str] = None

# Vendors and offerings
class Vendor(BaseModel):
    user_id: str
    category: str
    title: str
    description: Optional[str] = None
    pricing_type: str = Field(..., description="one_time or subscription")
    price_credits: int = Field(..., ge=0)
