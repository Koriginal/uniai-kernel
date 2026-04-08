import React from 'react';
import { Card, Typography, Spin, Space, Tag } from 'antd';
import { NodeIndexOutlined, RobotOutlined, CrownOutlined } from '@ant-design/icons';
import type { Agent } from './ChatView';

const { Title, Text } = Typography;

interface AgentTopologyGraphProps {
  agents: Agent[];
  onClickNode?: (agent: Agent) => void;
}

const AgentTopologyGraph: React.FC<AgentTopologyGraphProps> = ({ agents, onClickNode }) => {
  // 确保有 Orchestrator (当前选中的 agent 或默认的)
  // 此处做简单展示，所有非 public 的视为专家，被 public 的协调
  
  if (!agents || agents.length === 0) {
    return null;
  }

  const orchestrators = agents.filter(a => a.is_public);
  const experts = agents.filter(a => !a.is_public);

  return (
    <Card 
      style={{ marginBottom: 24, borderRadius: 8, border: '1px solid #e1e4e8', overflow: 'hidden' }}
      bodyStyle={{ padding: 0 }}
    >
      <div style={{ padding: '16px 20px', background: '#fafafa', borderBottom: '1px solid #f0f0f0' }}>
        <Space>
          <NodeIndexOutlined style={{ color: '#1890ff', fontSize: 18 }} />
          <Title level={5} style={{ margin: 0 }}>协作拓扑图 (Collaboration Topology)</Title>
        </Space>
      </div>
      <div style={{ 
          padding: '40px 24px', 
          background: '#fff', 
          display: 'flex', 
          justifyContent: 'center', 
          alignItems: 'center',
          gap: 60,
          position: 'relative'
      }}>
        {/* 背景连接线 */}
        <div style={{
           position: 'absolute',
           top: '50%',
           left: '50%',
           transform: 'translate(-50%, -50%)',
           width: '50%',
           height: 2,
           background: `repeating-linear-gradient(90deg, #d9d9d9, #d9d9d9 4px, transparent 4px, transparent 8px)`,
           zIndex: 0
        }} />

        {/* 左侧：Orchestrator 组 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, zIndex: 1 }}>
           {orchestrators.length > 0 ? orchestrators.map(orc => (
               <div 
                  key={orc.id} 
                  onClick={() => onClickNode && onClickNode(orc)}
                  style={{
                      padding: '12px 20px', background: '#e6f7ff', border: '1px solid #91d5ff',
                      borderRadius: 8, cursor: 'pointer', display: 'flex', flexDirection: 'column', 
                      alignItems: 'center', boxShadow: '0 4px 12px rgba(24,144,255,0.1)',
                      transition: 'all 0.3s'
                  }}
                  className="topology-node"
               >
                   <CrownOutlined style={{ fontSize: 24, color: '#1890ff', marginBottom: 8 }} />
                   <Text strong>{orc.name}</Text>
                   <Tag color="cyan" style={{ marginTop: 4, marginInlineEnd: 0 }}>主控 Orchestrator</Tag>
               </div>
           )) : (
               <div style={{ padding: '12px 20px', background: '#f5f5f5', borderRadius: 8, border: '1px dashed #d9d9d9' }}>
                   <Text type="secondary">暂无主控角色</Text>
               </div>
           )}
        </div>

        {/* 中间：路由枢纽（象征 LangGraph Handoff Node） */}
        <div style={{
            width: 48, height: 48, borderRadius: '50%', background: '#fff',
            border: '2px solid #1890ff', display: 'flex', justifyContent: 'center', 
            alignItems: 'center', zIndex: 1, boxShadow: '0 0 0 4px #e6f7ff'
        }}>
            <NodeIndexOutlined style={{ fontSize: 20, color: '#1890ff' }} />
        </div>

        {/* 右侧：专家集群 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, zIndex: 1 }}>
           {experts.map(exp => (
               <div 
                  key={exp.id}
                  onClick={() => onClickNode && onClickNode(exp)}
                  style={{
                      padding: '10px 16px', background: '#f9f0ff', border: '1px solid #d3adf7',
                      borderRadius: 8, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 12,
                      boxShadow: '0 2px 8px rgba(114,46,209,0.06)', transition: 'all 0.3s'
                  }}
                  className="topology-node"
               >
                   <div style={{ position: 'relative' }}>
                       <RobotOutlined style={{ fontSize: 20, color: '#722ed1' }} />
                       <div style={{
                          position: 'absolute', bottom: -2, right: -4,
                          width: 8, height: 8, borderRadius: '50%',
                          background: exp.is_active ? '#52c41a' : '#bfbfbf',
                          border: '2px solid #fff'
                       }} />
                   </div>
                   <div style={{ display: 'flex', flexDirection: 'column' }}>
                       <Text strong style={{ fontSize: 13 }}>{exp.name}</Text>
                       <Text type="secondary" style={{ fontSize: 11 }}>Expert Node</Text>
                   </div>
               </div>
           ))}
           {experts.length === 0 && (
               <div style={{ padding: '12px 20px', background: '#f5f5f5', borderRadius: 8, border: '1px dashed #d9d9d9' }}>
                   <Text type="secondary">暂无专家节点</Text>
               </div>
           )}
        </div>
      </div>
      <style>{`
          .topology-node:hover {
              transform: translateY(-2px);
              box-shadow: 0 6px 16px rgba(0,0,0,0.08) !important;
          }
      `}</style>
    </Card>
  );
};

export default AgentTopologyGraph;
