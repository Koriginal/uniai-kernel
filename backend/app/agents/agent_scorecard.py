import logging
from typing import Dict, Any, List, Optional
from sqlalchemy import select, func, desc
from datetime import datetime, timedelta

from app.core.db import SessionLocal
from app.models.graph_execution import GraphExecution
from app.models.agent_score import AgentScoreHistory

logger = logging.getLogger(__name__)

class AgentScore:
    """Agent 能力得分数据模型"""
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.total_calls = 0
        self.success_rate = 0.0
        self.avg_duration_ms = 0.0
        self.avg_quality_score = 0.0
        self.specialties: List[str] = []

class AgentScorecard:
    """
    Agent 评分卡系统
    负责评估每个 Agent 的历史表现，为路由决策提供数据支持。
    """
    
    async def get_agent_score(self, db, agent_id: str) -> Optional[AgentScore]:
        """
        从数据库获取指定 Agent 的最新评分。
        """
        stmt = (
            select(AgentScoreHistory)
            .where(AgentScoreHistory.agent_id == agent_id)
            .order_by(desc(AgentScoreHistory.computed_at))
            .limit(1)
        )
        result = await db.execute(stmt)
        history = result.scalar_one_or_none()
        
        if not history:
            return None
            
        score = AgentScore(agent_id)
        score.total_calls = history.total_calls
        score.success_rate = history.success_rate
        score.avg_duration_ms = history.avg_duration_ms
        score.avg_quality_score = history.avg_quality_score
        score.specialties = history.specialties
        return score

    async def rank_experts_for_task(self, db, task_description: str, expert_ids: List[str]) -> List[AgentScore]:
        """
        为特定任务对候选专家进行排名。
        目前初版：简单基于综合得分 (success_rate * quality_score) 排序。
        未来可扩展：基于任务描述与 specialties 的语义匹配。
        """
        scores = []
        for eid in expert_ids:
            score = await self.get_agent_score(db, eid)
            if score:
                scores.append(score)
            else:
                # 无数据者给予默认基准分
                default = AgentScore(eid)
                default.success_rate = 0.8
                default.avg_quality_score = 0.7
                scores.append(default)
        
        # 排序：得分越高越靠前
        scores.sort(key=lambda s: (s.success_rate * s.avg_quality_score), reverse=True)
        return scores

    async def update_all_scores(self):
        """
        定期任务：根据最近的图执行记录更新所有 Agent 的评分。
        """
        async with SessionLocal() as db:
            # 1. 获取所有有执行记录的 Agent
            stmt = select(GraphExecution.agent_id).distinct()
            result = await db.execute(stmt)
            agent_ids = [row[0] for row in result.all() if row[0]]
            
            for aid in agent_ids:
                # 2. 计算该 Agent 的统计指标
                stats_stmt = (
                    select(
                        func.count(GraphExecution.id).label("total"),
                        func.avg(GraphExecution.duration_ms).label("avg_dur"),
                        func.sum(case((GraphExecution.status == "success", 1), else_=0)).label("success_cnt")
                    )
                    .where(GraphExecution.agent_id == aid)
                )
                from sqlalchemy import case
                stats_res = await db.execute(stats_stmt)
                row = stats_res.fetchone()
                
                if not row or row.total == 0:
                    continue
                    
                # 3. 保存到历史表
                new_history = AgentScoreHistory(
                    agent_id=aid,
                    total_calls=row.total,
                    success_rate=(row.success_cnt / row.total),
                    avg_duration_ms=float(row.avg_dur or 0),
                    avg_quality_score=0.8, # 默认先给 0.8，后续接入反馈
                    specialties=[] # 未来从 LLM 总结提取
                )
                db.add(new_history)
                
            await db.commit()
            logger.info(f"[Scorecard] Updated scores for {len(agent_ids)} agents.")

# 全局单例
scorecard = AgentScorecard()
