# 🛍️ Bazaar — Decentralized Marketplace System with AI Fraud Detection and Geo-Tracking

A feature-rich marketplace app built with Python Flask, SQLite, Leaflet maps, and real-time chat.

## ✨ Features

| Feature | Details |
|---|---|
| 🤖 AI Verification | Heuristic engine detects fake/suspicious listings with score & flags |
| 🗺️ Live Map | Leaflet + OpenStreetMap — all listings plotted, distance & delivery time |
| 💬 Real-Time Chat | Socket.IO powered buyer-seller messaging per listing |
| 🤖 AI Chatbot | Per-listing assistant — price, safety, delivery, negotiation tips |
| 🔐 CAPTCHA | SVG-based math/text CAPTCHA on login & register — no external API |
| 💳 Payments | Cash on Delivery, UPI, Bank Transfer options |
| 🔍 Smart Search | Filter by category, price, city, condition, sort by price/date |
| ❤️ Favorites | Save & manage wishlist |
| ⭐ Reviews | Rate & review sellers |
| 🚩 Report System | Flag suspicious listings |
| 📱 Responsive | Mobile-first design |
| 🗄️ SQLite | Zero-config local database |

## 🚀 Setup & Run 


```bash
# 1. Create virtual environment
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
python app.py

# 4. Open in browser
# http://localhost:5000
```

## 📁 Project Structure

```
bazaar/
├── app.py                  # Main Flask app, routes, models, AI logic
├── requirements.txt
├── bazaar.db               # SQLite DB (auto-created)
├── static/
│   └── uploads/            # Uploaded listing photos
└── templates/
    ├── base.html           # Shared layout, nav, footer
    ├── index.html          # Homepage
    ├── listings.html       # Browse & filter
    ├── listing_detail.html # Single listing + AI chat + map
    ├── post_listing.html   # Create listing + AI pre-analysis
    ├── map.html            # Full map view
    ├── chat.html           # Real-time buyer-seller chat
    ├── messages.html       # Inbox
    ├── profile.html        # Seller profile
    ├── my_listings.html    # Dashboard
    ├── favorites.html      # Wishlist
    ├── register.html       # Sign up + CAPTCHA
    ├── login.html          # Sign in + CAPTCHA
    └── partials/
        └── listing_card.html
```

## 🤖 AI Features Explained

### Fake Product Detection
Every listing runs through a heuristic analyzer on submit:
- Suspicious phrases (advance fee, free money, lottery, etc.)
- Unrealistically low prices for category
- Too-short descriptions
- External contact requests (bypassing in-app chat)
- Excessive capitalization

Score 0–100:
- 🟢 ≥70 = AI Verified  
- 🟡 40–69 = Needs Review  
- 🔴 <40 = High Risk

### AI Chatbot
Per-listing contextual assistant using keyword matching. Understands:
price, condition, delivery, safety, payment, location, negotiation.

## 🗺️ Maps
- Uses free OpenStreetMap via Leaflet.js — no API key needed
- Reverse geocoding via Nominatim (free)
- Distance calculation: Haversine formula
- Delivery time estimate: 30 km/h average speed

## 💳 Payment Methods

- Cash on Delivery (COD)
- UPI (Unified Payment Interface)
- Bank Transfer
- Any method (seller's choice)


## 🔐 Security 
- CAPTCHA on all auth forms (custom SVG, no 3rd party)
- Password hashing (Werkzeug PBKDF2)
- Login required for posting, messaging, reviews
- Report system for community moderation
- AI fraud detection on every listing

  output:
  <img width="1350" height="721" alt="Screenshot 2026-04-13 220107" src="https://github.com/user-attachments/assets/a3e8fc7d-7186-4fb4-9813-a2ea6244f91d" />
<img width="1348" height="719" alt="Screenshot 2026-04-13 220118" src="https://github.com/user-attachments/assets/29880762-5744-4cdc-8f70-7487dee93ba4" />
<img width="1342" height="717" alt="Screenshot 2026-04-13 220138" src="https://github.com/user-attachments/assets/ed843ee1-0f7b-4df7-82d5-6c8c447c9b63" />


