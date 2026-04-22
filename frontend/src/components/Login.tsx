import React, { useState } from 'react';
import { Card, Form, Input, Button, Typography, message, Space } from 'antd';
import { 
  UserOutlined, 
  LockOutlined, 
  SafetyCertificateOutlined
} from '@ant-design/icons';
import axios from 'axios';
import BrandCatIcon from './BrandCatIcon';

const { Title, Text } = Typography;

interface LoginProps {
    onLoginSuccess: (token: string, user: any) => void;
}

const Login: React.FC<LoginProps> = ({ onLoginSuccess }) => {
    const [loading, setLoading] = useState(false);

    const onFinish = async (values: any) => {
        setLoading(true);
        try {
            const formData = new FormData();
            formData.append('username', values.account); // OAuth2PasswordRequestForm expects username
            formData.append('password', values.password);

            const res = await axios.post('/api/v1/auth/login', formData);
            const { access_token } = res.data;
            
            // 获取用户信息
            const userRes = await axios.get('/api/v1/auth/me', {
                headers: { Authorization: `Bearer ${access_token}` }
            });

            message.success('登录成功');
            onLoginSuccess(access_token, userRes.data);
        } catch (error: any) {
            console.error("Login failed:", error);
            message.error(error.response?.data?.detail || '登录失败，请检查邮箱和密码');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={{ 
            height: '100vh', width: '100vw', 
            display: 'flex', justifyContent: 'center', alignItems: 'center',
            background: 'linear-gradient(135deg, #1890ff 0%, #001529 100%)',
            overflow: 'hidden'
        }}>
            <Card style={{ width: 400, borderRadius: 12, boxShadow: '0 8px 24px rgba(0,0,0,0.2)' }}>
                <div style={{ textAlign: 'center', marginBottom: 32 }}>
                    <div style={{ marginBottom: 12 }}>
                        <BrandCatIcon size={52} color="#1890ff" strokeWidth={1.8} />
                    </div>
                    <Title level={3} style={{ margin: 0 }}>UniAI Kernel</Title>
                    <Text type="secondary">智能体开发基座 - 终端登录</Text>
                </div>

                <Form
                    name="login"
                    onFinish={onFinish}
                    layout="vertical"
                    size="large"
                >
                    <Form.Item
                        name="account"
                        rules={[{ required: true, message: '请输入邮箱、用户名或手机号' }]}
                    >
                        <Input prefix={<UserOutlined />} placeholder="邮箱 / 用户名 / 手机号" />
                    </Form.Item>

                    <Form.Item
                        name="password"
                        rules={[{ required: true, message: '请输入密码' }]}
                    >
                        <Input.Password prefix={<LockOutlined />} placeholder="******" />
                    </Form.Item>

                    <Form.Item>
                        <Button type="primary" htmlType="submit" loading={loading} block>
                            登录系统
                        </Button>
                    </Form.Item>
                </Form>

                <div style={{ textAlign: 'center', marginTop: 16 }}>
                    <Space>
                        <SafetyCertificateOutlined style={{ color: '#52c41a' }} />
                        <Text type="secondary" style={{ fontSize: 12 }}>安全加密传输已开启</Text>
                    </Space>
                </div>
            </Card>
        </div>
    );
};

export default Login;
