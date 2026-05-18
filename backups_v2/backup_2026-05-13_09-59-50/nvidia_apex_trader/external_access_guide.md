# Allowing External Access to Apex Trading Terminal

## Summary

I've updated the configuration to allow full web access to the Apex Trading Terminal from other devices on your network. The frontend and backend are now properly configured to accept connections from external devices.

## Changes Made

1. **Updated Vite Configuration**:
   - Added `host: true` to allow external connections to the frontend server
   - Kept port configuration at 5173 (Vite's default)

2. **Updated Backend CORS Settings**:
   - Modified server.py to explicitly allow all origins
   - Enabled credentials, methods, and headers for external access

## How to Access the Application

From your other device, you can now access the application at:
- Frontend: `http://[YOUR_LOCAL_IP]:5173`
- Backend API: `http://[YOUR_LOCAL_IP]:8000`

Replace `[YOUR_LOCAL_IP]` with your actual local IP address (e.g., 192.168.1.15).

## Testing the Setup

1. Start the backend server:
   ```
   cd nvidia_apex_trader
   python server.py
   ```

2. Start the frontend:
   ```
   cd frontend
   npm run dev
   ```

3. Access from your other device:
   - Navigate to `http://[YOUR_LOCAL_IP]:5173` in your mobile browser
   - The frontend should now connect to the backend and display real-time data

## Security Note

The CORS settings have been configured to allow all origins for development purposes. In a production environment, you should restrict the allowed origins to specific domains for security reasons.

## Troubleshooting

If you still experience connection issues:

1. Check that both the frontend and backend servers are running
2. Verify your local IP address using `ipconfig` (Windows) or `ifconfig` (Mac/Linux)
3. Ensure your firewall isn't blocking connections on ports 5173 or 8000
4. Confirm both devices are on the same network