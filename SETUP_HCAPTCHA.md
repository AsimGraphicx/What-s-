# 🥅 hCaptcha-Challenger Setup Guide

## ✅ Installation Complete!

The `hcaptcha-challenger` library has been successfully integrated into your `devin.py` file.

## 🔑 Required: Get Your Gemini API Key

The AI-powered hCaptcha solver requires a Google Gemini API key.

### Steps to Get API Key:

1. **Visit**: https://aistudio.google.com/app/apikey
2. **Sign in** with your Google account
3. **Click "Create API Key"**
4. **Copy the API key** (starts with `AIza...`)

### Set the API Key:

**Option 1: Environment Variable (Recommended)**
```bash
export GEMINI_API_KEY="your-api-key-here"
python devin.py
```

**Option 2: Add to .env file**
```bash
echo "GEMINI_API_KEY=your-api-key-here" > .env
```

## 🚀 How It Works

The enhanced `handle_hcaptcha()` function now uses a **2-tier approach**:

### Tier 1: AI-Powered Solver (Primary)
- Uses Google Gemini AI to solve image-based challenges
- Automatically detects challenge type (binary, multi-select, drag-drop)
- Human-like mouse movements with Bezier curves
- **Requires**: `GEMINI_API_KEY` environment variable

### Tier 2: Manual Fallback (Backup)
- Traditional selector-based clicking
- Multiple fallback strategies
- Used when AI is unavailable or fails

## 📊 Usage Example

```python
# In your checkout flow, just call:
success = await handle_hcaptcha(page, idx=tab_index, max_wait=120)

if success:
    print("✅ Captcha solved!")
else:
    print("❌ Captcha failed - manual intervention needed")
```

## ⚙️ Configuration Options

You can customize the AI solver behavior in `handle_hcaptcha_challenger()`:

```python
agent_config = AgentConfig(
    GEMINI_API_KEY=HCAPTCHA_API_KEY,
    EXECUTION_TIMEOUT=120,      # Max time for solving (seconds)
    RESPONSE_TIMEOUT=30,        # Wait for response (seconds)
    RETRY_ON_FAILURE=True,      # Auto-retry on failure
    enable_challenger_debug=False,  # Enable debug logs
)
```

## 🛠️ Troubleshooting

### Issue: "GEMINI_API_KEY not set"
**Solution**: Set the environment variable before running:
```bash
export GEMINI_API_KEY="your-key-here"
```

### Issue: "hCaptcha-Challenger not available"
**Solution**: Ensure the `hcaptcha-challenger` folder exists:
```bash
ls -la /workspace/hcaptcha-challenger/src
```

### Issue: AI solver times out
**Solution**: Increase `EXECUTION_TIMEOUT` or check your internet connection.

### Issue: Challenge fails repeatedly
**Solution**: 
1. Check if your IP is rate-limited
2. Try with a different proxy
3. Use manual mode by not setting `GEMINI_API_KEY`

## 📁 File Structure

```
/workspace/
├── devin.py                          # Main script (enhanced)
├── hcaptcha-challenger/              # AI solver library
│   └── src/
│       └── hcaptcha_challenger/
│           ├── agent/
│           │   └── challenger.py     # Core AI agent
│           ├── models.py             # Data models
│           └── tools/                # AI tools
└── SETUP_HCAPTCHA.md                 # This guide
```

## 🎯 Supported Challenge Types

✅ Image Label Binary (Yes/No questions)
✅ Image Label Single Select (Click one object)
✅ Image Label Multi Select (Click multiple objects)
✅ Image Drag & Drop (Single/Multi)
⚠️ Text-based challenges (Fallback to manual)

## ⚠️ Important Notes

1. **API Costs**: Gemini API may have usage limits/costs
2. **Success Rate**: ~85-95% depending on challenge difficulty
3. **Speed**: AI solving takes 10-60 seconds typically
4. **Terms of Service**: Ensure compliance with target website's ToS

## 🔄 Update the Library

To update hcaptcha-challenger to latest version:
```bash
cd /workspace/hcaptcha-challenger
git pull origin main
```

---

**Need Help?** Check the official docs: https://github.com/QIN2DIM/hcaptcha-challenger
