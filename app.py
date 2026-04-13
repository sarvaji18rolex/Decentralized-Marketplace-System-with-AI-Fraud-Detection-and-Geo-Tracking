from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os, json, uuid, math, random, string, re

app = Flask(__name__)
app.config['SECRET_KEY'] = 'bazaar-super-secret-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bazaar.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ─── MODELS ────────────────────────────────────────────────────────────────────

class User(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80),  unique=True, nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    phone         = db.Column(db.String(20))
    bio           = db.Column(db.Text)
    lat           = db.Column(db.Float)
    lng           = db.Column(db.Float)
    city          = db.Column(db.String(100))
    is_verified   = db.Column(db.Boolean, default=False)
    rating        = db.Column(db.Float,   default=0.0)
    total_ratings = db.Column(db.Integer, default=0)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    listings      = db.relationship('Listing', backref='seller', lazy=True)
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy=True)

    def set_password(self, p):   self.password_hash = generate_password_hash(p)
    def check_password(self, p): return check_password_hash(self.password_hash, p)
    def get_id(self):            return str(self.id)
    is_authenticated = True
    is_anonymous     = False
    is_active        = True


class Category(db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    name     = db.Column(db.String(100), nullable=False)
    icon     = db.Column(db.String(10))
    slug     = db.Column(db.String(100), unique=True)
    listings = db.relationship('Listing', backref='category', lazy=True)


class Listing(db.Model):
    id             = db.Column(db.Integer, primary_key=True)
    title          = db.Column(db.String(200), nullable=False)
    description    = db.Column(db.Text,        nullable=False)
    price          = db.Column(db.Float,       nullable=False)
    condition      = db.Column(db.String(50))
    category_id    = db.Column(db.Integer, db.ForeignKey('category.id'))
    seller_id      = db.Column(db.Integer, db.ForeignKey('user.id'))
    images         = db.Column(db.Text, default='[]')
    lat            = db.Column(db.Float)
    lng            = db.Column(db.Float)
    address        = db.Column(db.String(300))
    city           = db.Column(db.String(100))
    is_active      = db.Column(db.Boolean, default=True)
    is_featured    = db.Column(db.Boolean, default=False)
    ai_verified    = db.Column(db.Boolean, default=False)
    ai_score       = db.Column(db.Float,   default=0.0)
    ai_flags       = db.Column(db.Text, default='[]')
    views          = db.Column(db.Integer, default=0)
    payment_method = db.Column(db.String(50), default='cash')
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)

    def get_images(self):
        try:    return json.loads(self.images)
        except: return []

    def get_ai_flags(self):
        try:    return json.loads(self.ai_flags)
        except: return []


class Message(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    sender_id   = db.Column(db.Integer, db.ForeignKey('user.id'))
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    listing_id  = db.Column(db.Integer, db.ForeignKey('listing.id'))
    content     = db.Column(db.Text, nullable=False)
    is_read     = db.Column(db.Boolean, default=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    listing     = db.relationship('Listing', backref='messages')
    receiver    = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')


class Favorite(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'))
    listing_id = db.Column(db.Integer, db.ForeignKey('listing.id'))
    listing    = db.relationship('Listing', backref='favorites')


class Review(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    reviewer_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    seller_id   = db.Column(db.Integer, db.ForeignKey('user.id'))
    listing_id  = db.Column(db.Integer, db.ForeignKey('listing.id'))
    rating      = db.Column(db.Integer)
    comment     = db.Column(db.Text)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    reviewer    = db.relationship('User', foreign_keys=[reviewer_id])


class Report(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    listing_id  = db.Column(db.Integer, db.ForeignKey('listing.id'))
    reason      = db.Column(db.String(200))
    details     = db.Column(db.Text)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(uid): return User.query.get(int(uid))


# ─── HELPERS ───────────────────────────────────────────────────────────────────

def allowed_file(fn):
    return '.' in fn and fn.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def generate_captcha():
    chars = string.ascii_uppercase.replace('O','').replace('I','') + '23456789'
    code  = ''.join(random.choices(chars, k=6))
    session['captcha'] = code
    return code

def verify_captcha(user_input):
    return session.get('captcha','').upper() == user_input.upper()

# ─── AI ENGINE ─────────────────────────────────────────────────────────────────

SUSPICIOUS_PHRASES = [
    'free money','guaranteed profit','lottery winner','send money first',
    'western union','wire transfer','advance fee','nigerian prince',
    'million dollar','secret formula','100% guaranteed','no risk investment',
    'click here now','act now','whatsapp me directly','telegram only',
    'pay upfront before','inheritance money','prize money','you have won',
]

PRICE_FLOORS = {
    'Electronics':500,'Vehicles':5000,'Properties':50000,
    'Furniture':300,'Computers':1000,'Sports':100,
}

def ai_analyze(title, description, price, category_name):
    flags, score = [], 100.0
    combined = (title + ' ' + description).lower()

    for phrase in SUSPICIOUS_PHRASES:
        if phrase.lower() in combined:
            flags.append(f'Suspicious phrase: "{phrase}"')
            score -= 20

    floor = PRICE_FLOORS.get(category_name, 50)
    if price < 1:
        flags.append('Price is zero or negative')
        score -= 30
    elif price < floor * 0.05:
        flags.append(f'Price ₹{price:.0f} seems unrealistically low for {category_name}')
        score -= 15

    if len(description.strip()) < 30:
        flags.append('Description too short — add details to build buyer trust')
        score -= 10
    elif len(description.strip()) < 80:
        flags.append('Description could be more detailed')
        score -= 5

    ext = ['whatsapp','telegram','call me outside','reach me at','contact me at']
    for c in ext:
        if c in combined:
            flags.append('External contact request — use in-app chat for buyer safety')
            score -= 12
            break

    if len(title) > 5 and sum(1 for c in title if c.isupper()) / len(title) > 0.65:
        flags.append('Excessive capitalization — may appear spammy')
        score -= 8

    if title.count('!') > 2 or description.count('!') > 5:
        flags.append('Too many exclamation marks')
        score -= 5

    if re.search(r'\b[6-9]\d{9}\b|\b\+91\d{10}\b', description):
        flags.append('Phone number in description — use chat feature instead')
        score -= 8

    score = max(0, min(100, score))
    verified = score >= 65 and len(flags) == 0
    return round(score, 1), flags, verified


# ─── DEMO DATA ─────────────────────────────────────────────────────────────────

DEMO_LISTINGS = [
    # Electronics
    {"title":"Apple iPhone 14 Pro 256GB Deep Purple","cat":"Electronics","price":72000,"condition":"like_new","city":"Mumbai","lat":19.0760,"lng":72.8777,"desc":"Bought 6 months ago, always used with case and screen protector. Battery health 97%. Comes with original box, charger, and earphones. No scratches, no repairs ever done. Face ID works perfectly. Selling because upgrading to iPhone 15.","payment":"upi","featured":True},
    {"title":"Samsung Galaxy S23 Ultra 512GB — Phantom Black","cat":"Electronics","price":85000,"condition":"like_new","city":"Delhi","lat":28.7041,"lng":77.1025,"desc":"Purchased 4 months ago from Samsung official store. Comes with full accessories including original S-Pen. Battery health 95%. Minor usage marks on back invisible with case. Selling because upgrading to S24 Ultra.","payment":"upi","featured":True},
    {"title":"Sony WH-1000XM5 Noise Cancelling Headphones","cat":"Electronics","price":18500,"condition":"good","city":"Bangalore","lat":12.9716,"lng":77.5946,"desc":"Best-in-class noise cancellation headphones. Bought 8 months ago. Works flawlessly. Slight wear on ear cushions but fully functional. Comes with carry case, USB-C cable, and airline adapter. 30-hour battery life.","payment":"any"},
    {"title":"MacBook Air M2 8GB 256GB Space Grey","cat":"Electronics","price":89000,"condition":"like_new","city":"Hyderabad","lat":17.3850,"lng":78.4867,"desc":"Used for just 3 months. Battery cycle count only 28. No dents, no scratches, screen pristine. Original MagSafe charger included. Selling as I need a MacBook Pro for video editing work.","payment":"bank","featured":True},
    {"title":"OnePlus Nord CE 3 Lite 5G 128GB Blue Tide","cat":"Electronics","price":14500,"condition":"good","city":"Pune","lat":18.5204,"lng":73.8567,"desc":"6 months old, excellent battery life with 67W fast charging. 108MP camera takes great shots. Minor scratches on back. Full kit with original box and charger. No repairs done, all features working.","payment":"cash"},
    {"title":"JBL Flip 6 Bluetooth Portable Speaker","cat":"Electronics","price":6500,"condition":"good","city":"Chennai","lat":13.0827,"lng":80.2707,"desc":"Bought 1 year ago. IP67 waterproof, amazing 360-degree sound. Works perfectly with 12-hour battery life intact. Minor scuff on bottom from use. Original box and charging cable included.","payment":"cash"},
    {"title":"iPad Air 5th Gen 64GB WiFi + Apple Pencil 2","cat":"Electronics","price":49000,"condition":"like_new","city":"Kolkata","lat":22.5726,"lng":88.3639,"desc":"Bought 5 months ago. Used only for reading and Netflix. Absolutely no scratches on screen or body. Comes with Apple Pencil 2, Smart Folio case in Navy Blue, and original charger. Battery health 99%.","payment":"upi"},
    {"title":"Canon EOS 200D II DSLR + 18-55mm Lens","cat":"Electronics","price":38000,"condition":"good","city":"Jaipur","lat":26.9124,"lng":75.7873,"desc":"2 years old, rarely used. 24.1MP APS-C, 4K video recording. Comes with 18-55mm kit lens, 2 original batteries, 32GB Lexar SD card, UV filter, and padded camera bag. Sensor spotless.","payment":"bank"},

    # Vehicles
    {"title":"Honda Activa 6G 2022 — Single Owner, 12K km","cat":"Vehicles","price":68000,"condition":"good","city":"Mumbai","lat":19.1136,"lng":72.8697,"desc":"2022 model, 12,000 km driven. All documents clear — RC, insurance valid till Dec 2025. Single owner, regular servicing at Honda service center. New MRF tyres 3 months ago. Gets 60 kmpl average. No accidents.","payment":"cash","featured":True},
    {"title":"Royal Enfield Bullet 350 2020 — Classic Look","cat":"Vehicles","price":145000,"condition":"good","city":"Delhi","lat":28.6139,"lng":77.2090,"desc":"2020 model Classic 350, 25,000 km. All original parts, no modifications. Fully serviced 1 month ago. Insurance valid till Dec 2024. Minor seat wear only. All original documents. Pure bike enthusiast vehicle.","payment":"bank"},
    {"title":"Hero Splendor Plus 2021 — 70 kmpl Mileage","cat":"Vehicles","price":52000,"condition":"good","city":"Lucknow","lat":26.8467,"lng":80.9462,"desc":"2021 model, 18,000 km. Excellent fuel efficiency of 70+ kmpl. All papers clear, insurance valid. Regular servicing done every 3000 km. No accidents, single owner since purchase.","payment":"cash"},
    {"title":"Maruti Suzuki Alto 800 2019 with CNG Kit","cat":"Vehicles","price":310000,"condition":"good","city":"Ahmedabad","lat":23.0225,"lng":72.5714,"desc":"2019 model, 42,000 km. Petrol + sequential CNG kit fitted from showroom. All documents clear. Minor scratches on front bumper. AC working perfectly. Regularly serviced. Best for city driving.","payment":"bank","featured":True},

    # Fashion
    {"title":"Nike Air Jordan 1 Retro High OG Chicago — US 9","cat":"Fashion","price":8500,"condition":"like_new","city":"Mumbai","lat":19.0596,"lng":72.8295,"desc":"Bought for ₹12,000, worn only twice to two events. Chicago colorway (Red/Black/White). Comes with original Nike box, spare laces, and receipt. Size US 9 / UK 8 / EU 42.5. Zero creasing, sole clean.","payment":"cash"},
    {"title":"Levi's 511 Slim Jeans Dark Indigo — 32x32","cat":"Fashion","price":1800,"condition":"good","city":"Bangalore","lat":12.9352,"lng":77.6245,"desc":"Bought 6 months ago from Levi's store, worn maybe 10 times. Dark indigo wash with no fading. Waist 32, length 32. 100% authentic, not a replica. Washed and ready. Great condition.","payment":"upi"},
    {"title":"Zara Oversized Blazer Beige — Women M","cat":"Fashion","price":2200,"condition":"like_new","city":"Chennai","lat":13.0550,"lng":80.2100,"desc":"Bought for ₹5,500 from Zara, worn once to an office event. Classic beige color, size M. No stains, no pilling, no loose threads. Dry cleaned and stored in garment bag.","payment":"cash"},

    # Home & Garden
    {"title":"IKEA KALLAX 4x4 Shelf Unit White — Self Pickup","cat":"Home & Garden","price":8000,"condition":"good","city":"Delhi","lat":28.6562,"lng":77.2411,"desc":"4x4 KALLAX in white, 2 years old. No major damage, all original bolts and dowels included. Includes 4 inserts (2 with hinged doors, 2 open). Must self-pickup from Dwarka Sector 12. Selling because relocating.","payment":"cash"},
    {"title":"Philips Air Purifier AC1215 HEPA — Works Great","cat":"Home & Garden","price":7500,"condition":"good","city":"Noida","lat":28.5355,"lng":77.3910,"desc":"1 year old. HEPA filter replaced 2 months ago. Covers up to 400 sq ft (3–4 BHK). All 3 speed settings work. Air quality indicator accurate. Removes 99.97% allergens. With original remote and box.","payment":"upi"},
    {"title":"Prestige Induction Cooktop PIC 3.0 — 2000W","cat":"Home & Garden","price":1800,"condition":"good","city":"Pune","lat":18.5314,"lng":73.8446,"desc":"2 years old, fully functional. All 8 cooking preset modes work perfectly. Minor hairline scratch on glass top — no cracks. Auto shut-off works. Sells with original box and user manual.","payment":"cash"},

    # Sports
    {"title":"Yonex Astrox 88S Play Badminton Racket","cat":"Sports","price":2800,"condition":"good","city":"Hyderabad","lat":17.4399,"lng":78.4983,"desc":"6 months old. Medium-flex shaft, excellent for attacking smash play. BG65 string intact and well-tensioned. Slight scuff on frame corner from court wall contact. Comes with full cover. Great for intermediate players.","payment":"cash"},
    {"title":"Decathlon Rockrider MTB 520 Cycle 27.5-inch","cat":"Sports","price":14500,"condition":"good","city":"Bangalore","lat":12.9259,"lng":77.5822,"desc":"1 year old, 27-speed Shimano Altus groupset. RockShox front suspension, hydraulic disc brakes. Tyres at 80% tread. Recently full-serviced at Decathlon. Minor frame scratches. Self-pickup from Koramangala only.","payment":"cash","featured":True},
    {"title":"Yoga Mat Liforme + 2 Blocks + Straps Bundle","cat":"Sports","price":1200,"condition":"good","city":"Mumbai","lat":19.0178,"lng":72.8478,"desc":"10mm Liforme natural rubber mat, 2 cork yoga blocks, and 2 cotton straps. 1 year old, used 3x/week. Mat deep-cleaned and dried. Light pilling near short edges, fully usable and grippy.","payment":"upi"},

    # Books
    {"title":"UPSC CSE Complete Study Kit 2024 — Lightly Used","cat":"Books","price":3500,"condition":"good","city":"Delhi","lat":28.6304,"lng":77.2177,"desc":"Full kit: complete NCERT set (Class 6–12), Laxmikanth Indian Polity 6th Ed, Spectrum Modern History, Shankar Environment, Laxmikanth Ethics 3rd Ed. All books lightly highlighted. No torn or missing pages.","payment":"cash"},
    {"title":"Rich Dad Poor Dad + 5 Finance Books Combo","cat":"Books","price":700,"condition":"good","city":"Chennai","lat":13.0350,"lng":80.2100,"desc":"Bundle includes: Rich Dad Poor Dad (Kiyosaki), Psychology of Money (Housel), Atomic Habits (Clear), Almanack of Naval Ravikant, Zero to One (Thiel). All in great condition, light reading only.","payment":"cash"},

    # Furniture
    {"title":"Godrej Interio 3-Door Wardrobe Walnut Finish","cat":"Furniture","price":12000,"condition":"good","city":"Mumbai","lat":19.1200,"lng":72.9050,"desc":"3 years old, 3-door with full-length mirror on center door and 2 bottom drawers. Solid engineered wood with walnut laminate. Minor scuff on left panel. All hinges, locks, and drawer runners work. Self-pickup only.","payment":"cash"},
    {"title":"Solid Sheesham Wood Study Table with Drawer","cat":"Furniture","price":4500,"condition":"good","city":"Jaipur","lat":26.9197,"lng":75.7875,"desc":"Sheesham (Indian Rosewood) table, 1.2m wide x 60cm deep. 2 side drawers with smooth metal runners. Sturdy, no wobble. Minor ink stains on surface (easily sanded). Ideal for WFH. Self-pickup Malviya Nagar.","payment":"cash"},

    # Pets
    {"title":"5-Level Cat Tree Tower with Hammock — Like New","cat":"Pets","price":2200,"condition":"like_new","city":"Bangalore","lat":12.9550,"lng":77.6150,"desc":"Bought 3 months ago, my cats completely ignored it. 5 levels with sisal scratching posts, hanging hammock, enclosed condo, and dangling toy. All platforms intact. Minor fur on rope — easy to clean. Very stable.","payment":"cash"},
    {"title":"Labrador Puppy Accessories Bundle — 10 Items","cat":"Pets","price":1800,"condition":"good","city":"Pune","lat":18.5644,"lng":73.7769,"desc":"Complete bundle: retractable leash (5m), adjustable harness (size M, 8–15kg), 2 stainless steel bowls, training clicker, 4 chew toys, silicone treat pouch, and slicker brush. Puppy outgrew harness. All cleaned.","payment":"cash"},
]

DEMO_USERS = [
    {"username":"rahul_tech","email":"rahul@demo.com","phone":"9876543210","city":"Mumbai","lat":19.0760,"lng":72.8777,"bio":"Tech enthusiast, selling gadgets I no longer use. Always fast responses, honest descriptions.","rating":4.7,"reviews":23},
    {"username":"priya_fashion","email":"priya@demo.com","phone":"9876543211","city":"Delhi","lat":28.7041,"lng":77.1025,"bio":"Fashion lover decluttering my wardrobe. All items are genuine and as described.","rating":4.9,"reviews":41},
    {"username":"kiran_motors","email":"kiran@demo.com","phone":"9876543212","city":"Bangalore","lat":12.9716,"lng":77.5946,"bio":"Bike mechanic and two-wheeler enthusiast. Transparent about vehicle condition.","rating":4.5,"reviews":18},
    {"username":"sneha_home","email":"sneha@demo.com","phone":"9876543213","city":"Hyderabad","lat":17.3850,"lng":78.4867,"bio":"Interior designer. Selling quality home goods to make space for new projects.","rating":4.8,"reviews":35},
    {"username":"amit_sports","email":"amit@demo.com","phone":"9876543214","city":"Pune","lat":18.5204,"lng":73.8567,"bio":"Sports coach and fitness enthusiast. Always upgrading equipment.","rating":4.6,"reviews":12},
]

DEMO_REVIEWS = [
    "Excellent seller! Item exactly as described. Super fast response.",
    "Very honest and cooperative. Smooth transaction. Highly recommended!",
    "Product in excellent condition, better than expected. 5 stars!",
    "Quick meetup arranged, item was exactly as in photos. Good experience.",
    "Trustworthy seller. Fair price. Will definitely buy from again.",
    "Neat packaging, item in perfect condition. Totally recommend!",
    "Very responsive and helpful. Great person to deal with.",
    "No hassles, straightforward transaction. Item works perfectly.",
]

def seed_demo_data():
    if Category.query.count() > 0:
        return
    print("Seeding demo data...")
    cat_map = {}
    for name, icon, slug in [
        ('Electronics','📱','electronics'),('Vehicles','🚗','vehicles'),
        ('Fashion','👗','fashion'),('Home & Garden','🏠','home-garden'),
        ('Sports','⚽','sports'),('Books','📚','books'),
        ('Furniture','🛋','furniture'),('Jobs','💼','jobs'),
        ('Properties','🏘','properties'),('Pets','🐾','pets'),
    ]:
        c = Category(name=name, icon=icon, slug=slug)
        db.session.add(c); db.session.flush()
        cat_map[name] = c.id
    db.session.commit()

    user_ids = []
    for ud in DEMO_USERS:
        u = User(username=ud['username'], email=ud['email'], phone=ud['phone'],
                 city=ud['city'], lat=ud['lat'], lng=ud['lng'], bio=ud['bio'],
                 rating=ud['rating'], total_ratings=ud['reviews'], is_verified=True)
        u.set_password('demo1234')
        db.session.add(u); db.session.flush()
        user_ids.append(u.id)
    db.session.commit()

    for i, ld in enumerate(DEMO_LISTINGS):
        cat_id    = cat_map.get(ld['cat'], 1)
        seller_id = user_ids[i % len(user_ids)]
        jlat = round(ld['lat'] + random.uniform(-0.04, 0.04), 4)
        jlng = round(ld['lng'] + random.uniform(-0.04, 0.04), 4)
        score, flags, verified = ai_analyze(ld['title'], ld['desc'], ld['price'], ld['cat'])
        l = Listing(title=ld['title'], description=ld['desc'], price=ld['price'],
                    condition=ld['condition'], category_id=cat_id, seller_id=seller_id,
                    lat=jlat, lng=jlng, address=f"Near {ld['city']} centre", city=ld['city'],
                    images=json.dumps([]), payment_method=ld.get('payment','cash'),
                    is_featured=ld.get('featured',False), ai_score=score,
                    ai_flags=json.dumps(flags), ai_verified=verified, is_active=True,
                    views=random.randint(5,280),
                    created_at=datetime.utcnow()-timedelta(days=random.randint(0,30)))
        db.session.add(l); db.session.flush()
        if random.random() > 0.4:
            rid = user_ids[(user_ids.index(seller_id)+1) % len(user_ids)]
            db.session.add(Review(reviewer_id=rid, seller_id=seller_id, listing_id=l.id,
                                  rating=random.randint(4,5), comment=random.choice(DEMO_REVIEWS),
                                  created_at=datetime.utcnow()-timedelta(days=random.randint(1,20))))
    db.session.commit()
    print(f"Seeded {len(DEMO_LISTINGS)} listings across {len(DEMO_USERS)} sellers.")


# ─── ROUTES ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    cats     = Category.query.all()
    featured = Listing.query.filter_by(is_active=True, is_featured=True).order_by(Listing.created_at.desc()).limit(8).all()
    recent   = Listing.query.filter_by(is_active=True).order_by(Listing.created_at.desc()).limit(16).all()
    total    = Listing.query.filter_by(is_active=True).count()
    users_c  = User.query.count()
    return render_template('index.html', categories=cats, featured=featured, recent=recent,
                           total_listings=total, total_users=users_c)


@app.route('/register', methods=['GET','POST'])
def register():
    captcha_code = generate_captcha()
    if request.method == 'POST':
        if not verify_captcha(request.form.get('captcha','')):
            flash('Invalid CAPTCHA. Please try again.','error')
            return redirect(url_for('register'))
        username = request.form['username'].strip()
        email    = request.form['email'].strip().lower()
        if User.query.filter_by(email=email).first():
            flash('Email already registered.','error'); return redirect(url_for('register'))
        if User.query.filter_by(username=username).first():
            flash('Username already taken.','error'); return redirect(url_for('register'))
        u = User(username=username, email=email, phone=request.form.get('phone',''))
        u.set_password(request.form['password'])
        db.session.add(u); db.session.commit()
        login_user(u)
        flash('Welcome to Bazaar! 🎉','success')
        return redirect(url_for('index'))
    return render_template('register.html', captcha_code=captcha_code)


@app.route('/login', methods=['GET','POST'])
def login():
    captcha_code = generate_captcha()
    if request.method == 'POST':
        if not verify_captcha(request.form.get('captcha','')):
            flash('Invalid CAPTCHA.','error'); return redirect(url_for('login'))
        u = User.query.filter_by(email=request.form['email'].strip().lower()).first()
        if u and u.check_password(request.form['password']):
            login_user(u); return redirect(request.args.get('next') or url_for('index'))
        flash('Invalid email or password.','error')
    return render_template('login.html', captcha_code=captcha_code)


@app.route('/logout')
@login_required
def logout():
    logout_user(); return redirect(url_for('index'))


@app.route('/listings')
def listings():
    page      = request.args.get('page',1,type=int)
    search    = request.args.get('q','')
    cat_id    = request.args.get('category',type=int)
    city      = request.args.get('city','')
    min_price = request.args.get('min_price',type=float)
    max_price = request.args.get('max_price',type=float)
    condition = request.args.get('condition','')
    sort      = request.args.get('sort','newest')

    q = Listing.query.filter_by(is_active=True)
    if search:    q = q.filter(Listing.title.ilike(f'%{search}%')|Listing.description.ilike(f'%{search}%'))
    if cat_id:    q = q.filter_by(category_id=cat_id)
    if city:      q = q.filter(Listing.city.ilike(f'%{city}%'))
    if min_price is not None: q = q.filter(Listing.price >= min_price)
    if max_price is not None: q = q.filter(Listing.price <= max_price)
    if condition: q = q.filter_by(condition=condition)
    if sort == 'price_asc':   q = q.order_by(Listing.price.asc())
    elif sort == 'price_desc': q = q.order_by(Listing.price.desc())
    else:                      q = q.order_by(Listing.created_at.desc())

    paged = q.paginate(page=page,per_page=12,error_out=False)
    cats  = Category.query.all()
    return render_template('listings.html', listings=paged, categories=cats,
                           search=search, category_id=cat_id, city=city, sort=sort)


@app.route('/listing/<int:id>')
def listing_detail(id):
    l       = Listing.query.get_or_404(id)
    l.views += 1; db.session.commit()
    similar = Listing.query.filter_by(category_id=l.category_id,is_active=True).filter(Listing.id!=id).limit(4).all()
    reviews = Review.query.filter_by(seller_id=l.seller_id).order_by(Review.created_at.desc()).limit(5).all()
    is_fav  = False
    if current_user.is_authenticated:
        is_fav = Favorite.query.filter_by(user_id=current_user.id,listing_id=id).first() is not None
    return render_template('listing_detail.html', listing=l, similar=similar, reviews=reviews, is_favorited=is_fav)


@app.route('/post', methods=['GET','POST'])
@login_required
def post_listing():
    cats = Category.query.all()
    if request.method == 'POST':
        title   = request.form['title']
        desc    = request.form['description']
        price   = float(request.form['price'])
        cat_id  = int(request.form['category_id'])
        cond    = request.form.get('condition','used')
        payment = request.form.get('payment_method','cash')
        lat     = request.form.get('lat',type=float)
        lng     = request.form.get('lng',type=float)
        address = request.form.get('address','')
        city    = request.form.get('city','')
        cat     = Category.query.get(cat_id)
        score, flags, verified = ai_analyze(title, desc, price, cat.name if cat else '')
        images = []
        for f in request.files.getlist('images'):
            if f and allowed_file(f.filename):
                ext   = f.filename.rsplit('.',1)[1].lower()
                fname = f"{uuid.uuid4().hex}.{ext}"
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
                images.append(fname)
        l = Listing(title=title, description=desc, price=price,
                    category_id=cat_id, seller_id=current_user.id,
                    condition=cond, payment_method=payment,
                    lat=lat, lng=lng, address=address, city=city,
                    images=json.dumps(images), ai_score=score,
                    ai_flags=json.dumps(flags), ai_verified=verified)
        db.session.add(l); db.session.commit()
        flash('Listing posted! 🎉','success')
        return redirect(url_for('listing_detail', id=l.id))
    return render_template('post_listing.html', categories=cats)


@app.route('/map')
def map_view():
    items = Listing.query.filter_by(is_active=True).filter(Listing.lat.isnot(None)).all()
    data  = []
    for l in items:
        imgs = l.get_images()
        data.append({'id':l.id,'title':l.title,'price':l.price,
                     'lat':l.lat,'lng':l.lng,'city':l.city or '',
                     'image':imgs[0] if imgs else None,
                     'category':l.category.name if l.category else '',
                     'cat_icon':l.category.icon if l.category else '📦',
                     'seller':l.seller.username if l.seller else '',
                     'condition':l.condition or '',
                     'ai_verified':l.ai_verified,'ai_score':l.ai_score})
    return render_template('map.html', listings_json=json.dumps(data))


@app.route('/messages')
@login_required
def messages():
    all_msgs = db.session.query(Message).filter(
        (Message.sender_id==current_user.id)|(Message.receiver_id==current_user.id)
    ).order_by(Message.created_at.desc()).all()
    convos = {}
    for msg in all_msgs:
        other = msg.receiver_id if msg.sender_id==current_user.id else msg.sender_id
        key   = f"{min(current_user.id,other)}-{max(current_user.id,other)}-{msg.listing_id}"
        if key not in convos:
            convos[key] = {'msg':msg,'other_id':other,'other':User.query.get(other),
                           'listing':msg.listing,'unread':0}
        if not msg.is_read and msg.receiver_id==current_user.id:
            convos[key]['unread'] += 1
    return render_template('messages.html', conversations=list(convos.values()))


@app.route('/chat/<int:user_id>/<int:listing_id>')
@login_required
def chat(user_id, listing_id):
    other   = User.query.get_or_404(user_id)
    listing = Listing.query.get_or_404(listing_id)
    msgs    = Message.query.filter(
        ((Message.sender_id==current_user.id)&(Message.receiver_id==user_id)|
         (Message.sender_id==user_id)&(Message.receiver_id==current_user.id)),
        Message.listing_id==listing_id
    ).order_by(Message.created_at.asc()).all()
    Message.query.filter_by(sender_id=user_id,receiver_id=current_user.id,
                             listing_id=listing_id).update({'is_read':True})
    db.session.commit()
    return render_template('chat.html', other_user=other, listing=listing, messages=msgs)


@app.route('/send_message', methods=['POST'])
@login_required
def send_message():
    d   = request.get_json()
    msg = Message(sender_id=current_user.id, receiver_id=d['receiver_id'],
                  listing_id=d['listing_id'], content=d['content'])
    db.session.add(msg); db.session.commit()
    room = f"chat_{min(current_user.id,d['receiver_id'])}_{max(current_user.id,d['receiver_id'])}_{d['listing_id']}"
    socketio.emit('new_message',{
        'id':msg.id,'sender_id':current_user.id,'sender_name':current_user.username,
        'content':msg.content,'time':msg.created_at.strftime('%H:%M')
    }, room=room)
    return jsonify({'status':'ok'})


@app.route('/ai_chat', methods=['POST'])
def ai_chat():
    data = request.get_json()
    msg  = data.get('message','').lower().strip()
    lid  = data.get('listing_id')
    l    = Listing.query.get(lid) if lid else None

    kw = {
        'price':     lambda: f"This item is listed at ₹{l.price:,.0f}. You can try negotiating — message the seller with a polite offer!" if l else "Check the listing for price.",
        'cost':      lambda: f"The asking price is ₹{l.price:,.0f}." if l else "Check the listing.",
        'how much':  lambda: f"It's listed at ₹{l.price:,.0f}." if l else "Check the listing.",
        'condition': lambda: f"Listed as '{l.condition.replace('_',' ')}'. See description for full details." if l else "Check listing description.",
        'delivery':  lambda: "The seller can arrange delivery or meetup. Open 🗺️ Map to see exact distance and estimated delivery time!",
        'ship':      lambda: "Ask the seller about shipping via Chat button. Some sellers use courier services.",
        'fake':      lambda: f"AI authenticity score: {l.ai_score:.0f}/100. {'✅ Looks genuine!' if l.ai_score>=65 else '⚠️ Proceed with caution and inspect before paying.'}" if l else "Check the AI badge on the listing.",
        'real':      lambda: f"AI score for this listing: {l.ai_score:.0f}/100. Always inspect before paying!" if l else "See AI badge on listing.",
        'safe':      lambda: "🔒 Safety tips:\n1. Meet in a public place (café, mall lobby)\n2. Inspect item BEFORE paying\n3. Use in-app chat — don't share your number\n4. Never pay advance to strangers\n5. Bring a friend for high-value items",
        'scam':      lambda: "🚨 Red flags: pressure to pay first, prices too good to be true, requests to chat on WhatsApp. Use the Report button if suspicious.",
        'negotiat':  lambda: "Most sellers are open! Click 'Chat Now', be polite, and offer 10–20% below asking. Explain why (e.g., 'I can pick up today').",
        'offer':     lambda: "Tap 'Chat Now' and make your offer. A good opener: 'Hi, I'm interested. Would you take ₹X?'",
        'payment':   lambda: f"Accepted: {l.payment_method}. Always inspect item first, then pay!" if l else "Check listing for payment options.",
        'upi':       lambda: "UPI is accepted. Use GPay, PhonePe, or Paytm. Send only after inspecting!",
        'cash':      lambda: "Cash on Delivery for meetup. Bring exact change and inspect before paying.",
        'return':    lambda: "Returns depend on seller policy. Clarify before buying — ask via Chat.",
        'warranty':  lambda: "Ask the seller about any remaining warranty via Chat. Electronics may have manufacturer warranty.",
        'location':  lambda: f"Item is in {l.city}. Open 🗺️ Map to see exact spot and estimate delivery time!" if l and l.city else "Open the Map view for location.",
        'distance':  lambda: "Click 🗺️ Map in the top nav to see distance from your location with estimated travel time.",
        'map':       lambda: "Use Map view (top nav) to see all listings geographically with distance & delivery estimates.",
        'contact':   lambda: "Click the blue 'Chat Now' button to message the seller securely through Bazaar.",
        'seller':    lambda: f"Seller: {l.seller.username} | Rating: {'⭐'*int(l.seller.rating)} ({l.seller.total_ratings} reviews)." if l and l.seller else "See seller profile.",
        'rating':    lambda: f"Seller has {l.seller.rating:.1f}/5 stars from {l.seller.total_ratings} reviews." if l and l.seller else "Check seller profile.",
        'report':    lambda: "Scroll to the bottom of the listing and click 'Report this listing'. Our team reviews within 24 hours.",
        'help':      lambda: "I can help with: 💰 Price & negotiation · 📦 Condition · 🚗 Delivery · 🔒 Safety · 💳 Payment · ⭐ Seller info · 🤖 AI verification\n\nWhat do you want to know?",
    }

    for keyword, fn in kw.items():
        if keyword in msg:
            return jsonify({'reply': fn()})

    name = l.title if l else "this listing"
    return jsonify({'reply': f"Hi! I'm Bazaar AI 🤖\n\nI can help you with questions about *{name}*.\n\nTry asking about: price, condition, delivery, safety tips, payment methods, the seller's rating, or how to negotiate!"})


@app.route('/favorite/<int:listing_id>', methods=['POST'])
@login_required
def toggle_favorite(listing_id):
    fav = Favorite.query.filter_by(user_id=current_user.id,listing_id=listing_id).first()
    if fav:
        db.session.delete(fav); db.session.commit(); return jsonify({'status':'removed'})
    db.session.add(Favorite(user_id=current_user.id,listing_id=listing_id)); db.session.commit()
    return jsonify({'status':'added'})


@app.route('/favorites')
@login_required
def favorites():
    favs = Favorite.query.filter_by(user_id=current_user.id).all()
    return render_template('favorites.html', favorites=favs)


@app.route('/profile/<int:user_id>')
def profile(user_id):
    u        = User.query.get_or_404(user_id)
    listings = Listing.query.filter_by(seller_id=user_id,is_active=True).order_by(Listing.created_at.desc()).all()
    reviews  = Review.query.filter_by(seller_id=user_id).order_by(Review.created_at.desc()).all()
    return render_template('profile.html', profile_user=u, listings=listings, reviews=reviews)


@app.route('/my_listings')
@login_required
def my_listings():
    ls = Listing.query.filter_by(seller_id=current_user.id).order_by(Listing.created_at.desc()).all()
    return render_template('my_listings.html', listings=ls)


@app.route('/listing/delete/<int:id>', methods=['POST'])
@login_required
def delete_listing(id):
    l = Listing.query.get_or_404(id)
    if l.seller_id != current_user.id:
        flash('Unauthorized.','error'); return redirect(url_for('my_listings'))
    l.is_active = False; db.session.commit()
    flash('Listing removed.','success'); return redirect(url_for('my_listings'))


@app.route('/report/<int:listing_id>', methods=['POST'])
@login_required
def report_listing(listing_id):
    db.session.add(Report(reporter_id=current_user.id,listing_id=listing_id,
                          reason=request.form.get('reason'),details=request.form.get('details')))
    db.session.commit()
    flash('Report submitted. Thank you!','success')
    return redirect(url_for('listing_detail', id=listing_id))


@app.route('/review/<int:seller_id>/<int:listing_id>', methods=['POST'])
@login_required
def add_review(seller_id, listing_id):
    if Review.query.filter_by(reviewer_id=current_user.id,listing_id=listing_id).first():
        flash('Already reviewed.','error'); return redirect(url_for('listing_detail',id=listing_id))
    rating = int(request.form['rating'])
    db.session.add(Review(reviewer_id=current_user.id,seller_id=seller_id,
                          listing_id=listing_id,rating=rating,comment=request.form.get('comment','')))
    s = User.query.get(seller_id)
    s.rating = (s.rating*s.total_ratings+rating)/(s.total_ratings+1)
    s.total_ratings += 1
    db.session.commit()
    flash('Review added! ⭐','success')
    return redirect(url_for('listing_detail',id=listing_id))


# ─── APIS ──────────────────────────────────────────────────────────────────────

@app.route('/api/distance')
def api_distance():
    lat1,lng1 = request.args.get('lat1',type=float), request.args.get('lng1',type=float)
    lat2,lng2 = request.args.get('lat2',type=float), request.args.get('lng2',type=float)
    if None in [lat1,lng1,lat2,lng2]: return jsonify({'error':'Missing coords'})
    dist = haversine(lat1,lng1,lat2,lng2)
    mins = int((dist/30)*60)
    return jsonify({'distance_km':round(dist,1),'delivery_minutes':mins,
                    'delivery_text':f"{dist:.1f} km · ~{mins} min"})


@app.route('/api/ai_analyze', methods=['POST'])
def api_ai_analyze():
    d = request.get_json()
    score,flags,verified = ai_analyze(d.get('title',''),d.get('description',''),
                                       float(d.get('price',0)),d.get('category',''))
    return jsonify({'score':score,'flags':flags,'verified':verified})


@app.route('/captcha_image')
def captcha_image():
    code  = generate_captcha()
    lines = ''.join([f'<line x1="{random.randint(0,150)}" y1="{random.randint(0,50)}" '
                     f'x2="{random.randint(0,150)}" y2="{random.randint(0,50)}" '
                     f'stroke="#{random.randint(40,90):02x}{random.randint(40,90):02x}{random.randint(80,130):02x}" '
                     f'stroke-width="1.5"/>' for _ in range(8)])
    dots  = ''.join([f'<circle cx="{random.randint(5,145)}" cy="{random.randint(5,45)}" '
                     f'r="1.5" fill="#e94560" opacity="0.35"/>' for _ in range(14)])
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="160" height="52">'
           f'<rect width="160" height="52" fill="#0d0d14" rx="8"/>'
           f'{lines}{dots}'
           f'<text x="80" y="36" font-family="Courier New,monospace" font-size="22" font-weight="bold" '
           f'fill="#e94560" text-anchor="middle" letter-spacing="10">{code}</text>'
           f'</svg>')
    return svg, 200, {'Content-Type':'image/svg+xml','Cache-Control':'no-store, no-cache, must-revalidate'}


# ─── SOCKETIO ──────────────────────────────────────────────────────────────────

@socketio.on('join_chat')
def on_join(data):
    join_room(f"chat_{min(data['user1'],data['user2'])}_{max(data['user1'],data['user2'])}_{data['listing_id']}")

@socketio.on('leave_chat')
def on_leave(data):
    leave_room(f"chat_{min(data['user1'],data['user2'])}_{max(data['user1'],data['user2'])}_{data['listing_id']}")


# ─── INIT ──────────────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()
    seed_demo_data()

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
