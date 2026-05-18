# Fixing Cross-Device Connectivity for Apex Trading Terminal

## Issue Summary

The frontend application was hardcoded to connect to the backend using `localhost`, which only works when accessing the application from the same machine where the backend is running. To fix cross-device connectivity, I've updated the frontend to use dynamic URLs that adapt to the current host.

## Changes Made

1. **Updated WebSocket Connection**:
   - Changed from hardcoded `ws://localhost:8000` to dynamic `ws://${window.location.hostname}:8000`
   - This allows the WebSocket to connect to the backend regardless of which device is accessing the frontend

2. **Updated API Endpoints**:
   - Modified trading toggle function to use dynamic URL: `http://${window.location.hostname}:8000/api/trading/toggle`
   - Updated trading status fetch to use dynamic URL: `http://${window.location.hostname}:8000/api/trading/status`

## How It Works

When accessing the application from another device:
1. The browser's `window.location.hostname` will automatically resolve to the IP address of the machine hosting the frontend
2. The frontend will then connect to the backend using that same IP address
3. This eliminates the need to hardcode specific IP addresses

## Testing the Fix

To test that the connectivity is working properly:
1. Access the frontend from another device using `http://[YOUR_IP]:5173`
2. The WebSocket connection should now establish successfully
3. The backend status should show as "Live" instead of "Offline"
4. Database connection should be active

## Additional Notes

The backend server is already configured to accept external connections:
- It's bound to `0.0.0.0` to accept connections from any IP
- CORS settings allow all origins
- No additional server-side changes are needed

This fix should resolve the connectivity issues between frontend and backend when accessing from different devices on the same network.