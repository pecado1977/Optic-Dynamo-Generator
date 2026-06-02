# GitHub Upload Checklist

Before the first commit:

1. Replace the placeholder in `CITATION.cff`:

   ```text
   https://github.com/REPLACE_WITH_USERNAME/REPLACE_WITH_REPOSITORY
   ```

2. Optional cleanup before `git add .`:

   ```bash
   ./scripts/clean_generated_outputs.sh
   ```

   The `.gitignore` already ignores `.DS_Store`, `__pycache__` and Xcode
   `.derivedData`, so this is mostly housekeeping.

3. Run the Python simulator:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ./scripts/run_python_experiment.sh
   ```

4. Build the Objective-C AppKit app:

   ```bash
   ./scripts/build_xcode_app.sh
   ```

5. Commit:

   ```bash
   git init
   git add .
   git commit -m "Initial WR AMCC-1000 paraformer simulator"
   ```

6. Push to GitHub:

   ```bash
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
   git push -u origin main
   ```
