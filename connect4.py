import json
import sys
from web3 import Web3
from eth_account.messages import encode_defunct
import websockets
import asyncio
import aiohttp

# Configuration
KLAYTN_RPC = "https://rpc.ankr.com/kaia/1c5d4d0451c67d709381054da017466e0bc46956a69481ac5c0c75cf90ebbc38"
PRIVATE_KEYS_FILE = "privkeys.txt"
REFERRAL_CODES_FILE = "referral_codes.txt"
TOKENS_FILE = "bearer_tokens.txt"
WEBSOCKET_URL = "wss://atama.elderglade.com/socket.io/?EIO=4&transport=websocket"
MAX_CONCURRENT_CONNECTIONS = 50
ACCOUNTS_PER_REFERRAL = 10  # Number of accounts to assign to each referral code

def load_private_keys():
    """Load private keys from text file, one per line"""
    try:
        with open(PRIVATE_KEYS_FILE, 'r') as f:
            # Remove empty lines and whitespace
            return [line.strip() for line in f.readlines() if line.strip()]
    except FileNotFoundError:
        print(f"❌ Error: File '{PRIVATE_KEYS_FILE}' not found.")
        return []

def load_referral_codes():
    """Load referral codes from text file, one per line"""
    try:
        with open(REFERRAL_CODES_FILE, 'r') as f:
            return [line.strip() for line in f.readlines() if line.strip()]
    except FileNotFoundError:
        print(f"❌ Error: File '{REFERRAL_CODES_FILE}' not found.")
        return []

def save_token(token):
    """Save bearer token to file"""
    with open(TOKENS_FILE, 'a') as f:
        f.write(f"{token}\n")
    print(f"💾 Saved token to {TOKENS_FILE}")

def distribute_referral_codes(private_keys, referral_codes):
    """Distribute private keys evenly across referral codes"""
    distributed = []
    referral_index = 0
    
    for i, private_key in enumerate(private_keys):
        # If we have referral codes, use them in round-robin fashion
        if referral_codes:
            code = referral_codes[referral_index % len(referral_codes)]
            # Move to next code every ACCOUNTS_PER_REFERRAL accounts
            if (i + 1) % ACCOUNTS_PER_REFERRAL == 0:
                referral_index += 1
        else:
            code = ""
        
        distributed.append((private_key, code))
    
    return distributed

async def handle_websocket(token):
    """Handle WebSocket connection and messaging"""
    print(f"\n🔌 Connecting to WebSocket with token: {token[:15]}...")
    
    try:
        async with websockets.connect(WEBSOCKET_URL, ping_interval=10, ping_timeout=30) as ws:
            print(f"✅ WebSocket connected for token: {token[:15]}...")
            
            # Send authentication message
            auth_message = f'40/socket,{{"token":"{token}"}}'
            await ws.send(auth_message)
            print(f"🔑 Sent authentication: {auth_message[:50]}...")
            
            # Start ping loop
            while True:
                try:
                    # Send updateEnergy every 3 seconds
                    update_message = '42/socket,["updateEnergy",10]'
                    await ws.send(update_message)
                    await asyncio.sleep(3)
                    
                    # Check for incoming messages (optional)
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=1)
                        print(f"📥 Received: {message[:100]}...")
                    except asyncio.TimeoutError:
                        pass
                        
                except websockets.exceptions.ConnectionClosed:
                    print(f"❌ WebSocket connection closed for token: {token[:15]}...")
                    break
                except Exception as e:
                    print(f"❌ WebSocket error for token {token[:15]}...: {str(e)}")
                    break
                    
    except Exception as e:
        print(f"❌ Failed to connect WebSocket for token {token[:15]}...: {str(e)}")

async def process_private_key(session, private_key, referral_code=""):
    """Process a single private key with optional referral code"""
    w3 = Web3(Web3.HTTPProvider(KLAYTN_RPC))
    if not w3.is_connected():
        print("❌ Failed to connect to Kaia blockchain")
        return None

    account = w3.eth.account.from_key(private_key)
    wallet_address = account.address
    print(f"\n🔑 Processing wallet: {wallet_address} | Referral: {referral_code or 'None'}")

    try:
        # Step 1: Get message from ElderGlade
        elderglade_url = "https://atama.elderglade.com/auth/init-kaia"
        async with session.post(elderglade_url, json={"wallet": wallet_address}) as response:
            data = await response.json()
            message_to_sign = data.get("message")

            if not message_to_sign:
                print(f"⚠ No message to sign for wallet {wallet_address}")
                return None

            # Step 2: Sign message
            encoded_message = encode_defunct(text=message_to_sign)
            signed_message = w3.eth.account.sign_message(encoded_message, private_key=private_key)
            signature = signed_message.signature.hex()

            # Step 3: Verify signature with referral code
            verify_url = "https://atama.elderglade.com/auth/kaia"
            async with session.post(verify_url, json={
                "wallet": wallet_address,
                "message": message_to_sign,
                "signature": signature,
                "liffId": "",
                "referralCode": referral_code,
            }) as verify_response:
                verify_data = await verify_response.json()
                if verify_response.status == 200:
                    token = verify_data.get("accessToken")
                    if token:
                        save_token(token)
                        return token
                    else:
                        print(f"❌ No token for wallet {wallet_address}")
                else:
                    print(f"❌ Verification failed for {wallet_address}: {verify_data}")
                return None

    except Exception as e:
        print(f"❌ Error processing wallet {wallet_address}: {str(e)}")
        return None

async def main():
    private_keys = load_private_keys()
    referral_codes = load_referral_codes()
    
    if not private_keys:
        print(f"⛔ No private keys found in '{PRIVATE_KEYS_FILE}'")
        return

    print(f"🔎 Found {len(private_keys)} private key(s) to process")
    print(f"🔗 Found {len(referral_codes)} referral code(s) to distribute")
    
    # Distribute private keys across referral codes
    distributed_keys = distribute_referral_codes(private_keys, referral_codes)
    
    # Create a session for all HTTP requests
    async with aiohttp.ClientSession() as session:
        # Process all private keys concurrently to get tokens
        tokens = []
        
        async def get_token_with_semaphore(item):
            private_key, referral_code = item
            return await process_private_key(session, private_key, referral_code)
        
        # Get all tokens concurrently
        token_tasks = [get_token_with_semaphore(item) for item in distributed_keys]
        tokens = await asyncio.gather(*token_tasks)
        
        # Filter out None values (failed attempts)
        valid_tokens = [token for token in tokens if token is not None]
        
        print(f"\n🚀 Starting WebSocket connections for {len(valid_tokens)} valid tokens")
        
        # Connect all WebSockets concurrently
        ws_tasks = [handle_websocket(token) for token in valid_tokens]
        await asyncio.gather(*ws_tasks)

if __name__ == "__main__":
    # Create a new event loop policy if on Windows
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())