import asyncio
import websockets
import json
import sys

async def run_episode_test():
    url = "ws://127.0.0.1:8000/ws"
    print(f"Connecting to WebSocket server at {url}...")
    try:
        async with websockets.connect(url) as websocket:
            print("Connected! Sending initial updateSettings command...")
            
            # Send initial updateSettings to trigger site generation
            initial_settings = {
                "cmd": "updateSettings",
                "settings": {
                    "boundaryType": "lobed",
                    "atriumPolicy": "central",
                    "singleFloor": True,
                    "publicMode": False,
                    "parallelEnvironments": 4,
                    "maxModules": 25,
                    "learningRate": 0.05,
                    "minEdge": 1.5,
                    "maxEdge": 9.0,
                    "maxEdges": 8,
                    "dictCap": 10,
                    "angleStep": 15.0,
                    "coreSpacing": 8.0,
                    "travelLimit": 12,
                    "seed": 123
                }
            }
            await websocket.send(json.dumps(initial_settings))
            
            # Receive ack event
            raw_msg = await websocket.recv()
            msg = json.loads(raw_msg)
            print(f"Received event: {msg.get('type')} - {msg.get('message')}")
            
            # Receive site event
            raw_msg = await websocket.recv()
            msg = json.loads(raw_msg)
            print(f"Received event of type: {msg.get('type')}")
            if msg.get("type") != "site":
                print("Error: Expected event to be 'site'")
                return
            
            generation_id = msg["generationId"]
            episode = msg["episode"]
            dictionary = msg.get("dictionary", [])
            print(f"Generation: {generation_id}, Episode: {episode}")
            print(f"Dictionary size: {len(dictionary)}")
            
            # Print categories of the modules in the dictionary to verify corridors are removed
            categories = [m.get("category") for m in dictionary]
            print(f"Module categories in synthesized dictionary: {categories}")
            if "corridor" in categories:
                print("FAIL: corridor modules found in dictionary!")
                sys.exit(1)
            else:
                print("PASS: No corridors in dictionary.")
            
            # Send step events
            step_count = 0
            while True:
                step_count += 1
                payload = {
                    "cmd": "step",
                    "generationId": generation_id,
                    "episode": episode
                }
                await websocket.send(json.dumps(payload))
                
                raw_response = await websocket.recv()
                resp = json.loads(raw_response)
                resp_type = resp.get("type")
                
                if resp_type == "placements":
                    metrics = resp.get("metrics", {})
                    print(f"  Step {step_count}: Placements event, moduleCount: {metrics.get('moduleCount')}, fillRatio: {metrics.get('fillRatio'):.4f}")
                elif resp_type == "episodeDone":
                    print("Received episodeDone event!")
                    metrics = resp.get("metrics", {})
                    print("\n--- Final Episode Metrics ---")
                    for key, val in metrics.items():
                        if isinstance(val, (int, float)):
                            print(f"  {key}: {val}")
                    print("-----------------------------")
                    print("\nPASS: Full episode completed successfully without crash!")
                    break
                elif resp_type == "error":
                    print(f"FAIL: Server returned error: {resp.get('message')}")
                    sys.exit(1)
                else:
                    print(f"Received unknown event: {resp_type}")
                    break
    except Exception as e:
        print(f"FAIL: Exception in client connection/test: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_episode_test())
