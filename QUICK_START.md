# ⚡ QUICK START - 5 MINUTE SETUP

**Get transaction locking running in just 5 minutes**

---

## Pre-Check (30 seconds)

Verify you have:
- [ ] Python 3.8+ installed
- [ ] MySQL running
- [ ] BBMS project folder
- [ ] Admin access to database

---

## Step 1: Database Setup (1 minute)

```bash
cd d:\BBMS
mysql -u root -p blood_bank_db < transaction_schema.sql
```

**Check**: Should complete without errors. Look for: ✅ "Isolation level set"

---

## Step 2: Install Dependencies (1 minute)

```bash
pip install -r requirements.txt
```

**Check**: Should show mysql-connector-python==8.0.33 installed

---

## Step 3: Update app.py (2 minutes)

**Find line** with `from rbac import` and **add after it**:

```python
from transaction_routes import register_transaction_routes
```

**Find line** with `app = Flask(__name__)` and **add after it**:

```python
register_transaction_routes(app)
```

**Done!** You can remove the old `@app.route('/requests/<id>/update_status')` if it exists.

---

## Step 4: Start & Test (1 minute)

```bash
python app.py
```

**In another terminal:**

```bash
curl http://localhost:5000/api/requests/pending
```

**Check**: Should return JSON (maybe with error if not logged in - that's OK!)

---

## Done! ✅

You're done! Your system now has:
- ✅ Pessimistic locking
- ✅ Race condition prevention
- ✅ Atomic transactions
- ✅ HTTP API endpoints

**Next Steps**:
1. Login and test approval: Read [TRANSACTION_CHEATSHEET.md](TRANSACTION_CHEATSHEET.md)
2. Run full tests: See [TRANSACTION_INTEGRATION_GUIDE.md#5-testing](TRANSACTION_INTEGRATION_GUIDE.md#5-testing-the-implementation)
3. Deploy: Follow [TRANSACTION_INTEGRATION_GUIDE.md#9-deployment](TRANSACTION_INTEGRATION_GUIDE.md#9-deployment-checklist)

---

## If Something Goes Wrong

| Error | Fix |
|-------|-----|
| "No module named mysql" | `pip install mysql-connector-python==8.0.33` |
| SQL error running schema | Check MySQL is running, database exists |
| ImportError in app.py | Check indentation, make sure imports are at module level |
| Port 5000 already in use | `python app.py --port=5001` |
| 404 on /api/requests/pending | Stop app, restart it |

---

**Questions?** → Read [DOCUMENTATION_INDEX.md](DOCUMENTATION_INDEX.md)

**Full setup?** → Read [TRANSACTION_INTEGRATION_GUIDE.md](TRANSACTION_INTEGRATION_GUIDE.md)

**Need examples?** → Read [TRANSACTION_CHEATSHEET.md](TRANSACTION_CHEATSHEET.md)
