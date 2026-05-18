import React from 'react';

const TopBar = ({ marketData = {} }) => {
  const equity = marketData.equity || { total: 0, daily_pnl: 0, daily_change_pct: 0 };
  const positions = marketData.positions || [];
  const activePositions = positions.filter(p => p.status === 'active').length;
  
  // Calculate win rate based on positions
  const winRate = positions.length > 0 
    ? Math.round((positions.filter(p => p.pnl > 0).length / positions.length) * 100)
    : 0;

  const stats = [
    { label: 'Total Equity', value: `$${equity.total.toLocaleString()}`, change: equity.daily_change_pct ? `+${equity.daily_change_pct.toFixed(1)}%` : null },
    { label: 'Today P&L', value: `$${equity.daily_pnl.toLocaleString()}`, change: equity.daily_pnl > 0 ? `+${(equity.daily_pnl / equity.total * 100).toFixed(1)}%` : null },
    { label: 'Active Positions', value: `${activePositions}`, change: null },
    { label: 'Win Rate', value: `${winRate}%`, change: winRate > 50 ? '+3.2%' : null },
  ];

  return (
    <div className="bg-slate-900 border-b border-slate-800 p-4">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-lg font-semibold">Trading Dashboard</h2>
          <p className="text-slate-500 text-sm">Real-time market monitoring</p>
        </div>
        
        <div className="flex space-x-6">
          {stats.map((stat, index) => (
            <div key={index} className="text-center">
              <p className="text-slate-500 text-xs">{stat.label}</p>
              <p className="text-white font-semibold">{stat.value}</p>
              {stat.change && (
                <p className={`text-xs ${stat.change.startsWith('+') ? 'text-emerald-400' : 'text-red-400'}`}>
                  {stat.change}
                </p>
              )}
            </div>
          ))}
        </div>
        
        <div className="flex items-center space-x-4">
          <div className="relative">
            <div className="w-3 h-3 bg-emerald-500 rounded-full absolute bottom-0 right-0 ring-2 ring-slate-900"></div>
            <div className="w-10 h-10 rounded-full bg-slate-800 flex items-center justify-center">
              <span className="font-semibold">U</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TopBar;
