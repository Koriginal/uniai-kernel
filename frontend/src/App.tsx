import React, { useState, useEffect, useCallback } from 'react';
import { Layout, Menu, Typography, Avatar, Space, message } from 'antd';
import {
  ThunderboltOutlined, HistoryOutlined, AppstoreOutlined,
  DatabaseOutlined, PlusOutlined, RobotOutlined, DeleteOutlined,
  ToolOutlined
} from '@ant-design/icons';
import axios from 'axios';

import ChatView from './components/ChatView';
import AgentManager from './components/AgentManager';
import ProviderManager from './components/ProviderManager';
import ToolRegistry from './components/ToolRegistry';
import type { Message, Agent } from './components/ChatView';

const { Header, Content, Sider } = Layout;
const { Text, Title } = Typography;

type ViewType = 'chat' | 'agents' | 'providers' | 'tools';

interface Session {
  id: string;
  title: string;
  status: string;
  created_at: string;
}

const App: React.FC = () => {
  // 创建带有超时的 axios 实例，防止请求无限制 Pending
  const api = axios.create({
    timeout: 15000,
  });
  // --- Core State ---
  const [agents, setAgents] = useState<Agent[]>([]);
  const [modelConfigs, setModelConfigs] = useState<any[]>([]);
  const [currentAgent, setCurrentAgent] = useState<Agent | null>(null);
  const [activeView, setActiveView] = useState<ViewType>('chat');

  // --- Chat State ---
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(false);
  const [enableMemory, setEnableMemory] = useState(true);
  const [enableSwarm, setEnableSwarm] = useState(true);
  const [pendingImages, setPendingImages] = useState<string[]>([]);

  // --- Session State (真实后端) ---
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);

  // --- Data Fetching ---
  const fetchAgents = useCallback(async () => {
    try {
      console.log("[App] Fetching agents...");
      const res = await api.get('/api/v1/agents/');
      setAgents(res.data);
      // 只有在当前没有智能体时才进行默认赋值，防止后续刷新覆盖用户选择
      setCurrentAgent(prev => {
        if (!prev && res.data.length > 0) {
          console.log("[App] Auto-selecting first agent:", res.data[0].id);
          return res.data[0];
        }
        return prev;
      });
    } catch (err) {
      console.error("[App] Fetch agents failed:", err);
    }
  }, []);

  const fetchModelConfigs = useCallback(async () => {
    try {
      const res = await api.get('/api/v1/providers/my/providers');
      setModelConfigs(res.data);
    } catch { /* ignore */ }
  }, []);

  const fetchSessions = useCallback(async () => {
    try {
      const res = await api.get('/api/v1/chat-sessions/');
      setSessions(res.data);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    fetchAgents();
    fetchModelConfigs();
    fetchSessions();
  }, []);

  // --- Session Management ---
  const createNewSession = async (autoClear = true) => {
    try {
      console.log("[App] Creating new session, autoClear:", autoClear);
      const res = await api.post('/api/v1/chat-sessions/', {
        title: currentAgent ? `与 ${currentAgent.name} 的对话` : 'New Chat'
      });
      const newSession = res.data;
      setCurrentSessionId(newSession.id);
      if (autoClear) {
        setMessages([]);
      }
      setActiveView('chat');
      fetchSessions();
      message.success('已创建新会话');
      return newSession.id;
    } catch (err) {
      console.error("[App] Create session failed:", err);
      message.error('创建会话失败');
      setLoading(false); // 关键：发生报错时立即停止 UI 转圈
      return null;
    }
  };

  const loadSession = async (sessionId: string) => {
    setCurrentSessionId(sessionId);
    setMessages([]);
    setActiveView('chat');
    
    try {
      // 1. 恢复会话关联的专家信息
      const res = await api.get(`/api/v1/chat-sessions/${sessionId}`);
      const session = res.data;
      if (session.active_agent_id) {
        const agent = agents.find(a => a.id === session.active_agent_id);
        if (agent) setCurrentAgent(agent);
      }

      // 2. 拉取历史消息记录
      const msgRes = await api.get(`/api/v1/chat-sessions/${sessionId}/messages`);
      const history = msgRes.data.map((m: any) => ({
        id: m.id,
        role: m.role,
        content: m.content,
        timestamp: m.timestamp,
        agentName: agents.find(a => a.id === m.agent_id)?.name
      }));
      setMessages(history);
      console.log(`[App] Session ${sessionId} history loaded: ${history.length} messages`);
    } catch (err) {
      console.error("[App] Load session failed:", err);
      message.error('加载会话记录失败');
    }
  };

  const deleteSession = async (sessionId: string) => {
    try {
      await api.delete(`/api/v1/chat-sessions/${sessionId}`);
      if (currentSessionId === sessionId) {
        setCurrentSessionId(null);
        setMessages([]);
      }
      fetchSessions();
      message.success('会话已删除');
    } catch {
      message.error('删除失败');
    }
  };

  // --- Chat Handler ---
  const handleSendMessage = async () => {
    const text = inputText.trim();
    if (!text || !currentAgent) {
      console.warn("[App] handleSendMessage aborted: empty text or no agent selected");
      return;
    }

    console.log(`[App] >>> handleSendMessage Stream Mode Triggered! Text: "${text}"`, "AgentID:", currentAgent.id);
    const hasImages = pendingImages.length > 0;
    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: text,
      timestamp: Date.now(),
      images: hasImages ? [...pendingImages] : undefined
    };
    setMessages(prev => [...prev, userMsg]);
    setInputText('');
    setPendingImages([]);
    setLoading(true);

    // 若无会话，自动创建
    let sessionId = currentSessionId;
    if (!sessionId) {
      console.log("[App] No active session, triggering automatic creation...");
      sessionId = await createNewSession(false);
      if (!sessionId) { setLoading(false); return; }
    }

    // 构造具备视觉能力的 Payload 报文
    const contentPayload = hasImages ? [
      { type: 'text', text: text },
      ...userMsg.images!.map(img => ({
          type: 'image_url',
          image_url: { url: img } // img 通常为 data:image/jpeg;base64,... 格式
      }))
    ] : text;

    // 创建助理占位消息
    const assistantMsgId = (Date.now() + 1).toString();
    const assistantMsg: Message = {
      id: assistantMsgId,
      role: 'assistant',
      content: '', // 初始内容为空，后续流式追加
      timestamp: Date.now(),
      agentName: currentAgent.name
    };
    setMessages(prev => [...prev, assistantMsg]);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000); // 流式请求 30s 超时

    try {
      console.log("[App] Fetching chat stream from backend, session:", sessionId);
      const response = await fetch(`/api/v1/agents/${currentAgent.id}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: contentPayload, // 这里使用已经构造好的视觉报文
          session_id: sessionId,
          stream: true,
          enable_memory: enableMemory,
          enable_swarm: enableSwarm
        }),
        signal: controller.signal
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let accumulatedContent = '';

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split('\n');
          
          for (const line of lines) {
            const trimmedLine = line.trim();
            if (!trimmedLine || !trimmedLine.startsWith('data: ')) continue;
            
            const dataStr = trimmedLine.replace('data: ', '');
            if (dataStr === '[DONE]') break;

            try {
              const data = JSON.parse(dataStr);
              const delta = data.choices?.[0]?.delta?.content;
              if (delta) {
                accumulatedContent += delta;
                // 实时更新消息列表中的最后一条消息内容
                setMessages(prev => prev.map(m => 
                  m.id === assistantMsgId ? { ...m, content: accumulatedContent } : m
                ));
              }
            } catch (err) {
              console.warn("[App] SSE parse error:", err, dataStr);
            }
          }
        }
      }

      // 刷新会话列表
      fetchSessions();
    } catch (err: any) {
      console.error("[App] Streaming failed:", err);
      if (err.name === 'AbortError') {
        message.error('流式请求超时');
      } else {
        message.error('流式生成失败');
      }
    } finally {
      clearTimeout(timeoutId);
      setLoading(false);
    }
  };

  // 挂载全局调试入口
  (window as any).debugSendMessage = handleSendMessage;

  const handleAgentClick = (agent: Agent) => {
    console.log("[App] User clicked agent:", agent.id);
    if (!agent.is_active) {
      message.warning(`${agent.name} 当前离线`);
      return;
    }
    setActiveView('chat');
    setCurrentAgent(agent);
  };

  // --- Render ---
  return (
    <Layout style={{ height: '100vh', width: '100vw', overflow: 'hidden', background: '#f5f6fa' }}>
        <Sider
          width={240}
          theme="light"
          style={{ borderRight: '1px solid #e8e8e8', overflow: 'auto', flexShrink: 0 }}
        >
          <div style={{ padding: '16px 16px 12px', borderBottom: '1px solid #f0f0f0' }}>
            <Title level={5} style={{ margin: 0, color: '#1890ff', fontSize: 16 }}>
              <ThunderboltOutlined style={{ marginRight: 6 }} />
              UniAI Kernel
            </Title>
            <Text type="secondary" style={{ fontSize: '10px' }}>Agentic OS v1.0</Text>
          </div>

          <Menu
            mode="inline"
            selectedKeys={[activeView === 'chat' ? (currentSessionId || currentAgent?.id || 'chat') : activeView]}
            style={{ borderRight: 0, background: 'transparent' }}
          >
            {/* 会话管理 */}
            <Menu.SubMenu key="sessions" icon={<HistoryOutlined />} title="会话">
              <Menu.Item key="new-session" icon={<PlusOutlined />} onClick={() => createNewSession()}>
                新建会话
              </Menu.Item>
              {sessions.map(s => (
                <Menu.Item
                  key={s.id}
                  onClick={() => loadSession(s.id)}
                  style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    background: currentSessionId === s.id ? '#e6f7ff' : 'transparent'
                  }}
                >
                  <Text ellipsis={{ tooltip: true }} style={{ flex: 1, fontSize: '13px' }}>
                    {s.title || 'Untitled'}
                  </Text>
                  <DeleteOutlined
                    onClick={e => { e.stopPropagation(); deleteSession(s.id); }}
                    style={{ color: '#999', fontSize: '11px', marginLeft: 4 }}
                  />
                </Menu.Item>
              ))}
            </Menu.SubMenu>

            {/* 专家集群 */}
            <Menu.SubMenu key="agents" icon={<AppstoreOutlined />} title="专家集群">
              {agents.map(agent => (
                <Menu.Item
                  key={agent.id}
                  onClick={() => handleAgentClick(agent)}
                  style={{
                    opacity: agent.is_active ? 1 : 0.5,
                    background: currentAgent?.id === agent.id ? '#e6f7ff' : 'transparent'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ position: 'relative' }}>
                      <Avatar size="small" icon={<RobotOutlined />}
                        style={{ backgroundColor: currentAgent?.id === agent.id ? '#1890ff' : '#ccc' }} />
                      <div style={{
                        position: 'absolute', bottom: -1, right: -1,
                        width: 7, height: 7, borderRadius: '50%',
                        background: agent.is_active ? '#52c41a' : '#bfbfbf',
                        border: '1px solid #fff'
                      }} />
                    </div>
                    <Text style={{ fontSize: '13px' }}>{agent.name}</Text>
                  </div>
                </Menu.Item>
              ))}
              <Menu.Item key="manage-agents" onClick={() => setActiveView('agents')}>
                管理专家...
              </Menu.Item>
            </Menu.SubMenu>

            {/* 供应商 */}
            <Menu.Item key="providers" icon={<DatabaseOutlined />} onClick={() => setActiveView('providers')}>
              模型供应商
            </Menu.Item>

            {/* 工具注册表 */}
            <Menu.Item key="tools" icon={<ToolOutlined />} onClick={() => setActiveView('tools')}>
              工具注册表
            </Menu.Item>
          </Menu>
        </Sider>

        <Layout>
          <Header style={{
            background: '#fff', padding: '0 20px',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            borderBottom: '1px solid #f0f0f0', height: 52, lineHeight: '52px'
          }}>
            <div style={{ display: 'flex', alignItems: 'center' }}>
              {activeView === 'chat' && currentAgent ? (
                <div style={{ display: 'flex', alignItems: 'center' }}>
                  <Avatar size="small" icon={<RobotOutlined />} style={{ backgroundColor: '#1890ff', marginRight: 10 }} />
                  <div>
                    <Text strong style={{ fontSize: 14 }}>{currentAgent.name}</Text>
                    <Text type="secondary" style={{ fontSize: '11px', marginLeft: 8 }}>{currentAgent.description}</Text>
                  </div>
                </div>
              ) : (
                <Text strong style={{ fontSize: 14 }}>
                  {activeView === 'agents' ? '专家集群管理'
                    : activeView === 'providers' ? '模型供应商'
                    : activeView === 'tools' ? '工具注册表'
                    : 'UniAI Kernel'}
                </Text>
              )}
            </div>
            <Space />
          </Header>

          <Content style={{
            margin: '12px', background: '#fff', borderRadius: '8px',
            display: 'flex', flexDirection: 'column', overflow: 'hidden',
            boxShadow: '0 1px 4px rgba(0,0,0,0.06)'
          }}>
            {activeView === 'chat' && (
              <ChatView
                messages={messages} loading={loading}
                inputText={inputText} setInputText={setInputText}
                currentAgent={currentAgent}
                enableMemory={enableMemory} setEnableMemory={setEnableMemory}
                enableSwarm={enableSwarm} setEnableSwarm={setEnableSwarm}
                onSend={handleSendMessage}
                pendingImages={pendingImages}
                setPendingImages={setPendingImages}
              />
            )}

            {activeView === 'agents' && (
              <AgentManager
                agents={agents} setAgents={setAgents}
                modelConfigs={modelConfigs} msgApi={message}
                onRefresh={() => { fetchAgents(); fetchModelConfigs(); }}
              />
            )}

            {activeView === 'providers' && (
              <ProviderManager
                modelConfigs={modelConfigs} msgApi={message}
                onRefresh={fetchModelConfigs}
              />
            )}

            {activeView === 'tools' && (
              <ToolRegistry msgApi={message} />
            )}
          </Content>
        </Layout>
    </Layout>
  );
};

export default App;
