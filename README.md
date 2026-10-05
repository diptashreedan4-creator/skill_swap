# Smart Student Skill Exchange & Peer Learning Management System

A beginner-friendly full-stack Flask + SQLite project.

## Features
- Student registration/login
- Student profile
- Skills offered and skills wanted
- Compatibility-based peer matching
- Session requests
- Accept/reject/complete/cancel workflow
- Ratings and reviews
- SQLite database
- Responsive UI

## Setup

### 1. Install Python
Install Python 3.10+.

### 2. Open terminal in this folder

### 3. Create a virtual environment

Windows:
```bash
python -m venv venv
venv\Scripts\activate
```

macOS/Linux:
```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. Install dependencies
```bash
pip install -r requirements.txt
```

### 5. Run
```bash
python app.py
```

### 6. Open
http://127.0.0.1:5000

The SQLite database is created automatically on first run.

## Recommended demonstration
Create two accounts.

Account A:
- Offers: Python, C
- Wants: Web Development

Account B:
- Offers: Web Development
- Wants: Python

The matching page should identify them as compatible.
