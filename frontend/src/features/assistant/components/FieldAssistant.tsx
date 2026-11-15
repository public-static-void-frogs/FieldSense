import { Button, Drawer, Space } from 'antd';
import { Sparkles } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useResizableDrawer } from '../../../hooks/useResizableDrawer.ts';
import type { Field } from '../../../types/fields/field.types.ts';
import { useAssistantChat } from '../hooks/useAssistantChat.ts';
import { ChatComposer } from './ChatComposer';
import { ChatMessageList } from './ChatMessageList';
import './FieldAssistant.css';

type FieldAssistantProps = { field: Field };

export function FieldAssistant({ field }: FieldAssistantProps) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const drawerSize = useResizableDrawer('assistant-drawer-width');
  // The chat lives here, not in the drawer, so closing the drawer keeps the conversation.
  const chat = useAssistantChat(field.id, i18n.resolvedLanguage ?? 'en');

  return (
    <>
      <Button icon={<Sparkles size={19} />} onClick={() => setOpen(true)}>
        {t('Ask AI')}
      </Button>
      <Drawer
        title={
          <Space>
            <Sparkles size={20} className="ai-insight-sparkle" aria-hidden="true" />
            {t('Field assistant')}
          </Space>
        }
        placement="right"
        open={open}
        onClose={() => setOpen(false)}
        {...drawerSize}
        styles={{ wrapper: { maxWidth: '100vw' } }}
        footer={
          <ChatComposer isStreaming={chat.isStreaming} onSend={chat.send} onStop={chat.stop} />
        }
      >
        <ChatMessageList
          entries={chat.entries}
          activeTool={chat.activeTool}
          isStreaming={chat.isStreaming}
          error={chat.error}
          onAsk={chat.send}
          onRetry={chat.retry}
        />
      </Drawer>
    </>
  );
}
