'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';

const INACTIVITY_MINUTES = 15;
const INACTIVITY_MS = INACTIVITY_MINUTES * 60 * 1000;

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  citations?: Array<{ document: string; version: string; page: number }>;
}

function renderMarkdown(text: string) {
  const lines = text.split('\n');
  const elements: JSX.Element[] = [];
  let currentList: JSX.Element[] = [];
  let listType: 'ul' | 'ol' | null = null;
  let key = 0;

  const flushList = () => {
    if (currentList.length > 0) {
      if (listType === 'ul') {
        elements.push(
          <ul key={key++} className="list-disc list-inside my-2 space-y-1 ml-4">
            {currentList}
          </ul>
        );
      } else if (listType === 'ol') {
        elements.push(
          <ol key={key++} className="list-decimal list-inside my-2 space-y-1 ml-4">
            {currentList}
          </ol>
        );
      }
      currentList = [];
      listType = null;
    }
  };

  const processBold = (line: string, lineKey: number) => {
    const parts: (string | JSX.Element)[] = [];
    const regex = /\*\*(.*?)\*\*/g;
    let lastIndex = 0;
    let match;
    let matchKey = 0;
    while ((match = regex.exec(line)) !== null) {
      if (match.index > lastIndex) {
        parts.push(line.substring(lastIndex, match.index));
      }
      parts.push(<strong key={`bold-${lineKey}-${matchKey++}`} className="font-bold">{match[1]}</strong>);
      lastIndex = regex.lastIndex;
    }
    if (lastIndex < line.length) {
      parts.push(line.substring(lastIndex));
    }
    return parts.length > 0 ? <>{parts}</> : line;
  };

  lines.forEach((line, index) => {
    const trimmed = line.trim();
    if (trimmed === '') {
      flushList();
      if (index < lines.length - 1 && elements.length > 0) {
        elements.push(<div key={key++} className="h-2" />);
      }
      return;
    }
    if (trimmed.match(/^[-*]\s/)) {
      if (listType !== 'ul') {
        flushList();
        listType = 'ul';
      }
      currentList.push(
        <li key={currentList.length} className="text-sm md:text-base">
          {processBold(trimmed.substring(2).trim(), index)}
        </li>
      );
      return;
    }
    if (trimmed.match(/^\d+\.\s/)) {
      if (listType !== 'ol') {
        flushList();
        listType = 'ol';
      }
      currentList.push(
        <li key={currentList.length} className="text-sm md:text-base">
          {processBold(trimmed.replace(/^\d+\.\s/, '').trim(), index)}
        </li>
      );
      return;
    }
    flushList();
    elements.push(
      <p key={key++} className="my-1 text-sm md:text-base leading-relaxed">
        {processBold(trimmed, index)}
      </p>
    );
  });
  flushList();
  return <div className="markdown-content">{elements.length > 0 ? elements : <p className="text-sm md:text-base">{text}</p>}</div>;
}

export default function FloatingAIChat() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [greetingLoaded, setGreetingLoaded] = useState(false);
  const lastActivityRef = useRef<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    if (open) scrollToBottom();
  }, [open, messages, scrollToBottom]);

  const resetChat = useCallback(() => {
    setMessages([]);
    setGreetingLoaded(false);
    lastActivityRef.current = null;
  }, []);

  const loadGreeting = useCallback(async () => {
    if (greetingLoaded) return;
    try {
      const res = await api.get<{ response: string; citations?: any[] }>('/api/ai/greeting');
      if (res.data?.response) {
        setMessages([{ role: 'assistant', content: res.data.response, citations: res.data.citations }]);
        lastActivityRef.current = Date.now();
      } else {
        const name = user?.first_name || 'Member';
        const fallback = `Shani ama yama ba ${name}! I'm your Luboss VB Finance Assistant. I'm here to help you with:\n\n• Information about the app and how to use it\n• Questions about the uploaded constitution and its interpretation\n• Your account details, transactions, savings, loans, and declarations\n• Understanding village banking rules and policies\n\nHow can I assist you today?`;
        setMessages([{ role: 'assistant', content: fallback }]);
        lastActivityRef.current = Date.now();
      }
    } catch {
      const name = user?.first_name || 'Member';
      const fallback = `Shani ama yama ba ${name}! I'm your Luboss VB Finance Assistant. I'm here to help you with:\n\n• Information about the app and how to use it\n• Questions about the uploaded constitution and its interpretation\n• Your account details, transactions, savings, loans, and declarations\n• Understanding village banking rules and policies\n\nHow can I assist you today?`;
      setMessages([{ role: 'assistant', content: fallback }]);
      lastActivityRef.current = Date.now();
    }
    setGreetingLoaded(true);
  }, [greetingLoaded, user?.first_name]);

  useEffect(() => {
    if (open && !greetingLoaded) loadGreeting();
  }, [open, greetingLoaded, loadGreeting]);

  const handleToggle = () => {
    if (!open) {
      const last = lastActivityRef.current;
      if (last != null && Date.now() - last > INACTIVITY_MS) {
        resetChat();
      }
    }
    setOpen((o) => !o);
  };

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage: ChatMessage = { role: 'user', content: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    lastActivityRef.current = Date.now();
    setLoading(true);

    const res = await api.post<{ response: string; citations?: any[] }>('/api/ai/chat', { query: input });

    if (res.data) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: res.data!.response, citations: res.data!.citations },
      ]);
      lastActivityRef.current = Date.now();
    } else {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: res.error || 'Sorry, I encountered an error.' },
      ]);
      lastActivityRef.current = Date.now();
    }
    setLoading(false);
  };

  return (
    <>
      {/* Floating chat button */}
      <button
        type="button"
        onClick={handleToggle}
        className="fixed bottom-6 right-6 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-blue-600 text-white shadow-lg transition-all hover:bg-blue-700 hover:scale-105 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
        aria-label={open ? 'Close AI chat' : 'Open AI chat'}
        title={open ? 'Close chat' : 'Chat with AI'}
      >
        {open ? (
          <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        ) : (
          <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
        )}
      </button>

      {/* Chat popup */}
      {open && (
        <div
          className="fixed bottom-24 right-6 z-50 flex h-[min(70vh,520px)] w-[calc(100vw-3rem)] max-w-md flex-col overflow-hidden rounded-xl border-2 border-blue-200 bg-white shadow-2xl"
          role="dialog"
          aria-label="AI chat"
        >
          <div className="flex shrink-0 items-center justify-between border-b-2 border-blue-200 bg-blue-50 px-4 py-3">
            <span className="font-bold text-blue-900">Luboss AI Assistant</span>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded-full p-1.5 text-blue-600 hover:bg-blue-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
              aria-label="Close chat"
            >
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-4 space-y-4">
            {!greetingLoaded && (
              <div className="flex justify-center gap-1 py-8">
                <div className="h-2 w-2 rounded-full bg-blue-600 animate-bounce" />
                <div className="h-2 w-2 rounded-full bg-blue-600 animate-bounce" style={{ animationDelay: '0.2s' }} />
                <div className="h-2 w-2 rounded-full bg-blue-600 animate-bounce" style={{ animationDelay: '0.4s' }} />
              </div>
            )}

            {messages.map((m, idx) => (
              <div key={idx} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[85%] rounded-xl px-4 py-3 text-sm ${
                    m.role === 'user'
                      ? 'bg-blue-600 text-white'
                      : 'bg-blue-100 text-blue-900 border border-blue-200'
                  }`}
                >
                  {m.role === 'assistant' ? renderMarkdown(m.content) : <p className="whitespace-pre-wrap">{m.content}</p>}
                  {m.citations && m.citations.length > 0 && (
                    <div className="mt-2 border-t border-blue-300 pt-2 text-xs">
                      {m.citations.map((c, i) => (
                        <p key={i}>{c.document} v{c.version} (p{c.page})</p>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex justify-start">
                <div className="flex gap-1 rounded-xl border border-blue-200 bg-blue-100 px-4 py-3">
                  <div className="h-2 w-2 rounded-full bg-blue-600 animate-bounce" />
                  <div className="h-2 w-2 rounded-full bg-blue-600 animate-bounce" style={{ animationDelay: '0.2s' }} />
                  <div className="h-2 w-2 rounded-full bg-blue-600 animate-bounce" style={{ animationDelay: '0.4s' }} />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <form onSubmit={handleSend} className="shrink-0 border-t-2 border-blue-200 p-3">
            <div className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask a question..."
                className="min-w-0 flex-1 rounded-lg border-2 border-blue-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-400"
                disabled={loading}
              />
              <button
                type="submit"
                disabled={loading || !input.trim()}
                className="btn-primary min-h-0 px-4 py-2 text-sm disabled:opacity-50"
              >
                Send
              </button>
            </div>
          </form>
        </div>
      )}
    </>
  );
}
