import streamlit as st
import time
import re
import urllib.parse
from playwright.sync_api import sync_playwright
import os

# --- NEW: Playwright Installation Setup ---
@st.cache_resource
def install_playwright():
    os.system("playwright install chromium")

install_playwright()
# ----------------------------------------

BASE_URL = "https://www.geekorium.shop"

# Page Configuration
st.set_page_config(
    page_title="Geekorium Deck Checker",
    page_icon="🃏",
    layout="wide"
)

# ... [The rest of your script remains exactly the same] ...


# ---------------- HELPER FUNCTIONS ----------------

def clean_card_lines(raw_lines):
    ignored_keywords = [
        "añadir al carrito", "mercado", "añadir",
        "cart", "add to cart", "comprar"
    ]
    cleaned = []
    for line in raw_lines:
        line_clean = line.strip()
        if not any(kw in line_clean.lower() for kw in ignored_keywords):
            if line_clean:
                cleaned.append(line_clean)
    return cleaned


def parse_price(price_str):
    match = re.search(r'\$?(\d+(?:\.\d{1,2})?)', price_str)
    if match:
        return float(match.group(1))
    return 999999.0


def process_card_search(page, target_card):
    encoded = urllib.parse.quote(target_card)
    search_url = f"{BASE_URL}/?q={encoded}"

    page.goto(search_url)
    page.wait_for_timeout(2000)

    cards_raw = page.evaluate('''() => {
        const items = [];
        const nodes = Array.from(document.querySelectorAll('*')).filter(el => 
            el.innerText && el.innerText.includes('DISP:') && el.children.length === 0
        );

        nodes.forEach(dispNode => {
            let container = dispNode.closest('div');
            for (let i = 0; i < 4; i++) {
                if (container && container.parentElement && container.innerText.includes('$')) {
                    break;
                }
                if (container && container.parentElement) {
                    container = container.parentElement;
                }
            }
            if (container) {
                items.push(container.innerText);
            }
        });
        return Array.from(new Set(items));
    }''')

    valid_entries = []

    for raw in cards_raw:
        lines = [l.strip() for l in raw.split('\n') if l.strip()]
        cleaned = clean_card_lines(lines)

        exact_found = False
        card_price = 0.0
        disp_text = "N/A"
        set_code = "N/A"

        for line in cleaned:
            if line.strip().lower() == target_card.strip().lower():
                exact_found = True
            if '$' in line:
                card_price = parse_price(line)
            if "DISP:" in line:
                disp_text = line
            elif len(line) <= 4 and line.isalnum() and not line.startswith("$"):
                set_code = line

        if exact_found:
            valid_entries.append({
                "Card": target_card,
                "Price ($)": card_price,
                "Set": set_code,
                "Stock": disp_text,
                "Details": " | ".join(cleaned)
            })

    # Sort results by price ascending
    valid_entries.sort(key=lambda x: x["Price ($)"])
    return valid_entries


# ---------------- STREAMLIT USER INTERFACE ----------------

st.title("🃏 Geekorium MTG Singles Checker")
st.markdown("Paste your list of cards below (one per line) to check availability and calculate the lowest price total.")

# Sidebar Controls
with st.sidebar:
    st.header("Settings")
    headless_mode = st.checkbox("Run Browser Headless", value=True)
    st.info("Tip: Headless runs faster in the background.")

# Card input text box
default_list = "Sol Ring\nAnger\nLightning Bolt"
user_input = st.text_area("Input Card List:", value=default_list, height=180)

if st.button("🚀 Check Availability", type="primary"):
    # Parse card names from input
    cards = [c.strip() for c in user_input.split('\n') if c.strip()]

    if not cards:
        st.warning("Please enter at least one card name.")
    else:
        st.write(f"Checking **{len(cards)}** card(s)...")

        progress_bar = st.progress(0)
        status_text = st.empty()

        results_by_card = {}
        grand_total = 0.0
        found_count = 0

        # Launch Playwright session
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless_mode)
            context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
            page = context.new_page()

            for idx, card in enumerate(cards):
                status_text.text(f"Searching: {card}...")
                matches = process_card_search(page, card)

                results_by_card[card] = matches
                if matches:
                    found_count += 1
                    grand_total += matches[0]["Price ($)"]  # Add cheapest printing

                # Update progress bar
                progress_bar.progress((idx + 1) / len(cards))

            browser.close()

        status_text.text("Processing complete!")
        time.sleep(0.5)
        status_text.empty()
        progress_bar.empty()

        # Display Metrics
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Cards Searched", len(cards))
        col2.metric("Cards In-Stock", f"{found_count} / {len(cards)}")
        col3.metric("Minimum Grand Total", f"${grand_total:.2f}")

        st.divider()

        # Display Detailed Breakdown
        for card in cards:
            st.subheader(f"🃏 {card}")
            matches = results_by_card.get(card, [])

            if matches:
                # Format into clean Streamlit table
                st.dataframe(
                    matches,
                    column_order=["Set", "Price ($)", "Stock", "Details"],
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.error("❌ Exact name not found or out of stock.")
