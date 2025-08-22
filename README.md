# Elderglade
AI-assisted Elderglade for automating gameplay, referral tracking, and tier checking.

⚠️ Note: These scripts are for learning and experimentation only.

# 🕹️ ElderGlade

This repository contains a collection of Python scripts for automating gameplay and account management in **ElderGlade**.

## 📂 Project Structure
- **connect4.py**  
  Initializes WebSocket connections to ElderGlade, authenticates accounts with private keys, and generates **bearer tokens**.  
  Must be run **before** `eldergame.py`.

- **eldergame.py**  
  Connects to the ElderGlade game server, joins match rooms, and automatically plays the Connect-4 style game.  
  The bot analyzes the board, finds possible moves, and consumes all attempts (up to 10 per session).

- **tierchecker.py**  
  Checks the account **tier** and referral status for Kaia wallets.  
  - Saves Diamond-tier accounts into `diamond_tier.txt`  
  - Saves accounts that need more referrals into `need_more_referrals.txt`

## ⚙️ Features
- ✅ Generates and saves bearer tokens from Kaia wallets  
- ✅ Joins ElderGlade WebSocket game sessions automatically  
- ✅ Reads all possible board moves and executes valid swaps  
- ✅ Plays continuously until all attempts (10) are used  
- ✅ Checks account tiers (Bronze, Silver, Gold, Diamond)  
- ✅ Saves referral progress for account management  

## 🚀 Usage
1. Prepare your input files:
   - `privkeys.txt` → one private key per line  
   - `referral_codes.txt` → referral codes (optional)  
   - `bearer_tokens.txt` → will be generated automatically  

2. Run the scripts in order:
   ```bash
   # 1. Generate bearer tokens and connect wallets
   python connect4.py

   # 2. Start playing the ElderGlade game
   python eldergame.py

   # 3. (Optional) Check tiers and referral progress
   python tierchecker.py
