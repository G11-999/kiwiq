# Scrapeless Browser Profile Configuration
DEFAULT_CONCURRENT_PROFILES = 236
DEFAULT_ENTITY_PREFIX = "quickIQ"

# Browser Pool Configuration
MAX_CONCURRENT_SCRAPELESS_BROWSERS = 400
ACQUISITION_TIMEOUT = 300
BROWSER_TTL = 900

OPENAI_SELECTORS = {
    "base_url": "https://chatgpt.com/",
    "search_web_no_login":'button:has-text("Search")',
    "login_button": '[data-testid="login-button"]',
    "email_input": 'input[placeholder="Email address"]',
    "password_input": 'input[placeholder="Password"]',
    "code_input": 'input[placeholder="Code"]',
    "continue_button": 'button:has-text("Continue")',
    "close_popup": 'button[data-testid="close-button"]',
    "prompt_input": 'textarea[name="prompt-textarea"]', # '[data-placeholder="Ask anything"]',
    "send_button": 'button[data-testid="send-button"]',
    "response_container": "div.markdown.prose",

    "stay_logged_out":'a:has-text("Stay logged out")',
    "retry_button":'button:has-text("Retry")',
   
   "model_switcher_button":'#system-hint-button',
   
   "think_longer":'div[role="menuitemradio"] >> nth=0',
   "deep_research":'div[role="menuitemradio"] >> nth=1',
   "create_image":'div[role="menuitemradio"] >> nth=2',
   "search_web":'div[role="menuitemradio"] >> nth=3',
   "write_code":'div[role="menuitemradio"] >> nth=4',
   "link_blacklist": set([
       'chatgpt.com', 'openai.com/policies/cookie-policy'
   ]),
}


PERPLEXITY_SELECTORS = {
    "base_url": "https://www.perplexity.ai/",
    "email_input": 'input[name="email"]',
    "continue_button": 'button:has-text("Continue with email")',
    "close_popup": 'button:has-text("Close")',
    "close_popup_floater": 'button[data-testid="floating-signup-close-button"]',
    "verification_code_input": 'input[placeholder="Enter Code"]',
    "prompt_input":"#ask-input",
    "new_thread":"svg.tabler-icon-plus",
    "model_switcher_button"  : "svg.tabler-icon-cpu",

    "copy_button": 'button[aria-label="Copy"]',
    "answer_marker": 'div:has-text("Answer")',  #  'div.prose',
    "answer_container": 'div.prose',

    "model_sonar"            : 'div[class="group/item md:h-full"] >> nth=1',
    "model_claude_4.0_sonnet"    :'div[class="group/item md:h-full"] >> nth=2',
    "model_gpt_4.1"           : 'div[class="group/item md:h-full"] >> nth=3',
    "model_gemini_2.5"        : 'div[class="group/item md:h-full"] >> nth=4',
    "model_r1_1776"          : 'div[class="group/item md:h-full"] >> nth=5',
    "model_o3"               : 'div[class="group/item md:h-full"] >> nth=6',
    "model_claude_40_think"  : 'div[class="group/item md:h-full"] >> nth=7',
    
    "labs":'div[data-testid="search-mode-studio"]',
    "research" : 'div[data-testid="search-mode-research"]',
    "search":'div[data-testid="search-mode-search"]'
}


AIMODE_SELECTORS = {
    "base_url": "https://www.google.com/",
    "ai_mode_search_button": 'button:has-text("AI Mode")',
    "ai_mode_turn_selector": 'div[data-scope-id="turn"]',
    "ai_mode_response_container": 'div[data-container-id="main-col"]',
    "ai_mode_follow_up": 'textarea[placeholder="Ask anything"]',
    
    # BeautifulSoup-specific selectors
    "bs_ai_mode_turn_selector": {"tag": "div", "attrs": {"data-scope-id": "turn"}},
    "bs_ai_mode_response_container": {"tag": "div", "attrs": {"data-container-id": "main-col"}},

    "signin_button": "text=Sign in",
    "email_input": "input#identifierId",
    "password_input": "input[name=Passwd]",

    "enter_button": "Enter",
    "search_bar": 'textarea[name="q"]',
    "ai_mode_button": "text=AI Mode",
    "new_thread" :'button[aria-label="Start new thread"]',
    "link_blacklist": set([
        "support.google.com", "policies.google.com", 
        "www.google.com/search", "accounts.google.com",
        "www.google.com/intl/", 
        "www.google.co.in/intl/", "www.google.com/webhp",
        "maps.google.com", "www.google.com/travel",
        "www.google.com/finance", "myactivity.google.com",
    ]),
}

SCRAPELESS_DASHBOARD_AUTOMATION = {
    "create_profile": "button:has-text('Create Profile')",
    "form_input": "input[name='name']",
    "save_profile": "button:has-text('Save')",
    "success_toast": "div:has-text('Profile created successfully')",
    "profile_list_profile_selector": "td:has-text('{profile_name}')",
    "profile_copy_selector": ".cursor-copy",
}
