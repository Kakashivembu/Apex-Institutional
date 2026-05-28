import React, { useEffect, useRef, useState } from 'react';
import { createChart } from 'lightweight-charts';
import { API_BASE } from '../lib/api';
import { ActivitySquare, Loader2 } from 'lucide-react';

// Simple EMA calculator
function calculateEMA(data, period, key = 'close') {
  const k = 2 / (period + 1);
  let emaArray = [];
  let currentEMA = null;

  for (let i = 0; i < data.length; i++) {
    const val = data[i][key];
    if (i < period - 1) {
      emaArray.push({ time: data[i].time, value: NaN });
    } else if (i === period - 1) {
      // SMA for the first point
      const sum = data.slice(0, period).reduce((acc, d) => acc + d[key], 0);
      currentEMA = sum / period;
      emaArray.push({ time: data[i].time, value: currentEMA });
    } else {
      currentEMA = (val - currentEMA) * k + currentEMA;
      emaArray.push({ time: data[i].time, value: currentEMA });
    }
  }
  return emaArray;
}

// Simple SMA calculator
function calculateSMA(data, period, key = 'close') {
  let smaArray = [];
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      smaArray.push({ time: data[i].time, value: NaN });
    } else {
      const sum = data.slice(i - period + 1, i + 1).reduce((acc, d) => acc + d[key], 0);
      smaArray.push({ time: data[i].time, value: sum / period });
    }
  }
  return smaArray;
}

// ATR calculator
function calculateATR(data, period) {
  let atrArray = [];
  let trArray = [];
  for (let i = 0; i < data.length; i++) {
    if (i === 0) {
      trArray.push(data[i].high - data[i].low);
      atrArray.push(NaN);
    } else {
      const hl = data[i].high - data[i].low;
      const hc = Math.abs(data[i].high - data[i - 1].close);
      const lc = Math.abs(data[i].low - data[i - 1].close);
      const tr = Math.max(hl, hc, lc);
      trArray.push(tr);
      
      if (i < period) {
        atrArray.push(NaN);
      } else if (i === period) {
        const sum = trArray.slice(1, period + 1).reduce((a, b) => a + b, 0);
        atrArray.push(sum / period);
      } else {
        const prevAtr = atrArray[i - 1];
        const atr = (prevAtr * (period - 1) + tr) / period;
        atrArray.push(atr);
      }
    }
  }
  return atrArray;
}

const BotChartAnalysis = ({ symbol, marketData }) => {
  const chartContainerRef = useRef(null);
  const chartInstanceRef = useRef(null);
  const seriesRef = useRef(null);
  
  // Indicator series refs
  const ema200Ref = useRef(null);
  const ema50Ref = useRef(null);
  const keltnerUpperRef = useRef(null);
  const keltnerLowerRef = useRef(null);
  
  const [candles, setCandles] = useState([]);
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch data
  useEffect(() => {
    let active = true;
    const fetchData = async () => {
      try {
        setLoading(true);
        const tf = '5m';
        const cRes = await fetch(`${API_BASE}/api/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${tf}&count=1000`);
        const cData = await cRes.json();
        
        const tRes = await fetch(`${API_BASE}/api/bot-performance/trades`);
        const tData = await tRes.json();
        
        if (active) {
          if (cData.success) {
            setCandles(cData.data);
          } else {
            setError(cData.error);
          }
          if (tData.success) {
            setTrades(tData.trades.filter(t => t.symbol === symbol));
          }
          setLoading(false);
        }
      } catch (err) {
        if (active) {
          setError(err.message);
          setLoading(false);
        }
      }
    };
    fetchData();
    
    // Auto-refresh every minute
    const interval = setInterval(fetchData, 60000);
    return () => { active = false; clearInterval(interval); };
  }, [symbol]);

  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current) return;
    
    const handleResize = () => {
      if (chartInstanceRef.current && chartContainerRef.current) {
        chartInstanceRef.current.applyOptions({ 
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight
        });
      }
    };

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: 'solid', color: 'transparent' },
        textColor: '#94a3b8',
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: 'rgba(255, 255, 255, 0.1)',
      },
      rightPriceScale: {
        borderColor: 'rgba(255, 255, 255, 0.1)',
      },
      crosshair: {
        mode: 0,
      }
    });
    
    chartInstanceRef.current = chart;
    const series = chart.addCandlestickSeries({
      upColor: '#34d399',
      downColor: '#f43f5e',
      borderVisible: false,
      wickUpColor: '#34d399',
      wickDownColor: '#f43f5e',
    });
    seriesRef.current = series;

    // Add Indicator Series
    ema200Ref.current = chart.addLineSeries({ color: '#c084fc', lineWidth: 2, crosshairMarkerVisible: false });
    ema50Ref.current = chart.addLineSeries({ color: '#fbbf24', lineWidth: 1, crosshairMarkerVisible: false });
    keltnerUpperRef.current = chart.addLineSeries({ color: '#38bdf8', lineWidth: 1, lineStyle: 2, crosshairMarkerVisible: false });
    keltnerLowerRef.current = chart.addLineSeries({ color: '#38bdf8', lineWidth: 1, lineStyle: 2, crosshairMarkerVisible: false });

    window.addEventListener('resize', handleResize);
    
    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, []);

  // Update data and markers
  useEffect(() => {
    if (!seriesRef.current || !candles.length) return;
    
    try {
      // Format candles for lightweight charts (requires time in seconds)
      const formattedData = candles.map(c => ({
        time: c.time,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }));
      
      // Filter out duplicate times and strictly sort ascending
      const uniqueData = [];
      const dataTimes = new Set();
      formattedData.sort((a,b) => a.time - b.time).forEach(c => {
          if (!dataTimes.has(c.time)) {
              dataTimes.add(c.time);
              uniqueData.push(c);
          }
      });
      
      if (uniqueData.length === 0) return;
      seriesRef.current.setData(uniqueData);

      // Calculate and plot EMAs
      const ema200 = calculateEMA(uniqueData, 200).filter(d => !isNaN(d.value));
      const ema50 = calculateEMA(uniqueData, 50).filter(d => !isNaN(d.value));
      const ema20 = calculateEMA(uniqueData, 20);
      const atr20 = calculateATR(uniqueData, 20);
      
      const kUpper = [];
      const kLower = [];
      for (let i = 0; i < uniqueData.length; i++) {
        if (ema20[i] && !isNaN(ema20[i].value) && !isNaN(atr20[i])) {
          kUpper.push({ time: uniqueData[i].time, value: ema20[i].value + (2.25 * atr20[i]) });
          kLower.push({ time: uniqueData[i].time, value: ema20[i].value - (2.25 * atr20[i]) });
        }
      }

      if (ema200Ref.current && ema200.length > 0) ema200Ref.current.setData(ema200);
      if (ema50Ref.current && ema50.length > 0) ema50Ref.current.setData(ema50);
      if (keltnerUpperRef.current && kUpper.length > 0) keltnerUpperRef.current.setData(kUpper);
      if (keltnerLowerRef.current && kLower.length > 0) keltnerLowerRef.current.setData(kLower);
      
      // Generate markers from trades
      if (trades.length > 0) {
        const markers = [];
        trades.forEach(t => {
          if (!t.entry_time) return;
          const entryTime = Math.floor(new Date(t.entry_time).getTime() / 1000);
          const exitTime = t.exit_time ? Math.floor(new Date(t.exit_time).getTime() / 1000) : null;
          
          if (entryTime >= uniqueData[0].time) {
             markers.push({
               time: entryTime,
               position: t.side.toUpperCase() === 'LONG' ? 'belowBar' : 'aboveBar',
               color: t.side.toUpperCase() === 'LONG' ? '#34d399' : '#f43f5e',
               shape: t.side.toUpperCase() === 'LONG' ? 'arrowUp' : 'arrowDown',
               text: `${t.side} @ ${t.entry_price}`,
             });
          }
          
          if (exitTime && exitTime >= uniqueData[0].time && exitTime > entryTime) {
             const isProfit = t.pnl > 0;
             markers.push({
               time: exitTime,
               position: isProfit ? 'aboveBar' : 'belowBar',
               color: isProfit ? '#2dd4bf' : '#fbbf24',
               shape: 'circle',
               text: `CLOSE (${t.pnl > 0 ? '+' : ''}${t.pnl})`,
             });
          }
        });
        
        // Filter out duplicate times and sort for markers
        const uniqueMarkers = [];
        const markerTimes = new Set();
        markers.sort((a,b) => a.time - b.time).forEach(m => {
            let newTime = m.time;
            while(markerTimes.has(newTime)) newTime++;
            markerTimes.add(newTime);
            uniqueMarkers.push({...m, time: newTime});
        });
        
        if (uniqueMarkers.length > 0) {
            seriesRef.current.setMarkers(uniqueMarkers);
        }
      }
    } catch (e) {
      console.error("Error drawing chart data:", e);
      setError("Chart drawing error: " + e.message);
    }
  }, [candles, trades]);

  // Parse SMC and Elite values from marketData
  const smc = marketData?.smc_data || {};
  const trend = marketData?.consensus || {};
  
  return (
    <div className="flex flex-col h-full w-full relative">
      {/* Legend Overlay */}
      <div className="absolute top-4 left-4 z-10 pointer-events-none space-y-2">
        <div className="bg-black/80 backdrop-blur-md border border-white/10 rounded-xl p-4 shadow-xl flex flex-col gap-2 pointer-events-auto">
          <div className="flex items-center gap-2 mb-1">
             <ActivitySquare className="w-4 h-4 text-cyan-400" />
             <span className="font-black text-white text-sm">Elite Scalper Engine</span>
          </div>
          
          <div className="grid grid-cols-2 gap-x-8 gap-y-1 text-xs">
             <div className="flex justify-between gap-4">
                <span className="text-slate-500 font-bold">RSI(7)</span>
                <span className={`font-mono ${smc?.rsi < 30 ? 'text-pink-400' : smc?.rsi > 70 ? 'text-emerald-400' : 'text-slate-300'}`}>{smc?.rsi || '—'}</span>
             </div>
             <div className="flex justify-between gap-4">
                <span className="text-slate-500 font-bold">OFI</span>
                <span className={`font-mono ${smc?.ofi > 0 ? 'text-emerald-400' : smc?.ofi < 0 ? 'text-pink-400' : 'text-slate-300'}`}>{smc?.ofi || '—'}</span>
             </div>
             <div className="flex justify-between gap-4">
                <span className="text-slate-500 font-bold">EMA 200/50</span>
                <span className="font-mono text-purple-400">Plotted <span className="text-amber-400">●</span><span className="text-purple-400">●</span></span>
             </div>
             <div className="flex justify-between gap-4">
                <span className="text-slate-500 font-bold">Keltner</span>
                <span className="font-mono text-sky-400">Plotted</span>
             </div>
          </div>
          
          <div className="mt-2 pt-2 border-t border-white/10">
             <div className="text-[10px] text-slate-400 mb-1">Liquidity Pools</div>
             <div className="text-[11px] font-mono text-amber-400 leading-tight">
               {String(smc?.liquidity_pools || 'Scanning...')}
             </div>
             <div className="text-[11px] font-mono text-cyan-400 leading-tight mt-1">
               Zone: {String(smc?.premium_discount || '—')}
             </div>
          </div>
        </div>
      </div>
      
      {loading && (
        <div className="absolute inset-0 z-20 bg-black/50 backdrop-blur-sm flex items-center justify-center">
          <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
        </div>
      )}
      
      {error && (
        <div className="absolute inset-0 z-20 bg-black/80 flex items-center justify-center">
          <div className="text-pink-400 font-mono text-sm bg-pink-500/10 px-4 py-2 rounded border border-pink-500/20">
            Error loading chart: {error}
          </div>
        </div>
      )}

      {/* The actual chart container */}
      <div ref={chartContainerRef} className="flex-1 w-full h-[600px] rounded-3xl overflow-hidden" />
    </div>
  );
};

export default BotChartAnalysis;
