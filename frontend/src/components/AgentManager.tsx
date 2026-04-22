import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Avatar,
  Badge,
  Button,
  Card,
  Checkbox,
  Col,
  Collapse,
  Drawer,
  Divider,
  Empty,
  Form,
  Input,
  Modal,
  Row,
  Segmented,
  Select,
  Space,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import {
  CheckCircleOutlined,
  CrownOutlined,
  DeleteOutlined,
  ExperimentOutlined,
  PlusOutlined,
  PoweroffOutlined,
  RadarChartOutlined,
  ReloadOutlined,
  RobotOutlined,
  SearchOutlined,
  SettingOutlined,
  ThunderboltOutlined,
  EyeOutlined,
} from '@ant-design/icons';
import axios from 'axios';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import type { Agent } from './ChatView';
import AgentTopologyEditor from './AgentTopologyEditor';

dayjs.extend(relativeTime);

const { Title, Text, Paragraph } = Typography;

interface ActionMeta {
  name: string;
  label: string;
  description: string;
  category: string;
}

interface AgentDashboardItem {
  id: string;
  name: string;
  role: 'orchestrator' | 'expert';
  is_active: boolean;
  is_public: boolean;
  tools_count: number;
  routing_keywords_count: number;
  runs: number;
  success_rate: number;
  avg_duration_ms: number;
  error_count: number;
  last_run_at?: string | null;
}

interface AgentDashboardSummary {
  total: number;
  active: number;
  orchestrators: number;
  experts: number;
  public_count: number;
}

interface AgentDashboardResponse {
  summary: AgentDashboardSummary;
  agents: AgentDashboardItem[];
}

interface GraphExecutionItem {
  request_id?: string;
  node_name: string;
  status: string;
  error_message?: string | null;
  created_at?: string;
}

interface RouteInsight {
  latestRouteNodes: string[];
  latestRequestId: string;
  failureNode?: string;
  failureMessage?: string;
}

interface ValidationResult {
  ok: boolean;
  normalized_payload: Record<string, any>;
  warnings: string[];
}

interface AgentManagerProps {
  agents: Agent[];
  setAgents: React.Dispatch<React.SetStateAction<Agent[]>>;
  modelConfigs: any[];
  msgApi: any;
  onRefresh: () => void;
}

const ROLE_STYLES = {
  orchestrator: {
    color: '#faad14',
    bg: 'linear-gradient(135deg, #fff7e6 0%, #ffffff 100%)',
    border: '#ffd591',
    icon: <CrownOutlined />,
    label: '主控',
  },
  expert: {
    color: '#722ed1',
    bg: 'linear-gradient(135deg, #f9f0ff 0%, #ffffff 100%)',
    border: '#d3adf7',
    icon: <RobotOutlined />,
    label: '专家',
  },
};

const ROLE_CHANGE_HINTS = {
  orchestrator: '改成主控后，它会退出专家协作目录，其他主控不能再通过专家移交直接调用它，但可作为子应用被根主控委托。',
  expert: '改成专家后，它会重新进入专家协作目录，可被主控按路由关键词命中。',
} as const;

const AgentManager: React.FC<AgentManagerProps> = ({ agents, setAgents, modelConfigs, msgApi, onRefresh }) => {
  const [form] = Form.useForm();
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<'all' | 'orchestrator' | 'expert'>('all');
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [registeredTools, setRegisteredTools] = useState<ActionMeta[]>([]);
  const [dashboard, setDashboard] = useState<AgentDashboardResponse | null>(null);
  const [loadingDashboard, setLoadingDashboard] = useState(true);
  const [detailOpen, setDetailOpen] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingAgent, setEditingAgent] = useState<Agent | null>(null);
  const [topologyScopeId, setTopologyScopeId] = useState<string | null>(null);
  const [pageMode, setPageMode] = useState<'topology' | 'operations'>('topology');
  const [operationsView, setOperationsView] = useState<'cards' | 'table'>('cards');
  const [selectedOpsRowKeys, setSelectedOpsRowKeys] = useState<React.Key[]>([]);
  const [validating, setValidating] = useState(false);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [testQuery, setTestQuery] = useState('请用一句话介绍你的职责和适合处理的问题。');
  const [testInteractionMode, setTestInteractionMode] = useState<'chat' | 'workflow' | 'builder' | 'analysis'>('chat');
  const [testResult, setTestResult] = useState<string>('');
  const [routeInsight, setRouteInsight] = useState<RouteInsight | null>(null);

  const notify = {
    success: (content: string) => (msgApi?.success ? msgApi.success(content) : message.success(content)),
    error: (content: string) => (msgApi?.error ? msgApi.error(content) : message.error(content)),
  };
  const editorValues = Form.useWatch([], form) || {};

  const editorConflictWarnings = useMemo(() => {
    const warnings: string[] = [];
    const role = (editorValues?.role || editingAgent?.role || 'expert') as 'orchestrator' | 'expert';
    const tools = Array.isArray(editorValues?.tools) ? editorValues.tools : [];
    const keywords = Array.isArray(editorValues?.routing_keywords) ? editorValues.routing_keywords : [];

    if (editingAgent && editingAgent.role !== role) {
      warnings.push(`角色从 ${editingAgent.role === 'orchestrator' ? '主控' : '专家'} 切换为 ${role === 'orchestrator' ? '主控' : '专家'}，会影响协作链路。`);
    }
    if (role === 'expert' && keywords.length === 0) {
      warnings.push('专家未配置路由关键词，主控自动分发时命中率会下降。');
    }
    if (role === 'orchestrator' && keywords.length > 0) {
      warnings.push('主控的路由关键词不会用于专家协作目录，可按需清理。');
    }
    if (tools.length === 0) {
      warnings.push('当前未配置任何工具，只能进行纯文本推理。');
    }
    return warnings;
  }, [editorValues, editingAgent]);

  useEffect(() => {
    fetchTools();
    fetchDashboard();
    fetchRouteInsight();
  }, []);

  useEffect(() => {
    if (!selectedAgentId && agents.length > 0) {
      const preferred = agents.find((item) => item.role === 'orchestrator') || agents[0];
      setSelectedAgentId(preferred.id);
    }
  }, [agents, selectedAgentId]);

  useEffect(() => {
    if (!topologyScopeId) {
      const preferred = agents.find((item) => item.role === 'orchestrator');
      if (preferred) setTopologyScopeId(preferred.id);
    }
  }, [agents, topologyScopeId]);

  const fetchTools = async () => {
    try {
      const res = await axios.get('/api/v1/registry/actions');
      setRegisteredTools(res.data || []);
    } catch {
      notify.error('获取工具列表失败');
    }
  };

  const fetchDashboard = async () => {
    setLoadingDashboard(true);
    try {
      const res = await axios.get('/api/v1/agents/dashboard/summary');
      setDashboard(res.data);
    } catch {
      notify.error('获取专家概览失败');
    } finally {
      setLoadingDashboard(false);
    }
  };

  const fetchRouteInsight = async () => {
    try {
      const res = await axios.get('/api/v1/audit/dashboard?days=3');
      const recent: GraphExecutionItem[] = res.data?.recent_executions || [];
      if (!recent.length) {
        setRouteInsight(null);
        return;
      }
      const latestReq = recent[0]?.request_id;
      const latestReqExecutions = recent
        .filter((item) => item.request_id === latestReq)
        .slice()
        .reverse();
      // 只展示“最近一次请求”里的异常，避免历史旧错长期驻留
      const latestFailure = latestReqExecutions.find((item) => item.status === 'error');
      setRouteInsight({
        latestRequestId: latestReq || 'N/A',
        latestRouteNodes: latestReqExecutions.map((item) => item.node_name).filter(Boolean),
        failureNode: latestFailure?.node_name,
        failureMessage: latestFailure?.error_message || undefined,
      });
    } catch {
      setRouteInsight(null);
    }
  };

  const mergedAgents = useMemo(() => {
    const metricsMap = new Map((dashboard?.agents || []).map((item) => [item.id, item]));
    return agents.map((agent) => ({
      ...agent,
      metrics: metricsMap.get(agent.id),
    }));
  }, [agents, dashboard]);

  const filteredAgents = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return mergedAgents.filter((agent) => {
      if (roleFilter !== 'all' && agent.role !== roleFilter) return false;
      if (!keyword) return true;
      return [agent.name, agent.description, ...(agent.routing_keywords || []), ...(agent.tools || [])]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(keyword));
    });
  }, [mergedAgents, search, roleFilter]);

  const selectedAgent = mergedAgents.find((item) => item.id === selectedAgentId) || null;
  const selectedOpsAgents = useMemo(
    () => filteredAgents.filter((agent) => selectedOpsRowKeys.includes(agent.id)),
    [filteredAgents, selectedOpsRowKeys],
  );

  const sanitizeTools = (input?: string[]) => {
    const allowed = new Set(registeredTools.map((tool) => tool.name));
    return (input || []).filter((tool) => allowed.has(tool));
  };

  const openEditor = (agent?: Agent) => {
    setDetailOpen(false);
    setEditingAgent(agent || null);
    setValidation(null);
    setTestResult('');
    if (agent) {
      form.setFieldsValue({
        name: agent.name,
        description: agent.description,
        model_config_id: agent.model_config_id ? Number(agent.model_config_id) : undefined,
        system_prompt: agent.system_prompt,
        tools: sanitizeTools(agent.tools || []),
        role: agent.role || 'expert',
        routing_keywords: agent.routing_keywords || [],
        handoff_strategy: agent.handoff_strategy || 'return',
        is_public: agent.is_public,
        is_active: agent.is_active,
      });
    } else {
      form.resetFields();
      form.setFieldsValue({
        role: 'expert',
        handoff_strategy: 'return',
        tools: [],
        routing_keywords: [],
        is_public: false,
        is_active: true,
      });
    }
    setEditorOpen(true);
  };

  const openDetail = (agentId: string) => {
    setEditorOpen(false);
    setSelectedAgentId(agentId);
    setDetailOpen(true);
  };

  useEffect(() => {
    const keySet = new Set(filteredAgents.map((agent) => agent.id));
    setSelectedOpsRowKeys((prev) => prev.filter((key) => keySet.has(String(key))));
  }, [filteredAgents]);

  const validateConfig = async () => {
    try {
      const values = await form.validateFields();
      setValidating(true);
      const res = await axios.post('/api/v1/agents/validate', {
        ...values,
        model_config_id: Number(values.model_config_id),
      });
      setValidation(res.data);
      notify.success('专家配置校验通过');
      return res.data as ValidationResult;
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      if (detail) notify.error(detail);
      else if (!err?.errorFields) notify.error('配置校验失败');
      return null;
    } finally {
      setValidating(false);
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const checked = await validateConfig();
      if (!checked) return;

      const payload = {
        ...values,
        model_config_id: Number(values.model_config_id),
        tools: sanitizeTools(values.tools || []),
      };

      if (editingAgent) {
        await axios.put(`/api/v1/agents/${editingAgent.id}`, payload);
        notify.success(`${values.name} 已更新`);
      } else {
        await axios.post('/api/v1/agents/', payload);
        notify.success(`${values.name} 已创建`);
      }
      setEditorOpen(false);
      onRefresh();
      fetchDashboard();
      fetchRouteInsight();
    } catch (err: any) {
      const detail = err.response?.data?.detail || '操作失败';
      if (!err?.errorFields) notify.error(detail);
    }
  };

  const handleDelete = async (agent: Agent) => {
    Modal.confirm({
      title: `确认删除 ${agent.name}？`,
      content: '此操作不可恢复。',
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await axios.delete(`/api/v1/agents/${agent.id}`);
          notify.success(`${agent.name} 已删除`);
          if (selectedAgentId === agent.id) setSelectedAgentId(null);
          onRefresh();
          fetchDashboard();
          fetchRouteInsight();
        } catch {
          notify.error('删除失败');
        }
      },
    });
  };

  const toggleStatus = async (agent: Agent, checked: boolean) => {
    try {
      await axios.put(`/api/v1/agents/${agent.id}`, { is_active: checked });
      setAgents((prev) => prev.map((item) => (item.id === agent.id ? { ...item, is_active: checked } : item)));
      notify.success(`${agent.name} 已${checked ? '上线' : '下线'}`);
      fetchDashboard();
      fetchRouteInsight();
    } catch (err: any) {
      notify.error(err.response?.data?.detail || '状态更新失败');
    }
  };

  const runAgentTest = async (agent: Agent) => {
    try {
      setTesting(true);
      const res = await axios.post(`/api/v1/agents/${agent.id}/test`, {
        query: testQuery,
        interaction_mode: testInteractionMode,
        enable_canvas: false,
        enable_swarm: agent.role === 'orchestrator',
        enable_memory: false,
      });
      setTestResult(res.data.content || '');
      notify.success('试跑完成');
    } catch (err: any) {
      notify.error(err.response?.data?.detail || '试跑失败');
    } finally {
      setTesting(false);
    }
  };

  const modelOptions = useMemo(() => {
    const options: Array<{ label: string; value: number; group: string }> = [];
    const typeMap: Record<string, string> = { chat: '通用', vision: '视觉', reasoning: '推理' };
    modelConfigs.forEach((provider) => {
      (provider.models || []).forEach((model: any) => {
        let type = model.model_type === 'llm' ? 'chat' : model.model_type;
        const name = String(model.model_name || '').toLowerCase();
        if (name.includes('vl') || name.includes('vision')) type = 'vision';
        else if (name.includes('-r1') || name.includes('reasoner')) type = 'reasoning';
        options.push({
          label: `${model.model_name} (${provider.display_name})`,
          value: model.id,
          group: typeMap[type] || '其他',
        });
      });
    });
    return options;
  }, [modelConfigs]);

  const orchestratorApps = useMemo(
    () =>
      mergedAgents
        .filter((agent) => agent.role === 'orchestrator')
        .map((agent) => ({
          ...agent,
          attachedExpertCount: mergedAgents.filter((item) => item.role === 'expert' && item.is_active).length,
          mountedToolCount: agent.tools?.length || 0,
        })),
    [mergedAgents],
  );

  const renderAgentActions = (agent: Agent) => (
    <Space wrap>
      <Button size="small" onClick={(e) => { e.stopPropagation(); openDetail(agent.id); }}>
        查看详情
      </Button>
      <Button size="small" icon={<SettingOutlined />} onClick={(e) => { e.stopPropagation(); openEditor(agent); }}>
        编辑
      </Button>
      <Button size="small" icon={<PoweroffOutlined />} onClick={(e) => { e.stopPropagation(); toggleStatus(agent, !agent.is_active); }}>
        {agent.is_active ? '下线' : '上线'}
      </Button>
      <Button size="small" danger icon={<DeleteOutlined />} onClick={(e) => { e.stopPropagation(); handleDelete(agent); }}>
        删除
      </Button>
    </Space>
  );

  const renderTableActions = (agent: Agent) => (
    <Space size={6} wrap={false}>
      <Tooltip title="查看详情">
        <Button size="small" icon={<EyeOutlined />} aria-label="查看详情" onClick={() => openDetail(agent.id)} />
      </Tooltip>
      <Tooltip title="编辑配置">
        <Button size="small" icon={<SettingOutlined />} aria-label="编辑配置" onClick={() => openEditor(agent)} />
      </Tooltip>
      <Tooltip title={agent.is_active ? '下线专家' : '上线专家'}>
        <Button
          size="small"
          icon={<PoweroffOutlined />}
          aria-label={agent.is_active ? '下线专家' : '上线专家'}
          onClick={() => toggleStatus(agent, !agent.is_active)}
        />
      </Tooltip>
      <Tooltip title="删除专家">
        <Button size="small" danger icon={<DeleteOutlined />} aria-label="删除专家" onClick={() => handleDelete(agent)} />
      </Tooltip>
    </Space>
  );

  const handleBatchToggleAgents = async (nextActive: boolean) => {
    if (selectedOpsAgents.length === 0) {
      notify.error('请先选择至少一个专家');
      return;
    }
    try {
      await Promise.all(
        selectedOpsAgents.map((agent) =>
          agent.is_active === nextActive ? Promise.resolve() : axios.put(`/api/v1/agents/${agent.id}`, { is_active: nextActive }),
        ),
      );
      notify.success(nextActive ? '已批量上线所选专家' : '已批量下线所选专家');
      setSelectedOpsRowKeys([]);
      onRefresh();
      fetchDashboard();
      fetchRouteInsight();
    } catch (err: any) {
      notify.error(err.response?.data?.detail || '批量更新状态失败');
    }
  };

  const handleBatchDeleteAgents = async () => {
    if (selectedOpsAgents.length === 0) {
      notify.error('请先选择至少一个专家');
      return;
    }
    Modal.confirm({
      title: `确认删除 ${selectedOpsAgents.length} 个专家？`,
      content: '此操作不可恢复。',
      okText: '确认删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await Promise.all(selectedOpsAgents.map((agent) => axios.delete(`/api/v1/agents/${agent.id}`)));
          notify.success('已批量删除所选专家');
          setSelectedOpsRowKeys([]);
      onRefresh();
      fetchDashboard();
      fetchRouteInsight();
        } catch {
          notify.error('批量删除失败');
        }
      },
    });
  };

  return (
    <div style={{ padding: 18, background: '#edf2f7', minHeight: '100%', overflow: 'auto' }}>
      <div style={{ maxWidth: 1560, margin: '0 auto' }}>
        <Card
          bordered={false}
          style={{
            marginBottom: 12,
            borderRadius: 14,
            border: '1px solid #dbeafe',
            background: '#f8fbff',
            boxShadow: '0 8px 20px rgba(37,99,235,0.06)',
          }}
          bodyStyle={{ padding: '10px 14px' }}
        >
          <Row gutter={[10, 10]} align="middle">
            <Col xs={24} xl={10}>
              <Space direction="vertical" size={2}>
                <Space wrap size={6}>
                  <Tag color="blue" style={{ borderRadius: 999, margin: 0 }}>Swarm Control</Tag>
                  <Text type="secondary" style={{ fontSize: 12 }}>专家治理 + 路由编排 + 健康诊断 + 快速试跑</Text>
                </Space>
                <Title level={4} style={{ margin: 0, lineHeight: 1.2 }}>专家集群管理中心</Title>
              </Space>
            </Col>
            <Col xs={24} xl={9}>
              <Space wrap size={14}>
                <Space size={6}>
                  <ThunderboltOutlined style={{ color: '#1d4ed8' }} />
                  <Text type="secondary">活跃专家</Text>
                  <Text strong style={{ fontSize: 18 }}>{dashboard?.summary.active || 0}</Text>
                </Space>
                <Divider type="vertical" />
                <Space size={6}>
                  <RadarChartOutlined style={{ color: '#0f172a' }} />
                  <Text type="secondary">主控 / 专家</Text>
                  <Text strong style={{ fontSize: 18 }}>
                    {`${dashboard?.summary.orchestrators || 0} / ${dashboard?.summary.experts || 0}`}
                  </Text>
                </Space>
              </Space>
            </Col>
            <Col xs={24} xl={5} style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <Space wrap>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => openEditor()} size="middle">
                  新增专家
                </Button>
                <Button icon={<ReloadOutlined />} onClick={() => { onRefresh(); fetchDashboard(); }} size="middle">
                  刷新
                </Button>
              </Space>
            </Col>
          </Row>
        </Card>

        <Card bordered={false} style={{ borderRadius: 14, marginBottom: 12 }} bodyStyle={{ padding: 12 }}>
          <Space wrap style={{ width: '100%', justifyContent: 'space-between' }}>
            <Segmented
              value={pageMode}
              onChange={(value) => setPageMode(value as 'topology' | 'operations')}
              options={[
                { label: '编排视图', value: 'topology' },
                { label: '专家运营视图', value: 'operations' },
              ]}
            />
            <Text type="secondary">
              {pageMode === 'topology' ? '聚焦主控应用编排与连线配置' : '聚焦专家批量管理与状态运营'}
            </Text>
          </Space>
        </Card>

        {pageMode === 'topology' && (
        <Card bordered={false} style={{ borderRadius: 24, marginBottom: 18 }} bodyStyle={{ padding: 18 }}>
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <div>
                <Title level={4} style={{ margin: 0 }}>智能体应用编排</Title>
                <Text type="secondary">按主控视角查看当前应用的专家与能力，不再把整个系统资产默认铺进一张图。</Text>
              </div>
              <Space wrap>
                <Select
                  value={topologyScopeId || undefined}
                  style={{ minWidth: 240 }}
                  placeholder="选择主控应用"
                  onChange={(value) => setTopologyScopeId(value)}
                  options={agents
                    .filter((agent) => agent.role === 'orchestrator')
                    .map((agent) => ({ label: agent.name, value: agent.id }))}
                />
                <Button onClick={() => selectedAgent && openEditor(selectedAgent)} disabled={!selectedAgent}>
                  编辑当前选中专家
                </Button>
              </Space>
            </div>
            {orchestratorApps.length > 0 && (
              <Collapse
                defaultActiveKey={[]}
                items={[
                  {
                    key: 'orchestrator-apps',
                    label: `主控应用清单（${orchestratorApps.length}）`,
                    children: (
                      <Row gutter={[12, 12]}>
                        {orchestratorApps.map((app) => (
                          <Col key={app.id} xs={24} md={12} xl={8}>
                            <Card
                              hoverable
                              onClick={() => setTopologyScopeId(app.id)}
                              style={{
                                borderRadius: 14,
                                border: `1px solid ${topologyScopeId === app.id ? '#2563eb' : '#dbeafe'}`,
                                background: topologyScopeId === app.id ? 'linear-gradient(135deg, #eff6ff 0%, #ffffff 100%)' : '#fff',
                                boxShadow: topologyScopeId === app.id ? '0 10px 22px rgba(37,99,235,0.12)' : '0 6px 14px rgba(15,23,42,0.04)',
                              }}
                              bodyStyle={{ padding: 12 }}
                            >
                              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                                <Space wrap size={8}>
                                  <Avatar size={34} icon={<CrownOutlined />} style={{ background: '#faad14' }} />
                                  <div>
                                    <Text strong>{app.name}</Text>
                                    <div>
                                      <Tag color="gold" style={{ marginTop: 4, marginBottom: 0 }}>主控应用</Tag>
                                    </div>
                                  </div>
                                </Space>
                                <Text type="secondary" ellipsis>{app.description || '当前主控应用的编排入口。'}</Text>
                                <Space size={12}>
                                  <Text type="secondary">在线专家 {app.attachedExpertCount}</Text>
                                  <Text type="secondary">已装能力 {app.mountedToolCount}</Text>
                                </Space>
                              </Space>
                            </Card>
                          </Col>
                        ))}
                      </Row>
                    ),
                  },
                ]}
              />
            )}
            <Card size="small" style={{ borderRadius: 14, background: '#f8fafc' }}>
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                <Text strong>编排可观测性</Text>
                {routeInsight?.latestRouteNodes?.length ? (
                  <Space wrap size={6}>
                    <Text type="secondary" style={{ fontSize: 12 }}>最近路由:</Text>
                    {routeInsight.latestRouteNodes.map((node, idx) => (
                      <Tag key={`${node}-${idx}`} color="processing" style={{ margin: 0 }}>{node}</Tag>
                    ))}
                  </Space>
                ) : (
                  <Text type="secondary">暂无最近路由记录</Text>
                )}
                {routeInsight?.failureNode ? (
                  <Alert
                    type="warning"
                    showIcon
                    message={`最近异常节点：${routeInsight.failureNode}`}
                    description={routeInsight.failureMessage || '请查看审计日志定位具体报错。'}
                  />
                ) : (
                  <Alert type="success" showIcon message="最近未检测到节点级故障" />
                )}
              </Space>
            </Card>
            <div style={{ borderRadius: 18, overflow: 'hidden' }}>
              <AgentTopologyEditor
                agents={agents}
                scopeAgentId={topologyScopeId}
                onClickNode={(agent) => openDetail(agent.id)}
                onAgentsUpdated={() => {
      onRefresh();
      fetchDashboard();
      fetchRouteInsight();
                }}
              />
            </div>
          </Space>
        </Card>
        )}

        {pageMode === 'operations' && (
        <Card bordered={false} style={{ borderRadius: 24, marginBottom: 18 }} bodyStyle={{ padding: 18 }}>
          <Space wrap style={{ width: '100%', justifyContent: 'space-between' }}>
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder="搜索专家名、关键词、工具"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ width: 320 }}
            />
            <Space wrap>
              <Segmented
                value={roleFilter}
                onChange={(value) => setRoleFilter(value as 'all' | 'orchestrator' | 'expert')}
                options={[
                  { label: '全部', value: 'all' },
                  { label: '主控', value: 'orchestrator' },
                  { label: '专家', value: 'expert' },
                ]}
              />
              <Segmented
                value={operationsView}
                onChange={(value) => setOperationsView(value as 'cards' | 'table')}
                options={[
                  { label: '卡片', value: 'cards' },
                  { label: '表格', value: 'table' },
                ]}
              />
              <Text type="secondary">{operationsView === 'table' ? '支持批量操作与高密度管理' : '点击专家卡片查看详情与试跑'}</Text>
            </Space>
          </Space>
        </Card>
        )}

        {pageMode === 'operations' && (
        <Card bordered={false} style={{ borderRadius: 24 }}>
          {loadingDashboard ? (
            <div style={{ padding: 60, textAlign: 'center' }}>
              <Text type="secondary">正在加载专家状态...</Text>
            </div>
          ) : filteredAgents.length === 0 ? (
            <Empty description="没有匹配到专家" />
          ) : operationsView === 'table' ? (
            <Space direction="vertical" size={0} style={{ width: '100%' }}>
              <div
                style={{
                  padding: '10px 12px',
                  borderBottom: '1px solid #eef2f7',
                  background: 'linear-gradient(180deg, #f8fbff 0%, #ffffff 100%)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: 10,
                  flexWrap: 'wrap',
                }}
              >
                <Space size={10} wrap>
                  <Tag color="blue" style={{ margin: 0 }}>
                    已选 {selectedOpsRowKeys.length}
                  </Tag>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    支持批量上下线和批量删除
                  </Text>
                </Space>
                <Space wrap>
                  <Button size="small" icon={<PoweroffOutlined />} disabled={selectedOpsAgents.length === 0} onClick={() => handleBatchToggleAgents(true)}>
                    批量上线
                  </Button>
                  <Button size="small" icon={<PoweroffOutlined />} disabled={selectedOpsAgents.length === 0} onClick={() => handleBatchToggleAgents(false)}>
                    批量下线
                  </Button>
                  <Button size="small" danger icon={<DeleteOutlined />} disabled={selectedOpsAgents.length === 0} onClick={handleBatchDeleteAgents}>
                    批量删除
                  </Button>
                </Space>
              </div>
              <Table
                rowKey="id"
                size="middle"
                dataSource={filteredAgents}
                rowSelection={{
                  selectedRowKeys: selectedOpsRowKeys,
                  onChange: (keys) => setSelectedOpsRowKeys(keys),
                  preserveSelectedRowKeys: true,
                }}
                pagination={{ pageSize: 10, showSizeChanger: false }}
                scroll={{ x: 1020 }}
                columns={[
                  {
                    title: '专家',
                    key: 'agent',
                    width: 420,
                    render: (_, agent: any) => (
                      <Space align="start" size={10}>
                        <Avatar
                          size={34}
                          icon={ROLE_STYLES[(agent.role as 'orchestrator' | 'expert')].icon}
                          style={{ background: ROLE_STYLES[(agent.role as 'orchestrator' | 'expert')].color }}
                        />
                        <Space direction="vertical" size={1}>
                          <Space size={6}>
                            <Text strong>{agent.name}</Text>
                            <Tag color={agent.role === 'orchestrator' ? 'gold' : 'purple'} style={{ margin: 0 }}>
                              {ROLE_STYLES[(agent.role as 'orchestrator' | 'expert')].label}
                            </Tag>
                          </Space>
                          <Text type="secondary" ellipsis style={{ maxWidth: 420 }}>
                            {agent.description || '暂无角色描述'}
                          </Text>
                        </Space>
                      </Space>
                    ),
                  },
                  {
                    title: '状态',
                    dataIndex: 'is_active',
                    width: 96,
                    render: (isActive: boolean) => (
                      <Tag color={isActive ? 'success' : 'default'} style={{ borderRadius: 999, margin: 0 }}>
                        {isActive ? '在线' : '离线'}
                      </Tag>
                    ),
                  },
                  {
                    title: '工具',
                    key: 'tools',
                    width: 80,
                    align: 'center',
                    render: (_, agent: any) => agent.metrics?.tools_count ?? agent.tools?.length ?? 0,
                  },
                  {
                    title: '成功率',
                    key: 'success_rate',
                    width: 90,
                    align: 'center',
                    render: (_, agent: any) => `${(((agent.metrics?.success_rate ?? 0) || 0) * 100).toFixed(0)}%`,
                  },
                  {
                    title: '最近运行',
                    key: 'last_run',
                    width: 120,
                    render: (_, agent: any) => (agent.metrics?.last_run_at ? dayjs(agent.metrics.last_run_at).fromNow() : '暂无'),
                  },
                  {
                    title: '操作',
                    key: 'actions',
                    width: 170,
                    render: (_, agent: any) => renderTableActions(agent),
                  },
                ]}
              />
            </Space>
          ) : (
            <Row gutter={[16, 16]}>
              {filteredAgents.map((agent) => {
                const style = ROLE_STYLES[agent.role];
                const isSelected = selectedAgentId === agent.id;
                const metrics = agent.metrics;
                return (
                  <Col key={agent.id} xs={24} md={12} xl={8}>
                    <Card
                      hoverable
                      onClick={() => openDetail(agent.id)}
                      style={{
                        borderRadius: 22,
                        cursor: 'pointer',
                        background: style.bg,
                        border: `1px solid ${isSelected ? style.color : style.border}`,
                        boxShadow: isSelected ? `0 18px 40px rgba(37,99,235,0.12)` : '0 10px 28px rgba(15,23,42,0.05)',
                        height: '100%',
                      }}
                      bodyStyle={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 14, height: '100%' }}
                    >
                      <div style={{ display: 'flex', gap: 14 }}>
                        <Badge status={agent.is_active ? 'success' : 'default'}>
                          <Avatar size={52} icon={style.icon} style={{ background: style.color }} />
                        </Badge>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <Space wrap size={8}>
                            <Text strong style={{ fontSize: 18 }}>{agent.name}</Text>
                            <Tag color={agent.role === 'orchestrator' ? 'gold' : 'purple'}>{style.label}</Tag>
                            {agent.is_public && <Tag>公开</Tag>}
                          </Space>
                          <Paragraph ellipsis={{ rows: 2 }} style={{ marginTop: 8, marginBottom: 0, color: '#475569', minHeight: 52 }}>
                            {agent.description || '暂无角色描述'}
                          </Paragraph>
                        </div>
                      </div>

                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 10 }}>
                        <div style={{ background: 'rgba(255,255,255,0.75)', borderRadius: 14, padding: 12 }}>
                          <Text type="secondary" style={{ fontSize: 12 }}>工具</Text>
                          <div><Text strong>{metrics?.tools_count ?? agent.tools?.length ?? 0}</Text></div>
                        </div>
                        <div style={{ background: 'rgba(255,255,255,0.75)', borderRadius: 14, padding: 12 }}>
                          <Text type="secondary" style={{ fontSize: 12 }}>成功率</Text>
                          <div><Text strong>{`${(((metrics?.success_rate ?? 0) || 0) * 100).toFixed(0)}%`}</Text></div>
                        </div>
                        <div style={{ background: 'rgba(255,255,255,0.75)', borderRadius: 14, padding: 12 }}>
                          <Text type="secondary" style={{ fontSize: 12 }}>最近运行</Text>
                          <div><Text strong>{metrics?.last_run_at ? dayjs(metrics.last_run_at).fromNow() : '暂无'}</Text></div>
                        </div>
                      </div>

                      <Space wrap style={{ marginTop: 'auto' }}>{renderAgentActions(agent)}</Space>
                    </Card>
                  </Col>
                );
              })}
            </Row>
          )}
        </Card>
        )}
      </div>

      <Drawer
        title={selectedAgent ? selectedAgent.name : '专家详情'}
        placement="right"
        width={680}
        open={detailOpen && !!selectedAgent}
        onClose={() => setDetailOpen(false)}
        extra={selectedAgent ? <Button onClick={() => openEditor(selectedAgent)}>编辑配置</Button> : null}
      >
        {selectedAgent && (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Card bordered={false} style={{ borderRadius: 20, background: ROLE_STYLES[selectedAgent.role].bg, border: `1px solid ${ROLE_STYLES[selectedAgent.role].border}` }}>
              <Space wrap size={10}>
                <Avatar size={56} icon={ROLE_STYLES[selectedAgent.role].icon} style={{ background: ROLE_STYLES[selectedAgent.role].color }} />
                <div>
                  <Space wrap size={8}>
                    <Title level={4} style={{ margin: 0 }}>{selectedAgent.name}</Title>
                    <Tag color={selectedAgent.role === 'orchestrator' ? 'gold' : 'purple'}>
                      {ROLE_STYLES[selectedAgent.role].label}
                    </Tag>
                    <Badge status={selectedAgent.is_active ? 'success' : 'default'} text={selectedAgent.is_active ? '在线' : '离线'} />
                  </Space>
                  <Paragraph style={{ margin: '8px 0 0', color: '#475569' }}>
                    {selectedAgent.description || '暂无角色描述'}
                  </Paragraph>
                </div>
              </Space>
            </Card>

            <Row gutter={[12, 12]}>
              <Col span={8}><Card size="small" style={{ borderRadius: 16 }}><Statistic title="调用次数" value={selectedAgent.metrics?.runs || 0} /></Card></Col>
              <Col span={8}><Card size="small" style={{ borderRadius: 16 }}><Statistic title="平均耗时" value={Math.round(selectedAgent.metrics?.avg_duration_ms || 0)} suffix="ms" /></Card></Col>
              <Col span={8}><Card size="small" style={{ borderRadius: 16 }}><Statistic title="异常次数" value={selectedAgent.metrics?.error_count || 0} /></Card></Col>
            </Row>

            <Card size="small" title="工具装备" style={{ borderRadius: 18 }}>
              <Space wrap>
                {(selectedAgent.tools || []).length > 0 ? selectedAgent.tools?.map((tool) => <Tag key={tool}>{tool}</Tag>) : <Text type="secondary">未配置工具</Text>}
              </Space>
            </Card>

            <Card size="small" title="路由与协作" style={{ borderRadius: 18 }}>
              <Space direction="vertical" size={10} style={{ width: '100%' }}>
                <div>
                  <Text type="secondary">路由关键词</Text>
                  <div style={{ marginTop: 8 }}>
                    {(selectedAgent.routing_keywords || []).length > 0 ? selectedAgent.routing_keywords?.map((keyword) => <Tag key={keyword} color="blue">{keyword}</Tag>) : <Text type="secondary">未设置</Text>}
                  </div>
                </div>
                <div>
                  <Text type="secondary">接管策略</Text>
                  <div style={{ marginTop: 6 }}>
                    <Tag color={selectedAgent.handoff_strategy === 'return' ? 'green' : 'orange'}>
                      {selectedAgent.handoff_strategy === 'return' ? '执行后归还主控' : '执行后结束回合'}
                    </Tag>
                  </div>
                </div>
              </Space>
            </Card>

            <Card
              size="small"
              title={<span><ExperimentOutlined /> 快速试跑</span>}
              style={{ borderRadius: 18 }}
            >
              <Space direction="vertical" size={14} style={{ width: '100%' }}>
                <Alert
                  type="info"
                  showIcon
                  message="直接验证当前专家配置是否能正常响应"
                  description="默认关闭 Canvas，避免试跑时污染会话展示。"
                />
                <Input.TextArea rows={5} value={testQuery} onChange={(e) => setTestQuery(e.target.value)} placeholder="输入一段测试问题" />
                <Select
                  value={testInteractionMode}
                  onChange={(value) => setTestInteractionMode(value as 'chat' | 'workflow' | 'builder' | 'analysis')}
                  style={{ width: 220 }}
                  options={[
                    { label: '对话 Chat', value: 'chat' },
                    { label: '流程 Workflow', value: 'workflow' },
                    { label: '构建 Builder', value: 'builder' },
                    { label: '分析 Analysis', value: 'analysis' },
                  ]}
                />
                <Button type="primary" loading={testing} onClick={() => runAgentTest(selectedAgent)}>
                  运行测试
                </Button>
                <Card size="small" title="测试结果" style={{ borderRadius: 14, background: '#f8fafc' }}>
                  {testResult ? (
                    <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 320, overflow: 'auto' }}>
                      {testResult}
                    </pre>
                  ) : (
                    <Text type="secondary">还没有运行测试。</Text>
                  )}
                </Card>
              </Space>
            </Card>
          </Space>
        )}
      </Drawer>

      <Drawer
        title={<span style={{ fontSize: 24, fontWeight: 700 }}>{editingAgent ? `编辑专家 · ${editingAgent.name}` : '创建新专家'}</span>}
        placement="right"
        width={760}
        open={editorOpen}
        onClose={() => setEditorOpen(false)}
        extra={
          <Space>
            <Button onClick={validateConfig} loading={validating}>校验配置</Button>
            <Button type="primary" onClick={handleSubmit}>保存专家</Button>
          </Space>
        }
      >
        <Space direction="vertical" size={18} style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message="这一步不仅是填资料"
            description="建议同时明确职责边界、常用工具和路由关键词，这样主控才能更稳定地把任务分发给合适的专家。"
          />
          {editorConflictWarnings.length > 0 && (
            <Alert
              type="warning"
              showIcon
              message="保存前冲突预检"
              description={
                <ul style={{ marginBottom: 0, paddingLeft: 18 }}>
                  {editorConflictWarnings.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              }
            />
          )}

          <Form form={form} layout="vertical">
            <Tabs
              items={[
                {
                  key: 'base',
                  label: '基础配置',
                  children: (
                    <Space direction="vertical" size={12} style={{ width: '100%' }}>
                      <Row gutter={14}>
                        <Col span={12}>
                          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
                            <Input placeholder="例如 合同审查专家" />
                          </Form.Item>
                        </Col>
                        <Col span={12}>
                          <Form.Item name="role" label="角色" rules={[{ required: true }]}>
                            <Select>
                              <Select.Option value="orchestrator">主控 Orchestrator</Select.Option>
                              <Select.Option value="expert">垂直专家 Expert</Select.Option>
                            </Select>
                          </Form.Item>
                        </Col>
                      </Row>

                      <Form.Item shouldUpdate={(prev, curr) => prev.role !== curr.role} noStyle>
                        {({ getFieldValue }) => (
                          <Alert
                            type={getFieldValue('role') === 'orchestrator' ? 'warning' : 'info'}
                            showIcon
                            style={{ marginBottom: 12 }}
                            message={getFieldValue('role') === 'orchestrator' ? '当前角色：主控' : '当前角色：专家'}
                            description={ROLE_CHANGE_HINTS[(getFieldValue('role') || 'expert') as 'orchestrator' | 'expert']}
                          />
                        )}
                      </Form.Item>

                      <Form.Item name="description" label="角色描述">
                        <Input.TextArea rows={3} placeholder="用 1-2 段话描述它适合处理的问题、输出风格和边界。" />
                      </Form.Item>

                      <Form.Item name="model_config_id" label="核心模型" rules={[{ required: true, message: '请选择模型' }]}>
                        <Select showSearch optionFilterProp="label" placeholder="选择用于驱动该专家的模型">
                          {Array.from(new Set(modelOptions.map((item) => item.group))).map((group) => (
                            <Select.OptGroup key={group} label={group}>
                              {modelOptions.filter((item) => item.group === group).map((option) => (
                                <Select.Option key={option.value} value={option.value} label={option.label}>
                                  {option.label}
                                </Select.Option>
                              ))}
                            </Select.OptGroup>
                          ))}
                        </Select>
                      </Form.Item>

                      <Row gutter={14}>
                        <Col span={12}>
                          <Form.Item name="is_public" label="可见性" valuePropName="checked">
                            <Switch checkedChildren="公开" unCheckedChildren="私有" />
                          </Form.Item>
                        </Col>
                        <Col span={12}>
                          <Form.Item name="is_active" label="状态" valuePropName="checked">
                            <Switch checkedChildren="在线" unCheckedChildren="离线" />
                          </Form.Item>
                        </Col>
                      </Row>

                      <Form.Item name="system_prompt" label="系统指令">
                        <Input.TextArea rows={8} placeholder="描述该专家的身份、目标、步骤偏好、禁止事项和输出要求。" />
                      </Form.Item>
                    </Space>
                  ),
                },
                {
                  key: 'tools',
                  label: '工具与路由',
                  children: (
                    <Space direction="vertical" size={14} style={{ width: '100%' }}>
                      <Form.Item name="tools" label="工具装备">
                        <Checkbox.Group style={{ width: '100%' }}>
                          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                            {registeredTools.map((tool) => (
                              <Card key={tool.name} size="small" style={{ borderRadius: 14 }}>
                                <Checkbox value={tool.name}>
                                  <Space direction="vertical" size={4}>
                                    <Text strong>{tool.label}</Text>
                                    <Text type="secondary" style={{ fontSize: 12 }}>{tool.description}</Text>
                                    <Tag color="blue">{tool.category}</Tag>
                                  </Space>
                                </Checkbox>
                              </Card>
                            ))}
                          </div>
                        </Checkbox.Group>
                      </Form.Item>
                      <Form.Item shouldUpdate={(prev, curr) => prev.role !== curr.role} noStyle>
                        {({ getFieldValue }) =>
                          getFieldValue('role') === 'expert' ? (
                            <>
                              <Form.Item name="routing_keywords" label="路由关键词" extra="多个关键词按回车分隔，主控将据此判断是否移交给该专家。">
                                <Select mode="tags" placeholder="例如 合同、翻译、调试、前端" />
                              </Form.Item>

                              <Form.Item name="handoff_strategy" label="接管策略">
                                <Select>
                                  <Select.Option value="return">执行完成后归还主控</Select.Option>
                                  <Select.Option value="end">执行完成后结束当前回合</Select.Option>
                                </Select>
                              </Form.Item>
                            </>
                          ) : (
                            <Alert
                              type="info"
                              showIcon
                              message="主控应用不参与专家路由命中"
                              description="当前角色是主控，因此不会出现在专家协作目录里。路由关键词不会再用于被其他主控命中，后续更适合给它配置独立的应用编排。"
                            />
                          )
                        }
                      </Form.Item>
                    </Space>
                  ),
                },
              ]}
            />
          </Form>

          {validation && (
            <Alert
              type={validation.warnings.length > 0 ? 'warning' : 'success'}
              showIcon
              icon={validation.warnings.length > 0 ? <SettingOutlined /> : <CheckCircleOutlined />}
              message={validation.warnings.length > 0 ? '配置校验通过，但还有优化建议' : '配置校验通过'}
              description={
                validation.warnings.length > 0 ? (
                  <ul style={{ marginBottom: 0, paddingLeft: 18 }}>
                    {validation.warnings.map((item) => <li key={item}>{item}</li>)}
                  </ul>
                ) : '当前配置结构完整，可以安全保存。'
              }
            />
          )}
        </Space>
      </Drawer>
    </div>
  );
};

export default AgentManager;
