from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Union

class ChatRequest(BaseModel):
    question: str
    url: Optional[Union[HttpUrl, List[HttpUrl]]] = None

class ChatResponse(BaseModel):
    answer: str
    source_url: str