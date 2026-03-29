from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Union
from app.core.llm import completion
from app.services.vector_service import vector_service

router = APIRouter()

class CompletionRequest(BaseModel):
    model: str
    messages: List[Dict[str, str]]
    temperature: Optional[float] = 0.7

class EmbeddingRequest(BaseModel):
    model: Optional[str] = None
    input: Union[str, List[str]]

from typing import Union

@router.post("/chat/completions")
async def chat_completion(request: CompletionRequest):
    """
    使用 LiteLLM 的标准聊天完成端点。
    """
    try:
        response = await completion(
            model=request.model,
            messages=request.messages,
            temperature=request.temperature
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/embeddings")
async def create_embedding(request: EmbeddingRequest):
    """
    使用向量服务生成 Embeddings。
    """
    try:
        if not request.model:
            # 如果未提供，则使用服务的默认值
            try:
                vectors = await vector_service.embed_text(request.input)
            except ValueError:
                 raise HTTPException(status_code=400, detail="未指定嵌入模型且没有系统默认值。")
        else:
            # 显式传递请求的模型
            vectors = await vector_service.embed_text(request.input, model=request.model)
            
        return {"data": [{"embedding": v} for v in vectors], "model": vector_service.model_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
