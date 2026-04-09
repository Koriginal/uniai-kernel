import React, { useRef, useEffect, useState } from 'react';
import { Typography, Avatar, Input, Empty, Space, Divider, Button, Tooltip, message } from 'antd';
import { 
  AppstoreAddOutlined, CopyOutlined, CheckOutlined, SyncOutlined, ExpandOutlined, PartitionOutlined, RobotOutlined, 
  UserOutlined, HistoryOutlined, PlusOutlined, CaretRightOutlined, CaretDownOutlined, EditOutlined, DeleteOutlined, LikeOutlined, 
  DislikeOutlined, BorderOutlined, ReloadOutlined, LikeFilled, DislikeFilled, SendOutlined, InfoCircleOutlined,
  LineChartOutlined, CheckCircleOutlined, ThunderboltFilled
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';

const { Text } = Typography;

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string | any[];
  timestamp: number;
  agentName?: string;
  images?: string[]; 
  feedback?: 'like' | 'dislike' | 'null';
  tool_calls?: { id: string; function: { name: string; arguments: string; }; }[];
}

export interface Agent {
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
  onStop?: () => void;
  onDeleteMessage?: (id: string) => void;
  onEditMessage?: (id: string, content: string) => void;
  onFeedbackMessage?: (id: string, feedback: 'like' | 'dislike' | 'null') => void;
  onRegenerate?: () => void;
  pendingImages: string[];
  setPendingImages: (v: string[] | ((prev: string[]) => string[])) => void;
  onOpenCanvas?: (title: string, content: string, type: 'markdown' | 'code', language?: string, msgId?: string) => void;
  enableAutoCanvas?: boolean;
  setEnableAutoCanvas?: (v: boolean) => void;
  collaborationStatus?: { agentName?: string, content?: string, state: 'active' | 'completed' | null };
}

const CodeBlock = ({ language, children, onOpenCanvas }: { language: string, children: string, onOpenCanvas?: any }) => {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => { navigator.clipboard.writeText(children).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000); }); };
  return (
    <div style={{ position: 'relative', margin: '12px 0', borderRadius: '8px', overflow: 'hidden', border: '1px solid #f0f0f0' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 12px', background: '#f8f8f8', borderBottom: '1px solid #eee', fontSize: '12px', color: '#666' }}>
        <Space size={12}><span>{language || 'code'}</span></Space>
        <Space size={12}>
          <Button type="text" size="small" icon={<ExpandOutlined />} onClick={() => onOpenCanvas?.(`${language} 画布`, children, 'code', language)} />
          <Button type="text" size="small" icon={copied ? <CheckOutlined style={{ color: '#52c41a' }} /> : <CopyOutlined />} onClick={handleCopy} />
        </Space>
      </div>
      <SyntaxHighlighter 
        style={oneLight} 
        language={language} 
        PreTag="div" 
        wrapLongLines={true}
        customStyle={{ 
          margin: 0, 
          padding: '12px', 
          background: '#fff', 
          fontSize: '13px', 
          whiteSpace: 'pre-wrap', 
          wordBreak: 'break-word',
          overflowWrap: 'break-word',
          maxWidth: '100%'
        }}
        codeTagProps={{
          style: {
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            display: 'block'
          }
        }}
      >
        {children}
      </SyntaxHighlighter>
    </div>
  );
};

// 内部协作折叠块组件：通过 isGenerating 判断自动展开/折叠
const CollaborationBlock: React.FC<{ title: string; children: React.ReactNode; isGenerating?: boolean }> = ({ title, children, isGenerating = false }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  
  // 流式生成期间保持展开，一旦生成结束，自动折叠
  useEffect(() => {
    setIsExpanded(!!isGenerating);
  }, [isGenerating]);

  return (
    <div style={{ 
      margin: '12px 0', border: '1px solid #d9f7be', borderRadius: '8px', 
      background: '#f6ffed', overflow: 'hidden' 
    }}>
      <div 
        onClick={() => setIsExpanded(!isExpanded)}
        style={{ 
          padding: '8px 16px', display: 'flex', alignItems: 'center', gap: 8, 
          cursor: 'pointer', userSelect: 'none', color: '#52c41a', fontWeight: 500,
          background: isExpanded ? 'rgba(82, 196, 26, 0.05)' : 'transparent'
        }}
      >
        <PartitionOutlined />
        <span style={{ fontSize: '13px' }}>{title || '协作专家'} 处理详情</span>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', opacity: 0.6 }}>
          {isExpanded ? <CaretDownOutlined /> : <CaretRightOutlined />}
        </div>
      </div>
      {isExpanded && (
        <div style={{ 
          padding: '12px 16px', borderTop: '1px solid #d9f7be', 
          background: '#fff', fontSize: '13px' 
        }}>
          {children}
        </div>
      )}
    </div>
  );
};

const MessageContent = React.memo(({ content, loading, onOpenCanvas, collaborationStatus }: { 
  content: string | any[], 
  loading?: boolean, 
  onOpenCanvas?: any,
  collaborationStatus?: { agentName?: string, content?: string, state: 'active' | 'completed' | null } 
}) => {
  const textContent = typeof content === 'string' ? content : (Array.isArray(content) ? content.map(item => item.type === 'text' ? item.text : '').join('\n') : '');
  const preprocessMath = (text: string) => text
    .replace(/\\\[/g, '$$$$').replace(/\\\]/g, '$$$$')
    .replace(/\\\(/g, '$$').replace(/\\\)/g, '$$')
    .replace(/\\r\\n/g, '\n').replace(/\\r/g, '\n');
  
  // 状态归并逻辑：
  // 如果当前消息所属的模型正在通过全局协作条显示进度，则气泡内不再显示重复的长占位符
  const isExpertActive = loading && collaborationStatus?.state === 'active';

  const renderParts = () => {
    const parts: React.ReactNode[] = [];
    const regex = /<collaboration\s+title=['"](.*?)['"]>([\s\S]*?)(?:<\/collaboration>|$)/g;
    let lastIndex = 0;
    let match;

    const cleanContent = textContent.replace(/<\/collaboration>\s*<\/collaboration>/g, '</collaboration>');
    
    while ((match = regex.exec(cleanContent)) !== null) {
      let beforeText = cleanContent.substring(lastIndex, match.index);
      if (beforeText) {
        parts.push(
          <ReactMarkdown 
            key={`md-${lastIndex}`}
            remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}
            components={{
              code({ node, inline, className, children, ...props }: any) {
                const matchCode = /language-(\w+)/.exec(className || '');
                const codeVal = String(children).replace(/\n$/, '');
                return !inline && matchCode ? <CodeBlock language={matchCode[1]} onOpenCanvas={onOpenCanvas}>{codeVal}</CodeBlock> : <code className={className} {...props} style={{ background: '#f5f5f5', padding: '2px 4px', borderRadius: '4px' }}>{children}</code>;
              }
            }}
          >
            {preprocessMath(beforeText)}
          </ReactMarkdown>
        );
      }

      const [fullMatch, title, collabContent] = match;
      const safeCollabContent = collabContent.replace(/<collaboration[^>]*>/g, '').replace(/<\/collaboration>/g, '').trim();
      
      const finalDisplayContent = safeCollabContent || (isExpertActive ? "" : (loading ? "_专家计算中..._" : "_专家已完成任务协同_"));
      
      if (finalDisplayContent || isExpertActive) {
          parts.push(
            <CollaborationBlock key={`collab-${match.index}`} title={title} isGenerating={loading}>
              <ReactMarkdown 
                remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}
                components={{
                  code({ node, inline, className, children, ...props }: any) {
                    const matchCode = /language-(\w+)/.exec(className || '');
                    const codeVal = String(children).replace(/\n$/, '');
                    return !inline && matchCode ? <CodeBlock language={matchCode[1]} onOpenCanvas={onOpenCanvas}>{codeVal}</CodeBlock> : <code className={className} {...props} style={{ background: '#f5f5f5', padding: '2px 4px', borderRadius: '4px' }}>{children}</code>;
                  }
                }}
              >
                {preprocessMath(finalDisplayContent)}
              </ReactMarkdown>
            </CollaborationBlock>
          );
      }
      lastIndex = match.index + fullMatch.length;
    }

    let remainingText = cleanContent.substring(lastIndex);
    remainingText = remainingText.replace(/<\/collaboration>/g, '').trim();
    if (remainingText) {
      parts.push(
        <ReactMarkdown 
          key={`md-remaining-${lastIndex}`}
          remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}
          components={{
            code({ node, inline, className, children, ...props }: any) {
              const matchCode = /language-(\w+)/.exec(className || '');
              const codeVal = String(children).replace(/\n$/, '');
              return !inline && matchCode ? <CodeBlock language={matchCode[1]} onOpenCanvas={onOpenCanvas}>{codeVal}</CodeBlock> : <code className={className} {...props} style={{ background: '#f5f5f5', padding: '2px 4px', borderRadius: '4px' }}>{children}</code>;
            }
          }}
        >
          {preprocessMath(remainingText)}
        </ReactMarkdown>
      );
    }

    return parts;
  };

  return (
    <div className="message-markdown-content" style={{ fontSize: '14px', lineHeight: '1.6', wordBreak: 'break-word', whiteSpace: 'pre-wrap', maxWidth: '100%', overflowWrap: 'break-word' }}>
      {renderParts()}
      {loading && !isExpertActive && <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#1890ff', fontSize: '12px', marginTop: 8 }}><SyncOutlined spin />续写中...</div>}
    </div>
  );
}, (prevProps, nextProps) => {
  // 只有当内容、加载状态或协作状态发生变化时才更新
  return (
    prevProps.content === nextProps.content && 
    prevProps.loading === nextProps.loading &&
    prevProps.collaborationStatus?.state === nextProps.collaborationStatus?.state &&
    prevProps.collaborationStatus?.content === nextProps.collaborationStatus?.content
  );
});

const ChatView: React.FC<ChatViewProps> = (props) => {
  const { messages, loading, collaborationStatus, inputText, setInputText, currentAgent, enableMemory, setEnableMemory, enableSwarm, setEnableSwarm, onSend, onStop, onDeleteMessage, onEditMessage, onFeedbackMessage, onRegenerate, pendingImages, setPendingImages, onOpenCanvas, enableAutoCanvas, setEnableAutoCanvas } = props;
  const scrollRef = useRef<HTMLDivElement>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState('');
  const [hoveredMessageId, setHoveredMessageId] = useState<string | null>(null);
  const [isIME, setIsIME] = useState(false);
  

  const groupMessagesIntoTurns = (msgs: Message[]) => {
    const turns: { id: string, role: string, messages: Message[] }[] = [];
    msgs.forEach((m, idx) => {
      if (idx > 0 && m.role === msgs[idx-1].role && m.role === 'assistant') turns[turns.length - 1].messages.push(m);
      else turns.push({ id: m.id || `turn-${idx}`, role: m.role, messages: [m] });
    });
    return turns;
  };
  const messageTurns = groupMessagesIntoTurns(messages);

  useEffect(() => {
    if (scrollRef.current) {
        const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
        if (scrollHeight - scrollTop - clientHeight < 200) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);


  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: '#fff', position: 'relative' }}>
      <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: '24px 0', scrollBehavior: 'smooth' }}>
        <div style={{ maxWidth: '900px', margin: '0 auto', padding: '0 24px' }}>
          {messages.length === 0 ? (
            <div style={{ height: '70vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Empty description="UniAI 协作引擎已就绪" /></div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {messageTurns.map((turn, tIdx) => {
                const isUser = turn.role === 'user';
                const isAssistant = turn.role === 'assistant';
                const isSystem = turn.role === 'system';
                const isLastTurn = tIdx === messageTurns.length - 1;

                return (
                  <div key={turn.id} style={{ marginBottom: 32, width: '100%', position: 'relative' }}>
                    {isSystem ? (
                      <div style={{ width: '100%', textAlign: 'center', padding: '6px 16px', fontSize: '12px', color: 'rgba(0,0,0,0.45)', background: '#fafafa', borderRadius: '4px' }}>{turn.messages.map(m => (typeof m.content === 'string' ? m.content : '')).join('\n')}</div>
                    ) : (
                      <div style={{ display: 'flex', flexDirection: isUser ? 'row-reverse' : 'row', gap: '16px', maxWidth: '98%', position: 'relative' }}>
                        <div style={{ flexShrink: 0, width: 34 }}><Avatar size={34} icon={isUser ? <UserOutlined /> : <RobotOutlined />} style={{ background: isUser ? '#1890ff' : '#fff', color: isUser ? '#fff' : '#1890ff', border: '1px solid #eee' }} /></div>
                        
                        <div style={{ display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start', flex: 1, minWidth: 0 }}>
                          <div style={{ position: 'relative', width: isAssistant ? '100%' : 'auto' }}>
                            {turn.messages.map((m, mIdx) => {
                               const isLastInTurn = mIdx === turn.messages.length - 1;
                               const isMsgGenerating = loading && isLastTurn && isLastInTurn;
                               
                               return (
                                  <div key={m.id || m.timestamp} 
                                       onMouseEnter={() => setHoveredMessageId(m.id)} 
                                       onMouseLeave={() => setHoveredMessageId(null)} 
                                       style={{ marginBottom: isLastInTurn ? 0 : 20, display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start', width: '100%' }}>
                                      
                                      {/* [BUBBLE] 仅包裹消息内容与图片 */}
                                      <div style={{
                                        padding: '12px 16px', 
                                        background: isUser ? '#1890ff' : '#fff', 
                                        color: isUser ? '#fff' : 'rgba(0,0,0,0.85)',
                                        borderRadius: '16px', 
                                        borderTopRightRadius: (isUser && isLastInTurn) ? '2px' : '16px', 
                                        borderTopLeftRadius: (isAssistant && isLastInTurn) ? '2px' : '16px',
                                        fontSize: '15px', 
                                        lineHeight: '1.7', 
                                        boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
                                        border: isUser ? 'none' : '1px solid #f0f0f0', 
                                        position: 'relative', 
                                        width: isUser ? 'fit-content' : '100%', 
                                        maxWidth: '100%',
                                        wordBreak: 'break-word',
                                        overflowWrap: 'break-word',
                                        boxSizing: 'border-box'
                                      }}>
                                        {m.agentName && isAssistant && turn.messages.length > 1 && (
                                          <div style={{ fontSize: '11px', fontWeight: 600, color: isUser ? '#fff' : '#1890ff', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6, opacity: isUser ? 0.9 : 1 }}>
                                            <PartitionOutlined style={{ fontSize: 13 }} /><span>{m.agentName}</span>
                                          </div>
                                        )}
                                        {editingId === m.id ? (
                                          <div style={{ minWidth: '400px' }}><Input.TextArea autoSize={{ minRows: 2 }} value={editingText} onChange={e => setEditingText(e.target.value)} style={{ marginBottom: 12, borderRadius: 8 }} /><Space><Button size="small" type="primary" onClick={() => { onEditMessage?.(m.id, editingText); setEditingId(null); }}>保存</Button><Button size="small" onClick={() => setEditingId(null)}>取消</Button></Space></div>
                                        ) : (
                                          <MessageContent 
                                            content={m.content} 
                                            loading={isMsgGenerating} 
                                            onOpenCanvas={onOpenCanvas} 
                                            collaborationStatus={collaborationStatus}
                                          />
                                        )}
                                        {m.images && m.images.length > 0 && (
                                            <div style={{ marginTop: 16, display: 'flex', flexWrap: 'wrap', gap: 10 }}>
                                                {m.images.map((img, idx) => (<img key={idx} src={img} alt="msg-img" style={{ maxWidth: '100%', borderRadius: 8, maxHeight: 400, border: '1px solid #f0f0f0' }} />))}
                                            </div>
                                        )}
                                      </div>

                                      {/* [ACTIONS] 彻底置于气泡之外 */}
                                      {hoveredMessageId === m.id && !editingId && !loading && (
                                          <div style={{ 
                                              marginTop: 6,
                                              display: 'flex',
                                              justifyContent: isUser ? 'flex-end' : 'flex-start',
                                              alignItems: 'center',
                                              width: '100%',
                                              animation: 'fadeIn 0.2s ease-in-out'
                                          }}>
                                              <div style={{ 
                                                  padding: '2px 8px', 
                                                  background: 'rgba(255, 255, 255, 0.8)', 
                                                  backdropFilter: 'blur(12px)',
                                                  borderRadius: '12px', 
                                                  border: '1px solid #f0f0f0', 
                                                  display: 'flex', 
                                                  gap: 6, 
                                                  alignItems: 'center',
                                                  boxShadow: '0 2px 10px rgba(0,0,0,0.05)'
                                              }} className="message-action-bar">
                                                  {isUser ? (
                                                    <>
                                                      <Tooltip title="复制内容"><CopyOutlined style={{ fontSize: 12, cursor: 'pointer', color: '#999' }} onClick={() => { navigator.clipboard.writeText(typeof m.content === 'string' ? m.content : ""); message.success('已复制到剪贴板'); }} /></Tooltip>
                                                      <Tooltip title="编辑"><EditOutlined style={{ fontSize: 12, cursor: 'pointer', color: '#999' }} onClick={() => { setEditingId(m.id); setEditingText(typeof m.content === 'string' ? m.content : ""); }} /></Tooltip>
                                                      <div style={{ width: 1, height: 10, background: '#eee', margin: '0 2px' }} />
                                                      <Tooltip title="撤回"><DeleteOutlined style={{ fontSize: 12, cursor: 'pointer', color: '#ff4d4f' }} onClick={() => onDeleteMessage?.(m.id)} /></Tooltip>
                                                    </>
                                                  ) : (
                                                    <>
                                                      <Tooltip title="复制结果"><CopyOutlined style={{ fontSize: 12, cursor: 'pointer', color: '#999' }} onClick={() => { navigator.clipboard.writeText(typeof m.content === 'string' ? m.content : ""); message.success('已复制到剪贴板'); }} /></Tooltip>
                                                      <Tooltip title="重新生成"><ReloadOutlined style={{ fontSize: 12, cursor: 'pointer', color: '#999' }} onClick={() => onRegenerate?.()} /></Tooltip>
                                                      <Tooltip title="投至看板"><AppstoreAddOutlined style={{ fontSize: 12, cursor: 'pointer', color: '#1890ff' }} onClick={() => { const text = typeof m.content === 'string' ? m.content : JSON.stringify(m.content); onOpenCanvas?.('快照', text, 'markdown'); }} /></Tooltip>
                                                      <div style={{ width: 1, height: 10, background: '#eee', margin: '0 2px' }} />
                                                      {m.feedback === 'like' ? <LikeFilled style={{ fontSize: 12, color: '#1890ff', cursor: 'pointer' }} onClick={() => onFeedbackMessage?.(m.id, 'null')} /> : <LikeOutlined style={{ fontSize: 12, color: '#999', cursor: 'pointer' }} onClick={() => onFeedbackMessage?.(m.id, 'like')} />}
                                                      {m.feedback === 'dislike' ? <DislikeFilled style={{ fontSize: 12, color: '#ff4d4f', cursor: 'pointer' }} onClick={() => onFeedbackMessage?.(m.id, 'null')} /> : <DislikeOutlined style={{ fontSize: 12, color: '#999', cursor: 'pointer' }} onClick={() => onFeedbackMessage?.(m.id, 'dislike')} />}
                                                      <div style={{ width: 1, height: 10, background: '#eee', margin: '0 2px' }} />
                                                      <Tooltip title="清除消息"><DeleteOutlined style={{ fontSize: 12, cursor: 'pointer', color: '#999' }} onClick={() => onDeleteMessage?.(m.id)} /></Tooltip>
                                                    </>
                                                  )}
                                              </div>
                                          </div>
                                      )}
                                  </div>
                               );
                            })}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          {loading && collaborationStatus?.state === 'active' && (
              <div style={{ padding: '0 54px', display: 'flex', gap: 12, alignItems: 'center', marginTop: -16, marginBottom: 24 }}>
                  <SyncOutlined spin style={{ color: '#52c41a' }} />
                  <Text style={{ fontSize: '14px', color: '#389e0d', fontWeight: 500 }}>
                    {collaborationStatus.agentName} {collaborationStatus.content || '正在深入协作中...'}
                  </Text>
              </div>
          )}
        </div>
      </div>

      <div style={{ padding: '24px', background: '#fff', borderTop: '1px solid #f0f0f0' }}>
        <div style={{ maxWidth: '900px', margin: '0 auto' }}>
          {pendingImages.length > 0 && (
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
                {pendingImages.map((img, idx) => (
                    <div key={idx} style={{ position: 'relative' }}>
                        <img src={img} style={{ width: 64, height: 64, objectFit: 'cover', borderRadius: 8, border: '1px solid #eee' }} />
                        <div onClick={() => setPendingImages(prev => prev.filter((_, i) => i !== idx))} style={{ position: 'absolute', top: -8, right: -8, background: '#ff4d4f', color: '#fff', borderRadius: '50%', width: 20, height: 20, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', fontSize: 10 }}>✕</div>
                    </div>
                ))}
            </div>
          )}
          
          <div style={{ display: 'flex', gap: '16px', marginBottom: '12px' }}>
            <Space size={0} split={<Divider type="vertical" />}>
                <Button type="text" icon={<HistoryOutlined />} size="small" onClick={() => setEnableMemory(!enableMemory)} style={{ color: enableMemory ? '#1890ff' : '#999' }}>长效记忆</Button>
                <Button type="text" icon={<PartitionOutlined />} size="small" onClick={() => setEnableSwarm(!enableSwarm)} style={{ color: enableSwarm ? '#52c41a' : '#999' }}>Swarm 协作</Button>
                <Button type="text" icon={<AppstoreAddOutlined />} size="small" onClick={() => setEnableAutoCanvas?.(!enableAutoCanvas)} style={{ color: enableAutoCanvas ? '#eb2f96' : '#999' }}>自动看板</Button>
            </Space>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12, background: '#f9f9f9', border: '1px solid #e8e8e8', borderRadius: '24px', padding: '4px 12px' }}>
            <Button type="text" shape="circle" icon={<PlusOutlined style={{ fontSize: 20, color: '#999' }} />} onClick={() => document.getElementById('img-upload')?.click()} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 32, height: 32, flexShrink: 0 }} />
            <input type="file" id="img-upload" style={{ display: 'none' }} accept="image/*" onChange={(e) => { const file = e.target.files?.[0]; if (file) { const reader = new FileReader(); reader.onload = (ev) => setPendingImages(prev => [...prev, ev.target?.result as string]); reader.readAsDataURL(file); } }} />
            <Input.TextArea placeholder={currentAgent ? `向 ${currentAgent.name} 发送指令...` : "请先选择一个专家"} autoSize={{ minRows: 1, maxRows: 12 }} variant="borderless" style={{ flex: 1, padding: '8px 0', fontSize: '15px', lineHeight: '20px' }} value={inputText} onChange={e => setInputText(e.target.value)} onCompositionStart={() => setIsIME(true)} onCompositionEnd={() => setIsIME(false)} onKeyDown={(e) => { if (e.key === 'Enter' && !isIME && !e.shiftKey) { e.preventDefault(); onSend(); } }} />
            <div style={{ display: 'flex', alignItems: 'center', flexShrink: 0 }}>
                {loading ? <Button type="primary" shape="circle" danger icon={<BorderOutlined style={{ fontSize: 10 }} />} onClick={onStop} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 32, height: 32 }} /> : <Button type="primary" shape="circle" icon={<SendOutlined style={{ fontSize: 16 }} />} onClick={onSend} disabled={!currentAgent || (!inputText.trim() && pendingImages.length === 0)} style={{ width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center' }} />}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatView;
