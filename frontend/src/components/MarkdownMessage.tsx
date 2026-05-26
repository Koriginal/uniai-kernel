import React, { useEffect, useState } from 'react';
import { Button, Space } from 'antd';
import {
  CaretDownOutlined,
  CaretRightOutlined,
  CheckOutlined,
  CopyOutlined,
  ExpandOutlined,
  PartitionOutlined,
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';

interface MarkdownMessageProps {
  content: string | any[];
  loading?: boolean;
  onOpenCanvas?: (title: string, content: string, type: 'markdown' | 'code', language?: string) => void;
  collaborationStatus?: { agentName?: string; content?: string; state: 'active' | 'completed' | null };
}

const CodeBlock = ({ language, children, onOpenCanvas }: { language: string; children: string; onOpenCanvas?: MarkdownMessageProps['onOpenCanvas'] }) => {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(children).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

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
        wrapLongLines
        customStyle={{
          margin: 0,
          padding: '12px',
          background: '#fff',
          fontSize: '13px',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          overflowWrap: 'break-word',
          maxWidth: '100%',
        }}
        codeTagProps={{
          style: {
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            display: 'block',
          },
        }}
      >
        {children}
      </SyntaxHighlighter>
    </div>
  );
};

const CollaborationBlock: React.FC<{ title: string; children: React.ReactNode; isGenerating?: boolean }> = ({ title, children, isGenerating = false }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  useEffect(() => {
    setIsExpanded(!!isGenerating);
  }, [isGenerating]);

  return (
    <div style={{
      margin: '12px 0', border: '1px solid #d9f7be', borderRadius: '8px',
      background: '#f6ffed', overflow: 'hidden',
    }}>
      <div
        onClick={() => setIsExpanded(!isExpanded)}
        style={{
          padding: '8px 16px', display: 'flex', alignItems: 'center', gap: 8,
          cursor: 'pointer', userSelect: 'none', color: '#52c41a', fontWeight: 500,
          background: isExpanded ? 'rgba(82, 196, 26, 0.05)' : 'transparent',
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
          background: '#fff', fontSize: '13px',
        }}>
          {children}
        </div>
      )}
    </div>
  );
};

const preprocessMath = (text: string) => text
  .replace(/\\\[/g, '$$$$').replace(/\\\]/g, '$$$$')
  .replace(/\\\(/g, '$$').replace(/\\\)/g, '$$')
  .replace(/\\r\\n/g, '\n').replace(/\\r/g, '\n');

const renderMarkdown = (text: string, key: string, onOpenCanvas?: MarkdownMessageProps['onOpenCanvas']) => (
  <ReactMarkdown
    key={key}
    remarkPlugins={[remarkGfm, remarkMath]}
    rehypePlugins={[rehypeKatex]}
    components={{
      code({ inline, className, children, ...props }: any) {
        const matchCode = /language-(\w+)/.exec(className || '');
        const codeVal = String(children).replace(/\n$/, '');
        return !inline && matchCode ? (
          <CodeBlock language={matchCode[1]} onOpenCanvas={onOpenCanvas}>{codeVal}</CodeBlock>
        ) : (
          <code className={className} {...props} style={{ background: '#f5f5f5', padding: '2px 4px', borderRadius: '4px' }}>{children}</code>
        );
      },
    }}
  >
    {preprocessMath(text)}
  </ReactMarkdown>
);

const MarkdownMessage: React.FC<MarkdownMessageProps> = React.memo(({ content, loading, onOpenCanvas, collaborationStatus }) => {
  const textContent = typeof content === 'string'
    ? content
    : (Array.isArray(content) ? content.map(item => item.type === 'text' ? item.text : '').join('\n') : '');
  const isExpertActive = loading && collaborationStatus?.state === 'active';

  const parts: React.ReactNode[] = [];
  const regex = /<collaboration\s+title=['"](.*?)['"]>([\s\S]*?)(?:<\/collaboration>|$)/g;
  const cleanContent = textContent.replace(/<\/collaboration>\s*<\/collaboration>/g, '</collaboration>');
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(cleanContent)) !== null) {
    const beforeText = cleanContent.substring(lastIndex, match.index);
    if (beforeText) {
      parts.push(renderMarkdown(beforeText, `md-${lastIndex}`, onOpenCanvas));
    }

    const [fullMatch, title, collabContent] = match;
    const safeCollabContent = collabContent.replace(/<collaboration[^>]*>/g, '').replace(/<\/collaboration>/g, '').trim();
    const finalDisplayContent = safeCollabContent || (isExpertActive ? '' : (loading ? '_专家计算中..._' : '_专家已完成任务协同_'));

    if (finalDisplayContent || isExpertActive) {
      parts.push(
        <CollaborationBlock key={`collab-${match.index}`} title={title} isGenerating={loading}>
          {renderMarkdown(finalDisplayContent, `collab-md-${match.index}`, onOpenCanvas)}
        </CollaborationBlock>
      );
    }
    lastIndex = match.index + fullMatch.length;
  }

  const remainingText = cleanContent.substring(lastIndex).replace(/<\/collaboration>/g, '').trim();
  if (remainingText) {
    parts.push(renderMarkdown(remainingText, `md-remaining-${lastIndex}`, onOpenCanvas));
  }

  return (
    <div className="message-markdown-content" style={{ fontSize: '14px', lineHeight: '1.6', wordBreak: 'break-word', whiteSpace: 'pre-wrap', maxWidth: '100%', overflowWrap: 'break-word' }}>
      {parts}
      {loading && !isExpertActive && <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#1890ff', fontSize: '12px', marginTop: 8 }}>续写中...</div>}
    </div>
  );
}, (prevProps, nextProps) => (
  prevProps.content === nextProps.content &&
  prevProps.loading === nextProps.loading &&
  prevProps.collaborationStatus?.state === nextProps.collaborationStatus?.state &&
  prevProps.collaborationStatus?.content === nextProps.collaborationStatus?.content
));

export default MarkdownMessage;
