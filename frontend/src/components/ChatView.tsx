import React, { useRef, useEffect } from 'react';
import { Typography, Avatar, Input, Tag, Empty, Space, Divider, Button, Collapse } from 'antd';
import {
  SendOutlined, RobotOutlined, UserOutlined,
  HistoryOutlined, PartitionOutlined, PlusOutlined,
  SyncOutlined, CaretRightOutlined
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight, oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';

const { Text } = Typography;

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string | any[];
  timestamp: number;
  agentName?: string;
  images?: string[]; 
}

interface Agent {
  id: string;
  name: string;
  description: string;
  tools?: string[];
  is_active: boolean;
  is_public: boolean;
  model_config_id: number;
  system_prompt?: string;
}

interface ChatViewProps {
  messages: Message[];
  loading: boolean;
  inputText: string;
  setInputText: (v: string) => void;
  currentAgent: Agent | null;
  enableMemory: boolean;
  setEnableMemory: (v: boolean) => void;
  enableSwarm: boolean;
  setEnableSwarm: (v: boolean) => void;
  onSend: () => void;
  pendingImages: string[];
  setPendingImages: (v: string[] | ((prev: string[]) => string[])) => void;
}

const MessageContent: React.FC<{ content: string | any[]; role: string }> = ({ content, role }) => {
  const isDark = false;

  const processContent = (raw: string | any[]) => {
    if (Array.isArray(raw)) {
      return raw.map(item => item.type === 'text' ? item.text : '').join('\n');
    }
    return raw;
  };

  const parts: { type: 'text' | 'thought' | 'collaboration' | 'tool', content: string }[] = [];
  const textContent = processContent(content);
  let remaining = textContent;

  const thoughtRegex = /<thought>([\s\S]*?)<\/thought>/g;
  const collabRegex = /<collaboration>([\s\S]*?)<\/collaboration>/g;
  
  // 混合解析逻辑
  let allMatches: { index: number, length: number, type: 'thought' | 'collaboration', content: string }[] = [];
  
  let match;
  while ((match = thoughtRegex.exec(remaining)) !== null) {
    allMatches.push({ index: match.index, length: match[0].length, type: 'thought', content: match[1] });
  }
  collabRegex.lastIndex = 0;
  while ((match = collabRegex.exec(remaining)) !== null) {
    allMatches.push({ index: match.index, length: match[0].length, type: 'collaboration', content: match[1] });
  }
  
  allMatches.sort((a, b) => a.index - b.index);

  let lastIndex = 0;
  allMatches.forEach(m => {
    if (m.index > lastIndex) {
      parts.push({ type: 'text', content: remaining.slice(lastIndex, m.index) });
    }
    // 增加逻辑：判断标签是否闭合
    const rawTag = remaining.slice(m.index, m.index + m.length);
    const isClosed = rawTag.includes('</thought>') || rawTag.includes('</collaboration>');
    
    parts.push({ type: m.type, content: m.content, isClosed } as any);
    lastIndex = m.index + m.length;
  });

  if (lastIndex < remaining.length) {
    remaining = remaining.slice(lastIndex);
    // 处理可能存在的未闭合尾部
    if (remaining.includes('<thought>')) {
        const idx = remaining.indexOf('<thought>');
        if (idx > 0) parts.push({ type: 'text', content: remaining.slice(0, idx) });
        parts.push({ type: 'thought', content: remaining.slice(idx + 9), isClosed: false } as any);
        remaining = "";
    } else if (remaining.includes('<collaboration>')) {
        const idx = remaining.indexOf('<collaboration>');
        if (idx > 0) parts.push({ type: 'text', content: remaining.slice(0, idx) });
        parts.push({ type: 'collaboration', content: remaining.slice(idx + 15), isClosed: false } as any);
        remaining = "";
    }
  }

  if (parts.length === 0 && remaining) {
    const lines = remaining.split('\n');
    let currentText = "";
    lines.forEach(line => {
      if (line.trim().startsWith('⚡')) {
        if (currentText) parts.push({ type: 'text', content: currentText });
        parts.push({ type: 'tool', content: line.trim().replace(/^⚡\s*/, '') });
        currentText = "";
      } else {
        currentText += line + '\n';
      }
    });
    if (currentText) parts.push({ type: 'text', content: currentText });
  } else if (remaining) {
    parts.push({ type: 'text', content: remaining });
  }

  return (
    <div className="message-markdown-content" style={{ fontSize: '14px', lineHeight: '1.6' }}>
      {parts.map((p: any, i) => {
        if (p.type === 'thought') {
          return (
            <Collapse
              key={i}
              ghost
              defaultActiveKey={p.isClosed ? [] : ['1']}
              style={{ marginBottom: 12, border: '1px solid #e8e8e8', borderRadius: 8, background: '#fafafa' }}
              expandIcon={({ isActive }) => <CaretRightOutlined rotate={isActive ? 90 : 0} />}
              items={[{
                key: '1',
                label: <Text type="secondary" style={{ fontSize: '12px' }}><RobotOutlined style={{ marginRight: 6 }} />内核深度思考记录 {!p.isClosed && <SyncOutlined spin style={{ marginLeft: 8 }} />}</Text>,
                children: <div style={{ fontSize: '13px', color: '#666', borderLeft: '2px solid #ddd', paddingLeft: 12 }}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{p.content}</ReactMarkdown>
                </div>
              }]}
            />
          );
        }
        if (p.type === 'collaboration') {
          if (!p.isClosed) {
            return (
                <div key={i} style={{ 
                    marginBottom: 16, 
                    padding: '12px 16px', 
                    background: '#e6f7ff', 
                    border: '1px solid #91d5ff', 
                    borderRadius: '8px',
                    borderLeft: '4px solid #1890ff',
                    animation: 'fadeIn 0.3s ease-out'
                }}>
                    <Space style={{ marginBottom: 8 }}>
                        <SyncOutlined spin style={{ color: '#1890ff' }} />
                        <Text strong style={{ color: '#0050b3' }}>Swarm 专家正在输出中...</Text>
                    </Space>
                    <div style={{ color: '#003a8c', fontSize: '14px' }}>
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{p.content}</ReactMarkdown>
                    </div>
                </div>
            );
          }
          return (
            <Collapse
              key={i}
              ghost
              style={{ 
                  marginBottom: 16, 
                  border: '1px solid #d9f7be', 
                  borderRadius: '12px', 
                  background: 'linear-gradient(to right, #f6ffed, #ffffff)',
                  overflow: 'hidden'
              }}
              expandIcon={({ isActive }) => <CaretRightOutlined rotate={isActive ? 90 : 0} style={{ color: '#389e0d' }} />}
              items={[{
                key: '1',
                label: (
                    <Space>
                        <PartitionOutlined style={{ color: '#52c41a' }} />
                        <Text strong style={{ fontSize: '13px', color: '#135200' }}>Swarm 专家协同建议 (已完成)</Text>
                    </Space>
                ),
                children: <div style={{ fontSize: '14px', color: '#237804', paddingBottom: 4 }}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{p.content}</ReactMarkdown>
                </div>
              }]}
            />
          );
        }
        if (p.type === 'tool') {
          return (
            <Tag 
                key={i} 
                color="blue" 
                style={{ 
                    marginBottom: 12, 
                    display: 'inline-flex', 
                    alignItems: 'center', 
                    padding: '4px 10px',
                    borderRadius: '4px'
                }}
            >
              <PartitionOutlined style={{ marginRight: 6 }} /> 
              {p.content}
            </Tag>
          );
        }
        return (
          <ReactMarkdown
            key={i}
            remarkPlugins={[remarkGfm]}
            components={{
              code({ node, inline, className, children, ...props }: any) {
                const match = /language-(\w+)/.exec(className || '');
                return !inline && match ? (
                  <SyntaxHighlighter
                    style={isDark ? oneDark : oneLight}
                    language={match[1]}
                    PreTag="div"
                    {...props}
                  >
                    {String(children).replace(/\n$/, '')}
                  </SyntaxHighlighter>
                ) : (
                  <code className={className} {...props}>
                    {children}
                  </code>
                );
              }
            }}
          >
            {p.content}
          </ReactMarkdown>
        );
      })}
    </div>
  );
};

const ChatView: React.FC<ChatViewProps> = ({
  messages, loading, inputText, setInputText,
  currentAgent, enableMemory, setEnableMemory,
  enableSwarm, setEnableSwarm, onSend,
  pendingImages, setPendingImages
}) => {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  return (
    <div style={{ 
      flex: 1, 
      display: 'flex', 
      flexDirection: 'column', 
      overflow: 'hidden', 
      background: 'var(--bg-main)',
      position: 'relative'
    }}>
      <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: '24px 0' }}>
        <div style={{ maxWidth: '900px', margin: '0 auto', padding: '0 24px' }}>
          
          {messages.length === 0 ? (
            <div style={{ height: '70vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Empty description={<Text type="secondary">UniAI 协作内核已就绪，请输入指令</Text>} />
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {messages.map(m => (
                <div
                  key={m.id}
                  style={{
                    display: 'flex',
                    justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start',
                    marginBottom: '24px',
                    width: '100%'
                  }}
                >
                  {m.role === 'system' ? (
                    <div style={{
                      width: '100%', textAlign: 'center',
                      padding: '8px 16px', fontSize: '12px',
                      color: 'var(--text-secondary)', background: 'var(--msg-system-bg)',
                      borderRadius: '4px', border: '1px solid var(--border-color)'
                    }}>
                      {m.content}
                    </div>
                  ) : (
                    <div style={{
                      display: 'flex',
                      flexDirection: m.role === 'user' ? 'row-reverse' : 'row',
                      gap: '12px', maxWidth: '85%'
                    }}>
                      <div style={{ flexShrink: 0, paddingTop: '2px' }}>
                        <Avatar 
                          size={32} 
                          icon={m.role === 'user' ? <UserOutlined /> : <RobotOutlined />} 
                          style={{ 
                            background: m.role === 'user' ? 'var(--primary-blue)' : '#fff',
                            color: m.role === 'user' ? '#fff' : 'var(--primary-blue)',
                            border: '1px solid var(--border-color)',
                            boxShadow: '0 2px 4px rgba(0,0,0,0.05)'
                          }} 
                        />
                      </div>
                      <div 
                        className="pro-card"
                        style={{
                          padding: '12px 16px',
                          background: m.role === 'user' ? 'var(--primary-blue)' : '#fff',
                          color: m.role === 'user' ? '#fff' : 'var(--text-primary)',
                          borderRadius: '8px',
                          borderTopRightRadius: m.role === 'user' ? '2px' : '8px',
                          borderTopLeftRadius: m.role === 'assistant' ? '2px' : '8px',
                          fontSize: '14px',
                          lineHeight: '1.6',
                          wordBreak: 'break-word'
                        }}
                      >
                        {m.agentName && m.role === 'assistant' && (
                          <div style={{ 
                            fontSize: '11px', 
                            fontWeight: 600,
                            color: 'var(--primary-blue)',
                            marginBottom: 4
                          }}>
                            {m.agentName}
                          </div>
                        )}
                        <MessageContent content={m.content} role={m.role} />
                         {m.images && m.images.length > 0 && (
                            <div style={{ marginTop: 12, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                                {m.images.map((img, idx) => (
                                    <img 
                                      key={idx} src={img} alt="msg-img" 
                                      style={{ maxWidth: '100%', borderRadius: 4, maxHeight: 400, border: '1px solid var(--border-color)' }} 
                                    />
                                ))}
                            </div>
                         )}
                       </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {loading && (
            <div style={{ padding: '0 44px', display: 'flex', gap: 12, alignItems: 'center', marginTop: -12 }}>
                <SyncOutlined spin style={{ color: 'var(--primary-blue)' }} />
                <Text type="secondary" style={{ fontSize: '13px' }}>
                  {currentAgent?.name} 正在响应中...
                </Text>
            </div>
          )}
        </div>
      </div>

      <div style={{ 
        padding: '20px 24px 32px', 
        background: '#fff',
        borderTop: '1px solid var(--border-color)',
        boxShadow: '0 -2px 10px rgba(0,0,0,0.02)'
       }}>
        <div style={{ maxWidth: '900px', margin: '0 auto' }}>
          {pendingImages.length > 0 && (
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
                {pendingImages.map((img, idx) => (
                    <div key={idx} style={{ position: 'relative' }}>
                        <img src={img} style={{ width: 60, height: 60, objectFit: 'cover', borderRadius: 4, border: '1px solid var(--border-color)' }} />
                        <div 
                            onClick={() => setPendingImages(prev => prev.filter((_, i) => i !== idx))}
                            style={{ 
                              position: 'absolute', top: -6, right: -6, 
                              background: '#ff4d4f', color: '#fff', borderRadius: '50%', 
                              width: 18, height: 18, display: 'flex', alignItems: 'center', 
                              justifyContent: 'center', cursor: 'pointer', fontSize: 10
                            }}
                        >✕</div>
                    </div>
                ))}
            </div>
          )}
          <div style={{ display: 'flex', gap: '16px', marginBottom: '12px', alignItems: 'center' }}>
            <Space size={0} split={<Divider type="vertical" />}>
                <Button 
                    type="text" 
                    icon={<HistoryOutlined />} 
                    size="small"
                    onClick={() => setEnableMemory(!enableMemory)}
                    style={{ color: enableMemory ? 'var(--primary-blue)' : 'var(--text-secondary)' }}
                >
                    长效记忆
                </Button>
                <Button 
                    type="text" 
                    icon={<PartitionOutlined />} 
                    size="small"
                    onClick={() => setEnableSwarm(!enableSwarm)}
                    style={{ color: enableSwarm ? '#52c41a' : 'var(--text-secondary)' }}
                >
                    Swarm 协作
                </Button>
            </Space>
            
            <div style={{ flex: 1 }} />
            
            <Button 
                type="text" 
                icon={<PlusOutlined />} 
                size="small"
                onClick={() => document.getElementById('img-upload')?.click()}
                style={{ color: 'var(--text-secondary)' }}
            >
                上传素材
            </Button>
            
            <input 
                type="file" 
                id="img-upload" 
                style={{ display: 'none' }} 
                accept="image/*"
                onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) {
                        const reader = new FileReader();
                        reader.onload = (ev) => {
                            const base64 = ev.target?.result as string;
                            setPendingImages(prev => [...prev, base64]);
                        };
                        reader.readAsDataURL(file);
                    }
                }}
            />
          </div>
          
          <div style={{ 
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            background: '#fff',
            border: '1px solid var(--border-color)',
            borderRadius: '4px',
            paddingRight: '8px'
          }}>
            <Input.TextArea 
                placeholder={currentAgent ? `向 ${currentAgent.name} 发送指令...` : "请先选择一个专家"}
                autoSize={{ minRows: 1, maxRows: 6 }}
                variant="borderless"
                style={{ flex: 1, padding: '12px 16px', color: 'var(--text-primary)' }}
                value={inputText}
                onChange={e => setInputText(e.target.value)}
                onPressEnter={(e) => {
                  if (!e.shiftKey) { e.preventDefault(); onSend(); }
                }}
                onPaste={(e) => {
                    const items = e.clipboardData?.items;
                    if (!items) return;
                    for (let i = 0; i < items.length; i++) {
                        if (items[i].type.indexOf('image') !== -1) {
                            const file = items[i].getAsFile();
                            if (file) {
                                const reader = new FileReader();
                                reader.onload = (ev) => {
                                    const base64 = ev.target?.result as string;
                                    setPendingImages(prev => [...prev, base64]);
                                };
                                reader.readAsDataURL(file);
                            }
                        }
                    }
                }}
                disabled={!currentAgent}
            />
            <Button 
                type="primary" 
                icon={<SendOutlined />} 
                onClick={onSend}
                loading={loading}
                disabled={!currentAgent || (!inputText.trim() && pendingImages.length === 0)}
                style={{ 
                  background: 'var(--primary-blue)',
                  border: 'none',
                  height: '36px'
                }}
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatView;
export type { Message, Agent };
