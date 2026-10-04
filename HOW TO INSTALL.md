# BhavAI — Installation Guide

BhavAI is a lightweight terminal-based AI coding agent designed to help you work with your codebase directly from the command line.

## Prerequisites

Before installing BhavAI, make sure you have:

- **Python 3.11 or higher**
- **Git** (recommended)
- A valid **Sarvam AI API Key**

---

## Method 1 — Windows Installer

The easiest way to install BhavAI on Windows is by using the provided installer.

### Step 1: Download the Repository

Download the latest version of BhavAI from the official repository:

**GitHub:**  
https://github.com/BhavneeshBanga/BhavAI-Terminal-edition

Click:

**Code → Download ZIP**

### Step 2: Extract the ZIP

Once the ZIP file has been downloaded:

1. Extract the ZIP file.
2. Open the extracted BhavAI folder.
3. Locate the file:

```text
BhavAI-Install.bat
```

### Step 3: Run the Installer

Double-click:

```text
BhavAI-Install.bat
```

The installer will set up BhavAI on your Windows system.

---

# Method 2 — Install Using pip

If you prefer installing BhavAI manually from the source code, use the following method.

### Step 1: Clone the Repository

```bash
git clone https://github.com/BhavneeshBanga/BhavAI-Terminal-edition.git
```

Navigate into the project directory:

```bash
cd BhavAI-Terminal-edition
```

### Step 2: Install BhavAI

Run:

```bash
pip install -e .
```

The `-e` option installs BhavAI in **editable mode**, allowing you to run the `bhav` command while working directly with the source code.

---

# Configure Your API Key

BhavAI requires a Sarvam AI API key to communicate with the LLM.

Create a `.env` file in your working directory and add:

```env
SARVAM_API_KEY=your_sarvam_api_key_here
```

You can obtain your API key from the Sarvam AI dashboard.

---

# Verify the Installation

After installation, open a new terminal and run:

```bash
bhav --help
```

If the installation was successful, you should see the BhavAI command-line documentation and available commands.

You can also start an interactive BhavAI session using:

```bash
bhav wake up
```

---

# Getting Started

Once BhavAI is running, you can give it instructions directly from your terminal.

For example:

```text
> review the folder structure
```

```text
> explain the README file
```

```text
> create a Python Flask application
```

You can switch between the available modes using:

```text
mode plan
```

or:

```text
mode agent
```

To exit BhavAI:

```text
exit
```

---

# Troubleshooting

### `bhav` command is not recognized

If Windows cannot find the `bhav` command, try:

1. Close the current terminal.
2. Open a new terminal.
3. Make sure Python and its `Scripts` directory are added to your system `PATH`.
4. Re-run:

```bash
pip install -e .
```

### Check Python Version

Run:

```bash
python --version
```

BhavAI requires **Python 3.11 or newer**.

### Check pip

Run:

```bash
pip --version
```

---

## Official Repository

For source code, updates, issues, and the latest installation instructions, visit:

https://github.com/BhavneeshBanga/BhavAI-Terminal-edition

**BhavAI — Your AI coding agent in the terminal.**