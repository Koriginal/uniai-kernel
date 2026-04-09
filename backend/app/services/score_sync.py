import logging
import asyncio
from sqlalchemy import select, func, case
from app.core.db import SessionLocal
from app.models.graph_execution import GraphExecution
from app.models.agent_score import AgentScoreHistory

logger = logging.getLogger(__name__)

class ScoreSyncProcessor:
    """
    Agent 评分同步处理器
    定期将图执行记录 (GraphExecution) 中的真实表现数据同步到 AgentScoreHistory 中。
    实现“使用即进化”的反馈闭环。
    """
    
    async def run_once(self):
        """执行一次全量同步"""
        async with SessionLocal() as db:
            try:
                # 1. 查找所有涉及到的 Agent ID
                stmt = select(GraphExecution.agent_id).distinct()
                res = await db.execute(stmt)
                agent_ids = [r[0] for r in res.all() if r[0]]
                
                if not agent_ids:
                    # 关键：即便没有数据，也要确保事务正常退出而不是 idle
                    await db.rollback()
                    return
                
                logger.debug(f"[ScoreSync] Found {len(agent_ids)} agents to sync.")
                
                for aid in agent_ids:
                    # 2. 统计原始指标
                    stats_stmt = (
                        select(
                            func.count(GraphExecution.id).label("total"),
                            func.avg(GraphExecution.duration_ms).label("avg_dur"),
                            func.sum(case((GraphExecution.status == "success", 1), else_=0)).label("success_cnt")
                        )
                        .where(GraphExecution.agent_id == aid)
                    )
                    stats_res = await db.execute(stats_stmt)
                    row = stats_res.fetchone()
                    
                    if not row or row.total == 0:
                        continue
                    
                    success_rate = round(row.success_cnt / row.total, 4)
                    avg_dur = round(float(row.avg_dur or 0), 2)
                    
                    # 3. 更新最新历史记录 (此处采用合并/覆盖逻辑)
                    new_score = AgentScoreHistory(
                        agent_id=aid,
                        total_calls=row.total,
                        success_rate=success_rate,
                        avg_duration_ms=avg_dur,
                        avg_quality_score=0.85, 
                        specialties=[]
                    )
                    db.add(new_score)
                    
                await db.commit()
                logger.info(f"[ScoreSync] ✅ Sync completed for {len(agent_ids)} agents.")
            except Exception as e:
                logger.error(f"[ScoreSync] ❌ Sync failed: {e}")
                await db.rollback()
            finally:
                await db.close()

    async def start_background_loop(self, interval_seconds: int = 3600):
        """启动后台循环任务 (默认每小时一次)"""
        while True:
            await self.run_once()
            await asyncio.sleep(interval_seconds)

# 全局单例
score_sync = ScoreSyncProcessor()
