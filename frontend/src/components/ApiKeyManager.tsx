import React, { useState, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, message, Tag, Space, Typography, Card, Tooltip } from 'antd';
import { 
  KeyOutlined, 
  PlusOutlined, 
  DeleteOutlined, 
  CopyOutlined, 
  SafetyCertificateOutlined 
} from '@ant-design/icons';
import type { AxiosInstance } from 'axios';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';

dayjs.extend(relativeTime);

const { Title, Text, Paragraph } = Typography;

interface ApiKeyManagerProps {
    api: AxiosInstance;
    user: any;
}

const ApiKeyManager: React.FC<ApiKeyManagerProps> = ({ api, user }) => {
    const [loading, setLoading] = useState(true);
    const [keys, setKeys] = useState<any[]>([]);
    const [isModalVisible, setIsModalVisible] = useState(false);
    const [form] = Form.useForm();
    const [newKeyDetails, setNewKeyDetails] = useState<any>(null);

    // 移除硬编码：现在使用 props 中的 user.id 或后端自动关联 Token 身份

    const fetchKeys = async () => {
        setLoading(true);
        try {
            const res = await api.get(`/api/v1/user/api-keys/`);
            setKeys(res.data);
        } catch (error) {
            message.error("加载 API 秘钥失败");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchKeys();
    }, []);

    const handleCreate = async (values: any) => {
        try {
            const res = await api.post('/api/v1/user/api-keys/', {
                ...values
            });
            message.success("API 秘钥创建成功");
            setIsModalVisible(false);
            form.resetFields();
            setNewKeyDetails(res.data); // 展示给用户看一次
            fetchKeys();
        } catch (error) {
            message.error("创建失败");
        }
    };

    const handleDelete = async (id: string) => {
        try {
            await api.delete(`/api/v1/user/api-keys/${id}`);
            message.success("秘钥已吊销");
            fetchKeys();
        } catch (error) {
            message.error("操作失败");
        }
    };

    const copyToClipboard = (text: string) => {
        navigator.clipboard.writeText(text);
        message.success("已复制到剪贴板");
    };

    const columns = [
        {
            title: '名称',
            dataIndex: 'name',
            key: 'name',
            render: (text: string) => <Text strong>{text}</Text>,
        },
        {
            title: '秘钥',
            dataIndex: 'key',
            key: 'key',
            render: (key: string) => (
                <Space>
                    <Text code>{key.substring(0, 10)}****************{key.substring(key.length - 4)}</Text>
                    <Tooltip title="复制完整秘钥">
                        <Button type="link" size="small" icon={<CopyOutlined />} onClick={() => copyToClipboard(key)} />
                    </Tooltip>
                </Space>
            ),
        },
        {
            title: '状态',
            dataIndex: 'is_active',
            key: 'is_active',
            render: (active: boolean) => (
                <Tag color={active ? 'green' : 'red'}>{active ? '有效' : '已禁用'}</Tag>
            ),
        },
        {
            title: '最后使用时间',
            dataIndex: 'last_used_at',
            key: 'last_used_at',
            render: (text: string) => text ? dayjs(text).fromNow() : '从未使用',
        },
        {
            title: '创建时间',
            dataIndex: 'created_at',
            key: 'created_at',
            render: (text: string) => dayjs(text).format('YYYY-MM-DD HH:mm'),
        },
        {
            title: '操作',
            key: 'action',
            render: (_: any, record: any) => (
                <Button 
                    type="link" 
                    danger 
                    icon={<DeleteOutlined />} 
                    onClick={() => Modal.confirm({
                        title: '确定要吊销此 API 秘钥吗？',
                        content: '删除后，所有使用此秘钥的应用将无法访问内核。',
                        onOk: () => handleDelete(record.id)
                    })}
                >
                    吊销
                </Button>
            ),
        }
    ];

    return (
        <div style={{ padding: '24px', background: '#fff', minHeight: '100%' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                <div>
                    <Title level={4}><KeyOutlined /> API 秘钥管理</Title>
                    <Text type="secondary">用户 {user?.username} 的秘钥。使用 API 秘钥从 Dify、LobeChat 等第三方应用接入 UniAI-Kernel 能力。</Text>
                </div>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalVisible(true)}>
                    创建新秘钥
                </Button>
            </div>

            <Card bordered={false} bodyStyle={{ padding: 0 }}>
                <Table 
                    columns={columns} 
                    dataSource={keys} 
                    rowKey="id" 
                    loading={loading}
                    pagination={false}
                />
            </Card>

            {/* 创建弹窗 */}
            <Modal
                title="创建 API 秘钥"
                visible={isModalVisible}
                onCancel={() => setIsModalVisible(false)}
                onOk={() => form.submit()}
                destroyOnClose
            >
                <Form form={form} layout="vertical" onFinish={handleCreate}>
                    <Form.Item 
                        name="name" 
                        label="秘钥名称" 
                        rules={[{ required: true, message: '请输入名称' }]}
                        initialValue="Default Key"
                    >
                        <Input placeholder="例如：Dify 集成、测试 Key" maxLength={32} />
                    </Form.Item>
                    <Text type="secondary" style={{ fontSize: '12px' }}>
                        API 基地址: <Text code>{window.location.origin}/v1</Text>
                    </Text>
                </Form>
            </Modal>

            {/* 成功展示弹窗 */}
            <Modal
                title={<span><SafetyCertificateOutlined style={{ color: '#52c41a' }} /> 秘钥创建成功</span>}
                visible={!!newKeyDetails}
                onCancel={() => setNewKeyDetails(null)}
                footer={[<Button key="close" type="primary" onClick={() => setNewKeyDetails(null)}>我已保存</Button>]}
            >
                <Paragraph>
                    请务必立即复制并保存您的 API 秘钥。出于安全考虑，<Text strong type="danger">您之后将无法再次查看完整秘钥</Text>。
                </Paragraph>
                <Card size="small" style={{ background: '#f6f8fa', border: '1px solid #d0d7de' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Text strong style={{ fontSize: '16px', fontFamily: 'monospace' }}>
                            {newKeyDetails?.key}
                        </Text>
                        <Button type="link" icon={<CopyOutlined />} onClick={() => copyToClipboard(newKeyDetails?.key)} />
                    </div>
                </Card>
            </Modal>
        </div>
    );
};

export default ApiKeyManager;
