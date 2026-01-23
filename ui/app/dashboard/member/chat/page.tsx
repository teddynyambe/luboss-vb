'use client';

import { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import Link from 'next/link';
import UserMenu from '@/components/UserMenu';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  citations?: Array<{ document: string; version: string; page: number }>;
}

// Simple markdown renderer for basic formatting (bold, lists, line breaks)
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
    
    // Empty line - flush list and add paragraph break
    if (trimmed === '') {
      flushList();
      if (index < lines.length - 1 && elements.length > 0) {
        elements.push(<div key={key++} className="h-2" />);
      }
      return;
    }

    // Check for list items
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
    } else if (trimmed.match(/^\d+\.\s/)) {
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

    // Not a list item - flush any current list
    flushList();

    // Regular paragraph
    elements.push(
      <p key={key++} className="my-1 text-sm md:text-base leading-relaxed">
        {processBold(trimmed, index)}
      </p>
    );
  });

  flushList();

  return <div className="markdown-content">{elements.length > 0 ? elements : <p className="text-sm md:text-base">{text}</p>}</div>;
}

export default function AIChatPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [greetingLoaded, setGreetingLoaded] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const handleClose = () => {
    router.push('/dashboard/member');
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Load greeting on component mount
  useEffect(() => {
    const loadGreeting = async () => {
      if (greetingLoaded) return;
      
      try {
        const response = await api.get<{ response: string; citations?: any[] }>('/api/ai/greeting');
        if (response.data && response.data.response) {
          const greetingMessage: ChatMessage = {
            role: 'assistant',
            content: response.data.response,
            citations: response.data.citations,
          };
          setMessages([greetingMessage]);
          setGreetingLoaded(true);
        } else {
          // If API returns error, show fallback greeting
          const firstName = user?.first_name || 'Member';
          const fallbackGreeting: ChatMessage = {
            role: 'assistant',
            content: `Shani ama yama ba ${firstName}! I'm your Luboss VB Finance Assistant. I'm here to help you with:\n\n• Information about the app and how to use it\n• Questions about the uploaded constitution and its interpretation\n• Your account details, transactions, savings, loans, and declarations\n• Understanding village banking rules and policies\n\nHow can I assist you today?`,
          };
          setMessages([fallbackGreeting]);
          setGreetingLoaded(true);
        }
      } catch (error) {
        console.error('Error loading greeting:', error);
        // If greeting fails, show fallback greeting
        const firstName = user?.first_name || 'Member';
        const fallbackGreeting: ChatMessage = {
          role: 'assistant',
          content: `Shani ama yama ba ${firstName}! I'm your Luboss VB Finance Assistant. I'm here to help you with:\n\n• Information about the app and how to use it\n• Questions about the uploaded constitution and its interpretation\n• Your account details, transactions, savings, loans, and declarations\n• Understanding village banking rules and policies\n\nHow can I assist you today?`,
        };
        setMessages([fallbackGreeting]);
        setGreetingLoaded(true);
      }
    };

    loadGreeting();
  }, [greetingLoaded, user]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage: ChatMessage = { role: 'user', content: input };
    setMessages([...messages, userMessage]);
    setInput('');
    setLoading(true);

    const response = await api.post<{ response: string; citations?: any[] }>(
      '/api/ai/chat',
      { query: input }
    );

    if (response.data) {
      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: response.data.response,
        citations: response.data.citations,
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } else {
      const errorMessage: ChatMessage = {
        role: 'assistant',
        content: response.error || 'Sorry, I encountered an error.',
      };
      setMessages((prev) => [...prev, errorMessage]);
    }

    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200 flex flex-col">
      <nav className="bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 md:h-20">
            <div className="flex items-center space-x-3 md:space-x-4">
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">Luboss VB Finance Assistant</h1>
            </div>
            <div className="flex items-center space-x-3 md:space-x-4">
              <button
                onClick={handleClose}
                className="flex items-center justify-center w-10 h-10 md:w-12 md:h-12 rounded-full bg-blue-100 hover:bg-blue-200 text-blue-700 hover:text-blue-900 transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                aria-label="Close chat and return to dashboard"
                title="Close chat"
              >
                <svg
                  className="w-6 h-6 md:w-7 md:h-7"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
              <UserMenu />
            </div>
          </div>
        </div>
      </nav>

      <div className="flex-1 flex flex-col max-w-4xl mx-auto w-full p-4 md:p-6">
        <div className="card flex-1 flex flex-col">
          <div className="p-4 md:p-6 border-b-2 border-blue-200">
            <p className="text-base md:text-lg text-blue-700 font-medium">
              Your personalized finance assistant. Ask about the app, constitution, your account, or transactions.
            </p>
          </div>

          <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-4 md:space-y-6">
            {messages.length === 0 && !greetingLoaded && (
              <div className="text-center text-blue-700 py-12 md:py-16">
                <div className="flex justify-center mb-4">
                  <div className="flex space-x-2">
                    <div className="w-3 h-3 bg-blue-600 rounded-full animate-bounce"></div>
                    <div className="w-3 h-3 bg-blue-600 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                    <div className="w-3 h-3 bg-blue-600 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }}></div>
                  </div>
                </div>
                <p className="text-base md:text-lg font-medium">Loading your personalized assistant...</p>
              </div>
            )}
            
            {messages.length === 0 && greetingLoaded && (
              <div className="text-center text-blue-700 py-12 md:py-16">
                <p className="text-base md:text-lg font-medium mb-4">Start a conversation by asking a question below.</p>
                <p className="text-sm md:text-base font-semibold mb-2">Examples:</p>
                <ul className="text-sm md:text-base mt-2 space-y-2 text-left max-w-md mx-auto">
                  <li className="bg-blue-50 p-3 rounded-lg border border-blue-200">"What is the interest rate for a 3-month loan?"</li>
                  <li className="bg-blue-50 p-3 rounded-lg border border-blue-200">"What is my current savings balance?"</li>
                  <li className="bg-blue-50 p-3 rounded-lg border border-blue-200">"Explain the collateral policy"</li>
                </ul>
              </div>
            )}

            {messages.map((message, idx) => (
              <div
                key={idx}
                className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[85%] md:max-w-3xl rounded-xl p-4 md:p-5 ${
                    message.role === 'user'
                      ? 'bg-gradient-to-br from-blue-500 to-blue-600 text-white shadow-lg'
                      : 'bg-gradient-to-br from-blue-100 to-blue-200 text-blue-900 border-2 border-blue-300 shadow-md'
                  }`}
                >
                  <div className="text-sm md:text-base">
                    {message.role === 'assistant' ? renderMarkdown(message.content) : <p className="whitespace-pre-wrap">{message.content}</p>}
                  </div>
                  {message.citations && message.citations.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-blue-300">
                      <p className="text-xs md:text-sm font-bold mb-2">Sources:</p>
                      {message.citations.map((cite, i) => (
                        <p key={i} className="text-xs md:text-sm">
                          {cite.document} v{cite.version} (page {cite.page})
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex justify-start">
                <div className="bg-gradient-to-br from-blue-100 to-blue-200 rounded-xl p-4 md:p-5 border-2 border-blue-300">
                  <div className="flex space-x-2">
                    <div className="w-3 h-3 bg-blue-600 rounded-full animate-bounce"></div>
                    <div className="w-3 h-3 bg-blue-600 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                    <div className="w-3 h-3 bg-blue-600 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }}></div>
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          <form onSubmit={handleSend} className="p-4 md:p-6 border-t-2 border-blue-200">
            <div className="flex gap-2 md:gap-3">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask a question..."
                className="flex-1 min-h-[48px] text-base md:text-lg"
                disabled={loading}
              />
              <button
                type="submit"
                disabled={loading || !input.trim()}
                className="btn-primary disabled:opacity-50"
              >
                Send
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
