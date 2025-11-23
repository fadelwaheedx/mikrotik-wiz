# How to Host this Archive on GitHub Pages

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
