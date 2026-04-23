from fastapi import APIRouter, HTTPException, Depends
from app.models.openai import EmbeddingRequest, EmbeddingResponse, EmbeddingData, EmbeddingUsage
from app.services.vector_service import vector_service
from app.api import deps
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/embeddings")
async def create_embedding(
    request: EmbeddingRequest,
    user_id: str = Depends(deps.get_identity),
):
    """
    OpenAI 兼容的向量化接口。
    """
    try:
        # 使用内核向量引擎执行嵌入
        vectors = await vector_service.embed_text(request.input, model=request.model, user_id=user_id)
        
        # 组装标准响应格式
        data = [
            EmbeddingData(index=i, embedding=v) 
            for i, v in enumerate(vectors)
        ]
        
        return EmbeddingResponse(
            data=data,
            model=request.model or vector_service.model_name,
            usage=EmbeddingUsage(prompt_tokens=0, total_tokens=0) # 暂未接入 Token 统计
        )
    except Exception as e:
        logger.error(f"[Embeddings] Failed to generate: {e}")
        raise HTTPException(status_code=500, detail=str(e))
