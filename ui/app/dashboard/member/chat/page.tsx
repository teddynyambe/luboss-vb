'use client';

import { useState, useRef, useEffect } from 'react';
import { api } from '@/lib/api';
import Link from 'next/link';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  citations?: Array<{ document: string; version: string; page: number }>;
}

export default function AIChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

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
              <Link href="/dashboard/member" className="text-blue-600 hover:text-blue-800 text-base md:text-lg font-medium">
                ← Back
              </Link>
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">AI Chat Assistant</h1>
            </div>
          </div>
        </div>
      </nav>

      <div className="flex-1 flex flex-col max-w-4xl mx-auto w-full p-4 md:p-6">
        <div className="card flex-1 flex flex-col">
          <div className="p-4 md:p-6 border-b-2 border-blue-200">
            <p className="text-base md:text-lg text-blue-700 font-medium">
              Ask me about village banking rules, policies, or your account status.
            </p>
          </div>

          <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-4 md:space-y-6">
            {messages.length === 0 && (
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
                  <p className="whitespace-pre-wrap text-sm md:text-base">{message.content}</p>
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
