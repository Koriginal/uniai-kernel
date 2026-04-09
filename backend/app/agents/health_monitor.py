import logging
from typing import Dict, Any, List, Optional
from sqlalchemy import select, func, desc
from datetime import datetime, timedelta

from app.core.db import SessionLocal
from app.models.graph_execution import GraphExecution

logger = logging.getLogger(__name__)

class HealthReport:
    """健康诊断报告数据模型"""
    def __init__(self, overall_status: str = "healthy"):
        self.overall_status = overall_status
        self.diagnostics: List[str] = []
        self.node_stats: Dict[str, Any] = {}
        self.timestamp = datetime.now()

    def add_diagnostic(self, msg: str):
        self.diagnostics.append(msg)

class HealthMonitor:
    """
    图引擎健康自检引擎
    基于 GraphExecution 遥测数据，识别运行时的异常模式。
    """
    
    async def diagnose(self, window_minutes: int = 60) -> HealthReport:
        """执行图引擎健康诊断"""
        report = HealthReport()
        
        async with SessionLocal() as db:
            # 1. 节点统计数据采集
            node_stats = await self.get_node_stats(db, window_minutes)
            report.node_stats = node_stats
            
            # 2. 核心分析逻辑
            for node, stats in node_stats.items():
                # a. 错误率检测 (阈值: 30%)
                error_rate = stats.get("error_rate", 0)
                if error_rate > 30:
                    report.overall_status = "degraded"
                    report.add_diagnostic(f"Node '{node}' has high error rate: {error_rate:.1f}%")
                
                # b. 延迟退化检测 (P95 暂用简单均值对比，实际可进一步精细化)
                avg_duration = stats.get("avg_duration", 0)
                if avg_duration > 15000: # 超过15秒
                    report.add_diagnostic(f"Node '{node}' is slow: {avg_duration/1000:.1f}s avg")
            
            # 3. 活跃会话死锁核查 (查询是否有极高步数且活跃的 Session)
            # 这部分逻辑可以扩展为查询活跃会话的迭代次数分布
            
        return report

    async def get_node_stats(self, db, minutes: int = 60) -> Dict[str, Any]:
        """获取最近一段时间内各节点的统计信息"""
        since = datetime.now() - timedelta(minutes=minutes)
        
        # 聚合查询
        stmt = (
            select(
                GraphExecution.node_name,
                func.count(GraphExecution.id).label("total_calls"),
                func.avg(GraphExecution.duration_ms).label("avg_duration"),
                func.sum(case((GraphExecution.status == "error", 1), else_=0)).label("error_count")
            )
            .where(GraphExecution.created_at >= since)
            .group_by(GraphExecution.node_name)
        )
        
        # 处理 SQLAlchemy case 语法差异 (此处简略适配)
        from sqlalchemy import case
        
        result = await db.execute(stmt)
        rows = result.all()
        
        stats = {}
        for row in rows:
            name = row.node_name
            total = row.total_calls
            error_cnt = row.error_count or 0
            stats[name] = {
                "total_calls": total,
                "avg_duration": float(row.avg_duration or 0),
                "error_rate": (error_cnt / total * 100) if total > 0 else 0
            }
        return stats

# 全局单例
health_monitor = HealthMonitor()
