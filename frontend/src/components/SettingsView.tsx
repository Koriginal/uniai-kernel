import React, { useState, useEffect } from 'react';
import { 
  Card, Typography, Button, 
  Space, Tag, Form, Input, message, Slider, Select, Tabs, Divider, Row, Col, Avatar, Progress, Statistic
} from 'antd';
import { 
  ThunderboltOutlined, EditOutlined, SaveOutlined, 
  CloseOutlined, BulbOutlined,
  GlobalOutlined, UserOutlined, ArrowLeftOutlined,
  SafetyCertificateOutlined,
  SafetyOutlined, DashboardOutlined, ProfileOutlined,
  NodeIndexOutlined, HistoryOutlined
} from '@ant-design/icons';
import type { AxiosInstance } from 'axios';

const { Title, Text, Paragraph } = Typography;

interface SettingsCenterProps {
  user: any;
  api: AxiosInstance;
  modelConfigs: any[];
  onRefresh: () => void;
  onBack: () => void;
}

const SettingsCenter: React.FC<SettingsCenterProps> = ({ user, api, modelConfigs, onRefresh, onBack }) => {
  const [activeTab, setActiveTab] = useState('collaboration');
  const [editingPreferences, setEditingPreferences] = useState(false);
  const [loading, setLoading] = useState(false);
  const [prefForm] = Form.useForm();
  const [profileForm] = Form.useForm();

  useEffect(() => {
    if (user) {
      prefForm.setFieldsValue(user.preferences || {});
      profileForm.setFieldsValue({
        username: user.username,
        email: user.email,
        bio: user.bio,
        avatar: user.avatar
      });
    }
  }, [user, prefForm, profileForm]);

  const handleUpdatePreferences = async (values: any) => {
    setLoading(true);
    try {
      await api.patch('/api/v1/users/me', {
        preferences: values
      });
      message.success('系统设置已更新');
      setEditingPreferences(false);
      onRefresh();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '设置保存失败');
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateProfile = async (values: any) => {
    setLoading(true);
    try {
      await api.patch('/api/v1/users/me', values);
      message.success('个人资料已更新');
      onRefresh();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '保存失败');
    } finally {
      setLoading(false);
    }
  };

  const allModels = modelConfigs.flatMap(p => 
    (p.models || []).map((m: any) => ({
      label: `${m.model_name} (${p.display_name})`,
      value: m.id,
    }))
  );

  const langOptions = [
    { label: '自动检测 (Auto)', value: 'auto' },
    { label: '简体中文 (Chinese)', value: 'zh-CN' },
    { label: '英语 (English)', value: 'en-US' },
    { label: '日语 (Japanese)', value: 'ja-JP' },
  ];

  // --- Sub-renderers ---

  const renderDashboard = () => (
    <div className="settings-section">
      <Title level={3}>使用概览</Title>
      <Paragraph type="secondary">查看您的资源消耗与智能体互动摘要。</Paragraph>
      
      <Row gutter={24} style={{ marginTop: 24 }}>
        <Col span={8}>
          <Card bordered={false} style={{ boxShadow: '0 2px 8px rgba(0,0,0,0.05)', borderRadius: 12 }}>
            <Statistic title="本月 Token 消耗" value={125430} prefix={<NodeIndexOutlined />} />
            <Progress percent={65} size="small" status="active" />
          </Card>
        </Col>
        <Col span={8}>
          <Card bordered={false} style={{ boxShadow: '0 2px 8px rgba(0,0,0,0.05)', borderRadius: 12 }}>
            <Statistic title="智能体互动次数" value={842} prefix={<HistoryOutlined />} />
          </Card>
        </Col>
        <Col span={8}>
          <Card bordered={false} style={{ boxShadow: '0 2px 8px rgba(0,0,0,0.05)', borderRadius: 12 }}>
            <Statistic title="对话会话总数" value={21} prefix={<ProfileOutlined />} />
          </Card>
        </Col>
      </Row>

      <Card 
        title="活跃动态" 
        style={{ marginTop: 24, borderRadius: 12, border: '1px solid #f0f0f0' }}
        bordered={false}
      >
        <Text type="secondary">正在集成审计日志流，实时监控 AI 内核动态...</Text>
      </Card>
    </div>
  );

  const renderAccount = () => (
    <div className="settings-section">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>个人中心</Title>
          <Text type="secondary">管理您的数字身份与账户公开信息。</Text>
        </div>
      </div>

      <Form 
        form={profileForm} 
        layout="vertical" 
        onFinish={handleUpdateProfile}
      >
        <Card bordered={false} style={{ background: '#f9f9f9', borderRadius: 16, marginBottom: 24 }}>
           <Row gutter={40} align="middle">
             <Col>
               <Avatar size={100} icon={<UserOutlined />} src={user.avatar} style={{ border: '4px solid #fff', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }} />
             </Col>
             <Col flex="auto">
               <Title level={4} style={{ margin: 0 }}>{user.username}</Title>
               <Text type="secondary">{user.email}</Text>
               <div style={{ marginTop: 8 }}>
                 {user.is_admin ? <Tag color="gold">管理员特权</Tag> : <Tag color="blue">标准用户</Tag>}
               </div>
             </Col>
           </Row>
        </Card>

        <Row gutter={24}>
          <Col span={12}>
            <Form.Item name="username" label="登录名" tooltip="不可更改，用于系统识别。">
              <Input disabled />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="email" label="绑定邮箱" rules={[{ type: 'email', message: '邮箱格式不正确' }]}>
              <Input placeholder="邮箱地址" />
            </Form.Item>
          </Col>
        </Row>

        <Form.Item name="avatar" label="头像 URL" tooltip="输入公共图片地址。">
          <Input placeholder="https://..." prefix={<GlobalOutlined />} />
        </Form.Item>

        <Form.Item name="bio" label="个人简介">
          <Input.TextArea rows={3} placeholder="简单的描述一下你自己，这有助于 AI 更好的了解你..." />
        </Form.Item>

        <Button type="primary" htmlType="submit" loading={loading} icon={<SaveOutlined />} size="large">
          更新资料
        </Button>
      </Form>
    </div>
  );

  const renderCollaboration = () => (
    <div className="settings-section">
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>智能体协作</Title>
          <Text type="secondary">调节 AI 内核的专家级采样参数与全局人设。</Text>
        </div>
        {!editingPreferences && (
          <Button type="primary" ghost icon={<EditOutlined />} onClick={() => setEditingPreferences(true)}>
            进入编辑模式
          </Button>
        )}
      </div>

      <Form 
        form={prefForm} 
        layout="vertical" 
        onFinish={handleUpdatePreferences}
        disabled={!editingPreferences}
      >
        <Card 
          title={<><BulbOutlined style={{ color: '#faad14' }} /> 生成控制</>} 
          bordered={false} 
          style={{ marginBottom: 20, borderRadius: 14, background: '#fafafa' }}
        >
          <Row gutter={32}>
            <Col span={12}>
              <Form.Item name="default_model" label="默认内核模型">
                <Select showSearch placeholder="选择模型" options={allModels} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="response_language" label="响应语言">
                <Select options={langOptions} />
              </Form.Item>
            </Col>
          </Row>

          <Divider style={{ margin: '12px 0 24px 0' }} />

          <Form.Item name="temperature" label="生成温度 (Temperature)" initialValue={0.7}>
            <Slider min={0} max={1.2} step={0.1} marks={{ 0: '严谨', 0.7: '平衡', 1.2: '创意' }} />
          </Form.Item>

          <Row gutter={32} style={{ marginTop: 32 }}>
            <Col span={12}>
               <Form.Item name="top_p" label="核采样 (Top-P)" initialValue={1.0}>
                 <Slider min={0} max={1} step={0.05} />
               </Form.Item>
            </Col>
            <Col span={12}>
               <Form.Item name="frequency_penalty" label="重复惩罚 (Frequency Penalty)" initialValue={0}>
                 <Slider min={0} max={1} step={0.1} />
               </Form.Item>
            </Col>
          </Row>
        </Card>

        <Card 
          title={<><SafetyOutlined style={{ color: '#52c41a' }} /> 专家指令微调</>} 
          bordered={false}
          style={{ borderRadius: 14, background: '#fafafa' }}
        >
          <Form.Item name="global_persona" label="全局人设引导词 (Global Persona)">
            <Input.TextArea rows={3} placeholder="例如：你是一个极其严谨且专业的架构师..." />
          </Form.Item>
          <Form.Item name="system_prompt_suffix" label="系统提示词后缀">
            <Input.TextArea rows={3} placeholder="自动追加到所有会话末尾..." />
          </Form.Item>
        </Card>

        {editingPreferences && (
          <div style={{ marginTop: 24, display: 'flex', gap: 12 }}>
            <Button type="primary" htmlType="submit" loading={loading} icon={<SaveOutlined />} size="large">
              保存设置
            </Button>
            <Button onClick={() => setEditingPreferences(false)} icon={<CloseOutlined />} size="large">
              取消
            </Button>
          </div>
        )}
      </Form>
    </div>
  );

  return (
    <div style={{ 
      height: '100vh', 
      width: '100vw', 
      background: '#fff', 
      display: 'flex', 
      flexDirection: 'column',
      animation: 'fadeIn 0.3s ease'
    }}>
      {/* 沉浸式顶部标题栏 */}
      <div style={{ 
        padding: '0 40px', 
        height: 64, 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'space-between',
        borderBottom: '1px solid #f0f0f0'
      }}>
        <Space align="center" size="large">
          <Button icon={<ArrowLeftOutlined />} type="text" onClick={onBack} size="large" />
          <Title level={4} style={{ margin: 0 }}>系统控制中心</Title>
          <Tag color="cyan">Agentic OS Settings</Tag>
        </Space>
        {user && (
          <Space>
            <Text strong>{user.username}</Text>
            <Avatar size="small" style={{ background: '#1890ff' }}>{user.username?.[0]?.toUpperCase()}</Avatar>
          </Space>
        )}
      </div>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* 左侧垂直菜单 */}
        <div style={{ 
          width: 280, 
          background: '#fafafa', 
          borderRight: '1px solid #f0f0f0',
          padding: '24px 0'
        }}>
          <Tabs
            tabPosition="left"
            activeKey={activeTab}
            onChange={setActiveTab}
            style={{ height: '100%' }}
            className="settings-center-tabs"
            items={[
              { key: 'dashboard', label: <Space><DashboardOutlined />使用概览</Space> },
              { key: 'account', label: <Space><UserOutlined />个人资料</Space> },
              { key: 'collaboration', label: <Space><ThunderboltOutlined />智能体协作</Space> },
              { key: 'safety', label: <Space><SafetyCertificateOutlined />数据与隐私管理</Space> },
            ]}
          />
        </div>

        {/* 右侧主区域 */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '48px 80px', background: '#fff' }}>
          <div style={{ maxWidth: 880, margin: '0 auto' }}>
            {activeTab === 'dashboard' && renderDashboard()}
            {activeTab === 'account' && renderAccount()}
            {activeTab === 'collaboration' && renderCollaboration()}
            {activeTab === 'safety' && (
              <Card bordered={false} style={{ background: '#fff7e6', border: '1px solid #ffe7ba', borderRadius: 12 }}>
                <Title level={4}>数据与隐私</Title>
                <Paragraph>UniAI Kernel 高度重视您的数据隐私。所有本地偏好设置和对话数据都将根据您的存储策略进行处理。</Paragraph>
                <div style={{ marginTop: 24 }}>
                  <Text strong>对话清理策略：</Text>
                  <Select defaultValue="manual" style={{ width: 240, display: 'block', marginTop: 8 }}>
                    <Select.Option value="manual">手动清理</Select.Option>
                    <Select.Option value="weekly">每周自动归档</Select.Option>
                  </Select>
                </div>
              </Card>
            )}
          </div>
        </div>
      </div>

      <style>{`
        .settings-center-tabs .ant-tabs-nav-list { width: 100%; }
        .settings-center-tabs .ant-tabs-tab { 
          padding: 12px 32px !important; 
          margin: 4px 0 !important;
          font-size: 15px !important;
        }
        .settings-center-tabs .ant-tabs-tab-active { background: #e6f7ff; color: #1890ff !important; font-weight: 600; }
        .settings-section { animation: slideUp 0.4s ease; }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes slideUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
      `}</style>
    </div>
  );
};

export default SettingsCenter;
