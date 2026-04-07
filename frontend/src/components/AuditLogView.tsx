import React, { useState, useEffect } from 'react';
import { Table, Card, Row, Col, Statistic, Tag, Typography, Button, Drawer, Descriptions, Space, Empty, List } from 'antd';
import { Area, Pie } from '@ant-design/plots';
import { 
  BarChartOutlined, 
  HistoryOutlined, 
  ThunderboltOutlined, 
  DollarOutlined,
  EyeOutlined,
  ToolOutlined
} from '@ant-design/icons';
import axios from 'axios';
import dayjs from 'dayjs';

const { Title, Text } = Typography;

const AuditLogView: React.FC = () => {
    const [loading, setLoading] = useState(true);
    const [stats, setStats] = useState<any>(null);
    const [logs, setLogs] = useState<any[]>([]);
    const [selectedLog, setSelectedLog] = useState<any>(null);

    const fetchData = async () => {
        setLoading(true);
        // 分别请求，互不干扰
        const fetchStats = async () => {
            try {
                const res = await axios.get('/api/v1/audit/stats?days=7');
                setStats(res.data);
            } catch (err) {
                console.error("Failed to fetch stats", err);
            }
        };

        const fetchLogs = async () => {
            try {
                const res = await axios.get('/api/v1/audit/actions?limit=50');
                setLogs(res.data);
            } catch (err) {
                console.error("Failed to fetch logs", err);
            }
        };

        await Promise.all([fetchStats(), fetchLogs()]);
        setLoading(false);
    };

    useEffect(() => {
        fetchData();
    }, []);

    const columns = [
        {
            title: '时间',
            dataIndex: 'created_at',
            key: 'created_at',
            render: (text: string) => dayjs(text).format('MM-DD HH:mm:ss'),
            width: 140,
        },
        {
            title: '工具/行动',
            dataIndex: 'action_name',
            key: 'action_name',
            render: (text: string) => <Tag color="blue">{text}</Tag>,
        },
        {
            title: '状态',
            dataIndex: 'status',
            key: 'status',
            render: (status: string) => (
                <Tag color={status === 'success' ? 'green' : 'red'}>
                    {status?.toUpperCase() || 'UNKNOWN'}
                </Tag>
            ),
        },
        {
            title: '耗时',
            dataIndex: 'duration_ms',
            key: 'duration_ms',
            render: (ms: number) => `${(ms || 0).toFixed(0)}ms`,
        },
        {
            title: 'Tokens',
            dataIndex: 'total_tokens',
            key: 'total_tokens',
            render: (val: number) => <Text strong>{val || 0}</Text>,
        },
        {
            title: '操作',
            key: 'action',
            render: (_: any, record: any) => (
                <Button type="link" icon={<EyeOutlined />} onClick={() => setSelectedLog(record)}>
                    详情
                </Button>
            ),
        }
    ];

    const chartConfig = {
        data: stats?.daily || [],
        xField: 'date',
        yField: 'tokens',
        smooth: true,
        areaStyle: {
            fill: 'l(270) 0:#ffffff 0.5:#7ec2f3 1:#1890ff',
        },
    };

    const pieConfig = {
        appendPadding: 10,
        data: stats?.by_agent || [],
        angleField: 'tokens',
        colorField: 'agent_id',
        radius: 0.8,
        label: {
            type: 'outer',
            content: '{name} {percentage}',
        },
        interactions: [{ type: 'element-active' }],
    };

    return (
        <div style={{ padding: '24px', background: '#f5f6fa', flex: 1, overflow: 'auto' }}>
            <Title level={4} style={{ marginBottom: 24 }}>
                <BarChartOutlined /> 使用统计与审计日志
            </Title>

            {/* 汇总统计卡片 */}
            <Row gutter={16} style={{ marginBottom: 24 }}>
                <Col span={6}>
                    <Card bordered={false} hoverable>
                        <Statistic
                            title="累计调用次数"
                            value={stats?.summary?.total_calls || 0}
                            prefix={<ThunderboltOutlined style={{ color: '#1890ff' }} />}
                        />
                    </Card>
                </Col>
                <Col span={6}>
                    <Card bordered={false} hoverable>
                        <Statistic
                            title="Token 消耗总量"
                            value={stats?.summary?.total_tokens || 0}
                            prefix={<HistoryOutlined style={{ color: '#52c41a' }} />}
                        />
                    </Card>
                </Col>
                <Col span={6}>
                    <Card bordered={false} hoverable>
                        <Statistic
                            title="平均响应延迟"
                            value={stats?.summary?.avg_latency || 0}
                            precision={0}
                            suffix="ms"
                            prefix={<ThunderboltOutlined style={{ color: '#faad14' }} />}
                        />
                    </Card>
                </Col>
                <Col span={6}>
                    <Card bordered={false} hoverable>
                        <Statistic
                            title="预估总成本"
                            value={stats?.summary?.total_cost || 0}
                            precision={4}
                            prefix={<DollarOutlined style={{ color: '#f5222d' }} />}
                            suffix="USD"
                        />
                    </Card>
                </Col>
            </Row>

            <Row gutter={16} style={{ marginBottom: 24 }}>
                {/* 使用趋势图表 */}
                <Col span={16}>
                    <Card title="Token 消耗趋势 (近 7 天)" bordered={false}>
                        <div style={{ height: 350 }}>
                            {stats?.daily?.length > 0 ? <Area {...chartConfig} /> : <Empty description="暂无趋势数据" />}
                        </div>
                    </Card>
                </Col>
                {/* 智能体分布 */}
                <Col span={8}>
                    <Card title="智能体 Token 分布" bordered={false}>
                        <div style={{ height: 350 }}>
                            {stats?.by_agent?.length > 0 ? <Pie {...pieConfig} /> : <Empty description="暂无分布数据" />}
                        </div>
                    </Card>
                </Col>
            </Row>

            <Row gutter={16} style={{ marginBottom: 24 }}>
                {/* 热门工具排行 */}
                <Col span={8}>
                    <Card title={<span><ToolOutlined /> 热门行动排行</span>} bordered={false}>
                        <List
                            dataSource={stats?.top_actions || []}
                            renderItem={(item: any, index: number) => (
                                <List.Item>
                                    <Space>
                                        <Tag color={index < 3 ? 'gold' : 'blue'}>{index + 1}</Tag>
                                        <Text strong>{item.name}</Text>
                                    </Space>
                                    <Text type="secondary">{item.calls} 次调用</Text>
                                </List.Item>
                            )}
                        />
                    </Card>
                </Col>
                {/* 审计日志列表 */}
                <Col span={16}>
                    <Card title={<span><HistoryOutlined /> 最近行动日志</span>} bordered={false}>
                        <Table
                            columns={columns}
                            dataSource={logs}
                            rowKey="id"
                            loading={loading}
                            pagination={{ pageSize: 8 }}
                            size="small"
                        />
                    </Card>
                </Col>
            </Row>

            {/* 日志详情抽屉 */}
            <Drawer
                title="日志详情"
                placement="right"
                width={600}
                onClose={() => setSelectedLog(null)}
                open={!!selectedLog}
            >
                {selectedLog && (
                    <Descriptions column={1} bordered size="small">
                        <Descriptions.Item label="Action ID">{selectedLog.id}</Descriptions.Item>
                        <Descriptions.Item label="Session ID">{selectedLog.session_id || '-'}</Descriptions.Item>
                        <Descriptions.Item label="智能体 ID">{selectedLog.agent_id || '-'}</Descriptions.Item>
                        <Descriptions.Item label="行动名称">{selectedLog.action_name}</Descriptions.Item>
                        <Descriptions.Item label="执行状态">
                            <Tag color={selectedLog.status === 'success' ? 'green' : 'red'}>
                                {selectedLog.status?.toUpperCase() || 'UNKNOWN'}
                            </Tag>
                        </Descriptions.Item>
                        <Descriptions.Item label="Token 详情">
                            <Space>
                                <Tag>Prompt: {selectedLog.request_tokens}</Tag>
                                <Tag>Completion: {selectedLog.response_tokens}</Tag>
                                <Tag color="blue">Total: {selectedLog.total_tokens}</Tag>
                            </Space>
                        </Descriptions.Item>
                        <Descriptions.Item label="成本耗时">
                            ${(selectedLog.cost || 0).toFixed(4)} / {(selectedLog.duration_ms || 0).toFixed(0)}ms
                        </Descriptions.Item>
                        <Descriptions.Item label="输入参数">
                            <pre style={{ background: '#f5f5f5', padding: 8, borderRadius: 4, maxHeight: 150, overflow: 'auto' }}>
                                {JSON.stringify(selectedLog.input_params, null, 2)}
                            </pre>
                        </Descriptions.Item>
                        <Descriptions.Item label="输出结果摘要">
                            <pre style={{ background: '#f5f5f5', padding: 8, borderRadius: 4, maxHeight: 300, overflow: 'auto', whiteSpace: 'pre-wrap' }}>
                                {selectedLog.output_result}
                            </pre>
                        </Descriptions.Item>
                    </Descriptions>
                )}
            </Drawer>
        </div>
    );
};

export default AuditLogView;
