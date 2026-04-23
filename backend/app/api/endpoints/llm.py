from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional, Union
from app.services.vector_service import vector_service
from app.api import deps

router = APIRouter()

class EmbeddingRequest(BaseModel):
    model: Optional[str] = None
    input: Union[str, List[str]]

@router.post("/embeddings")
async def create_embedding(
    request: EmbeddingRequest,
    user_id: str = Depends(deps.get_identity),
):
    """
    使用向量服务生成 Embeddings。
    """
    try:
        if not request.model:
            # 如果未提供，则使用服务的默认值
            try:
                vectors = await vector_service.embed_text(request.input, user_id=user_id)
            except ValueError:
                 raise HTTPException(status_code=400, detail="未指定嵌入模型且没有系统默认值。")
        else:
            # 显式传递请求的模型
            vectors = await vector_service.embed_text(request.input, model=request.model, user_id=user_id)
            
        return {"data": [{"embedding": v} for v in vectors], "model": vector_service.model_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
