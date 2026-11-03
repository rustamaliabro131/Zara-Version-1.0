from playwright.sync_api import sync_playwright

def get_logged_in_browser():
    # Connects to persistent user profile so cookies/logins stay active
    p = sync_playwright().start()
    # Opens browser pointing to your default Chrome profile data directory
    browser = p.chromium.launch_persistent_context(
        user_data_dir="C:\\Users\\YourUsername\\AppData\\Local\\Google\\Chrome\\User Data",
        headless=False,  # Visible browser so you can watch Zara work
        args=["--start-maximized"]
    )
    return browser