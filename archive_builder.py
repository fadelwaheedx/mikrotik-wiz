import os
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import shutil

class MikroTikArchiver:
    BASE_URL = "https://buananet.com/mikrotik/"
    OUTPUT_DIR = "MikroTik_Archive"
    IMAGES_DIR = "images"
    SCRIPTS_DIR = "scripts"
    ASSETS_DIR = "assets"

    # Link Hunting Patterns
    LINK_PATTERNS = [
        r'(https?://(?:www\.)?drive\.google\.com/[^\s"\']+)',
        r'(https?://(?:www\.)?mediafire\.com/[^\s"\']+)',
        r'(https?://(?:www\.)?mega\.nz/[^\s"\']+)',
        r'(https?://(?:www\.)?dropbox\.com/[^\s"\']+)',
        r'(https?://(?:www\.)?github\.com/[^\s"\']+)',
        r'(https?://[^\s"\']+\.(?:rsc|txt|html|zip|rar|7z))'
    ]

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; MikroTikArchiver/1.0)"
        })
        self.scripts_data = []

    def setup_directories(self):
        """Creates the necessary folder structure."""
        # We don't wipe the directory to avoid accidental data loss during dev,
        # but in production it might be cleaner.
        for d in [self.IMAGES_DIR, self.SCRIPTS_DIR, self.ASSETS_DIR]:
            path = os.path.join(self.OUTPUT_DIR, d)
            os.makedirs(path, exist_ok=True)

        print(f"[*] Directories prepared in {self.OUTPUT_DIR}/")

    def fetch_main_list(self):
        """Crawls the main page to get all script links."""
        print("[*] Fetching main list...")
        resp = self.session.get(self.BASE_URL)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        links = soup.find_all('a', href=True)

        for a in links:
            href = a['href']

            # Skip anchors and known non-script pages
            if '#' in href:
                continue
            if href in ['/', 'index.html', 'contact.html', 'updates.html', 'docs.html', 'login/', 'javascript:void(0)']:
                continue
            if any(x in href for x in ['facebook.com', 'github.com', 'twitter.com']):
                 if href.startswith('http'):
                     continue

            full_url = urljoin(self.BASE_URL, href)

            # Extra safety: Script pages should belong to the base path
            if not full_url.startswith(self.BASE_URL):
                continue

            if full_url == self.BASE_URL:
                continue

            # Skip the Alphabet links if they somehow passed (they usually have #)
            # But just in case they are like "mikrotik/A" (unlikely).

            # Extract Title
            title = a.get_text(strip=True)
            if not title:
                continue

            # Deduplication check
            if any(s['url'] == full_url for s in self.scripts_data):
                continue

            self.scripts_data.append({
                "title": title,
                "url": full_url,
                "slug": self._slugify(title)
            })

        print(f"[*] Found {len(self.scripts_data)} potential scripts.")

    def _slugify(self, text):
        """Simple slugify for filenames."""
        text = text.lower()
        text = re.sub(r'[^a-z0-9]+', '-', text)
        return text.strip('-')

    def process_scripts(self, limit=None):
        """Process each script: download content, images, and find links."""
        print("[*] Processing scripts...")
        count = 0
        for script in self.scripts_data:
            if limit and count >= limit:
                break

            try:
                self._process_single_script(script)
                count += 1
                time.sleep(0.5) # Mild Rate limiting
            except Exception as e:
                print(f"[!] Error processing {script['title']}: {e}")

    def _process_single_script(self, script):
        print(f"    -> Processing: {script['title']}")
        try:
            resp = self.session.get(script['url'], timeout=10)
        except Exception as e:
            print(f"       [!] Fetch error: {e}")
            return

        if resp.status_code != 200:
            print(f"       [!] Status {resp.status_code}")
            return

        soup = BeautifulSoup(resp.text, 'html.parser')

        # Extract Content
        content = soup.find('div', class_='welcome')
        if not content:
            h1 = soup.find('h1')
            if h1:
                content = h1.find_next_sibling('pre')

        if not content:
            content = soup.find('pre')

        if not content:
            script['content'] = "<p><em>Content extraction failed or page is empty.</em></p>"
            script['attachments'] = []
            return

        # Link Hunting
        script['attachments'] = self._find_attachments(str(content))

        # Image Downloading & rewriting
        self._download_images(content, script['slug'])

        # Store processed HTML
        script['content'] = str(content)

    def _find_attachments(self, html_content):
        attachments = []
        seen_links = set()

        for pattern in self.LINK_PATTERNS:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            for match in matches:
                if match not in seen_links:
                    clean_link = match.strip('"\';<>()')
                    # Filter out internal relative links or common false positives if any
                    if not clean_link.startswith('http'):
                         continue
                    attachments.append(clean_link)
                    seen_links.add(match)

        return attachments

    def _download_images(self, soup_element, file_prefix):
        """Finds img tags, downloads them, rewrites src."""
        images = soup_element.find_all('img')
        for i, img in enumerate(images):
            src = img.get('src')
            if not src:
                continue

            # Resolve absolute URL
            img_url = urljoin(self.BASE_URL, src)

            # Skip external tracking images if known (optional, but good practice)
            if 'hits.sh' in img_url or 'facebook.com' in img_url:
                continue

            # Generate local filename
            path = urlparse(img_url).path
            ext = os.path.splitext(path)[1]
            if not ext or len(ext) > 5:
                ext = '.jpg' # Default

            filename = f"{file_prefix}_{i}{ext}"
            local_path = os.path.join(self.OUTPUT_DIR, self.IMAGES_DIR, filename)

            # Download
            try:
                img_resp = self.session.get(img_url, stream=True, timeout=10)
                if img_resp.status_code == 200:
                    with open(local_path, 'wb') as f:
                        img_resp.raw.decode_content = True
                        shutil.copyfileobj(img_resp.raw, f)

                    # Rewrite src to relative path from scripts/ folder
                    img['src'] = f"../{self.IMAGES_DIR}/{filename}"

                    # Remove fixed dimensions
                    if img.has_attr('width'): del img['width']
                    if img.has_attr('height'): del img['height']
                    if img.has_attr('style'): del img['style'] # Remove inline styles that might mess up layout

                else:
                    print(f"       [!] Failed to download image: {img_url}")
            except Exception as e:
                print(f"       [!] Error downloading image: {e}")

    def generate_site(self):
        """Generates the static HTML files."""
        print("[*] Generating static site...")

        self._create_assets()
        self._generate_index()
        for script in self.scripts_data:
            if 'content' in script:
                self._generate_script_page(script)

    def _create_assets(self):
        """Creates CSS and JS files."""
        css_content = """
:root {
    --bg-color: #1a1a1a;
    --text-color: #e0e0e0;
    --sidebar-bg: #252525;
    --accent-color: #00ff9d;
    --code-bg: #000000;
    --code-text: #00ff00;
}
body {
    margin: 0;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    background-color: var(--bg-color);
    color: var(--text-color);
    display: flex;
    height: 100vh;
    overflow: hidden;
}
/* Sidebar */
.sidebar {
    width: 300px;
    background-color: var(--sidebar-bg);
    border-right: 1px solid #333;
    display: flex;
    flex-direction: column;
    height: 100%;
    flex-shrink: 0;
}
.search-box {
    padding: 15px;
    border-bottom: 1px solid #333;
}
.search-box input {
    width: 100%;
    padding: 8px;
    box-sizing: border-box;
    background: #333;
    border: none;
    color: white;
    border-radius: 4px;
}
.nav-list {
    flex: 1;
    overflow-y: auto;
    list-style: none;
    padding: 0;
    margin: 0;
}
.nav-item a {
    display: block;
    padding: 12px 15px;
    color: #bbb;
    text-decoration: none;
    border-bottom: 1px solid #2a2a2a;
    transition: background 0.2s;
    font-size: 0.9rem;
}
.nav-item a:hover {
    background-color: #333;
    color: var(--accent-color);
}
.nav-item.hidden {
    display: none;
}

/* Main Content */
.main-content {
    flex: 1;
    padding: 40px;
    overflow-y: auto;
    position: relative;
}
h1 { color: var(--accent-color); border-bottom: 1px solid #333; padding-bottom: 10px; }
a { color: var(--accent-color); }

/* Code Blocks */
pre {
    background-color: var(--code-bg);
    color: var(--code-text);
    padding: 15px;
    border-radius: 5px;
    overflow-x: auto;
    font-family: 'Consolas', 'Monaco', monospace;
    border: 1px solid #333;
    white-space: pre-wrap; /* Wrap text inside pre */
    word-wrap: break-word;
}
code { font-family: inherit; }

/* Images in content */
.script-content img {
    max-width: 100%;
    height: auto;
    border: 1px solid #444;
    border-radius: 4px;
    margin: 10px 0;
}

/* Attachments Box */
.attachments-box {
    background-color: #2d2d2d;
    border-left: 4px solid #ffcc00;
    padding: 15px;
    margin-bottom: 20px;
    border-radius: 4px;
}
.attachments-box h3 { margin-top: 0; color: #ffcc00; }
.download-btn {
    display: inline-block;
    background: #444;
    color: white;
    padding: 8px 12px;
    border-radius: 4px;
    text-decoration: none;
    margin-right: 10px;
    margin-bottom: 5px;
    border: 1px solid #555;
}
.download-btn:hover { background: #555; }

/* Dashboard Grid */
.dashboard-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
    gap: 20px;
}
.grid-item {
    background: var(--sidebar-bg);
    padding: 20px;
    border-radius: 8px;
    transition: transform 0.2s;
    border: 1px solid #333;
}
.grid-item:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 8px rgba(0,0,0,0.3);
    border-color: var(--accent-color);
}
.grid-item h3 { margin-top: 0; font-size: 1em; color: #eee; }
.grid-item a { text-decoration: none; color: inherit; display: block; height: 100%; }

/* Responsive */
@media (max-width: 768px) {
    body { flex-direction: column; overflow: auto; height: auto; }
    .sidebar { width: 100%; height: 300px; border-right: none; border-bottom: 1px solid #333; }
    .main-content { overflow-y: visible; }
}
"""

        js_content = """
function filterScripts() {
    const input = document.getElementById('searchInput');
    const filter = input.value.toUpperCase();
    const ul = document.getElementById('navList');
    const li = ul.getElementsByTagName('li');

    for (let i = 0; i < li.length; i++) {
        const a = li[i].getElementsByTagName("a")[0];
        const txtValue = a.textContent || a.innerText;
        if (txtValue.toUpperCase().indexOf(filter) > -1) {
            li[i].classList.remove('hidden');
        } else {
            li[i].classList.add('hidden');
        }
    }
}
"""
        with open(os.path.join(self.OUTPUT_DIR, self.ASSETS_DIR, "style.css"), "w") as f:
            f.write(css_content)
        with open(os.path.join(self.OUTPUT_DIR, self.ASSETS_DIR, "script.js"), "w") as f:
            f.write(js_content)

    def _get_sidebar_html(self, active_slug=None):
        """Generates the sidebar HTML."""
        items = []
        for script in self.scripts_data:
            if active_slug is None:
                # From Index
                link = f"scripts/{script['slug']}.html"
            else:
                # From Script Page
                link = f"{script['slug']}.html"

            active_class = 'style="color: var(--accent-color);"' if active_slug == script['slug'] else ''
            items.append(f'<li class="nav-item"><a href="{link}" {active_class}>{script["title"]}</a></li>')

        return f"""
        <div class="sidebar">
            <div class="search-box">
                <input type="text" id="searchInput" onkeyup="filterScripts()" placeholder="Search scripts...">
            </div>
            <ul class="nav-list" id="navList">
                {''.join(items)}
            </ul>
        </div>
        """

    def _generate_index(self):
        """Generates the main dashboard index.html."""

        grid_items = []
        for script in self.scripts_data:
            grid_items.append(f"""
            <div class="grid-item">
                <a href="scripts/{script['slug']}.html">
                    <h3>{script['title']}</h3>
                </a>
            </div>
            """)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MikroTik Script Archive</title>
    <link rel="stylesheet" href="assets/style.css">
</head>
<body>
    {self._get_sidebar_html(active_slug=None)}
    <div class="main-content">
        <h1>MikroTik Script Archive Dashboard</h1>
        <p>Welcome to the offline archive of {len(self.scripts_data)} MikroTik RouterOS scripts. Select a script from the sidebar or the grid below.</p>
        <p><em>Archived on {time.strftime('%Y-%m-%d')}</em></p>
        <div class="dashboard-grid">
            {''.join(grid_items)}
        </div>
    </div>
    <script src="assets/script.js"></script>
</body>
</html>
"""
        with open(os.path.join(self.OUTPUT_DIR, "index.html"), "w") as f:
            f.write(html)

    def _generate_script_page(self, script):
        """Generates an individual script page."""

        # Build Attachments HTML
        attachments_html = ""
        if script['attachments']:
            links = []
            for att in script['attachments']:
                links.append(f'<a href="{att}" class="download-btn" target="_blank">⬇ {att.split("/")[-1] if "/" in att else "Download"}</a>')

            attachments_html = f"""
            <div class="attachments-box">
                <h3>📂 Attached Files / External Links</h3>
                {''.join(links)}
            </div>
            """

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{script['title']}</title>
    <link rel="stylesheet" href="../assets/style.css">
</head>
<body>
    {self._get_sidebar_html(active_slug=script['slug'])}
    <div class="main-content">
        <h1>{script['title']}</h1>
        {attachments_html}
        <div class="script-content">
            {script['content']}
        </div>
    </div>
    <script src="../assets/script.js"></script>
</body>
</html>
"""
        with open(os.path.join(self.OUTPUT_DIR, self.SCRIPTS_DIR, f"{script['slug']}.html"), "w") as f:
            f.write(html)

    def generate_guide(self):
        """Generates HOW_TO_HOST.md"""
        content = """# How to Host this Archive on GitHub Pages

This archive is designed to be hosted freely on GitHub Pages. Follow these steps to get it online.

## Prerequisites
1. A GitHub account.
2. Git installed on your computer.

## Steps

1. **Create a new Repository:**
   - Go to GitHub and create a new repository (e.g., `mikrotik-archive`).
   - Make it **Public**.

2. **Initialize Git in the output folder:**
   Open your terminal or command prompt inside the `MikroTik_Archive` folder (the folder containing `index.html`) and run:

   ```bash
   git init
   git add .
   git commit -m "Initial commit of MikroTik Archive"
   ```

3. **Push to GitHub:**
   Replace `YOUR_USERNAME` and `YOUR_REPO_NAME` with your actual details:

   ```bash
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
   git push -u origin main
   ```

4. **Enable GitHub Pages:**
   - Go to your repository settings on GitHub.
   - Navigate to the **Pages** section (usually on the left sidebar).
   - Under **Source**, select `Deploy from a branch`.
   - Select `main` branch and `/ (root)` folder.
   - Click **Save**.

5. **Done!**
   Your site will be live at `https://YOUR_USERNAME.github.io/YOUR_REPO_NAME/` in a few minutes.
"""
        with open(os.path.join(self.OUTPUT_DIR, "HOW_TO_HOST.md"), "w") as f:
            f.write(content)

    def run(self, limit=None):
        self.setup_directories()
        self.fetch_main_list()
        self.process_scripts(limit=limit)
        self.generate_site()
        self.generate_guide()
        print("[*] Archiving complete! Check 'MikroTik_Archive/' folder.")

if __name__ == "__main__":
    archiver = MikroTikArchiver()
    # Run without limit to archive everything
    archiver.run()
