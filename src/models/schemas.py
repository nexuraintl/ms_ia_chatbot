from pydantic import BaseModel, HttpUrl

class ChatRequest(BaseModel):
    question: str
    url: HttpUrl

class ChatResponse(BaseModel):
    answer: str
    source_url: str