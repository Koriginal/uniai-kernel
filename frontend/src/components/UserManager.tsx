import React, { useState, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, Checkbox, message, Tag, Space, Typography, Card } from 'antd';
import { 
  UserOutlined, 
  UserAddOutlined, 
  DeleteOutlined, 
  SafetyOutlined 
} from '@ant-design/icons';
import axios from 'axios';

const { Title, Text } = Typography;

const UserManager: React.FC = () => {
    const [loading, setLoading] = useState(false);
    const [users, setUsers] = useState<any[]>([]);
    const [isModalVisible, setIsModalVisible] = useState(false);
    const [form] = Form.useForm();

    const token = localStorage.getItem('token');
    const api = axios.create({
        headers: { Authorization: `Bearer ${token}` }
    });

    const fetchUsers = async () => {
        setLoading(true);
        try {
            const res = await api.get('/api/v1/users/');
            setUsers(res.data);
        } catch (error: any) {
            message.error(error.response?.data?.detail || "加载用户失败");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchUsers();
    }, []);

    const handleCreate = async (values: any) => {
        try {
            await api.post('/api/v1/users/', values);
            message.success("用户创建成功");
            setIsModalVisible(false);
            form.resetFields();
            fetchUsers();
        } catch (error: any) {
            message.error(error.response?.data?.detail || "创建失败");
        }
    };

    const handleDelete = async (id: string) => {
        try {
            await api.delete(`/api/v1/users/${id}`);
            message.success("用户已删除");
            fetchUsers();
        } catch (error: any) {
            message.error(error.response?.data?.detail || "操作失败");
        }
    };

    const columns = [
        {
            title: '用户名',
            dataIndex: 'username',
            key: 'username',
            render: (text: string) => <Text strong>{text}</Text>,
        },
        {
            title: '邮箱',
            dataIndex: 'email',
            key: 'email',
        },
        {
            title: '角色',
            key: 'role',
            render: (_: any, record: any) => (
                <Space>
                    {record.is_admin ? <Tag color="gold" icon={<SafetyOutlined />}>管理员</Tag> : <Tag color="blue">普通用户</Tag>}
                    {!record.is_active && <Tag color="red">已禁用</Tag>}
                </Space>
            ),
        },
        {
            title: '操作',
            key: 'action',
            render: (_: any, record: any) => (
                <Button 
                    type="link" 
                    danger 
                    icon={<DeleteOutlined />} 
                    disabled={record.email === 'admin@uniai.local'} // 防止删除种子管理员
                    onClick={() => Modal.confirm({
                        title: '确定要删除此用户吗？',
                        content: '删除后，该用户的所有数据都将无法访问。',
                        onOk: () => handleDelete(record.id)
                    })}
                >
                    删除
                </Button>
            ),
        }
    ];

    return (
        <div style={{ padding: '24px', background: '#fff', minHeight: '100%' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                <div>
                    <Title level={4}><UserOutlined /> 用户管理</Title>
                    <Text type="secondary">管理 UniAI Kernel 的多租户用户，只有管理员有权操作。</Text>
                </div>
                <Button type="primary" icon={<UserAddOutlined />} onClick={() => setIsModalVisible(true)}>
                    新建用户
                </Button>
            </div>

            <Card bordered={false} bodyStyle={{ padding: 0 }}>
                <Table 
                    columns={columns} 
                    dataSource={users} 
                    rowKey="id" 
                    loading={loading}
                    pagination={{ pageSize: 15 }}
                />
            </Card>

            <Modal
                title="创建新用户"
                visible={isModalVisible}
                onCancel={() => setIsModalVisible(false)}
                onOk={() => form.submit()}
                destroyOnClose
            >
                <Form form={form} layout="vertical" onFinish={handleCreate}>
                    <Form.Item 
                        name="email" 
                        label="邮箱 (登录账号)" 
                        rules={[{ required: true, type: 'email', message: '请输入有效的邮箱' }]}
                    >
                        <Input placeholder="user@example.com" />
                    </Form.Item>
                    <Form.Item 
                        name="username" 
                        label="显示名称" 
                        rules={[{ required: true, message: '请输入用户名' }]}
                    >
                        <Input placeholder="张三" />
                    </Form.Item>
                    <Form.Item 
                        name="password" 
                        label="初始密码" 
                        rules={[{ required: true, min: 6, message: '密码至少 6 位' }]}
                    >
                        <Input.Password placeholder="******" />
                    </Form.Item>
                    <Form.Item name="is_admin" valuePropName="checked">
                        <Checkbox>设为管理员</Checkbox>
                    </Form.Item>
                </Form>
            </Modal>
        </div>
    );
};

export default UserManager;
