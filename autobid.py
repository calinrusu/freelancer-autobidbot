import json
import os
import re
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

LOGIN_URL = "https://www.freelancer.com/login"
DASHBOARD_URL = "https://www.freelancer.com/dashboard"
SEARCH_URL = (
    "https://www.freelancer.com/search/projects?"
    "projectSkills=3,95,305,323,343,602,901&projectLanguages=en&projectSort=latest&types=fixed&projectFixedPriceMin=100"
)
COOKIE_FILE = Path(__file__).with_name("freelancer_cookies.json")
BID_AMOUNT = os.getenv("FREELANCER_BID_AMOUNT", "250") or "250"
MAX_PROJECTS = int(os.getenv("FREELANCER_MAX_PROJECTS", "20")) or 20
MIN_BID_THRESHOLD = 100
PROPOSAL_TEXT = (
    "I am a full stack developer with more than 10 years of experience in building custom websites and apps and various automation tasks (ecommerce stocks updates and imports, web scrapers to extract data and various cronjobs). "
    "My tech stack includes php and mysql for the back ends and html with vanilla javascript and css for the front end. "
    "I am always available for long term collaboration with the right employer and I am also expert in setting up hosting solutions on Linux servers, deploying apps and websites and maintaining security. "
    "Portfolio: ..................... "
    "Please message me to discuss details and estimate timeline based on your exact requirements. "
)


def create_driver() -> webdriver.Chrome:
	def build_options(use_profile: bool):
		options = webdriver.ChromeOptions()
		options.add_argument("--start-maximized")
		if use_profile:
			user_data_dir = os.getenv("CHROME_USER_DATA_DIR") or "/home/calin/.config/google-chrome"
			profile_dir = os.getenv("CHROME_PROFILE_DIR") or "Default"
			options.add_argument(f"--user-data-dir={user_data_dir}")
			options.add_argument(f"--profile-directory={profile_dir}")
		return options

	for use_profile in [True, False]:
		options = build_options(use_profile)
		try:
			return webdriver.Chrome(options=options)
		except Exception:
			if use_profile:
				print("Profile-based Chrome startup failed; retrying with a fresh browser profile.")
				continue
			raise

	raise RuntimeError("Unable to start Chrome for Freelancer automation.")


def save_cookies(driver: webdriver.Chrome, path: Path) -> None:
	with path.open("w", encoding="utf-8") as fp:
		json.dump(driver.get_cookies(), fp, indent=2)


def load_cookies(driver: webdriver.Chrome, path: Path) -> bool:
	if not path.exists():
		return False

	with path.open("r", encoding="utf-8") as fp:
		cookies = json.load(fp)

	for cookie in cookies:
		# Selenium expects integer expiry when present.
		if "expiry" in cookie:
			cookie["expiry"] = int(cookie["expiry"])
		try:
			driver.add_cookie(cookie)
		except Exception:
			# Ignore stale/invalid cookies and continue loading others.
			continue
	return True


def is_logged_in(driver: webdriver.Chrome, wait: WebDriverWait) -> bool:
	try:
		wait.until(lambda d: d.current_url.startswith("https://www.freelancer.com"))
	except Exception:
		return False

	current_url = driver.current_url.lower()
	if any(token in current_url for token in ["/login", "/signup", "/register", "/password-reset"]):
		return False

	page_text = driver.page_source.lower()
	if "logout" in page_text or "log out" in page_text:
		return True
	if "dashboard" in current_url:
		return True
	if "log in" in page_text or "sign up" in page_text:
		return False
	return False


def do_login(driver: webdriver.Chrome, wait: WebDriverWait, username: str, password: str) -> bool:
	driver.get(LOGIN_URL)

	email_input = wait.until(
		EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder='Email or Username']"))
	)
	password_input = wait.until(
		EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder='Password']"))
	)
	login_button = wait.until(
		EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Log in']"))
	)

	email_input.clear()
	email_input.send_keys(username)
	password_input.clear()
	password_input.send_keys(password)
	login_button.click()

	# Allow manual completion for CAPTCHA/2FA if needed.
	for _ in range(120):
		if is_logged_in(driver, wait):
			return True
		time.sleep(1)
	return False


def click_visible(driver, selectors):
	for by, value in selectors:
		try:
			elements = driver.find_elements(by, value)
		except Exception:
			elements = []
		for element in elements:
			try:
				text = (element.text or element.get_attribute("innerText") or "").lower()
				label = (element.get_attribute("aria-label") or "").lower()
				combined = f"{text} {label}"
			except Exception:
				combined = ""
			if "bid" not in combined:
				continue
			try:
				element.click()
				return True
			except Exception:
				pass
			try:
				driver.execute_script("arguments[0].click();", element)
				return True
			except Exception:
				continue

	try:
		clicked = driver.execute_script(
			"""
			const nodes = Array.from(document.querySelectorAll('button, a, input, [role="button"], div, span'));
			for (const el of nodes) {
			  const text = (el.innerText || el.textContent || '').toLowerCase();
			  const label = (el.getAttribute('aria-label') || '').toLowerCase();
			  const value = `${text} ${label}`;
			  if (value.includes('bid')) {
			    el.click();
			    return true;
			  }
			}
			return false;
			"""
		)
		if clicked:
			return True
	except Exception:
		pass
	return False


def is_project_url(href: str) -> bool:
	if not href:
		return False
	lower = href.lower()
	if any(token in lower for token in ["/proposals", "/bids", "/messages", "/reviews", "/contracts", "/offers"]):
		return False
	if "/projects/" not in lower and "/job-search/projects/" not in lower:
		return False
	parsed = href.split("#", 1)[0].split("?", 1)[0]
	if parsed.startswith("/"):
		parsed = "https://www.freelancer.com" + parsed
	path = "/" + parsed.split("//", 1)[-1].split("/", 3)[-1]
	if path.startswith("/projects/") and path.count("/") > 2:
		return False
	return True


def get_project_links(driver: webdriver.Chrome):
	links = []
	seen = set()

	for anchor in driver.find_elements(By.CSS_SELECTOR, "a[href]"):
		href = (anchor.get_attribute("href") or "").strip()
		if not href:
			continue
		if not is_project_url(href):
			continue
		if href.startswith("/"):
			href = "https://www.freelancer.com" + href
		href = href.split("#", 1)[0]
		href = href.split("?", 1)[0]
		if href and href not in seen:
			seen.add(href)
			links.append(href)

	if links:
		return links

	pattern = r"https?://www\.freelancer\.com/projects/[^\s\"'<>]+|/projects/[^\s\"'<>]+"
	for match in re.finditer(pattern, driver.page_source):
		href = match.group(0)
		if href.startswith("/"):
			href = "https://www.freelancer.com" + href
		if not is_project_url(href):
			continue
		href = href.split("#", 1)[0]
		href = href.split("?", 1)[0]
		if href and href not in seen:
			seen.add(href)
			links.append(href)
	return links


def extract_budget_numbers(text: str):
	values = []
	for match in re.finditer(
		r"(?i)(?:\$|usd|eur|gbp|£|€)\s*(\d[\d,]*(?:\.\d+)?)|\b(\d[\d,]*(?:\.\d+)?)\b",
		text,
	):
		value = (match.group(1) or match.group(2) or "").replace(",", "")
		if value:
			values.append(float(value))
	return values


def get_project_midpoint(driver: webdriver.Chrome) -> float | None:
	page_text = driver.page_source
	budget_range_match = re.search(
		r"(?is)(?:budget|range|estimated|project\s+budget|budget\s*(?:range)?)\D{0,80}(\d[\d,]*(?:\.\d+)?)\D{0,30}(?:-|to|–|through|until|and)\D{0,30}(\d[\d,]*(?:\.\d+)?)",
		page_text,
	)
	if budget_range_match:
		min_value = float(budget_range_match.group(1).replace(",", ""))
		max_value = float(budget_range_match.group(2).replace(",", ""))
		return (min_value + max_value) / 2.0

	max_budget_match = re.search(
		r"(?is)(?:budget|range|amount|up\s+to|maximum|max)\D{0,80}(?:\$|usd|eur|gbp|£|€)?\s*(\d[\d,]*(?:\.\d+)?)",
		page_text,
	)
	if max_budget_match:
		return float(max_budget_match.group(1).replace(",", ""))

	all_values = extract_budget_numbers(page_text)
	if all_values:
		return float(max(all_values))

	return None


def get_bid_amount(driver: webdriver.Chrome) -> str:
	midpoint = get_project_midpoint(driver)
	if midpoint is not None:
		return str(int(round(midpoint)))
	return BID_AMOUNT


def wait_for_bid_form(driver: webdriver.Chrome, wait: WebDriverWait):
	for _ in range(40):
		try:
			elements = driver.find_elements(By.XPATH, "//input[@type='number' or @role='spinbutton' or contains(@aria-label, 'amount') or contains(@name, 'amount') or contains(@id, 'amount') or contains(@placeholder, 'amount')]")
			if elements:
				for element in elements:
					if element.is_displayed():
						return True
			elements = driver.find_elements(By.XPATH, "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'bid') or contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'place your bid') or contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'bid on the project')]")
			if elements:
				for element in elements:
					if element.is_displayed():
						return True
		except Exception:
			pass
		time.sleep(0.5)
	return False


def fill_bid_form(driver: webdriver.Chrome, wait: WebDriverWait, amount: str):
	wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
	amount_input = None
	textarea = None

	selectors = [
		(By.XPATH, "//input[@type='number' or @role='spinbutton' or @aria-label='Bid amount' or contains(@aria-label, 'Bid amount') or contains(@aria-label, 'amount') or contains(@name, 'amount')]"),
		(By.XPATH, "//input[contains(@placeholder, 'Bid') or contains(@placeholder, 'Amount') or contains(@aria-label, 'Bid') or contains(@aria-label, 'amount') or contains(@name, 'bid') or contains(@id, 'bid')]"),
		(By.XPATH, "//div[contains(., 'Bid amount') or contains(., 'Amount')]//input"),
		(By.CSS_SELECTOR, "input[type='number'], input[role='spinbutton'], input[aria-label*='amount' i], input[name*='amount' i], input[id*='amount' i]"),
	]
	for by, value in selectors:
		try:
			elements = driver.find_elements(by, value)
		except Exception:
			elements = []
		for element in elements:
			if element.is_displayed():
				amount_input = element
				break
		if amount_input:
			break

	if amount_input is None:
		js_set_amount = driver.execute_script(
			"""
			const selectors = [
			  'input[type="number"]',
			  'input[role="spinbutton"]',
			  'input[aria-label*="amount" i]',
			  'input[name*="amount" i]',
			  'input[id*="amount" i]',
			  'input[aria-label*="bid" i]',
			  'input[placeholder*="amount" i]'
			];
			for (const selector of selectors) {
			  const candidates = [...document.querySelectorAll(selector)];
			  for (const el of candidates) {
			    const style = window.getComputedStyle(el);
			    if (!el || el.disabled) continue;
			    if (style.display === 'none' || style.visibility === 'hidden') continue;
			    el.focus();
			    el.value = arguments[0];
			    el.dispatchEvent(new Event('input', { bubbles: true }));
			    el.dispatchEvent(new Event('change', { bubbles: true }));
			    return true;
			  }
			}
			return false;
			""",
			str(amount),
		)
		amount_input = js_set_amount

	for element in driver.find_elements(By.CSS_SELECTOR, "textarea, input[type='text'], input:not([type])"):
		if not element.is_displayed():
			continue
		label = " ".join(
			filter(
				None,
				[
					element.get_attribute("placeholder"),
					element.get_attribute("aria-label"),
					element.get_attribute("name"),
					element.get_attribute("id"),
					element.get_attribute("data-testid"),
				],
			)
		).lower()
		if textarea is None and (
			"proposal" in label or "message" in label or "description" in label or "details" in label or "cover" in label or "letter" in label
		):
			textarea = element
		if textarea is None and element.tag_name.lower() == "textarea":
			textarea = element

	if textarea is None:
		textarea_set = driver.execute_script(
			"""
			const selectors = ['textarea', 'input[type="text"]', 'input:not([type])'];
			for (const selector of selectors) {
			  const candidates = [...document.querySelectorAll(selector)];
			  for (const el of candidates) {
			    const label = [
			      el.getAttribute('placeholder'),
			      el.getAttribute('aria-label'),
			      el.getAttribute('name'),
			      el.getAttribute('id'),
			      el.getAttribute('data-testid')
			    ].filter(Boolean).join(' ').toLowerCase();
			    const style = window.getComputedStyle(el);
			    if (style.display === 'none' || style.visibility === 'hidden') continue;
			    if (label.includes('proposal') || label.includes('message') || label.includes('description') || label.includes('details') || label.includes('cover') || label.includes('letter') || el.tagName.toLowerCase() === 'textarea') {
			      el.focus();
			      el.value = arguments[0];
			      el.dispatchEvent(new Event('input', { bubbles: true }));
			      el.dispatchEvent(new Event('change', { bubbles: true }));
			      return true;
			    }
			  }
			}
			return false;
			""",
			PROPOSAL_TEXT,
		)
		textarea = textarea_set

	if amount_input is not None and amount_input is not False:
		if hasattr(amount_input, "send_keys"):
			try:
				amount_input.clear()
			except Exception:
				pass
			amount_input.send_keys(str(amount))

	if textarea is not None and textarea is not False and hasattr(textarea, "send_keys"):
		try:
			textarea.clear()
		except Exception:
			pass
		textarea.send_keys(PROPOSAL_TEXT)

	return bool(amount_input) or bool(textarea)


def submit_bid_for_project(driver: webdriver.Chrome, wait: WebDriverWait, project_url: str) -> bool:
	if not is_project_url(project_url):
		print(f"Skipping non-project URL: {project_url}")
		return False

	print(f"Opening project: {project_url}")
	visited = set()
	for current_url in [project_url, f"{project_url.rstrip('/')}/details"]:
		current_url = current_url.replace("\u200b", "")
		if current_url in visited:
			continue
		visited.add(current_url)
		driver.get(current_url)
		# Freelancer loads the bid form dynamically; wait until the form or bid action is actually present.
		if not wait_for_bid_form(driver, wait):
			print("Bid form did not become ready in time; skipping project.")
			return False
		if "login" in driver.current_url.lower():
			print("Session expired; cannot access project page.")
			return False
		if "/proposals" in driver.current_url.lower():
			print("Skipping proposals page instead of project detail page.")
			return False

		if click_visible(
			driver,
			[
				(By.XPATH, "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'bid') or normalize-space(.)='Bid on the project' or normalize-space(.)='Bid' or normalize-space(.)='Place Bid' or normalize-space(.)='Submit Bid' or normalize-space(.)='Bid Now']"),
				(By.XPATH, "//a[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'bid') or normalize-space(.)='Bid' or normalize-space(.)='Place Bid' or normalize-space(.)='Bid Now']"),
				(By.CSS_SELECTOR, "button[title*='Bid' i], a[title*='Bid' i], [data-testid*='bid' i], button[aria-label*='Bid' i], button[aria-label*='place bid' i]"),
			],
		):
			break
	else:
		print("No bid button found; skipping project.")
		return False

	midpoint = get_project_midpoint(driver)
	if midpoint is None or midpoint < MIN_BID_THRESHOLD:
		print(f"Skipping project because midpoint is too low: {midpoint}")
		return False

	amount = str(int(round(midpoint)))
	if not fill_bid_form(driver, wait, amount):
		print("Bid form fields were not detected; skipping project.")
		return False

	try:
		button = wait.until(
			EC.element_to_be_clickable(
				(
					By.XPATH,
					"//button[normalize-space()='Submit Bid' or normalize-space()='Place Bid' or normalize-space()='Submit Offer' or normalize-space()='Send Bid' or normalize-space()='Bid on the project' or contains(., 'Place Bid') or contains(., 'Submit Bid') or contains(., 'Bid on the project')]"
				)
			)
		)
		button.click()
	except Exception:
		clicked = driver.execute_script(
			"""
			const tokens = ['place your bid', 'bid on the project', 'submit bid', 'place bid', 'send bid', 'submit offer', 'submit proposal'];
			const nodes = Array.from(document.querySelectorAll('button, input[type="submit"], a, [role="button"], div, span'));
			for (const el of nodes) {
			  const text = (el.innerText || el.textContent || el.value || '').toLowerCase();
			  const label = (el.getAttribute('aria-label') || '').toLowerCase();
			  const combined = `${text} ${label}`;
			  if (tokens.some(token => combined.includes(token))) {
			    el.click();
			    return true;
			  }
			}
			return false;
			"""
		)
		if not clicked:
			print("Final bid submission button was not found.")
			return False

	for _ in range(20):
		source = driver.page_source.lower()
		if any(token in source for token in ["bid submitted", "bid placed", "bid has been submitted", "proposal submitted"]):
			print("Bid submitted successfully.")
			return True
		if any(token in source for token in ["already bid", "already placed", "you have already bid", "bid is already"]):
			print("Bid already exists for this project.")
			return False
		time.sleep(1)
	return True


def browse_and_bid(driver: webdriver.Chrome, wait: WebDriverWait):
	driver.get(SEARCH_URL)
	wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
	time.sleep(3)

	project_links = get_project_links(driver)
	if not project_links:
		print("No project links found on the results page.")
		return

	print(f"Found {len(project_links)} candidate projects.")
	for project_url in project_links[:MAX_PROJECTS]:
		submit_bid_for_project(driver, wait, project_url)
		time.sleep(2)


def main() -> None:
	username = os.getenv("FREELANCER_EMAIL") or os.getenv("FREELANCER_USERNAME")
	password = os.getenv("FREELANCER_PASSWORD")

	driver = create_driver()
	wait = WebDriverWait(driver, 20)

	try:
		# Visit domain first; cookies can only be added for a loaded matching domain.
		driver.get("https://www.freelancer.com")

		if load_cookies(driver, COOKIE_FILE):
			driver.get(DASHBOARD_URL)
			if is_logged_in(driver, wait):
				print("Logged in using saved cookies.")
				print(f"Dashboard URL: {driver.current_url}")
			else:
				print("Saved cookies were stale or invalid; continuing with login.")

		if not is_logged_in(driver, wait):
			if not username or not password:
				raise RuntimeError(
					"Set FREELANCER_EMAIL and FREELANCER_PASSWORD environment variables first."
				)

			print("No valid cookie session found. Logging in with credentials...")
			if not do_login(driver, wait, username, password):
				raise RuntimeError(
					"Login did not complete in time. You may need to solve CAPTCHA/2FA in the browser."
				)

		driver.get(DASHBOARD_URL)
		if not is_logged_in(driver, wait):
			raise RuntimeError("Login appears unsuccessful: still redirected to login page.")

		save_cookies(driver, COOKIE_FILE)
		print(f"Login successful. Cookies saved to: {COOKIE_FILE}")
		print(f"Dashboard URL: {driver.current_url}")

		browse_and_bid(driver, wait)
		print("Automation finished.")
		input("Press Enter to close browser...")
	finally:
		driver.quit()


if __name__ == "__main__":
	main()
