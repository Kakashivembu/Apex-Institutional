import React from 'react';
import { 
  LayoutDashboard, 
  BarChart3, 
  Database, 
  Key, 
  Settings 
} from 'lucide-react';

const Sidebar = ({ activeTab, setActiveTab }) => {
  const menuItems = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'backtest', label: 'Backtest', icon: BarChart3 },
    { id: 'fundamentals', label: 'Fundamentals', icon: Database },
    { id: 'api-keys', label: 'API Keys', icon: Key },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  return (
    <div className="w-64 bg-slate-900 border-r border-slate-800 flex flex-col">
      <div className="p-4 border-b border-slate-800">
        <h1 className="text-xl font-bold text-cyan-400">Apex Institutional</h1>
        <p className="text-slate-500 text-sm">AI Trading Terminal</p>
      </div>
      
      <nav className="flex-1 py-4">
        <ul className="space-y-1 px-2">
          {menuItems.map((item) => {
            const Icon = item.icon;
            return (
              <li key={item.id}>
                <button
                  onClick={() => setActiveTab(item.id)}
                  className={`w-full flex items-center px-4 py-3 text-sm rounded-lg transition-all duration-200 ${
                    activeTab === item.id
                      ? 'bg-cyan-900/30 text-cyan-400 border-l border-cyan-400'
                      : 'text-slate-400 hover:bg-slate-800 hover:text-white'
                  }`}
                >
                  <Icon className="w-5 h-5 mr-3" />
                  <span>{item.label}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>
      
      <div className="p-4 border-t border-slate-800">
        <div className="text-xs text-slate-500">
          <p>v2.1.0</p>
          <p className="mt-1">Connected: Primary</p>
        </div>
      </div>
    </div>
  );
};

export default Sidebar;
