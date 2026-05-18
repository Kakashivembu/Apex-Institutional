import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Loader2 } from 'lucide-react';
import { API_BASE } from '../lib/api';

const ChatBox = () => {
  const [messages, setMessages] = useState([
    { sender: 'assistant', text: 'Hello! I am the Apex Institutional AI. How can I assist you with your quantitative analysis today?' }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim()) return;

    const userText = input.trim();
    setInput('');
    const newMessages = [...messages, { sender: 'user', text: userText }];
    setMessages(newMessages);
    setIsLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userText, history: messages })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setMessages([...newMessages, { sender: 'assistant', text: data.response }]);
    } catch (error) {
      console.error("Chat Error:", error);
      setMessages([...newMessages, { sender: 'assistant', text: `⚠️ Error: Could not connect to Apex Backend. (${error.message})` }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full bg-black/40 border border-white/5 rounded-2xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center px-4 py-3 border-b border-white/5 bg-black/60">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-indigo-500/20 mr-3">
          <Bot className="w-4.5 h-4.5 text-white" />
        </div>
        <div>
          <h2 className="text-sm font-bold text-white">Apex Terminal AI</h2>
          <p className="text-[10px] text-indigo-400 font-mono tracking-wider">NVIDIA NIM 70B</p>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-[300px]">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`flex max-w-[85%] ${msg.sender === 'user' ? 'flex-row-reverse' : 'flex-row'} items-start gap-2`}>
              <div className={`w-6 h-6 rounded-md flex items-center justify-center shrink-0 mt-1 ${msg.sender === 'user' ? 'bg-pink-500/20 text-pink-400' : 'bg-indigo-500/20 text-indigo-400'}`}>
                {msg.sender === 'user' ? <User className="w-3.5 h-3.5" /> : <Bot className="w-3.5 h-3.5" />}
              </div>
              <div className={`px-4 py-2.5 rounded-2xl text-sm ${
                msg.sender === 'user' 
                  ? 'bg-pink-500/10 border border-pink-500/20 text-pink-100 rounded-tr-sm' 
                  : 'bg-white/5 border border-white/10 text-slate-300 rounded-tl-sm'
              }`}>
                {msg.text.split('\n').map((line, i) => (
                  <p key={i} className="mb-1 last:mb-0">{line}</p>
                ))}
              </div>
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="flex justify-start">
            <div className="flex max-w-[85%] flex-row items-start gap-2">
              <div className="w-6 h-6 rounded-md flex items-center justify-center shrink-0 mt-1 bg-indigo-500/20 text-indigo-400">
                <Bot className="w-3.5 h-3.5" />
              </div>
              <div className="px-4 py-3 rounded-2xl bg-white/5 border border-white/10 text-slate-300 rounded-tl-sm flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
                <span className="text-xs text-indigo-400/80">Analyzing...</span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-3 border-t border-white/5 bg-black/40">
        <div className="relative flex items-center">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask the Apex AI..."
            className="w-full bg-white/5 border border-white/10 rounded-xl pl-4 pr-12 py-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500/40 focus:bg-white/10 transition-all resize-none overflow-hidden"
            rows="1"
            style={{ minHeight: '44px', maxHeight: '120px' }}
          />
          <button
            onClick={handleSend}
            disabled={isLoading || !input.trim()}
            className="absolute right-2 p-2 rounded-lg bg-indigo-500 hover:bg-indigo-600 disabled:bg-white/5 disabled:text-slate-500 text-white transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
        <p className="text-center text-[9px] text-slate-500 mt-2 font-mono">
          Powered by NVIDIA NIM
        </p>
      </div>
    </div>
  );
};

export default ChatBox;
