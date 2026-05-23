import os
import json
import asyncio
import websockets
from datetime import datetime
from dotenv import load_dotenv
from aiohttp import web

env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_API_KEY_3 = os.getenv("NVIDIA_API_KEY_3", "")

api_keys_storage = []

class ApexWebSocketServer:
    def __init__(self):
        self.clients = set()
        self.last_positions = []
        self.last_swarm_decisions = []
        self.last_equity = 0
        self.running = True
        self.app = web.Application()
        self._setup_http_routes()

    def _setup_http_routes(self):
        self.app.router.add_get('/api/keys', self.get_api_keys)
        self.app.router.add_post('/api/keys', self.add_api_key)
        self.app.router.add_delete('/api/keys', self.delete_api_key)
        self.app.router.add_delete('/api/keys/{key_id}', self.delete_api_key)

    async def get_api_keys(self, request):
        return web.json_response({"keys": api_keys_storage})

    async def add_api_key(self, request):
        try:
            data = await request.json()
            new_key = {
                "id": len(api_keys_storage) + 1,
                "account_name": data.get("account_name", "Unnamed"),
                "api_key": data.get("api_key", ""),
                "api_secret": data.get("api_secret", ""),
                "network": data.get("network", "testnet"),
                "created_at": datetime.now().isoformat(),
            }
            api_keys_storage.append(new_key)
            masked_key = {
                "id": new_key["id"],
                "account_name": new_key["account_name"],
                "api_key": new_key["api_key"][:8] + "..." + new_key["api_key"][-4:] if len(new_key["api_key"]) > 12 else "***",
                "api_secret": "***" + new_key["api_secret"][-4:] if new_key["api_secret"] else "***",
                "network": new_key["network"],
                "created_at": new_key["created_at"],
            }
            return web.json_response({"success": True, "key": masked_key}, status=201)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=400)

    async def delete_api_key(self, request):
        global api_keys_storage
        account_name = request.query.get('account_name')

        if account_name:
            api_keys_storage = [k for k in api_keys_storage if k.get("account_name") != account_name]
            return web.json_response({"success": True})

        try:
            key_id = int(request.match_info.get('key_id', 0))
            api_keys_storage = [k for k in api_keys_storage if k.get("id") != key_id]
        except (ValueError, KeyError):
            pass

        return web.json_response({"success": True})

    async def register(self, websocket):
        self.clients.add(websocket)
        print(f"Client connected. Total clients: {len(self.clients)}")

    def unregister(self, websocket):
        self.clients.discard(websocket)
        print(f"Client disconnected. Total clients: {len(self.clients)}")

    async def broadcast(self, message: dict):
        if self.clients:
            message_str = json.dumps(message)
            await asyncio.gather(
                *[client.send(message_str) for client in self.clients],
                return_exceptions=True
            )

    async def simulate_market_data(self):
        import random

        while self.running:
            try:
                sentiment_choice = random.choice(["BULLISH", "BEARISH", "NEUTRAL"])

                claw_decision = {
                    "agent": "CLAW",
                    "name": "Fundamental Desk",
                    "decision": sentiment_choice,
                    "confidence": random.randint(70, 95),
                    "signal": f"Sentiment: {sentiment_choice}",
                    "status": "strong" if random.random() > 0.3 else "moderate"
                }

                macro_decision = random.choice(["BUY", "SELL", "HOLD"])
                self.last_swarm_decisions = [
                    claw_decision,
                    {
                        "agent": "NVIDIA_MACRO",
                        "name": "Macro Trend Follower",
                        "decision": macro_decision,
                        "confidence": random.randint(75, 95),
                        "signal": f"Trend: {macro_decision}",
                        "status": "strong"
                    },
                    {
                        "agent": "NVIDIA_SCALPER",
                        "name": "NVIDIA Scalper",
                        "decision": random.choice(["BUY", "BUY", "HOLD"]),
                        "confidence": random.randint(70, 90),
                        "signal": "Entry: Sniper",
                        "status": "strong"
                    }
                ]

                base_positions = [
                    {"symbol": "BTCUSD", "qty": 100, "entry": 42000.00, "current": 42500.00, "pnl": 500.00, "change": "+1.19%", "status": "active", "tp": 44000.00, "sl": 40000.00},
                    {"symbol": "ETHUSD", "qty": 50, "entry": 2200.00, "current": 2185.00, "pnl": -750.00, "change": "-3.41%", "status": "active", "tp": 2400.00, "sl": 2000.00},
                    {"symbol": "NVDA", "qty": 120, "entry": 845.32, "current": 852.15, "pnl": 820.45, "change": "+0.81%", "status": "active", "tp": 875.00, "sl": 825.00},
                    {"symbol": "TSLA", "qty": 45, "entry": 178.45, "current": 182.33, "pnl": 174.60, "status": "active", "tp": 190.00, "sl": 170.00},
                    {"symbol": "MSFT", "qty": 75, "entry": 420.15, "current": 418.75, "pnl": -105.00, "change": "-0.33%", "status": "active", "tp": 440.00, "sl": 400.00},
                ]

                self.last_positions = []
                for pos in base_positions:
                    price_change = random.uniform(-0.02, 0.02)
                    current = pos["current"] * (1 + price_change)
                    pnl = (current - pos["entry"]) * pos["qty"]
                    change_pct = ((current - pos["entry"]) / pos["entry"]) * 100

                    self.last_positions.append({
                        "symbol": pos["symbol"],
                        "qty": pos["qty"],
                        "entry": pos["entry"],
                        "current": round(current, 2),
                        "pnl": round(pnl, 2),
                        "change": f"{change_pct:+.2f}%",
                        "status": pos["status"],
                        "tp": pos["tp"],
                        "sl": pos["sl"]
                    })

                total_pnl = sum(p["pnl"] for p in self.last_positions)
                self.last_equity = 100000 + total_pnl

                await self.broadcast({
                    "type": "market_update",
                    "timestamp": datetime.now().isoformat(),
                    "data": {
                        "swarm_decisions": self.last_swarm_decisions,
                        "positions": self.last_positions,
                        "equity": {
                            "total": round(self.last_equity, 2),
                            "daily_pnl": round(total_pnl, 2),
                            "daily_change_pct": round((total_pnl / 100000) * 100, 2)
                        },
                        "consensus": self._calculate_consensus()
                    }
                })

            except Exception as e:
                print(f"Error in market data simulation: {e}")

            await asyncio.sleep(2)

    def _calculate_consensus(self):
        agent_weights = {
            "NVIDIA_MACRO": 0.40,
            "MACRO": 0.40,
            "CLAW": 0.35,
            "NVIDIA_SCALPER": 0.25,
            "SCALPER": 0.25,
        }
        direction_map = {
            "BUY": 1,
            "LONG": 1,
            "BULLISH": 1,
            "SELL": -1,
            "SHORT": -1,
            "BEARISH": -1,
            "HOLD": 0,
            "NEUTRAL": 0,
        }

        directional_score = 0.0
        hold_penalty = 0.0
        for decision in self.last_swarm_decisions:
            agent = str(decision.get("agent", "")).upper()
            direction = str(decision.get("decision", "HOLD")).upper()
            confidence = float(decision.get("confidence", 0) or 0)
            if confidence > 1:
                confidence /= 100

            weight = agent_weights.get(agent, 0)
            direction_int = direction_map.get(direction, 0)
            if direction_int == 0:
                hold_penalty += confidence * weight
            else:
                directional_score += direction_int * confidence * weight

        if directional_score > 0:
            final_score = max(0, directional_score - hold_penalty)
        else:
            final_score = min(0, directional_score + hold_penalty)

        if final_score >= 0.40:
            direction = "BUY"
        elif final_score <= -0.40:
            direction = "SELL"
        else:
            direction = "HOLD"

        return {"direction": direction, "strength": min(100, int(abs(final_score) * 100))}

    async def handle_client(self, websocket):
        await self.register(websocket)
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    msg_type = data.get("type")

                    if msg_type == "ping":
                        await websocket.send(json.dumps({"type": "pong", "timestamp": datetime.now().isoformat()}))
                    elif msg_type == "get_state":
                        await websocket.send(json.dumps({
                            "type": "market_update",
                            "timestamp": datetime.now().isoformat(),
                            "data": {
                                "swarm_decisions": self.last_swarm_decisions,
                                "positions": self.last_positions,
                                "equity": {
                                    "total": round(self.last_equity, 2),
                                    "daily_pnl": round(sum(p["pnl"] for p in self.last_positions), 2),
                                    "daily_change_pct": round((sum(p["pnl"] for p in self.last_positions) / 100000) * 100, 2)
                                },
                                "consensus": self._calculate_consensus()
                            }
                        }))
                    else:
                        print(f"Unknown message type: {msg_type}")

                except json.JSONDecodeError:
                    print("Invalid JSON received")
                except Exception as e:
                    print(f"Error handling message: {e}")
        finally:
            self.unregister(websocket)

    async def start(self, host="localhost", port=8000):
        print(f"Starting Apex WebSocket Server on ws://{host}:{port}")
        print("Press Ctrl+C to stop")

        simulation_task = asyncio.create_task(self.simulate_market_data())

        http_runner = web.AppRunner(self.app)
        await http_runner.setup()
        http_site = web.TCPSite(http_runner, "0.0.0.0", 8001)
        await http_site.start()
        print(f"HTTP API server running on http://localhost:8001")

        async with websockets.serve(self.handle_client, host, port):
            print(f"WebSocket server running on ws://{host}:{port}")
            print(f"API Endpoints: http://localhost:8001/api/keys")
            try:
                await asyncio.Future()
            except KeyboardInterrupt:
                print("\nShutting down...")
                self.running = False
                simulation_task.cancel()
                await http_runner.cleanup()

async def main():
    server = ApexWebSocketServer()
    await server.start(host="0.0.0.0", port=8000)

if __name__ == "__main__":
    print("=" * 60)
    print("APEX INSTITUTIONAL - WebSocket Server")
    print("=" * 60)
    print("Starting WebSocket server on ws://localhost:8000")
    print("Starting HTTP API server on http://localhost:8001")
    print("Endpoints:")
    print(" - WebSocket: ws://localhost:8000")
    print(" - API Keys: GET http://localhost:8001/api/keys")
    print(" - API Keys: POST http://localhost:8001/api/keys")
    print(" - API Keys: DELETE http://localhost:8001/api/keys/{id}")
    print("=" * 60)
    asyncio.run(main())
