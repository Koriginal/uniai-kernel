import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { 
  ReactFlow, 
  Background, 
  Controls, 
  MiniMap, 
  useNodesState, 
  useEdgesState, 
  addEdge, 
  Panel,
  Handle,
  MarkerType, 
  Position,
  type Connection, 
  type Edge, 
  type NodeProps,
  type Node
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { 
  Card, Typography, Space, Tag, Avatar, Badge, 
  Button, Segmented, Drawer, List, 
  message, Empty, Divider,
  Switch,
  Form,
  Input,
  Select
} from 'antd';
import { 
  NodeIndexOutlined, CrownOutlined, RobotOutlined, 
  ThunderboltFilled, LinkOutlined, SaveOutlined, 
  HistoryOutlined, RocketOutlined, BuildOutlined,
  CheckCircleOutlined, ClockCircleOutlined,
  InfoCircleOutlined,
  DisconnectOutlined,
  DeleteOutlined,
  PlusOutlined
} from '@ant-design/icons';
import axios from 'axios';
import type { Agent } from './ChatView';
import * as dagre from 'dagre';

const { Title, Text } = Typography;

type FlowNodeProps = NodeProps;

const handleStyle = {
  width: 18,
  height: 18,
  borderRadius: '50%',
  border: '3px solid #fff',
  boxShadow: '0 0 0 8px rgba(24,144,255,0.12)',
} as const;

// --- 类型定义 ---
interface AgentNodeData {
  agent: Agent;
  stats?: any;
  [key: string]: any;
}

interface ToolMeta {
  name: string;
  label: string;
  description: string;
  category: string;
  [key: string]: unknown;
}

interface ToolNodeData {
  tool: ToolMeta;
  linkedAgents: string[];
  isMounted: boolean;
  [key: string]: unknown;
}

// --- 自定义节点组件 (Custom Agent Node) ---
const AgentNode: React.FC<FlowNodeProps> = (props) => {
  const data = props.data as AgentNodeData;
  const agent = data?.agent;
  const stats = data?.stats;

  if (!agent) {
    return null;
  }

  const isOrc = agent.role === 'orchestrator';
  
  return (
    <div style={{
      background: '#fff',
      border: `2px solid ${isOrc ? '#faad14' : '#d3adf7'}`,
      borderRadius: '16px',
      padding: '0',
      width: 240,
      boxShadow: isOrc ? '0 12px 30px rgba(250,173,20,0.18)' : '0 8px 20px rgba(0,0,0,0.06)',
      overflow: 'hidden',
      transition: 'all 0.3s ease'
    }} className="agent-node-card">
      {/* 头部：角色与名称 */}
      <div style={{ 
        background: isOrc ? 'linear-gradient(135deg, #fffbe6 0%, #fff7e6 100%)' : 'linear-gradient(135deg, #f9f0ff 0%, #ffffff 100%)',
        padding: '14px',
        borderBottom: `1px solid ${isOrc ? '#ffe58f' : '#efdbff'}`,
        display: 'flex',
        alignItems: 'center',
        gap: 12
      }}>
        <Badge dot color={agent.is_active ? '#52c41a' : '#bfbfbf'} offset={[-2, 34]}>
          <Avatar 
            size={44} 
            icon={isOrc ? <CrownOutlined /> : <RobotOutlined />} 
            style={{ 
              background: isOrc ? 'linear-gradient(135deg, #ffc53d 0%, #faad14 100%)' : 'linear-gradient(135deg, #b37feb 0%, #722ed1 100%)',
              boxShadow: '0 4px 8px rgba(0,0,0,0.1)'
            }} 
          />
        </Badge>
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <div style={{ fontWeight: 800, fontSize: 15, color: '#1a1a1a', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {agent.name}
          </div>
          <Tag color={isOrc ? 'gold' : 'purple'} style={{ fontSize: 9, margin: 0, borderRadius: 4 }}>
            {isOrc ? 'ORCHESTRATOR' : 'EXPERT'}
          </Tag>
        </div>
      </div>

      {/* 指标看板 (Scorecard Integration) */}
      <div style={{ padding: '12px', background: '#fafafa' }}>
        {stats && stats.total_calls > 0 ? (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ textAlign: 'center', flex: 1 }}>
              <div style={{ fontSize: 10, color: '#8c8c8c' }}>成功率</div>
              <div style={{ fontSize: 13, fontWeight: 700, color: (stats.success_rate || 0) > 0.8 ? '#52c41a' : '#faad14' }}>
                {((stats.success_rate || 0) * 100).toFixed(0)}%
              </div>
            </div>
            <Divider type="vertical" />
            <div style={{ textAlign: 'center', flex: 1 }}>
              <div style={{ fontSize: 10, color: '#8c8c8c' }}>调用/次</div>
              <div style={{ fontSize: 13, fontWeight: 700 }}>{stats.total_calls}</div>
            </div>
            <Divider type="vertical" />
            <div style={{ textAlign: 'center', flex: 1 }}>
              <div style={{ fontSize: 10, color: '#8c8c8c' }}>时延</div>
              <div style={{ fontSize: 13, fontWeight: 700 }}>{(stats.avg_duration_ms || 0) < 1000 ? `${Math.round(stats.avg_duration_ms || 0)}ms` : `${((stats.avg_duration_ms || 0)/1000).toFixed(1)}s`}</div>
            </div>
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: '4px 0' }}>
            <Text type="secondary" style={{ fontSize: 11 }}>暂无执行指标</Text>
          </div>
        )}
      </div>

      {/* 专家技能/触发词 */}
      {!isOrc && (
        <div style={{ padding: '10px 14px', borderTop: '1px solid #f0f0f0' }}>
          <div style={{ fontSize: 10, color: '#8c8c8c', marginBottom: 6 }}>
            <ThunderboltFilled style={{ color: '#faad14' }} /> 语义入口
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {agent.routing_keywords && agent.routing_keywords.length > 0 ? (
              agent.routing_keywords.slice(0, 3).map(k => (
                <Tag key={k} bordered={false} style={{ fontSize: 10, borderRadius: 4, background: '#f0f0f0', margin: 0 }}>{k}</Tag>
              ))
            ) : (
              <Text type="secondary" style={{ fontSize: 10, fontStyle: 'italic' }}>无触发词</Text>
            )}
          </div>
        </div>
      )}

      {/* 端口句柄 */}
      <Handle
        type="target"
        position={Position.Left}
        style={{
          ...handleStyle,
          background: '#1890ff',
          left: -10,
        }}
      />
      <Handle
        type="source"
        position={Position.Right}
        style={{
          ...handleStyle,
          background: '#faad14',
          right: -10,
        }}
      />
    </div>
  );
};

const ToolNode: React.FC<FlowNodeProps> = (props) => {
  const data = props.data as ToolNodeData;
  const tool = data?.tool;

  if (!tool) return null;

  return (
    <div
      style={{
        background: 'linear-gradient(135deg, #eff6ff 0%, #ffffff 100%)',
        border: '2px solid #93c5fd',
        borderRadius: 16,
        width: 220,
        padding: 14,
        boxShadow: '0 10px 24px rgba(37,99,235,0.08)',
      }}
      className="tool-node-card"
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: 12,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'linear-gradient(135deg, #60a5fa 0%, #2563eb 100%)',
            color: '#fff',
            fontSize: 18,
          }}
        >
          <LinkOutlined />
        </div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 14, color: '#0f172a', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {tool.label}
          </div>
          <Tag color="blue" style={{ margin: 0, fontSize: 10, borderRadius: 4 }}>
            {tool.category}
          </Tag>
        </div>
      </div>
      <Text type="secondary" style={{ display: 'block', fontSize: 11, minHeight: 32 }}>
        {tool.description || '能力节点'}
      </Text>
      <div style={{ marginTop: 10 }}>
        <Text code style={{ fontSize: 11 }}>{tool.name}</Text>
      </div>
      <div style={{ marginTop: 10 }}>
        <Text type="secondary" style={{ fontSize: 10 }}>
          {data.isMounted ? `已挂载到 ${data.linkedAgents.length} 个专家` : '未挂载，可在手动模式下拖线接入'}
        </Text>
      </div>

      <Handle
        type="target"
        position={Position.Left}
        style={{
          ...handleStyle,
          background: '#2563eb',
          left: -10,
        }}
      />
    </div>
  );
};

// --- 主组件 ---
const nodeTypes = {
  agent: AgentNode,
  tool: ToolNode,
} as const;

interface AgentTopologyEditorProps {
  agents: Agent[];
  onClickNode?: (agent: Agent) => void;
  onAgentsUpdated?: () => void;
  scopeAgentId?: string | null;
}

const AgentTopologyEditor: React.FC<AgentTopologyEditorProps> = ({ agents, onClickNode, onAgentsUpdated, scopeAgentId }) => {
  const [edgeForm] = Form.useForm();
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<any>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [mode, setMode] = useState<'auto' | 'manual'>('auto');
  const [versions, setVersions] = useState<any[]>([]);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [activeVersionId, setActiveVersionId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [tools, setTools] = useState<ToolMeta[]>([]);
  const [showExperts, setShowExperts] = useState(true);
  const [showTools, setShowTools] = useState(true);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [edgeEditorOpen, setEdgeEditorOpen] = useState(false);
  const [savingEdge, setSavingEdge] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [activeVersion, setActiveVersion] = useState<any | null>(null);

  // 加载版本列表
  const fetchVersions = useCallback(async () => {
    try {
      const res = await axios.get('/api/v1/graph/versions?template_id=standard');
      setVersions(res.data.versions || []);
      setActiveVersionId(res.data.active_version_id);
      
      const active = (res.data.versions || []).find((v: any) => v.is_active);
      setActiveVersion(active || null);
      if (active && active.mode === 'manual') {
        setMode('manual');
      }
    } catch (err) {
      console.error("Failed to fetch versions", err);
    }
  }, []);

  useEffect(() => {
    fetchVersions();
  }, [fetchVersions]);

  const scopedOrchestrator = useMemo(
    () => agents.find((agent) => agent.id === scopeAgentId && agent.role === 'orchestrator')
      || agents.find((agent) => agent.role === 'orchestrator')
      || null,
    [agents, scopeAgentId],
  );

  const visibleAgents = useMemo(() => {
    const scoped = scopedOrchestrator
      ? agents.filter((agent) => agent.id === scopedOrchestrator.id || agent.role === 'expert')
      : agents;
    if (showExperts) return scoped;
    return scoped.filter((agent) => agent.role === 'orchestrator');
  }, [agents, showExperts, scopedOrchestrator]);

  const selectedEdge = useMemo(
    () => edges.find((edge) => edge.id === selectedEdgeId) || null,
    [edges, selectedEdgeId],
  );

  const selectedRouteAgents = useMemo(() => {
    if (!selectedEdge) return { sourceAgent: null, targetAgent: null };
    const sourceAgent = agents.find((agent) => agent.id === selectedEdge.source) || null;
    const targetAgent = agents.find((agent) => agent.id === selectedEdge.target) || null;
    return { sourceAgent, targetAgent };
  }, [agents, selectedEdge]);

  const selectedToolMeta = useMemo(() => {
    if (!selectedEdge || !String(selectedEdge.id).startsWith('tool-edge-')) return null;
    const toolName = String(selectedEdge.target).replace('tool:', '');
    return tools.find((tool) => tool.name === toolName) || null;
  }, [selectedEdge, tools]);

  const renderedEdges = useMemo(
    () =>
      edges.map((edge) => ({
        ...edge,
        selected: edge.id === selectedEdgeId,
        className: edge.id === selectedEdgeId ? 'selected' : '',
      })),
    [edges, selectedEdgeId],
  );

  const canvasAgentIds = useMemo(
    () => new Set(nodes.filter((node) => node.type === 'agent').map((node) => node.id)),
    [nodes],
  );

  const canvasToolIds = useMemo(
    () => new Set(nodes.filter((node) => node.type === 'tool').map((node) => String(node.id).replace('tool:', ''))),
    [nodes],
  );

  const availableExperts = useMemo(
    () => visibleAgents.filter((agent) => agent.role === 'expert' && !canvasAgentIds.has(agent.id)),
    [visibleAgents, canvasAgentIds],
  );

  const availableTools = useMemo(
    () => tools.filter((tool) => !canvasToolIds.has(tool.name)),
    [tools, canvasToolIds],
  );

  const updateAgentInCanvas = useCallback((agentId: string, updater: (agent: Agent) => Agent) => {
    setNodes((current) =>
      current.map((node) =>
        node.id === agentId && node.type === 'agent'
          ? {
              ...node,
              data: {
                ...node.data,
                agent: updater(node.data.agent),
              },
            }
          : node,
      ),
    );
  }, [setNodes]);

  const addAgentToCanvas = useCallback(async (agentId: string) => {
    const agent = visibleAgents.find((item) => item.id === agentId);
    if (!agent) return;
    let stats = null;
    try {
      const res = await axios.get(`/api/v1/agents/${agent.id}/stats`);
      stats = res.data;
    } catch {}
    setNodes((current) => [
      ...current,
      {
        id: agent.id,
        type: 'agent',
        data: { agent, stats },
        position: { x: 200 + current.length * 28, y: 160 + current.length * 18 },
      },
    ]);
    setPaletteOpen(false);
  }, [visibleAgents, setNodes]);

  const addToolToCanvas = useCallback((toolName: string) => {
    const tool = tools.find((item) => item.name === toolName);
    if (!tool) return;
    const linkedAgents = visibleAgents.filter((agent) => (agent.tools || []).includes(tool.name)).map((agent) => agent.id);
    setNodes((current) => [
      ...current,
      {
        id: `tool:${tool.name}`,
        type: 'tool',
        data: { tool, linkedAgents, isMounted: linkedAgents.length > 0 },
        position: { x: 520 + current.length * 20, y: 180 + current.length * 18 },
        draggable: true,
        selectable: true,
      },
    ]);
    setPaletteOpen(false);
  }, [tools, visibleAgents, setNodes]);

  useEffect(() => {
    const fetchTools = async () => {
      try {
        const res = await axios.get('/api/v1/registry/actions');
        setTools(res.data || []);
      } catch (err) {
        console.error('Failed to fetch tool catalog', err);
      }
    };
    fetchTools();
  }, []);

  // 节点数据同步与自动布局
  useEffect(() => {
    if (mode === 'manual' && activeVersion?.topology) {
      const setupManualNodes = async () => {
        const topology = activeVersion.topology || {};
        const savedNodes = (topology.nodes || []) as any[];
        const savedEdges = (topology.edges || []) as any[];

        const manualAgentNodes = await Promise.all(
          savedNodes
            .filter((node) => node.type === 'agent')
            .map(async (savedNode) => {
              const agentId = savedNode.data?.agent_id || savedNode.id;
              const agent = visibleAgents.find((item) => item.id === agentId);
              if (!agent) return null;
              let stats = null;
              try {
                const res = await axios.get(`/api/v1/agents/${agent.id}/stats`);
                stats = res.data;
              } catch {}
              return {
                id: agent.id,
                type: 'agent',
                data: { agent, stats },
                position: savedNode.position || { x: 0, y: 0 },
              };
            }),
        );

        const manualToolNodes = savedNodes
          .filter((node) => node.type === 'tool')
          .map((savedNode) => {
            const toolName = savedNode.data?.tool_name || String(savedNode.id).replace('tool:', '');
            const tool = tools.find((item) => item.name === toolName);
            if (!tool) return null;
            const linkedAgents = visibleAgents.filter((agent) => (agent.tools || []).includes(tool.name)).map((agent) => agent.id);
            return {
              id: `tool:${tool.name}`,
              type: 'tool',
              data: { tool, linkedAgents, isMounted: linkedAgents.length > 0 },
              position: savedNode.position || { x: 0, y: 0 },
              draggable: true,
              selectable: true,
            };
          })
          .filter(Boolean) as Node<ToolNodeData>[];

        const manualEdges: Edge[] = savedEdges.map((edge) => ({
          id: edge.id || `e-${edge.source}-${edge.target}`,
          source: edge.source,
          target: edge.target,
          label: edge.label,
          animated: !String(edge.id || '').startsWith('tool-edge-'),
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: String(edge.id || '').startsWith('tool-edge-') ? '#93c5fd' : '#1890ff',
          },
          style: String(edge.id || '').startsWith('tool-edge-')
            ? { stroke: '#93c5fd', strokeWidth: 1.5, strokeDasharray: '5 5' }
            : { stroke: '#1890ff', strokeWidth: 2 },
          selectable: true,
        }));

        setNodes([...manualAgentNodes.filter(Boolean), ...manualToolNodes] as Node<any>[]);
        setEdges(manualEdges);
        setSelectedEdgeId(null);
      };

      setupManualNodes();
      return;
    }

    if (!visibleAgents || visibleAgents.length === 0) return;

    const setupNodes = async () => {
      const orchestrators = scopedOrchestrator ? [scopedOrchestrator] : visibleAgents.filter(a => a.role === 'orchestrator');
      
      const nodePromises = visibleAgents.map(async (agent) => {
        let stats = null;
        try {
          const res = await axios.get(`/api/v1/agents/${agent.id}/stats`);
          stats = res.data;
        } catch {}
        
        return {
          id: agent.id,
          type: 'agent',
          data: { agent, stats },
          position: { x: 0, y: 0 },
        };
      });

      const agentNodes = await Promise.all(nodePromises);
      const newEdges: Edge[] = [];

      visibleAgents.forEach(agent => {
        if (agent.role === 'expert' && orchestrators.length > 0) {
          newEdges.push({
            id: `e-${orchestrators[0].id}-${agent.id}`,
            source: orchestrators[0].id,
            target: agent.id,
            animated: agent.is_active,
            label: agent.routing_keywords?.[0] || '默认跳转',
            labelStyle: { fontSize: 10, fill: '#8c8c8c' },
            markerEnd: { type: MarkerType.ArrowClosed, color: '#d9d9d9' },
            style: { stroke: '#d9d9d9', strokeWidth: 1.5 }
          });
        }
      });

      let toolNodes: Node<ToolNodeData>[] = [];
      if (showTools) {
        const usedToolNames = Array.from(new Set(visibleAgents.flatMap(agent => agent.tools || [])));
        const visibleToolCatalog = tools.filter((tool) => usedToolNames.includes(tool.name));

        toolNodes = visibleToolCatalog
          .map((toolName) => {
            const tool = typeof toolName === 'string' ? tools.find((item) => item.name === toolName) : toolName;
            if (!tool) return null;
            const linkedAgents = visibleAgents.filter((agent) => (agent.tools || []).includes(tool.name)).map((agent) => agent.id);
            return {
              id: `tool:${tool.name}`,
              type: 'tool',
              data: { tool, linkedAgents, isMounted: linkedAgents.length > 0 },
              position: { x: 0, y: 0 },
              draggable: false,
              selectable: true,
            };
          })
          .filter(Boolean) as Node<ToolNodeData>[];

        visibleAgents.forEach((agent) => {
          (agent.tools || []).forEach((toolName) => {
            if (!usedToolNames.includes(toolName)) return;
            newEdges.push({
              id: `tool-edge-${agent.id}-${toolName}`,
              source: agent.id,
              target: `tool:${toolName}`,
              animated: false,
              label: '能力挂载',
              labelStyle: { fontSize: 10, fill: '#60a5fa' },
              markerEnd: { type: MarkerType.ArrowClosed, color: '#93c5fd' },
              style: { stroke: '#93c5fd', strokeWidth: 1.5, strokeDasharray: '5 5' },
              selectable: true,
            });
          });
        });
      }

      const g = new dagre.graphlib.Graph();
      g.setGraph({ rankdir: 'LR', nodesep: 100, ranksep: 180 });
      g.setDefaultEdgeLabel(() => ({}));

      const newNodes = [...agentNodes, ...toolNodes];
      newNodes.forEach(node => g.setNode(node.id, { width: node.type === 'tool' ? 220 : 240, height: node.type === 'tool' ? 120 : 160 }));
      newEdges.forEach(edge => g.setEdge(edge.source, edge.target));

      dagre.layout(g);

      const layoutedNodes: Node<any>[] = newNodes.map(node => {
        const gNode = g.node(node.id);
        return {
          ...node,
          position: {
            x: (gNode.x || 0) - (node.type === 'tool' ? 110 : 120),
            y: (gNode.y || 0) - (node.type === 'tool' ? 60 : 80),
          }
        };
      });

      setNodes(layoutedNodes);
      setEdges(newEdges);
      setSelectedEdgeId(null);
    };

    setupNodes();
  }, [visibleAgents, tools, mode, activeVersionId, setNodes, setEdges, showTools, nodes.length, activeVersion, scopedOrchestrator]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (mode !== 'manual' || !selectedEdgeId) return;
      if (event.key !== 'Delete' && event.key !== 'Backspace') return;
      const edge = edges.find((item) => item.id === selectedEdgeId);
      if (!edge) return;
      event.preventDefault();
      setSelectedEdgeId(edge.id);
      handleDisconnectSelected(edge);
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [mode, selectedEdgeId, edges]);

  // 手动连线处理
  const onConnect = useCallback(async (params: Connection) => {
    if (mode === 'auto') {
      message.warning("当前为自动模式，无法手动修改连线。请先切换至手动模式。");
      return;
    }
    if (!params.source || !params.target) return;

    const sourceAgent = agents.find((agent) => agent.id === params.source);
    const targetAgent = agents.find((agent) => agent.id === params.target);
    const targetToolName = String(params.target).startsWith('tool:') ? String(params.target).replace('tool:', '') : null;

    if (String(params.source).startsWith('tool:')) {
      message.warning('能力节点只能作为被挂载目标，请从专家节点拖向能力节点。');
      return;
    }

    if (targetToolName) {
      if (!sourceAgent) {
        message.warning('只有专家节点可以挂载能力。');
        return;
      }
      const nextTools = Array.from(new Set([...(sourceAgent.tools || []), targetToolName]));
      if (nextTools.length === (sourceAgent.tools || []).length) {
        message.info('该专家已挂载这个能力。');
        return;
      }
      try {
        await axios.put(`/api/v1/agents/${sourceAgent.id}`, { tools: nextTools });
        updateAgentInCanvas(sourceAgent.id, (agent) => ({ ...agent, tools: nextTools }));
        setEdges((current) =>
          addEdge(
            {
              ...params,
              id: `tool-edge-${sourceAgent.id}-${targetToolName}`,
              animated: false,
              label: '能力挂载',
              labelStyle: { fontSize: 10, fill: '#60a5fa' },
              markerEnd: { type: MarkerType.ArrowClosed, color: '#93c5fd' },
              style: { stroke: '#93c5fd', strokeWidth: 1.5, strokeDasharray: '5 5' },
              selectable: true,
            },
            current.filter((edge) => edge.id !== `tool-edge-${sourceAgent.id}-${targetToolName}`),
          ),
        );
        onAgentsUpdated?.();
        message.success('能力已从图上挂载到专家配置');
      } catch (err: any) {
        message.error(err.response?.data?.detail || '挂载能力失败');
      }
      return;
    }

    if (!sourceAgent || !targetAgent) {
      message.warning('当前仅支持专家到专家、专家到能力的连线。');
      return;
    }

    const nextEdgeId = `e-${params.source}-${params.target}`;
    setEdges((eds) =>
      addEdge(
        {
          ...params,
          id: nextEdgeId,
          animated: true,
          label: targetAgent.routing_keywords?.[0] || '默认跳转',
          markerEnd: { type: MarkerType.ArrowClosed, color: '#1890ff' },
          style: { stroke: '#1890ff', strokeWidth: 2 },
        },
        eds.filter((edge) => edge.id !== nextEdgeId),
      ),
    );
    setSelectedEdgeId(nextEdgeId);
    edgeForm.setFieldsValue({
      edge_label: targetAgent.routing_keywords?.[0] || '',
      routing_keywords: targetAgent.routing_keywords || [],
      handoff_strategy: targetAgent.handoff_strategy || 'return',
      tool_name: undefined,
    });
    setEdgeEditorOpen(true);
  }, [mode, agents, setEdges, edgeForm, onAgentsUpdated, updateAgentInCanvas]);

  const handleEdgeClick = useCallback((_: React.MouseEvent, edge: Edge) => {
    setSelectedEdgeId(edge.id);
  }, []);

  const openEdgeEditor = useCallback(() => {
    if (!selectedEdge) return;
    const { targetAgent } = selectedRouteAgents;
    const isToolEdge = String(selectedEdge.id).startsWith('tool-edge-');
    edgeForm.setFieldsValue(
      isToolEdge
        ? {
            tool_name: selectedToolMeta?.name,
          }
        : {
            edge_label: typeof selectedEdge.label === 'string' ? selectedEdge.label : '',
            routing_keywords: targetAgent?.routing_keywords || [],
            handoff_strategy: targetAgent?.handoff_strategy || 'return',
          },
    );
    setEdgeEditorOpen(true);
  }, [selectedEdge, selectedRouteAgents, edgeForm, selectedToolMeta]);

  const handleDisconnectSelected = useCallback(async (edgeArg?: Edge | null) => {
    const edge = edgeArg || selectedEdge;
    if (!edge) return;
    if (mode !== 'manual') {
      message.warning('请先切换到手动编排模式，再断开路由。');
      return;
    }
    try {
      if (String(edge.id).startsWith('tool-edge-')) {
        const sourceAgent = agents.find((agent) => agent.id === edge.source);
        const toolName = String(edge.target).replace('tool:', '');
        if (!sourceAgent) {
          message.error('未找到能力挂载的来源专家');
          return;
        }
        const nextTools = (sourceAgent.tools || []).filter((tool) => tool !== toolName);
        await axios.put(`/api/v1/agents/${sourceAgent.id}`, { tools: nextTools });
        updateAgentInCanvas(sourceAgent.id, (agent) => ({ ...agent, tools: nextTools }));
        setEdges((current) => current.filter((item) => item.id !== edge.id));
        setSelectedEdgeId(null);
        onAgentsUpdated?.();
        message.success('已断开能力挂载，并同步更新专家 tools 配置');
        return;
      }

      const targetAgent = agents.find((agent) => agent.id === edge.target);
      if (targetAgent?.role === 'expert') {
        await axios.put(`/api/v1/agents/${targetAgent.id}`, {
          routing_keywords: [],
        });
        updateAgentInCanvas(targetAgent.id, (agent) => ({ ...agent, routing_keywords: [] }));
        onAgentsUpdated?.();
      }
      setEdges((current) => current.filter((item) => item.id !== edge.id));
      setSelectedEdgeId(null);
      message.success('已断开选中路由，并同步清空该专家的路由关键词');
    } catch (err: any) {
      message.error(err.response?.data?.detail || '断开失败');
    }
  }, [selectedEdge, mode, agents, setEdges, onAgentsUpdated, updateAgentInCanvas]);

  const handleSaveEdgeConfig = useCallback(async () => {
    if (!selectedEdge) return;
    try {
      const values = await edgeForm.validateFields();
      setSavingEdge(true);
      if (String(selectedEdge.id).startsWith('tool-edge-')) {
        const sourceAgent = agents.find((agent) => agent.id === selectedEdge.source);
        if (!sourceAgent) {
          message.error('未找到来源专家');
          return;
        }
        const oldToolName = String(selectedEdge.target).replace('tool:', '');
        const nextToolName = values.tool_name;
        const nextTools = Array.from(
          new Set([...(sourceAgent.tools || []).filter((tool) => tool !== oldToolName), nextToolName]),
        );
        await axios.put(`/api/v1/agents/${sourceAgent.id}`, { tools: nextTools });
        updateAgentInCanvas(sourceAgent.id, (agent) => ({ ...agent, tools: nextTools }));
        setEdges((current) =>
          current.map((edge) =>
            edge.id === selectedEdge.id
              ? {
                  ...edge,
                  id: `tool-edge-${sourceAgent.id}-${nextToolName}`,
                  target: `tool:${nextToolName}`,
                }
              : edge,
          ),
        );
        onAgentsUpdated?.();
        setSelectedEdgeId(`tool-edge-${sourceAgent.id}-${nextToolName}`);
        message.success('能力挂载已同步到专家真实配置');
      } else {
        const { targetAgent } = selectedRouteAgents;
        if (!targetAgent) {
          message.error('未找到目标专家');
          return;
        }
        await axios.put(`/api/v1/agents/${targetAgent.id}`, {
          routing_keywords: values.routing_keywords || [],
          handoff_strategy: values.handoff_strategy,
        });
        updateAgentInCanvas(targetAgent.id, (agent) => ({
          ...agent,
          routing_keywords: values.routing_keywords || [],
          handoff_strategy: values.handoff_strategy,
        }));
        setEdges((current) =>
          current.map((edge) =>
            edge.id === selectedEdge.id
              ? {
                  ...edge,
                  label: values.edge_label || (values.routing_keywords?.[0] || '默认跳转'),
                }
              : edge,
          ),
        );
        onAgentsUpdated?.();
        message.success('路由配置已同步到专家真实配置');
      }
      setEdgeEditorOpen(false);
    } catch (err: any) {
      if (!err?.errorFields) {
        message.error(err.response?.data?.detail || '保存边配置失败');
      }
    } finally {
      setSavingEdge(false);
    }
  }, [selectedEdge, selectedRouteAgents, edgeForm, setEdges, onAgentsUpdated, agents, updateAgentInCanvas]);

  // 保存新版本
  const handleSaveVersion = async () => {
    setLoading(true);
    try {
      const topology = {
        nodes: nodes
          .map((n) => ({
            id: n.id,
            type: n.type,
            position: n.position,
            data: n.type === 'agent'
              ? { agent_id: n.data.agent.id }
              : { tool_name: n.data.tool.name },
          })),
        edges: edges
          .map((e) => ({ id: e.id, source: e.source, target: e.target, label: e.label }))
      };

      await axios.post('/api/v1/graph/versions', {
        name: `Snapshot ${new Date().toLocaleString()}`,
        topology,
        mode,
        is_active: true
      });

      message.success("拓扑版本已成功发布");
      fetchVersions();
    } catch (err) {
      message.error("保存失败");
    } finally {
      setLoading(false);
    }
  };

  const handleActivate = async (vid: number) => {
    try {
      await axios.post(`/api/v1/graph/versions/${vid}/active`);
      message.success("版本已激活");
      fetchVersions();
      setDrawerVisible(false);
    } catch (err) {
      message.error("激活失败");
    }
  };

  return (
    <Card
      style={{ marginBottom: 24, borderRadius: 20, border: '1px solid #f0f0f0', overflow: 'hidden', height: 600, boxShadow: '0 10px 40px rgba(0,0,0,0.04)' }}
      bodyStyle={{ padding: 0, height: '100%', position: 'relative' }}
    >
      <div style={{
        padding: '10px 14px',
        background: 'rgba(255,255,255,0.92)',
        backdropFilter: 'blur(10px)',
        borderBottom: '1px solid #f0f0f0',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: 12,
        flexWrap: 'wrap',
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 10
      }}>
        <Space size={12} wrap>
          <div style={{ background: 'linear-gradient(135deg, #1890ff 0%, #096dd9 100%)', width: 30, height: 30, borderRadius: 10, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
            <NodeIndexOutlined style={{ color: '#fff', fontSize: 18 }} />
          </div>
          <div>
            <Space size={8} wrap>
              <Title level={5} style={{ margin: 0, fontSize: 15 }}>当前智能体应用编排</Title>
              <Badge status={mode === 'auto' ? 'processing' : 'warning'} text={mode === 'auto' ? '自动发现' : '手动编排'} style={{ fontSize: 11 }} />
            </Space>
            <Space size={6} wrap style={{ marginTop: 2 }}>
              <Text type="secondary" style={{ fontSize: 11 }}>
                {scopedOrchestrator ? `主控视角：${scopedOrchestrator.name}` : '当前主控视角'}
              </Text>
            </Space>
          </div>
          <Divider type="vertical" style={{ marginInline: 4 }} />
          <Segmented
            options={[
              { label: '自动发现', value: 'auto', icon: <RocketOutlined /> },
              { label: '手动编排', value: 'manual', icon: <BuildOutlined /> },
            ]}
            value={mode}
            onChange={(val) => setMode(val as any)}
          />
          <Space size={10} wrap>
            <Space size={6}>
              <Switch size="small" checked={showExperts} onChange={setShowExperts} />
              <Text type="secondary" style={{ fontSize: 12 }}>专家</Text>
            </Space>
            <Space size={6}>
              <Switch size="small" checked={showTools} onChange={setShowTools} />
              <Text type="secondary" style={{ fontSize: 12 }}>能力</Text>
            </Space>
          </Space>
        </Space>

        <Space size={8} wrap>
          {mode === 'manual' && (
            <Button size="small" icon={<PlusOutlined />} onClick={() => setPaletteOpen(true)}>
              加入画布
            </Button>
          )}
          {selectedEdge && (
            <Button
              size="small"
              danger
              icon={String(selectedEdge.id).startsWith('tool-edge-') ? <DisconnectOutlined /> : <DeleteOutlined />}
              onClick={() => handleDisconnectSelected()}
            >
              {String(selectedEdge.id).startsWith('tool-edge-') ? '断开能力挂载' : '断开选中连线'}
            </Button>
          )}
          {selectedEdge && (
            <Button size="small" icon={<BuildOutlined />} onClick={openEdgeEditor}>
              {String(selectedEdge.id).startsWith('tool-edge-') ? '编辑能力挂载' : '编辑选中连线'}
            </Button>
          )}
          <Button size="small" icon={<HistoryOutlined />} onClick={() => setDrawerVisible(true)}>版本历史</Button>
          <Button 
            size="small"
            type="primary" 
            icon={<SaveOutlined />} 
            loading={loading}
            onClick={handleSaveVersion}
            disabled={mode === 'auto'}
          >
            发布当前拓扑
          </Button>
        </Space>
      </div>
      
      <div style={{ height: '100%', width: '100%', paddingTop: 62 }}>
        <ReactFlow
          nodes={nodes}
          edges={renderedEdges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onEdgeClick={handleEdgeClick}
          onPaneClick={() => setSelectedEdgeId(null)}
          onNodeClick={(_, node) => node.type === 'agent' && onClickNode && onClickNode(node.data.agent)}
          connectionRadius={28}
          fitView
          style={{ background: '#f8f9fa' }}
        >
          <Background color="#e2e8f0" gap={24} size={1} />
          <Controls style={{ boxShadow: '0 4px 12px rgba(0,0,0,0.1)', borderRadius: 8, overflow: 'hidden' }} />
          <MiniMap style={{ borderRadius: 8, border: '1px solid #e2e8f0' }} />
          
          <Panel position="bottom-center">
            <div style={{ padding: '6px 12px', background: 'rgba(255,255,255,0.92)', borderRadius: 999, boxShadow: '0 4px 15px rgba(0,0,0,0.05)', display: 'flex', gap: 14 }}>
              <div style={{ fontSize: 12, color: '#8c8c8c' }}><InfoCircleOutlined /> 当前只展示已加入该应用画布的节点</div>
              <div style={{ fontSize: 12, color: '#8c8c8c' }}><BuildOutlined /> 手动模式可连线、改边、断边</div>
            </div>
          </Panel>
        </ReactFlow>
      </div>

      <Drawer
        title={<Space><HistoryOutlined /> 拓扑编排历史</Space>}
        placement="right"
        onClose={() => setDrawerVisible(false)}
        open={drawerVisible}
        width={400}
      >
        <List
          dataSource={versions}
          renderItem={(item: any) => (
            <List.Item
              actions={[
                item.is_active ? 
                  <Tag color="success" icon={<CheckCircleOutlined />}>活跃</Tag> : 
                  <Button type="link" size="small" onClick={() => handleActivate(item.id)}>激活</Button>
              ]}
            >
              <List.Item.Meta
                avatar={<ClockCircleOutlined style={{ color: '#bfbfbf', fontSize: 20 }} />}
                title={item.name}
                description={
                  <Space direction="vertical" size={0}>
                    <Text type="secondary" style={{ fontSize: 12 }}>{item.created_at}</Text>
                    <Tag>{item.mode === 'auto' ? '自动模式' : '手动模式'}</Tag>
                  </Space>
                }
              />
            </List.Item>
          )}
          locale={{ emptyText: <Empty description="暂无历史版本" /> }}
        />
      </Drawer>

      <Drawer
        title={<Space><PlusOutlined /> 加入当前画布</Space>}
        placement="right"
        onClose={() => setPaletteOpen(false)}
        open={paletteOpen}
        width={360}
      >
        <Space direction="vertical" size={18} style={{ width: '100%' }}>
          <Card size="small" style={{ borderRadius: 16 }}>
            <Space direction="vertical" size={4}>
              <Text strong>当前策略</Text>
              <Text type="secondary" style={{ fontSize: 12 }}>
                默认只显示已经在当前智能体编排中的专家与能力，避免把整个系统资产全部塞进画布。
              </Text>
            </Space>
          </Card>

          <div>
            <Text strong style={{ display: 'block', marginBottom: 10 }}>未加入的专家</Text>
            <List
              size="small"
              dataSource={availableExperts}
              locale={{ emptyText: '没有可加入的专家' }}
              renderItem={(agent) => (
                <List.Item
                  actions={[
                    <Button key={agent.id} size="small" type="link" onClick={() => addAgentToCanvas(agent.id)}>
                      加入画布
                    </Button>,
                  ]}
                >
                  <List.Item.Meta
                    title={agent.name}
                    description={agent.description || '暂无描述'}
                  />
                </List.Item>
              )}
            />
          </div>

          <div>
            <Text strong style={{ display: 'block', marginBottom: 10 }}>未加入的能力</Text>
            <List
              size="small"
              dataSource={availableTools}
              locale={{ emptyText: '没有可加入的能力' }}
              renderItem={(tool) => (
                <List.Item
                  actions={[
                    <Button key={tool.name} size="small" type="link" onClick={() => addToolToCanvas(tool.name)}>
                      加入画布
                    </Button>,
                  ]}
                >
                  <List.Item.Meta
                    title={tool.label}
                    description={tool.description || tool.name}
                  />
                </List.Item>
              )}
            />
          </div>
        </Space>
      </Drawer>

      <Drawer
        title={<Space><BuildOutlined /> {selectedEdge && String(selectedEdge.id).startsWith('tool-edge-') ? '编辑能力挂载' : '编辑路由连线'}</Space>}
        placement="right"
        onClose={() => setEdgeEditorOpen(false)}
        open={edgeEditorOpen}
        width={420}
        extra={
          <Button type="primary" loading={savingEdge} onClick={handleSaveEdgeConfig}>
            保存联动配置
          </Button>
        }
      >
        {selectedEdge ? (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Card size="small" style={{ borderRadius: 16 }}>
              <Space direction="vertical" size={4}>
                <Text strong>{selectedRouteAgents.sourceAgent?.name || selectedEdge.source} {'→'} {selectedRouteAgents.targetAgent?.name || selectedEdge.target}</Text>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {String(selectedEdge.id).startsWith('tool-edge-')
                    ? '这里编辑的是能力挂载边，保存时会同步更新来源专家的 tools 配置。'
                    : '这里编辑的是路由连线，同时会同步更新目标专家的真实配置。'}
                </Text>
              </Space>
            </Card>
            <Form form={edgeForm} layout="vertical">
              {String(selectedEdge.id).startsWith('tool-edge-') ? (
                <Form.Item
                  name="tool_name"
                  label="挂载能力"
                  extra="可直接把当前连线切换到另一个已注册能力。"
                  rules={[{ required: true, message: '请选择一个能力' }]}
                >
                  <Select
                    showSearch
                    optionFilterProp="label"
                    options={tools.map((tool) => ({
                      label: `${tool.label} (${tool.category})`,
                      value: tool.name,
                    }))}
                  />
                </Form.Item>
              ) : (
                <>
                  <Form.Item
                    name="edge_label"
                    label="连线标签"
                    extra="用于画布上的短标签展示，建议写成该专家的主命中意图。"
                  >
                    <Input placeholder="例如：代码问题 / 联网研究 / 翻译请求" />
                  </Form.Item>
                  <Form.Item
                    name="routing_keywords"
                    label="命中关键词"
                    extra="这些关键词会直接写回专家的 routing_keywords。"
                    rules={[{ required: true, message: '请至少填写一个命中关键词' }]}
                  >
                    <Select
                      mode="tags"
                      tokenSeparators={[',']}
                      placeholder="输入多个关键词后回车"
                    />
                  </Form.Item>
                  <Form.Item
                    name="handoff_strategy"
                    label="接管策略"
                    extra="会同步写回目标专家的 handoff_strategy。"
                    rules={[{ required: true, message: '请选择接管策略' }]}
                  >
                    <Select
                      options={[
                        { label: '执行后归还主控', value: 'return' },
                        { label: '执行后结束回合', value: 'end' },
                      ]}
                    />
                  </Form.Item>
                </>
              )}
            </Form>
          </Space>
        ) : (
          <Empty description="请先选中一条路由边" />
        )}
      </Drawer>

      <style>{`
        .agent-node-card:hover {
          transform: translateY(-8px);
          box-shadow: 0 20px 40px rgba(0,0,0,0.12) !important;
        }
        .tool-node-card:hover {
          transform: translateY(-4px);
        }
        .react-flow__handle:hover {
          transform: scale(1.15);
          background: #1890ff !important;
        }
        .react-flow__handle {
          transition: transform 0.18s ease, box-shadow 0.18s ease;
        }
        .react-flow__edge-path {
          stroke-dasharray: 6;
          animation: flow-dash 1s linear infinite;
        }
        .react-flow__edge.selected .react-flow__edge-path {
          stroke: #2563eb !important;
          stroke-width: 3px !important;
          filter: drop-shadow(0 0 6px rgba(37,99,235,0.25));
        }
        @keyframes flow-dash {
          from { stroke-dashoffset: 12; }
          to { stroke-dashoffset: 0; }
        }
      `}</style>
    </Card>
  );
};

export default AgentTopologyEditor;
