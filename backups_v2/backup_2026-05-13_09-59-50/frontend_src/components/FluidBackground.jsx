import React, { useEffect, useRef } from 'react';

const FluidBackground = () => {
  const canvasRef = useRef(null);
  const initialized = useRef(false);

  useEffect(() => {
    let simulation = null;
    let initFluid = null;
    
    import('webgl-fluid').then((webGLFluid) => {
      initFluid = webGLFluid.default || webGLFluid;
      
      try {
        if (!canvasRef.current || initialized.current) return;
        initialized.current = true;
        simulation = initFluid(canvasRef.current, {
          IMMEDIATE: true,
          TRIGGER: 'hover',
          SIM_RESOLUTION: 128,
          DYE_RESOLUTION: 1024,
          CAPTURE_RESOLUTION: 512,
          DENSITY_DISSIPATION: 1.2, // Slower dissipation for thicker oil
          VELOCITY_DISSIPATION: 1.0,
          PRESSURE: 0.8,
          PRESSURE_ITERATIONS: 20,
          CURL: 30, // More swirling
          SPLAT_RADIUS: 0.35, // Larger splats
          SPLAT_FORCE: 6000,
          SHADING: true,
          COLORFUL: true, // Allow a bit more color variance
          COLOR_UPDATE_SPEED: 10,
          PAUSED: false,
          BACK_COLOR: { r: 0, g: 0, b: 0 },
          TRANSPARENT: false,
          BLOOM: true,
          BLOOM_ITERATIONS: 8,
          BLOOM_RESOLUTION: 256,
          BLOOM_INTENSITY: 0.8,
          BLOOM_THRESHOLD: 0.6,
          BLOOM_SOFT_KNEE: 0.7,
          SUNRAYS: true,
          SUNRAYS_RESOLUTION: 196,
          SUNRAYS_WEIGHT: 1.0,
          COLOR_PALETTE: ['#f70670', '#ff3388', '#d6005c', '#8b5cf6', '#21001a']
        });
      } catch (err) {
        console.warn('Fluid simulation failed to initialize:', err);
      }
    }).catch(err => console.warn('Failed to load webgl-fluid module:', err));

    // Forward mouse events from window to canvas so fluid works under UI
    const handlePointerMove = (e) => {
      if (canvasRef.current) {
        // Dispatch synthetic event to canvas
        const event = new MouseEvent('mousemove', {
          view: window,
          bubbles: true,
          cancelable: true,
          clientX: e.clientX,
          clientY: e.clientY,
          screenX: e.screenX,
          screenY: e.screenY
        });
        // WebGL fluid needs offsetX/Y or pageX/Y depending on version
        Object.defineProperty(event, 'offsetX', { get: () => e.clientX });
        Object.defineProperty(event, 'offsetY', { get: () => e.clientY });
        Object.defineProperty(event, 'pageX', { get: () => e.pageX });
        Object.defineProperty(event, 'pageY', { get: () => e.pageY });
        canvasRef.current.dispatchEvent(event);
      }
    };
    
    const handleTouchMove = (e) => {
      if (canvasRef.current && e.touches.length > 0) {
        const touch = e.touches[0];
        const event = new TouchEvent('touchmove', {
          view: window,
          bubbles: true,
          cancelable: true,
          touches: e.touches,
          targetTouches: e.targetTouches,
          changedTouches: e.changedTouches
        });
        // Add pageX/Y to the touch object if it checks there
        Object.defineProperty(event, 'pageX', { get: () => touch.pageX });
        Object.defineProperty(event, 'pageY', { get: () => touch.pageY });
        canvasRef.current.dispatchEvent(event);
      }
    };

    window.addEventListener('mousemove', handlePointerMove, { passive: false });
    window.addEventListener('touchmove', handleTouchMove, { passive: false });

    return () => {
      window.removeEventListener('mousemove', handlePointerMove);
      window.removeEventListener('touchmove', handleTouchMove);
    };
  }, []);

  return (
    <canvas 
      ref={canvasRef} 
      style={{ 
        position: 'fixed', 
        top: 0, 
        left: 0, 
        width: '100vw', 
        height: '100vh', 
        zIndex: -1,
        pointerEvents: 'none' // We manually forward events, so this won't block UI
      }} 
    />
  );
};

export default FluidBackground;
