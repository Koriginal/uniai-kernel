import React, { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Empty,
  message,
  Progress,
  Row,
  Select,
  Segmented,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd';
import { Column, Line, Pie } from '@ant-design/plots';
import {
  ApiOutlined,
  BarChartOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  LikeOutlined,
  MessageOutlined,
  PartitionOutlined,
  ReloadOutlined,
  TeamOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import axios from 'axios';
import dayjs from 'dayjs';

const { Title, Text } = Typography;

interface DashboardSummary {
  total_sessions: number;
  active_sessions: number;
  total_messages: number;
  user_messages: number;
  assistant_messages: number;
  total_executions: number;
  tool_calls: number;
  avg_duration_ms: number;
  error_rate: number;
  total_tokens: number;
  likes: number;
  dislikes: number;
  tenant_count: number;
  api_key_sessions: number;
  external_api_ratio: number;
  orchestrator_sessions: number;
}

interface DailyActivity {
  date: string;
  sessions: number;
  messages: number;
  tokens: number;
  executions: number;
  tool_calls: number;
}

interface TopAgent {
  agent_id?: string | null;
  agent_name: string;
  executions: number;
  avg_duration_ms: number;
  success_rate: number;
  error_count: number;
  tool_calls: number;
}

interface TopNode {
  node_name: string;
  executions: number;
  avg_duration_ms: number;
  error_count: number;
}

interface RecentExecution {
  id: string;
  created_at: string;
  session_id?: string | null;
  request_id?: string | null;
  node_name: string;
  agent_id?: string | null;
  agent_name: string;
  status: string;
  duration_ms: number;
  input_tokens: number;
  output_tokens: number;
  tool_calls_count: number;
  error_message?: string | null;
  user_id?: string | null;
  auth_source?: string;
  api_key_id?: string | null;
}

interface AuthSourceItem {
  source: string;
  sessions: number;
}

interface ApiKeyUsageItem {
  api_key_id: string;
  name: string;
  sessions: number;
  messages: number;
  executions: number;
  tokens: number;
  tool_calls: number;
  errors: number;
  is_active: boolean;
}

interface TenantUsageItem {
  user_id: string;
  tenant_name: string;
  sessions: number;
  messages: number;
  executions: number;
  tokens: number;
  tool_calls: number;
  errors: number;
}

interface DashboardData {
  scope: 'mine' | 'global';
  summary: DashboardSummary;
  daily_activity: DailyActivity[];
  top_agents: TopAgent[];
  top_nodes: TopNode[];
  recent_executions: RecentExecution[];
  binding: {
    auth_source_breakdown: AuthSourceItem[];
    top_api_keys: ApiKeyUsageItem[];
    tenant_usage: TenantUsageItem[];
  };
  filter_options?: {
    orchestrators: Array<{ id: string; name: string }>;
    agents: Array<{ id: string; name: string; role?: string }>;
    api_keys: Array<{ id: string; name: string; user_id?: string; is_active?: boolean }>;
    tenants: Array<{ user_id: string; name: string }>;
    auth_sources: string[];
  };
  selection?: {
    orchestrator_id?: string | null;
    agent_id?: string | null;
    auth_source?: string | null;
    api_key_id?: string | null;
    tenant_user_id?: string | null;
  };
}

const defaultData: DashboardData = {
  scope: 'mine',
  summary: {
    total_sessions: 0,
    active_sessions: 0,
    total_messages: 0,
    user_messages: 0,
    assistant_messages: 0,
    total_executions: 0,
    tool_calls: 0,
    avg_duration_ms: 0,
    error_rate: 0,
    total_tokens: 0,
    likes: 0,
    dislikes: 0,
    tenant_count: 0,
    api_key_sessions: 0,
    external_api_ratio: 0,
    orchestrator_sessions: 0,
  },
  daily_activity: [],
  top_agents: [],
  top_nodes: [],
  recent_executions: [],
  binding: {
    auth_source_breakdown: [],
    top_api_keys: [],
    tenant_usage: [],
  },
  filter_options: {
    orchestrators: [],
    agents: [],
    api_keys: [],
    tenants: [],
    auth_sources: [],
  },
  selection: {},
};

const SOURCE_LABEL: Record<string, string> = {
  dashboard_jwt: '控制台登录',
  api_key: 'API Key',
  fallback: '兼容回退',
  unknown: '未知',
};

const AuditLogView: React.FC = () => {
  const kpiCardStyle: React.CSSProperties = { borderRadius: 12, height: 132 };
  const kpiCardBodyStyle: React.CSSProperties = {
    padding: '16px 18px',
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'space-between',
  };
  const blockCardStyle: React.CSSProperties = { borderRadius: 12 };
  const equalPanelCardStyle: React.CSSProperties = { ...blockCardStyle, height: '100%', width: '100%' };
  const panelCardBodyStyle: React.CSSProperties = { padding: 14 };
  const statTileStyle: React.CSSProperties = {
    background: '#f6f8fb',
    border: '1px solid #edf0f5',
    borderRadius: 10,
    padding: '10px 12px',
    minHeight: 106,
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'space-between',
  };
  const kpiHintStyle: React.CSSProperties = {
    display: 'block',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  };

  const [loading, setLoading] = useState(true);
  const [dashboard, setDashboard] = useState<DashboardData>(defaultData);
  const [selectedExecution, setSelectedExecution] = useState<RecentExecution | null>(null);
  const [days, setDays] = useState<number>(7);
  const [scope, setScope] = useState<'mine' | 'global'>('mine');
  const [isAdmin, setIsAdmin] = useState<boolean>(false);
  const [orchestratorFilter, setOrchestratorFilter] = useState<string | undefined>(undefined);
  const [agentFilter, setAgentFilter] = useState<string | undefined>(undefined);
  const [authSourceFilter, setAuthSourceFilter] = useState<string | undefined>(undefined);
  const [apiKeyFilter, setApiKeyFilter] = useState<string | undefined>(undefined);
  const [tenantFilter, setTenantFilter] = useState<string | undefined>(undefined);
  const getAuthHeaders = () => {
    const token = localStorage.getItem('token');
    return token ? { Authorization: `Bearer ${token}` } : {};
  };

  const fetchDashboard = async (
    nextDays = days,
    nextScope = scope,
    extraFilters?: {
      orchestrator_id?: string;
      agent_id?: string;
      auth_source?: string;
      api_key_id?: string;
      tenant_user_id?: string;
    }
  ) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('days', String(nextDays));
      params.set('scope', nextScope);
      const merged = {
        orchestrator_id: orchestratorFilter,
        agent_id: agentFilter,
        auth_source: authSourceFilter,
        api_key_id: apiKeyFilter,
        tenant_user_id: tenantFilter,
        ...(extraFilters || {}),
      };
      if (merged.orchestrator_id) params.set('orchestrator_id', merged.orchestrator_id);
      if (merged.agent_id) params.set('agent_id', merged.agent_id);
      if (merged.auth_source) params.set('auth_source', merged.auth_source);
      if (merged.api_key_id) params.set('api_key_id', merged.api_key_id);
      if (merged.tenant_user_id) params.set('tenant_user_id', merged.tenant_user_id);
      const res = await axios.get(`/api/v1/audit/dashboard?${params.toString()}`, {
        headers: getAuthHeaders(),
      });
      setDashboard({
        ...defaultData,
        ...res.data,
        summary: { ...defaultData.summary, ...(res.data?.summary || {}) },
        daily_activity: res.data?.daily_activity || [],
        top_agents: res.data?.top_agents || [],
        top_nodes: res.data?.top_nodes || [],
        recent_executions: res.data?.recent_executions || [],
        binding: {
          auth_source_breakdown: res.data?.binding?.auth_source_breakdown || [],
          top_api_keys: res.data?.binding?.top_api_keys || [],
          tenant_usage: res.data?.binding?.tenant_usage || [],
        },
        filter_options: res.data?.filter_options || defaultData.filter_options,
        selection: res.data?.selection || {},
      });
    } catch (err) {
      console.error('Failed to fetch audit dashboard', err);
      const status = (err as any)?.response?.status;
      if (status === 401) {
        message.error('登录态已失效，请重新登录后查看审计数据');
      }
      if (status === 403) {
        setScope('mine');
      }
      setDashboard(defaultData);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const bootstrap = async () => {
      try {
        const meRes = await axios.get('/api/v1/auth/me', {
          headers: getAuthHeaders(),
        });
        const admin = !!meRes?.data?.is_admin;
        setIsAdmin(admin);
        const initialScope: 'mine' | 'global' = admin ? scope : 'mine';
        if (!admin) setScope('mine');
        await fetchDashboard(days, initialScope);
      } catch (err) {
        setIsAdmin(false);
        setScope('mine');
        await fetchDashboard(days, 'mine');
      }
    };
    bootstrap();
  }, []);

  useEffect(() => {
    const sel = dashboard.selection || {};
    if (sel.orchestrator_id !== undefined) setOrchestratorFilter(sel.orchestrator_id || undefined);
    if (sel.agent_id !== undefined) setAgentFilter(sel.agent_id || undefined);
    if (sel.auth_source !== undefined) setAuthSourceFilter(sel.auth_source || undefined);
    if (sel.api_key_id !== undefined) setApiKeyFilter(sel.api_key_id || undefined);
    if (sel.tenant_user_id !== undefined) setTenantFilter(sel.tenant_user_id || undefined);
  }, [dashboard.selection?.orchestrator_id, dashboard.selection?.agent_id, dashboard.selection?.auth_source, dashboard.selection?.api_key_id, dashboard.selection?.tenant_user_id]);

  const activitySeries = useMemo(
    () =>
      (dashboard.daily_activity || []).flatMap((item) => [
        { date: item.date, type: '会话', value: item.sessions },
        { date: item.date, type: '消息', value: item.messages },
        { date: item.date, type: '节点执行', value: item.executions },
      ]),
    [dashboard.daily_activity]
  );

  const authSourceChart = useMemo(
    () =>
      (dashboard.binding.auth_source_breakdown || []).map((item) => ({
        type: SOURCE_LABEL[item.source] || item.source,
        value: item.sessions,
      })),
    [dashboard.binding.auth_source_breakdown]
  );

  const nodeChartData = useMemo(
    () =>
      (dashboard.top_nodes || []).map((item) => ({
        name: item.node_name,
        value: item.executions,
      })),
    [dashboard.top_nodes]
  );

  const feedbackTotal = dashboard.summary.likes + dashboard.summary.dislikes;
  const approvalRate = feedbackTotal > 0 ? dashboard.summary.likes / feedbackTotal : 0;
  const successRate = dashboard.summary.total_executions > 0 ? (1 - dashboard.summary.error_rate) : 0;
  const feedbackCoverageRate = dashboard.summary.assistant_messages > 0 ? (feedbackTotal / dashboard.summary.assistant_messages) : 0;
  const recentErrorCount = (dashboard.recent_executions || []).filter((item) => item.status !== 'success').length;
  const nodeErrorTop = [...(dashboard.top_nodes || [])]
    .sort((a, b) => (b.error_count || 0) - (a.error_count || 0))
    .filter((item) => (item.error_count || 0) > 0)
    .slice(0, 5);
  const slowAgentTop = [...(dashboard.top_agents || [])]
    .sort((a, b) => (b.avg_duration_ms || 0) - (a.avg_duration_ms || 0))
    .slice(0, 5);
  const avgToolCallsPerExecution = dashboard.summary.total_executions > 0
    ? dashboard.summary.tool_calls / dashboard.summary.total_executions
    : 0;
  const dislikeRate = feedbackTotal > 0 ? dashboard.summary.dislikes / feedbackTotal : 0;

  const lineConfig = {
    data: activitySeries,
    xField: 'date',
    yField: 'value',
    seriesField: 'type',
    smooth: true,
    point: { size: 3 },
    color: ['#1677ff', '#52c41a', '#fa8c16'],
    legend: { position: 'top' as const },
  };

  const pieConfig = {
    data: nodeChartData,
    angleField: 'value',
    colorField: 'name',
    radius: 0.82,
    label: { type: 'outer', content: '{name} {percentage}' },
    interactions: [{ type: 'element-active' }],
  };

  const sourcePieConfig = {
    data: authSourceChart,
    angleField: 'value',
    colorField: 'type',
    radius: 0.78,
    label: { type: 'inner', offset: '-30%', content: '{percentage}' },
    legend: { position: 'bottom' as const },
  };

  const agentColumnConfig = {
    data: dashboard.top_agents || [],
    xField: 'agent_name',
    yField: 'executions',
    label: false,
    color: '#1677ff',
  };
  const isPersonalMode = !isAdmin || scope === 'mine';

  const executionColumns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 150,
      render: (value: string) => dayjs(value).format('MM-DD HH:mm:ss'),
    },
    {
      title: '节点',
      dataIndex: 'node_name',
      key: 'node_name',
      render: (value: string) => <Tag color="blue">{value}</Tag>,
    },
    {
      title: '专家',
      dataIndex: 'agent_name',
      key: 'agent_name',
      render: (value: string) => value || '-',
    },
    {
      title: '来源',
      dataIndex: 'auth_source',
      key: 'auth_source',
      width: 130,
      render: (value: string) => <Tag>{SOURCE_LABEL[value] || value || '未知'}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (value: string) => <Tag color={value === 'success' ? 'green' : 'red'}>{value}</Tag>,
    },
    {
      title: '耗时',
      dataIndex: 'duration_ms',
      key: 'duration_ms',
      width: 100,
      render: (value: number) => `${Math.round(value || 0)}ms`,
    },
    {
      title: '详情',
      key: 'action',
      width: 90,
      render: (_: unknown, record: RecentExecution) => (
        <Text style={{ color: '#1677ff', cursor: 'pointer' }} onClick={() => setSelectedExecution(record)}>
          查看
        </Text>
      ),
    },
  ];

  return (
    <div style={{ padding: 14, background: '#edf2f7', minHeight: '100%', overflow: 'auto' }}>
      <div style={{ width: '100%', margin: 0 }}>
        <Card
          bordered={false}
          style={{ marginBottom: 10, borderRadius: 12, border: '1px solid #dbeafe', background: '#f8fbff', boxShadow: '0 4px 12px rgba(29,78,216,0.05)' }}
          bodyStyle={{ padding: '10px 12px' }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
            <Space direction="vertical" size={4}>
              <Space wrap size={6}>
                <Tag color="blue" style={{ borderRadius: 999, margin: 0 }}>Audit Hub</Tag>
                <Text type="secondary" style={{ fontSize: 12 }}>绑定租户、API Key 与执行链路的统一监控</Text>
              </Space>
              <Title level={4} style={{ margin: 0, lineHeight: 1.25 }}>
                <BarChartOutlined /> 使用审计与业务统计
              </Title>
            </Space>
            <Space wrap>
              <Select
                value={days}
                onChange={(value) => {
                  setDays(value);
                  fetchDashboard(value, scope);
                }}
                options={[
                  { label: '近 3 天', value: 3 },
                  { label: '近 7 天', value: 7 },
                  { label: '近 14 天', value: 14 },
                  { label: '近 30 天', value: 30 },
                ]}
                style={{ width: 120 }}
              />
              {isAdmin ? (
                <Segmented
                  value={scope}
                  onChange={(value) => {
                    const next = value as 'mine' | 'global';
                    setScope(next);
                    if (next === 'mine') {
                      setTenantFilter(undefined);
                      fetchDashboard(days, next, { tenant_user_id: undefined });
                    } else {
                      fetchDashboard(days, next);
                    }
                  }}
                  options={[
                    { label: '我的租户', value: 'mine' },
                    { label: '全局租户', value: 'global' },
                  ]}
                />
              ) : (
                <Tag color="blue" style={{ margin: 0 }}>我的租户视图</Tag>
              )}
              <Tag icon={<ReloadOutlined />} style={{ margin: 0, cursor: 'pointer' }} onClick={() => fetchDashboard()}>
                刷新
              </Tag>
            </Space>
          </div>
        </Card>

        <Card bordered={false} style={{ marginBottom: 10, borderRadius: 12 }} bodyStyle={{ padding: '10px 12px' }}>
          <Row gutter={[8, 8]} align="middle">
            <Col xs={24} sm={12} lg={6}>
            <Select
              allowClear
              placeholder="按主控应用筛选"
              value={orchestratorFilter}
              notFoundContent="暂无可筛选数据"
              listHeight={224}
              style={{ width: '100%' }}
              options={(dashboard.filter_options?.orchestrators || []).map((item) => ({
                label: item.name,
                value: item.id,
              }))}
              onChange={(value) => {
                const next = value || undefined;
                setOrchestratorFilter(next);
                fetchDashboard(days, scope, { orchestrator_id: next });
              }}
            />
            </Col>
            <Col xs={24} sm={12} lg={6}>
            <Select
              allowClear
              placeholder="按专家筛选"
              value={agentFilter}
              notFoundContent="暂无可筛选数据"
              listHeight={224}
              style={{ width: '100%' }}
              options={(dashboard.filter_options?.agents || []).map((item) => ({
                label: `${item.name}${item.role ? ` · ${item.role === 'orchestrator' ? '主控' : '专家'}` : ''}`,
                value: item.id,
              }))}
              onChange={(value) => {
                const next = value || undefined;
                setAgentFilter(next);
                fetchDashboard(days, scope, { agent_id: next });
              }}
            />
            </Col>
            <Col xs={24} sm={12} lg={6}>
            <Select
              allowClear
              placeholder="按鉴权来源筛选"
              value={authSourceFilter}
              notFoundContent="暂无可筛选数据"
              listHeight={224}
              style={{ width: '100%' }}
              options={(dashboard.filter_options?.auth_sources || []).map((item) => ({
                label: SOURCE_LABEL[item] || item,
                value: item,
              }))}
              onChange={(value) => {
                const next = value || undefined;
                setAuthSourceFilter(next);
                fetchDashboard(days, scope, { auth_source: next });
              }}
            />
            </Col>
            <Col xs={24} sm={12} lg={6}>
            <Select
              allowClear
              placeholder="按 API Key 筛选"
              value={apiKeyFilter}
              notFoundContent="暂无可筛选数据"
              listHeight={224}
              style={{ width: '100%' }}
              options={(dashboard.filter_options?.api_keys || []).map((item) => ({
                label: `${item.name} (${item.id})`,
                value: item.id,
              }))}
              onChange={(value) => {
                const next = value || undefined;
                setApiKeyFilter(next);
                fetchDashboard(days, scope, { api_key_id: next });
              }}
            />
            </Col>
            {scope === 'global' && (
              <Col xs={24} sm={12} lg={6}>
                <Select
                allowClear
                placeholder="按租户筛选"
                value={tenantFilter}
                notFoundContent="暂无可筛选数据"
                listHeight={224}
                style={{ width: '100%' }}
                options={(dashboard.filter_options?.tenants || []).map((item) => ({
                  label: `${item.name} (${item.user_id})`,
                  value: item.user_id,
                }))}
                onChange={(value) => {
                  const next = value || undefined;
                  setTenantFilter(next);
                  fetchDashboard(days, scope, { tenant_user_id: next });
                }}
              />
              </Col>
            )}
            <Col xs={24} sm={12} lg={scope === 'global' ? 6 : 24}>
              <Button
                size="middle"
                onClick={() => {
                  setOrchestratorFilter(undefined);
                  setAgentFilter(undefined);
                  setAuthSourceFilter(undefined);
                  setApiKeyFilter(undefined);
                  setTenantFilter(undefined);
                  fetchDashboard(days, scope, {
                    orchestrator_id: undefined,
                    agent_id: undefined,
                    auth_source: undefined,
                    api_key_id: undefined,
                    tenant_user_id: undefined,
                  });
                }}
              >
                清空筛选
              </Button>
            </Col>
          </Row>
        </Card>

        <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
          <Col xs={24} sm={12} md={12} lg={6} xl={6} xxl={6}>
            <Card bordered={false} loading={loading} style={kpiCardStyle} bodyStyle={kpiCardBodyStyle}>
              <Statistic title="会话" value={dashboard.summary.total_sessions} prefix={<DatabaseOutlined style={{ color: '#1677ff' }} />} />
              <Text type="secondary" style={kpiHintStyle}>活跃 {dashboard.summary.active_sessions}</Text>
            </Card>
          </Col>
          <Col xs={24} sm={12} md={12} lg={6} xl={6} xxl={6}>
            <Card bordered={false} loading={loading} style={kpiCardStyle} bodyStyle={kpiCardBodyStyle}>
              <Statistic title="消息" value={dashboard.summary.total_messages} prefix={<MessageOutlined style={{ color: '#52c41a' }} />} />
              <Text type="secondary" style={kpiHintStyle}>用户 {dashboard.summary.user_messages} / 助手 {dashboard.summary.assistant_messages}</Text>
            </Card>
          </Col>
          <Col xs={24} sm={12} md={12} lg={6} xl={6} xxl={6}>
            <Card bordered={false} loading={loading} style={kpiCardStyle} bodyStyle={kpiCardBodyStyle}>
              <Statistic title="执行节点" value={dashboard.summary.total_executions} prefix={<PartitionOutlined style={{ color: '#fa8c16' }} />} />
              <Text type="secondary" style={kpiHintStyle}>工具调用 {dashboard.summary.tool_calls}</Text>
            </Card>
          </Col>
          <Col xs={24} sm={12} md={12} lg={6} xl={6} xxl={6}>
            <Card bordered={false} loading={loading} style={kpiCardStyle} bodyStyle={kpiCardBodyStyle}>
              <Statistic title="租户" value={dashboard.summary.tenant_count} prefix={<TeamOutlined style={{ color: '#722ed1' }} />} />
              <Text type="secondary" style={kpiHintStyle}>主控会话 {dashboard.summary.orchestrator_sessions}</Text>
            </Card>
          </Col>
          <Col xs={24} sm={12} md={12} lg={6} xl={6} xxl={6}>
            <Card bordered={false} loading={loading} style={kpiCardStyle} bodyStyle={kpiCardBodyStyle}>
              <Statistic title="平均耗时" value={dashboard.summary.avg_duration_ms} precision={0} suffix="ms" prefix={<ClockCircleOutlined style={{ color: '#13c2c2' }} />} />
              <Text type="secondary" style={kpiHintStyle}>错误率 {(dashboard.summary.error_rate * 100).toFixed(1)}%</Text>
            </Card>
          </Col>
          <Col xs={24} sm={12} md={12} lg={6} xl={6} xxl={6}>
            <Card bordered={false} loading={loading} style={kpiCardStyle} bodyStyle={kpiCardBodyStyle}>
              <Statistic title="总 Token" value={dashboard.summary.total_tokens} prefix={<ApiOutlined style={{ color: '#1677ff' }} />} />
              <Text type="secondary" style={kpiHintStyle}>外部会话 {dashboard.summary.api_key_sessions} · {(dashboard.summary.external_api_ratio * 100).toFixed(1)}%</Text>
            </Card>
          </Col>
          <Col xs={24} sm={12} md={12} lg={6} xl={6} xxl={6}>
            <Card bordered={false} loading={loading} style={kpiCardStyle} bodyStyle={kpiCardBodyStyle}>
              <Statistic
                title="执行成功率"
                value={successRate * 100}
                precision={1}
                suffix="%"
                prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
              />
              <Text type="secondary" style={kpiHintStyle}>失败率 {(dashboard.summary.error_rate * 100).toFixed(1)}%</Text>
            </Card>
          </Col>
          <Col xs={24} sm={12} md={12} lg={6} xl={6} xxl={6}>
            <Card bordered={false} loading={loading} style={kpiCardStyle} bodyStyle={kpiCardBodyStyle}>
              <Statistic
                title="反馈覆盖率"
                value={feedbackCoverageRate * 100}
                precision={1}
                suffix="%"
                prefix={<LikeOutlined style={{ color: '#1677ff' }} />}
              />
              <Text type="secondary" style={kpiHintStyle}>反馈 {feedbackTotal} / 助手消息 {dashboard.summary.assistant_messages}</Text>
            </Card>
          </Col>
        </Row>

        <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
          <Col xs={24} xl={14}>
            <Card title="活跃趋势（会话/消息/执行）" bordered={false} loading={loading} style={{ ...blockCardStyle, height: '100%' }} bodyStyle={panelCardBodyStyle}>
              <div style={{ height: 300 }}>
                {activitySeries.length > 0 ? <Line {...lineConfig} /> : <Empty description="近时段暂无活跃数据" />}
              </div>
            </Card>
          </Col>
          <Col xs={24} xl={10}>
            <Card title={isPersonalMode ? '我的身份来源分布（登录 / API Key）' : '身份来源分布（登录 / API Key）'} bordered={false} loading={loading} style={{ ...blockCardStyle, height: '100%' }} bodyStyle={panelCardBodyStyle}>
              <div style={{ height: 300 }}>
                {authSourceChart.length > 0 ? <Pie {...sourcePieConfig} /> : <Empty description="暂无身份来源数据" />}
              </div>
            </Card>
          </Col>
        </Row>

        {isAdmin && (
          <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
            <Col xs={24} xl={12}>
              <Card title="API Key 使用排行" bordered={false} loading={loading} style={{ ...blockCardStyle, height: '100%' }} bodyStyle={panelCardBodyStyle}>
              <Table<ApiKeyUsageItem>
                rowKey="api_key_id"
                size="small"
                pagination={{ pageSize: 6, showSizeChanger: false }}
                scroll={{ x: 640 }}
                dataSource={dashboard.binding.top_api_keys}
                locale={{ emptyText: '暂无 API Key 访问数据' }}
                columns={[
                  {
                    title: 'API Key',
                    key: 'key',
                    render: (_, row) => (
                      <Space direction="vertical" size={0}>
                        <Space>
                          <Text strong>{row.name}</Text>
                          <Tag color={row.is_active ? 'green' : 'default'}>{row.is_active ? '有效' : '停用'}</Tag>
                        </Space>
                        <Text type="secondary" style={{ fontSize: 12 }}>{row.api_key_id}</Text>
                      </Space>
                    ),
                  },
                  { title: '会话', dataIndex: 'sessions', width: 70 },
                  { title: '消息', dataIndex: 'messages', width: 70 },
                  { title: '执行', dataIndex: 'executions', width: 70 },
                  { title: '错误', dataIndex: 'errors', width: 70 },
                ]}
              />
              </Card>
            </Col>
            <Col xs={24} xl={12}>
              <Card title="租户使用排行" bordered={false} loading={loading} style={{ ...blockCardStyle, height: '100%' }} bodyStyle={panelCardBodyStyle}>
              <Table<TenantUsageItem>
                rowKey="user_id"
                size="small"
                pagination={{ pageSize: 6, showSizeChanger: false }}
                scroll={{ x: 640 }}
                dataSource={dashboard.binding.tenant_usage}
                locale={{ emptyText: '暂无租户统计数据' }}
                columns={[
                  {
                    title: '租户',
                    key: 'tenant_name',
                    render: (_, row) => (
                      <Space direction="vertical" size={0}>
                        <Text strong>{row.tenant_name}</Text>
                        <Text type="secondary" style={{ fontSize: 12 }}>{row.user_id}</Text>
                      </Space>
                    ),
                  },
                  { title: '会话', dataIndex: 'sessions', width: 70 },
                  { title: '消息', dataIndex: 'messages', width: 70 },
                  { title: '执行', dataIndex: 'executions', width: 70 },
                  { title: '错误', dataIndex: 'errors', width: 70 },
                ]}
              />
              </Card>
            </Col>
          </Row>
        )}

        <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
          <Col xs={24} xl={14}>
            <Card title={isPersonalMode ? '我的专家执行排名' : '专家执行排名'} bordered={false} loading={loading} style={{ ...blockCardStyle, height: '100%' }} bodyStyle={panelCardBodyStyle}>
              <div style={{ height: 250 }}>
                {dashboard.top_agents.length > 0 ? <Column {...agentColumnConfig} /> : <Empty description="暂无专家执行数据" />}
              </div>
            </Card>
          </Col>
          <Col xs={24} xl={10}>
            <Card title={<span><ToolOutlined /> {isPersonalMode ? '我的热点节点' : '热点节点'}</span>} bordered={false} loading={loading} style={{ ...blockCardStyle, height: '100%' }} bodyStyle={panelCardBodyStyle}>
              <div style={{ height: 250 }}>
                {nodeChartData.length > 0 ? <Pie {...pieConfig} /> : <Empty description="暂无节点执行数据" />}
              </div>
            </Card>
          </Col>
        </Row>

        <Card
          title={isPersonalMode ? '我的最近执行记录（支持链路追溯）' : '最近执行记录（可追溯到租户/API 来源）'}
          bordered={false}
          loading={loading}
          style={{ ...blockCardStyle, marginBottom: 12 }}
          bodyStyle={{ padding: 14 }}
        >
          {dashboard.recent_executions.length > 0 ? (
            <Table
              columns={executionColumns}
              dataSource={dashboard.recent_executions}
              rowKey="id"
              pagination={{ pageSize: 8 }}
              size="small"
              scroll={{ x: 920 }}
            />
          ) : (
            <div style={{ minHeight: 84, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '8px 0' }}>
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无执行记录" style={{ margin: 0 }} />
            </div>
          )}
        </Card>

        <Row gutter={[12, 12]}>
          <Col xs={24} xl={12}>
            <Card title={isPersonalMode ? '我的反馈质量' : '用户反馈质量'} bordered={false} loading={loading} style={equalPanelCardStyle} bodyStyle={panelCardBodyStyle}>
              <Row gutter={[10, 10]} style={{ marginBottom: 10 }}>
                <Col xs={24} sm={8}>
                  <div style={statTileStyle}>
                    <Statistic title="反馈总数" value={feedbackTotal} valueStyle={{ fontSize: 22, lineHeight: 1.15 }} />
                  </div>
                </Col>
                <Col xs={24} sm={8}>
                  <div style={statTileStyle}>
                    <Statistic
                      title="正向占比"
                      value={approvalRate * 100}
                      precision={1}
                      formatter={(value) => `${Number(value || 0).toFixed(1)}%`}
                      valueStyle={{ fontSize: 22, lineHeight: 1.15 }}
                    />
                  </div>
                </Col>
                <Col xs={24} sm={8}>
                  <div style={statTileStyle}>
                    <Statistic
                      title="负向占比"
                      value={dislikeRate * 100}
                      precision={1}
                      formatter={(value) => `${Number(value || 0).toFixed(1)}%`}
                      valueStyle={{ fontSize: 22, lineHeight: 1.15 }}
                    />
                  </div>
                </Col>
              </Row>
              <div style={{ marginBottom: 8 }}>
                <Text strong>反馈构成</Text>
              </div>
              <Table
                size="small"
                pagination={false}
                rowKey="name"
                locale={{ emptyText: '暂无消息反馈数据' }}
                dataSource={[
                  { name: 'LIKE', count: dashboard.summary.likes, ratio: feedbackTotal > 0 ? (dashboard.summary.likes / feedbackTotal) : 0 },
                  { name: 'DISLIKE', count: dashboard.summary.dislikes, ratio: feedbackTotal > 0 ? (dashboard.summary.dislikes / feedbackTotal) : 0 },
                ]}
                columns={[
                  { title: '类型', dataIndex: 'name', key: 'name' },
                  { title: '数量', dataIndex: 'count', key: 'count', width: 80 },
                  {
                    title: '占比',
                    dataIndex: 'ratio',
                    key: 'ratio',
                    width: 110,
                    render: (value: number) => `${(value * 100).toFixed(1)}%`,
                  },
                ]}
              />
              <div style={{ marginTop: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                  <Text type="secondary">反馈覆盖率（反馈/助手消息）</Text>
                  <Text strong>{(feedbackCoverageRate * 100).toFixed(1)}%</Text>
                </div>
                <Progress percent={Number((feedbackCoverageRate * 100).toFixed(1))} strokeColor="#1677ff" />
              </div>
            </Card>
          </Col>
          <Col xs={24} xl={12}>
            <Card title={isPersonalMode ? '我的稳定性统计' : '稳定性统计'} bordered={false} loading={loading} style={equalPanelCardStyle} bodyStyle={panelCardBodyStyle}>
              <Row gutter={[10, 10]} style={{ marginBottom: 10 }}>
                <Col xs={24} sm={8}>
                  <div style={statTileStyle}>
                    <Statistic title="最近异常" value={recentErrorCount} valueStyle={{ fontSize: 22, lineHeight: 1.15 }} />
                  </div>
                </Col>
                <Col xs={24} sm={8}>
                  <div style={statTileStyle}>
                    <Statistic title="异常节点数" value={nodeErrorTop.length} valueStyle={{ fontSize: 22, lineHeight: 1.15 }} />
                  </div>
                </Col>
                <Col xs={24} sm={8}>
                  <div style={statTileStyle}>
                    <Statistic title="均次工具调用" value={avgToolCallsPerExecution} precision={2} valueStyle={{ fontSize: 22, lineHeight: 1.15 }} />
                  </div>
                </Col>
              </Row>

              <div style={{ marginBottom: 8 }}>
                <Text strong>节点异常 TOP</Text>
              </div>
              <Table
                size="small"
                rowKey={(row: TopNode) => row.node_name}
                pagination={false}
                locale={{ emptyText: '暂无异常节点' }}
                dataSource={nodeErrorTop}
                columns={[
                  { title: '节点', dataIndex: 'node_name', key: 'node_name', ellipsis: true },
                  { title: '异常', dataIndex: 'error_count', key: 'error_count', width: 70 },
                  { title: '执行', dataIndex: 'executions', key: 'executions', width: 70 },
                ]}
              />

              <div style={{ margin: '12px 0 8px' }}>
                <Text strong>慢专家 TOP</Text>
              </div>
              <Table
                size="small"
                rowKey={(row: TopAgent) => row.agent_id || row.agent_name}
                pagination={false}
                locale={{ emptyText: '暂无执行数据' }}
                dataSource={slowAgentTop}
                columns={[
                  { title: '专家', dataIndex: 'agent_name', key: 'agent_name', ellipsis: true },
                  {
                    title: '平均耗时',
                    dataIndex: 'avg_duration_ms',
                    key: 'avg_duration_ms',
                    width: 92,
                    render: (value: number) => `${Math.round(value || 0)}ms`,
                  },
                  { title: '执行', dataIndex: 'executions', key: 'executions', width: 70 },
                ]}
              />
            </Card>
          </Col>
        </Row>
      </div>

      <Drawer
        title="执行详情"
        placement="right"
        width={560}
        open={!!selectedExecution}
        onClose={() => setSelectedExecution(null)}
      >
        {selectedExecution && (
          <Descriptions bordered column={1} size="small">
            <Descriptions.Item label="执行时间">
              {dayjs(selectedExecution.created_at).format('YYYY-MM-DD HH:mm:ss')}
            </Descriptions.Item>
            <Descriptions.Item label="节点">{selectedExecution.node_name}</Descriptions.Item>
            <Descriptions.Item label="专家">{selectedExecution.agent_name || '-'}</Descriptions.Item>
            <Descriptions.Item label="租户">{selectedExecution.user_id || '-'}</Descriptions.Item>
            <Descriptions.Item label="来源">
              <Tag>{SOURCE_LABEL[selectedExecution.auth_source || 'unknown'] || selectedExecution.auth_source || '未知'}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="API Key">{selectedExecution.api_key_id || '-'}</Descriptions.Item>
            <Descriptions.Item label="状态">
              <Tag color={selectedExecution.status === 'success' ? 'green' : 'red'}>
                {selectedExecution.status}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="会话 ID">{selectedExecution.session_id || '-'}</Descriptions.Item>
            <Descriptions.Item label="请求 ID">{selectedExecution.request_id || '-'}</Descriptions.Item>
            <Descriptions.Item label="耗时">{Math.round(selectedExecution.duration_ms || 0)}ms</Descriptions.Item>
            <Descriptions.Item label="Token">
              输入 {selectedExecution.input_tokens} / 输出 {selectedExecution.output_tokens}
            </Descriptions.Item>
            <Descriptions.Item label="工具调用">{selectedExecution.tool_calls_count}</Descriptions.Item>
            <Descriptions.Item label="错误详情">
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                {selectedExecution.error_message || '无'}
              </pre>
            </Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>
    </div>
  );
};

export default AuditLogView;
