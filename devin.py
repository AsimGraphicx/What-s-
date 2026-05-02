import asyncio
import re
import os
import random
import subprocess
import time
import sys
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

# ═══════════════════════════════════════════════════════════════
# INJECT HCAPTCHA-CHALLENGER INTO PYTHON PATH
# ═══════════════════════════════════════════════════════════════
HCAPTCHA_CHALLENGER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hcaptcha-challenger", "src")
if HCAPTCHA_CHALLENGER_PATH not in sys.path:
    sys.path.insert(0, HCAPTCHA_CHALLENGER_PATH)

# Now import hcaptcha_challenger modules
try:
    from hcaptcha_challenger import AgentV, AgentConfig, CaptchaResponse
    from hcaptcha_challenger.models import ChallengeSignal
    from hcaptcha_challenger.utils import SiteKey
    HCAPTCHA_CHALLENGER_AVAILABLE = True
    print("✅ hCaptcha-Challenger loaded successfully")
except Exception as e:
    print(f"⚠️ hCaptcha-Challenger not available: {e}")
    HCAPTCHA_CHALLENGER_AVAILABLE = False

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════
THREADS = 3
CHECKOUT_HEADLESS = False
CHECKOUT_CDP_PORT = 9222
CHECKOUTS_FILE = "checkouts.txt"
FAILED_FILE = "failed.txt"
EMAILS_FILE = "emails.txt"
CHECKOUT_BATCH_SIZE = 25
PENDING_CHECKOUTS_FILE = "pending_checkouts.txt"
IN_PROGRESS_CHECKOUTS_FILE = "in_progress_checkouts.txt"
COMPLETED_CHECKOUTS_FILE = "completed_checkouts.txt"
REVIEW_CHECKOUTS_FILE = "review_checkouts.txt"
FAILED_CHECKOUTS_FILE = "failed_checkouts.txt"

# hCaptcha Challenger Config
HCAPTCHA_API_KEY = os.environ.get("GEMINI_API_KEY", "")  # Required for AI-powered solving

# ═══════════════════════════════════════════════════════════════
# FORMATTING FUNCTIONS
# ═══════════════════════════════════════════════════════════════
def get_current_datetime():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def get_current_date_short():
    return datetime.now().strftime("%d/%m/%y")

def get_expiry_date():
    expiry = datetime.now() + timedelta(days=14)
    return expiry.strftime("%d/%m/%y")

def get_current_time():
    return datetime.now().strftime("%H:%M:%S")

def mask_email_console(email):
    if '@' in email:
        username, domain = email.split('@', 1)
        if len(username) > 4:
            masked = username[:4] + '***@' + domain
        else:
            masked = username + '***@' + domain
    else:
        masked = email
    if len(masked) > 20:
        masked = masked[:17] + "..."
    return masked.ljust(20)

def format_email_file(email):
    """Format email for file output with exactly 30 characters"""
    if len(email) > 30:
        email = email[:27] + "..."
    return email.ljust(30)

def format_error_message(error_message):
    if len(error_message) > 30:
        error_message = error_message[:27] + "..."
    return error_message.ljust(30)

def calculate_percentage(current_step, total_steps=6):
    if current_step >= total_steps:
        return 100
    return int((current_step / total_steps) * 100)

def format_time_duration(seconds):
    if seconds <= 0:
        return "0m00s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}m{secs:02d}s"

def calculate_eta(current_step, elapsed_time, total_steps=6):
    if current_step >= total_steps:
        return "ETA 0m00s"
    if current_step == 0 or elapsed_time <= 0:
        return "ETA --    "
    avg_time_per_step = elapsed_time / current_step
    remaining_steps = total_steps - current_step
    eta_seconds = remaining_steps * avg_time_per_step
    return f"ETA {format_time_duration(eta_seconds)}"

def get_step_name(step):
    steps = {
        0: "⏳ Waiting       ",
        1: "📧 Get Email     ",
        2: "🔐 Signup        ",
        3: "📥 Get OTP       ",
        4: "⌨️ Enter OTP     ",
        5: "🎯 Plans Page    ",
        6: "💳 Checkout      ",
        7: "💳 Card Details  ",
        8: "🤖 CAPTCHA       ",
        9: "💰 Payment       ",
        10: "✅ Paid         "
    }
    return steps.get(step, "❓ Unknown       ")

def format_console_line(account_num, total, status, email, current_step, percentage, eta):
    task_str = f"{account_num:03d}/{total:03d}"
    email_masked = mask_email_console(email)
    step_str = get_step_name(current_step)
    pct_str = f"{percentage:3d}%"
    eta_str = eta.ljust(10)
    return f"{task_str} | {status} | {email_masked} | {step_str} | {pct_str} | {eta_str}"

def create_file_header(title, emoji, target_count):
    datetime_str = get_current_datetime()
    return f"""═══════════════════════════════════════════════════════════════
{emoji} {title} - {datetime_str} - @TurabCoder {emoji}
📊 Target: {target_count} accounts | 🧵 Threads: {THREADS} | 🌐 Browser: Brave
═══════════════════════════════════════════════════════════════
"""

def count_existing_accounts():
    """Count existing accounts in files to continue numbering"""
    existing_count = 0
    try:
        if os.path.exists(EMAILS_FILE):
            with open(EMAILS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if "📧 " in line and "@" in line and not line.startswith("═"):
                        existing_count += 1
    except:
        pass
    return existing_count

def write_file_header(file_path, title, emoji, target_count):
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        header = create_file_header(title, emoji, target_count)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(header)

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def show_banner(total):
    clear_screen()
    print(f"""
═══════════════════════════════════════════════════════════════
🚀 DEVIN ACCOUNT GENERATOR - @TurabCoder 🚀
🎯 Target: {total} accounts | 🧵 Threads: {THREADS} | 🌐 Browser: Brave
═══════════════════════════════════════════════════════════════
""")

# ═══════════════════════════════════════════════════════════════
# ACCOUNT STATUS TRACKING
# ═══════════════════════════════════════════════════════════════
class AccountStatus:
    def __init__(self, account_num, email):
        self.account_num = account_num
        self.email = email
        self.current_step = 0
        self.status = "⏳"
        self.file_saved = False
        self.start_time = time.time()
        self.error_message = None

    def update_step(self, step):
        self.current_step = step
        if step > 0:
            self.status = "🔄"

    def get_percentage(self):
        return calculate_percentage(self.current_step)

    def get_eta(self):
        elapsed = time.time() - self.start_time
        return calculate_eta(self.current_step, elapsed)

    def mark_completed(self):
        self.current_step = 6
        self.status = "✅"
        self.file_saved = True

    def mark_failed(self, error):
        self.status = "❌"
        self.error_message = error

# ═══════════════════════════════════════════════════════════════
# GLOBAL TRACKING
# ═══════════════════════════════════════════════════════════════
accounts = {}
cards = []
file_lock = asyncio.Lock()

def read_cards():
    """Read card details from cards.txt"""
    cards_list = []
    try:
        if os.path.exists("cards.txt"):
            with open("cards.txt", "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if "|" in line:
                        parts = line.split("|")
                        if len(parts) >= 4:
                            year = parts[2].strip()
                            if len(year) == 4:
                                year = year[-2:]
                            cards_list.append({
                                "number": parts[0].strip(),
                                "expiry": f"{parts[1].strip().zfill(2)}/{year}",
                                "cvc": parts[3].strip()
                            })
                        elif len(parts) >= 3:
                            cards_list.append({
                                "number": parts[0].strip(),
                                "expiry": parts[1].strip(),
                                "cvc": parts[2].strip()
                            })
    except:
        pass
    return cards_list

async def append_paid_log(email, card_masked):
    async with file_lock:
        line = f"📧 {email.ljust(30)} | 💳 {card_masked} | $20.00 | ✅ PAID | {get_current_time()}"
        with open("paid_accounts.txt", "a", encoding="utf-8") as f:
            f.write(line + "\n")

async def append_failed_log(email, card_masked, error):
    async with file_lock:
        error_short = str(error)[:20] if len(str(error)) > 20 else str(error)
        line = f"📧 {email.ljust(30)} | 💳 {card_masked} | ❌ {error_short} | {get_current_time()}"
        with open("payment_failed.txt", "a", encoding="utf-8") as f:
            f.write(line + "\n")

async def append_email_log(email):
    async with file_lock:
        email_padded = format_email_file(email)
        line = f"📧 {email_padded} | GEN {get_current_date_short()} | EXP {get_expiry_date()} | 🎯 Trial-14D | ✅ Active"
        with open(EMAILS_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")

async def add_email_if_not_exists(email):
    """Add email to emails.txt with proper format if not already exists"""
    async with file_lock:
        email_clean = email.strip().lower()
        try:
            if os.path.exists(EMAILS_FILE):
                with open(EMAILS_FILE, "r", encoding="utf-8") as f:
                    content = f.read()
                if email_clean in content.lower():
                    return
            email_padded = format_email_file(email)
            line = f"📧 {email_padded} | GEN {get_current_date_short()} | EXP {get_expiry_date()} | 🎯 Trial-14D | ✅ Active"
            with open(EMAILS_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            print(f"  📝 Added email to emails.txt: {email}")
        except Exception as e:
            print(f"  ⚠️ Failed to add email: {e}")

async def mark_email_paid(email):
    async with file_lock:
        if not os.path.exists(EMAILS_FILE):
            await add_email_if_not_exists(email)
            return
        try:
            with open(EMAILS_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            email_clean = email.strip().lower()
            found = False
            new_lines = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    new_lines.append(line)
                    continue
                if email_clean in stripped.lower() and "✅ PAID" not in stripped:
                    new_lines.append(line.rstrip() + " | ✅ PAID\n")
                    found = True
                else:
                    new_lines.append(line)
            if found:
                with open(EMAILS_FILE, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
            else:
                await add_email_if_not_exists(email)
                await mark_email_paid(email)
        except:
            pass

def remove_checkout_from_master(url):
    """Remove completed checkout from checkouts.txt"""
    try:
        if not os.path.exists(CHECKOUTS_FILE):
            return
        with open(CHECKOUTS_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        new_lines = []
        for line in lines:
            if url not in line:
                new_lines.append(line)
        with open(CHECKOUTS_FILE, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    except:
        pass

async def append_checkout_log(email, checkout_url):
    async with file_lock:
        email_padded = format_email_file(email)
        line = f"📧 {email_padded} | 💳 {checkout_url}"
        with open(CHECKOUTS_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        with open(PENDING_CHECKOUTS_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")

def extract_checkout_url(line):
    match = re.search(r'https?://\S+', line)
    return match.group(0).strip() if match else ""

def extract_email_from_line(line):
    if '|' not in line:
        return ""
    first_part = line.split('|')[0]
    return first_part.replace('📧', '').strip()

def normalize_checkout_line(line):
    line = line.strip()
    if not line or line.startswith("═") or "STRIPE CHECKOUT LINKS" in line:
        return ""
    url = extract_checkout_url(line)
    if not url:
        return ""
    if "📧" in line:
        return line
    return f"📧 {'unknown'.ljust(30)} | 💳 {url}"

def load_checkout_lines(file_path):
    lines = []
    seen = set()
    if not os.path.exists(file_path):
        return lines
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = normalize_checkout_line(raw_line)
                url = extract_checkout_url(line)
                if line and url and url not in seen:
                    lines.append(line)
                    seen.add(url)
    except:
        pass
    return lines

def write_checkout_lines(file_path, lines):
    seen = set()
    cleaned = []
    for raw_line in lines:
        line = normalize_checkout_line(raw_line)
        url = extract_checkout_url(line)
        if line and url and url not in seen:
            cleaned.append(line)
            seen.add(url)
    with open(file_path, "w", encoding="utf-8") as f:
        for line in cleaned:
            f.write(line + "\n")

def append_checkout_status(file_path, line, status):
    checkout_line = normalize_checkout_line(line)
    if not checkout_line:
        return
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(f"{checkout_line} | {status} | 🕐 {get_current_time()}\n")

def sync_pending_checkouts_from_master():
    master_lines = load_checkout_lines(CHECKOUTS_FILE)
    pending_lines = load_checkout_lines(PENDING_CHECKOUTS_FILE)
    completed_urls = {extract_checkout_url(line) for line in load_checkout_lines(COMPLETED_CHECKOUTS_FILE)}
    failed_urls = {extract_checkout_url(line) for line in load_checkout_lines(FAILED_CHECKOUTS_FILE)}
    review_urls = {extract_checkout_url(line) for line in load_checkout_lines(REVIEW_CHECKOUTS_FILE)}
    pending_urls = {extract_checkout_url(line) for line in pending_lines}
    final_pending = pending_lines[:]
    for line in master_lines:
        url = extract_checkout_url(line)
        if url and url not in completed_urls and url not in failed_urls and url not in review_urls and url not in pending_urls:
            final_pending.append(line)
            pending_urls.add(url)
    write_checkout_lines(PENDING_CHECKOUTS_FILE, final_pending)
    return len(final_pending)

def pop_pending_checkout_batch(batch_size=CHECKOUT_BATCH_SIZE):
    pending_lines = load_checkout_lines(PENDING_CHECKOUTS_FILE)
    batch = pending_lines[:batch_size]
    remaining = pending_lines[batch_size:]
    write_checkout_lines(PENDING_CHECKOUTS_FILE, remaining)
    write_checkout_lines(IN_PROGRESS_CHECKOUTS_FILE, batch)
    return batch

BATCH_CARD = {"number": "4549240640456853", "expiry": "01/31", "cvc": "127"}
BATCH_NAME = "Turab Coder"

# ═══════════════════════════════════════════════════════════════
# hCAPTCHA HANDLER - ENHANCED WITH HCAPTCHA-CHALLENGER
# ═══════════════════════════════════════════════════════════════
async def handle_hcaptcha_challenger(page, idx=0, max_wait=120):
    """
    AI-powered hCaptcha solver using hcaptcha-challenger library.
    Uses Gemini AI to solve image-based challenges automatically.
    
    Args:
        page: Playwright page object
        idx: Tab index for logging
        max_wait: Maximum time to wait for captcha solving (seconds)
    
    Returns:
        tuple: (success: bool, used_ai: bool)
    """
    if not HCAPTCHA_CHALLENGER_AVAILABLE:
        return False, False
    
    if not HCAPTCHA_API_KEY:
        print(f"  Tab {idx:02d}: ⚠️ GEMINI_API_KEY not set, skipping AI solver")
        return False, False
    
    try:
        print(f"  Tab {idx:02d}: 🤖 Initializing AI-powered hCaptcha solver...")
        
        # Initialize AgentConfig with API key
        agent_config = AgentConfig(
            GEMINI_API_KEY=HCAPTCHA_API_KEY,
            EXECUTION_TIMEOUT=max_wait,
            RESPONSE_TIMEOUT=30,
            RETRY_ON_FAILURE=True,
            enable_challenger_debug=False,
        )
        
        # Initialize AgentV
        agent = AgentV(page=page, agent_config=agent_config)
        
        # Click the checkbox to trigger the challenge
        print(f"  Tab {idx:02d}: ⏳ Triggering hCaptcha challenge...")
        await agent.robotic_arm.click_checkbox()
        
        # Wait for challenge to complete
        print(f"  Tab {idx:02d}: 🧩 Solving hCaptcha challenge with AI...")
        result = await agent.wait_for_challenge()
        
        if result == ChallengeSignal.SUCCESS:
            print(f"  Tab {idx:02d}: ✅ hCaptcha solved by AI!")
            return True, True
        elif result == ChallengeSignal.FAILURE:
            print(f"  Tab {idx:02d}: ❌ AI failed to solve hCaptcha")
            return False, True
        elif result == ChallengeSignal.EXECUTION_TIMEOUT:
            print(f"  Tab {idx:02d}: ⏱️ AI solver timed out")
            return False, True
        else:
            print(f"  Tab {idx:02d}: ⚠️ Unknown challenge result: {result}")
            return False, True
            
    except Exception as e:
        print(f"  Tab {idx:02d}: ❌ AI solver error: {e}")
        return False, True


async def handle_hcaptcha_manual(page, idx=0, max_wait=60):
    """
    Manual hCaptcha handler with multiple fallback strategies.
    Used when AI solver is not available or fails.
    
    Args:
        page: Playwright page object
        idx: Tab index for logging
        max_wait: Maximum time to wait for captcha (seconds)
    
    Returns:
        bool: True if captcha was handled successfully
    """
    import asyncio
    
    captcha_handled = False
    
    try:
        # Bring page to front
        await page.bring_to_front()
        await asyncio.sleep(1)
        
        # Strategy 1: Look for hCaptcha in main frame first
        hcaptcha_selectors = [
            '.hcaptcha-checkbox',
            'label[title*="hCaptcha"]',
            'div.hcaptcha-holder',
            'iframe[src*="hcaptcha.com"]',
            'span:text("I am human")',
            'label:text("I am human")',
            'div:text("I am human")',
        ]
        
        for selector in hcaptcha_selectors:
            try:
                element = await page.wait_for_selector(selector, timeout=3000)
                if element:
                    await element.click()
                    print(f"  Tab {idx:02d}: ✅ hCaptcha clicked (main frame)")
                    captcha_handled = True
                    break
            except:
                continue
        
        # Strategy 2: Try iframe approach
        if not captcha_handled:
            try:
                # Wait for hCaptcha iframe
                hcaptcha_frame = await page.wait_for_selector(
                    'iframe[src*="hcaptcha.com"], iframe[title*="hCaptcha"], iframe[name*="hcaptcha"]',
                    timeout=5000
                )
                
                if hcaptcha_frame:
                    frame = await hcaptcha_frame.content_frame()
                    if frame:
                        # Multiple selectors for the checkbox
                        checkbox_selectors = [
                            'label:has-text("I am human")',
                            'div:has-text("I am human")',
                            'input[type="checkbox"]',
                            '.checkbox-wrapper label',
                            '#anchor',
                        ]
                        
                        for selector in checkbox_selectors:
                            try:
                                checkbox = await frame.wait_for_selector(selector, timeout=2000)
                                if checkbox:
                                    await checkbox.click()
                                    print(f"  Tab {idx:02d}: ✅ hCaptcha clicked (iframe)")
                                    captcha_handled = True
                                    break
                            except:
                                continue
            except Exception as e:
                print(f"  Tab {idx:02d}: ⚠️ Iframe strategy failed: {e}")
        
        # Strategy 3: Try locating by text content
        if not captcha_handled:
            try:
                # Use locator with text
                human_label = page.locator('text="I am human"').first
                if await human_label.count() > 0:
                    await human_label.click(timeout=3000)
                    print(f"  Tab {idx:02d}: ✅ hCaptcha clicked (text locator)")
                    captcha_handled = True
            except:
                pass
        
        # Strategy 4: Try challenge API detection
        if not captcha_handled:
            try:
                # Check if challenge is already solved
                await page.wait_for_function(
                    "() => document.querySelector('iframe[src*=\\'hcaptcha.com\\']') === null",
                    timeout=5000
                )
                print(f"  Tab {idx:02d}: ✅ hCaptcha already solved or disappeared")
                captcha_handled = True
            except:
                pass
                
    except Exception as e:
        print(f"  Tab {idx:02d}: ❌ hCaptcha handler error: {e}")
    
    # Wait for verification completion
    if captcha_handled:
        print(f"  Tab {idx:02d}: ⏳ Waiting for hCaptcha verification...")
        
        # Dynamic wait - check for success indicators
        for i in range(max_wait):
            try:
                # Check for success tokens or iframe disappearance
                success_indicators = [
                    await page.query_selector('textarea[name="h-captcha-response"]'),
                    await page.query_selector('iframe[src*="hcaptcha.com"][style*="display: none"]'),
                ]
                
                if any(success_indicators):
                    print(f"  Tab {idx:02d}: ✅ hCaptcha verified!")
                    break
                    
                # Check for error/retry
                retry_button = await page.query_selector('text="Retry", text="Try Again"')
                if retry_button:
                    print(f"  Tab {idx:02d}: ⚠️ Retry required")
                    break
                    
            except:
                pass
            
            await asyncio.sleep(1)
        else:
            print(f"  Tab {idx:02d}: ⚠️ hCaptcha verification timeout")
    
    return captcha_handled


async def handle_hcaptcha(page, idx=0, max_wait=120):
    """
    Smart hCaptcha handler that tries AI solver first, then falls back to manual method.
    
    Args:
        page: Playwright page object
        idx: Tab index for logging
        max_wait: Maximum time to wait for captcha (seconds)
    
    Returns:
        bool: True if captcha was handled successfully
    """
    # Try AI-powered solver first
    if HCAPTCHA_CHALLENGER_AVAILABLE and HCAPTCHA_API_KEY:
        success, used_ai = await handle_hcaptcha_challenger(page, idx, max_wait)
        if success:
            return True
    
    # Fallback to manual method
    print(f"  Tab {idx:02d}: 🔄 Falling back to manual hCaptcha handling...")
    return await handle_hcaptcha_manual(page, idx, max_wait)


# ═══════════════════════════════════════════════════════════════
# CORE FUNCTIONS (MODIFIED FOR YOUR EXACT NEED)
# ═══════════════════════════════════════════════════════════════
async def connect_or_launch_brave_cdp(p, first_url=None):
    """ONLY connects to existing Brave. NEVER launches new instance."""
    try:
        browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{CHECKOUT_CDP_PORT}", timeout=5000)
        print("✅ Connected to your existing Brave instance (CDP)")
        return browser
    except Exception as e:
        print("❌ Could not connect to existing Brave.")
        print(f"   Make sure it's running with: --remote-debugging-port={CHECKOUT_CDP_PORT}")
        return None

async def autofill_checkout_tab(page, idx, email_hint=""):
    try:
        await page.wait_for_timeout(4000)
        card_clicked = False
        try:
            card_text = page.get_by_text("Card", exact=True).first
            if await card_text.is_visible(timeout=5000):
                box = await card_text.bounding_box()
                if box:
                    await page.mouse.click(max(box["x"] - 45, 0), box["y"] + box["height"] / 2)
                else:
                    await card_text.click()
                card_clicked = True
        except:
            pass
        if not card_clicked:
            try:
                card_row = page.locator('label:has-text("Card"), [role="radio"]:has-text("Card"), button:has-text("Card"), div[role="tab"]:has-text("Card")').first
                if await card_row.is_visible(timeout=3000):
                    await card_row.click()
                    card_clicked = True
            except:
                pass
        print(f"  Tab {idx:02d}: {'✅' if card_clicked else '⚠️'} Card select")
        await page.wait_for_timeout(2000)

        card_number_filled = False
        for frame in page.frames:
            try:
                card_input = frame.locator('input[name="cardnumber"], input[name="cardNumber"], input[autocomplete="cc-number"], input[placeholder*="card number" i], input[aria-label*="card number" i]').first
                if await card_input.is_visible(timeout=1500):
                    await card_input.click()
                    await card_input.fill(BATCH_CARD["number"])
                    card_number_filled = True
                    break
            except:
                continue
        if not card_number_filled:
            try:
                card_input = page.locator('input[name="cardnumber"], input[name="cardNumber"], input[autocomplete="cc-number"], input[placeholder*="card number" i]').first
                if await card_input.is_visible(timeout=2000):
                    await card_input.click()
                    await card_input.fill(BATCH_CARD["number"])
                    card_number_filled = True
            except:
                pass
        await page.wait_for_timeout(500)

        expiry_filled = False
        for frame in page.frames:
            try:
                exp = frame.locator('input[name="exp-date"], input[name="cardExpiry"], input[autocomplete="cc-exp"], input[placeholder*="MM" i], input[aria-label*="expir" i]').first
                if await exp.is_visible(timeout=1500):
                    await exp.click()
                    await exp.fill(BATCH_CARD["expiry"])
                    expiry_filled = True
                    break
            except:
                continue
        if not expiry_filled:
            try:
                exp = page.locator('input[name="exp-date"], input[name="cardExpiry"], input[autocomplete="cc-exp"], input[placeholder*="MM" i]').first
                if await exp.is_visible(timeout=2000):
                    await exp.click()
                    await exp.fill(BATCH_CARD["expiry"])
                    expiry_filled = True
            except:
                pass
        await page.wait_for_timeout(500)

        cvc_filled = False
        for frame in page.frames:
            try:
                cvc = frame.locator('input[name="cvc"], input[name="cardCvc"], input[autocomplete="cc-csc"], input[placeholder*="CVC" i], input[placeholder*="CVV" i], input[aria-label*="CVC" i]').first
                if await cvc.is_visible(timeout=1500):
                    await cvc.click()
                    await cvc.fill(BATCH_CARD["cvc"])
                    cvc_filled = True
                    break
            except:
                continue
        if not cvc_filled:
            try:
                cvc = page.locator('input[name="cvc"], input[name="cardCvc"], input[autocomplete="cc-csc"], input[placeholder*="CVC" i], input[placeholder*="CVV" i]').first
                if await cvc.is_visible(timeout=2000):
                    await cvc.click()
                    await cvc.fill(BATCH_CARD["cvc"])
                    cvc_filled = True
            except:
                pass
        print(f"  Tab {idx:02d}: Card={'✅' if card_number_filled else '❌'} Exp={'✅' if expiry_filled else '❌'} CVC={'✅' if cvc_filled else '❌'}")

        async def fill_field(selector, value):
            try:
                fields = await page.locator(selector).all()
                for field in fields:
                    try:
                        if await field.is_visible(timeout=700):
                            await field.click()
                            await field.fill(value)
                            return True
                    except:
                        continue
            except:
                pass
            return False

        await fill_field('input[name="billingName"], input[name="nameOnCard"], input[autocomplete="cc-name"], input[placeholder*="name on card" i], input[placeholder*="cardholder" i]', BATCH_NAME)

        try:
            country_select = page.locator('select[name="billingCountry"], select[name="country"], select[autocomplete*="country"]').first
            if await country_select.is_visible(timeout=1500):
                try:
                    await country_select.select_option("PK")
                except:
                    await country_select.select_option(label="Pakistan")
        except:
            pass

        billing_address = random.choice(["123 Mall Road", "456 Gulberg Avenue", "789 DHA Phase 2", "321 Johar Town", "654 Model Town", "987 Cantt Area"])
        billing_city = random.choice(["Lahore", "Karachi", "Islamabad", "Rawalpindi", "Faisalabad"])
        billing_postal = random.choice(["54000", "75500", "44000", "46000", "38000"])

        await fill_field('input[name="billingAddressLine1"], input[name="addressLine1"], input[autocomplete*="address-line1"], input[placeholder*="address" i]', billing_address)
        await fill_field('input[name="billingLocality"], input[name="city"], input[autocomplete*="address-level2"], input[placeholder*="city" i]', billing_city)
        await fill_field('input[name="billingPostalCode"], input[name="postal"], input[name="zip"], input[autocomplete*="postal-code"], input[placeholder*="postal" i], input[placeholder*="zip" i]', billing_postal)

        # Check and click "I agree" in two places
        try:
            # First location: checkbox input
            agree_checkbox = page.locator('input[type="checkbox"]').nth(1)
            if await agree_checkbox.is_visible(timeout=3000):
                if not await agree_checkbox.is_checked():
                    await agree_checkbox.click()
                    print(f"  Tab {idx:02d}: ✅ I agree checkbox clicked (location 1)")
        except:
            pass
        
        try:
            # Second location: text "I agree"
            agree_text = page.get_by_text("I agree", exact=False).first
            if await agree_text.is_visible(timeout=2000):
                box = await agree_text.bounding_box()
                if box:
                    await page.mouse.click(max(box["x"] - 18, 0), box["y"] + box["height"] / 2)
                else:
                    await agree_text.click()
                print(f"  Tab {idx:02d}: ✅ I agree text clicked (location 2)")
        except:
            pass
        
        await page.wait_for_timeout(1000)

        for start_selector in [
            'button[type="submit"]:has-text("Start trial")',
            'button:has-text("Start trial")',
            'button:has-text("Start free trial")',
            'button[type="submit"]',
        ]:
            try:
                start_btn = page.locator(start_selector).first
                if await start_btn.is_visible(timeout=2000) and await start_btn.is_enabled():
                    await start_btn.click()
                    print(f"  Tab {idx:02d}: ✅ Start trial clicked")
                    
                    # Wait until "processing" text appears on the button (confirms click worked)
                    print(f"  Tab {idx:02d}: ⏳ Waiting for processing state...")
                    max_wait_processing = 15000  # Max 15 seconds
                    check_interval = 500
                    elapsed = 0
                    processing_detected = False
                    
                    while elapsed < max_wait_processing:
                        await page.wait_for_timeout(check_interval)
                        elapsed += check_interval
                        
                        # Check if button now shows "processing" or is disabled
                        try:
                            btn_text = await start_btn.inner_text(timeout=1000)
                            btn_disabled = await start_btn.is_disabled()
                            if "processing" in btn_text.lower() or btn_disabled:
                                processing_detected = True
                                print(f"  Tab {idx:02d}: ✅ Processing state detected")
                                break
                        except:
                            pass
                    
                    # Wait 10 seconds after processing starts
                    if processing_detected:
                        print(f"  Tab {idx:02d}: ⏳ Waiting 10 seconds after processing started...")
                        await page.wait_for_timeout(10000)
                    
                    # Click on captcha popup checkbox with humanized random delay
                    human_clicked = False
                    
                    # Random delay before clicking (human-like behavior)
                    await page.wait_for_timeout(random.randint(2000, 5000))
                    
                    # Look for captcha popup elements: close button, "I am human" text, checkbox
                    for frame in page.frames:
                        try:
                            # First try to find the checkbox inside iframe
                            for captcha_selector in ['#recaptcha-anchor', '.recaptcha-checkbox-border', '[role="checkbox"]', '#checkbox', 'input[type="checkbox"]']:
                                try:
                                    captcha_box = frame.locator(captcha_selector).first
                                    if await captcha_box.is_visible(timeout=2000):
                                        box = await captcha_box.bounding_box()
                                        if box:
                                            offset_x = random.uniform(-3, 3)
                                            offset_y = random.uniform(-3, 3)
                                            await page.mouse.move(box["x"] + box["width"] / 2 + offset_x, box["y"] + box["height"] / 2 + offset_y, steps=random.randint(5, 15))
                                            await page.wait_for_timeout(random.randint(100, 200))
                                            await page.mouse.click(box["x"] + box["width"] / 2 + offset_x, box["y"] + box["height"] / 2 + offset_y)
                                        else:
                                            await captcha_box.click(force=True)
                                        print(f"  Tab {idx:02d}: ✅ Captcha checkbox clicked in popup")
                                        human_clicked = True
                                        break
                                except:
                                    continue
                            if human_clicked:
                                break
                        except:
                            continue
                    
                    if not human_clicked:
                        # Try clicking "I am human" text in popup
                        for human_selector in [
                            'text="I am human"',
                            'text="I\'m human"',
                            'text="I am not a robot"',
                            'text="Verify you are human"',
                            '[data-testid*="human"]',
                            '.human-check',
                        ]:
                            try:
                                human_btn = page.locator(human_selector).first
                                if await human_btn.is_visible(timeout=3000):
                                    box = await human_btn.bounding_box()
                                    if box:
                                        offset_x = random.uniform(-5, 5)
                                        offset_y = random.uniform(-5, 5)
                                        await page.mouse.move(box["x"] + box["width"] / 2 + offset_x, box["y"] + box["height"] / 2 + offset_y, steps=random.randint(10, 30))
                                        await page.wait_for_timeout(random.randint(100, 300))
                                        await page.mouse.click(box["x"] + box["width"] / 2 + offset_x, box["y"] + box["height"] / 2 + offset_y)
                                    else:
                                        await human_btn.click()
                                    print(f"  Tab {idx:02d}: ✅ I am human clicked")
                                    human_clicked = True
                                    break
                            except:
                                continue
                    
                    if not human_clicked:
                        # Fallback: look for any visible checkbox in popup
                        try:
                            checkboxes = page.locator('input[type="checkbox"]')
                            count = await checkboxes.count()
                            for i in range(count):
                                try:
                                    cb = checkboxes.nth(i)
                                    if await cb.is_visible(timeout=1000):
                                        box = await cb.bounding_box()
                                        if box:
                                            offset_x = random.uniform(-2, 2)
                                            offset_y = random.uniform(-2, 2)
                                            await page.mouse.move(box["x"] + box["width"] / 2 + offset_x, box["y"] + box["height"] / 2 + offset_y, steps=random.randint(5, 10))
                                            await page.wait_for_timeout(random.randint(50, 150))
                                            await page.mouse.click(box["x"] + box["width"] / 2 + offset_x, box["y"] + box["height"] / 2 + offset_y)
                                        else:
                                            await cb.click(force=True)
                                        print(f"  Tab {idx:02d}: ✅ Fallback checkbox clicked")
                                        human_clicked = True
                                        break
                                except:
                                    continue
                        except:
                            pass
                    
                    # Wait for new window/page to open with "welcome back" or success indicators
                    print(f"  Tab {idx:02d}: ⏳ Monitoring for completion...")
                    max_wait_time = 60000  # Maximum 60 seconds
                    check_interval = 2000  # Check every 2 seconds
                    elapsed_time = 0
                    
                    while elapsed_time < max_wait_time:
                        await page.wait_for_timeout(check_interval)
                        elapsed_time += check_interval
                        
                        # Check if link changed and new page has "welcome back" or checkout done indicators
                        try:
                            current_url = page.url.lower()
                            page_text = (await page.locator("body").inner_text(timeout=3000)).lower()
                            
                            # Check for completion indicators including login page after checkout
                            completion_indicators = [
                                "welcome back", "success", "complete", "completed", "thank you", 
                                "payment successful", "subscription active", "already paid", 
                                "checkout done", "order confirmed", "log in to your account",
                                "continue with github", "continue with google", "continue with windsurf",
                                "email address", "don't have an account", "sign up"
                            ]
                            
                            # Special check: if "welcome back" AND "log in to your account" appear together, it's checkout success
                            welcome_back_present = "welcome back" in page_text
                            login_page_present = "log in to your account" in page_text
                            continue_options_present = any(opt in page_text for opt in ["continue with github", "continue with google", "continue with windsurf"])
                            
                            if (welcome_back_present and login_page_present) or \
                               (welcome_back_present and continue_options_present) or \
                               any(indicator in current_url or indicator in page_text for indicator in completion_indicators):
                                print(f"  Tab {idx:02d}: ✅ Checkout completed! Login page detected = Success!")
                                
                                # Wait 10 seconds then navigate to new URL in same window
                                print(f"  Tab {idx:02d}: ⏳ Waiting 10 seconds before navigating...")
                                await page.wait_for_timeout(10000)
                                
                                # Navigate to new URL in same window (user will handle manually)
                                # Just keep the window open for user
                                return  # Exit early as task is complete
                        except:
                            pass
                    
                    break
            except:
                continue
        print(f"  Tab {idx:02d}: ✅ Autofill done — CAPTCHA remaining")
    except Exception as e:
        print(f"  Tab {idx:02d}: ❌ Autofill error: {str(e)[:80]}")

async def process_single_checkout(browser, line, idx, total):
    """Creates a NEW WINDOW per checkout, processes it, then CLOSES ONLY THAT WINDOW."""
    url = extract_checkout_url(line)
    if not url:
        print(f"⚠️ [{idx}/{total}] No URL found, skipping")
        append_checkout_status(REVIEW_CHECKOUTS_FILE, line, "no_url")
        return "review"

    # ✅ New context = New window with SAME humanized profile
    temp_ctx = await browser.new_context()
    page = await temp_ctx.new_page()

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        print(f"✅ [{idx}/{total}] Page loaded")
    except Exception as e:
        print(f"⚠️ [{idx}/{total}] Load issue: {str(e)[:80]}")
        await temp_ctx.close()
        return "failed"

    await autofill_checkout_tab(page, idx)
    await page.wait_for_timeout(random.randint(15, 30) * 1000)

    # Use the new hCaptcha handler
    print(f"  Tab {idx:02d}: 🤖 Running hCaptcha handler...")
    captcha_clicked = await handle_hcaptcha(page, idx=idx, max_wait=60)

    if not captcha_clicked:
        # Fallback to old reCAPTCHA logic if hCaptcha handler didn't find anything
        print(f"  Tab {idx:02d}: ⚠️ hCaptcha handler returned False, trying reCAPTCHA fallback...")
        for attempt in range(1, 4):
            for frame in page.frames:
                for selector in ['#recaptcha-anchor', '.recaptcha-checkbox-border', '[role="checkbox"]', '#checkbox', 'input[type="checkbox"]']:
                    try:
                        captcha_box = frame.locator(selector).first
                        if await captcha_box.is_visible(timeout=2000):
                            box = await captcha_box.bounding_box()
                            if box:
                                await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                            else:
                                await captcha_box.click(force=True)
                            captcha_clicked = True
                            break
                    except:
                        continue
            if captcha_clicked:
                break
            await page.wait_for_timeout(5000)

        if not captcha_clicked:
            try:
                captcha_box = page.locator('iframe[src*="recaptcha"], iframe[title*="reCAPTCHA"], iframe[title*="captcha"]').first
                if await captcha_box.is_visible(timeout=2000):
                    box = await captcha_box.bounding_box()
                    if box:
                        await page.mouse.click(box["x"] + 35, box["y"] + 35)
                    else:
                        await captcha_box.click(force=True)
                    captcha_clicked = True
            except:
                pass

    await page.wait_for_timeout(random.randint(15, 30) * 1000)

    status = "review"
    try:
        text = (await page.locator("body").inner_text(timeout=5000)).lower()
        current_url = page.url.lower()
        completed_words = ["success", "complete", "completed", "thank you", "welcome back", "payment successful", "subscription active", "already paid", "already completed", "you're all done here", "all done", "this page could not be found", "page could not be found", "404"]
        failed_words = ["expired", "no longer available", "session expired", "unable to find", "no longer valid", "link has expired"]

        if any(w in current_url or w in text for w in completed_words):
            status = "completed"
            print(f"  ✅ COMPLETED!")
            append_checkout_status(COMPLETED_CHECKOUTS_FILE, line, "completed")
            email = extract_email_from_line(line)
            if email and email != "unknown":
                await add_email_if_not_exists(email)
                await mark_email_paid(email)
            if url:
                remove_checkout_from_master(url)
                print(f"  🗑️ Removed from checkouts.txt")
        elif any(w in text for w in failed_words):
            status = "failed"
            print(f"  ❌ FAILED/EXPIRED")
            append_checkout_status(FAILED_CHECKOUTS_FILE, line, "failed_or_expired")
        else:
            status = "review"
            print(f"  👀 Status unclear — marked for review")
            append_checkout_status(REVIEW_CHECKOUTS_FILE, line, "unknown")
    except:
        append_checkout_status(REVIEW_CHECKOUTS_FILE, line, "check_error")

    if status == "completed":
        print(f"  ⏳ Waiting 30s after success...")
        await page.wait_for_timeout(30000)

    # ✅ CLOSE ONLY THIS WINDOW/CONTEXT
    await temp_ctx.close()
    return status

async def process_all_checkouts_one_by_one(p, batch_lines, launch_args):
    processed_urls = set()
    browser = None

    try:
        browser = await connect_or_launch_brave_cdp(p)
        if not browser:
            write_checkout_lines(PENDING_CHECKOUTS_FILE, batch_lines + load_checkout_lines(PENDING_CHECKOUTS_FILE))
            write_checkout_lines(IN_PROGRESS_CHECKOUTS_FILE, [])
            return False
    except Exception as e:
        print(f"❌ Checkout browser launch failed: {str(e)[:120]}")
        write_checkout_lines(PENDING_CHECKOUTS_FILE, batch_lines + load_checkout_lines(PENDING_CHECKOUTS_FILE))
        write_checkout_lines(IN_PROGRESS_CHECKOUTS_FILE, [])
        return False

    total = len(batch_lines)
    completed_count = 0
    failed_count = 0
    review_count = 0

    try:
        for idx, line in enumerate(batch_lines, 1):
            if extract_checkout_url(line) in processed_urls:
                continue
            processed_urls.add(extract_checkout_url(line))

            status = await process_single_checkout(browser, line, idx, total)
            if status == "completed":
                completed_count += 1
            elif status == "failed":
                failed_count += 1
            else:
                review_count += 1

            if idx < total:
                wait_next = random.randint(25, 35)
                print(f"\n⏳ Waiting {wait_next}s before next checkout...")
                await asyncio.sleep(wait_next)
    except asyncio.CancelledError:
        remaining = [line for line in batch_lines if extract_checkout_url(line) not in processed_urls]
        write_checkout_lines(PENDING_CHECKOUTS_FILE, remaining + load_checkout_lines(PENDING_CHECKOUTS_FILE))
        write_checkout_lines(IN_PROGRESS_CHECKOUTS_FILE, [])
        raise

    print(f"\n{'═'*60}")
    print(f"📊 Batch done: ✅ {completed_count} | ❌ {failed_count} | 👀 {review_count}")
    write_checkout_lines(IN_PROGRESS_CHECKOUTS_FILE, [])

    # 🚫 NO browser.close() HERE — YOUR BRAVE STAYS ALIVE!
    return True

async def classify_checkout_status(p, line, launch_args):
    url = extract_checkout_url(line)
    if not url:
        return "review", "no_url"
    brave_paths = ["/usr/bin/brave-browser", "/usr/bin/brave", "/opt/brave.com/brave/brave-browser", "/snap/bin/brave"]
    brave_path = None
    for bp in brave_paths:
        if os.path.exists(bp):
            brave_path = bp
            break
    if brave_path:
        browser = await p.chromium.launch(headless=True, executable_path=brave_path, args=launch_args)
    else:
        browser = await p.chromium.launch(headless=True, args=launch_args)
    context = await browser.new_context()
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(3000)
        current_url = page.url.lower()
        text = ""
        try:
            text = (await page.locator("body").inner_text(timeout=5000)).lower()
        except:
            text = (await page.content()).lower()
        completed_words = ["success", "complete", "completed", "thank you", "welcome back", "payment successful", "subscription active", "already paid", "already completed", "you're all done here", "all done", "this page could not be found", "page could not be found", "404"]
        failed_words = ["expired", "no longer available", "session expired", "unable to find", "no longer valid", "link has expired"]
        pending_words = ["card", "payment method", "start trial", "pay", "captcha"]
        if any(word in current_url or word in text for word in completed_words):
            return "completed", "completed_detected"
        if any(word in text for word in failed_words):
            return "failed", "failed_or_expired"
        if any(word in text for word in pending_words):
            return "pending", "still_checkout"
        return "review", "unknown"
    except Exception as e:
        return "review", str(e)[:60]
    finally:
        try:
            await browser.close()
        except:
            pass

async def check_and_mark_batch(p, batch_lines, launch_args):
    print(f"\n🔎 Checking {len(batch_lines)} checkout links after window close")
    for idx, line in enumerate(batch_lines, 1):
        status, reason = await classify_checkout_status(p, line, launch_args)
        if status == "completed":
            append_checkout_status(COMPLETED_CHECKOUTS_FILE, line, reason)
            print(f"✅ [{idx}/{len(batch_lines)}] COMPLETED")
        elif status == "failed":
            append_checkout_status(FAILED_CHECKOUTS_FILE, line, reason)
            print(f"❌ [{idx}/{len(batch_lines)}] FAILED/EXPIRED")
        elif status == "pending":
            append_checkout_status(PENDING_CHECKOUTS_FILE, line, reason)
            print(f"⏳ [{idx}/{len(batch_lines)}] STILL PENDING")
        else:
            append_checkout_status(REVIEW_CHECKOUTS_FILE, line, reason)
            print(f"👀 [{idx}/{len(batch_lines)}] REVIEW: {reason}")
    write_checkout_lines(IN_PROGRESS_CHECKOUTS_FILE, [])

def update_console_display(total):
    show_banner(total)
    active_accounts = list(accounts.values())[:10]
    for account in active_accounts:
        line = format_console_line(
            account.account_num, total, account.status, account.email,
            account.current_step, account.get_percentage(), account.get_eta()
        )
        print(line)
    for i in range(len(active_accounts), 10):
        print("")

# ═══════════════════════════════════════════════════════════════
# MAIN ACCOUNT CREATION FUNCTION
# ═══════════════════════════════════════════════════════════════
async def run_account(browser, task_id, sem):
    async with sem:
        email_address = "unknown"
        ctx = None
        account = AccountStatus(task_id, "Waiting...")
        accounts[task_id] = account
        try:
            await asyncio.sleep(((task_id - 1) % THREADS) * 0.8 + random.uniform(0.5, 1.5))
            ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
            email_page = await ctx.new_page()
            account.update_step(1)
            account.email = "Getting email..."
            await email_page.goto("https://generator.email", wait_until="domcontentloaded", timeout=60000)
            await email_page.wait_for_timeout(random.randint(2000, 4000))
            email_el = await email_page.wait_for_selector("#email_ch_text", timeout=15000)
            email_address = (await email_el.inner_text()).strip()
            username = email_address.split("@")[0]
            account.email = email_address
            account.update_step(2)
            signup_page = await ctx.new_page()
            for retry in range(3):
                try:
                    await signup_page.goto("https://app.devin.ai/signup", wait_until="domcontentloaded", timeout=60000)
                    break
                except Exception as nav_err:
                    if retry == 2:
                        raise nav_err
                    await asyncio.sleep(random.randint(3, 6))
            await signup_page.wait_for_timeout(random.randint(2000, 3000))
            email_input = await signup_page.wait_for_selector('input[type="email"], input[name="email"], input[placeholder*="email" i]', timeout=15000)
            await email_input.fill(email_address)
            await asyncio.sleep(random.uniform(0.5, 1.5))
            try:
                btn = await signup_page.wait_for_selector('button:has-text("Sign up with email"), button[type="submit"]', timeout=8000)
                await btn.click()
            except:
                await email_input.press("Enter")
            await signup_page.wait_for_timeout(random.randint(2000, 3000))
            account.update_step(3)
            inbox_url = f"https://generator.email/{email_address}"
            otp_code = None
            for attempt in range(15):
                await email_page.goto(inbox_url, wait_until="domcontentloaded", timeout=60000)
                await email_page.wait_for_timeout(random.randint(2000, 3500))
                content = await email_page.content()
                text = await email_page.evaluate('() => document.body.innerText')
                if "devin" in content.lower() or "verification" in text.lower():
                    for pat in [r'verification code.*?\n\s*(\d{6})', r'original window.*?\n\s*(\d{6})', r'(\d{6})\s*\n.*expires', r'\b(\d{6})\b']:
                        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
                        if m:
                            otp_code = m.group(1)
                            break
                    if otp_code:
                        break
                await asyncio.sleep(random.randint(2, 4))
            if not otp_code:
                raise Exception("OTP not found after 15 attempts")
            account.update_step(4)
            await signup_page.bring_to_front()
            otp_filled = False
            try:
                digits = signup_page.locator('input[inputmode="numeric"], input[type="text"][maxlength="1"]')
                cnt = await digits.count()
                if cnt >= 6:
                    for i in range(6):
                        await digits.nth(i).fill(otp_code[i])
                        await signup_page.wait_for_timeout(random.randint(100, 300))
                    otp_filled = True
            except:
                pass
            if not otp_filled:
                for sel in ['input[autocomplete="one-time-code"]', 'input[name="code"]', 'input[placeholder*="code" i]', 'input[type="text"][maxlength="6"]']:
                    try:
                        await signup_page.fill(sel, otp_code, timeout=2000)
                        otp_filled = True
                        break
                    except:
                        continue
            if not otp_filled:
                try:
                    await signup_page.locator('input').first.click()
                    await signup_page.keyboard.type(otp_code, delay=random.randint(80, 150))
                    otp_filled = True
                except:
                    pass
            if not otp_filled:
                raise Exception("OTP entry failed")
            await signup_page.wait_for_timeout(random.randint(3000, 5000))
            try:
                vbtn = signup_page.locator('button:has-text("Verify"), button:has-text("Continue"), button[type="submit"]').first
                if await vbtn.is_visible(timeout=2000):
                    await vbtn.click(force=True)
            except:
                pass
            await signup_page.wait_for_timeout(random.randint(2000, 3000))
            await append_email_log(email_address)
            account.update_step(5)
            plans_url = f"https://app.devin.ai/org/{username}/plans"
            await signup_page.goto(plans_url, wait_until="domcontentloaded", timeout=60000)
            await signup_page.wait_for_timeout(random.randint(3000, 5000))
            try:
                pro_btn = await signup_page.wait_for_selector('button:has-text("Pro"), button:has-text("Start free trial"), button:has-text("Start trial"), a:has-text("Pro")', timeout=10000)
                await pro_btn.click()
            except:
                pass
            account.update_step(6)
            try:
                await signup_page.wait_for_timeout(random.randint(4000, 7000))
                await signup_page.wait_for_load_state("networkidle", timeout=15000)
            except:
                pass
            try:
                card_tab = signup_page.locator('button:has-text("Card"), [data-testid*="CARD"], div[role="tab"]:has-text("Card"), label:has-text("Card")').first
                if await card_tab.is_visible(timeout=5000):
                    await card_tab.click()
                    await signup_page.wait_for_timeout(random.randint(1500, 2500))
            except:
                pass
            checkout_url = signup_page.url
            if "checkout.stripe.com" not in checkout_url and "pay" not in checkout_url.lower():
                try:
                    await signup_page.wait_for_timeout(random.randint(2000, 4000))
                    checkout_url = signup_page.url
                except:
                    pass
            await append_checkout_log(email_address, checkout_url)
            print(f"✅ Checkout queued for manual batch: {email_address} | {checkout_url}")
            account.mark_completed()
            try:
                await email_page.evaluate("Delete_all_Message()")
            except:
                pass
        except Exception as e:
            account.mark_failed(str(e))
            try:
                await append_failed_log(email_address, "N/A", str(e))
            except:
                pass
        finally:
            if ctx:
                try:
                    await ctx.close()
                except:
                    pass

# ═══════════════════════════════════════════════════════════════
# MAIN FUNCTION
# ═══════════════════════════════════════════════════════════════
async def main():
    existing_accounts = count_existing_accounts()
    print("🚀 DEVIN ACCOUNT GENERATOR - @TurabCoder 🚀")
    if existing_accounts > 0:
        print(f"📊 Found {existing_accounts} existing accounts")
    pending_count = sync_pending_checkouts_from_master()
    print(f"🧾 Pending checkout links ready: {pending_count}")
    print("💡 How many NEW accounts do you want to create in background? (0 = pending only)")
    try:
        import sys
        if len(sys.argv) > 1:
            new_accounts = int(sys.argv[1])
        elif sys.stdin.isatty():
            new_accounts = int(input("💡 Enter number (default 100): ") or "100")
        else:
            new_accounts = 100
        if new_accounts < 0:
            new_accounts = 0
    except (ValueError, EOFError):
        new_accounts = 100
    total_target = existing_accounts + new_accounts
    print(f"🎯 Will create accounts {existing_accounts + 1} to {total_target}" if new_accounts > 0 else "🎯 Pending checkout processing only")
    write_file_header(EMAILS_FILE, "DEVIN EMAILS", "📧", total_target)
    write_file_header(CHECKOUTS_FILE, "STRIPE CHECKOUT LINKS", "💳", total_target)
    write_file_header(FAILED_FILE, "FAILED ACCOUNTS", "❌", total_target)
    sem = asyncio.Semaphore(THREADS)
    launch_args = ["--no-first-run", "--no-default-browser-check", "--disable-dev-shm-usage", "--disable-extensions", "--disable-background-networking"]
    async with async_playwright() as p:
        creator_browser = None
        async def launch_creator_browser():
            brave_paths = ["/usr/bin/brave-browser", "/usr/bin/brave", "/opt/brave.com/brave/brave-browser", "/snap/bin/brave"]
            for path in brave_paths:
                if os.path.exists(path):
                    try:
                        return await p.chromium.launch(headless=True, executable_path=path, args=launch_args)
                    except:
                        break
            return await p.chromium.launch(headless=True, args=launch_args)
        async def create_accounts_background():
            if new_accounts <= 0:
                return
            tasks = [run_account(creator_browser, existing_accounts + i + 1, sem) for i in range(new_accounts)]
            await asyncio.gather(*tasks, return_exceptions=True)
        if new_accounts > 0:
            creator_browser = await launch_creator_browser()
            creator_task = asyncio.create_task(create_accounts_background())
            print(f"🏭 Background account creation started: {new_accounts} accounts")
        else:
            creator_task = None
        while True:
            sync_pending_checkouts_from_master()
            pending_lines = load_checkout_lines(PENDING_CHECKOUTS_FILE)
            if pending_lines:
                batch = pop_pending_checkout_batch(CHECKOUT_BATCH_SIZE)
                result = await process_all_checkouts_one_by_one(p, batch, launch_args)
                if not result:
                    print("🛑 Checkout processing failed. Pending links restored. Stopping checkout loop.")
                    break
                continue
            if creator_task and not creator_task.done():
                print("⏳ Waiting for new checkout links from background account creator...")
                await asyncio.sleep(5)
                continue
            break
        if creator_task:
            await creator_task
        try:
            if creator_browser:
                await creator_browser.close()
        except:
            pass
    completed = len([a for a in accounts.values() if a.status == "✅"])
    failed = len([a for a in accounts.values() if a.status == "❌"])
    completed_checkouts = len(load_checkout_lines(COMPLETED_CHECKOUTS_FILE))
    pending_checkouts = len(load_checkout_lines(PENDING_CHECKOUTS_FILE))
    review_checkouts = len(load_checkout_lines(REVIEW_CHECKOUTS_FILE))
    print(f"""
✅ Checkout links : {completed}
❌ Failed         : {failed}
✅ Completed checkouts : {completed_checkouts}
⏳ Pending checkouts   : {pending_checkouts}
👀 Review checkouts    : {review_checkouts}
📁 Files: {EMAILS_FILE}, {CHECKOUTS_FILE}, {PENDING_CHECKOUTS_FILE}, {COMPLETED_CHECKOUTS_FILE}, {REVIEW_CHECKOUTS_FILE}, {FAILED_CHECKOUTS_FILE}
""")

if __name__ == "__main__":
    asyncio.run(main())
