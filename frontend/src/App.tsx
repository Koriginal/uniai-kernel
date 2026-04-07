import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Layout, Menu, Typography, Avatar, Space, message, Modal, Tag, Dropdown, Button, Tooltip } from 'antd';
import {
  ThunderboltOutlined, HistoryOutlined, AppstoreOutlined,
  DatabaseOutlined, PlusOutlined, RobotOutlined, DeleteOutlined,
  ToolOutlined, BarChartOutlined, KeyOutlined, EditOutlined, UserOutlined,
  LockOutlined, AppstoreAddOutlined
} from '@ant-design/icons';
import axios from 'axios';

import ChatView from './components/ChatView';
import ArtifactCanvas from './components/ArtifactCanvas';
import AgentManager from './components/AgentManager';
import ProviderManager from './components/ProviderManager';
import ToolRegistry from './components/ToolRegistry';
import AuditLogView from './components/AuditLogView';
import ApiKeyManager from './components/ApiKeyManager';
import UserManager from './components/UserManager';
import ChangePasswordModal from './components/ChangePasswordModal';
import SettingsCenter from './components/SettingsView';
import Login from './components/Login';
import type { Message, Agent } from './components/ChatView';

const { Header, Content, Sider } = Layout;
const { Text, Title } = Typography;

type ViewType = 'chat' | 'agents' | 'providers' | 'tools' | 'audit' | 'api_keys' | 'users' | 'profile' | 'settings';

interface Session {
  id: string;
  title: string;
  status: string;
  created_at: string;
}

const App: React.FC = () => {
  // --- Auth State ---
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'));
  const [user, setUser] = useState<any | null>(null);

  // 创建带有超时的 axios 实例，并在请求拦截器中注入 Token
  const api = axios.create({
    timeout: 15000,
  });

  api.interceptors.request.use(config => {
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  });

  const logout = () => {
    localStorage.removeItem('token');
    setToken(null);
    setUser(null);
  };

  const handleLoginSuccess = (newToken: string, userData: any) => {
    localStorage.setItem('token', newToken);
    setToken(newToken);
    setUser(userData);
  };
  // --- Core State ---
  const [agents, setAgents] = useState<Agent[]>([]);
  const [modelConfigs, setModelConfigs] = useState<any[]>([]);
  const [currentAgent, setCurrentAgent] = useState<Agent | null>(null);
  // 使用 Ref 同步记录专家模式，解决异步判定崩溃
  const isExpertRef = useRef(false);
  const [activeView, setActiveView] = useState<ViewType>((localStorage.getItem('activeView') as ViewType) || 'chat');

  // --- Chat State ---
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(false);
  const [enableMemory, setEnableMemory] = useState(true);
  const [enableSwarm, setEnableSwarm] = useState(true);
  const [pendingImages, setPendingImages] = useState<string[]>([]);
  const [collaborationStatus, setCollaborationStatus] = useState<{ agentName?: string, content?: string, state: 'active' | 'completed' | null }>({ state: null });
  const abortControllerRef = React.useRef<AbortController | null>(null);

  // --- Session State (真实后端) ---
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(localStorage.getItem('currentSessionId'));
  const [passwordModalVisible, setPasswordModalVisible] = useState(false);

  // --- Canvas State ---
  const [canvasVisible, setCanvasVisible] = useState(false);
  const [canvasContent, setCanvasContent] = useState<string | null>(null);
  const [canvasType, setCanvasType] = useState<'markdown' | 'code'>('markdown');
  const [canvasTitle, setCanvasTitle] = useState('预览');
  const [canvasLanguage, setCanvasLanguage] = useState('javascript');
  const [enableAutoCanvas, setEnableAutoCanvas] = useState<boolean>(() => {
    const saved = localStorage.getItem('enableAutoCanvas');
    return saved === null ? true : saved === 'true';
  });

  useEffect(() => {
    localStorage.setItem('enableAutoCanvas', String(enableAutoCanvas));
  }, [enableAutoCanvas]);

  // 记录用户手动关闭过的消息 ID，防止流式输出过程中自动重开

  // --- Data Fetching ---
  const fetchAgents = useCallback(async () => {
    try {
      console.log("[App] Fetching agents...");
      const res = await api.get('/api/v1/agents/');
      const agentsData: Agent[] = res.data;
      setAgents(agentsData);
      
      const savedAgentId = localStorage.getItem('currentAgentId');
      
      setCurrentAgent(prev => {
        if (prev) return prev; // 已有则不覆盖
        
        if (savedAgentId && agentsData.length > 0) {
            const found = agentsData.find(a => a.id === savedAgentId);
            if (found) {
                console.log("[App] Restoring saved agent:", found.id);
                return found;
            }
        }

        if (agentsData.length > 0) {
          console.log("[App] Auto-selecting first agent:", agentsData[0].id);
          return agentsData[0];
        }
        return null;
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

  const fetchMe = useCallback(async () => {
    if (!token) return;
    try {
        const res = await api.get('/api/v1/auth/me');
        setUser(res.data);
    } catch {
        logout();
    }
  }, [token]);

  useEffect(() => {
    if (token) {
        fetchMe();
        fetchAgents();
        fetchModelConfigs();
        fetchSessions();
    }
  }, [token, fetchMe, fetchAgents, fetchModelConfigs, fetchSessions]);

  // --- Persistence Sync ---
  useEffect(() => {
    localStorage.setItem('activeView', activeView);
  }, [activeView]);

  useEffect(() => {
    if (currentAgent) {
        localStorage.setItem('currentAgentId', currentAgent.id);
    }
  }, [currentAgent]);

  useEffect(() => {
    if (currentSessionId) {
        localStorage.setItem('currentSessionId', currentSessionId);
    } else {
        localStorage.removeItem('currentSessionId');
    }
  }, [currentSessionId]);

  // --- Initial Session Restore ---
  const [sessionRestored, setSessionRestored] = useState(false);
  useEffect(() => {
    if (token && currentSessionId && sessions.length > 0 && agents.length > 0 && !sessionRestored) {
        loadSession(currentSessionId);
        setSessionRestored(true);
    }
  }, [token, currentSessionId, sessions, agents, sessionRestored]);

  // --- Session Management ---
  const startNewChat = () => {
    setCurrentSessionId(null);
    setMessages([]);
    setActiveView('chat');
    setCanvasVisible(false);
    setCanvasContent(null);
  };

  const createNewSession = async (autoClear = true, showToast = true) => {
    try {
      console.log("[App] Creating new session, autoClear:", autoClear);
      const res = await api.post('/api/v1/chat-sessions/', {
        title: currentAgent ? `与 ${currentAgent.name} 的对话` : 'New Chat',
        active_agent_id: currentAgent?.id
      });
      const newSession = res.data;
      setCurrentSessionId(newSession.id);
      if (autoClear) {
        setMessages([]);
      }
      setActiveView('chat');
      fetchSessions();
      if (showToast) message.success('已开启新会话');
      return newSession.id;
    } catch (err) {
      console.error("[App] Create session failed:", err);
      message.error('创建会话失败');
      setLoading(false);
      return null;
    }
  };

  const loadSession = async (sessionId: string) => {
    setCurrentSessionId(sessionId);
    setMessages([]);
    setActiveView('chat');
    setCanvasVisible(false);
    setCanvasContent(null);
    
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
        agentName: agents.find(a => a.id === m.agent_id)?.name,
        tool_calls: m.tool_calls // 恢复工具调用持久化状态
      }));
      setMessages(history);
      
      // 自动寻回逻辑：寻找最后一次看板投射并恢复状态
      const lastCanvasCall = [...history].reverse().find(m => 
        m.tool_calls && m.tool_calls.some((tc: any) => tc.function?.name === 'upsert_canvas')
      );
      if (lastCanvasCall) {
        const tc = lastCanvasCall.tool_calls.find((tc: any) => tc.function?.name === 'upsert_canvas');
        try {
          const args = typeof tc.function.arguments === 'string' ? JSON.parse(tc.function.arguments) : tc.function.arguments;
          if (args.content) {
            setCanvasContent(args.content);
            setCanvasTitle(args.title || '预览');
            setCanvasType(args.type || 'markdown');
            if (args.language) setCanvasLanguage(args.language);
            setCanvasVisible(true);
          }
        } catch (e) { console.warn("[App] Failed to restore canvas from history:", e); }
      }

      console.log(`[App] Session ${sessionId} history loaded and canvas restored: ${history.length} messages`);
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

  const renameSession = async (sessionId: string) => {
    const currentTitle = sessions.find(s => s.id === sessionId)?.title || "";
    const newTitle = prompt("修改会话标题", currentTitle);
    if (newTitle && newTitle !== currentTitle) {
      try {
        await api.patch(`/api/v1/chat-sessions/${sessionId}`, { title: newTitle });
        fetchSessions();
        message.success('标题已更新');
      } catch {
        message.error('更新失败');
      }
    }
  };

  const onStopGeneration = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setLoading(false);
      message.info('已停止生成');
    }
  };

  const onDeleteMessage = async (messageId: string) => {
    try {
      await api.delete(`/api/v1/messages/${messageId}`);
      setMessages(prev => prev.filter(m => m.id !== messageId));
      message.success('消息已删除');
    } catch {
      message.error('删除失败');
    }
  };

  const onFeedbackMessage = async (messageId: string, feedback: 'like' | 'dislike' | 'null') => {
    try {
      await api.patch(`/api/v1/messages/${messageId}`, { feedback });
      setMessages(prev => prev.map(m => m.id === messageId ? { ...m, feedback } : m));
      // 不弹窗，静默更新
    } catch {
      message.error('反馈提交失败');
    }
  };

  const onEditMessage = async (messageId: string, newContent: string) => {
    if (loading) return;
    try {
      // 1. 物理回溯：删除该消息之后的所有消息
      await api.delete(`/api/v1/messages/${messageId}?truncate=true`);
      
      // 2. 更新当前消息内容
      await api.patch(`/api/v1/messages/${messageId}`, { content: newContent });
      
      // 3. 前端同步：保留该消息及之前的所有消息，并更新内容
      const msgIndex = messages.findIndex(m => m.id === messageId);
      const newMessages = messages.slice(0, msgIndex + 1).map(m => 
        m.id === messageId ? { ...m, content: newContent } : m
      );
      setMessages(newMessages);

      // 4. 定位到当前 Agent 并触发重新生成
      // 找到该消息对应的 agent_id（如果有），或者直接用当前 active agent
      setInputText(""); // 清空输入框，因为我们是修改已有消息
      
      const originalMsg = messages.find(m => m.id === messageId);
      const originalImages = originalMsg?.images;

      // 触发 handleSendMessage 的逻辑，设置 skipSave 为 true，避免后端重复创建 User 消息
      await handleSendMessageInternal(newContent, true, true, originalImages);
    } catch (err) {
      console.error("[App] Edit message failed:", err);
      message.error('编辑失败');
    }
  };

  const onRegenerate = async () => {
    if (loading) return;
    if (messages.length < 2) return;
    const lastMsg = messages[messages.length - 1];
    if (lastMsg.role !== 'assistant') return;

    try {
      // 删除最后一条 AI 回复
      await api.delete(`/api/v1/messages/${lastMsg.id}`);
      const newMessages = messages.slice(0, -1);
      setMessages(newMessages);
      
      // 获取上一条用户消息内容
      const lastUserMsg = newMessages[newMessages.length - 1];
      if (lastUserMsg.role === 'user') {
        // 设置 skipSave 为 true，避免后端重复创建 User 消息
        await handleSendMessageInternal(typeof lastUserMsg.content === 'string' ? lastUserMsg.content : "", true, true);
      }
    } catch {
      message.error('重新生成失败');
    }
  };

  // --- Chat Handler ---
  const handleSendMessage = async () => {
    if (loading) return;
    const text = inputText.trim();
    await handleSendMessageInternal(text);
    setInputText('');
  };

  const handleSendMessageInternal = async (
    text: string, 
    isRetry = false, 
    skipSaveUser = false, 
    overrideImages?: string[]
  ) => {
    if (!currentAgent) return;

    console.log(`[App] >>> handleSendMessageInternal! Text: "${text}"`, "AgentID:", currentAgent.id, "SkipSave:", skipSaveUser);
    const activeImages = overrideImages || (isRetry ? [] : pendingImages);
    const hasImages = activeImages.length > 0;
    
    if (!isRetry) {
        const userMsg: Message = {
          id: Date.now().toString(),
          role: 'user',
          content: text,
          timestamp: Date.now(),
          images: hasImages ? [...activeImages] : undefined
        };
        setMessages(prev => [...prev, userMsg]);
        setPendingImages([]);
    }
    
    setLoading(true);

    // 若无会话，自动创建 (Lazy Creation)
    let sessionId = currentSessionId;
    if (!sessionId) {
      sessionId = await createNewSession(false, false);
      if (!sessionId) { setLoading(false); return; }
    }

    const contentPayload = hasImages ? [
      { type: 'text', text: text },
      ...activeImages.map(img => ({ type: 'image_url', image_url: { url: img } }))
    ] : text;

    let assistantMsgId = (Date.now() + 1).toString();
    const assistantMsg: Message = {
      id: assistantMsgId,
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
      agentName: currentAgent.name
    };
    setMessages(prev => [...prev, assistantMsg]);

    const controller = new AbortController();
    abortControllerRef.current = controller;
    // 在每次发起对话请求前，强制重置专家模式同步锁
    isExpertRef.current = false;

    try {
      const response = await fetch(`/api/v1/agents/${currentAgent.id}/chat`, {
        method: 'POST',
        headers: { 
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}` 
        },
        body: JSON.stringify({
          query: contentPayload,
          session_id: sessionId,
          stream: true,
          enable_memory: enableMemory,
          enable_swarm: enableSwarm,
          enable_canvas: enableAutoCanvas, // 同步看板开关状态到后端
          skip_save_user: skipSaveUser
        }),
        signal: controller.signal
      });

      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let accumulatedContent = '';
      let initialTempId = assistantMsgId; // 记录初始临时 ID，用于稳健同步
      let toolCallsBuffer: any[] = []; 
      let lineBuffer = ''; // 用于处理跨 chunk 的完整行

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          lineBuffer += chunk;
          
          const lines = lineBuffer.split('\n');
          // 留最后一行到 buffer (如果它不以 \n 结尾)
          lineBuffer = lines.pop() || '';
          
          for (const line of lines) {
            const trimmedLine = line.trim();
            if (!trimmedLine || !trimmedLine.startsWith('data: ')) continue;
            
            const dataStr = trimmedLine.replace('data: ', '');
            if (dataStr === '[DONE]') break;

            try {
              const data = JSON.parse(dataStr);
              
              // 处理元数据同步 ID
              if (data.type === 'metadata') {
                if (data.user_message_id) {
                    setMessages(prev => {
                        const newMsgs = [...prev];
                        for (let i = newMsgs.length - 1; i >= 0; i--) {
                            if (newMsgs[i].role === 'user') {
                                newMsgs[i] = { ...newMsgs[i], id: data.user_message_id };
                                break;
                            }
                        }
                        return newMsgs;
                    });
                }
                if (data.assistant_message_id) {
                    // 核心逻辑：只有当前 ID 既不是旧跟踪 ID 也不是初始临时 ID 时，才认为是真正的新消息，才执行清空。
                    // [IMPORTANT] 重大修复：移除 setCanvasContent("")。看板应跨专家生命周期持久，直到被新内容覆盖。
                    if (data.assistant_message_id !== assistantMsgId && data.assistant_message_id !== initialTempId) {
                        accumulatedContent = "";
                        toolCallsBuffer = [];
                    }
                    
                    setMessages(prev => prev.map(m => 
                      // 稳健匹配：兼容初始临时 ID 和当前正在跟踪的助理 ID
                      (m.id === assistantMsgId || m.id === initialTempId) ? { ...m, id: data.assistant_message_id } : m
                    ));
                    // 闭包内的 ID 同步更新，保证后续代码块逻辑连贯
                    assistantMsgId = data.assistant_message_id;
                }
                continue;
              }

              // 移除依赖 State 的局部变量，改用受控 Ref 同步锁
              if (data.type === 'status') {
                if (data.state === 'active') {
                  isExpertRef.current = true; // 同步加锁
                  setCollaborationStatus({ agentName: data.agentName, content: data.content, state: 'active' });
                } else if (data.state === 'completed') {
                  isExpertRef.current = false; // 同步解锁
                  setCollaborationStatus({ state: 'completed' });
                }
                continue;
              }

              // 稳健型受限正则解析器：精准定位 JSON Key，防止被模型思考过程中的描述性文字干扰
              const extractPartialJsonField = (jsonStr: string, fieldName: string) => {
                // 精准匹配 "key": " 或 "key":" (支持空格)
                const regex = new RegExp(`"${fieldName}"\\s*:\\s*"`);
                const match = jsonStr.match(regex);
                if (!match) return null;

                const valueStart = (match.index || 0) + match[0].length;
                let valueEnd = jsonStr.length;

                // 查找下一个未转义的引号作为结束符
                for (let i = valueStart; i < jsonStr.length; i++) {
                  if (jsonStr[i] === '"' && jsonStr[i - 1] !== '\\') {
                    valueEnd = i;
                    break;
                  }
                }

                const rawValue = jsonStr.substring(valueStart, valueEnd);
                try {
                  // 物理还原转义字符，处理速度快，容错能力强
                  return rawValue
                    .replace(/\\n/g, '\n')
                    .replace(/\\"/g, '"')
                    .replace(/\\\\/g, '\\')
                    .replace(/\\t/g, '\t')
                    .replace(/\\r/g, '\r');
                } catch (e) {
                  return rawValue;
                }
              };

              const delta = data.choices?.[0]?.delta;
              if (delta?.content) {
                accumulatedContent += delta.content;
              }
              
              if (delta?.tool_calls) {
                delta.tool_calls.forEach((tc: any) => {
                  const idx = tc.index;
                  if (!toolCallsBuffer[idx]) {
                    toolCallsBuffer[idx] = { 
                      id: tc.id, 
                      function: { name: tc.function?.name || "", arguments: "" } 
                    };
                  }
                  if (tc.function?.arguments) {
                    toolCallsBuffer[idx].function.arguments += tc.function.arguments;
                    const currentTC = toolCallsBuffer[idx];
                    
                    if (currentTC.function.name === 'upsert_canvas' || toolCallsBuffer[idx].isCanvasUpdate) {
                      toolCallsBuffer[idx].isCanvasUpdate = true;
                      const argsStr = currentTC.function.arguments;
                      
                      // 展示 Loading 骨架，减少等待感
                      if (!canvasVisible) setCanvasVisible(true);

                      const sContent = extractPartialJsonField(argsStr, "content");
                      const sTitle = extractPartialJsonField(argsStr, "title");
                      const sType = extractPartialJsonField(argsStr, "type");
                      const sLanguage = extractPartialJsonField(argsStr, "language");
                      
                      if (sType) setCanvasType(sType as any);
                      if (sLanguage) setCanvasLanguage(sLanguage);
                      if (sTitle) setCanvasTitle(sTitle);
                      
                      // 关键：仅在有效提取时更新，防止推流抖动置空
                      if (sContent !== null) {
                        setCanvasContent(sContent);
                      }
                    }
                  }
                });
              }

              if (delta?.content || delta?.tool_calls) {
                setMessages(prev => prev.map(m => 
                  // 只要 ID 没变或者是正在流式更新的气泡，就持续喂入内容块
                  (m.id === assistantMsgId || m.id === initialTempId) ? 
                  { ...m, content: accumulatedContent, tool_calls: toolCallsBuffer.filter(Boolean) } : m
                ));
              }
            } catch (err) {
              console.warn("[App] SSE parse error:", err);
            }
          }
        }
      }
      // 物理级结案对齐逻辑 (Final Consensus)
      // [IMPORTANT] 采用“倒序优先”策略：确保在多轮接力中，看板展现的是主控最终确认的最新版本
      const finalCanvasTC = [...toolCallsBuffer].reverse().find(tc => tc && tc.function.name === 'upsert_canvas');
      if (finalCanvasTC) {
          try {
              const finalArgs = JSON.parse(finalCanvasTC.function.arguments);
              if (finalArgs.content) {
                  setCanvasContent(finalArgs.content);
                  if (!canvasVisible) setCanvasVisible(true);
              }
              if (finalArgs.title) setCanvasTitle(finalArgs.title);
              if (finalArgs.type) setCanvasType(finalArgs.type);
          } catch (e) {
              console.warn("[App] Final alignment failed:", e);
          }
      }

      fetchSessions();
    } catch (err: any) {
      if (err.name === 'AbortError') {
        console.log("[App] Stream aborted by user");
      } else {
        console.error("[App] Streaming failed:", err);
        message.error('流式生成失败');
      }
    } finally {
      abortControllerRef.current = null;
      setLoading(false);
      setCollaborationStatus({ state: null }); // 重置协作状态
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
    
    // 如果切换了不同的智能体，则进入“新会话”预备状态，避免内容错位
    if (currentAgent?.id !== agent.id) {
        startNewChat();
    }

    setActiveView('chat');
    setCurrentAgent(agent);
  };

  // --- Render ---
  if (!token) {
    return <Login onLoginSuccess={handleLoginSuccess} />;
  }

  return (
    <Layout style={{ height: '100vh', width: '100vw', overflow: 'hidden', background: '#f5f6fa' }}>
        {activeView !== 'settings' && (
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

          {/* 新建会话 - 全局快速操作 (Gemini Style) */}
          <div style={{ padding: '12px 16px', borderBottom: '1px solid #f0f0f0' }}>
            <Button 
              type="primary" 
              icon={<PlusOutlined />} 
              block 
              onClick={startNewChat}
              style={{ borderRadius: 8, height: 40, fontWeight: 500, boxShadow: '0 2px 4px rgba(24,144,255,0.2)' }}
            >
              开启新会话
            </Button>
          </div>

          <Menu
            mode="inline"
            selectedKeys={[activeView === 'chat' ? (currentSessionId || currentAgent?.id || 'chat') : activeView]}
            style={{ borderRight: 0, background: 'transparent' }}
          >
            {/* 会话管理 */}
            <Menu.SubMenu key="sessions" icon={<HistoryOutlined />} title="所有会话">
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
                  <Space size={4}>
                      <EditOutlined
                        onClick={e => { e.stopPropagation(); renameSession(s.id); }}
                        style={{ color: '#999', fontSize: '11px' }}
                      />
                      <DeleteOutlined
                        onClick={e => { e.stopPropagation(); deleteSession(s.id); }}
                        style={{ color: '#ff4d4f', fontSize: '11px' }}
                      />
                  </Space>
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

            {/* 开量/统计 */}
            <Menu.Item key="audit" icon={<BarChartOutlined />} onClick={() => setActiveView('audit')}>
              使用审计
            </Menu.Item>

            {/* API 秘钥 */}
            <Menu.Item key="api_keys" icon={<KeyOutlined />} onClick={() => setActiveView('api_keys')}>
              API 秘钥
            </Menu.Item>

          </Menu>
        </Sider>
        )}

        <Layout style={{ 
          marginLeft: 0, 
          transition: 'all 0.2s',
          height: '100vh', 
          display: 'flex', 
          flexDirection: 'column' 
        }}>
          {activeView !== 'settings' && (
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
                    : activeView === 'users' ? '系统用户管理'
                    : 'UniAI Kernel'}
                </Text>
              )}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
              {activeView === 'chat' && (
                <Tooltip title={canvasVisible ? "关闭侧边看板" : "打开侧边看板"}>
                  <Button 
                    type="text" 
                    icon={<AppstoreAddOutlined style={{ fontSize: 16, color: canvasVisible ? '#1890ff' : 'rgba(0,0,0,0.45)' }} />} 
                    onClick={() => setCanvasVisible(!canvasVisible)}
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                  />
                </Tooltip>
              )}
              {user && (
                <Dropdown 
                  overlay={
                    <Menu>
                      <Menu.Item key="username" disabled>
                        <Text strong>{user.username}</Text>
                        <br/>
                        <Text type="secondary" style={{ fontSize: '12px' }}>{user.email}</Text>
                      </Menu.Item>
                      <Menu.Divider />
                      <Menu.Item key="settings" icon={<ThunderboltOutlined />} onClick={() => setActiveView('settings')}>
                        个人中心与系统设置
                      </Menu.Item>
                      <Menu.Item key="change-password" icon={<LockOutlined />} onClick={() => setPasswordModalVisible(true)}>
                        修改密码
                      </Menu.Item>
                      {user.is_admin && (
                        <Menu.Item key="user-mgmt" icon={<AppstoreOutlined />} onClick={() => setActiveView('users')}>
                          系统用户管理
                        </Menu.Item>
                      )}
                      <Menu.Divider />
                      <Menu.Item key="logout" danger icon={<DeleteOutlined />} onClick={() => Modal.confirm({
                          title: '确定要退出吗？',
                          content: '退出后需要重新登录方可访问系统。',
                          onOk: logout
                      })}>
                        退出登录
                      </Menu.Item>
                    </Menu>
                  } 
                  placement="bottomRight" 
                  arrow
                >
                  <div style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Avatar 
                      size="small" 
                      icon={<UserOutlined />} 
                      style={{ background: user.is_admin ? '#f56a00' : '#1890ff' }} 
                    />
                    <Text strong>{user.username}</Text>
                    {user.is_admin && <Tag color="gold" style={{ margin: 0 }}>ADMIN</Tag>}
                  </div>
                </Dropdown>
              )}
            </div>
          </Header>
          )}

          <Content style={{
            margin: (activeView === 'settings' || activeView === 'audit') ? 0 : '12px', 
            background: (activeView === 'settings' || activeView === 'audit') ? 'transparent' : '#fff', 
            borderRadius: (activeView === 'settings' || activeView === 'audit') ? 0 : '8px',
            display: 'flex', flexDirection: 'column', overflow: 'hidden',
            boxShadow: (activeView === 'settings' || activeView === 'audit') ? 'none' : '0 1px 4px rgba(0,0,0,0.06)'
          }}>
            {activeView === 'chat' && (
              <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
                <ChatView
                  messages={messages} loading={loading}
                  collaborationStatus={collaborationStatus}
                  inputText={inputText} setInputText={setInputText}
                  currentAgent={currentAgent}
                  enableMemory={enableMemory} setEnableMemory={setEnableMemory}
                  enableSwarm={enableSwarm} setEnableSwarm={setEnableSwarm}
                  onSend={handleSendMessage}
                  onStop={onStopGeneration}
                  onDeleteMessage={onDeleteMessage}
                  onEditMessage={onEditMessage}
                  onFeedbackMessage={onFeedbackMessage}
                  onRegenerate={onRegenerate}
                  pendingImages={pendingImages}
                  setPendingImages={setPendingImages}
                  enableAutoCanvas={enableAutoCanvas}
                  setEnableAutoCanvas={setEnableAutoCanvas}
                  onOpenCanvas={(title, content, type, lang) => {
                    setCanvasTitle(title);
                    setCanvasContent(content);
                    setCanvasType(type);
                    if (lang) setCanvasLanguage(lang);
                    setCanvasVisible(true);
                  }}
                />
                <ArtifactCanvas
                  visible={canvasVisible}
                  onClose={() => {
                    setCanvasVisible(false);
                  }}
                  title={canvasTitle}
                  content={canvasContent}
                  type={canvasType}
                  language={canvasLanguage}
                  loading={loading}
                />
              </div>
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

            {activeView === 'audit' && (
              <AuditLogView />
            )}

            {activeView === 'api_keys' && (
              <ApiKeyManager api={api} user={user} />
            )}
            
            {activeView === 'settings' && user && (
               <SettingsCenter 
                user={user} 
                api={api} 
                modelConfigs={modelConfigs} 
                onRefresh={fetchMe}
                onBack={() => setActiveView('chat')}
               />
            )}

            {activeView === 'users' && (
              <UserManager />
            )}
          </Content>
          <ChangePasswordModal 
            visible={passwordModalVisible}
            onCancel={() => setPasswordModalVisible(false)}
            api={api}
            onSuccess={() => {
                setPasswordModalVisible(false);
                logout();
            }}
          />
        </Layout>
    </Layout>
  );
};

export default App;
