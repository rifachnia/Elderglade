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
OUTPUT_FILE_NEED_REFERRALS = "need_more_referrals.txt"
OUTPUT_FILE_DIAMOND = "diamond_tier.txt"
WEBSOCKET_URL = "wss://atama.elderglade.com/socket.io/?EIO=4&transport=websocket"

def load_private_keys():
    """Load private keys from text file, one per line"""
    try:
        with open(PRIVATE_KEYS_FILE, 'r') as f:
            return [line.strip() for line in f.readlines() if line.strip()]
    except FileNotFoundError:
        print(f"❌ Error: File '{PRIVATE_KEYS_FILE}' not found.")
        return []

def save_to_file(filename, content):
    """Save content to a file"""
    with open(filename, 'a') as f:
        f.write(f"{content}\n")

async def get_referral_info(session, token, private_key):
    """Get referral information via WebSocket"""
    wallet_address = Web3().eth.account.from_key(private_key).address
    try:
        async with websockets.connect(WEBSOCKET_URL) as ws:
            # Authenticate
            await ws.send(f'40/socket,{{"token":"{token}"}}')
            
            while True:
                message = await ws.recv()
                if 'referralSummary' in message or 'tier' in message:
                    try:
                        # Extract the JSON part from the message
                        json_str = message.split('{', 1)[1].rsplit('}', 1)[0]
                        json_str = '{' + json_str + '}'
                        data = json.loads(json_str)
                        
                        referrals = data.get('referralSummary', {}).get('totalReferrals', 0)
                        tier = data.get('tier', 'Unknown')
                        
                        # Save Diamond tier private keys
                        if tier == "Diamond":
                            save_to_file(OUTPUT_FILE_DIAMOND, private_key)
                            print(f"💎 {wallet_address} - Tier: {tier}, {referrals} referrals (Diamond tier - SAVED)")
                        elif referrals < 5:
                            save_to_file(OUTPUT_FILE_NEED_REFERRALS, private_key)
                            print(f"❌ {wallet_address} - Tier: {tier}, {referrals} referrals (needs more)")
                        else:
                            print(f"✅ {wallet_address} - Tier: {tier}, {referrals} referrals")
                        
                        return referrals, tier
                    except json.JSONDecodeError:
                        print(f"⚠ Couldn't parse account data for {wallet_address}")
                        return 0, 'Unknown'
                    
    except Exception as e:
        print(f"❌ WebSocket error for {wallet_address}: {str(e)}")
        return 0, 'Unknown'

async def process_private_key(session, private_key):
    """Process a single private key to get token and check referrals"""
    w3 = Web3(Web3.HTTPProvider(KLAYTN_RPC))
    account = w3.eth.account.from_key(private_key)
    wallet_address = account.address

    try:
        # Step 1: Get message from ElderGlade
        async with session.post(
            "https://atama.elderglade.com/auth/init-kaia",
            json={"wallet": wallet_address}
        ) as response:
            data = await response.json()
            message_to_sign = data.get("message")

            if not message_to_sign:
                print(f"⚠ No message to sign for wallet {wallet_address}")
                return

            # Step 2: Sign message
            encoded_message = encode_defunct(text=message_to_sign)
            signed_message = w3.eth.account.sign_message(encoded_message, private_key=private_key)
            signature = signed_message.signature.hex()

            # Step 3: Verify signature to get token
            async with session.post(
                "https://atama.elderglade.com/auth/kaia",
                json={
                    "wallet": wallet_address,
                    "message": message_to_sign,
                    "signature": signature,
                    "liffId": "",
                    "referralCode": "",
                }
            ) as verify_response:
                verify_data = await verify_response.json()
                if verify_response.status == 200:
                    token = verify_data.get("accessToken")
                    if token:
                        return await get_referral_info(session, token, private_key)
                    else:
                        print(f"❌ No token for wallet {wallet_address}")
                else:
                    print(f"❌ Verification failed for {wallet_address}")

    except Exception as e:
        print(f"❌ Error processing wallet {wallet_address}: {str(e)}")

async def main():
    # Clear output files at start
    open(OUTPUT_FILE_NEED_REFERRALS, 'w').close()
    open(OUTPUT_FILE_DIAMOND, 'w').close()
    
    private_keys = load_private_keys()
    if not private_keys:
        print(f"⛔ No private keys found in '{PRIVATE_KEYS_FILE}'")
        return

    print(f"🔎 Checking {len(private_keys)} private key(s)")
    print(f"💎 Diamond tier keys will be saved to: {OUTPUT_FILE_DIAMOND}")
    print(f"📝 Keys needing referrals will be saved to: {OUTPUT_FILE_NEED_REFERRALS}")
    
    async with aiohttp.ClientSession() as session:
        tasks = [process_private_key(session, key) for key in private_keys]
        await asyncio.gather(*tasks)
    
    # Print summary
    with open(OUTPUT_FILE_DIAMOND, 'r') as f:
        diamond_count = len(f.readlines())
    with open(OUTPUT_FILE_NEED_REFERRALS, 'r') as f:
        need_ref_count = len(f.readlines())
    
    print(f"\n✅ Done checking all private keys")
    print(f"💎 Found {diamond_count} Diamond tier accounts")
    print(f"❌ Found {need_ref_count} accounts needing more referrals")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())