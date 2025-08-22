import asyncio
import aiohttp
import websockets
import random
import json
import base64
import time
from datetime import datetime
from typing import List, Dict

# Configuration
BASE_URL = "https://jp-nrt-ebe49840.elderglade.com"
HEADERS_TEMPLATE = {
    "accept": "application/json",
    "origin": "https://line.elderglade.com",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
}

ACCOUNT_TEMPLATE = {
    "cookie": "connect.sid=s%3ARD5lENQIF3X0XK6BqVnOzyRUwJ8uhbuo.LGq23RU4UzjJCaWyM6T7%2FvMWwzFhoJOi%2BWHphHighAQ",
    "playerName": "Feral (•ᴥ•)",
    "playerSkinId": 7,
    "platform": "Line"
}

async def load_bearer_tokens() -> List[str]:
    try:
        with open('bearer_tokens.txt', 'r') as file:
            tokens = [line.strip() for line in file if line.strip()]
            return tokens
    except FileNotFoundError:
        print("Error: bearer_tokens.txt file not found")
        return []
    except Exception as e:
        print(f"Error reading tokens: {e}")
        return []

async def create_accounts() -> List[Dict]:
    tokens = await load_bearer_tokens()
    accounts = []
    for i, token in enumerate(tokens):
        account = ACCOUNT_TEMPLATE.copy()
        account["accessToken"] = token
        account["account_id"] = i+1
        accounts.append(account)
    return accounts

async def log(account_id: int, message: str):
    timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    print(f"[{timestamp}] [Bearer Token {account_id}] {message}")

def parse_initial_board(hex_str: str):
    try:
        # Skip the first 4 hex chars (message type)
        hex_data = hex_str[4:]
        raw_bytes = bytes.fromhex(hex_data)

        # Check for empty board case
        if hex_data.endswith("a25b5d"):  # This is '[]' in hex
            return []
        
        # The message format is:
        # 1. Binary header (including 'initial-board-info')
        # 2. JSON data (starting with '[')
        
        # Find the start of JSON data (first '[' character)
        json_start = raw_bytes.find(b'[')
        if json_start == -1:
            return []
            
        # Extract just the JSON portion
        json_data = raw_bytes[json_start:]
        
        # Clean any trailing null bytes
        json_data = json_data.split(b'\x00')[0]
        
        # Parse the JSON
        board = json.loads(json_data.decode('utf-8'))
        return board
        
    except Exception as e:
        print(f"Board parsing error: {e}")
        print(f"Raw hex: {hex_str}")
        print(f"Raw bytes: {raw_bytes}")
        return []

def parse_updated_board(hex_str: str):
    try:
        hex_data = hex_str[4:]  # Skip message type
        raw_bytes = bytes.fromhex(hex_data)
        
        # Find JSON start
        json_start = raw_bytes.find(b'{')
        if json_start == -1:
            return None
        
        # Extract JSON portion
        json_data = raw_bytes[json_start:].split(b'\x00')[0]
        data = json.loads(json_data.decode('utf-8'))
        
        # Get the final board state
        final_board = None
        if 'boardsInfo' in data and len(data['boardsInfo']) > 0:
            final_board = data['boardsInfo'][-1]['boardLayout']
        
        return {
            'final_board': final_board,
            'chainsCount': data.get('chainsInfo', [{}])[0].get('chainsCount', 0) if 'chainsInfo' in data else 0
        }
    except Exception as e:
        print(f"Failed to parse board update: {e}")
        return None

def find_valid_swap(board):
    rows = len(board)
    cols = len(board[0]) if rows > 0 else 0

    def is_valid_position(r, c):
        return 0 <= r < rows and 0 <= c < cols


    def is_match(bd):
        # Horizontal matches
        for r in range(rows):
            for c in range(cols-2):
                if (is_valid_position(r, c) and 
                    is_valid_position(r, c+1) and 
                    is_valid_position(r, c+2)):
                    if bd[r][c] == bd[r][c+1] == bd[r][c+2]:
                        return True
        # Vertical matches
        for r in range(rows-2):
            for c in range(cols):
                if (is_valid_position(r, c) and 
                    is_valid_position(r+1, c) and 
                    is_valid_position(r+2, c)):
                    if bd[r][c] == bd[r+1][c] == bd[r+2][c]:
                        return True
        return False

    for r in range(rows):
        for c in range(cols):
            # Right swap
            if c+1 < cols:
                bd = [row[:] for row in board]
                if (is_valid_position(r, c) and is_valid_position(r, c+1)):
                    bd[r][c], bd[r][c+1] = bd[r][c+1], bd[r][c]
                    if is_match(bd):
                        return (r, c, r, c+1)
            # Down swap
            if r+1 < rows:
                bd = [row[:] for row in board]
                if (is_valid_position(r, c) and is_valid_position(r+1, c)):
                    bd[r][c], bd[r+1][c] = bd[r+1][c], bd[r][c]
                    if is_match(bd):
                        return (r, c, r+1, c)
    return None

def generate_swap_command(r1: int, c1: int, r2: int, c2: int) -> bytes:
    """Generates the EXACT binary command the server requires"""
    # Fixed prefix including the special d92b marker
    prefix = bytes.fromhex("0db2706c617965722d737761702d696e74656e74d92b")
    
    # Create the JSON payload with minimal formatting
    swap_data = [{"row": r1, "column": c1}, {"row": r2, "column": c2}]
    payload = json.dumps(swap_data, separators=(',', ':')).encode('utf-8')
    
    # Combine prefix and payload
    return prefix + payload

async def get_or_create_room(headers: Dict, account_id: int):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BASE_URL}/matchmake/matcher_room", headers=headers) as resp:
                rooms = await resp.json()
                if rooms:
                    return rooms[0]
            async with session.post(f"{BASE_URL}/matchmake/create/matcher_room", headers=headers, json={"private": False}) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
    except Exception as e:
        await log(account_id, f"Room error: {str(e)}")
        return None

async def join_room(room_id: str, payload: Dict, headers: Dict, account_id: int):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{BASE_URL}/matchmake/joinById/{room_id}", json=payload, headers=headers) as resp:
                return await resp.json()
    except Exception as e:
        await log(account_id, f"Error joining room: {str(e)}")
        return None

async def play_game(ws_url: str, headers: Dict, account_id: int):
    async with websockets.connect(
        ws_url,
        extra_headers={
            "Origin": "https://line.elderglade.com",
            "User-Agent": headers["user-agent"]
        }
    ) as ws:
        await ws.send("40/game")
        await log(account_id, "Handshake: 40/game")

        probe = await ws.recv()
        await log(account_id, f"Received probe: {probe.hex() if isinstance(probe, bytes) else probe}")
        await ws.send("5")
        await log(account_id, "Handshake complete")

        commands = [
            bytes.fromhex("0a"),
            bytes.fromhex("0db8706c617965722d726571756573742d677269642d696e666f"),
            bytes.fromhex("0db1706c617965722d67616d652d7265616479")
        ]
        for cmd in commands:
            await ws.send(cmd)
            await log(account_id, f"Sent command: {cmd.hex()}")
            await asyncio.sleep(0.5)

        board = None
        game_active = True
        round_started = False
        round_active = False  # Add this new variable here
        valid_board_received = False

        async def receive_messages():
            nonlocal board, game_active, round_started, round_active, valid_board_received
            expected_hex_prefix = "0db2696e697469616c2d626f6172642d696e666f"

            while game_active:
                try:
                    msg = await ws.recv()
                    hex_msg = msg.hex() if isinstance(msg, bytes) else msg
                    await log(account_id, f"SERVER RAW: {hex_msg}")

                    if hex_msg.startswith(expected_hex_prefix):
                        if hex_msg == expected_hex_prefix + "a25b5d":
                            await log(account_id, "[STATUS] Menerima template kosong, waiting for update...")
                            continue

                        board = parse_initial_board(hex_msg)
                        if board and len(board) > 0:  # Pastikan board tidak kosong
                            valid_board_received = True
                            await log(account_id, f"Valid initial board received: {board}")
                        else:
                            await log(account_id, "Received empty board, waiting...")
                            continue
                        # Now that we have the board, we can proceed
                        round_active = True

                    if hex_msg.startswith('0db0626f6172642d70726f67726573736564'):
                        data = parse_updated_board(hex_msg)
                        if data:
                            board = data['final_board']
                            chain_count = data.get('chainsCount', 0)
                            valid_board_received = True
                        
                        if chain_count > 0:
                            chain_in_progress = True
                            await log(account_id, f"Chain reaction detected ({chain_count} chains)")
                        else:
                            # Only reset chain_in_progress when we get a non-chain update
                            chain_in_progress = False
                        
                        await log(account_id, "Board updated")

                    if "0dab73746172742d726f756e64ac537461727420726f756e6421" in hex_msg:
                        round_started = True
                        round_active = True
                        await log(account_id, "ROUND STARTED")

                    if "67616d652d656e6465642d62792d74696d6572" in hex_msg:
                        await log(account_id, "Game End Detected.")
                        game_active = False
                        round_active = False

                except websockets.exceptions.ConnectionClosed as e:
                    await log(account_id, f"Connection closed in receiver: {e}")
                    game_active = False
                except Exception as e:
                    await log(account_id, f"Receiver error: {e}")
                    game_active = False

        async def send_swaps():
            nonlocal board, game_active, round_started, round_active
            initial_wait_complete = False
            last_board_state = None
            chain_in_progress = False
            random_swap_mode = False  # Track if we're in random swap mode
            round_has_started = False
            last_valid_board_time = 0
            
            while game_active:
                try:
                    if not round_has_started:
                        if round_started:
                            await log(account_id, "Round start detected, resetting flags")
                            round_has_started = True
                            initial_wait_complete = False
                            round_started = False
                            # Wait after round starts before making any moves
                            await asyncio.sleep(1.5)
                        else:
                            await asyncio.sleep(0.1)
                        continue

                    # Check if we have a valid board (either from initial message or update)
                    current_time = time.time()
                    if valid_board_received and board and len(board) > 0 and len(board[0]) > 0:
                        if random_swap_mode:
                            await log(account_id, "Valid board received, exiting random swap mode")
                            random_swap_mode = False
                        last_valid_board_time = current_time
                    elif current_time - last_valid_board_time > 5:  # If no valid board for 5 seconds
                        if not random_swap_mode:
                            await log(account_id, "No valid board received, entering random swap mode")
                            random_swap_mode = True
                            board = [[0]*6 for _ in range(8)]  # Dummy board

                    # Skip if chain is in progress
                    if chain_in_progress:
                        await asyncio.sleep(0.3)
                        continue

                    # Random swap mode (when we don't have valid board info)
                    if random_swap_mode:
                        if valid_board_received and board and len(board) > 0 and len(board[0]) > 0:
                            await log(account_id, "Valid board received, exiting random swap mode")
                            random_swap_mode = False
                            continue
                        
                        # Generate random swap
                        rows = len(board)
                        cols = len(board[0]) if rows > 0 else 0
                        
                        if rows > 0 and cols > 0:
                            # Randomly choose direction (0=right, 1=down)
                            direction = random.randint(0, 1)
                            r1 = random.randint(0, rows-1)
                            c1 = random.randint(0, cols-1)
                            
                            if direction == 0:  # Right swap
                                c2 = min(c1 + 1, cols-1)
                                r2 = r1
                            else:  # Down swap
                                r2 = min(r1 + 1, rows-1)
                                c2 = c1
                            
                            swap_cmd = generate_swap_command(r1, c1, r2, c2)
                            await log(account_id, f"Sending RANDOM swap: ({r1},{c1})<->({r2},{c2})")
                            await ws.send(swap_cmd)
                            await asyncio.sleep(1)
                            continue

                    # Skip if board hasn't changed or chain is in progress
                    if board == last_board_state or chain_in_progress:
                        await asyncio.sleep(0.3)
                        continue

                    valid_swap = find_valid_swap(board)
                    if not valid_swap:
                        await log(account_id, "No valid swap found!")
                        await asyncio.sleep(0.5)
                        continue

                    r1, c1, r2, c2 = valid_swap
                    swap_cmd = generate_swap_command(r1, c1, r2, c2)
                    
                    await log(account_id, f"Sending swap: ({r1},{c1})<->({r2},{c2})")
                    await ws.send(swap_cmd)
                    
                    # Store current board state and mark potential chain start
                    last_board_state = [row[:] for row in board]
                    
                    # Wait longer after sending a swap to allow for chains
                    await asyncio.sleep(1.8)

                except Exception as e:
                    await log(account_id, f"Swap error: {str(e)}")
                    game_active = False

        receiver_task = asyncio.create_task(receive_messages())
        sender_task = asyncio.create_task(send_swaps())

        try:
            await asyncio.gather(receiver_task, sender_task)
        except Exception as e:
            await log(account_id, f"Error game loop: {e}")
        finally:
            game_active = False
            receiver_task.cancel()
            sender_task.cancel()
            try:
                await receiver_task
            except:
                pass
            try:
                await sender_task
            except:
                pass

async def run_account(account: Dict, play_count: int = 5):
    headers = HEADERS_TEMPLATE.copy()
    headers["cookie"] = account["cookie"]
    account_id = account["account_id"]

    payload = {
        "playerName": account["playerName"],
        "playerSkinId": account["playerSkinId"],
        "accessToken": account["accessToken"],
        "platform": account["platform"]
    }

    last_room_ids = []
    successful_plays = 0

    while successful_plays < play_count:
        attempt = successful_plays + 1
        await log(account_id, f"Attempt {attempt}/{play_count}")

        try:
            await log(account_id, "Finding room...")
            room = await get_or_create_room(headers, account_id)

            if not room:
                await log(account_id, "No rooms available")
                await asyncio.sleep(0.005)
                continue

            if room['roomId'] in last_room_ids:
                await log(account_id, f"Ignoring duplicate room: {room['roomId']}")
                await asyncio.sleep(0.005)
                continue

            last_room_ids.append(room['roomId'])
            if len(last_room_ids) > 5:
                last_room_ids.pop(0)

            await log(account_id, f"Found room: {room['roomId']}")

            join_data = await join_room(room['roomId'], payload, headers, account_id)
            if not join_data or "sessionId" not in join_data:
                await log(account_id, "Failed to join room")
                await asyncio.sleep(0.005)
                continue

            await log(account_id, f"Joined! Session ID: {join_data['sessionId']}")

            ws_url = f"wss://{room['publicAddress']}/{room['processId']}/{room['roomId']}?sessionId={join_data['sessionId']}"

            try:
                await play_game(ws_url, headers, account_id)
                successful_plays += 1
                await log(account_id, f"Successfully completed play {successful_plays}/{play_count}")
            except Exception as e:
                await log(account_id, f"Game error: {str(e)}")
                continue

        except Exception as e:
            await log(account_id, f"Error during attempt {attempt}: {str(e)}")
            await asyncio.sleep(0.1)

async def main():
    accounts = await create_accounts()

    if not accounts:
        await log(0, "No accounts to process. Please check bearer_tokens.txt")
        return

    await asyncio.gather(
        *[run_account(account) for account in accounts]
    )

    await log(0, "All accounts completed")

if __name__ == "__main__":
    asyncio.run(main())
