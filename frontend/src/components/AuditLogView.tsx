import React, { useEffect, useMemo, useState } from 'react';
import {
  Card,
  Col,
  Descriptions,
  Drawer,
  Empty,
  Progress,
  Row,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  List,
} from 'antd';
import { Column, Line, Pie } from '@ant-design/plots';
import {
  BarChartOutlined,
  ClockCircleOutlined,
  MessageOutlined,
  PartitionOutlined,
  RobotOutlined,
  ThunderboltOutlined,
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
}

interface DashboardData {
  summary: DashboardSummary;
  daily_activity: DailyActivity[];
  top_agents: TopAgent[];
  top_nodes: TopNode[];
  recent_executions: RecentExecution[];
}

const defaultData: DashboardData = {
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
  },
  daily_activity: [],
  top_agents: [],
  top_nodes: [],
  recent_executions: [],
};

const AuditLogView: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [dashboard, setDashboard] = useState<DashboardData>(defaultData);
  const [selectedExecution, setSelectedExecution] = useState<RecentExecution | null>(null);

  useEffect(() => {
    const fetchDashboard = async () => {
      setLoading(true);
      try {
        const res = await axios.get('/api/v1/audit/dashboard?days=7');
        setDashboard({
          ...defaultData,
          ...res.data,
          summary: { ...defaultData.summary, ...(res.data?.summary || {}) },
          daily_activity: res.data?.daily_activity || [],
          top_agents: res.data?.top_agents || [],
          top_nodes: res.data?.top_nodes || [],
          recent_executions: res.data?.recent_executions || [],
        });
      } catch (err) {
        console.error('Failed to fetch audit dashboard', err);
      } finally {
        setLoading(false);
      }
    };

    fetchDashboard();
  }, []);

  const activitySeries = useMemo(
    () =>
      (dashboard.daily_activity || []).flatMap((item) => [
        { date: item.date, type: '会话', value: item.sessions },
        { date: item.date, type: '消息', value: item.messages },
        { date: item.date, type: '节点执行', value: item.executions },
      ]),
    [dashboard.daily_activity]
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

  const lineConfig = {
    data: activitySeries,
    xField: 'date',
    yField: 'value',
    seriesField: 'type',
    smooth: true,
    point: { size: 4 },
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

  const agentColumnConfig = {
    data: dashboard.top_agents || [],
    xField: 'agent_name',
    yField: 'executions',
    label: false,
    color: '#1677ff',
  };

  const columns = [
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
      title: '工具调用',
      dataIndex: 'tool_calls_count',
      key: 'tool_calls_count',
      width: 100,
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
    <div style={{ padding: 24, background: '#f5f7fb', minHeight: '100%', overflow: 'auto' }}>
      <Space direction="vertical" size={4} style={{ marginBottom: 24 }}>
        <Title level={4} style={{ margin: 0 }}>
          <BarChartOutlined /> 运行审计总览
        </Title>
        <Text type="secondary">基于当前会话、消息与图执行遥测数据的近 7 天观测结果。</Text>
      </Space>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card bordered={false} loading={loading}>
            <Statistic title="新增会话" value={dashboard.summary.total_sessions} prefix={<ThunderboltOutlined style={{ color: '#1677ff' }} />} />
            <Text type="secondary">活跃中 {dashboard.summary.active_sessions}</Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card bordered={false} loading={loading}>
            <Statistic title="消息总量" value={dashboard.summary.total_messages} prefix={<MessageOutlined style={{ color: '#52c41a' }} />} />
            <Text type="secondary">用户 {dashboard.summary.user_messages} / 助手 {dashboard.summary.assistant_messages}</Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card bordered={false} loading={loading}>
            <Statistic title="节点执行" value={dashboard.summary.total_executions} prefix={<PartitionOutlined style={{ color: '#fa8c16' }} />} />
            <Text type="secondary">工具调用 {dashboard.summary.tool_calls}</Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card bordered={false} loading={loading}>
            <Statistic title="平均耗时" value={dashboard.summary.avg_duration_ms} precision={0} suffix="ms" prefix={<ClockCircleOutlined style={{ color: '#722ed1' }} />} />
            <Text type="secondary">错误率 {(dashboard.summary.error_rate * 100).toFixed(1)}%</Text>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} lg={16}>
          <Card title="运行活跃趋势" bordered={false} loading={loading}>
            <div style={{ height: 320 }}>
              {activitySeries.length > 0 ? <Line {...lineConfig} /> : <Empty description="近 7 天暂无活跃数据" />}
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="节点分布" bordered={false} loading={loading}>
            <div style={{ height: 320 }}>
              {nodeChartData.length > 0 ? <Pie {...pieConfig} /> : <Empty description="暂无节点执行数据" />}
            </div>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} lg={14}>
          <Card title="专家执行排名" bordered={false} loading={loading}>
            <div style={{ height: 280 }}>
              {dashboard.top_agents.length > 0 ? <Column {...agentColumnConfig} /> : <Empty description="暂无专家执行数据" />}
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="用户反馈" bordered={false} loading={loading}>
            {feedbackTotal > 0 ? (
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <Statistic title="反馈总数" value={feedbackTotal} prefix={<RobotOutlined style={{ color: '#1677ff' }} />} />
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                    <Text>正向反馈占比</Text>
                    <Text strong>{(approvalRate * 100).toFixed(1)}%</Text>
                  </div>
                  <Progress percent={Number((approvalRate * 100).toFixed(1))} strokeColor="#52c41a" />
                </div>
                <Space size={12}>
                  <Tag color="success">LIKE {dashboard.summary.likes}</Tag>
                  <Tag color="error">DISLIKE {dashboard.summary.dislikes}</Tag>
                </Space>
              </Space>
            ) : (
              <Empty description="暂无消息反馈数据" />
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <Card title={<span><ToolOutlined /> 热点节点</span>} bordered={false} loading={loading}>
            <List
              dataSource={dashboard.top_nodes}
              locale={{ emptyText: <Empty description="暂无节点数据" /> }}
              renderItem={(item, index) => (
                <List.Item>
                  <Space direction="vertical" size={2} style={{ flex: 1 }}>
                    <Space>
                      <Tag color={index < 3 ? 'gold' : 'blue'}>{index + 1}</Tag>
                      <Text strong>{item.node_name}</Text>
                    </Space>
                    <Text type="secondary">
                      {item.executions} 次执行，平均 {Math.round(item.avg_duration_ms || 0)}ms，错误 {item.error_count}
                    </Text>
                  </Space>
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} lg={16}>
          <Card title="最近执行记录" bordered={false} loading={loading}>
            <Table
              columns={columns}
              dataSource={dashboard.recent_executions}
              rowKey="id"
              pagination={{ pageSize: 8 }}
              size="small"
              scroll={{ x: 760 }}
            />
          </Card>
        </Col>
      </Row>

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
