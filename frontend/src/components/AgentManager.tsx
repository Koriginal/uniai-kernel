import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Avatar,
  Badge,
  Button,
  Card,
  Checkbox,
  Col,
  Drawer,
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
  Tabs,
  Tag,
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
  orchestrator: '改成主控后，它会退出专家协作目录，其他主控不能再通过专家移交直接调用它。',
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
  const [validating, setValidating] = useState(false);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [testQuery, setTestQuery] = useState('请用一句话介绍你的职责和适合处理的问题。');
  const [testResult, setTestResult] = useState<string>('');

  const notify = {
    success: (content: string) => (msgApi?.success ? msgApi.success(content) : message.success(content)),
    error: (content: string) => (msgApi?.error ? msgApi.error(content) : message.error(content)),
  };

  useEffect(() => {
    fetchTools();
    fetchDashboard();
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
    } catch (err: any) {
      notify.error(err.response?.data?.detail || '状态更新失败');
    }
  };

  const runAgentTest = async (agent: Agent) => {
    try {
      setTesting(true);
      const res = await axios.post(`/api/v1/agents/${agent.id}/test`, {
        query: testQuery,
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

  return (
    <div style={{ padding: 24, background: '#edf3fb', minHeight: '100%', overflow: 'auto' }}>
      <div style={{ maxWidth: 1500, margin: '0 auto' }}>
        <Card
          bordered={false}
          style={{
            marginBottom: 18,
            borderRadius: 24,
            overflow: 'hidden',
            background: 'linear-gradient(135deg, #111827 0%, #2563eb 40%, #dbeafe 100%)',
            boxShadow: '0 18px 44px rgba(37,99,235,0.14)',
          }}
          bodyStyle={{ padding: '18px 22px' }}
        >
          <Row gutter={[24, 24]} align="middle">
            <Col xs={24} xl={16}>
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                <Tag color="rgba(255,255,255,0.14)" style={{ color: '#fff', border: '1px solid rgba(255,255,255,0.2)', padding: '2px 10px', borderRadius: 999, width: 'fit-content' }}>
                  Swarm Control
                </Tag>
                <Title level={3} style={{ margin: 0, color: '#fff' }}>
                  专家集群管理中心
                </Title>
                <Text style={{ color: 'rgba(255,255,255,0.82)', fontSize: 14 }}>
                  专家治理、路由编排、健康诊断和快速试跑集中在这一页完成。
                </Text>
                <Space wrap>
                  <Button type="primary" icon={<PlusOutlined />} onClick={() => openEditor()} style={{ background: '#fff', color: '#2563eb', borderColor: '#fff' }}>
                    新增专家
                  </Button>
                  <Button icon={<ReloadOutlined />} onClick={() => { onRefresh(); fetchDashboard(); }} style={{ background: 'rgba(255,255,255,0.08)', color: '#fff', borderColor: 'rgba(255,255,255,0.2)' }}>
                    刷新数据
                  </Button>
                </Space>
              </Space>
            </Col>
            <Col xs={24} xl={8}>
              <Row gutter={[12, 12]}>
                <Col span={12}>
                  <Card bordered={false} size="small" style={{ borderRadius: 16, background: 'rgba(255,255,255,0.14)', backdropFilter: 'blur(10px)' }}>
                    <Statistic title={<span style={{ color: 'rgba(255,255,255,0.72)', fontSize: 12 }}>活跃专家</span>} value={dashboard?.summary.active || 0} valueStyle={{ color: '#fff', fontSize: 28 }} prefix={<ThunderboltOutlined style={{ color: '#fff' }} />} />
                  </Card>
                </Col>
                <Col span={12}>
                  <Card bordered={false} size="small" style={{ borderRadius: 16, background: 'rgba(255,255,255,0.14)', backdropFilter: 'blur(10px)' }}>
                    <Statistic title={<span style={{ color: 'rgba(255,255,255,0.72)', fontSize: 12 }}>主控 / 专家</span>} value={`${dashboard?.summary.orchestrators || 0} / ${dashboard?.summary.experts || 0}`} valueStyle={{ color: '#fff', fontSize: 28 }} prefix={<RadarChartOutlined style={{ color: '#fff' }} />} />
                  </Card>
                </Col>
              </Row>
            </Col>
          </Row>
        </Card>

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
            <div style={{ borderRadius: 18, overflow: 'hidden' }}>
              <AgentTopologyEditor
                agents={agents}
                scopeAgentId={topologyScopeId}
                onClickNode={(agent) => openDetail(agent.id)}
                onAgentsUpdated={() => {
                  onRefresh();
                  fetchDashboard();
                }}
              />
            </div>
          </Space>
        </Card>

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
              <Text type="secondary">点击专家卡片查看详情与试跑</Text>
            </Space>
          </Space>
        </Card>

        <Card bordered={false} style={{ borderRadius: 24 }}>
          {loadingDashboard ? (
            <div style={{ padding: 60, textAlign: 'center' }}>
              <Text type="secondary">正在加载专家状态...</Text>
            </div>
          ) : filteredAgents.length === 0 ? (
            <Empty description="没有匹配到专家" />
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

                      <Space wrap style={{ marginTop: 'auto' }}>
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
                    </Card>
                  </Col>
                );
              })}
            </Row>
          )}
        </Card>
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

                      <Form.Item name="routing_keywords" label="路由关键词" extra="多个关键词按回车分隔，主控将据此判断是否移交给该专家。">
                        <Select mode="tags" placeholder="例如 合同、翻译、调试、前端" />
                      </Form.Item>

                      <Form.Item name="handoff_strategy" label="接管策略">
                        <Select>
                          <Select.Option value="return">执行完成后归还主控</Select.Option>
                          <Select.Option value="end">执行完成后结束当前回合</Select.Option>
                        </Select>
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
