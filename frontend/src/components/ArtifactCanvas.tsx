import React from 'react';
import { Typography, Button, Space, Empty, Tabs, Tooltip } from 'antd';
import { 
  CloseOutlined, 
  CopyOutlined, 
  CheckOutlined,
  CodeOutlined,
  FileTextOutlined,
  EyeOutlined,
  DownloadOutlined
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import 'katex/dist/katex.min.css';

const { Title, Text } = Typography;

interface ArtifactCanvasProps {
  visible: boolean;
  onClose: () => void;
  title: string;
  content: string | null;
  type: 'markdown' | 'code' | 'html';
  language?: string;
  loading?: boolean;
}

const ArtifactCanvas: React.FC<ArtifactCanvasProps> = ({
  visible,
  onClose,
  title,
  content,
  type,
  language,
  loading
}) => {
  const [copied, setCopied] = React.useState(false);
  const [activeTab, setActiveTab] = React.useState<'preview' | 'code'>('preview');

  // 当内容类型变化或重新开启时，重置默认 Tab
  React.useEffect(() => {
    if (visible) {
      setActiveTab(type === 'code' ? 'code' : 'preview');
    }
  }, [visible, type]);

  if (!visible) return null;

  const handleCopy = () => {
    if (!content) return;
    navigator.clipboard.writeText(content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const handleDownload = () => {
    if (!content) return;
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = title || 'artifact.txt';
    a.click();
    URL.revokeObjectURL(url);
  };

  const renderTabs = () => {
    const items = [
      {
        key: 'preview',
        label: (
          <span>
            <EyeOutlined /> 预览
          </span>
        ),
      },
      {
        key: 'code',
        label: (
          <span>
            <CodeOutlined /> 源代码
          </span>
        ),
      },
    ];

    // 如果只是 markdown，不显示选项卡切换，直接显示预览
    if (type === 'markdown') return null;

    return (
      <Tabs 
        activeKey={activeTab} 
        onChange={(key) => setActiveTab(key as any)}
        size="small"
        className="canvas-tabs"
        items={items}
        style={{ marginBottom: 0 }}
      />
    );
  };

  return (
    <div style={{
      width: '520px',
      height: '100%',
      background: '#fff',
      borderLeft: '1px solid #e8e8e8',
      display: 'flex',
      flexDirection: 'column',
      flexShrink: 0,
      boxShadow: '-4px 0 12px rgba(0,0,0,0.03)',
      zIndex: 100,
      transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)'
    }}>
      {/* Header */}
      <div style={{
        padding: '10px 16px',
        borderBottom: '1px solid #f0f0f0',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        background: '#fff'
      }}>
        <Space direction="vertical" size={0}>
          <Space size={8}>
            <div style={{ 
              width: 24, height: 24, 
              borderRadius: 6, 
              background: type === 'html' ? '#722ed1' : (type === 'code' ? '#1890ff' : '#52c41a'), 
              display: 'flex', alignItems: 'center', justifyContent: 'center' 
            }}>
              {type === 'code' ? <CodeOutlined style={{ color: '#fff', fontSize: 12 }} /> : 
               (type === 'html' ? <RocketOutlined style={{ color: '#fff', fontSize: 12 }} /> : <FileTextOutlined style={{ color: '#fff', fontSize: 12 }} />)}
            </div>
            <Title level={5} style={{ margin: 0, fontSize: '14px', fontWeight: 600 }}>{title}</Title>
          </Space>
          {loading && <Text type="secondary" style={{ fontSize: '11px', animation: 'blink 1.5s infinite' }}>正在接收流式内容...</Text>}
        </Space>
        <Space size={4}>
          <Tooltip title="下载">
             <Button type="text" size="small" icon={<DownloadOutlined />} onClick={handleDownload} />
          </Tooltip>
          <Button 
            type="text" 
            size="small" 
            icon={copied ? <CheckOutlined style={{ color: '#52c41a' }} /> : <CopyOutlined />} 
            onClick={handleCopy}
          />
          <Button 
            type="text" 
            size="small" 
            icon={<CloseOutlined />} 
            onClick={onClose} 
          />
        </Space>
      </div>

      {/* Tabs Row (Only for non-markdown types) */}
      <div style={{ padding: '0 16px', background: '#fff', borderBottom: '1px solid #f0f0f0' }}>
        {renderTabs()}
      </div>

      {/* Content Area */}
      <div style={{ 
        flex: 1, 
        overflowY: 'auto', 
        padding: (activeTab === 'preview' && type === 'markdown') ? '24px' : '0',
        background: '#fff',
        position: 'relative'
      }}>
        {!content && !loading ? (
          <Empty description="等待投射内容..." style={{ marginTop: '30%' }} />
        ) : (
          <>
            {activeTab === 'preview' ? (
              type === 'html' ? (
                <iframe
                  title="Canvas Preview"
                  srcDoc={content || ''}
                  style={{
                    width: '100%',
                    height: '100%',
                    border: 'none',
                    background: '#fff'
                  }}
                  sandbox="allow-scripts"
                />
              ) : (
                <div className="canvas-markdown" style={{ fontSize: '15px', lineHeight: '1.7', color: '#2c3e50' }}>
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm, remarkMath]}
                    rehypePlugins={[rehypeKatex]}
                    components={{
                      code({ node, inline, className, children, ...props }: any) {
                        const match = /language-(\w+)/.exec(className || '');
                        return !inline && match ? (
                          <SyntaxHighlighter
                            style={oneLight}
                            language={match[1]}
                            PreTag="div"
                            customStyle={{ margin: '16px 0', borderRadius: '8px', fontSize: '13px', border: '1px solid #f0f0f0' }}
                            {...props}
                          >
                            {String(children).replace(/\n$/, '')}
                          </SyntaxHighlighter>
                        ) : (
                          <code className={className} {...props} style={{ background: '#f8f9fa', padding: '2px 4px', borderRadius: '4px', border: '1px solid #eee' }}>
                            {children}
                          </code>
                        );
                      }
                    }}
                  >
                    {content + (loading ? ' ▌' : '')}
                  </ReactMarkdown>
                </div>
              )
            ) : (
              /* Code Mode */
              <div style={{ position: 'relative', minHeight: '100%' }}>
                <SyntaxHighlighter
                  style={oneLight}
                  language={language || (type === 'html' ? 'html' : 'javascript')}
                  PreTag="div"
                  showLineNumbers
                  customStyle={{ 
                    margin: 0, 
                    padding: '20px', 
                    background: '#fff', 
                    fontSize: '12px',
                    minHeight: '100%',
                    lineHeight: '1.6'
                  }}
                >
                  {content + (loading ? ' ▌' : '')}
                </SyntaxHighlighter>
              </div>
            )}
          </>
        )}
      </div>

      <style dangerouslySetInnerHTML={{ __html: `
        @keyframes blink { 
          0%, 100% { opacity: 1; } 
          50% { opacity: 0.4; } 
        }
        .canvas-tabs .ant-tabs-nav { margin-bottom: 0 !important; }
        .canvas-tabs .ant-tabs-nav::before { border-bottom: none !important; }
        .canvas-markdown pre { background: transparent !important; }
        .canvas-markdown h1, .canvas-markdown h2, .canvas-markdown h3 { margin-top: 1.5em; border-bottom: none; }
      `}} />
    </div>
  );
};

// 辅助图标
const RocketOutlined = (props: any) => (
  <svg viewBox="0 0 1024 1024" focusable="false" data-icon="rocket" width="1em" height="1em" fill="currentColor" aria-hidden="true" {...props}>
     <path d="M912 192a31.94 31.94 0 00-22.6-9.4H441.7l-94 94c-10.7 10.7-10.7 28 0 38.7l50.4 50.4L184.2 579.5l-50.4-50.4c-10.7-10.7-28-10.7-38.7 0l-94 94V832a48.05 48.05 0 0048 48h208.9l94-94c10.7-10.7 10.7-28 0-38.7l-51.4-51.4 213.8-213.8 51.4 51.4c10.7 10.7 28 10.7 38.7 0l94-94V214.6c0-8.5-3.4-16.6-9.4-22.6zm-192 192c-26.5 0-48-21.5-48-48s21.5-48 48-48 48 21.5 48 48-21.5 48-48 48z"></path>
  </svg>
);

export default ArtifactCanvas;
